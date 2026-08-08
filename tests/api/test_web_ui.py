"""Fase 11 web UI tests.

Constraints (same as previous phases):

* no httpx, no TestClient, no Selenium / Playwright / Cypress;
* a minimal ASGI harness drives the app end-to-end for HTTP checks;
* asset content (CSS/JS/HTML/SVG) is asserted on disk so the tests
  fail loudly if a required element is renamed or removed.

The tests cover the ten parts the prompt lists as validation targets:
Home, Formulario, /predict flow (via JS content assertions), /version
consumption, /health + /ready consumption, CSS, JS, Templates,
Responsive design, error handling.
"""

from __future__ import annotations

import asyncio
import re
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from fastapi import FastAPI

from alquileres_uy.api.app import create_app
from alquileres_uy.api.routes import web as web_module

ROOT = Path(__file__).resolve().parents[2]
TEMPLATES_DIR = web_module.TEMPLATES_DIR
STATIC_DIR = web_module.STATIC_DIR
INDEX_HTML = TEMPLATES_DIR / "index.html"
BASE_HTML = TEMPLATES_DIR / "base.html"
CSS_FILE = STATIC_DIR / "css" / "styles.css"
JS_FILE = STATIC_DIR / "js" / "app.js"
FAVICON = STATIC_DIR / "favicon.svg"


# ---- minimal ASGI harness ----------------------------------------


async def _asgi_call(
    app: FastAPI,
    method: str,
    path: str,
    *,
    headers: list[tuple[bytes, bytes]] | None = None,
    body: bytes = b"",
) -> dict:
    result: dict = {"headers": {}, "body": b""}
    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": headers or [],
        "server": ("testserver", 80),
        "client": ("testclient", 12345),
        "app": app,
    }
    sent = [False]

    async def _receive():
        if not sent[0]:
            sent[0] = True
            return {"type": "http.request", "body": body, "more_body": False}
        return {"type": "http.disconnect"}

    async def _send(message):
        if message["type"] == "http.response.start":
            result["status"] = message["status"]
            result["headers"] = {k.decode(): v.decode() for k, v in message.get("headers", [])}
        elif message["type"] == "http.response.body":
            result["body"] += message.get("body", b"")

    @asynccontextmanager
    async def _lifespan_ctx():
        async with app.router.lifespan_context(app):
            yield

    async with _lifespan_ctx():
        try:
            await app(scope, _receive, _send)
        except Exception:
            if "status" not in result:
                raise
    return result


# ---- Home route --------------------------------------------------


def test_home_returns_200_and_html(api_env):
    app = create_app()
    result = asyncio.run(_asgi_call(app, "GET", "/"))
    assert result["status"] == 200
    content_type = result["headers"].get("content-type", "")
    assert content_type.startswith("text/html")


def test_home_body_has_required_sections(api_env):
    app = create_app()
    result = asyncio.run(_asgi_call(app, "GET", "/"))
    body = result["body"].decode()
    # Title & description
    assert "alquileres-uy" in body
    assert "Estimador de alquileres" in body or "estimador" in body.lower()
    # CTA "Calcular precio" button
    assert "Calcular precio" in body
    # Model info container populated at runtime.
    assert 'id="model-info"' in body
    # API version rendered from server-side context.
    assert "API v" in body
    # Repo link
    assert "https://github.com/CarlosGardel1891/alquileres-uy" in body


def test_home_renders_all_form_fields(api_env):
    app = create_app()
    result = asyncio.run(_asgi_call(app, "GET", "/"))
    body = result["body"].decode()
    for field_id in (
        "neighborhood",
        "property_type",
        "bedrooms",
        "bathrooms",
        "total_area",
        "covered_area",
        "latitude",
        "longitude",
        "price",
    ):
        assert f'id="{field_id}"' in body, f"form missing field {field_id}"


def test_home_form_has_html_validation(api_env):
    """HTML-level validation must exist on every model-feature field."""
    body = INDEX_HTML.read_text(encoding="utf-8")
    # Every non-optional field has a `required` attribute.
    for field_id in (
        "neighborhood",
        "property_type",
        "bedrooms",
        "bathrooms",
        "total_area",
        "covered_area",
        "latitude",
        "longitude",
    ):
        pattern = rf'id="{re.escape(field_id)}"[^>]*required'
        assert re.search(pattern, body, flags=re.DOTALL), f"{field_id} missing required attribute"
    # Latitude / longitude get proper bounds.
    assert re.search(r'id="latitude"[^>]*min="-90"', body, flags=re.DOTALL)
    assert re.search(r'id="latitude"[^>]*max="90"', body, flags=re.DOTALL)
    assert re.search(r'id="longitude"[^>]*min="-180"', body, flags=re.DOTALL)
    assert re.search(r'id="longitude"[^>]*max="180"', body, flags=re.DOTALL)


