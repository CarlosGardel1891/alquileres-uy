"""Model selection: best-overall vs. serving-candidate.

The serving candidate is picked from the classical models only —
PyTorch stays out because the future FastAPI image will not bundle
Torch runtimes. Both decisions use validation metrics exclusively;
test metrics are only reported downstream.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .config import MODEL_NAMES, SERVING_ELIGIBLE_MODEL_NAMES

SERVING_TIE_TOLERANCE: float = 5.0  # USD


@dataclass(frozen=True)
class SelectionResult:
    best_overall_model: str
    serving_candidate: str
    tie_tolerance_usd: float
    eligible: tuple[str, ...]
    excluded: dict[str, str]
    validation_metrics: dict[str, dict[str, float]]
    data_mode: str

    def as_json(self, *, deployable: bool) -> dict[str, Any]:
        return {
            "best_overall_model": self.best_overall_model,
            "serving_candidate": self.serving_candidate,
            "criterion": "lowest validation MAE, then MAPE, then simplicity",
            "tie_tolerance_usd": self.tie_tolerance_usd,
            "eligible": list(self.eligible),
            "excluded": dict(self.excluded),
            "validation_metrics": self.validation_metrics,
            "data_mode": self.data_mode,
            "deployable": deployable,
            "blocked_reason": (None if deployable else "fixture training run"),
        }


def select_models(
    validation_metrics: dict[str, dict[str, float]],
    *,
    data_mode: str,
) -> SelectionResult:
    if not validation_metrics:
        raise ValueError("selection requires at least one model")

    def _key(model: str) -> tuple:
        m = validation_metrics[model]
        try:
            simplicity = SERVING_ELIGIBLE_MODEL_NAMES.index(model)
        except ValueError:
            simplicity = len(SERVING_ELIGIBLE_MODEL_NAMES)  # push non-classical last
        return (m["mae_usd"], m.get("mape_fraction", float("inf")), simplicity, model)

    overall = min(validation_metrics.keys(), key=_key)

    serving_candidates = {
        name: validation_metrics[name]
        for name in validation_metrics
        if name in SERVING_ELIGIBLE_MODEL_NAMES
    }
    if not serving_candidates:
        raise ValueError("no classical model was trained; serving candidate cannot be picked")

    # Serving choice: sort by MAE; if a simpler model is within tolerance of
    # the current best, prefer it.
    ranked = sorted(serving_candidates.keys(), key=_key)
    serving = ranked[0]
    for challenger in ranked[1:]:
        gap = validation_metrics[challenger]["mae_usd"] - validation_metrics[serving]["mae_usd"]
        if abs(gap) <= SERVING_TIE_TOLERANCE and SERVING_ELIGIBLE_MODEL_NAMES.index(
            challenger
        ) < SERVING_ELIGIBLE_MODEL_NAMES.index(serving):
            serving = challenger

    excluded: dict[str, str] = {}
    for name in MODEL_NAMES:
        if name in validation_metrics and name not in SERVING_ELIGIBLE_MODEL_NAMES:
            excluded[name] = "excluded from serving bundle by architecture decision"
        if name not in validation_metrics:
            excluded[name] = "not trained in this run"

    return SelectionResult(
        best_overall_model=overall,
        serving_candidate=serving,
        tie_tolerance_usd=SERVING_TIE_TOLERANCE,
        eligible=tuple(serving_candidates.keys()),
        excluded=excluded,
        validation_metrics=validation_metrics,
        data_mode=data_mode,
    )


__all__ = ["SERVING_TIE_TOLERANCE", "SelectionResult", "select_models"]
