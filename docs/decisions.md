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

## MercadoLibre como fuente primaria

La fuente primaria de publicaciones es **MercadoLibre Uruguay** (`site_id = MLU`). Su uso queda **condicionado al source gate** documentado en `docs/mercadolibre-source-contract.md`.

Si el gate devuelve `REJECTED` o `INCONCLUSIVE`:

- no se implementa ni ejecuta la ingesta masiva sobre MercadoLibre;
- no se inicia scraping automáticamente sobre otra fuente (InfoCasas, Gallito);
- se detiene la fase y se entrega la evidencia (respuestas y cobertura) al TL para decidir una fase de fallback.

Esta decisión evita construir infraestructura sobre una fuente que no puede sostener el volumen o la calidad requerida.

## Segmentación en lugar de `search_type=scan`

Para la búsqueda pública general (`/sites/MLU/search`) **no se usa** `search_type=scan`.

La documentación oficial describe `search_type=scan` para `/users/{user_id}/items/search` (ítems de un usuario), no para la búsqueda general del sitio. Asumir lo contrario sería un supuesto no verificado que se sale del contrato observado.

En su lugar, cuando un segmento reporta más de ~900 resultados, la ingesta lo divide:

1. por rango de precio;
2. por dormitorios si sigue excedido;
3. eventualmente por barrio.

Los rangos son contiguos y sin huecos. La segmentación se registra en `queries` (SQLite) y en cada `manifest.json`.

## SQLite para control, no para datos analíticos

`data/ingestion.sqlite` almacena únicamente **control-plane**:

- corridas (`runs`);
- consultas ejecutadas (`queries`);
- IDs vistos (`items`) con idempotencia por `item_id`;
- relación entre corridas e ítems (`run_items`);
- errores permanentes (`request_errors`).

**No** contiene el payload analítico de las publicaciones. El payload analítico (con features derivadas) aparecerá como **Parquet** en la Fase 2, generado a partir de los archivos crudos en `data/raw/mercadolibre/`.

Esta separación deja a SQLite en un rol simple y auditable, y permite reprocesar el analítico sin tocar el control de corridas.

## Ingesta local

La ingesta real corre **localmente**, nunca desde GitHub Actions ni desde Render.

Motivación:

- GitHub Actions no debe emitir tráfico sostenido contra MercadoLibre desde IPs compartidas ni almacenar tokens.
- Render tiene filesystem efímero y no ofrece garantías de persistencia para carpetas crudas.
- Reproducibilidad y control quedan en la máquina de desarrollo; el pipeline de deploy sólo sirve modelos ya entrenados.

CI se limita a instalar dependencias y correr tests con fixtures locales.

## Datos crudos inmutables (refuerzo)

Una respuesta de MercadoLibre guardada en `data/raw/mercadolibre/**/` **nunca** se modifica:

- las escrituras son atómicas (`.tmp` + `os.replace`);
- `atomic_write_bytes` rehúsa sobrescribir un archivo existente;
- las nuevas corridas van a carpetas nuevas identificadas por `timestamp_run-id`;
- todas las correcciones se hacen re-parseando los originales.

Esto garantiza que cualquier resultado de ETL o entrenamiento se pueda reproducir bit-a-bit a partir de la evidencia original.

## Artefacto firmado del source gate

Cuando el source gate decide `APPROVED`, además del `coverage.json` emite un `source_gate_approval.json` en el mismo directorio. Ese archivo declara la fuente, el sitio, las categorías verificadas contra `/sites/{site_id}/categories`, y — crítico — el **SHA-256** del `coverage.json` referenciado.

El pipeline de ingesta (`scripts/run_ingestion.py`) requiere el flag `--gate-approval PATH`. Antes de abrir sockets, crear SQLite o escribir en disco:

1. lee el archivo;
2. valida que la decisión sea `APPROVED` y que la fuente/sitio coincidan con el target del proyecto;
3. valida que exista al menos un `category_ids` con IDs no vacíos;
4. relee `coverage.json` desde disco y recalcula su SHA-256;
5. compara con el hash almacenado en el approval.

Cualquier discrepancia (`SourceGateApprovalMissing`, `SourceGateApprovalInvalid`, `SourceGateApprovalIntegrityError`) termina el proceso en exit code `2` sin efectos secundarios.

Motivación:

- Un README con una advertencia no impide correr un comando por accidente. La restricción tiene que estar **en el código**.
- Sin este check, sería posible ejecutar la ingesta con categorías incorrectas hardcodeadas (`MLU1466` era "Casas", no "Apartamentos") y contaminar el dataset silenciosamente.
- El SHA-256 impide que alguien edite `coverage.json` a posteriori para "aprobar" una corrida que no cumplió los umbrales.

## Primera consulta como fuente de trazabilidad

Cada `run_items.query_id` guarda la **primera** consulta (dentro de esa corrida) que descubrió el `item_id`. Cuando el mismo ID aparece en una consulta posterior:

- **no** se reasigna el `query_id`;
- **no** se crea otra fila en `run_items`;
- se contabiliza como duplicado en `duplicate_ids_across_queries`.

De manera análoga, `run_items.position` proviene del orden global de descubrimiento (empezando en 1), **no** de la posición dentro del batch de multiget (que ordena alfabéticamente sólo para agrupar de forma determinista).

Motivación:

- Permite reconstruir, para cada publicación, en qué segmento (barrio, precio, dormitorios) fue encontrada por primera vez. Es información imprescindible para diagnosticar la cobertura del plan.
- Sin esta trazabilidad, dos plans distintos pueden producir el mismo inventario final sin que se pueda auditar cuál segmento aportó qué.
- Deja `run_items.query_id` **no nulo** para todo ítem descargado correctamente, lo que simplifica los joins de análisis.