def test_home_price_field_is_marked_optional_in_ui(api_env):
    body = INDEX_HTML.read_text(encoding="utf-8")
    # The price field label wears the (opcional …) tag.
    assert 'for="price"' in body
    assert "opcional" in body.lower()
    # And is NOT required at the HTML level.
    assert not re.search(r'id="price"[^>]*required', body, flags=re.DOTALL)


# ---- Templates + Jinja2 wiring ---------------------------------


def test_templates_directory_uses_jinja2():
    assert INDEX_HTML.is_file(), "index template missing"
    assert BASE_HTML.is_file(), "base template missing"
    body = INDEX_HTML.read_text(encoding="utf-8")
    # Uses Jinja inheritance / substitution.
    assert "{% extends" in body
    assert "{% block content %}" in body


def test_templates_do_not_pull_frontend_frameworks(api_env):
    app = create_app()
    body = (
        asyncio.run(_asgi_call(app, "GET", "/")).body
        if False
        else (asyncio.run(_asgi_call(app, "GET", "/"))["body"].decode())
    )
    for banned in (
        "cdn.tailwindcss.com",
        "bootstrap.min",
        "react.production",
        "react.development",
        "vue.global",
        "unpkg.com/@angular",
    ):
        assert banned not in body, f"UI must not pull {banned}"


def test_web_router_is_excluded_from_openapi_schema():
    from alquileres_uy.api.routes import web

    for route in web.router.routes:
        include_in_schema = getattr(route, "include_in_schema", True)
        assert include_in_schema is False


# ---- Static assets -----------------------------------------------


def test_css_asset_is_served(api_env):
    app = create_app()
    result = asyncio.run(_asgi_call(app, "GET", "/static/css/styles.css"))
    assert result["status"] == 200
    assert result["headers"].get("content-type", "").startswith("text/css")
    assert len(result["body"]) > 0


def test_js_asset_is_served(api_env):
    app = create_app()
    result = asyncio.run(_asgi_call(app, "GET", "/static/js/app.js"))
    assert result["status"] == 200
    ctype = result["headers"].get("content-type", "")
    assert "javascript" in ctype
    assert len(result["body"]) > 0


def test_favicon_is_served(api_env):
    app = create_app()
    result = asyncio.run(_asgi_call(app, "GET", "/static/favicon.svg"))
    assert result["status"] == 200
    assert "svg" in result["headers"].get("content-type", "")
    assert b"<svg" in result["body"]


def test_static_missing_asset_returns_404(api_env):
    app = create_app()
    result = asyncio.run(_asgi_call(app, "GET", "/static/does-not-exist.txt"))
    assert result["status"] == 404


# ---- CSS content (responsive + palette + shadows) ---------------


def test_css_uses_custom_palette_and_shadows():
    text = CSS_FILE.read_text(encoding="utf-8")
    # Custom vars — no Tailwind / Bootstrap references.
    assert ":root" in text
    assert "--color-primary" in text
    assert "box-shadow" in text
    # Responsive breakpoint.
    assert "@media" in text and "max-width" in text
    # Cards + soft shadow.
    assert ".card" in text
    # Ensure nothing imports a framework.
    for banned in ("tailwind", "bootstrap", "bulma"):
        assert banned not in text.lower(), f"CSS should not reference {banned}"


# ---- JS content (fetch calls + no framework) ---------------------


def test_js_uses_fetch_and_targets_expected_endpoints():
    text = JS_FILE.read_text(encoding="utf-8")
    assert "fetch(" in text
    for endpoint in ("/predict", "/version", "/health", "/ready"):
        assert endpoint in text, f"JS should call {endpoint}"
    # No framework globals.
    for banned in ("React", "Vue", "angular", "$(", "jQuery"):
        assert banned not in text, f"JS should not depend on {banned}"


def test_js_predict_call_uses_json_post():
    text = JS_FILE.read_text(encoding="utf-8")
    assert 'method: "POST"' in text
    assert 'Content-Type": "application/json"' in text


def test_js_comparison_semaforo_states():
    text = JS_FILE.read_text(encoding="utf-8")
    # Semáforo classification is present.
    for token in ("below", "near", "over"):
        assert token in text
    # Emoji dots match the prompt.
    assert "🟢" in text
    assert "🟡" in text
    assert "🔴" in text


