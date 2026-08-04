# alquileres-uy

Pipeline end-to-end para ingesta, procesamiento y predicción de precios de alquileres mensuales en Montevideo.

> Estado: Fase 0 completada. Fase 1 (ingesta MercadoLibre) en curso. Todavía no existe un modelo entrenado ni una demo desplegada.

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

Sólo si el source gate devolvió `0`.

```bash
python scripts/run_ingestion.py --max-items 100        # corrida chica de validación
python scripts/run_ingestion.py --max-items 5000       # corrida completa
python scripts/run_ingestion.py --dry-run              # imprime el plan, sin red
```

Flags disponibles: `--max-items`, `--requests-per-second`, `--timeout`, `--max-attempts`, `--output-dir`, `--database-path`, `--dry-run`.

Cada corrida escribe sus datos crudos en `data/raw/mercadolibre/<timestamp>_<run-id>/`, con subdirectorios `searches/`, `items/`, `descriptions/`, `errors/`, más `manifest.json` e `ingestion_summary.json`.

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
