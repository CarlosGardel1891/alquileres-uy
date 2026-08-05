"""CLI entry point for the training pipeline.

Exit codes:

* 0 — training or dry-run finished successfully;
* 2 — configuration error, invalid ETL contract, missing approval, or
  missing PyTorch when ``--include-torch`` was requested;
* 1 — anything else.

The final result is printed as a compact JSON blob to stdout. Any
other diagnostic (progress, warnings) goes through ``logging`` so the
JSON contract stays parseable.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from alquileres_uy.models.config import (
    DEFAULT_SEED,
    DEFAULT_TEST_FRACTION,
    DEFAULT_TRAIN_FRACTION,
    DEFAULT_VALIDATION_FRACTION,
    TrainingConfig,
    TrainingConfigError,
)
from alquileres_uy.models.contracts import TrainingInputError
from alquileres_uy.models.pipeline import dry_run as pipeline_dry_run
from alquileres_uy.models.pipeline import run as pipeline_run
from alquileres_uy.models.serving import ServingBundleError
from alquileres_uy.models.split import SplitError

_LOGGER = logging.getLogger("alquileres_uy.train")


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--etl-run-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--etl-approval", type=Path, default=None)
    parser.add_argument("--fixture-mode", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--include-torch", action="store_true")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--train-fraction", type=float, default=DEFAULT_TRAIN_FRACTION)
    parser.add_argument("--validation-fraction", type=float, default=DEFAULT_VALIDATION_FRACTION)
    parser.add_argument("--test-fraction", type=float, default=DEFAULT_TEST_FRACTION)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO)
    args = _parse_args(argv or sys.argv[1:])
    try:
        config = TrainingConfig(
            etl_run_dir=args.etl_run_dir,
            output_dir=args.output_dir,
            fixture_mode=args.fixture_mode,
            dry_run=args.dry_run,
            include_torch=args.include_torch,
            etl_approval_path=args.etl_approval,
            seed=args.seed,
            train_fraction=args.train_fraction,
            validation_fraction=args.validation_fraction,
            test_fraction=args.test_fraction,
        )
    except TrainingConfigError as exc:
        _LOGGER.error("configuration error: %s", exc)
        return 2

    try:
        if args.dry_run:
            plan = pipeline_dry_run(config)
            print(json.dumps(plan, indent=2, sort_keys=True))
            return 0
        result = pipeline_run(config)
    except (TrainingInputError, TrainingConfigError, SplitError, ServingBundleError) as exc:
        _LOGGER.error("invalid input: %s", exc)
        return 2
    except Exception as exc:
        _LOGGER.exception("unexpected error: %s", exc)
        return 1

    print(
        json.dumps(
            {
                "training_run_id": result.training_run_id,
                "status": result.status,
                "data_mode": result.data_mode,
                "output_dir": str(result.output_dir),
                "serving_candidate": result.serving_candidate,
                "best_overall_model": result.best_overall,
                "metrics_summary": {
                    name: {
                        "validation_mae_usd": result.metrics["validation"][name]["mae_usd"],
                        "test_mae_usd": result.metrics["test"][name]["mae_usd"],
                    }
                    for name in result.metrics["validation"]
                },
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
