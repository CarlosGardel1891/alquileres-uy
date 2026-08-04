"""CLI entrypoint that runs the MercadoLibre ingestion pipeline.

Requires a validated ``source_gate_approval.json`` from an APPROVED
source gate. Without it — or with a tampered coverage report — the
command exits with code 2 and performs no network I/O, no SQLite
writes, and no filesystem mutation beyond stdout.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from alquileres_uy.ingest.approval import load_approved_contract
from alquileres_uy.ingest.auth import load_access_token
from alquileres_uy.ingest.config import (
    DEFAULT_DATABASE_PATH,
    DEFAULT_MAX_ATTEMPTS,
    DEFAULT_MAX_ITEMS,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_REQUEST_TIMEOUT_SECONDS,
    DEFAULT_REQUESTS_PER_SECOND,
    IngestionConfig,
)
from alquileres_uy.ingest.errors import (
    SourceGateApprovalIntegrityError,
    SourceGateApprovalInvalid,
    SourceGateApprovalMissing,
)
from alquileres_uy.ingest.service import IngestionService

EXIT_APPROVAL_ERROR = 2


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the MercadoLibre ingestion.")
    parser.add_argument(
        "--gate-approval",
        type=Path,
        required=True,
        help="Path to a source_gate_approval.json produced by an APPROVED run.",
    )
    parser.add_argument("--max-items", type=int, default=DEFAULT_MAX_ITEMS)
    parser.add_argument("--requests-per-second", type=float, default=DEFAULT_REQUESTS_PER_SECOND)
    parser.add_argument("--timeout", type=float, default=DEFAULT_REQUEST_TIMEOUT_SECONDS)
    parser.add_argument("--max-attempts", type=int, default=DEFAULT_MAX_ATTEMPTS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--database-path", type=Path, default=DEFAULT_DATABASE_PATH)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate config and print the query plan without touching the network.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    try:
        contract = load_approved_contract(args.gate_approval)
    except (
        SourceGateApprovalMissing,
        SourceGateApprovalInvalid,
        SourceGateApprovalIntegrityError,
    ) as exc:
        logging.error("source gate approval error: %s", exc)
        return EXIT_APPROVAL_ERROR

    config = IngestionConfig(
        output_dir=args.output_dir,
        database_path=args.database_path,
        max_items=args.max_items,
        requests_per_second=args.requests_per_second,
        request_timeout_seconds=args.timeout,
        max_attempts=args.max_attempts,
        access_token=load_access_token(),
    )

    service = IngestionService(config, contract)
    if args.dry_run:
        plan = service.dry_run()
        print(json.dumps(plan, indent=2, ensure_ascii=False))
        return 0

    try:
        result = service.run()
    except Exception:
        logging.exception("ingestion crashed")
        return 1
    print(json.dumps(result.summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
