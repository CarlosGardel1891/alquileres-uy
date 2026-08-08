# Contribuir a `alquileres-uy`

Gracias por tu interés en el proyecto. Este documento describe el
workflow que usamos internamente: cómo levantar el proyecto, cómo
nombrar ramas, cómo escribir commits y qué esperar de los tests /
del estilo.

## Levantar el proyecto

Requisitos: Python 3.12, Git, un venv local.

```bash
git clone https://github.com/CarlosGardel1891/alquileres-uy.git
cd alquileres-uy
python -m venv .venv
source .venv/bin/activate           # Linux / macOS
# .\.venv\Scripts\Activate.ps1      # Windows PowerShell

python -m pip install --upgrade pip
pip install -r requirements-dev.txt
pip install -e .
pre-commit install
```

Para trabajar en la API + UI también necesitás:

```bash
pip install -r requirements-api.txt -r requirements-train.txt
python scripts/_generate_model_fixture.py
```

Para correr los tests que pisan PyTorch:

```bash
pip install -r requirements-torch-cpu.txt
```

## Ramas

Cada cambio vive en su propia rama, nombrada según el patrón:

```
feat/<NNN>-<slug>       # nueva funcionalidad
fix/<slug>              # bug fix
docs/<slug>             # cambios sólo de documentación
chore/<slug>            # tooling, config, deps
refactor/<slug>         # refactor sin cambio funcional
```

`NNN` es la fase en curso (`014`, `015`, …). El `slug` va en
kebab-case: `feat/015-neighborhood-aliases`.

Nunca commitear directo a `main`. Todo cambio se hace vía PR.

## Commits

Convención: **subject imperativo corto** (< 72 chars), cuerpo
opcional pero recomendado si el cambio no es evidente.

```
tipo(scope): resumen imperativo

Cuerpo explicando el porqué. Referencias a issues / PRs cuando
correspondan.
```

Tipos habituales:

- `feat` — nueva funcionalidad.
- `fix` — corrección de bug.
- `refactor` — refactor sin cambio funcional.
- `docs` — solo documentación.
- `test` — solo tests.
- `chore` — build system, deps, tooling.
- `ci` — cambios en GitHub Actions.

Un ejemplo real del histórico:

```
feat(web-ui): polish state, comparison, a11y, microcopy, animations

Fase 13 refines the UI without adding endpoints or backend changes...
```

## Pull requests

- Abrir la PR **como Draft** hasta que el ciclo verde de CI esté
  completo.
- El título del PR sigue el mismo formato del commit subject.
- El cuerpo debe listar: alcance, archivos tocados, tests nuevos,
  resultado de las validaciones locales, y una sección
  **Desviaciones respecto del prompt** si aplica.
- **No mergear vos**. El Technical Lead revisa y decide cuando
  pasar a "Ready for review" y mergear.

Antes de marcar Ready, ejecutá:

```bash
ruff check .
ruff format --check .
pytest -q -m "not torch"
pre-commit run --all-files
python -m build
```

CI corre exactamente lo mismo — si pasa local, pasa en la nube.

## Tests

- Framework: `pytest`.
- Ubicación: `tests/` — mismo nombre que el módulo bajo test
  (`tests/api/test_reliability.py` → `src/alquileres_uy/api/*`).
- Marker `torch` para los tests que requieren PyTorch instalado —
  se ejecutan en el job `PyTorch CPU`.
- **Sin `httpx`, sin `fastapi.testclient.TestClient`, sin
  Selenium/Playwright/Cypress**. La suite de API usa un harness
  ASGI custom (ver `tests/api/test_reliability.py`).
- Cada PR debería agregar tests que fallen antes del cambio y pasen
  después. No hay excepciones de "cambio trivial".

Ejecutar tests de un solo archivo mientras iterás:

```bash
pytest tests/api/test_web_ui_polish.py -q
```

## Estilo

- **Formato**: `ruff format` (basado en Black). Pre-commit lo aplica
  automáticamente.
- **Lint**: `ruff check` con reglas E, F, I, B, UP, SIM, RUF. Fixes
  automáticos con `ruff check --fix`.
- **Type hints**: recomendados en toda función pública. `from
  __future__ import annotations` en la mayoría de módulos.
- **Docstrings**: siempre en funciones públicas. Estilo NumPy-lite:
  descripción corta + secciones opcionales.
- **Naming**: `snake_case` para variables y funciones; `PascalCase`
  para clases; constantes en `SCREAMING_SNAKE_CASE`.
- **Comentarios**: sólo cuando el porqué no es obvio. No repetir el
  qué (el código ya lo dice).

## Documentación

- Todo cambio en la API pública debe actualizar `docs/api.md`.
- Todo cambio en env vars debe actualizar `docs/deployment.md` y la
  tabla del `README.md`.
- Cambios en la UI pueden requerir actualizar `docs/demo.md`.
- **Toda entrega** actualiza `CHANGELOG.md` bajo `[Unreleased]`.

## Reportar bugs

Abrí un issue con:

- Versión (`GET /build` o `alquileres_uy.__version__`).
- Reproducción mínima (curl, payload, comandos).
- Comportamiento esperado vs. observado.
- Logs relevantes (redactar tokens / IDs sensibles).

## Código de conducta

Sé respetuoso. Trabajá en cambios pequeños y verificables. No
introduzcas secretos en commits ni en PRs.

## Licencia

Contribuir implica que aceptás publicar tu contribución bajo la
misma licencia del proyecto (MIT, ver `LICENSE`).
