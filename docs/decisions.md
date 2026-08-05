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

## Categorías obligatorias del contrato

El alcance de la ingesta está cerrado a **dos** categorías de MercadoLibre Uruguay: apartamentos y casas. El proyecto expone esa lista como una única constante compartida:

```python
REQUIRED_PROPERTY_TYPES = frozenset({"apartment", "house"})
```

y la usa en cuatro puntos:

1. `source_gate._decide` — sólo devuelve `APPROVED` cuando `verified_category_ids` cubre exactamente esas dos claves;
2. `approval.write_approval` — se niega a emitir `source_gate_approval.json` con una categoría faltante;
3. `approval.load_approved_contract` — al cargar el approval, exige `category_ids["apartment"]` y `category_ids["house"]` no vacíos e indica en el mensaje de error cuál falta;
4. `query_plan.build_initial_plan` — vuelve a validar la precondición porque nada garantiza que el contrato haya venido del loader (por ejemplo en tests).

Motivación:

- La ingesta con una sola categoría produciría un dataset sesgado y silenciosamente incorrecto (por ejemplo, todos "Casas" sin "Apartamentos").
- Las claves internas son `"apartment"` y `"house"` — nunca `"apartamento"`, `"casas"`, `"apartments"`, etc. Los nombres en español sólo se usan para hacer *matching* contra la metadata de MercadoLibre en `_verify_category_ids`.
- Que la validación viva en un único lugar (constante compartida) evita que las cuatro capas divergen.

## Evidencia de probes fallidos

Toda llamada de búsqueda del source gate genera un artefacto en disco, tanto en éxito (`200`) como en fallo (`401`, `403`, timeout, etc.). El formato uniforme es:

```json
{
  "request": {
    "method": "GET",
    "endpoint": "/sites/MLU/search",
    "authenticated": false
  },
  "response": {
    "status_code": 403,
    "body": {
      "message": "forbidden",
      "error": "forbidden",
      "status": 403
    }
  }
}
```

Para errores de red sin respuesta HTTP, `status_code` es `null` y se agregan `error_type` y `message`.

Los archivos son:

- `search_no_auth.json` — siempre.
- `search_with_auth.json` — sólo si el pipeline **decidió** ejecutar la llamada autenticada (o sea: el anónimo devolvió `401`/`403` **y** hay `authenticated_client`).

Motivación:

- El caso más importante para auditar la fuente es cuando falla. Perder el body del `403` obligaba a re-consultar manualmente MercadoLibre para reconstruir la evidencia.
- El wrapper `{request, response}` deja explícito qué se pidió y qué respondió, y separa metadatos del request (`authenticated`) del body real, evitando ambigüedad cuando el body está vacío o es un error.
- Todos los artefactos pasan por `sanitize_for_artifact`, que redacta claves sensibles (`authorization`, `access_token`, `token`, `cookie`, `x-auth-token`, case-insensitive) y — si se conoce el token literal — lo reemplaza en cualquier string, URL o mensaje anidado.

## Semántica de `token_used`

`token_used` responde a "¿se envió un bearer token en al menos una llamada?", no a "¿la llamada autenticada fue exitosa?". Se marca `true` en el momento en que el pipeline decide ejecutar `authenticated_client.search_items(...)`, antes del `try`, así:

- si el anónimo devolvió `200` y no se llegó a llamar al autenticado, `token_used = false` (incluso con `MELI_ACCESS_TOKEN` seteado);
- si el anónimo devolvió `401`/`403` y el autenticado también, `token_used = true`;
- si el autenticado terminó en timeout, `token_used = true`;
- si no hay `authenticated_client`, `token_used = false`.

Motivación:

- Un `token_used = false` cuando el token se envió y falló era engañoso: sugería que el proyecto ni siquiera intentó autenticarse.
- Con la semántica correcta, el reporte y el `coverage.json` reflejan fielmente el comportamiento del pipeline y permiten diagnosticar "¿la API rechazó al token?" vs "¿no había token disponible?".

## Resolución jerárquica de categorías

`/sites/{site_id}/categories` sólo devuelve los nodos raíz del árbol de categorías de MercadoLibre. Los tipos que el proyecto necesita (`Apartamentos`, `Casas`) pueden estar varios niveles por debajo, típicamente dentro de un nodo intermedio como `Inmuebles`. El source gate resuelve esto con un recorrido iterativo BFS (`src/alquileres_uy/ingest/category_tree.py`):

