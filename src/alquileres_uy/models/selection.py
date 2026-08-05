"""Model selection: best-overall vs. serving-candidate.

Two independent decisions:

* **best_overall_model** — smallest validation MAE across every trained
  candidate (torch included). Ties break by MAPE then by model name.
  Simplicity is *not* a criterion for best-overall.
* **serving_candidate** — restricted to the classical models (baseline
  / linear / lightgbm). The tie set is anchored to the smallest
  eligible MAE: any model whose MAE is within ``SERVING_TIE_TOLERANCE``
  USD of that anchor is a candidate, and the simplest of those wins.
  This avoids "chained" tie logic where model A justifies model B
  which justifies model C even though C is outside the tolerance of A.

Test metrics never influence selection.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from .config import MODEL_NAMES, SERVING_ELIGIBLE_MODEL_NAMES

SERVING_TIE_TOLERANCE: float = 5.0  # USD


@dataclass(frozen=True)
class SelectionResult:
    best_overall_model: str
    serving_candidate: str
    tie_tolerance_usd: float
    best_eligible_mae: float
    practical_tie_threshold: float
    practical_tie_models: tuple[str, ...]
    simplicity_order: tuple[str, ...]
    eligible: tuple[str, ...]
    excluded: dict[str, str]
    validation_metrics: dict[str, dict[str, float]]
    data_mode: str

    def as_json(self, *, deployable: bool) -> dict[str, Any]:
        return {
            "best_overall_model": self.best_overall_model,
            "serving_candidate": self.serving_candidate,
            "criterion": (
                "best_overall: (validation_mae, validation_mape, model_name); "
                "serving_candidate: anchor to best eligible MAE, then simplest inside "
                "SERVING_TIE_TOLERANCE"
            ),
            "tie_tolerance_usd": self.tie_tolerance_usd,
            "best_eligible_mae": self.best_eligible_mae,
            "practical_tie_threshold": self.practical_tie_threshold,
            "practical_tie_models": list(self.practical_tie_models),
            "simplicity_order": list(self.simplicity_order),
            "eligible": list(self.eligible),
            "excluded": dict(self.excluded),
            "validation_metrics": self.validation_metrics,
            "data_mode": self.data_mode,
            "deployable": deployable,
            "blocked_reason": (None if deployable else "fixture training run"),
        }


def _assert_finite(validation_metrics: dict[str, dict[str, float]]) -> None:
    for name, entry in validation_metrics.items():
        for key in ("mae_usd", "mape_fraction"):
            value = entry.get(key)
            if value is None or not isinstance(value, int | float):
                raise ValueError(f"validation metric '{name}.{key}' must be a finite number")
            if math.isnan(float(value)) or math.isinf(float(value)):
                raise ValueError(f"validation metric '{name}.{key}' must be finite (got {value!r})")


def select_models(
    validation_metrics: dict[str, dict[str, float]],
    *,
    data_mode: str,
) -> SelectionResult:
    if not validation_metrics:
        raise ValueError("selection requires at least one model")
    _assert_finite(validation_metrics)

    # ---- best overall: MAE → MAPE → name -----------------------------
    def _overall_key(model: str) -> tuple:
        entry = validation_metrics[model]
        return (
            float(entry["mae_usd"]),
            float(entry.get("mape_fraction", float("inf"))),
            model,
        )

    overall = min(validation_metrics.keys(), key=_overall_key)

    # ---- serving candidate: anchored practical-tie set ---------------
    serving_candidates = {
        name: validation_metrics[name]
        for name in validation_metrics
        if name in SERVING_ELIGIBLE_MODEL_NAMES
    }
    if not serving_candidates:
        raise ValueError("no classical model was trained; serving candidate cannot be picked")

    best_eligible_mae = min(entry["mae_usd"] for entry in serving_candidates.values())
    threshold = best_eligible_mae + SERVING_TIE_TOLERANCE

    practical_tie: list[str] = [
        name for name, entry in serving_candidates.items() if float(entry["mae_usd"]) <= threshold
    ]
    # Preserve the canonical simplicity order.
    practical_tie_ordered = tuple(
        name for name in SERVING_ELIGIBLE_MODEL_NAMES if name in practical_tie
    )
    if not practical_tie_ordered:
        # Numerical safety net — should never trigger since the anchor
        # itself is inside the tolerance.
        practical_tie_ordered = tuple(
            name for name in SERVING_ELIGIBLE_MODEL_NAMES if name in serving_candidates
        )

    serving = practical_tie_ordered[0]

    # ---- excluded reasons --------------------------------------------
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
        best_eligible_mae=float(best_eligible_mae),
        practical_tie_threshold=float(threshold),
        practical_tie_models=practical_tie_ordered,
        simplicity_order=tuple(SERVING_ELIGIBLE_MODEL_NAMES),
        eligible=tuple(serving_candidates.keys()),
        excluded=excluded,
        validation_metrics=validation_metrics,
        data_mode=data_mode,
    )


__all__ = ["SERVING_TIE_TOLERANCE", "SelectionResult", "select_models"]
