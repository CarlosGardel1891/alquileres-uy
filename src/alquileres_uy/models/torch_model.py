"""PyTorch tabular regressor with lazy import.

The module exposes :func:`tune_torch_model` (train-only fit with early
stopping against validation) and :func:`refit_torch_model` (train +
validation refit for exactly ``best_epoch + 1`` epochs, no early
stopping, same seed and architecture). ``torch`` itself is only
imported when either function runs, so the classical training path (CI
job 1, ``pytest -m 'not torch'``) does not need the PyTorch wheel.

Serving path exclusion: PyTorch participates in the metric comparison
but is deliberately excluded from the serving bundle. Serialization
uses ``state_dict`` (not ``pickle``) so a small config JSON is enough
to rebuild the architecture on load.
"""

from __future__ import annotations

import json
import os
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .config import NUMERIC_FEATURES
from .features import (
    TorchVocabularies,
    build_torch_vocabularies,
    encode_torch_frame,
)

TORCH_MODEL_VERSION: str = "1.0.0"
_TORCH_MISSING_HELP = (
    "PyTorch is not installed. Install requirements-torch-cpu.txt "
    "before requesting --include-torch."
)


class TorchNotAvailableError(RuntimeError):
    """Raised when the caller asks for the torch model but torch is missing."""


def _import_torch():
    try:
        import torch

        return torch
    except ImportError as exc:  # pragma: no cover — env-specific
        raise TorchNotAvailableError(_TORCH_MISSING_HELP) from exc


@dataclass
class TorchTrainingHistory:
    train_loss: list[float] = field(default_factory=list)
    validation_loss: list[float] = field(default_factory=list)
    validation_mae: list[float] = field(default_factory=list)
    best_epoch: int = -1
    stopped_at_epoch: int = -1
    final_epochs: int | None = None


@dataclass
class TorchModelConfig:
    numeric_dim: int
    neighborhood_vocab_size: int
    property_vocab_size: int
    neighborhood_embedding_dim: int
    property_embedding_dim: int
    hidden_sizes: list[int]
    dropout: float

    def as_json(self) -> dict[str, Any]:
        return {
            "version": TORCH_MODEL_VERSION,
            "numeric_dim": self.numeric_dim,
            "neighborhood_vocab_size": self.neighborhood_vocab_size,
            "property_vocab_size": self.property_vocab_size,
            "neighborhood_embedding_dim": self.neighborhood_embedding_dim,
            "property_embedding_dim": self.property_embedding_dim,
            "hidden_sizes": list(self.hidden_sizes),
            "dropout": self.dropout,
        }


def _build_module(config: TorchModelConfig):
    torch = _import_torch()
    from torch import nn

    class TabularNet(nn.Module):
        def __init__(self, cfg: TorchModelConfig) -> None:
            super().__init__()
            self.neighborhood_embedding = nn.Embedding(
                cfg.neighborhood_vocab_size, cfg.neighborhood_embedding_dim
            )
            self.property_embedding = nn.Embedding(
                cfg.property_vocab_size, cfg.property_embedding_dim
            )
            input_dim = (
                cfg.numeric_dim + cfg.neighborhood_embedding_dim + cfg.property_embedding_dim
            )
            layers: list[nn.Module] = []
            current = input_dim
            for size in cfg.hidden_sizes:
                layers.append(nn.Linear(current, size))
                layers.append(nn.ReLU())
                layers.append(nn.Dropout(cfg.dropout))
                current = size
            layers.append(nn.Linear(current, 1))
            self.mlp = nn.Sequential(*layers)

        def forward(
            self,
            numeric: torch.Tensor,
            neighborhood_idx: torch.Tensor,
            property_idx: torch.Tensor,
        ) -> torch.Tensor:
            neighborhood = self.neighborhood_embedding(neighborhood_idx)
            prop = self.property_embedding(property_idx)
            joined = torch.cat([numeric, neighborhood, prop], dim=1)
            return self.mlp(joined).squeeze(-1)

    return TabularNet(config)


