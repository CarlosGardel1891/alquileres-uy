# Guión de la demo

Guía práctica para grabar un video demo de `alquileres-uy` que sirva
en portfolio o presentaciones. La idea es mostrar el pipeline
completo — ingesta → serving → UI → observabilidad — sin tocar
código en vivo.

## Duración sugerida

- **1 minuto** — micro-demo (home + un cálculo + estado del modelo).
- **3–5 minutos** — recorrido para portfolio (recomendado).
- **8–10 minutos** — deep-dive técnico (arquitectura + release
  engineering + observabilidad).

Grabá horizontal 1080p, 30 fps mínimo. Voz en off > cámara en
picture-in-picture.

## Preparación

Antes de grabar:

1. Levantá la API con un bundle listo:

   ```bash
   python scripts/_generate_model_fixture.py
   python scripts/train_models.py \
       --fixture-mode \
       --etl-run-dir tests/fixtures/models/etl_run \
       --output-dir artifacts/demo \
       --seed 42
   ALQUILERES_API_MODEL_BUNDLE_PATH=artifacts/demo/serving_bundle \
   ALQUILERES_API_ALLOW_FIXTURE_MODEL=true \
   python scripts/run_api.py
   ```

2. Abrí una segunda terminal con `curl` a mano para mostrar el
   contrato JSON de `/predict`.
3. En el navegador, dejá abiertas dos pestañas:
   - <http://127.0.0.1:8000/> (UI).
   - <http://127.0.0.1:8000/metrics> (Prometheus text).
4. Limpiá `localStorage` del navegador para arrancar con historial
   vacío.
5. Cerrá notificaciones del sistema.

## Guión sugerido (3–5 minutos)

### 1. Presentación (20 s)

- "Hola, soy [nombre]. Voy a mostrar `alquileres-uy`, un pipeline
  end-to-end que estima el precio de un alquiler en Montevideo."
- Mostrar el README brevemente en GitHub (badges + índice).

### 2. UI + primer cálculo (60 s)

- Abrir la home y leer el título + eyebrow.
- Click en **Cargar ejemplo** → mostrar cómo se completan los
  campos.
- Click en **Calcular precio** → esperar el spinner → resaltar el
  precio estimado + comparación con el precio publicado (semáforo
  🟢🟡🔴).
- Explicar en voz off: "el color depende de la diferencia porcentual
  con el precio publicado; si supera +10 % es rojo, entre -5 y +10 %
  es amarillo, si está por debajo de -5 % es verde."

### 3. Historial + accesibilidad (30 s)

- Cambiar algún valor (por ejemplo el barrio) y recalcular →
  aparece una segunda entrada en el historial lateral.
- Clic en la primera entrada → los valores del formulario se
  restauran.
- Mostrar el foco al tabular por el formulario (para hablar de
  accesibilidad: `:focus-visible`, `aria-live`).

### 4. Contratos HTTP (60 s)

- Volver a la terminal.

  ```bash
  curl -s http://127.0.0.1:8000/health | jq
  curl -s http://127.0.0.1:8000/ready  | jq
  curl -s http://127.0.0.1:8000/version | jq
  curl -s http://127.0.0.1:8000/build   | jq
  ```

- Mostrar el envelope de `/version` y de `/build` — remarcar que
  ambos vienen del bundle / de `build_info.json`.
- Correr un `POST /predict`:

  ```bash
  curl -s http://127.0.0.1:8000/predict \
    -H 'Content-Type: application/json' \
    -d '{"property_type":"apartment","price":950,"bedrooms":2,"bathrooms":1,
         "covered_area":58,"total_area":65,"latitude":-34.9067,
         "longitude":-56.1553,"neighborhood":"Pocitos"}' | jq
  ```

### 5. Observabilidad (30 s)

- Abrir la pestaña de `/metrics`, mostrar
  `prediction_requests_total` y `model_loaded`.
- Grep opcional en la consola donde corre uvicorn: la línea de log
  estructurado con `request_id`, `duration_ms`, `model_version`.

### 6. Cierre (20 s)

- Volver al README y mostrar el índice: `docs/architecture.md`,
  `docs/api.md`, `docs/portfolio.md`.
- CTA: "Si querés discutirlo, escribime — link al repositorio y a
  mi LinkedIn en la descripción."

## Guión para deep-dive (8–10 minutos)

Encima del recorrido anterior:

- **Arquitectura**: abrir `docs/architecture.md`, recorrer los
  diagramas Mermaid.
- **`PredictionService`**: mostrar `prediction_service.py` en el
  editor, resaltar semáforo + `asyncio.timeout` + drain.
- **CI**: mostrar la última corrida en GitHub Actions con los 4 jobs
  verdes.
- **Release engineering**: mostrar `_version.py`, `CHANGELOG.md` y
  cómo `scripts/release.py --help` avisa qué va a hacer.

## Qué no mostrar

- **No** mostrar datos reales de MercadoLibre — todo es fixture.
- **No** mostrar tokens, `.env`, ni credenciales. Si tenés
  `MELI_ACCESS_TOKEN` seteado, `unset`-lo antes de grabar.
- **No** grabar el shell con historial personal — usá una terminal
  limpia.

## Post-producción mínima

- Cortar silencios largos.
- Poner el título del proyecto los primeros 3 s.
- Subtítulos en español o inglés (dependiendo del target).
- Anexar el link del repositorio al final.

## Checklist de publicación

- [ ] Video subido a YouTube (no listado o público según preferencia).
- [ ] Enlace copiado al `README.md` (sección Capturas).
- [ ] Screenshot representativo en `docs/screenshots/` (referenciado
      desde el README).
- [ ] Post en LinkedIn / X con link al repositorio.
