# alquileres-uy

Pipeline end-to-end para ingesta, procesamiento y predicción de precios de alquileres mensuales en Montevideo.

> Estado: Fase 0 completada. Fase 1 (ingesta MercadoLibre) **detenida por bloqueo del source gate** (ver más abajo). Todavía no existe un modelo entrenado ni una demo desplegada.

## Alcance

El proyecto integrará, en fases sucesivas:

- ingesta de publicaciones de alquiler desde fuentes públicas;
- ETL y normalización de datos;
- construcción de features geográficas y estructurales;
- entrenamiento y comparación de modelos de predicción de precios;
- servicio de inferencia expuesto vía API;
- interfaz de consulta para usuarios finales.

Esta primera fase (Fase 0) se limita a dejar la base técnica del repositorio: estructura, empaquetado, herramientas de calidad, tests, CI y documentación.

## Arquitectura prevista

- `src/alquileres_uy/`: paquete Python con toda la lógica reutilizable, organizado en submódulos por responsabilidad (`ingest`, `etl`, `features`, `models`, `api`).
- `scripts/`: entrypoints ejecutables que orquestan pipelines (ingesta, ETL, entrenamiento, tareas operativas).
- `notebooks/`: exploración, visualización y análisis. Nunca contiene lógica productiva.
- `data/`: almacenamiento local de datos crudos, procesados y de modelo. No versionado.
- `artifacts/`: modelos entrenados y artefactos derivados. No versionado.
- `docs/`: decisiones técnicas y documentación del proyecto.

## Estructura de carpetas

```
alquileres-uy/
├── .github/workflows/       # Pipelines de CI
├── artifacts/               # Modelos y artefactos (no versionados)
├── data/                    # Datos locales (no versionados)
│   ├── raw/
│   ├── processed/
│   └── model/
├── docs/                    # Decisiones técnicas
├── notebooks/               # Exploración y análisis
├── scripts/                 # Entrypoints operativos
├── src/alquileres_uy/       # Paquete Python principal
│   ├── api/
│   ├── etl/
│   ├── features/
│   ├── ingest/
│   └── models/
└── tests/                   # Suite de tests
```

## Requisitos

- Python **3.12** (ver `.python-version`).
- Git.
- Un entorno virtual local (`.venv`).

## Instalación local

Clonar el repositorio:

```bash
git clone https://github.com/CarlosGardel1891/alquileres-uy.git
cd alquileres-uy
```

Crear el entorno virtual:

```bash
python -m venv .venv
```

Activación en Windows (PowerShell):

```powershell
.\.venv\Scripts\Activate.ps1
```

Activación en Linux o macOS:

```bash
source .venv/bin/activate
```

Instalar dependencias de desarrollo y el paquete en modo editable:

```bash
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
pip install -e .
pre-commit install
```

## Comandos de calidad

Ejecutar la suite completa de checks antes de abrir un Pull Request:

```bash
ruff check .
ruff format --check .
pytest -q
python -m build
```

Ejecutar los hooks de pre-commit sobre todos los archivos:

```bash
pre-commit run --all-files
```

## Ingesta MercadoLibre (Fase 1)

La ingesta es un pipeline local, reproducible e idempotente. Descubre y persiste publicaciones de alquiler mensual en Montevideo desde MercadoLibre.

### Dependencias adicionales

```bash
pip install -r requirements-ingest.txt
```

Sólo agrega `requests` como dependencia productiva. El resto (SQLite, retries, CLI, hashing, timestamps) usa la biblioteca estándar.

### Autenticación opcional

El token se lee **exclusivamente** de la variable de entorno `MELI_ACCESS_TOKEN`. Nunca se registra, imprime ni guarda en artefactos. El source gate primero prueba anónimamente y sólo reintenta con token si la búsqueda devolvió `401` o `403`.

### 1. Ejecutar el source gate

Antes de cualquier ingesta, hay que aprobar la fuente:

```bash
python scripts/run_source_gate.py
```

Exit codes:

