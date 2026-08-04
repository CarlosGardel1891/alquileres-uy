# Decisiones técnicas

Este documento registra las decisiones que enmarcan la construcción del proyecto. Cada decisión describe qué se eligió y por qué. Cambios significativos deben registrarse aquí.

## Python 3.12

El proyecto usa **Python 3.12** como versión de referencia.

Motivación:

- Compatibilidad estable con las librerías de datos y machine learning que se usarán en fases siguientes (`pandas`, `scikit-learn`, `LightGBM`, `PyTorch`, `FastAPI`).
- Buen equilibrio entre madurez del ecosistema y disponibilidad de wheels precompilados.
- Alineación con las versiones soportadas por los entornos de deploy previstos.

Se congela la versión mayor y menor en `.python-version` y en `pyproject.toml` mediante `requires-python = ">=3.12,<3.13"` para evitar migraciones accidentales.

## Estructura `src/`

El paquete `alquileres_uy` vive dentro de `src/` en lugar de estar directamente en la raíz del repositorio.

Motivación:

- Evita importar accidentalmente código desde el directorio de trabajo (por ejemplo, cuando se corren tests con el cwd en la raíz).
- Obliga a instalar el paquete correctamente (`pip install -e .`) para poder importarlo, lo que hace explícita la superficie pública.
- Facilita separar código productivo (`src/`) de código de soporte (`tests/`, `scripts/`, `notebooks/`).

## Datos crudos inmutables

Los archivos ubicados en `data/raw/` son **inmutables** una vez descargados.

- Las correcciones se hacen re-ejecutando el pipeline sobre los datos originales, no editando los archivos crudos.
- Los datos derivados se materializan en `data/processed/` y son regenerables.
- `data/` no se versiona; se documenta la fuente y la forma de obtenerlo.

Esto garantiza reproducibilidad y elimina la ambigüedad sobre "qué versión del dato" se usó en cada entrenamiento.

## Render de solo lectura

El servicio desplegado (Render u otro PaaS equivalente) opera en **modo de solo lectura**.

- No se ejecuta scraping desde el servicio en producción.
- No se ejecutan entrenamientos desde el servicio en producción.
- No se escriben datos persistentes en el filesystem del servicio, porque es efímero y no confiable.

Los artefactos de modelo se generan offline y se empaquetan con el deploy o se descargan al arrancar desde un almacenamiento externo definido en fases posteriores.

## Separación de dependencias

A medida que crezca el proyecto se dividirán las dependencias en archivos específicos:

- `requirements-api.txt`: dependencias mínimas para servir la API (por ejemplo `fastapi`, `pydantic`, cliente del modelo desplegado).
- `requirements-train.txt`: dependencias para entrenamiento clásico (`pandas`, `scikit-learn`, `LightGBM`).
- `requirements-spike.txt`: dependencias exploratorias, notebooks, EDA.
- `requirements-torch-cpu.txt`: PyTorch en su variante CPU, aislado del resto.

**PyTorch no formará parte de la imagen de la API** para mantener el runtime liviano y evitar arrastrar dependencias pesadas en el path crítico.

En Fase 0 el único archivo es `requirements-dev.txt` con herramientas de calidad.

## Modelos que se compararán

Se evaluarán múltiples familias de modelos para predecir precios:

- **Baseline por barrio:** mediana o media condicionada por barrio y tipo de propiedad. Sirve de piso obligatorio.
- **Regresión lineal:** modelo interpretable, útil para diagnosticar features y outliers.
- **LightGBM:** modelo de gradient boosting sobre tabular, esperado como candidato fuerte.
- **Red neuronal PyTorch:** para capturar interacciones no lineales complejas si el volumen de datos lo justifica.

El modelo desplegado será el que ofrezca **la mejor relación entre rendimiento predictivo, consumo de recursos y mantenibilidad**. No se asume de antemano que PyTorch será el ganador; la decisión se toma con evidencia empírica sobre el dataset real.

## Evaluación temporal

El split de entrenamiento y evaluación es **temporal**, no aleatorio.

- El conjunto de entrenamiento contiene publicaciones anteriores a un corte temporal.
- El conjunto de validación y test contiene publicaciones posteriores.

Motivación:

- El mercado de alquileres tiene tendencia y estacionalidad; un split aleatorio filtra información del futuro hacia el pasado y sobreestima el rendimiento.
- El objetivo de producción es predecir precios sobre publicaciones **nuevas**, por lo que la evaluación debe simular exactamente ese escenario.
- Reduce fuga de información y hace el número reportado comparable con lo que ocurrirá en producción.
