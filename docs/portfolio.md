# Portfolio — `alquileres-uy`

Guía narrativa del proyecto pensada para presentarlo en entrevistas
técnicas o revisar el alcance rápidamente.

## Elevator pitch

Un pipeline reproducible que va desde la ingesta cruda de publicaciones
de alquiler en Montevideo hasta una API HTTP + UI web que estima el
precio mensual de una propiedad y lo compara con el precio publicado.
Se construyó en 14 fases entregables, cada una en su propia PR y con
CI verde antes de mergear.

## El problema

No existe un dataset abierto y actualizado de precios de alquiler
mensual en Uruguay. Cualquier evaluación de "¿este alquiler está caro?"
depende de intuición, comparación con vecinos o recorrer publicaciones
manualmente. El proyecto entrega:

- una fuente de verdad reproducible (ingesta + ETL + modelo);
- una API con contratos estables (`/predict`, `/version`, `/metrics`);
- una interfaz visual pública para hacer la comparación de un click.

## Decisiones técnicas relevantes

| Decisión | Alternativas descartadas | Por qué |
| --- | --- | --- |
| **Source Gate previo a la ingesta** | Ir directo con retries genéricos | Nunca ejecutar una ingesta masiva contra una fuente que no aprobó cobertura. El gate es un contrato con hash + evidencia auditable. |
| **Protocolo `tune-then-refit-v2`** | Grid search estándar | Elimina fuga de validation: el intervalo residual y la selección salen del tuning model; test se toca una única vez. |
| **PyTorch fuera del bundle de serving** | Incluir el modelo torch en el bundle | Evita cargar el runtime completo de Torch en la imagen de API. El selector se limita a baseline / Ridge / LightGBM. |
| **Custom ASGI harness** | `httpx.AsyncClient` o `TestClient` | Los tests corren sin librería HTTP extra ni un event loop compartido; funciona con `asyncio.run` puro y evita bugs de `TestClient` con lifespan + Prometheus. |
| **PredictionService entre Predictor y router** | Semáforo dentro del router | Concurrencia + timeout + shutdown gracioso viven en una capa dedicada, testeada aparte del transporte HTTP. |
| **`minimum_api_version` en el bundle** | Sin validación de compat | Un bundle emitido para una API futura no arranca en un proceso viejo — falla ruidosamente al startup en vez de generar predicciones inválidas. |
| **Single-source semver** | Duplicar version en pyproject, config, Docker | `_version.py` es la fuente de verdad; `pyproject.toml` la lee vía `[tool.setuptools.dynamic]`. Un bump = un commit. |
| **UI vanilla-JS** | React / Vue / Alpine | Sin bundler, sin toolchain de frontend; se sirve con `StaticFiles` desde el mismo proceso. Testeable inspeccionando HTML/JS/CSS + drivando el ASGI. |
| **Historial en localStorage sin coordenadas** | Persistir todo el payload | Evita fuga a disco de lat/lng/precio; el usuario ve historial útil sin regalar location. |

## Desafíos

### 1. Source Gate contra MercadoLibre bloqueado por `403`

La fuente elegida (MercadoLibre Uruguay) responde `403` con
`PolicyAgent` a los endpoints de sitio sin token oficial. El pipeline
lo detecta y devuelve `INCONCLUSIVE`, dejando evidencia sanitizada
(`search_no_auth.json`, `coverage.json`). El diseño previó este
escenario: no hay corrida masiva sin approval hash-validado, y el
`ETL` en modo real se rechaza sin `etl_production_approval.json`
consistente. Corolario: hoy el pipeline entrena en modo fixture y las
métricas de `experiments.md` están explícitamente marcadas como no
representativas.

### 2. Concurrencia + timeout + shutdown sin bloquear el event loop

`Predictor.predict` es sincrónico (LightGBM + sklearn). Envolverlo con
`asyncio.timeout` requiere ejecutarlo en `asyncio.to_thread` para no
tapar el loop. El `PredictionService` combina:

- `asyncio.Semaphore(MAX_CONCURRENT_PREDICTIONS)` — los requests que
  exceden esperan, nunca se rechazan.
- `asyncio.timeout(PREDICT_TIMEOUT)` — inferencias que exceden
  levantan `PredictionTimeoutError` → 503 con envelope estable.
- Graceful shutdown: `begin_shutdown()` rechaza nuevos y
  `wait_for_drain(timeout)` espera in-flight sin cancelarlos.

### 3. Contratos públicos vs. evolución interna

Cinco fases posteriores (Prometheus, request-id, timeout,
compat gate, release engineering) no debían romper el contrato de
`POST /predict` ni los headers de error. La disciplina fue:

- fase por fase, PR draft con lista explícita de "no modificar";
- tests que validan el envelope al inicio y al final de cada fase;
- `release-check` en CI que valida CHANGELOG + version consistency
  + labels Docker + wheel/sdist.

