"""CLI entrypoint for the alquileres-uy ETL pipeline.

Two mutually exclusive modes:

- ``--fixture-mode``: run against a sanitized fixture directory under
  ``tests/fixtures/``. Outputs are marked ``data_mode: fixture`` and
  their metrics must never be reported as project results.
- Real mode (default): requires ``--gate-approval`` pointing to a
  validated :func:`load_approved_contract` file plus a real
  ``--input-run-dir``. Without a valid approval the CLI exits 2 with
  no network, SQLite, or filesystem side effects.

``--dry-run`` validates every input (approval, exchange rate, run
directories) and prints the plan without writing any Parquet.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from alquileres_uy.etl.config import EtlConfig
from alquileres_uy.etl.contracts import RawRunValidationError
from alquileres_uy.etl.currency import ExchangeRateModeMismatch, InvalidExchangeRate
from alquileres_uy.etl.neighborhoods import InvalidAliasFile
from alquileres_uy.etl.pipeline import EtlPipeline, StrictQualityGateError
from alquileres_uy.ingest.approval import load_approved_contract
from alquileres_uy.ingest.errors import (
    SourceGateApprovalIntegrityError,
    SourceGateApprovalInvalid,
    SourceGateApprovalMissing,
)

EXIT_APPROVAL_ERROR = 2
EXIT_CONFIG_ERROR = 2
EXIT_SCHEMA_ERROR = 1


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the alquileres-uy ETL pipeline.")
    parser.add_argument(
        "--input-run-dir",
        type=Path,
        action="append",
        required=True,
        help="Directory containing manifest.json, items/, descriptions/. Repeatable.",
    )
    parser.add_argument(
        "--exchange-rate",
        type=Path,
        required=True,
        help="Path to a JSON file describing the USD/UYU rate for this run.",
    )
    parser.add_argument(
        "--gate-approval",
        type=Path,
        default=None,
        help="Path to a source_gate_approval.json. Required in real mode.",
    )
    parser.add_argument(
        "--neighborhood-aliases",
        type=Path,
        default=None,
        help="Path to the neighborhood aliases JSON. Optional.",
    )
    parser.add_argument("--output-dir", type=Path, default=Path("data/processed"))
    parser.add_argument("--fixture-mode", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--strict", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    verified_category_ids: dict[str, str] = {}
    gate_approval_path: Path | None = None

    if not args.fixture_mode:
        if args.gate_approval is None:
            logging.error("real mode requires --gate-approval")
            return EXIT_APPROVAL_ERROR
        try:
            contract = load_approved_contract(args.gate_approval)
        except (
            SourceGateApprovalMissing,
            SourceGateApprovalInvalid,
            SourceGateApprovalIntegrityError,
        ) as exc:
            logging.error("source gate approval error: %s", exc)
            return EXIT_APPROVAL_ERROR
        verified_category_ids = dict(contract.category_ids)
        gate_approval_path = args.gate_approval

    try:
        config = EtlConfig(
            input_run_dirs=tuple(args.input_run_dir),
            exchange_rate_path=args.exchange_rate,
            neighborhood_aliases_path=args.neighborhood_aliases,
            output_dir=args.output_dir,
            gate_approval_path=gate_approval_path,
            fixture_mode=args.fixture_mode,
            dry_run=args.dry_run,
            strict=args.strict,
        )
    except ValueError as exc:
        logging.error("invalid ETL config: %s", exc)
        return EXIT_CONFIG_ERROR

    pipeline = EtlPipeline(config, verified_category_ids=verified_category_ids)

    try:
        if args.dry_run:
            plan = pipeline.dry_run()
            print(json.dumps(plan, indent=2, ensure_ascii=False))
            return 0
        result = pipeline.run()
    except ExchangeRateModeMismatch as exc:
        logging.error("exchange rate data_mode mismatch: %s", exc)
        return EXIT_CONFIG_ERROR
    except InvalidExchangeRate as exc:
        logging.error("invalid exchange rate: %s", exc)
        return EXIT_CONFIG_ERROR
    except (RawRunValidationError, InvalidAliasFile) as exc:
        logging.error("invalid input: %s", exc)
        return EXIT_CONFIG_ERROR
    except StrictQualityGateError as exc:
        logging.error("%s", exc)
        return EXIT_SCHEMA_ERROR
    except Exception:
        logging.exception("etl pipeline crashed")
        return EXIT_SCHEMA_ERROR

    print(json.dumps(result.summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
