"""End-to-end smoke test for a running alquileres-uy API.

Hits each documented endpoint and prints a pass/fail line per check.
Exits with 0 when every endpoint responded as expected, otherwise 1.
Stdlib only.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DEFAULT_PAYLOAD = {
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


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str


def _http(url: str, method: str = "GET", body: dict | None = None, timeout: float = 10.0):
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["content-type"] = "application/json"
    req = Request(url, data=data, method=method, headers=headers)
    try:
        with urlopen(req, timeout=timeout) as resp:
            payload = resp.read()
            return resp.status, payload, dict(resp.headers)
    except HTTPError as exc:
        return exc.code, exc.read(), dict(exc.headers)
    except URLError as exc:
        return None, str(exc).encode("utf-8"), {}


def check_health(base_url: str) -> CheckResult:
    status, body, _ = _http(f"{base_url.rstrip('/')}/health")
    ok = status == 200 and json.loads(body or b"{}") == {"status": "ok"}
    return CheckResult("GET /health", ok, f"status={status}")


def check_ready(base_url: str) -> CheckResult:
    status, body, _ = _http(f"{base_url.rstrip('/')}/ready")
    ok = status == 200 and json.loads(body or b"{}") == {"status": "ready"}
    return CheckResult("GET /ready", ok, f"status={status}")


def check_version(base_url: str) -> CheckResult:
    status, body, _ = _http(f"{base_url.rstrip('/')}/version")
    if status != 200:
        return CheckResult("GET /version", False, f"status={status}")
    payload = json.loads(body or b"{}")
    required = {"api_version", "model_version", "model_type", "trained_at", "bundle_sha256"}
    missing = required - set(payload)
    return CheckResult(
        "GET /version",
        not missing,
        "ok" if not missing else f"missing fields: {sorted(missing)}",
    )


def check_metrics(base_url: str) -> CheckResult:
    status, body, headers = _http(f"{base_url.rstrip('/')}/metrics")
    text = (body or b"").decode("utf-8", errors="replace")
    content_type = headers.get("Content-Type", headers.get("content-type", ""))
    ok = status == 200 and "# HELP prediction_requests_total" in text
    return CheckResult(
        "GET /metrics",
        ok,
        f"status={status} content_type={content_type!r}",
    )


def check_predict(base_url: str) -> CheckResult:
    status, body, _ = _http(f"{base_url.rstrip('/')}/predict", method="POST", body=DEFAULT_PAYLOAD)
    if status != 200:
        return CheckResult("POST /predict", False, f"status={status}")
    payload = json.loads(body or b"{}")
    required = {"prediction", "currency", "model_version", "prediction_timestamp"}
    ok = required <= set(payload) and isinstance(payload.get("prediction"), int | float)
    return CheckResult("POST /predict", ok, "ok" if ok else f"unexpected payload: {payload}")


def run_smoke(base_url: str) -> list[CheckResult]:
    return [
        check_health(base_url),
        check_ready(base_url),
        check_version(base_url),
        check_metrics(base_url),
        check_predict(base_url),
    ]


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    results = run_smoke(args.url)
    all_ok = True
    for result in results:
        marker = "PASS" if result.passed else "FAIL"
        print(f"{marker} {result.name} — {result.detail}")
        if not result.passed:
            all_ok = False
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