### 4. Testing sin `httpx`

Desde Fase 4 no se puede usar `httpx.AsyncClient` ni
`fastapi.testclient.TestClient`. Se resolvió con un harness ASGI
propio que construye el `scope`, corre el lifespan y captura los
mensajes de `send`. Es ~50 líneas, funciona con `asyncio.run` y no
tiene el warm-up de un event loop compartido.

## Aprendizajes

- **Contratos primero, código después**. El `manifest.json` +
  `lineage.json` + `checksums.json` del ETL / bundle previnieron una
  cantidad enorme de regresiones. Un test que compara hashes es más
  útil que uno que compara valores.
- **Cada fase termina en `main` con CI verde**. Poder revertir una
  fase entera con `git revert -m 1 <merge>` fue posible porque nunca
  se acumularon dos features en un mismo merge.
- **La documentación estable ahorra contexto**. `docs/decisions.md`
  y los contratos versionados sirvieron para retomar el proyecto
  después de semanas sin tocarlo.
- **Sin frameworks JS también se pueden hacer productos serios**. La
  UI cumple con validación cliente, historial, comparación visual,
  a11y WCAG-AA y estados de carga — todo con `fetch()` y CSS custom.
- **Runtime reliability barato**. Warmup + semáforo + timeout +
  drain se implementaron en menos de 200 líneas de Python; toda la
  ingeniería estuvo en los tests que reproducen la contención.

## Arquitectura resumida

Detalle completo en [`architecture.md`](architecture.md).

```
Ingesta → ETL → Entrenamiento → Serving bundle → API (/predict) → UI
```

Cada flecha es un contrato con hash. Cada rectángulo es un módulo
con tests que lo cubren aisladamente. El pipeline horizontal se cruza
con dos verticales: **observabilidad** (Prometheus + logs + request-id)
y **release engineering** (single-source semver, release workflow,
release-check job).

## Métricas del proyecto

| Métrica | Valor |
| --- | --- |
| Tests | **932+** (Fase 13) |
| Coverage aproximado | 90 %+ en `src/alquileres_uy/api` |
| PRs entregadas | 14 (Fase 0..13) |
| Jobs de CI por PR | 4 (quality, torch, docker, release-check) |
| Endpoints públicos | 6 (`/health`, `/ready`, `/version`, `/build`, `/metrics`, `/predict`) |
| Modelos entrenados | 4 (baseline, Ridge, LightGBM, PyTorch tabular) |
| Densidad de docs | 10+ archivos bajo `docs/` |

Todas las métricas del modelo son fixture — hasta que exista una
corrida real con approval, no se publican como "resultado del
proyecto".

## Tecnologías utilizadas

- **Lenguaje**: Python 3.12.
- **Data**: `pandas`, `pyarrow`, `pandera`, `requests`.
- **Modelos**: `scikit-learn`, `lightgbm`, `joblib`, PyTorch CPU.
- **API**: `fastapi`, `uvicorn`, `pydantic` v2, `pydantic-settings`.
- **Observabilidad**: `prometheus-client`, logging estructurado.
- **Frontend**: Jinja2 + vanilla JS + CSS propio.
- **Testing**: `pytest`, `pre-commit`, harness ASGI custom.
- **Empaquetado**: `setuptools` con `pyproject.toml` dinámico,
  `build`, wheel + sdist.
- **CI**: GitHub Actions (4 jobs), Docker Buildx, artefactos de
  training.
- **Release**: `softprops/action-gh-release`, OCI labels,
  `scripts/release.py`.

## Cómo mirar el código

Recorrido sugerido si sos revisor y tenés 30 minutos:

1. `README.md` (10 min) — quick start + roadmap + docs.
2. `docs/architecture.md` (5 min) — diagramas del flujo.
3. `src/alquileres_uy/api/prediction_service.py` (5 min) —
   semáforo + timeout + shutdown.
4. `src/alquileres_uy/api/lifespan.py` (3 min) — orden de startup
   con warmup + compat gate.
5. `tests/api/test_reliability.py` (5 min) — cómo se testea
   concurrencia sin httpx.
6. `.github/workflows/release.yml` + `ci.yml release-check` (2 min)
   — cómo se derivan wheel/sdist/Docker desde el tag.

## Estado y próximos pasos

- **v0.10.0** (actual) — release engineering + web UI + polish
  cerrado. Sin corrida real; toda la evaluación es sobre fixtures.
- **v0.11.x** — sumar fuentes adicionales al gate (Infocasa,
  Gallito).
- **v0.12.x** — features geoespaciales (POIs, transporte, distancia
  a rambla).
- **v1.0.0** — corrida real con `MODEL_PRODUCTION_VALIDATED` y demo
  desplegada.
