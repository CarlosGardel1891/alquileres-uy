"""End-to-end tests for the pipeline + CLI + integration with Fase 2."""

from __future__ import annotations

import importlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from alquileres_uy.models.config import TrainingConfig
from alquileres_uy.models.pipeline import dry_run, run

_CLI_SPEC = importlib.util.spec_from_file_location(
    "train_models_cli", Path(__file__).resolve().parents[2] / "scripts" / "train_models.py"
)
_CLI_MODULE = importlib.util.module_from_spec(_CLI_SPEC)
_CLI_SPEC.loader.exec_module(_CLI_MODULE)


def _base_config(etl_run_dir: Path, output_dir: Path, **kwargs) -> TrainingConfig:
    defaults = {
        "etl_run_dir": etl_run_dir,
        "output_dir": output_dir,
        "fixture_mode": True,
        "seed": 42,
    }
    defaults.update(kwargs)
    return TrainingConfig(**defaults)


# ---- Pipeline (in-process) ------------------------------------------


def test_pipeline_dry_run_returns_plan(model_etl_run_dir, isolated_output_dir):
    plan = dry_run(_base_config(model_etl_run_dir, isolated_output_dir))
    assert plan["status"] == "dry-run-ok"
    assert plan["data_mode"] == "fixture"
    assert "baseline" in plan["models_planned"]
    assert plan["split_plan"]["rows"]["train"] > 0


def test_pipeline_classical_run_completes(model_etl_run_dir, isolated_output_dir):
    result = run(_base_config(model_etl_run_dir, isolated_output_dir))
    assert result.status == "completed"
    assert result.data_mode == "fixture"
    assert result.serving_candidate in {"baseline", "linear", "lightgbm"}
    assert result.output_dir.is_dir()


def test_pipeline_all_four_models_when_torch(model_etl_run_dir, isolated_output_dir):
    pytest.importorskip("torch")
    result = run(_base_config(model_etl_run_dir, isolated_output_dir, include_torch=True))
    assert "torch" in result.metrics["validation"]
    assert result.serving_candidate != "torch"


def test_pipeline_writes_all_artifacts(model_etl_run_dir, isolated_output_dir):
    result = run(_base_config(model_etl_run_dir, isolated_output_dir))
    for name in (
        "metrics.json",
        "model_selection.json",
        "dataset_profile.json",
        "split_manifest.json",
        "reproducibility.json",
        "training_summary.json",
        "training_lineage.json",
        "predictions.parquet",
        "worst_errors.csv",
        "error_analysis.json",
    ):
        assert (result.output_dir / name).is_file(), f"missing {name}"
    assert (result.output_dir / "serving_bundle" / "model.joblib").is_file()
    for name in ("predicted_vs_actual.png", "feature_importance.png", "residuals.png"):
        assert (result.output_dir / "plots" / name).is_file(), f"missing plot {name}"


def test_pipeline_learned_model_beats_baseline(model_etl_run_dir, isolated_output_dir):
    result = run(_base_config(model_etl_run_dir, isolated_output_dir))
    baseline = result.metrics["validation"]["baseline"]["mae_usd"]
    best_learned = min(
        v["mae_usd"] for name, v in result.metrics["validation"].items() if name != "baseline"
    )
    assert best_learned < baseline


def test_pipeline_atomic_publish_leaves_no_tmp(model_etl_run_dir, isolated_output_dir):
    result = run(_base_config(model_etl_run_dir, isolated_output_dir))
    tmp_leftovers = list(isolated_output_dir.glob("*.tmp"))
    assert tmp_leftovers == []
    assert result.output_dir.parent == isolated_output_dir


def test_pipeline_no_overwrite(model_etl_run_dir, isolated_output_dir, monkeypatch):
    # Freezing the clock + uuid forces both runs to target the same directory
    # so we can prove that the second run refuses to overwrite the first.
    fixed_ts = datetime(2026, 1, 1, tzinfo=UTC)
    import alquileres_uy.models.pipeline as pipeline_module
    from alquileres_uy.models.artifacts import ArtifactError

    class _FrozenClock(datetime):
        @classmethod
        def now(cls, tz=None):  # type: ignore[override]
            return fixed_ts

    monkeypatch.setattr(pipeline_module, "datetime", _FrozenClock)
    monkeypatch.setattr(
        pipeline_module.uuid,
        "uuid4",
        lambda: type("u", (), {"hex": "deadbeefdeadbeefdeadbeefdeadbeef"})(),
    )

    result = run(_base_config(model_etl_run_dir, isolated_output_dir))
    with pytest.raises(ArtifactError, match="already exists"):
        run(_base_config(model_etl_run_dir, isolated_output_dir))
    # The original run directory must still be intact.
    assert result.output_dir.is_dir()


def test_pipeline_fixture_bundle_marked_not_deployable(model_etl_run_dir, isolated_output_dir):
    result = run(_base_config(model_etl_run_dir, isolated_output_dir))
    selection = json.loads((result.output_dir / "model_selection.json").read_text(encoding="utf-8"))
    assert selection["deployable"] is False
    metadata = json.loads(
        (result.output_dir / "serving_bundle" / "metadata.json").read_text(encoding="utf-8")
    )
    assert metadata["deployable"] is False


