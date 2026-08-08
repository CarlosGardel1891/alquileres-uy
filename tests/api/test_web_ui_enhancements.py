"""Fase 12 web-UI enhancement tests.

Same no-httpx / no-Selenium / no-Playwright constraint as before: the
UI behaviour is exercised by inspecting the packaged HTML / CSS / JS
on disk plus the ASGI-rendered home page. Client-side APIs
(localStorage, clipboard, historial) are validated at the source
level — the tests fail loudly if a required feature is renamed or
removed.

The tests cover every part the prompt lists as a validation target:

* Persistencia del formulario (localStorage save + restore + reset).
* Historial local (panel lateral, límite 10, entries sin PII).
* Modo ejemplo (botón + valores válidos).
* Copiar resultado (botón + Clipboard API + fallback execCommand).
* Estados de carga (loading / success / error / retrying, sin alert).
* Accesibilidad (labels, focus-visible, aria-live, contraste, keyboard).
* Validaciones UI (obligatorios, rangos, lat/lng, superficie cero).
* Comparación visual mejorada (barra, badges, interpretación textual).
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


# ---- minimal ASGI harness (identical to previous phases) ---------


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


@pytest.fixture(scope="module")
def js_text():
    return JS_FILE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def css_text():
    return CSS_FILE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def html_text():
    return INDEX_HTML.read_text(encoding="utf-8")


# ---- Persistencia del formulario ---------------------------------


def test_js_persists_form_values_to_localstorage(js_text):
    # A storage-key constant + read/write helpers exist.
    assert "STORAGE_KEYS" in js_text
    assert "form-values" in js_text
    assert "saveFormValues" in js_text
    assert "loadFormValues" in js_text
    assert "localStorage.setItem" in js_text or "storage.setItem" in js_text
    assert "localStorage.getItem" in js_text or "storage.getItem" in js_text


def test_js_restores_form_on_load(js_text):
    # loadFormValues() must run during bootstrap so a reload restores the
    # last input.
    match = re.search(r"function bootstrap\s*\([^)]*\)\s*\{([^}]+)\}", js_text, flags=re.DOTALL)
    assert match, "bootstrap() function not found"
    body = match.group(1)
    assert "loadFormValues" in body


def test_js_reset_button_clears_persisted_values(js_text):
    # The reset click handler must remove the persisted values so the
    # user can start over cleanly.
    assert "clearFormValues" in js_text
    assert "resetBtn" in js_text or 'byId("reset-btn")' in js_text


def test_js_never_submits_form_automatically(js_text):
    # The bootstrap only wires listeners; there is no top-level submit /
    # requestSubmit call that could fire without a user gesture.
    forbidden_patterns = (
        r"form\.submit\s*\(\)",
        r"\.requestSubmit\s*\(",
        r"submitPrediction\s*\(\s*\)\s*;",
    )
    for pattern in forbidden_patterns:
        assert not re.search(pattern, js_text), f"JS auto-submits: {pattern}"


# ---- Historial local --------------------------------------------


def test_history_sidebar_present_in_html(html_text):
    assert 'id="history-panel"' in html_text
    assert 'id="history-list"' in html_text
    assert 'id="history-empty"' in html_text
    # ARIA label so the panel is discoverable by assistive tech.
    assert "aria-label" in html_text
    assert "Historial" in html_text


def test_js_history_limit_is_ten(js_text):
    assert re.search(r"HISTORY_LIMIT\s*=\s*10", js_text)


def test_js_history_helpers_exist(js_text):
    for name in ("loadHistory", "saveHistory", "pushHistoryEntry", "renderHistory", "clearHistory"):
        assert name in js_text, f"history helper missing: {name}"


def test_js_history_uses_localstorage_key(js_text):
    assert re.search(r"history[^\"']*['\"]", js_text)
    assert "alquileres-uy:history" in js_text


def test_js_history_does_not_store_sensitive_fields(js_text):
    """Latitude/longitude, exact address or user identifiers should not
    make it into the persisted history payload.

    We assert this at the source level: the historial-entry constructor
    must NOT include latitude / longitude / price."""
    entry_fn = re.search(
        r"function buildHistoryEntry[^{]*\{([\s\S]*?)\n  \}",
        js_text,
    )
    assert entry_fn, "buildHistoryEntry not found"
    body = entry_fn.group(1)
    for banned in ("latitude", "longitude", "price:", "values.price"):
        assert banned not in body, f"history entry should not persist {banned}"


def test_js_history_renders_required_fields(js_text):
    # The rendering path shows barrio, tipo, superficie, precio, timestamp,
    # and a state badge.
    for token in (
        "history-item-title",
        "history-item-badge",
        "history-item-meta",
        "history-item-price",
        "formatTimestamp",
    ):
        assert token in js_text


# ---- Modo ejemplo -----------------------------------------------


def test_html_has_load_example_button(html_text):
    assert 'id="load-example-btn"' in html_text
    assert "Cargar ejemplo" in html_text


def test_js_load_example_fills_all_persisted_fields(js_text):
    assert "EXAMPLE_VALUES" in js_text
    # All 9 form fields must have a value in the example payload.
    for field in (
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
        assert re.search(rf"{re.escape(field)}\s*:\s*\"", js_text), f"example missing {field}"


def test_js_load_example_does_not_auto_submit(js_text):
    example_fn = re.search(r"function loadExample[^{]*\{([\s\S]*?)\n  \}", js_text)
    assert example_fn, "loadExample not found"
    body = example_fn.group(1)
    assert "submitPrediction" not in body
    assert "form.submit" not in body
    assert "requestSubmit" not in body


# ---- Copiar resultado -------------------------------------------


def test_html_has_copy_button_and_feedback(html_text):
    assert 'id="copy-result-btn"' in html_text
    assert 'id="copy-feedback"' in html_text
    # Live region so screen readers pick up "Copiado".
    assert re.search(r'id="copy-feedback"[^>]*aria-live', html_text, flags=re.DOTALL)


def test_js_copy_uses_clipboard_api_with_fallback(js_text):
    assert "navigator.clipboard" in js_text
    assert "writeText" in js_text
    # Fallback path for browsers without the clipboard API.
    assert "execCommand" in js_text


def test_js_copy_payload_covers_required_fields(js_text):
    copy_fn = re.search(r"async function copyResult[^{]*\{([\s\S]*?)\n  \}", js_text)
    assert copy_fn, "copyResult not found"
    body = copy_fn.group(1)
    for token in ("Precio estimado", "Modelo", "Versión", "Timestamp"):
        assert token in body, f"copy payload missing {token}"


# ---- Estados de carga -------------------------------------------


def test_js_uses_form_status_state_machine(js_text):
    for state in ("loading", "success", "error", "retrying"):
        assert re.search(rf'setFormStatus\(\s*"{state}"', js_text), f"missing state: {state}"


def test_js_never_uses_alert_or_confirm(js_text):
    assert "alert(" not in js_text
    assert "confirm(" not in js_text
    assert "prompt(" not in js_text


def test_js_submit_button_toggles_busy_state(js_text):
    assert "setSubmitBusy" in js_text
    assert "aria-busy" in js_text
    assert "disabled" in js_text


def test_html_and_css_render_button_spinner(html_text, css_text):
    assert "btn-spinner" in html_text
    assert "btn-spinner" in css_text
    # Spinner must live inside a keyframes animation.
    assert "@keyframes spin" in css_text


def test_css_provides_state_colors_for_form_status(css_text):
    for state in ("loading", "success", "error", "retrying"):
        assert f'data-state="{state}"' in css_text, f"CSS missing status state {state}"


def test_html_has_retry_button_in_error_card(html_text):
    assert 'id="retry-btn"' in html_text
    # Sits inside the error card.
    error_section = re.search(
        r'<section[^>]*class="[^"]*error-card[^"]*"[^>]*>[\s\S]*?</section>',
        html_text,
    )
    assert error_section is not None
    assert 'id="retry-btn"' in error_section.group(0)


def test_js_retry_button_reuses_last_payload(js_text):
    assert "retryPrediction" in js_text
    assert "lastPayload" in js_text


# ---- Accesibilidad ----------------------------------------------


def test_every_input_has_a_matching_label(html_text):
    """Every id="foo" input/select gets a <label for="foo"> element."""
    ids = re.findall(r'<(?:input|select)[^>]*id="([^"]+)"', html_text)
    for input_id in ids:
        assert re.search(
            rf'<label[^>]*for="{re.escape(input_id)}"', html_text
        ), f"input {input_id} missing label"


def test_html_uses_aria_live_for_results_and_errors(html_text):
    # Result card + form status + comparison + copy feedback + error card
    # must be live regions.
    for target in (
        r'id="result-card"[^>]*aria-live',
        r'id="form-status"[^>]*aria-live',
        r'id="error-card"[^>]*aria-live',
        r'id="model-info"[^>]*aria-live',
    ):
        assert re.search(target, html_text, flags=re.DOTALL), f"missing live region: {target}"


def test_css_defines_focus_visible_ring(css_text):
    # A dedicated :focus-visible rule is present.
    assert re.search(r":focus-visible\s*\{[^}]*outline", css_text, flags=re.DOTALL)


def test_css_uses_high_contrast_palette(css_text):
    # Body text is very dark (#0f172a, ratio ≈ 16.7:1 vs #f5f7fb).
    assert "--color-text: #0f172a" in css_text
    # Muted text is #475569 (ratio ≈ 4.6:1 — meets WCAG AA for body).
    assert "--color-muted: #475569" in css_text
    # Primary meets contrast at 4.5:1 against white backgrounds.
    assert "--color-primary: #4338ca" in css_text or "--color-primary: #4f46e5" in css_text


def test_css_supports_reduced_motion_preference(css_text):
    assert "prefers-reduced-motion: reduce" in css_text


def test_html_has_skip_link_for_keyboard_users(html_text):
    body = BASE_HTML.read_text(encoding="utf-8")
    assert 'class="skip-link"' in body
    assert 'href="#main"' in body


def test_field_errors_are_role_alert(html_text):
    """Inline field errors must be role='alert' so assistive tech announces them."""
    error_ids = re.findall(r'id="([^"]+-error)"', html_text)
    assert error_ids, "no per-field error slots found"
    for eid in error_ids:
        assert re.search(rf'id="{re.escape(eid)}"[^>]*role="alert"', html_text)


def test_form_status_uses_role_status(html_text):
    assert re.search(r'id="form-status"[^>]*role="status"', html_text)


# ---- Validaciones UI --------------------------------------------


def test_js_declares_numeric_field_bounds(js_text):
    # All the bounded numeric fields have a rule in NUMERIC_FIELDS.
    assert "NUMERIC_FIELDS" in js_text
    for field in ("bedrooms", "bathrooms", "total_area", "covered_area", "latitude", "longitude"):
        assert re.search(
            rf"{re.escape(field)}\s*:\s*\{{", js_text
        ), f"NUMERIC_FIELDS missing {field}"


def test_js_validation_rejects_lat_lng_out_of_range(js_text):
    # latitude bounded to [-90, 90]; longitude to [-180, 180].
    assert re.search(r"latitude\s*:\s*\{\s*min:\s*-90\s*,\s*max:\s*90", js_text)
    assert re.search(r"longitude\s*:\s*\{\s*min:\s*-180\s*,\s*max:\s*180", js_text)


def test_js_validation_rejects_zero_surface(js_text):
    # total_area / covered_area must have a min of 1.
    assert re.search(r"total_area\s*:\s*\{\s*min:\s*1\b", js_text)
    assert re.search(r"covered_area\s*:\s*\{\s*min:\s*1\b", js_text)


def test_js_validation_covers_empty_and_negative(js_text):
    # Empty required field message + negative-value guard for price.
    assert "obligatorio" in js_text
    assert "no puede ser negativo" in js_text


def test_js_validates_cross_field_covered_le_total(js_text):
    assert "no puede superar la superficie total" in js_text


def test_js_validate_runs_before_submit(js_text):
    submit_fn = re.search(r"async function submitPrediction[^{]*\{([\s\S]*?)\n  \}", js_text)
    assert submit_fn, "submitPrediction not found"
    body = submit_fn.group(1)
    assert "validateForm" in body
    # First error stops the submission.
    assert "return;" in body


# ---- Comparación mejorada ---------------------------------------


def test_html_has_enhanced_comparison_bar(html_text):
    for token in (
        "comparison-bar",
        "comparison-bar-track",
        "comparison-bar-zone",
        "comparison-bar-marker",
        "comparison-bar-labels",
        "comparison-interpretation",
    ):
        assert token in html_text, f"comparison HTML missing {token}"


def test_css_paints_three_zones_and_marker(css_text):
    for token in (
        ".comparison-bar",
        ".comparison-bar-track",
        ".zone-below",
        ".zone-near",
        ".zone-over",
        ".comparison-bar-marker",
    ):
        assert token in css_text, f"comparison CSS missing {token}"


def test_js_moves_marker_by_diff_percent(js_text):
    assert "updateComparisonBar" in js_text
    # The marker uses left: {n}% derived from the clamped diff percent.
    assert re.search(r"marker\.style\.left\s*=", js_text)
    assert "Math.max(-20" in js_text
    assert "Math.min(20" in js_text


def test_js_classifies_interpretation_for_each_state(js_text):
    # A friendly interpretation string per state so the UI is readable.
    classify_fn = re.search(r"function classifyComparison[^{]*\{([\s\S]*?)\n  \}", js_text)
    assert classify_fn, "classifyComparison not found"
    body = classify_fn.group(1)
    # Three states + a matching interpretation each.
    for state in ("below", "near", "over"):
        assert f'state = "{state}"' in body, f"missing state: {state}"
    for emoji in ("🟢", "🟡", "🔴"):
        assert emoji in body, f"missing emoji: {emoji}"
    assert body.count("interpretation =") >= 3


# ---- Home page still renders + contract preserved ---------------


def test_home_still_returns_200_and_html(api_env):
    app = create_app()
    result = asyncio.run(_asgi_call(app, "GET", "/"))
    assert result["status"] == 200
    assert result["headers"].get("content-type", "").startswith("text/html")


def test_home_layout_includes_sidebar_and_main(api_env):
    app = create_app()
    body = asyncio.run(_asgi_call(app, "GET", "/"))["body"].decode()
    assert 'id="layout"' in body
    assert "layout-main" in body
    assert "layout-sidebar" in body


def test_predict_endpoint_still_returns_json(api_env):
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


# ---- Responsive still works at both breakpoints -----------------


def test_css_has_sidebar_stack_breakpoint(css_text):
    # At <= 960 px the sidebar must collapse (single column).
    match = re.search(r"@media\s*\(\s*max-width:\s*960px\s*\)\s*\{([\s\S]*?)\}\s*\}", css_text)
    assert match, "no 960px media block"
    assert "grid-template-columns: 1fr" in match.group(1)


def test_css_has_form_stack_breakpoint(css_text):
    match = re.search(r"@media\s*\(\s*max-width:\s*640px\s*\)\s*\{([\s\S]*?)\}\s*\}", css_text)
    assert match, "no 640px media block"
    assert "grid-template-columns: 1fr" in match.group(1)


# ---- Restrictions -----------------------------------------------


def test_no_bootstrap_or_tailwind_or_framework_in_css(css_text):
    for banned in ("tailwind", "bootstrap", "bulma", "foundation"):
        assert banned not in css_text.lower(), f"CSS should not reference {banned}"


def test_no_framework_globals_in_js(js_text):
    for banned in ("React", "Vue", "angular", "jQuery", "$("):
        assert banned not in js_text, f"JS should not depend on {banned}"


def test_no_selenium_playwright_cypress_references():
    """Sanity: neither the JS nor the CSS pull the banned browser
    automation frameworks."""
    for text in (JS_FILE.read_text(encoding="utf-8"), CSS_FILE.read_text(encoding="utf-8")):
        for banned in ("selenium", "playwright", "cypress"):
            assert banned not in text.lower(), f"banned reference: {banned}"
