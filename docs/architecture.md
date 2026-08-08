# Arquitectura

`alquileres-uy` es un pipeline end-to-end. Este documento describe
cómo fluyen los datos desde la ingesta hasta la interfaz web, y qué
componentes viven en cada capa.

## Índice

- [Visión general](#visión-general)
- [Flujo de datos](#flujo-de-datos)
- [Ingesta](#ingesta)
- [ETL](#etl)
- [Entrenamiento](#entrenamiento)
- [Serving](#serving)
- [Frontend](#frontend)
- [Observabilidad](#observabilidad)
- [Docker + Compose (opcional)](#docker--compose-opcional)

## Visión general

```mermaid
flowchart LR
  subgraph Ingesta [Fase 1 · Ingesta]
    Source[MercadoLibre API]
    Gate[Source Gate\ncoverage.json + approval]
    Ingest[run_ingestion.py]
    Raw[(data/raw/**)]
    SQLite[(data/ingestion.sqlite)]
  end

  subgraph ETL [Fase 2 · ETL]
    ETLRun[run_etl.py]
    Processed[(data/processed/**)]
  end

  subgraph Training [Fase 3 · Entrenamiento]
    Train[train_models.py]
    Bundle[serving_bundle/]
  end

  subgraph Serving [Fase 4..9 · API + Runtime]
    Loader[ModelLoader]
    Predictor
    Service[PredictionService]
    API[FastAPI /predict /health /ready /version /build /metrics]
  end

  subgraph UI [Fase 11..13 · Frontend]
    Web[Jinja2 templates + vanilla JS + CSS]
  end

  subgraph Ops [Fase 8 + 10 · Ops]
    Prom[Prometheus /metrics]
    Logs[Structured logs]
    Release[release.yml + release-check]
  end

  Source -->|search + multiget| Gate
  Gate --> Ingest
  Ingest --> Raw
  Ingest --> SQLite
  Raw --> ETLRun
  ETLRun --> Processed
  Processed --> Train
  Train --> Bundle
  Bundle --> Loader
  Loader --> Predictor
  Predictor --> Service
  Service --> API
  API --> Web
  API --> Prom
  API --> Logs
  Bundle -.->|minimum_api_version| Loader
```

## Flujo de datos

```mermaid
sequenceDiagram
  participant U as Usuario
  participant W as Web UI
  participant A as FastAPI
  participant S as PredictionService
  participant P as Predictor
  participant M as ModelLoader / bundle

  Note over A,M: Startup (Fase 9): load bundle → verify minimum_api_version<br/>→ warmup dummy predict → publish service
  U->>W: Completa formulario
  W->>A: POST /predict {property_type, price, bedrooms, ...}
  A->>S: predict(request)
  S->>S: semaphore.acquire() (async)
  S->>P: predict(request) en asyncio.to_thread + asyncio.timeout
  P->>M: features via bundle.feature_order
  M-->>P: modelo entrenado
  P-->>S: PredictionResult
  S-->>A: PredictResponse
  A-->>W: {prediction, currency, model_version, prediction_timestamp}
  W->>U: Renderiza precio + comparación con precio publicado
```

## Ingesta

```mermaid
flowchart TB
  Gate[Source Gate\nrun_source_gate.py]
  Approval{{source_gate_approval.json}}
  Ingest[run_ingestion.py]
  Raw[(data/raw/mercadolibre/&lt;ts&gt;_&lt;run-id&gt;)]
  DB[(data/ingestion.sqlite)]

  Gate -->|APPROVED| Approval
  Approval -->|hash + campos verificados| Ingest
  Ingest -->|JSON crudo| Raw
  Ingest -->|control + idempotencia| DB
```

Puntos clave:

- El gate recorre jerárquicamente `/sites/{site_id}/categories`
  hasta encontrar las categorías finales (`apartment`, `house`) o
  aborta con `INCONCLUSIVE`.
- El approval **no** es el contrato final: es un puntero al
  `coverage.json`. El loader releé el coverage, valida su hash y
  compara campo por campo.
- La ingesta es idempotente por `item_id`: dos corridas no duplican
  filas.

## ETL

```mermaid
flowchart LR
  Raw[(raw run + manifest.json)]
  Contracts[Contratos<br/>data_mode, unidades,<br/>timestamps]
  Runner[run_etl.py]
  Canonical[listings.parquet]
  Ready[model_ready.parquet]
  Rejected[rejected_listings.parquet]
  Dups[duplicate_candidates.parquet]
  Reports[etl_summary.json<br/>data_quality_report.json<br/>lineage.json<br/>schema.json]

  Raw --> Runner
  Contracts --> Runner
  Runner --> Canonical
  Runner --> Ready
  Runner --> Rejected
  Runner --> Dups
  Runner --> Reports
```

- **Publicación atómica**: el ETL escribe en `<workdir>.tmp` y sólo
  renombra al final.
- **Lineage**: `lineage.json` es el último archivo; incluye hashes
  SHA-256 de todos los inputs y outputs.
- **Modo fixture** vs. **modo real** — sólo el modo real requiere
  approval con hashes coincidentes.

## Entrenamiento

```mermaid
flowchart TB
  Ready[model_ready.parquet]
  Split[Split temporal estricto<br/>train &lt; val &lt; test]
  subgraph Tune [1. Tuning]
    Baseline
    Ridge
    LGBM[LightGBM]
    Torch[PyTorch tabular]
  end
  Metrics[Validation metrics]
  Select[best_overall<br/>serving_candidate]
  Refit[2. Final refit<br/>train + validation]
  Test[Test metrics<br/>una única vez]
  Interval[residual_interval.json<br/>del tuning model del serving]
  Bundle[serving_bundle/]

  Ready --> Split
  Split --> Tune
  Tune --> Metrics
  Metrics --> Select
  Select --> Refit
  Refit --> Test
  Refit --> Interval
  Refit --> Bundle
```

- Protocolo `tune-then-refit-v2`: el intervalo residual y las
  métricas de validation salen del tuning model; test se toca una
  única vez.
- PyTorch queda fuera del serving por decisión de arquitectura
  (evita cargar runtime de Torch en la imagen de API).

## Serving

```mermaid
flowchart LR
  Bundle[serving_bundle/]
  Loader[ModelLoader]
  Predictor
  Service[PredictionService<br/>semaphore + timeout + shutdown]
  App[FastAPI app]
  subgraph Endpoints
    Health[/GET /health/]
    Ready[/GET /ready/]
    Version[/GET /version/]
    Build[/GET /build/]
    Metrics[/GET /metrics/]
    Predict[/POST /predict/]
  end

  Bundle -->|checksums + minimum_api_version| Loader
  Loader --> Predictor
  Predictor --> Service
  Service --> App
  App --> Endpoints
```

- **Warmup** al startup: una predicción sintética a través del
  Predictor. Nunca toca Prometheus.
- **Timeout** vía `asyncio.timeout(PREDICT_TIMEOUT)` → HTTP 503
  con `prediction_timeout`.
- **Graceful shutdown**: `begin_shutdown()` rechaza nuevos,
  `wait_for_drain()` espera in-flight.

## Frontend

```mermaid
flowchart LR
  Templates[templates/base.html<br/>templates/index.html]
  Static[static/css/styles.css<br/>static/js/app.js<br/>static/favicon.svg]
  Web[/GET / (HTML)/]
  Fetch[fetch()]
  API[API JSON endpoints]
  LS[(localStorage:<br/>form + history)]

  Templates --> Web
  Static --> Web
  Web -->|POST /predict| Fetch
  Fetch --> API
  Web -->|save/restore| LS
```

- **Sin frameworks JS**: sólo `fetch`, `Intl.NumberFormat` y APIs
  del DOM.
- **Historial local**: hasta 10 predicciones, sin lat / lng / price
  (evitar fuga de PII a disco).
- **A11y**: `aria-live` en resultado, `aria-describedby` en cada
  input, `:focus-visible` outline, `prefers-reduced-motion` guard.

## Observabilidad

```mermaid
flowchart LR
  Req[Cliente HTTP]
  RID[RequestIdMiddleware]
  MW[MetricsMiddleware]
  Route[Endpoint handler]
  Log[Structured logs<br/>request_id · duration_ms]
  Prom[Prometheus registry]
  Metrics[/GET /metrics/]

  Req --> RID
  RID --> MW
  MW --> Route
  MW --> Log
  MW --> Prom
  Prom --> Metrics
```

Métricas expuestas:

| Métrica | Tipo | Labels |
| --- | --- | --- |
| `prediction_requests_total` | Counter | endpoint, method, status_code |
| `prediction_errors_total` | Counter | endpoint, method, status_code |
| `prediction_latency_seconds` | Histogram | endpoint, method |
| `model_loaded` | Gauge | — |

Logs: una línea por request; nunca incluye payload, coordenadas ni
precio (política Fase 7+).

## Docker + Compose (opcional)

El proyecto se despliega como un único contenedor stateless. Un
`docker-compose.yml` no está incluido en el repositorio, pero el
patrón mínimo para desarrollo con Prometheus local es:

```yaml
version: "3.9"
services:
  api:
    build:
      context: .
      args:
        APP_VERSION: 0.10.0
    ports:
      - "8000:8000"
    environment:
      ALQUILERES_API_MODEL_BUNDLE_PATH: /app/artifacts/serving_bundle
    volumes:
      - ./artifacts/dev-run/serving_bundle:/app/artifacts/serving_bundle:ro

  prometheus:
    image: prom/prometheus:latest
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml:ro
```

Sirve como referencia — no se prueba en CI.
