# alquileres-uy

[![Python](https://img.shields.io/badge/python-3.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/fastapi-0.115-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Docker](https://img.shields.io/badge/docker-ready-2496ED?logo=docker&logoColor=white)](./Dockerfile)
[![CI](https://img.shields.io/badge/CI-passing-16a34a?logo=githubactions&logoColor=white)](./.github/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-4338ca)](./LICENSE)
[![Version](https://img.shields.io/badge/version-0.10.0-6366f1)](./CHANGELOG.md)

Pipeline end-to-end para estimación de precios de alquiler mensual en Montevideo
— ingesta, ETL, entrenamiento comparativo de modelos, API HTTP de inferencia,
frontend server-rendered y toda la infraestructura de release engineering,
observabilidad y runtime reliability que necesita para operar.

> Estado actual: **0.10.0** — API + UI públicas, release engineering listo,
> pipeline entrenado en modo fixture. El source gate contra MercadoLibre
> sigue bloqueado por `403` sin token oficial; documentado en
> [`docs/mercadolibre-source-contract.md`](docs/mercadolibre-source-contract.md).

---

## Problema

En Montevideo, no existe un dataset abierto y actualizado de precios de
alquiler mensual que permita comparar una publicación individual con la
mediana del mercado. Los usuarios (inquilinos, propietarios, agencias
chicas) se apoyan en intuición y sesgo de disponibilidad.

## Objetivo

Construir el pipeline reproducible que:

1. Descarga publicaciones de fuentes públicas (con gate de contrato y
   tasa límite explícita).
2. Normaliza, deduplica y valida los datos.
3. Entrena y compara modelos clásicos (baseline, Ridge, LightGBM) y
   una red tabular en PyTorch, con protocolo `tune-then-refit-v2` que
   no filtra validation.
4. Sirve las predicciones detrás de una API HTTP observable y
   confiable.
5. Ofrece una interfaz web pública para que un usuario final compare
   una publicación contra la estimación del modelo.

## Arquitectura

```
Ingesta → ETL → Entrenamiento → Serving bundle → API (/predict) → UI
   │        │          │              │             │             │
   │        │          │              │             ├── /health   │
   │        │          │              │             ├── /ready    │
   │        │          │              │             ├── /version  │
   │        │          │              │             ├── /build    │
   │        │          │              │             ├── /metrics  │
   │        │          │              │             └── /predict  │
   │        │          │              └── minimum_api_version     │
   │        │          └── metrics.json / model_selection.json    │
   │        └── model_ready.parquet + lineage + quality report    │
   └── raw JSON + SQLite + source_gate_approval.json              │
                                                                  │
      Observabilidad transversal (Prometheus + logs) ─────────────┘
```

Detalle completo en [`docs/architecture.md`](docs/architecture.md) con
diagramas Mermaid del flujo end-to-end.

## Stack

| Capa | Tecnologías |
| --- | --- |
| Lenguaje | Python 3.12 |
| Ingesta / ETL | `requests`, `pandas`, `pyarrow`, `pandera` |
| Modelos | `scikit-learn`, `lightgbm`, `joblib`, PyTorch CPU |
| API | `fastapi`, `uvicorn`, `pydantic` v2, `pydantic-settings` |
| Observabilidad | `prometheus-client`, logging estructurado, Request-ID |
| Frontend | Jinja2 + vanilla JS (sin frameworks) + CSS propio |
| Testing | `pytest`, harness ASGI custom (sin `httpx`/`TestClient`) |
| Empaquetado | `setuptools` con `pyproject.toml` dinámico |
| CI / CD | GitHub Actions (quality, torch, docker, release-check) |
| Runtime reliability | `asyncio.Semaphore` + `asyncio.timeout` + graceful shutdown |
| Release | Tag-driven workflow, OCI-labeled Docker, single-source semver |

## Capturas

Placeholder — la sección se poblará cuando se grabe la demo (ver
[`docs/demo.md`](docs/demo.md)).

- ![Home](docs/screenshots/home.png "Home")
- ![Formulario + resultado](docs/screenshots/form-result.png "Formulario y resultado")
- ![Comparación con precio publicado](docs/screenshots/comparison.png "Comparación")

## Quick Start

Requisitos: Python 3.12, Git, un venv local.

```bash
git clone https://github.com/CarlosGardel1891/alquileres-uy.git
cd alquileres-uy
python -m venv .venv
# Linux/macOS
source .venv/bin/activate
# Windows PowerShell
# .\.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
pip install -r requirements-dev.txt
pip install -e .
pre-commit install
```

Para levantar la API + UI en local con un bundle sintético:

```bash
pip install -r requirements-api.txt -r requirements-train.txt
python scripts/_generate_model_fixture.py
python scripts/train_models.py \
    --fixture-mode \
    --etl-run-dir tests/fixtures/models/etl_run \
    --output-dir artifacts/dev-run \
    --seed 42
ALQUILERES_API_MODEL_BUNDLE_PATH=artifacts/dev-run/serving_bundle \
ALQUILERES_API_ALLOW_FIXTURE_MODEL=true \
python scripts/run_api.py
```

Abrir <http://127.0.0.1:8000/>.

## Docker

```bash
docker build \
  --build-arg APP_VERSION=$(python -c "import alquileres_uy;print(alquileres_uy.__version__)") \
  -t alquileres-uy-api:local .

docker run --rm -p 8000:8000 \
  -e ALQUILERES_API_MODEL_BUNDLE_PATH=/app/artifacts/serving_bundle \
  -v $(pwd)/artifacts/dev-run/serving_bundle:/app/artifacts/serving_bundle:ro \
  alquileres-uy-api:local
```

La imagen final lleva los `org.opencontainers.image.*` labels
(`version`, `source`, `description`, `licenses`). Ver
[`docs/deployment.md`](docs/deployment.md) para el detalle operativo.

## Docker Compose

El proyecto no incluye `docker-compose.yml` hoy — corre como un único
contenedor stateless. Un compose es útil cuando querés simular
Prometheus + Grafana en local; en `docs/architecture.md` hay un ejemplo
mínimo que se puede copiar como punto de partida.

## Variables de entorno

Todas las variables usan el prefijo `ALQUILERES_API_`. Los defaults
viven en `src/alquileres_uy/api/config.py`; la tabla completa está
en [`docs/deployment.md`](docs/deployment.md).

| Variable | Default | Notas |
| --- | --- | --- |
| `ALQUILERES_API_HOST` | `127.0.0.1` | Interfaz uvicorn. |
| `ALQUILERES_API_PORT` | `8000` | Puerto uvicorn. |
| `ALQUILERES_API_LOG_LEVEL` | `INFO` | Level del logger estructurado. |
| `ALQUILERES_API_MODEL_BUNDLE_PATH` | `artifacts/models/latest/serving_bundle` | Directorio con el serving bundle. |
| `ALQUILERES_API_ALLOW_FIXTURE_MODEL` | `false` | Debe ser `true` sólo en dev / tests. |
| `ALQUILERES_API_MAX_CONCURRENT_PREDICTIONS` | `4` | Semáforo del `PredictionService`. |
| `ALQUILERES_API_PREDICT_TIMEOUT` | `5.0` | Timeout por request en segundos. |
| `ALQUILERES_API_ENABLE_METRICS` | `true` | Deshabilita `/metrics` cuando `false`. |
| `ALQUILERES_API_METRICS_PATH` | `/metrics` | Ruta del endpoint Prometheus. |

## Entrenamiento

Fase 3 corre en modo fixture (los datos reales requieren
`ETL_PRODUCTION_VALIDATED`, hoy no disponible). Detalle del protocolo
`tune-then-refit-v2` y de los cuatro modelos entrenados en
[`docs/model-training-contract.md`](docs/model-training-contract.md).

```bash
pip install -r requirements-train.txt requirements-torch-cpu.txt
python scripts/train_models.py \
    --fixture-mode \
    --etl-run-dir tests/fixtures/models/etl_run \
    --output-dir artifacts/dev-run \
    --include-torch \
    --seed 42
```

## API

Endpoints públicos:

| Método | Ruta | Descripción |
| --- | --- | --- |
| `GET` | `/health` | Probe de liveness. |
| `GET` | `/ready` | Probe de readiness del modelo. |
| `GET` | `/version` | Versión de API + versión / SHA del bundle. |
| `GET` | `/build` | Metadata de build: version, git commit, build date, python. |
| `GET` | `/metrics` | Exposición Prometheus. |
| `POST` | `/predict` | Estimación de precio a partir del payload de propiedad. |

Contratos, ejemplos y errores en [`docs/api.md`](docs/api.md).

## Frontend

Interfaz web servida por FastAPI en `GET /`:

- Jinja2 templates + vanilla JS + CSS propio (sin frameworks).
- Formulario con validación HTML + validación cliente + envío por
  `fetch()`.
- Historial local (localStorage, hasta 10 predicciones), botón
  "Cargar ejemplo", copiar resultado al portapapeles, comparación con
  precio publicado (semáforo 🟢🟡🔴 con barra visual y interpretación
  textual).
- Accesibilidad reforzada: labels 1:1, `aria-describedby`,
  `:focus-visible`, `prefers-reduced-motion`, skip link, contraste
  WCAG-AA.

## Observabilidad

- **Prometheus** — `prediction_requests_total`,
  `prediction_errors_total`, `prediction_latency_seconds` y
  `model_loaded`, más las métricas de proceso estándar del cliente.
- **Logs estructurados** — una línea por request con `request_id`,
  método, endpoint, status_code, duration_ms y model_version. Nunca
  contiene payload, coordenadas ni precio.
- **Request-ID** — middleware que inyecta / respeta el header
  `X-Request-ID` y lo propaga por logs vía `ContextVar`.

Runbook en [`docs/operations.md`](docs/operations.md).

## Testing

```bash
pytest -q -m "not torch"       # suite clásica (rápida)
pytest -q -m torch             # suite PyTorch (más lenta)
pytest -q                      # todo
```

- **932+** tests que cubren ingesta, ETL, entrenamiento, API, runtime
  reliability, release engineering, UI y polish.
- Constraint desde Fase 4: **sin `httpx` / sin `TestClient`**; se usa
  un harness ASGI custom bajo `tests/api/`.
- Sin Selenium / Playwright / Cypress en la parte de UI — los tests
  inspeccionan HTML / CSS / JS empaquetados + drivean el ASGI para
  chequeos end-to-end.

## CI

Workflow `.github/workflows/ci.yml` corre en cada PR + push a `main`:

| Job | Qué hace |
| --- | --- |
| `Quality + classical models` | ruff + format + `pytest -m "not torch"` + `python -m build` + smoke training clásico |
| `PyTorch CPU` | Instala PyTorch CPU + `pytest -m torch` + smoke training con `--include-torch` |
| `Docker image build (no push)` | Construye la imagen sin publicarla |
| `Release readiness check` | Verifica CHANGELOG, version sync, `build_info.json`, wheel + sdist, Docker labels |

## Release

- **Single-source semver** en `src/alquileres_uy/_version.py`.
  `pyproject.toml` lo lee vía `[tool.setuptools.dynamic]`; la API,
  Docker y CI derivan de ahí.
- **CHANGELOG** en formato Keep a Changelog.
- **`scripts/release.py`** — valida árbol limpio, corre tests, chequea
  CHANGELOG, crea el tag anotado `v<version>` y sugiere próxima
  versión. **Nunca hace push automáticamente.**
- **`.github/workflows/release.yml`** — corre sobre tags `v*`,
  construye wheel + sdist + imagen Docker, sube artefactos y crea un
  GitHub Release (draft) con el bloque correspondiente del CHANGELOG.

Detalle en [`docs/upgrade.md`](docs/upgrade.md).

## Roadmap

- **v0.11.x** — cobertura de nuevas fuentes de datos (Infocasa,
  Gallito) y source gate ampliado.
- **v0.12.x** — feature engineering geoespacial: enriquecer con POIs,
  distancia a rambla, transporte público.
- **v0.13.x** — evaluación temporal continua (backtesting mensual).
- **v1.0.0** — corrida real end-to-end con `MODEL_PRODUCTION_VALIDATED`.

## Licencia

MIT — ver [`LICENSE`](LICENSE).

## Documentación

| Documento | Qué cubre |
| --- | --- |
| [`docs/architecture.md`](docs/architecture.md) | Arquitectura general + Mermaid |
| [`docs/api.md`](docs/api.md) | Contratos HTTP con ejemplos |
| [`docs/portfolio.md`](docs/portfolio.md) | Narrativa para entrevistas |
| [`docs/deployment.md`](docs/deployment.md) | Deploy + env vars |
| [`docs/operations.md`](docs/operations.md) | Runbook operacional |
| [`docs/upgrade.md`](docs/upgrade.md) | Rollback + semver |
| [`docs/demo.md`](docs/demo.md) | Guión de la demo en video |
| [`docs/project-tree.md`](docs/project-tree.md) | Árbol del repositorio |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | Cómo contribuir |
| [`CHANGELOG.md`](CHANGELOG.md) | Cambios por versión |