@dataclass
class TorchTabularModel:
    module: Any  # torch.nn.Module
    config: TorchModelConfig
    vocabularies: TorchVocabularies
    history: TorchTrainingHistory
    seed: int
    train_row_count: int
    stage: str = "tuning"  # "tuning" or "final"
    version: str = TORCH_MODEL_VERSION
    eligible_for_api_serving: bool = False

    def predict(self, frame: pd.DataFrame) -> np.ndarray:
        torch = _import_torch()
        self.module.eval()
        neighborhood_idx, property_idx, numeric = encode_torch_frame(frame, self.vocabularies)
        with torch.no_grad():
            output = self.module(
                torch.from_numpy(numeric),
                torch.from_numpy(neighborhood_idx),
                torch.from_numpy(property_idx),
            )
        prediction = output.detach().cpu().numpy().astype(float)
        return np.clip(prediction, a_min=0.0, a_max=None)

    def save(self, directory: Path) -> Path:
        torch = _import_torch()
        directory.mkdir(parents=True, exist_ok=True)
        state_path = directory / "state_dict.pt"
        torch.save(self.module.state_dict(), state_path)
        _write_json(directory / "config.json", self.config.as_json())
        _write_json(directory / "vocabularies.json", self.vocabularies.as_json())
        _write_json(
            directory / "numeric_scaler.json",
            {
                "mean": self.vocabularies.numeric_mean,
                "std": self.vocabularies.numeric_std,
                "impute_values": self.vocabularies.numeric_impute_values,
                "imputation_sources": self.vocabularies.imputation_sources,
                "feature_order": list(NUMERIC_FEATURES),
            },
        )
        _write_json(
            directory / "training_history.json",
            {
                "train_loss": list(self.history.train_loss),
                "validation_loss": list(self.history.validation_loss),
                "validation_mae": list(self.history.validation_mae),
                "best_epoch": self.history.best_epoch,
                "stopped_at_epoch": self.history.stopped_at_epoch,
                "final_epochs": self.history.final_epochs,
                "seed": self.seed,
                "train_row_count": self.train_row_count,
                "stage": self.stage,
                "eligible_for_api_serving": self.eligible_for_api_serving,
            },
        )
        return directory

    @classmethod
    def load(cls, directory: Path) -> TorchTabularModel:
        torch = _import_torch()
        config_payload = json.loads((directory / "config.json").read_text(encoding="utf-8"))
        vocab_payload = json.loads((directory / "vocabularies.json").read_text(encoding="utf-8"))
        history_payload = json.loads(
            (directory / "training_history.json").read_text(encoding="utf-8")
        )
        config = TorchModelConfig(
            numeric_dim=int(config_payload["numeric_dim"]),
            neighborhood_vocab_size=int(config_payload["neighborhood_vocab_size"]),
            property_vocab_size=int(config_payload["property_vocab_size"]),
            neighborhood_embedding_dim=int(config_payload["neighborhood_embedding_dim"]),
            property_embedding_dim=int(config_payload["property_embedding_dim"]),
            hidden_sizes=list(config_payload["hidden_sizes"]),
            dropout=float(config_payload["dropout"]),
        )
        vocabularies = TorchVocabularies(
            neighborhood=dict(vocab_payload["neighborhood"]),
            property_type=dict(vocab_payload["property_type"]),
            numeric_mean={str(k): float(v) for k, v in vocab_payload["numeric_mean"].items()},
            numeric_std={str(k): float(v) for k, v in vocab_payload["numeric_std"].items()},
            numeric_impute_values={
                str(k): float(v) for k, v in vocab_payload.get("numeric_impute_values", {}).items()
            },
            imputation_sources={
                str(k): str(v) for k, v in vocab_payload.get("imputation_sources", {}).items()
            },
        )
        module = _build_module(config)
        module.load_state_dict(
            torch.load(directory / "state_dict.pt", map_location="cpu", weights_only=True)
        )
        history = TorchTrainingHistory(
            train_loss=[float(v) for v in history_payload.get("train_loss", [])],
            validation_loss=[float(v) for v in history_payload.get("validation_loss", [])],
            validation_mae=[float(v) for v in history_payload.get("validation_mae", [])],
            best_epoch=int(history_payload.get("best_epoch", -1)),
            stopped_at_epoch=int(history_payload.get("stopped_at_epoch", -1)),
            final_epochs=(
                int(history_payload["final_epochs"])
                if history_payload.get("final_epochs") is not None
                else None
            ),
        )
        return cls(
            module=module,
            config=config,
            vocabularies=vocabularies,
            history=history,
            seed=int(history_payload.get("seed", 0)),
            train_row_count=int(history_payload.get("train_row_count", 0)),
            stage=str(history_payload.get("stage", "final")),
            eligible_for_api_serving=bool(history_payload.get("eligible_for_api_serving", False)),
        )


