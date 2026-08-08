"""Simple concurrent benchmark for the alquileres-uy prediction API.

Uses only the Python standard library (``urllib.request`` +
``concurrent.futures``) so the script has zero deployment cost. Sends
``--requests`` ``POST /predict`` calls with ``--concurrency`` workers
and prints a summary block with total requests, throughput and the
usual latency percentiles.

Example
-------

    python scripts/benchmark.py \\
        --url http://localhost:8000 \\
        --requests 1000 \\
        --concurrency 20

The script does not modify the API in any way, does not require
Prometheus, and does not read the model bundle.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DEFAULT_PAYLOAD: dict[str, Any] = {
    "property_type": "apartment",
    "price": 1000.0,
    "bedrooms": 2,
    "bathrooms": 1,
    "covered_area": 50.0,
    "total_area": 55.0,
    "latitude": -34.9,
    "longitude": -56.2,
    "neighborhood": "Pocitos",
}


def _fire_one(url: str, payload: bytes, timeout: float) -> tuple[float, int | None]:
    """Return ``(elapsed_seconds, status_code)``. Status is ``None`` on network error."""
    started = time.perf_counter()
    request = Request(
        url, data=payload, method="POST", headers={"content-type": "application/json"}
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            response.read()
            return (time.perf_counter() - started, response.status)
    except HTTPError as exc:
        exc.read()
        return (time.perf_counter() - started, exc.code)
    except URLError:
        return (time.perf_counter() - started, None)


def run_benchmark(
    *,
    url: str,
    total_requests: int,
    concurrency: int,
    timeout: float = 30.0,
) -> dict[str, Any]:
    """Fire ``total_requests`` at ``url`` and return summary statistics."""
    if total_requests < 1:
        raise ValueError("--requests must be >= 1")
    if concurrency < 1:
        raise ValueError("--concurrency must be >= 1")
    predict_url = url.rstrip("/") + "/predict"
    payload = json.dumps(DEFAULT_PAYLOAD).encode("utf-8")

    latencies_ms: list[float] = []
    status_counts: dict[str, int] = {}
    errors = 0

    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [
            pool.submit(_fire_one, predict_url, payload, timeout) for _ in range(total_requests)
        ]
        for future in as_completed(futures):
            elapsed, status = future.result()
            latencies_ms.append(elapsed * 1000)
            if status is None:
                errors += 1
                status_counts["network_error"] = status_counts.get("network_error", 0) + 1
                continue
            key = str(status)
            status_counts[key] = status_counts.get(key, 0) + 1
            if status >= 400:
                errors += 1
    total_seconds = time.perf_counter() - started

    return {
        "total_requests": total_requests,
        "concurrency": concurrency,
        "total_seconds": total_seconds,
        "throughput_rps": total_requests / total_seconds if total_seconds > 0 else 0.0,
        "avg_ms": statistics.fmean(latencies_ms) if latencies_ms else 0.0,
        "min_ms": min(latencies_ms) if latencies_ms else 0.0,
        "max_ms": max(latencies_ms) if latencies_ms else 0.0,
        "p50_ms": _quantile(latencies_ms, 0.50),
        "p95_ms": _quantile(latencies_ms, 0.95),
        "p99_ms": _quantile(latencies_ms, 0.99),
        "status_counts": status_counts,
        "errors": errors,
    }


def _quantile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    # NumPy-style linear interpolation between closest ranks.
    rank = q * (len(ordered) - 1)
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    weight = rank - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def format_report(stats: dict[str, Any]) -> str:
    lines = [
        "alquileres-uy benchmark",
        "-----------------------",
        f"total requests   : {stats['total_requests']}",
        f"concurrency      : {stats['concurrency']}",
        f"total seconds    : {stats['total_seconds']:.3f}",
        f"throughput (rps) : {stats['throughput_rps']:.2f}",
        f"avg latency (ms) : {stats['avg_ms']:.2f}",
        f"min latency (ms) : {stats['min_ms']:.2f}",
        f"p50 latency (ms) : {stats['p50_ms']:.2f}",
        f"p95 latency (ms) : {stats['p95_ms']:.2f}",
        f"p99 latency (ms) : {stats['p99_ms']:.2f}",
        f"max latency (ms) : {stats['max_ms']:.2f}",
        f"errors           : {stats['errors']}",
        f"status counts    : {stats['status_counts']}",
    ]
    return "\n".join(lines)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--url", required=True, help="Base URL of the API (e.g. http://localhost:8000)"
    )
    parser.add_argument("--requests", type=int, default=100)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--timeout", type=float, default=30.0)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        stats = run_benchmark(
            url=args.url,
            total_requests=args.requests,
            concurrency=args.concurrency,
            timeout=args.timeout,
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(format_report(stats))
    return 0 if stats["errors"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
