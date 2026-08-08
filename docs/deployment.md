# Deployment

Operational guide for shipping `alquileres-uy` to a production
environment. Assumes the runtime reliability layer from Fase 9 and the
release engineering from Fase 10 are in place.

## Contents

- [Runtime prerequisites](#runtime-prerequisites)
- [Environment variables](#environment-variables)
- [Docker image](#docker-image)
- [Startup sequence](#startup-sequence)
- [Health, readiness and metrics endpoints](#health-readiness-and-metrics-endpoints)
- [Shutdown sequence](#shutdown-sequence)

## Runtime prerequisites

- Python 3.12 (matches the pins in `requirements-api.txt`).
- A serving bundle produced by `scripts/train_models.py`. Layout:
  `<bundle>/model.joblib`, `metadata.json`, `checksums.json`,
  `feature_schema.json`, `residual_interval.json`.
- Write access to `stdout` for structured logs (Prometheus + JSON
  fields — no PII).

## Environment variables

All variables use the `ALQUILERES_API_` prefix; every default lives in
`src/alquileres_uy/api/config.py`.

| Variable | Default | Purpose |
| --- | --- | --- |
| `ALQUILERES_API_APP_VERSION` | derived from `_version.__version__` | Reported by `/version` and `/build`. Do not override in production — let the packaged value win. |
| `ALQUILERES_API_HOST` | `127.0.0.1` locally, `0.0.0.0` in Docker | Interface for uvicorn. |
| `ALQUILERES_API_PORT` | `8000` | Listen port. |
| `ALQUILERES_API_LOG_LEVEL` | `INFO` | Structured-log level. `DEBUG` for troubleshooting only. |
| `ALQUILERES_API_MODEL_BUNDLE_PATH` | `artifacts/models/latest/serving_bundle` | Path (inside the container) to the bundle directory. |
| `ALQUILERES_API_ALLOW_FIXTURE_MODEL` | `false` | Must stay `false` in production; fixture bundles carry `deployable=false`. |
| `ALQUILERES_API_REQUEST_TIMEOUT` | `30` | Uvicorn `--timeout-keep-alive`. |
| `ALQUILERES_API_MAX_WORKERS` | `1` | Single-process default; scale horizontally, not vertically. |
| `ALQUILERES_API_ENABLE_METRICS` | `true` | Exposes `/metrics` and wires the collectors. |
| `ALQUILERES_API_METRICS_PATH` | `/metrics` | Where the Prometheus text is served. |
| `ALQUILERES_API_MAX_CONCURRENT_PREDICTIONS` | `4` | Fase 9 semaphore. Tune with the benchmark script. |
| `ALQUILERES_API_PREDICT_TIMEOUT` | `5.0` | Per-request budget in seconds; a 503 with `prediction_timeout` fires when exceeded. |

## Docker image

```bash
docker build \
  --build-arg APP_VERSION=$(cat src/alquileres_uy/_version.py | grep -oE '"[0-9]+\.[0-9]+\.[0-9]+"' | tr -d '"') \
  -t alquileres-uy-api:local .
```

The image is stamped with the OCI labels
`org.opencontainers.image.version`, `org.opencontainers.image.source`,
`org.opencontainers.image.description` and
`org.opencontainers.image.licenses`. `docker inspect` should show the
build-arg version.

Run with a mounted bundle:

```bash
docker run --rm -p 8000:8000 \
  -v /path/to/bundle:/app/artifacts/serving_bundle:ro \
  -e ALQUILERES_API_MODEL_BUNDLE_PATH=/app/artifacts/serving_bundle \
  alquileres-uy-api:local
```

## Startup sequence

Managed by `src/alquileres_uy/api/lifespan.py`:

1. `configure_logging` — structured JSON output on stdout.
2. `ModelLoader.load()` — validates checksums and metadata; refuses
   fixture bundles unless `ALLOW_FIXTURE_MODEL` is `true`.
3. `verify_bundle_compatibility(loaded, api_version=APP_VERSION)` —
   raises `IncompatibleBundleError` when the bundle's
   `metadata.minimum_api_version` is above the running API. Startup
   aborts.
4. `run_warmup(predictor)` — one synthetic prediction through the raw
   `Predictor`. Never touches Prometheus; failure raises
   `WarmupError` and aborts startup.
5. `PredictionService` built from `MAX_CONCURRENT_PREDICTIONS` /
   `PREDICT_TIMEOUT` and published to `app.state.prediction_service`.
6. `model_loaded` gauge flipped to `1`.

If any step raises the container exits non-zero; the orchestrator will
restart it. Configure liveness probes on `/health` and readiness
probes on `/ready`.

## Health, readiness and metrics endpoints

| Endpoint | Purpose | Notes |
| --- | --- | --- |
| `GET /health` | Process liveness. | Returns `{"status":"ok"}` while the loop runs, regardless of model state. Use for liveness probes. |
| `GET /ready` | Model readiness. | 200 when the bundle is loaded and the service is not shutting down; 503 otherwise. Use for readiness probes. |
| `GET /version` | Bundle + API version. | Returns model version, model type, trained-at, bundle SHA and the running API version. |
| `GET /build` | Build metadata. | Returns `version`, `git_commit`, `build_date`, `python_version`, `api_version`. Sourced from `build_info.json`. |
| `GET /metrics` | Prometheus text. | Scrape target. Includes `prediction_requests_total`, `prediction_errors_total`, `prediction_latency_seconds`, `model_loaded`, process metrics. |
| `POST /predict` | Prediction. | Semaphore-guarded, timeout-bounded. |

## Shutdown sequence

On SIGTERM (Docker stop, k8s termination) the FastAPI lifespan exits:

1. `PredictionService.begin_shutdown()` — new callers get 503
   `service_unavailable`.
2. `PredictionService.wait_for_drain(timeout=max(PREDICT_TIMEOUT, 5.0))`
   — waits for in-flight predictions; never cancels them.
3. `app.state` cleared, `model_loaded` gauge flipped to `0`, log line
   `"api shutdown"` emitted.

Set the orchestrator grace period ≥ `PREDICT_TIMEOUT + a few seconds`
so the drain has time to complete. In-flight predictions are always
awaited within that window.
