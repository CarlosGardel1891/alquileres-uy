# alquileres-uy

Pipeline end-to-end para ingesta, procesamiento y predicción de precios de alquileres mensuales en Montevideo.

> Estado: bootstrap técnico en progreso. Todavía no existe un modelo entrenado ni una demo desplegada.

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
