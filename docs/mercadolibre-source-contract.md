# Contrato observado de MercadoLibre Uruguay

Este documento registra el contrato **observado** de la API pública de MercadoLibre (`https://api.mercadolibre.com`) para el sitio Uruguay (`MLU`), en el contexto de publicaciones de alquiler mensual en Montevideo.

Distingue explícitamente entre:

- **comportamiento observado:** medido en respuestas reales;
- **supuestos:** conclusiones tentativas que aún no fueron validadas;
- **información oficial:** documentación pública citada;
- **decisiones propias:** elecciones del proyecto sobre cómo consumir la fuente.

> Estado del documento: **pendiente de ejecución real del source gate**. Los campos marcados con `<pendiente>` se completan tras correr `python scripts/run_source_gate.py`.

## 1. Fecha de la prueba

`<pendiente>` (formato ISO-8601 UTC).

## 2. Endpoints probados

| Endpoint | Rol |
| --- | --- |
| `GET /sites/{site_id}/search` | Búsqueda paginada de publicaciones. |
| `GET /items` (multiget con `ids=`) | Detalle de hasta 20 ítems por llamada. |
| `GET /items/{item_id}/description` | Descripción larga del ítem. |
| `GET /categories/{category_id}` | Metadata de categoría. |
| `GET /categories/{category_id}/attributes` | Contrato de atributos estructurados. |

## 3. Resultado con y sin autenticación

- **Sin token:** `<pendiente>` (código de estado, si devuelve resultados válidos).
- **Con token (`MELI_ACCESS_TOKEN`):** sólo se prueba si la búsqueda anónima devuelve `401` o `403`. `<pendiente>`.

**Decisión propia:** no crear aplicaciones ni obtener credenciales por medios no autorizados. Si la búsqueda anónima cubre el contrato mínimo, la ingesta se ejecuta sin token.

## 4. Categorías observadas

Categorías esperadas (a confirmar por el gate):

- `MLU1466` — Apartamentos.
- `MLU1472` — Casas.

Observado: `<pendiente>` (lista real).

## 5. Filtros disponibles

Se leen desde `available_filters` en la respuesta de búsqueda.

Observados: `<pendiente>`. Se espera al menos:

- `OPERATION` (Alquiler vs. Venta vs. Alquiler temporal).
- `PROPERTY_TYPE`.
- `BEDROOMS`.
- filtro estructurado de precio (`price`).

## 6. Atributos estructurados

Se consultan mediante `/categories/{category_id}/attributes` y se comparan con los presentes en cada ítem.

Observados: `<pendiente>`. Se espera al menos: `OPERATION`, `PROPERTY_TYPE`, `BEDROOMS`, `TOTAL_AREA`, `COVERED_AREA`, `FULL_BATHROOMS`, `EXPENSES`, `FLOOR`, `FURNISHED`.

## 7. Cobertura de campos (sample = 20)

Se mide sobre el batch de 20 ítems devuelto por el multiget. Umbral mínimo: **16 de 20** para cada campo esencial.

| Campo | Presentes | Umbral | Estado |
| --- | --- | --- | --- |
| price | `<pendiente>` | 16 | `<pendiente>` |
| currency | `<pendiente>` | 16 | `<pendiente>` |
| location | `<pendiente>` | 16 | `<pendiente>` |
| property_type | `<pendiente>` | 16 | `<pendiente>` |
| operation | `<pendiente>` | 16 | `<pendiente>` |
| bedrooms | `<pendiente>` | 16 | `<pendiente>` |
| surface | `<pendiente>` | 16 | `<pendiente>` |
| date_created (válida) | `<pendiente>` | 16 | `<pendiente>` |

Campos adicionales medidos sin usarlos como gate: `bathrooms`, `expenses`, `floor`, `furnished`, `description`, `permalink`, `last_updated`.

## 8. Límite de paginación observado

- **Oficial:** cada página acepta `limit` de hasta 100 resultados.
- **Oficial:** la combinación `offset + limit` no debe exceder 1.000 en la búsqueda pública.
- Observado: `<pendiente>` (por ejemplo, cómo responde la API si se piden `offset=1000`).

## 9. Respuestas de error observadas

| Código | Comportamiento | Manejo del cliente |
| --- | --- | --- |
| `429` | Rate limit. Retorna `Retry-After` cuando corresponde. | Reintento con backoff exponencial + jitter; respeta `Retry-After`. |
| `500`/`502`/`503`/`504` | Errores upstream transitorios. | Reintento con backoff. |
| `400` | Parámetros inválidos. | **No** se reintenta; se registra en `request_errors`. |
| `401`/`403` | Autenticación/autorización. | **No** se reintenta automáticamente; el source gate decide si reintentar con token. |
| `404` | Ítem inexistente. | Descarta la operación puntual; no aborta la corrida. |

Observado en la corrida del gate: `<pendiente>`.

## 10. Acceso a descripciones

Endpoint independiente: `GET /items/{item_id}/description`. No viene incluido en la respuesta de `/items`.

Cobertura observada en la muestra: `<pendiente>%`. La descripción **no** bloquea la aprobación del source gate; ausencia de descripción se registra pero se continúa.

## 11. Decisión final del source gate

`<pendiente>` — uno de `APPROVED`, `REJECTED`, `INCONCLUSIVE`.

- **APPROVED:** habilita la ingesta masiva controlada por segmentación.
- **REJECTED:** se detiene la fase y se entrega la evidencia al TL.
- **INCONCLUSIVE:** se detiene la fase; puede requerir credenciales o revisión del alcance.

## 12. Limitaciones conocidas

- `offset + limit ≤ 1000` en búsqueda pública; requiere segmentación por precio y dormitorios.
- `multiget` limitado a 20 ítems por llamada.
- Cambios de contrato: los IDs de atributo pueden variar por categoría; deben re-verificarse periódicamente.
- La API pública puede requerir token en el futuro; el proyecto debe estar preparado para el flag `token_used = true`.
- Rate limiting: el proyecto usa por defecto 2 requests/segundo con backoff; no intenta evadir bloqueos.

---

**Nota:** este documento no incluye tokens, IDs sensibles, datos personales, respuestas completas ni miles de URLs. Los payloads observados quedan en `data/raw/mercadolibre/source_gate/` fuera del control de versión.