- Empieza en la respuesta del endpoint del sitio, encola cada nodo raíz.
- Para cada nodo desencolado, consulta `/categories/{id}` para leer sus `children_categories` y los encola.
- Mantiene un `visited: set[str]` para evitar ciclos y llamadas duplicadas.
- Aplica dos límites defensivos (`MAX_CATEGORY_DEPTH=10`, `MAX_CATEGORY_NODES=1000`). Si se supera cualquiera, marca `limits_exceeded=True`, agrega una nota al reporte, no aprueba y no emite approval.
- Compara nombres mediante `normalize_category_name` (NFKD + strip + lower + colapso de espacios) contra un alias set fijo — nunca por substring.

Cuando aparecen dos nodos con el mismo alias para un tipo (por ejemplo dos categorías cuyo nombre normalizado es `apartamentos`), el resolver **no elige silenciosamente uno**: registra todas las candidatas en `candidates[apartment]`, marca `apartment` como ambiguous y fuerza `INCONCLUSIVE`. La ambigüedad es un problema del contrato, no del código.

Motivación:

- Consumir sólo el nivel raíz era el bug histórico que hacía que el gate perdiera categorías aunque el token funcionara.
- Un match por substring convertiría un nodo llamado "Propiedades y Apartamentos" en un candidato falso, contaminando el plan.
- Un límite defensivo evita que una API malformada o un ciclo produzcan un loop infinito.

## Cobertura combinada del target

La decisión del gate exige que al menos **16 de 20** publicaciones de la muestra cumplan **simultáneamente**:

- operación clasificada como *alquiler mensual* (por `OPERATION.value_name` o `value_id`, nunca inferida del título);
- tipo de propiedad *apartment* o *house* (por `category_id` verificada, o atributo `PROPERTY_TYPE`; si ambas fuentes se contradicen → `property_type_conflict` → inválido);
- ubicación normalizada dentro de Montevideo (por `location.state.name`).

Motivación:

- Medir "presencia del campo" ya no es suficiente — un ítem puede tener `OPERATION=Venta` con el campo presente y aún así estar fuera del alcance.
- Métricas separadas (20 alquileres, 20 casas, 20 en Montevideo) pueden ocultar que ningún ítem cumple los tres criterios a la vez. Sólo el **target combinado** protege contra ese sesgo.
- Distingue calidad (`REJECTED` si el target < 16 con datos accesibles) de acceso (`INCONCLUSIVE` si no se pudieron obtener datos estructurados).

## Coverage como fuente de verdad del approval

El `source_gate_approval.json` funciona como un puntero + comprobante:

- **puntero:** contiene el nombre del `coverage.json` acompañante.
- **hash de integridad:** el SHA-256 del `coverage.json` está guardado en el approval; el loader recalcula el hash del archivo en disco y rechaza cualquier discrepancia.
- **copia redundante verificable:** `category_ids`, `available_filters`, `operation_filter.mode` y `sample_size` están duplicados en el approval sólo para que el loader pueda **compararlos** con los valores dentro de `coverage.json`.

El loader:

1. valida forma básica del approval (source, site_id, decision, categorías exactamente `{apartment, house}`);
2. resuelve `source_gate_report_path` con defensa contra path traversal (`..`, rutas absolutas o resolución fuera del directorio → `SourceGateApprovalIntegrityError`);
3. recalcula el SHA-256 del archivo referenciado y lo compara con el hash guardado;
4. reléé el `coverage.json`, valida que tenga `decision=APPROVED` y que sus valores semánticos coincidan **exactamente** con los del approval;
5. re-valida los umbrales (sample_size=20; cada campo esencial ≥16/20; date_created ≥16/20; target combinado ≥16/20);
6. construye `ApprovedSourceContract` usando los valores del `coverage.json` — el approval no puede introducir un contrato distinto.

Motivación:

- Sin comparación semántica, un atacante podía dejar `coverage.json` intacto (para preservar el hash) y modificar sólo `category_ids` en el approval para inyectar categorías arbitrarias en el plan de ingesta.
- Path traversal en `source_gate_report_path` permitía referenciar `/etc/passwd` o un `coverage.json` favorable ubicado fuera del run folder.
- Construir el contrato desde el coverage (no desde el approval) hace irrelevante cualquier discrepancia futura que el loader olvide comparar.

## ETL contract-first mientras la fuente esté bloqueada

El source gate real todavía devuelve `INCONCLUSIVE` sin token oficial, así que no existe una corrida real de ingesta. En vez de esperar, la Fase 2 construye el ETL completo contra fixtures sanitizadas (`tests/fixtures/etl/raw_run/`). Todos los outputs de fixtures llevan `data_mode="fixture"` y el `data_quality_report.json` incluye un `warning` explícito. Ninguna métrica de fixture puede reportarse como resultado del proyecto.

El pipeline se declara en dos estados discretos: `ETL_CONTRACT_READY` (código, tests y CI verdes, sin datos reales) y `ETL_PRODUCTION_VALIDATED` (corrida real con approval válido). Sólo el segundo autoriza la Fase 3 de entrenamiento.