- `0` — APPROVED — se puede ejecutar la ingesta.
- `2` — REJECTED — la cobertura mínima no se cumple; detener la fase.
- `3` — INCONCLUSIVE — no fue posible probar la fuente (por ejemplo sin `401`/`403` claros y sin resultados); detener la fase.
- `1` — error inesperado.

Los artefactos del gate (respuestas crudas de búsqueda, batch de multiget, descripciones y `coverage.json`) quedan en `data/raw/mercadolibre/source_gate/<timestamp>_<id>/`.

### 2. Ejecutar la ingesta

Sólo si el source gate devolvió `0`. La ingesta **requiere** el flag `--gate-approval` apuntando al `source_gate_approval.json` emitido por esa corrida APPROVED. El pipeline valida internamente que el `source`, `site_id`, `category_ids` verificados y el SHA-256 del `coverage.json` referenciado coincidan; cualquier discrepancia termina en exit code `2` sin llamadas de red, sin escritura en SQLite y sin crear carpeta de corrida.

Reemplazá `PATH` por la ruta al `source_gate_approval.json` de tu corrida APPROVED (que hoy **no existe**: la fase está bloqueada, ver más abajo).

```bash
python scripts/run_ingestion.py --gate-approval PATH --dry-run              # imprime el plan real, sin red
python scripts/run_ingestion.py --gate-approval PATH --max-items 100        # corrida chica de validación
python scripts/run_ingestion.py --gate-approval PATH --max-items 5000       # corrida completa
```

Flags disponibles: `--gate-approval` (obligatorio), `--max-items`, `--requests-per-second`, `--timeout`, `--max-attempts`, `--output-dir`, `--database-path`, `--dry-run`.

Cada corrida escribe sus datos crudos en `data/raw/mercadolibre/<timestamp>_<run-id>/`, con subdirectorios `searches/`, `items/`, `descriptions/`, `errors/`, más `manifest.json` e `ingestion_summary.json`.

> Hasta que exista un source gate `APPROVED` real (con token oficial), no hay `source_gate_approval.json`. La ingesta masiva permanece **bloqueada por código**, no sólo por convención.

### Datos y persistencia

- Los datos crudos y `data/ingestion.sqlite` **no se versionan**. La carpeta `data/` está ignorada en `.gitignore`.
- Los archivos crudos son **inmutables**: nunca se modifican después de guardarse. Una nueva corrida escribe una carpeta nueva.
- `data/ingestion.sqlite` almacena únicamente control de la ingesta (corridas, consultas, IDs, errores, idempotencia). Los datos analíticos aparecerán como Parquet en la Fase 2.

### Idempotencia

La ingesta es idempotente respecto a `item_id`. Correr dos veces con el mismo plan:

- no duplica filas en la tabla `items`;
- conserva `first_seen_at`;
- actualiza `last_seen_at`;
- registra nuevas relaciones en `run_items` para la nueva corrida;
- crea una nueva carpeta cruda y no sobrescribe archivos anteriores.

### GitHub Actions

GitHub Actions **no** ejecuta la ingesta ni el source gate. Sólo instala dependencias y corre tests con fixtures locales (`ruff`, `pytest`, `pre-commit`, `build`).

## ETL (Fase 2)

El pipeline ETL transforma corridas crudas de ingesta en cuatro Parquet + JSON de trazabilidad bajo `data/processed/<timestamp>_<etl-run-id>/`. Detalle completo en `docs/etl-data-contract.md` y `docs/etl-quality-rules.md`.

### Dependencias

```bash
pip install -r requirements-etl.txt
```

Trae `pandas==2.2.3`, `pyarrow==18.1.0`, `pandera==0.22.1`.

### Modo fixture (CI + desarrollo)

```bash
python scripts/run_etl.py --fixture-mode \
    --input-run-dir tests/fixtures/etl/raw_run \
    --exchange-rate config/exchange_rate.example.json \
    --neighborhood-aliases config/neighborhood_aliases.json \
    --output-dir data/processed
```

Todos los outputs quedan marcados con `data_mode = "fixture"`. **Sus métricas no son resultados del proyecto** — el `data_quality_report.json` incluye un `warning` explícito al respecto.

### Modo real (bloqueado hoy)

