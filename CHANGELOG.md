# Changelog

All notable changes to `alquileres-uy` are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

The version is the single source of truth stored in
`src/alquileres_uy/_version.py`; every consumer (Python package, API,
Docker image, release script, docs) resolves back to it.

## [Unreleased]

### Added — Fase 11 (web UI)

- Server-rendered home page at `GET /` (Jinja2 templates, no
  framework CDN). Includes project title, description, "Calcular
  precio" CTA, model info card (populated from `/version`), API
  version badge and repository link.
- HTML form with `neighborhood`, `property_type`, `bedrooms`,
  `bathrooms`, `total_area`, `covered_area`, `latitude`, `longitude`
  and an optional `price` field for comparison. Native HTML
  validation on every model-feature field.
- Vanilla-JS front-end (`/static/js/app.js`) that posts the form via
  `fetch()` to the existing `POST /predict`, renders the estimated
  price + model + version + timestamp, and — when the user provides
  a published price — shows the absolute / percent difference with a
  🟢 / 🟡 / 🔴 semaphore badge.
- Live header status indicator that polls `/health` + `/ready` every
  30 seconds and shows ● Online / ● Inicializando / ● Error.
- Friendly error handling that translates HTTP 0 / 408 / 422 / 503 /
  5xx into user-facing messages; tracebacks are never surfaced.
- Custom responsive CSS (`/static/css/styles.css`), simple palette,
  card layout, soft shadows, single-column breakpoint on narrow
  viewports. No Bootstrap / Tailwind / other framework.
- SVG favicon served from `/static/favicon.svg`.
- `StaticFiles` mount at `/static` for CSS / JS / favicon; packaged
  via `pyproject.toml` `package-data`.
- 29 new tests in `tests/api/test_web_ui.py` covering the home
  route, form fields, HTML validation, template inheritance, static
  serving, CSS palette + responsive breakpoint, JS fetch calls and
  semaphore states, `/predict`/`/version`/`/health`/`/ready`
  contract preservation, and OpenAPI hygiene.

## [0.10.0] — 2026-08-07

Release-engineering pass. The runtime behaviour of the API is unchanged
from 0.9.x; this release introduces the versioning, packaging and
release-tooling that a real deploy needs.

### Added

- **Single-source semantic versioning** in `src/alquileres_uy/_version.py`.
  `pyproject.toml` reads it via `[tool.setuptools.dynamic]`, the API's
  `APP_VERSION` setting defaults to it, and the Docker image label is
  built from it. Bumping the number in one file bumps every downstream
  reference in one commit.
- **`CHANGELOG.md`** in Keep-a-Changelog format, back-filling the
  history from Fase 0 through Fase 9.
- **`GET /build`** endpoint returning `version`, `git_commit`,
  `build_date`, `python_version`, `api_version`. All values come from
  the `build_info.json` shipped with the package — nothing is
  hard-coded at request time.
- **`build_info.json`** generated at build time by
  `scripts/generate_build_info.py`. Contains version + git SHA + UTC
  build date + Python version + platform. Bundled with the wheel via
  `package-data`.
- **`scripts/release.py`** — stdlib-only helper that validates a clean
  working tree, runs the test suite, optionally regenerates the
  changelog stub, creates the annotated `v<version>` tag and prints
  the suggested next version. Never pushes.
- **`scripts/generate_build_info.py`** — writes the build metadata
  file. Callable from CI, from `python -m build` and from the Docker
  build.
- **`.github/workflows/release.yml`** — runs on `v*` tags. Builds the
  wheel + sdist, builds the Docker image, uploads the artifacts and
  creates a GitHub Release with the changelog section attached. Does
  not push to any registry.
- **`release-check` job in `.github/workflows/ci.yml`** — verifies
  `CHANGELOG.md` has an entry for the current version, that
  `_version.__version__` matches the `[Unreleased]`/latest entry,
  that `build_info.json` can be generated, that the wheel + sdist +
  Docker image build cleanly.
- **OCI labels on the Docker image** — `org.opencontainers.image.version`,
  `org.opencontainers.image.source`, `org.opencontainers.image.description`,
  `org.opencontainers.image.licenses`. Version is passed in via a build
  arg so the labelled version matches the shipped wheel.
- **Operational docs**: `docs/deployment.md`, `docs/operations.md`,
  `docs/upgrade.md`. Cover env vars, Docker, startup/shutdown,
  observability, warmup/timeouts, benchmark, smoke test, bundle
  upgrades, rollback and semver.

### Changed

- `pyproject.toml` moves the version from a static field to a dynamic
  attribute read from `alquileres_uy._version.__version__`.
- `ApiSettings.APP_VERSION` default is now sourced from the package
  version, not a duplicated literal.
- `Dockerfile` accepts an `APP_VERSION` build arg and stamps the
  standard OCI labels.

### Notes

- No changes to `POST /predict`, request/response schemas, `Predictor`,
  `ModelLoader`, `PredictionService`, Prometheus metrics, middleware,
  Request-ID handling, error handlers, training, ETL or existing
  bundles. Fase 10 is exclusively a release-engineering pass.

