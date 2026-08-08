"""Fase 13 UI-polish tests.

Same no-httpx / no-Selenium / no-Playwright / no-Cypress constraint
as the previous phases. UI behaviour is validated by inspecting the
packaged HTML / CSS / JS on disk and by driving the ASGI app for
end-to-end HTTP checks.

Coverage per prompt part:

* Estado de formulario más claro (required indicators, helper text,
  visible success + error status).
* Comparación más útil (headline, texto explicativo, porcentaje
  redondeado legible, empty state, jerarquía visual).
* Accesibilidad reforzada (aria-describedby, semántica de headings,
  visually-hidden helpers, focus más evidente).
* Microcopy (qué hace la página / qué se envía / qué significa el
  resultado / que es una estimación).
* Home visual polish (spacing tokens, footer prolijo, indicador de
  estado del modelo con hint, cards balanceadas).
* Animaciones suaves (fade-in on result/error, respeta reduced motion).
* Errores diferenciados (validation / network / timeout / unavailable /
  model), sin traceback, con guidance.
* Home + contract preservation.
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


@pytest.fixture(scope="module")
def js_text():
    return JS_FILE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def css_text():
    return CSS_FILE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def html_text():
    return INDEX_HTML.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def base_html_text():
    return BASE_HTML.read_text(encoding="utf-8")


# ---- Formulario más claro ----------------------------------------


def test_form_has_required_legend(html_text):
    assert 'class="required-legend"' in html_text
    assert "obligatorio" in html_text.lower() or "obligatorios" in html_text.lower()


def test_required_fields_render_visible_marker(html_text):
    # Every input that has `required` sits next to a <span class="required-mark">.
    required_inputs = re.findall(
        r'<(?:input|select)[^>]*id="([^"]+)"[^>]*required[^>]*>',
        html_text,
    )
    assert required_inputs, "no required inputs found"
    # The label for each required input must contain the required-mark class.
    for input_id in required_inputs:
        label_match = re.search(
            rf'<label[^>]*for="{re.escape(input_id)}"[^>]*>([\s\S]*?)</label>',
            html_text,
        )
        assert label_match, f"label missing for {input_id}"
        label_body = label_match.group(1)
        assert "required-mark" in label_body, f"label for {input_id} has no required marker"
        # Screen-reader companion.
        assert "visually-hidden" in label_body, f"label for {input_id} missing SR-only helper"


def test_form_has_helper_text_on_key_fields(html_text):
    # At least three fields carry a persistent field-hint helper.
    hints = re.findall(r'class="field-hint"', html_text)
    assert len(hints) >= 3, f"expected ≥3 helper texts, found {len(hints)}"
    # Specific hints for surface, neighborhood and price.
    assert 'id="neighborhood-hint"' in html_text
    assert 'id="total_area-hint"' in html_text
    assert 'id="price-hint"' in html_text


def test_form_shows_visible_status_when_incomplete(js_text):
    # Submit path must set an error status + message when validateForm returns errors.
    submit_fn = re.search(r"async function submitPrediction[^{]*\{([\s\S]*?)\n  \}", js_text)
    assert submit_fn, "submitPrediction not found"
    body = submit_fn.group(1)
    assert "errors.length" in body
    assert 'setFormStatus("error"' in body or 'setFormStatus(\n        "error"' in body
    # And renders a visible error card with a validation kind.
    assert 'kind: "validation"' in body


def test_form_shows_visible_success_state(js_text):
    submit_fn = re.search(r"async function submitPrediction[^{]*\{([\s\S]*?)\n  \}", js_text)
    assert submit_fn, "submitPrediction not found"
    body = submit_fn.group(1)
    assert 'setFormStatus("success"' in body
    # Success verbiage confirms the estimation.
    assert "estimación" in body.lower() or "listo" in body.lower()


def test_form_never_uses_alert(js_text):
    assert "alert(" not in js_text
    assert "confirm(" not in js_text
    assert "prompt(" not in js_text


# ---- Comparación más útil ---------------------------------------


def test_comparison_headline_shows_published_vs_estimated(html_text):
    assert 'class="comparison-headline"' in html_text
    assert 'id="comparison-published"' in html_text
    assert 'id="comparison-estimated"' in html_text
    assert "vs." in html_text


def test_comparison_empty_state_present(html_text):
    assert 'id="comparison-empty"' in html_text
    # Empty state visible when the user did NOT provide a published price.
    match = re.search(
        r'<p[^>]*id="comparison-empty"[^>]*>([\s\S]*?)</p>',
        html_text,
    )
    assert match, "comparison empty state not found"
    body = match.group(1)
    assert "Precio publicado" in body


def test_js_toggles_empty_state_correctly(js_text):
    # renderResult must reveal the empty state only when no publishedPrice was set.
    render_fn = re.search(r"function renderResult[^{]*\{([\s\S]*?)\n  \}", js_text)
    assert render_fn, "renderResult not found"
    body = render_fn.group(1)
    assert "comparisonEmpty" in body
    # Both branches must be present.
    assert "comparisonEmpty.hidden = true" in body
    assert "comparisonEmpty.hidden = false" in body


def test_js_rounds_percent_readably(js_text):
    assert "roundPercent" in js_text
    # Drops trailing .0 for whole-number percents.
    round_fn = re.search(r"function roundPercent[^{]*\{([\s\S]*?)\n  \}", js_text)
    assert round_fn, "roundPercent not found"
    body = round_fn.group(1)
    assert "isInteger" in body
    assert "toFixed(1)" in body


def test_js_comparison_language_is_natural(js_text):
    classify_fn = re.search(r"function classifyComparison[^{]*\{([\s\S]*?)\n  \}", js_text)
    assert classify_fn, "classifyComparison not found"
    body = classify_fn.group(1)
    # Human-language labels rather than raw jargon.
    for phrase in ("buen precio", "en línea con el mercado", "precio elevado"):
        assert phrase in body, f"missing natural label: {phrase}"


def test_css_gives_visual_hierarchy_between_estimated_and_published(css_text):
    # Estimated value gets the primary colour, published stays neutral.
    assert ".comparison-value-estimated" in css_text
    assert "color: var(--color-primary)" in css_text
    # Comparison headline sits inside a raised surface for visual weight.
    assert ".comparison-headline" in css_text
    assert "background: var(--color-surface-muted)" in css_text or "surface-muted" in css_text


# ---- Accesibilidad reforzada ------------------------------------


def test_every_input_has_matching_label(html_text):
    ids = re.findall(r'<(?:input|select)[^>]*id="([^"]+)"', html_text)
    for input_id in ids:
        assert re.search(
            rf'<label[^>]*for="{re.escape(input_id)}"', html_text
        ), f"input {input_id} missing label"


def test_inputs_use_aria_describedby(html_text):
    """Every hint or error node is referenced by its input via aria-describedby."""
    described_by = re.findall(
        r'<(?:input|select)[^>]*id="([^"]+)"[^>]*aria-describedby="([^"]+)"',
        html_text,
    )
    assert described_by, "no inputs use aria-describedby"
    # At minimum: neighborhood, price and covered_area must reference their hints.
    field_map = dict(described_by)
    assert "neighborhood-hint" in field_map.get("neighborhood", "")
    assert "price-hint" in field_map.get("price", "")
    assert "covered_area-hint" in field_map.get("covered_area", "")


def test_form_status_and_help_are_referenced_by_form(html_text):
    # The <form> itself points to the help + status live regions.
    form_match = re.search(r'<form[^>]*id="predict-form"[^>]*>', html_text)
    assert form_match, "form tag not found"
    form_attrs = form_match.group(0)
    assert "aria-describedby" in form_attrs
    assert "form-status" in form_attrs
    assert "form-help" in form_attrs


def test_visually_hidden_utility_exists(css_text, html_text):
    assert ".visually-hidden" in css_text
    # Used in labels to spell out "obligatorio" for screen readers.
    assert "visually-hidden" in html_text


def test_semantic_heading_hierarchy(html_text, base_html_text):
    # Base template owns the single h1 (brand). Index uses h2 for section titles.
    assert re.search(r"<h1[^>]*>", base_html_text)
    assert not re.search(r"<h1[^>]*>", html_text), "index must not introduce a second h1"
    # Section titles are h2, sub-sections h3.
    assert html_text.count("<h2") >= 3
    assert re.search(r'<h3[^>]*id="comparison-title"', html_text)


def test_focus_visible_ring_is_stronger(css_text):
    match = re.search(r":focus-visible\s*\{([^}]+)\}", css_text, flags=re.DOTALL)
    assert match, "no :focus-visible rule"
    body = match.group(1)
    # Outline + box-shadow makes the ring more prominent than the previous phase.
    assert "outline:" in body
    assert "box-shadow:" in body


def test_skip_link_is_still_present(base_html_text):
    assert 'class="skip-link"' in base_html_text
    assert 'href="#main"' in base_html_text


def test_status_indicator_has_aria_label(base_html_text):
    match = re.search(r'id="status-indicator"[^>]*>', base_html_text)
    assert match, "status indicator not found"
    tag = match.group(0)
    assert "aria-label" in tag
    assert "role=" in tag


# ---- Microcopy --------------------------------------------------


def test_home_explains_what_the_page_does(html_text):
    assert re.search(r"Estimá[^<]*alquiler", html_text)


def test_home_documents_what_gets_sent(html_text):
    # Hero privacy note enumerates the fields we transmit.
    assert 'class="hero-privacy"' in html_text
    for token in ("barrio", "superficie", "coordenadas"):
        assert token in html_text.lower(), f"privacy copy missing {token}"


def test_home_labels_result_as_estimate(html_text):
    # Two places should mark the result as an "estimación".
    assert html_text.lower().count("estimación") >= 2 or html_text.lower().count("estimacion") >= 2
    # Explicit disclaimer inside the result card.
    assert 'class="result-disclaimer"' in html_text


def test_no_vague_placeholder_verbiage(html_text):
    for banned in ("Lorem ipsum", "TODO", "TBD", "placeholder text"):
        assert banned.lower() not in html_text.lower()


# ---- Home visual polish -----------------------------------------


def test_css_uses_semantic_spacing_scale(css_text):
    # A larger spacing token (--space-6) plus rounded --radius-lg for
    # more balanced cards.
    assert "--space-6" in css_text
    assert "--radius-lg" in css_text
    # Cards use the larger radius.
    assert re.search(
        r"\.card\s*\{[^}]*border-radius:\s*var\(--radius-lg\)", css_text, flags=re.DOTALL
    )


def test_footer_has_polished_structure(base_html_text, css_text):
    assert 'class="footer-primary"' in base_html_text
    assert 'class="footer-secondary"' in base_html_text
    assert 'class="footer-version"' in base_html_text
    # CSS gives the footer a real layout, not just a stack.
    assert ".footer-primary" in css_text
    assert ".footer-secondary" in css_text
    assert ".footer-version" in css_text


def test_model_info_hints_the_source(html_text):
    assert 'class="model-info-hint"' in html_text
    assert "GET /version" in html_text


def test_hero_uses_eyebrow_and_privacy_block(html_text, css_text):
    assert 'class="eyebrow"' in html_text
    assert 'class="hero-privacy"' in html_text
    for cls in (".eyebrow", ".hero-privacy"):
        assert cls in css_text, f"CSS missing {cls}"


def test_brand_mark_present_in_header(base_html_text, css_text):
    assert 'class="brand-mark"' in base_html_text
    assert ".brand-mark" in css_text


# ---- Animaciones suaves -----------------------------------------


def test_css_defines_result_and_error_fade_in(css_text):
    assert "@keyframes fade-in-up" in css_text
    assert "@keyframes fade-in" in css_text
    assert re.search(
        r"\.result-card:not\(\[hidden\]\)[\s\S]*?animation:\s*fade-in-up",
        css_text,
    )
    assert re.search(
        r"\.error-card:not\(\[hidden\]\)[\s\S]*?animation:\s*fade-in-up",
        css_text,
    )


def test_css_defines_card_transition(css_text):
    # Cards ease into hover / state changes rather than jumping.
    assert re.search(
        r"\.card\s*\{[^}]*transition:[^}]*box-shadow",
        css_text,
        flags=re.DOTALL,
    )


def test_css_animates_buttons_and_inputs(css_text):
    # Buttons + form controls have a transition on visual state.
    assert re.search(r"\.btn\s*\{[^}]*transition:", css_text, flags=re.DOTALL)
    assert re.search(
        r"\.field input,\s*\.field select\s*\{[^}]*transition:",
        css_text,
        flags=re.DOTALL,
    )


def test_reduced_motion_disables_animations(css_text):
    match = re.search(
        r"@media\s*\(\s*prefers-reduced-motion:\s*reduce\s*\)\s*\{([\s\S]*?)\}\s*\}?",
        css_text,
    )
    assert match, "no prefers-reduced-motion block"
    body = match.group(1)
    assert "animation-duration: 0" in body
    assert "transition-duration: 0" in body


# ---- Errores mejorados ------------------------------------------


def test_js_classifies_errors_by_kind(js_text):
    assert "ERROR_KIND_LABEL" in js_text
    for kind in ("validation", "network", "timeout", "unavailable", "model", "unknown"):
        assert f'"{kind}"' in js_text, f"missing kind: {kind}"


def test_js_error_messages_are_user_friendly(js_text):
    for phrase in (
        "No pudimos conectarnos",
        "tardó demasiado",
        "Datos inválidos",
        "El modelo no está listo",
    ):
        assert phrase in js_text, f"missing friendly error: {phrase}"


def test_js_error_includes_guidance_field(js_text):
    classify_fn = re.search(r"function classifyError[^{]*\{([\s\S]*?)\n  \}", js_text)
    assert classify_fn, "classifyError not found"
    body = classify_fn.group(1)
    # Every branch should return a guidance field (at minimum: not null for common cases).
    assert body.count("guidance:") >= 4


def test_js_never_surfaces_traceback(js_text):
    for banned in ("Traceback", "stack trace", "console.error"):
        assert banned.lower() not in js_text.lower()


def test_html_has_error_kind_chip(html_text, css_text):
    assert 'id="error-kind"' in html_text
    # A chip per kind gets a distinct colour in CSS.
    for kind in ("network", "timeout", "unavailable", "model", "validation"):
        assert f'data-kind="{kind}"' in css_text, f"CSS missing error kind {kind}"


def test_html_error_card_has_guidance_slot(html_text):
    assert 'id="error-guidance"' in html_text
    assert re.search(r'id="error-guidance"[^>]*hidden', html_text)


# ---- Home still renders + contract preserved --------------------


def test_home_returns_200_and_html(api_env):
    app = create_app()
    result = asyncio.run(_asgi_call(app, "GET", "/"))
    assert result["status"] == 200
    assert result["headers"].get("content-type", "").startswith("text/html")


def test_predict_contract_untouched(api_env):
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
    for field in ("prediction", "currency", "model_version", "prediction_timestamp"):
        assert field in body


# ---- Restrictions -----------------------------------------------


def test_css_still_carries_no_framework_reference(css_text):
    for banned in ("tailwind", "bootstrap", "bulma", "foundation"):
        assert banned not in css_text.lower(), f"framework leaked: {banned}"


def test_js_still_has_no_framework_globals(js_text):
    for banned in ("React", "Vue", "angular", "jQuery", "$("):
        assert banned not in js_text, f"framework leaked: {banned}"


def test_no_selenium_playwright_cypress_references(js_text, css_text):
    for text in (js_text, css_text):
        for banned in ("selenium", "playwright", "cypress"):
            assert banned not in text.lower()
