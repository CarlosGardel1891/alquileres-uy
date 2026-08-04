# Contrato observado de MercadoLibre Uruguay

Este documento registra el contrato **observado** de la API pública de MercadoLibre (`https://api.mercadolibre.com`) para el sitio Uruguay (`MLU`), en el contexto de publicaciones de alquiler mensual en Montevideo.

Distingue explícitamente entre:

- **comportamiento observado:** medido en respuestas reales;
- **supuestos:** conclusiones tentativas que aún no fueron validadas;
- **información oficial:** documentación pública citada;
- **decisiones propias:** elecciones del proyecto sobre cómo consumir la fuente.

> **Estado:** source gate ejecutado el 2026-08-04. Decisión **INCONCLUSIVE**. La API responde `403` a todos los endpoints del sitio `MLU` sin token. La fase queda **detenida** hasta obtener credenciales autorizadas o una decisión de fallback.

## 1. Fecha de la prueba

- 2026-08-04, aprox. 17:04 UTC.
- Evidencia local: `data/raw/mercadolibre/source_gate/2026-08-04T170426Z_a9c546bd/`
  - `coverage.json` — reporte estructurado del gate.
  - `exploration.json` — sondeo adicional a endpoints complementarios.

## 2. Endpoints probados

| Endpoint | Rol | Resultado observado (sin token) |
| --- | --- | --- |
| `GET /sites/MLU/search?q=alquiler&limit=1` | Búsqueda paginada. | `403 forbidden` — `{"message":"forbidden","error":"forbidden","status":403}` |
| `GET /sites/MLU/search?limit=1` | Búsqueda sin filtro `q`. | `403 forbidden` (idéntico). |
| `GET /sites/MLU` | Metadata del sitio. | `403 PA_UNAUTHORIZED_RESULT_FROM_POLICIES` — `blocked_by: PolicyAgent`. |
| `GET /sites/MLU/categories` | Árbol de categorías del sitio. | `403 PA_UNAUTHORIZED_RESULT_FROM_POLICIES` — `blocked_by: PolicyAgent`. |
| `GET /categories/MLU1466` | Metadata puntual de una categoría. | **`200 OK`** — se obtiene `{"id":"MLU1466","name":"Casas","total_items_in_this_category":41745,...}`. |
| `GET /items` (multiget) | Detalle de ítems. | **No probado** — el gate no llegó a esta llamada por falta de IDs. |
| `GET /items/{id}/description` | Descripción larga. | **No probado** — mismo motivo. |
| `GET /categories/{cat}/attributes` | Contrato de atributos. | **No probado** — mismo motivo. |

## 3. Resultado con y sin autenticación

- **Sin token (observado):** todos los endpoints bajo `/sites/MLU/*` devuelven `403`. El aviso `blocked_by: PolicyAgent` con código `PA_UNAUTHORIZED_RESULT_FROM_POLICIES` indica que MercadoLibre aplica una política de bloqueo del lado del servidor sobre esos recursos, incluso para consumo aparentemente "público".
- **Con token (`MELI_ACCESS_TOKEN`):** **no probado**. La variable de entorno no está seteada y el proyecto no crea credenciales por medios no autorizados.

**Decisión propia:** el diseño del gate reintenta con token si la búsqueda anónima devuelve `401` o `403`. Sin token, el gate devuelve `INCONCLUSIVE` (no `REJECTED`), porque el bloqueo por política no descarta la fuente en sí — sólo confirma que no se puede consumir anónimamente.

## 4. Categorías observadas

- **Observado:** `MLU1466` existe y es la categoría **"Casas"** (no "Apartamentos" como asumía inicialmente el seed plan). `total_items_in_this_category = 41745` a la fecha del sondeo.
- **No conocido:** el ID validado de "Apartamentos". `/sites/MLU/categories` (que lista todo el árbol del sitio) responde `403` sin token, por lo que no puede consultarse anónimamente.
- **Decisión propia:** el código **ya no** contiene constantes hardcodeadas de categorías. `query_plan.build_initial_plan` exige un `ApprovedSourceContract.category_ids` verificado por el propio gate contra `/sites/MLU/categories`. Sin ese mapping validado no hay approval, y sin approval no hay ingesta.

## 5. Filtros disponibles

- **Observado:** no se pudieron leer `available_filters` porque `/sites/MLU/search` respondió `403` antes de devolver cuerpo con paginación y filtros.
- **Información oficial:** `available_filters` incluye típicamente `OPERATION`, `PROPERTY_TYPE`, `BEDROOMS` y `price`.