def test_pipeline_reproducibility_same_seed(model_etl_run_dir, isolated_output_dir):
    result_a = run(_base_config(model_etl_run_dir, isolated_output_dir))
    result_b = run(_base_config(model_etl_run_dir, isolated_output_dir))
    split_a = json.loads((result_a.output_dir / "split_manifest.json").read_text(encoding="utf-8"))
    split_b = json.loads((result_b.output_dir / "split_manifest.json").read_text(encoding="utf-8"))
    assert split_a["id_hashes"] == split_b["id_hashes"]
    metrics_a = json.loads((result_a.output_dir / "metrics.json").read_text(encoding="utf-8"))
    metrics_b = json.loads((result_b.output_dir / "metrics.json").read_text(encoding="utf-8"))
    for name in metrics_a["models"]:
        assert (
            abs(
                metrics_a["models"][name]["validation"]["mae_usd"]
                - metrics_b["models"][name]["validation"]["mae_usd"]
            )
            < 1e-6
        )


def test_pipeline_training_lineage_not_self_hashed(model_etl_run_dir, isolated_output_dir):
    result = run(_base_config(model_etl_run_dir, isolated_output_dir))
    lineage = json.loads((result.output_dir / "training_lineage.json").read_text(encoding="utf-8"))
    assert lineage["lineage_self_hashed"] is False
    assert "training_lineage.json" not in lineage["outputs_sha256"]


# ---- CLI ------------------------------------------------------------


def test_cli_dry_run_returns_zero(model_etl_run_dir, isolated_output_dir):
    exit_code = _CLI_MODULE.main(
        [
            "--fixture-mode",
            "--dry-run",
            "--etl-run-dir",
            str(model_etl_run_dir),
            "--output-dir",
            str(isolated_output_dir),
            "--seed",
            "42",
        ]
    )
    assert exit_code == 0


def test_cli_real_mode_without_approval_exits_2(model_etl_run_dir, isolated_output_dir):
    exit_code = _CLI_MODULE.main(
        [
            "--etl-run-dir",
            str(model_etl_run_dir),
            "--output-dir",
            str(isolated_output_dir),
            "--seed",
            "42",
        ]
    )
    assert exit_code == 2
    # No output artifacts must exist.
    assert list(isolated_output_dir.glob("*")) == []


def test_cli_fixture_with_approval_rejected(model_etl_run_dir, isolated_output_dir, tmp_path):
    approval = tmp_path / "approval.json"
    approval.write_text(json.dumps({"status": "ETL_PRODUCTION_VALIDATED"}))
    exit_code = _CLI_MODULE.main(
        [
            "--fixture-mode",
            "--etl-approval",
            str(approval),
            "--etl-run-dir",
            str(model_etl_run_dir),
            "--output-dir",
            str(isolated_output_dir),
        ]
    )
    assert exit_code == 2


def test_cli_include_torch_without_torch(monkeypatch, model_etl_run_dir, isolated_output_dir):
    import alquileres_uy.models.pipeline as pipeline_module

    monkeypatch.setattr(pipeline_module, "_torch_available", lambda: False)
    exit_code = _CLI_MODULE.main(
        [
            "--fixture-mode",
            "--include-torch",
            "--etl-run-dir",
            str(model_etl_run_dir),
            "--output-dir",
            str(isolated_output_dir),
        ]
    )
    assert exit_code == 2


def test_cli_wrong_hash_exits_2(tmp_path, copy_etl_fixture, isolated_output_dir):
    lineage = json.loads((copy_etl_fixture / "lineage.json").read_text(encoding="utf-8"))
    lineage["output_sha256"]["model_ready"] = "0" * 64
    (copy_etl_fixture / "lineage.json").write_text(json.dumps(lineage))
    exit_code = _CLI_MODULE.main(
        [
            "--fixture-mode",
            "--etl-run-dir",
            str(copy_etl_fixture),
            "--output-dir",
            str(isolated_output_dir),
        ]
    )
    assert exit_code == 2
    assert list(isolated_output_dir.glob("*")) == []


# ---- Integration Fase 2 → Fase 3 -----------------------------------


def test_phase2_etl_output_is_readable_by_training(tmp_path):
    """Actually run Fase 2 EtlPipeline on the shipped fixture and load the result.

    The shipped Fase 2 fixture only yields ~17 rows — too small to train
    four models, but big enough to verify that the training input contract
    accepts an untouched Fase 2 output.
    """
    from alquileres_uy.etl.config import EtlConfig
    from alquileres_uy.etl.pipeline import EtlPipeline

    etl_fixture = Path(__file__).resolve().parents[1] / "fixtures" / "etl" / "raw_run"
    exchange_rate = Path("config/exchange_rate.example.json").resolve()
    neighborhood_aliases = Path("config/neighborhood_aliases.json").resolve()
    output_dir = tmp_path / "etl-out"

    config = EtlConfig(
        input_run_dirs=(etl_fixture,),
        exchange_rate_path=exchange_rate,
        neighborhood_aliases_path=neighborhood_aliases,
        output_dir=output_dir,
        fixture_mode=True,
    )
    EtlPipeline(config).run()
    run_dir = next(output_dir.iterdir())

    from alquileres_uy.models.contracts import load_training_input

    inp = load_training_input(run_dir)
    assert inp.data_mode == "fixture"
    assert not inp.model_ready.empty
    # smoke: baseline can train on the Fase 2 fixture too
    from alquileres_uy.models.baseline import fit_baseline
    from alquileres_uy.models.split import temporal_split

    split = temporal_split(
        inp.model_ready, train_fraction=0.7, validation_fraction=0.15, test_fraction=0.15
    )
    baseline = fit_baseline(split.train, data_mode="fixture", input_hashes={})
    pred = baseline.predict(split.test)
    assert len(pred) == len(split.test)