## Cotización fija por corrida

La conversión de UYU→USD nunca consulta una API en runtime. Cada corrida recibe un `--exchange-rate PATH` a un JSON versionado con `base_currency`, `quote_currency`, `uyu_per_usd`, `effective_date`, `source`, `retrieved_at`, `data_mode`. El `lineage.json` de la corrida registra la ruta y el SHA-256 del archivo, así que dos corridas con tasas distintas son distinguibles bit a bit.

Motivación: reproducibilidad y auditoría. Una cotización que cambia en tiempo real vuelve imposible replicar un dataset. Mantenerla explícita también permite comparar el efecto de una tasa vs. otra sin re-ingestar.

## Canonical vs. model-ready

`listings.parquet` (canonical) es el **inventario auditado** y admite campos opcionales faltantes (por ejemplo, `neighborhood_normalized` o `date_created` pueden ser null). `model_ready.parquet` es el **subset apto para entrenamiento** y exige `source_item_id`, `property_type`, `neighborhood_normalized`, `bedrooms`, `total_area_m2`, `price_usd`, `date_created` no nulos, superficie positiva y sin conflictos entre `total_area_m2` y `covered_area_m2`.

Motivación: rechazar cada fila con un opcional faltante perdería trazabilidad. Aceptarlas en el canónico y filtrarlas en el model-ready deja auditables tanto los datos ingeridos como los datos usables para modelar.

## Duplicados conservadores

- **Mismo `source_item_id`**: deduplicado a una sola fila con la observación más nueva (`last_updated` → `last_seen_at` → `raw_item_path`), pero `first_seen_at` y `observations_count` se preservan.
- **Mismo contenido, IDs distintos**: se etiqueta con `exact_content_hash` — **nada se elimina**.
- **Posibles duplicados entre inmobiliarias**: clave bucketed conservadora `(property_type, neighborhood_normalized, bedrooms, total_area_m2 // 5 m², price_usd // 50 USD)` que emite `possible_duplicate_group_id` y una fila por candidato en `duplicate_candidates.parquet`. Nunca se elimina del canonical.

Motivación: en esta fase no hay evidencia de matching semántico confiable ni fuzzy matching probado. Eliminar automáticamente introduce falsos positivos silenciosos. La política es "marcar y auditar".

## Prevención de leakage

`model_ready.parquet` está cerrado a cualquier columna derivada del target `price_usd`: `price_per_m2`, `price_bucket`, `total_monthly_cost_usd` (que sí existe en el canonical, como campo informativo). La función `check_model_ready_leakage` corre antes de escribir el Parquet y termina la corrida con exit `1` si alguna forbidden column aparece.

Motivación: `price_per_m2` es análisis útil (aparece en el `data_quality_report.json`), pero como feature de entrenamiento filtra el target y produce métricas de validación infladas. La regla es más simple de mantener que auditar cada feature manualmente.

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


## Fase 3 — Entrenamiento de modelos

Estas decisiones enmarcan el pipeline de entrenamiento (`src/alquileres_uy/models/`).

### Ridge como modelo lineal

El "modelo lineal interpretable" del proyecto es Ridge (`sklearn.linear_model.Ridge`) con grid `alpha ∈ {0.1, 1.0, 10.0}` seleccionado por MAE de validation. Regresión sin regularización es inestable ante one-hot encoding con barrios raros; Ridge da coeficientes acotados sin destruir la interpretabilidad.

### Split temporal (sin shuffle)

Se usa un split temporal agrupado por `date_created` (`temporal-grouped-v1`). No se usa `train_test_split` ni ningún split aleatorio: el sistema debe entrenar con el pasado y validarse con el futuro, y filas con el mismo timestamp nunca cruzan splits. Un split que no cumpla las invariantes falla explícitamente; no hay degradación silenciosa.

### PyTorch en CPU y separado del serving

PyTorch participa en la comparación de métricas pero **no** entra al `serving_bundle/`. Motivo: el bundle futuro de FastAPI (Fase 4) no llevará runtime de Torch — pesa demás y el modelo tabular no gana lo suficiente sobre LightGBM en el fixture actual para justificarlo. `requirements-torch-cpu.txt` se instala solo cuando se pide `--include-torch`; la falta de la wheel devuelve exit 2 con mensaje claro.

### LightGBM como candidato esperado, no garantizado

LightGBM suele quedar por encima del baseline y del linear en el fixture, pero el pipeline no lo asume: el `serving_candidate` se elige por validation MAE (con preferencia por el modelo más simple ante empate práctico dentro de `SERVING_TIE_TOLERANCE = 5 USD`). Cualquiera de baseline/linear/lightgbm puede ganar según la corrida.