Requiere una corrida real de ingesta y un `source_gate_approval.json` válido de la Fase 1:

```bash
python scripts/run_etl.py \
    --input-run-dir data/raw/mercadolibre/<timestamp>_<run-id> \
    --gate-approval data/raw/mercadolibre/source_gate/<...>/source_gate_approval.json \
    --exchange-rate <path> \
    --neighborhood-aliases config/neighborhood_aliases.json
```

Sin `--gate-approval` válido el CLI termina con exit code `2`, sin abrir sockets, sin crear SQLite, sin carpeta de corrida. Al día de hoy no existe approval real: el source gate sigue en `INCONCLUSIVE`, por lo que el modo real está **bloqueado por código**.

### Outputs

Cada corrida ETL escribe:

- `listings.parquet` — dataset canónico (una fila por `source_item_id`).
- `model_ready.parquet` — subconjunto estricto listo para entrenamiento (sin columnas derivadas del target).
- `rejected_listings.parquet` — filas rechazadas con el motivo (`rejection_reasons`) en cada una.
- `duplicate_candidates.parquet` — grupos conservadores de duplicados posibles entre inmobiliarias. **No** se eliminan filas del canonical.
- `etl_summary.json`, `data_quality_report.json`, `unmapped_attributes.json`, `lineage.json`, `schema.json`.

**Canonical vs. model-ready:** canonical acepta rows con opcionales faltantes (para no perder trazabilidad); model-ready exige `date_created`, `neighborhood_normalized`, `bedrooms`, `total_area_m2`, `price_usd`, `property_type` no nulos, superficie positiva y sin conflictos.

### Datos

`data/processed/**` y los Parquet no se versionan (ver `.gitignore`). Cada corrida escribe una carpeta nueva; ninguna corrida anterior se sobrescribe. La entrada cruda es de sólo lectura para el ETL.

### Estado actual

- Source gate real: `INCONCLUSIVE`.
- Datos reales procesados: **no**.
- Corridas reales de ETL: **no**.
- Estado de la fase: **ETL_CONTRACT_READY** (código, tests y CI aprobados; sin resultados reales).
- La Fase 3 (entrenamiento) queda bloqueada hasta que exista `ETL_PRODUCTION_VALIDATED`.

### Requisitos del source gate

- El gate sólo puede devolver `APPROVED` si **ambas** categorías del alcance cerrado (`apartment` y `house`) se verificaron contra el árbol vivo del sitio. La verificación **recorre jerárquicamente** el árbol partiendo de `/sites/{site_id}/categories` y consultando `/categories/{id}` para expandir `children_categories`; las categorías finales pueden estar varios niveles debajo del root. Un contrato parcial, ambiguo (dos candidatos para el mismo tipo) o incompleto fuerza `INCONCLUSIVE` y no crea `source_gate_approval.json`. Esto se valida en el gate, en el writer del approval, en el loader del approval y en el query plan.
- El recorrido usa un límite defensivo (`MAX_CATEGORY_DEPTH=10`, `MAX_CATEGORY_NODES=1000`), un `visited` set para evitar ciclos y coincidencia **exacta** normalizada contra un alias set fijo (`apartamento`, `apartment`, `casas`, etc.) — nunca substring.
- El **target combinado** del gate exige que al menos **16 de 20** publicaciones cumplan simultáneamente: operación *alquiler mensual* (`OPERATION.value_name` o `value_id` en la lista permitida, nunca inferido del título), tipo de propiedad *apartment* o *house* (vía categoría verificada o atributo `PROPERTY_TYPE`; contradicción entre ambos → `property_type_conflict` → inválido) y ubicación *Montevideo* (`location.state.name` normalizado). Coberturas separadas (por ejemplo 20 alquileres + 15 casas) **no** sustituyen el combinado.
- Cada probe de búsqueda deja evidencia sanitizada bajo `search_no_auth.json` y — sólo si realmente se ejecutó — `search_with_auth.json`. El formato es `{"request": {method, endpoint, authenticated}, "response": {status_code, body|error_type|message}}`. Se guarda tanto para respuestas `200` como para `401`, `403`, timeouts y demás fallos de red. `status_code` puede ser `null` cuando no hubo respuesta HTTP.
- `token_used` significa "se envió un bearer token en al menos una llamada". Se marca `true` en el momento en que el pipeline **decide** ejecutar la llamada autenticada — aun si esa llamada termina en `403` o timeout. No es un flag de éxito.
- Tokens y headers de autorización se redactan en todos los artefactos, tanto por clave sensible (`authorization`, `access_token`, `token`, `cookie`, `x-auth-token`, case-insensitive) como por reemplazo literal del valor conocido del token cuando se pasa a `sanitize_for_artifact`.
- El `source_gate_approval.json` es **sólo un puntero** al `coverage.json`. El loader releé la cobertura, valida su hash SHA-256, y compara campo por campo (`category_ids`, `available_filters`, `operation_filter.mode`, `sample_size`) contra el approval. También re-valida umbrales (sample_size=20; cada campo esencial ≥16/20; date_created ≥16/20; target combinado ≥16/20). Si alguien manipula sólo el approval (por ejemplo agregando `garage`), el pipeline lo rechaza. El contrato final se construye desde el coverage, no desde el approval. Además, `source_gate_report_path` se resuelve estrictamente dentro del directorio del approval — `..`, rutas absolutas o traversal fuera se rechazan con `SourceGateApprovalIntegrityError`.

