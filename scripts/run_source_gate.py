"""CLI entrypoint that runs the MercadoLibre source gate.

Exit codes:
    0 = APPROVED
    1 = unexpected error
    2 = REJECTED
    3 = INCONCLUSIVE
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

from alquileres_uy.ingest.auth import load_access_token
from alquileres_uy.ingest.client import MercadoLibreClient
from alquileres_uy.ingest.config import (
    DEFAULT_DATABASE_PATH,
    DEFAULT_OUTPUT_DIR,
    IngestionConfig,
)
from alquileres_uy.ingest.models import SourceGateDecision
from alquileres_uy.ingest.source_gate import run_source_gate

DECISION_EXIT_CODES = {
    SourceGateDecision.APPROVED: 0,
    SourceGateDecision.REJECTED: 2,
    SourceGateDecision.INCONCLUSIVE: 3,
}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the MercadoLibre source gate.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--database-path", type=Path, default=DEFAULT_DATABASE_PATH)
    parser.add_argument("--requests-per-second", type=float, default=2.0)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--max-attempts", type=int, default=5)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    config = IngestionConfig(
        output_dir=args.output_dir,
        database_path=args.database_path,
        requests_per_second=args.requests_per_second,
        request_timeout_seconds=args.timeout,
        max_attempts=args.max_attempts,
        access_token=load_access_token(),
    )

    timestamp = datetime.now(UTC).strftime("%Y-%m-%dT%H%M%SZ")
    workdir = config.output_dir / "source_gate" / f"{timestamp}_{uuid.uuid4().hex[:8]}"

    try:
        client = MercadoLibreClient(config)
        report, artifacts = run_source_gate(config, client, workdir)
    except Exception:
        logging.exception("source gate crashed")
        return 1

    print(json.dumps(report.as_dict(), indent=2, ensure_ascii=False))
    logging.info(
        "source gate finished: decision=%s workdir=%s",
        report.decision.value,
        workdir,
    )
    _ = artifacts
    return DECISION_EXIT_CODES.get(report.decision, 1)


if __name__ == "__main__":
    sys.exit(main())