## 6. Atributos estructurados

- **Observado:** no medidos. Requiere acceso al multiget o a `/categories/{id}/attributes`.
- **Información oficial:** los IDs de atributo pueden variar por categoría; el proyecto documentará los valores efectivos una vez pueda consumirlos.

## 7. Cobertura de campos (sample = 20)

- **Observado:** `sample_size = 0`. El gate no obtuvo ningún ítem para medir cobertura.
- **Umbral requerido:** 16 de 20 por cada campo esencial (`price`, `currency`, `location`, `property_type`, `operation`, `bedrooms`, `surface`) y 16 de 20 con `date_created` válida.

## 8. Límite de paginación observado

- **Oficial:** `limit ≤ 100`, `offset + limit ≤ 1000` en la búsqueda pública.
- **Observado:** no se pudo verificar por el bloqueo `403`.

## 9. Respuestas de error observadas

- **`403 forbidden`** en toda la ruta `/sites/MLU/*` sin token, con dos formas de cuerpo:
  - Simple: `{"message":"forbidden","error":"forbidden","status":403,"cause":[]}`.
  - Enriquecida: `{"code":"PA_UNAUTHORIZED_RESULT_FROM_POLICIES","status":403,"message":"At least one policy returned UNAUTHORIZED.","blocked_by":"PolicyAgent"}`.
- **`200 OK`** en `/categories/{id}` sin token, confirmando que sólo los recursos del sitio están cerrados.
- **`429`, `500`, `502`, `503`, `504`, `400`, `404`:** no observados en esta corrida.

## 10. Acceso a descripciones

- **No probado**. Es plausible que `/items/{id}/description` sí sea consumible con token, pero requiere primero obtener IDs válidos.

## 11. Decisión final del source gate

**`INCONCLUSIVE`** (exit code `3`).

Motivo: la búsqueda anónima devolvió `403` y no hay `MELI_ACCESS_TOKEN` para reintentar. No se puede afirmar ni negar que MercadoLibre cumpla el contrato mínimo; sólo se puede afirmar que no lo cumple **anónimamente**.

Consecuencias, siguiendo el "Camino bloqueado" del plan de la fase:

- **No** se implementó ni ejecutó la ingesta masiva.
- **No** se inició scraping de otra fuente (InfoCasas, Gallito).
- **No existe** un `source_gate_approval.json` — el pipeline de ingesta se niega a arrancar sin ese artefacto. La ingesta está bloqueada **por código**, no sólo por convención.
- Se detiene la fase.
- La rama `feat/002-mercadolibre-ingestion` queda como spike + documentación del bloqueo.
- Se solicita decisión del TL para abrir una fase de fallback (por ejemplo: obtener token oficial de MercadoLibre, o priorizar otra fuente).

## 12. Limitaciones conocidas

- `PolicyAgent` bloquea `/sites/MLU/*` sin token. Este es el bloqueo principal de esta fase.
- `offset + limit ≤ 1000` en la búsqueda pública — limitación estructural que motiva la segmentación por precio y dormitorios cuando el gate esté aprobado.
- `multiget` limitado a 20 ítems por llamada.
- Los IDs de atributo pueden variar por categoría; deben re-verificarse periódicamente cuando la fuente esté disponible.
- La API pública puede requerir token en el futuro; el proyecto ya está preparado para el flag `token_used = true` y para leer el token exclusivamente de `MELI_ACCESS_TOKEN`.

## Anexo — Reproducción del sondeo

Con el venv activo:

```bash
python scripts/run_source_gate.py
```

Para el sondeo complementario que documentó los distintos endpoints:

```python
python -c "
import requests
UA = {'User-Agent': 'alquileres-uy/0.1.0 (exploration)'}
for url in [
    'https://api.mercadolibre.com/sites/MLU',
    'https://api.mercadolibre.com/sites/MLU/search?q=alquiler&limit=1',
    'https://api.mercadolibre.com/sites/MLU/search?limit=1',
    'https://api.mercadolibre.com/sites/MLU/categories',
    'https://api.mercadolibre.com/categories/MLU1466',
]:
    r = requests.get(url, headers=UA, timeout=15)
    print(r.status_code, url, '->', r.text[:200])
"
```

---

**Nota:** este documento no incluye tokens, IDs sensibles, datos personales, respuestas completas ni miles de URLs. Los payloads observados quedan bajo `data/raw/mercadolibre/source_gate/` fuera del control de versión.
