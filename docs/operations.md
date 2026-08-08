# Operations

Day-two guide: how to read the running system, how to load-test it and
how to smoke it after a deploy.

## Logs

The API emits structured logs on stdout. Every request produces one
line with `request_id`, `method`, `path`, `status`, `duration_ms` —
never a payload, never latitude / longitude / price / features. Fase 8
formalised the contract; do not add fields that carry PII.

Notable log lines to alert on:

| Line | Meaning | Response |
| --- | --- | --- |
| `warmup completed` | Startup passed the synthetic prediction. | Info only. |
| `warmup failed` | Startup could not run one prediction. | The container will exit — investigate the bundle. |
| `prediction timeout` | A prediction exceeded `PREDICT_TIMEOUT`. | Check the benchmark; either raise the timeout or scale horizontally. Bumps `prediction_errors_total{status_code="503"}`. |
| `shutdown waiting` | Drain has started. | Nothing — expect it during rolling deploys. |
| `shutdown completed` | Drain finished. | Nothing. |

## Prometheus

Scrape `GET /metrics`. Baseline SLIs:

- `prediction_requests_total` — request rate. Split by
  `endpoint`, `method`, `status_code`.
- `prediction_errors_total{status_code="5.."}` — server-side error
  rate. `status_code="503"` includes timeouts and shutdowns.
- `prediction_latency_seconds` — histogram. Compute p50/p95/p99 in
  Prometheus / Grafana.
- `model_loaded` — 1 while a bundle is loaded, 0 during startup /
  shutdown / after a failed load.

Recommended alerts:

- `model_loaded == 0` for > 5 minutes (bundle refused or process
  restart loop).
- `sum(rate(prediction_errors_total[5m])) / sum(rate(prediction_requests_total[5m])) > 0.02`
  (error budget burn).
- `histogram_quantile(0.95, sum by (le) (rate(prediction_latency_seconds_bucket[5m]))) > 0.5s`
  (latency regression).

## Warmup

`scripts/train_models.py` is not involved at runtime; the warmup
happens inside the API startup. It runs one synthetic prediction
through the raw `Predictor` so numpy / sklearn / lightgbm caches are
primed before the first user-visible call. It never emits a Prometheus
counter and never appears as a request line.

If the warmup fails the container exits non-zero. The most common
causes:

- Bundle mismatch — the bundle expects a feature schema the fixture
  request cannot satisfy. Re-emit the bundle with
  `scripts/train_models.py` at the current model version.
- Missing dependency — the image was built without the runtime pins.
- `PREDICT_TIMEOUT` too low — warmup uses the same predictor path but
  is not bounded by `PREDICT_TIMEOUT` (it runs *before* the service is
  built).

## Timeouts

`PREDICT_TIMEOUT` is per-request; `MAX_CONCURRENT_PREDICTIONS`
serialises callers above that ceiling. Callers over the cap wait —
they are never rejected. A caller that waits + runs + times out
receives a 503 with the `prediction_timeout` envelope.

Tuning workflow:

1. Baseline the container with `scripts/benchmark.py` at
   `--concurrency 1`.
2. Increase concurrency until throughput plateaus. The plateau minus
   one is a safe `MAX_CONCURRENT_PREDICTIONS`.
3. Set `PREDICT_TIMEOUT` to `p95 * 2` under the plateau load, with a
   floor of 1s.

## Benchmark

`python scripts/benchmark.py --url http://host:8000/predict --requests 500 --concurrency 8`

Prints total requests, throughput (requests/s), average, min, max,
p50, p95, p99 (all in ms), the status-code distribution and the
transport error count. stdlib-only — safe to run from any Python 3.12
environment without installing the API dependencies.

## Smoke test

`python scripts/smoke_api.py --base-url http://host:8000`

Hits `/health`, `/ready`, `/version`, `/metrics` and issues one
`POST /predict` with a canned payload. Exits `0` on success, `1` on
the first failure. Suitable for a post-deploy check or a CI e2e
sanity net.