def _build_config(vocabs: TorchVocabularies, numeric_dim: int) -> TorchModelConfig:
    return TorchModelConfig(
        numeric_dim=numeric_dim,
        neighborhood_vocab_size=max(len(vocabs.neighborhood), 2),
        property_vocab_size=max(len(vocabs.property_type), 2),
        neighborhood_embedding_dim=min(8, max(2, len(vocabs.neighborhood) // 2)),
        property_embedding_dim=2,
        hidden_sizes=[64, 32],
        dropout=0.1,
    )


def tune_torch_model(
    train_frame: pd.DataFrame,
    validation_frame: pd.DataFrame,
    *,
    target_column: str,
    seed: int,
    max_epochs: int,
    patience: int,
    batch_size: int,
) -> TorchTabularModel:
    """Tune the torch model on train only, using validation for early stopping."""
    torch = _import_torch()
    from torch import nn
    from torch.utils.data import DataLoader, TensorDataset

    _seed_everything(seed)

    vocabularies = build_torch_vocabularies(train_frame)
    train_neigh, train_prop, train_numeric = encode_torch_frame(train_frame, vocabularies)
    val_neigh, val_prop, val_numeric = encode_torch_frame(validation_frame, vocabularies)
    train_target = (
        pd.to_numeric(train_frame[target_column], errors="coerce").astype(np.float32).to_numpy()
    )
    validation_target = (
        pd.to_numeric(validation_frame[target_column], errors="coerce")
        .astype(np.float32)
        .to_numpy()
    )

    config = _build_config(vocabularies, numeric_dim=train_numeric.shape[1])
    module = _build_module(config)
    optimizer = torch.optim.Adam(module.parameters(), lr=1e-3)
    loss_fn = nn.SmoothL1Loss()

    effective_batch = max(1, min(batch_size, len(train_frame)))
    dataset = TensorDataset(
        torch.from_numpy(train_numeric),
        torch.from_numpy(train_neigh),
        torch.from_numpy(train_prop),
        torch.from_numpy(train_target),
    )
    generator = torch.Generator()
    generator.manual_seed(seed)
    loader = DataLoader(
        dataset,
        batch_size=effective_batch,
        shuffle=True,
        num_workers=0,
        generator=generator,
    )

    val_numeric_t = torch.from_numpy(val_numeric)
    val_neigh_t = torch.from_numpy(val_neigh)
    val_prop_t = torch.from_numpy(val_prop)
    val_target_t = torch.from_numpy(validation_target)

    history = TorchTrainingHistory()
    best_state: dict[str, torch.Tensor] | None = None
    best_validation_mae = float("inf")
    epochs_since_improvement = 0

    for epoch in range(max_epochs):
        module.train()
        running_loss = 0.0
        seen = 0
        for numeric_batch, neigh_batch, prop_batch, target_batch in loader:
            optimizer.zero_grad()
            output = module(numeric_batch, neigh_batch, prop_batch)
            loss = loss_fn(output, target_batch)
            loss.backward()
            optimizer.step()
            batch_len = int(numeric_batch.shape[0])
            running_loss += float(loss.detach().item()) * batch_len
            seen += batch_len
        train_loss = running_loss / max(1, seen)
        module.eval()
        with torch.no_grad():
            predictions = module(val_numeric_t, val_neigh_t, val_prop_t)
            val_loss = float(loss_fn(predictions, val_target_t).item())
            val_mae = float(torch.mean(torch.abs(predictions - val_target_t)).item())

        history.train_loss.append(train_loss)
        history.validation_loss.append(val_loss)
        history.validation_mae.append(val_mae)

        if val_mae + 1e-6 < best_validation_mae:
            best_validation_mae = val_mae
            best_state = {k: v.detach().clone() for k, v in module.state_dict().items()}
            history.best_epoch = epoch
            epochs_since_improvement = 0
        else:
            epochs_since_improvement += 1
            if epochs_since_improvement >= patience:
                history.stopped_at_epoch = epoch
                break

    if history.stopped_at_epoch < 0:
        history.stopped_at_epoch = max_epochs - 1

    if best_state is not None:
        module.load_state_dict(best_state)

    return TorchTabularModel(
        module=module,
        config=config,
        vocabularies=vocabularies,
        history=history,
        seed=seed,
        train_row_count=int(len(train_frame)),
        stage="tuning",
    )


def refit_torch_model(
    train_validation_frame: pd.DataFrame,
    *,
    target_column: str,
    seed: int,
    batch_size: int,
    tuning_model: TorchTabularModel,
) -> TorchTabularModel:
    """Refit torch on train + validation for exactly best_epoch + 1 epochs."""
    torch = _import_torch()
    from torch import nn
    from torch.utils.data import DataLoader, TensorDataset

    _seed_everything(seed)

    vocabularies = build_torch_vocabularies(train_validation_frame)
    neigh_idx, prop_idx, numeric = encode_torch_frame(train_validation_frame, vocabularies)
    target = (
        pd.to_numeric(train_validation_frame[target_column], errors="coerce")
        .astype(np.float32)
        .to_numpy()
    )

    config = _build_config(vocabularies, numeric_dim=numeric.shape[1])
    module = _build_module(config)
    optimizer = torch.optim.Adam(module.parameters(), lr=1e-3)
    loss_fn = nn.SmoothL1Loss()

    effective_batch = max(1, min(batch_size, len(train_validation_frame)))
    dataset = TensorDataset(
        torch.from_numpy(numeric),
        torch.from_numpy(neigh_idx),
        torch.from_numpy(prop_idx),
        torch.from_numpy(target),
    )
    generator = torch.Generator()
    generator.manual_seed(seed)
    loader = DataLoader(
        dataset,
        batch_size=effective_batch,
        shuffle=True,
        num_workers=0,
        generator=generator,
    )

    best_epoch = tuning_model.history.best_epoch if tuning_model.history.best_epoch >= 0 else 0
    final_epochs = best_epoch + 1

    train_loss_history: list[float] = []
    for _epoch in range(final_epochs):
        module.train()
        running_loss = 0.0
        seen = 0
        for numeric_batch, neigh_batch, prop_batch, target_batch in loader:
            optimizer.zero_grad()
            output = module(numeric_batch, neigh_batch, prop_batch)
            loss = loss_fn(output, target_batch)
            loss.backward()
            optimizer.step()
            batch_len = int(numeric_batch.shape[0])
            running_loss += float(loss.detach().item()) * batch_len
            seen += batch_len
        train_loss_history.append(running_loss / max(1, seen))

    history = TorchTrainingHistory(
        train_loss=train_loss_history,
        validation_loss=[],
        validation_mae=[],
        best_epoch=best_epoch,
        stopped_at_epoch=final_epochs - 1,
        final_epochs=final_epochs,
    )
    return TorchTabularModel(
        module=module,
        config=config,
        vocabularies=vocabularies,
        history=history,
        seed=seed,
        train_row_count=int(len(train_validation_frame)),
        stage="final",
    )


def _seed_everything(seed: int) -> None:
    torch = _import_torch()
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.use_deterministic_algorithms(False)  # false to keep CPU embedding backward practical
    os.environ.setdefault("PYTHONHASHSEED", str(seed))


def _write_json(path: Path, payload: dict) -> None:
    path.write_bytes(
        (json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n").encode("utf-8")
    )


__all__ = [
    "TORCH_MODEL_VERSION",
    "TorchModelConfig",
    "TorchNotAvailableError",
    "TorchTabularModel",
    "TorchTrainingHistory",
    "refit_torch_model",
    "tune_torch_model",
]