### Resultado del source gate (2026-08-04)

- **Decisión:** `INCONCLUSIVE` (exit code `3`).
- **Token usado:** no (no hay `MELI_ACCESS_TOKEN`, así que el gate ni siquiera intenta la llamada autenticada).
- **Motivo:** MercadoLibre respondió `403 forbidden` (con `blocked_by: PolicyAgent`) a `GET /sites/MLU/search` y otros endpoints del sitio sin token. El endpoint puntual `/categories/{id}` sí responde `200`, lo que confirma que sólo los recursos del sitio están cerrados anónimamente.
- **Categorías verificadas:** **ninguna** — sin acceso al árbol del sitio, el resolver jerárquico (`CategoryTreeResolver`) no se llegó a invocar; el gate se detuvo antes por el `403`. La lógica del recorrido BFS con límites defensivos, normalización de nombres y detección de ambigüedad quedó **implementada y testeada con fixtures** (`tests/ingest/test_category_tree.py`), pero todavía no se verificó contra el árbol real. La constante hardcodeada anterior (`MLU1466` como "Apartamentos") era incorrecta: el endpoint real la devuelve como "Casas".
- **Evidencia local:** `data/raw/mercadolibre/source_gate/<timestamp>_<id>/coverage.json` y `search_no_auth.json` (wrapper con `{request, response: {status_code: 403, body: {...}}}`, sin tokens).
- **Consecuencia:** la ingesta masiva **no** se ejecutó y no puede ejecutarse. El script `run_ingestion.py` requiere un `source_gate_approval.json` con hash del reporte de cobertura **y** las dos categorías verificadas; hoy ese artefacto no existe.
- **Próximos pasos posibles:** obtener token oficial de MercadoLibre, priorizar otra fuente, o alcance reducido con `/categories`.
- **Detalle:** `docs/mercadolibre-source-contract.md`.

## Fases del proyecto

- **Fase 0 — Bootstrap técnico (en curso):** estructura del repositorio, empaquetado, Ruff, Pytest, pre-commit, CI y documentación de decisiones.
- **Fase 1 — Ingesta:** obtención sistemática de publicaciones de alquiler.
- **Fase 2 — ETL y normalización:** limpieza, deduplicación y unificación de esquemas.
- **Fase 3 — Features:** enriquecimiento geográfico y de contexto.
- **Fase 4 — Modelado:** comparación de baseline, regresión lineal, LightGBM y red neuronal PyTorch.
- **Fase 5 — Servicio:** API de inferencia y despliegue de solo lectura.
- **Fase 6 — Interfaz:** frontend público de consulta.

## Estado actual

Todavía no existe:

- un modelo entrenado;
- métricas de evaluación;
- una demo desplegada;
- una API pública.

Ver `docs/decisions.md` para las decisiones técnicas que enmarcan las próximas fases.