def test_js_handles_error_states():
    text = JS_FILE.read_text(encoding="utf-8")
    # Explicit friendly error handling for common failure modes:
    for keyword in (
        "prediction_timeout",
        "422",
        "503",
        "conectarnos con la API",
    ):
        assert keyword in text


def test_js_never_shows_traceback_verbiage():
    text = JS_FILE.read_text(encoding="utf-8")
    for banned in ("Traceback", "stack trace", "exception:"):
        assert banned.lower() not in text.lower()


def test_js_polls_status_indicator():
    text = JS_FILE.read_text(encoding="utf-8")
    assert "refreshStatus" in text
    assert "setInterval" in text


# ---- HTML: status indicator wiring ------------------------------


def test_home_renders_status_indicator(api_env):
    app = create_app()
    body = asyncio.run(_asgi_call(app, "GET", "/"))["body"].decode()
    assert 'id="status-indicator"' in body
    # Three states must be spelled somewhere so the CSS covers them.
    css = CSS_FILE.read_text(encoding="utf-8")
    for state in ('data-state="ok"', 'data-state="init"', 'data-state="error"'):
        assert state in css


# ---- End-to-end: real /predict call driven by the ASGI harness --


def test_predict_endpoint_still_returns_json_after_ui_wired(api_env):
    """/predict must keep its JSON contract — the UI must not have
    accidentally masked it with the HTML router."""
    import json

    payload = json.dumps(
        {
            "property_type": "apartment",
            "price": 1500.0,
            "bedrooms": 2,
            "bathrooms": 1,
            "covered_area": 55.0,
            "total_area": 60.0,
            "latitude": -34.9,
            "longitude": -56.2,
            "neighborhood": "Pocitos",
        }
    ).encode()
    app = create_app()
    result = asyncio.run(
        _asgi_call(
            app,
            "POST",
            "/predict",
            headers=[(b"content-type", b"application/json")],
            body=payload,
        )
    )
    assert result["status"] == 200
    body = json.loads(result["body"])
    assert "prediction" in body
    assert "currency" in body


def test_version_endpoint_still_serves_json_for_ui(api_env):
    import json

    app = create_app()
    result = asyncio.run(_asgi_call(app, "GET", "/version"))
    assert result["status"] == 200
    body = json.loads(result["body"])
    for field in ("model_type", "model_version", "trained_at", "bundle_sha256", "api_version"):
        assert field in body


def test_health_and_ready_endpoints_still_work(api_env):
    import json

    app = create_app()
    for endpoint in ("/health", "/ready"):
        result = asyncio.run(_asgi_call(app, endpoint and "GET", endpoint))
        assert result["status"] in (200, 503), f"{endpoint} unexpected status"
        body = json.loads(result["body"])
        assert "status" in body


# ---- Docs ------------------------------------------------------


def test_openapi_still_hides_web_routes(api_env):
    """The web UI must not pollute the OpenAPI schema."""
    import json

    app = create_app()
    result = asyncio.run(_asgi_call(app, "GET", "/openapi.json"))
    assert result["status"] == 200
    schema = json.loads(result["body"])
    paths = schema.get("paths", {})
    assert "/" not in paths, "Home page leaked into OpenAPI schema"


# ---- Cross-check: templates + jinja2 dependency available -----


def test_jinja2_is_a_declared_api_dependency():
    text = (ROOT / "requirements-api.txt").read_text(encoding="utf-8")
    assert re.search(r"^jinja2==", text, flags=re.MULTILINE)


def test_pyproject_includes_web_assets_in_package_data():
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    for pattern in ("api/templates/", "api/static/css/", "api/static/js/"):
        assert pattern in text, f"pyproject.toml package-data missing {pattern}"


# ---- Responsive design sanity check ---------------------------


def test_html_declares_viewport_for_responsive_rendering():
    body = BASE_HTML.read_text(encoding="utf-8")
    assert 'name="viewport"' in body
    assert "width=device-width" in body


@pytest.mark.parametrize(
    "keyword",
    [
        "grid-template-columns: 1fr",  # form collapses to single column
        "flex-direction: column",  # header + footer stack vertically
    ],
)
def test_css_has_mobile_breakpoint_rules(keyword):
    text = CSS_FILE.read_text(encoding="utf-8")
    # The rule must live inside a @media block.
    media_blocks = re.findall(r"@media[^{]*\{[^{}]*(?:\{[^}]*\}[^{}]*)*\}", text, flags=re.DOTALL)
    combined = "\n".join(media_blocks)
    assert keyword in combined, f"missing responsive rule: {keyword}"
