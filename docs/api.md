# API HTTP

Contratos completos de los endpoints públicos de `alquileres-uy`.
Todo lo que no aparece acá **no** es parte del contrato.

Base URL en desarrollo: `http://127.0.0.1:8000`. Todos los responses
son JSON salvo `/metrics` (Prometheus text) y `/` (HTML).

Todo request 5xx incluye el header `X-Request-ID` con el mismo id que
llegó (o uno nuevo, generado por `RequestIdMiddleware`).

## Índice

- [`GET /health`](#get-health)
- [`GET /ready`](#get-ready)
- [`GET /version`](#get-version)
- [`GET /build`](#get-build)
- [`GET /metrics`](#get-metrics)
- [`POST /predict`](#post-predict)
- [Envelope de errores](#envelope-de-errores)

## `GET /health`

Probe de liveness. No depende del modelo; sólo confirma que el
proceso está aceptando requests.

**Response 200**

```json
{ "status": "ok" }
```

**Uso recomendado**: liveness probe de Kubernetes / Docker.

## `GET /ready`

Probe de readiness. Devuelve 200 cuando el bundle está cargado y
`Predictor.predict` está disponible; 503 en caso contrario.

**Response 200**

```json
{ "status": "ready" }
```

**Response 503**

```json
{ "status": "not_ready" }
```

**Uso recomendado**: readiness probe de Kubernetes; también lo
consume la UI para pintar el indicador ● Online / ● Inicializando.

## `GET /version`

Devuelve versión de API + versión / SHA del bundle cargado.
Los valores vienen del `metadata.json` del bundle — nunca se
reconstruyen.

**Response 200**

```json
{
  "api_version": "0.10.0",
  "model_version": "0.10.0",
  "model_type": "lightgbm",
  "trained_at": "2026-08-01T12:00:00+00:00",
  "bundle_sha256": "abcdef1234567890..."
}
```

**Response 503** — cuando no hay bundle:

```json
{
  "error": {
    "code": "model_unavailable",
    "message": "Model is not available"
  }
}
```

## `GET /build`

Metadata de build. Los valores salen del `build_info.json` empaquetado
por `scripts/generate_build_info.py`. Nada se hardcodea a request-time.

**Response 200**

```json
{
  "version": "0.10.0",
  "git_commit": "36cca1d000",
  "build_date": "2026-08-08T14:03:00+00:00",
  "python_version": "3.12.10",
  "platform": "Linux-5.15-x86_64-with-glibc2.35",
  "api_version": "0.10.0"
}
```

Si el archivo falta (por ejemplo un editable install sin correr el
generator), los campos `git_commit` y `build_date` valen `"unknown"`
y el resto se sintetiza — la forma del payload no cambia.

## `GET /metrics`

Expone métricas Prometheus en el formato text-based (Content-Type
`text/plain; version=0.0.4; charset=utf-8`). Excluido de sus propios
contadores.

Snippet de ejemplo:

```
# HELP prediction_requests_total ...
# TYPE prediction_requests_total counter
prediction_requests_total{endpoint="/predict",method="POST",status_code="200"} 4.0
prediction_requests_total{endpoint="/health",method="GET",status_code="200"} 12.0

# HELP prediction_latency_seconds ...
# TYPE prediction_latency_seconds histogram
prediction_latency_seconds_bucket{endpoint="/predict",le="0.005",method="POST"} 0.0
...

# HELP model_loaded ...
# TYPE model_loaded gauge
model_loaded 1.0
```

Se puede deshabilitar en un entorno controlado con
`ALQUILERES_API_ENABLE_METRICS=false`.

## `POST /predict`

Estima el precio mensual de un alquiler.

**Request**

```http
POST /predict HTTP/1.1
Content-Type: application/json

{
  "property_type": "apartment",
  "price": 950,
  "bedrooms": 2,
  "bathrooms": 1,
  "covered_area": 58,
  "total_area": 65,
  "latitude": -34.9067,
  "longitude": -56.1553,
  "neighborhood": "Pocitos"
}
```

| Campo | Tipo | Reglas |
| --- | --- | --- |
| `property_type` | string | `apartment` o `house`. |
| `price` | number > 0 | Precio publicado que el cliente quiere comparar. |
| `bedrooms` | int ≥ 0 | Dormitorios. |
| `bathrooms` | int ≥ 0 | Baños. |
| `covered_area` | number > 0 | Superficie cubierta (m²). Debe ser ≤ `total_area`. |
| `total_area` | number > 0 | Superficie total incluida terrazas / patio. |
| `latitude` | number ∈ [-90, 90] | Latitud de la propiedad. |
| `longitude` | number ∈ [-180, 180] | Longitud de la propiedad. |
| `neighborhood` | string no vacío | Nombre del barrio. |

**Response 200**

```json
{
  "prediction": 1123.5,
  "currency": "USD",
  "model_version": "0.10.0",
  "prediction_timestamp": "2026-08-08T14:12:34+00:00"
}
```

**Response 422** — validación Pydantic (uno o más campos fuera de
rango):

```json
{
  "error": {
    "code": "validation_error",
    "message": "Input validation failed",
    "details": [
      {
        "field": "latitude",
        "message": "Input should be greater than or equal to -90"
      }
    ]
  }
}
```

**Response 500** — falla interna del `Predictor`:

```json
{
  "error": {
    "code": "prediction_failed",
    "message": "..."
  }
}
```

**Response 503 — timeout de predicción** (`PredictionService`
excedió `ALQUILERES_API_PREDICT_TIMEOUT`):

```json
{
  "error": {
    "code": "prediction_timeout",
    "message": "Prediction timed out."
  }
}
```

Genera `prediction_errors_total{endpoint="/predict",method="POST",status_code="503"}`.

**Response 503 — servicio drenando**:

```json
{
  "error": {
    "code": "service_unavailable",
    "message": "Service is shutting down"
  }
}
```

Se dispara cuando el proceso recibió SIGTERM y no acepta más
requests hasta que termine el drain.

## Envelope de errores

Todos los responses no-2xx respetan el mismo envelope:

```json
{
  "error": {
    "code": "<string>",
    "message": "<string>"
  }
}
```

`details` puede aparecer en errores de validación (422). Nunca se
serializa un traceback o el payload original — el error handler
está en `src/alquileres_uy/api/errors.py` y es parte del contrato
público desde Fase 7.

Todas las respuestas de error llevan el header `X-Request-ID` para
correlacionar con la línea correspondiente del log estructurado.