### Best-overall vs. serving-candidate

Se separan dos decisiones:

- `best_overall_model` puede ser cualquiera de los cuatro (baseline / linear / lightgbm / torch).
- `serving_candidate` solo puede ser clásico. Esto deja constancia de que Torch puede ganar en métricas sin obligar a servirlo, y evita mezclar "el mejor modelo" con "el modelo que se despliega".

### Intervalo de predicción empírico (no CI estadístico)

La API futura devolverá `[lower, upper]` alrededor de la predicción. Se calcula sobre los residuos de validation del `serving_candidate` (q10/q90). Es explícitamente etiquetado como `empirical residual interval` — no se afirma que sea un intervalo de confianza estadístico formal.

### Sin MLflow ni Optuna

Alcance conscientemente reducido: grids pequeños y fijos, resultados serializados como JSON/Parquet. MLflow y Optuna aportan valor cuando hay decenas de experimentos concurrentes; con cuatro familias y un puñado de hiperparámetros el overhead operativo no se justifica todavía.

### PyTorch fuera de la API

El serving bundle refuerza la exclusión: `build_serving_bundle` levanta `ServingBundleError` si se le pide empaquetar Torch; `metadata.json` deja constancia con `eligible_for_api_serving=false` en el side-car del modelo Torch.

### Correcciones review Fase 3 (tune-then-refit-v2)

El protocolo original re-entrenaba Ridge y LightGBM con `train + validation` y luego calculaba validation metrics con ese modelo — fuga silenciosa. La revisión introdujo:

- separación explícita entre `tune_*` (train-only) y `refit_*` (`train + validation`);
- validation metrics y residual interval calculados con el tuning model;
- test metrics calculadas una única vez con el final model;
- selección anclada al menor MAE elegible (no encadenada);
- `training_run_id` distinto de `etl_run_id`;
- `training_config.json` hasheado dentro del lineage;
- `load_serving_bundle` ejecuta `validate_runtime_compatibility` **antes** de `joblib.load` (tests con `joblib.load` monkey-patched aseguran call-count 0);
- `source_item_id` exige instancia de `str`; barrio no vacío; bedrooms finito; bathrooms opcional en Parquet con imputación por mediana (ni el DataFrame ni el Parquet se modifican);
- `residual = actual - predicted` en `predictions.parquet` (incluye train / validation / test con columna `model_stage`);
- worst_errors del serving candidate en test/final_refit.

Motivación: las métricas fixture anteriores eran inválidas (LightGBM caía de 38.78 → 80.23 en validation al eliminar el leak). El pipeline honesto no admite atajos.


## Correcciones finales del review Fase 3

Cambios mínimos aplicados sobre `tune-then-refit-v2`:

- **Cobertura exacta del serving bundle**: `REQUIRED_BUNDLE_PAYLOAD_FILES` y `REQUIRED_BUNDLE_FILES` son la única fuente. `checksums.json` debe declarar los cuatro payloads exactamente; el directorio debe contener sólo los cinco archivos. Subdirs, symlinks y extras se rechazan antes de leer metadata. `build_serving_bundle` construye `checksums.json` desde la constante — no enumera el directorio.
- **Consistencia `data_mode` / `deployable`**: `deployable` debe ser bool real (no `0`, `1`, `"true"`, null) y estrictamente igual a `data_mode == "real"`. Incoherencias (`fixture + true`, `real + false`) se rechazan.
- **Bathrooms opcional con fallback 0.0**: helper `resolve_numeric_imputation_values` compartido entre clásico y PyTorch. Mediana cuando hay observaciones; `0.0` cuando el fit frame no tiene ninguna. Clásico usa `SimpleImputer(keep_empty_features=True)`. Torch registra `imputation_sources` en `vocabularies.json` / `numeric_scaler.json`.
- **Test perturbation con Torch**: nuevo test marcado `@pytest.mark.torch` que usa los IDs reales de test extraídos del `predictions.parquet` (no un índice aproximado). Verifica que validation MAE, best_epoch, hiperparámetros, selection y residual interval permanecen idénticos.
- **Real-mode ephemeral test**: `test_real_mode_lineage_contains_exact_approval_hash` promueve la fixture a real bajo `tmp_path`, genera un approval sintético con hashes reales, corre el pipeline y verifica que `inputs_sha256["etl_approval"]` coincide con `sha256(approval_path.read_bytes())`. Nunca versiona un approval real.
- **Runtime mismatches**: cobertura parametrizada de NumPy, pandas, scikit-learn y joblib más dos casos específicos para LightGBM (versión ausente y runtime ausente). Todos monkeypatchean `joblib.load` y assertean call-count 0.