## [0.9.0] — Fase 9 — Runtime reliability

- Startup warmup runs one synthetic prediction through the raw
  `Predictor` (never touches Prometheus, never counted as a request).
- `PredictionService` wraps the predictor with an asyncio semaphore
  (`MAX_CONCURRENT_PREDICTIONS`, default 4), a per-request timeout
  (`PREDICT_TIMEOUT`, default 5.0 s) and a graceful-shutdown drain
  that refuses new callers but never cancels in-flight work.
- Timeout responses return HTTP 503 with
  `{"error":{"code":"prediction_timeout","message":"Prediction timed out."}}`
  and bump `prediction_errors_total{status_code="503"}`.
- Serving bundles gained `metadata.minimum_api_version`; startup
  rejects a bundle whose floor is above the running API. Bundles
  produced before Fase 9 (no floor) keep loading.
- `scripts/benchmark.py` (concurrent load-test) and
  `scripts/smoke_api.py` (e2e health check) added, stdlib-only.

## [0.8.0] — Fase 8 — Observability

- Prometheus metrics: `prediction_requests_total`,
  `prediction_errors_total`, `prediction_latency_seconds`, plus
  `model_loaded` and standard process metrics.
- `MetricsMiddleware` records status/method/endpoint labels and
  latency. `RequestIdMiddleware` injects and echoes back an
  `X-Request-ID` header.
- `/metrics` endpoint exposes the collectors in the Prometheus
  text format.
- Structured logs for every request with `request_id`, method,
  path, status and duration. Never logs payloads.

## [0.7.0] — Fase 7 — Production wiring

- Serving bundle validated at startup by `ModelLoader` (checksums,
  metadata schema, feature schema).
- Uniform error envelope on all failures: `{"error":{"code","message"}}`.
- `scripts/run_api.py` launcher wired to Uvicorn with
  ENV-driven host / port / log-level / max-workers.
- Dockerfile that ships the runtime API + serving bundle.

## [0.6.0] — Fase 6 — Prediction API surface

- FastAPI application factory with routers for `/health`, `/ready`,
  `/version`, `/model/info` and `POST /predict`.
- Pydantic v2 schemas for `PredictRequest` / `PredictResponse`.

## [0.5.0] — Fase 5 — Serving bundle contract

- `build_serving_bundle` writes `model.joblib`, `metadata.json`,
  `checksums.json`, `feature_schema.json` and
  `residual_interval.json` under a versioned directory.
- Checksums file locks each artifact by SHA-256.

## [0.4.0] — Fase 4 — Model training pipeline

- `scripts/train_models.py` trains a baseline + optional torch model
  from the ETL run outputs and emits a full training-run bundle.
- Custom ASGI test harness replaces `httpx` / `TestClient` for API
  tests — kept ever since.

## [0.3.0] — Fase 3 — ETL

- `scripts/run_etl.py` normalises the raw scrapes into curated
  parquet: schema validation via `pandera`, deduplication,
  outlier trimming.
- Data-quality rules documented in `docs/etl-quality-rules.md`.

## [0.2.0] — Fase 2 — Source gate + ingestion

- `scripts/run_source_gate.py` blocks scraping when the
  MercadoLibre source contract is not met (User-Agent,
  robots.txt, throttle).
- `scripts/run_ingestion.py` writes raw JSON runs under
  `artifacts/raw/`.

## [0.1.0] — Fase 1 — Bootstrap

- Repository skeleton, packaging, ruff, pytest, pre-commit,
  CI workflow.
- Source contract documented in
  `docs/mercadolibre-source-contract.md`.

## [0.0.1] — Fase 0 — Kickoff

- Project scope, glossary and delivery plan agreed with the
  Technical Lead.

[Unreleased]: https://github.com/CarlosGardel1891/alquileres-uy/compare/v0.10.0...HEAD
[0.10.0]: https://github.com/CarlosGardel1891/alquileres-uy/releases/tag/v0.10.0
[0.9.0]: https://github.com/CarlosGardel1891/alquileres-uy/releases/tag/v0.9.0
[0.8.0]: https://github.com/CarlosGardel1891/alquileres-uy/releases/tag/v0.8.0
[0.7.0]: https://github.com/CarlosGardel1891/alquileres-uy/releases/tag/v0.7.0
[0.6.0]: https://github.com/CarlosGardel1891/alquileres-uy/releases/tag/v0.6.0
[0.5.0]: https://github.com/CarlosGardel1891/alquileres-uy/releases/tag/v0.5.0
[0.4.0]: https://github.com/CarlosGardel1891/alquileres-uy/releases/tag/v0.4.0
[0.3.0]: https://github.com/CarlosGardel1891/alquileres-uy/releases/tag/v0.3.0
[0.2.0]: https://github.com/CarlosGardel1891/alquileres-uy/releases/tag/v0.2.0
[0.1.0]: https://github.com/CarlosGardel1891/alquileres-uy/releases/tag/v0.1.0
[0.0.1]: https://github.com/CarlosGardel1891/alquileres-uy/releases/tag/v0.0.1
