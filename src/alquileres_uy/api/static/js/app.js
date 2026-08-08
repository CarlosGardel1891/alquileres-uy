// alquileres-uy web UI — vanilla JS (no framework, no bundler).
// All XHR done through fetch() against the same origin.

(function () {
  "use strict";

  const ENDPOINTS = {
    predict: "/predict",
    version: "/version",
    health: "/health",
    ready: "/ready",
  };

  // ---- DOM -----------------------------------------------------------

  const byId = (id) => document.getElementById(id);
  const form = byId("predict-form");
  const submitBtn = byId("submit-btn");
  const resultCard = byId("result-card");
  const errorCard = byId("error-card");
  const errorMessage = byId("error-message");
  const errorDismiss = byId("error-dismiss");
  const modelInfoRoot = byId("model-info");
  const statusIndicator = byId("status-indicator");

  // ---- helpers -------------------------------------------------------

  function setText(el, value) {
    if (el) el.textContent = value;
  }

  function formatCurrency(value, currency) {
    if (typeof value !== "number" || !isFinite(value)) return "—";
    try {
      return new Intl.NumberFormat("es-UY", {
        style: "currency",
        currency: currency || "USD",
        maximumFractionDigits: 0,
      }).format(value);
    } catch (_) {
      return `${currency || "USD"} ${value.toFixed(0)}`;
    }
  }

  function setStatus(state, label) {
    if (!statusIndicator) return;
    const dot = statusIndicator.querySelector(".status-dot");
    const text = statusIndicator.querySelector(".status-label");
    if (dot) dot.dataset.state = state;
    if (text) text.textContent = label;
  }

  function showError(message) {
    if (!errorCard) return;
    setText(errorMessage, message || "Ocurrió un problema inesperado.");
    errorCard.hidden = false;
    errorCard.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function hideError() {
    if (errorCard) errorCard.hidden = true;
  }

  function hideResult() {
    if (resultCard) resultCard.hidden = true;
  }

  // ---- friendly error messages --------------------------------------

  function humanReadableError(status, body) {
    if (status === 0) {
      return "No pudimos conectarnos con la API. Verificá tu conexión o probá de nuevo en unos segundos.";
    }
    if (status === 408 || status === 504) {
      return "La API tardó demasiado en responder. Intentá de nuevo en unos segundos.";
    }
    if (status === 422) {
      return "Alguno de los datos ingresados no es válido. Revisá el formulario y volvé a intentar.";
    }
    if (status === 503) {
      const code = body && body.error && body.error.code;
      if (code === "prediction_timeout") {
        return "La predicción tardó demasiado. Volvé a intentar en unos segundos.";
      }
      if (code === "service_unavailable" || code === "model_not_ready") {
        return "El modelo no está disponible en este momento. Probá de nuevo más tarde.";
      }
      return "El servicio no está disponible en este momento.";
    }
    if (status >= 500) {
      return "El servicio tuvo un problema interno. Intentá de nuevo más tarde.";
    }
    if (body && body.error && body.error.message) {
      return body.error.message;
    }
    return "No pudimos calcular el precio. Revisá los datos y volvé a intentar.";
  }

  // ---- comparison logic ---------------------------------------------

  function classifyComparison(publishedPrice, estimatedPrice) {
    if (!publishedPrice || publishedPrice <= 0) return null;
    const diffAbs = publishedPrice - estimatedPrice;
    const diffPct = (diffAbs / estimatedPrice) * 100;
    let state;
    let label;
    if (diffPct <= -5) {
      state = "below";
      label = "🟢 debajo del valor estimado";
    } else if (diffPct <= 10) {
      state = "near";
      label = "🟡 cercano al valor estimado";
    } else {
      state = "over";
      label = "🔴 muy por encima del valor estimado";
    }
    return { diffAbs, diffPct, state, label };
  }

  // ---- form submission ---------------------------------------------

  function collectPayload() {
    const priceInput = byId("price").value;
    const publishedPrice = priceInput === "" ? null : Number(priceInput);
    // The API contract requires price > 0. When the user leaves the
    // published price blank we submit a minimal placeholder so the
    // request validates, and we hide the comparison card because the
    // user never gave us a reference to compare against.
    const priceForApi = publishedPrice !== null && publishedPrice > 0 ? publishedPrice : 1;
    return {
      payload: {
        property_type: byId("property_type").value,
        price: priceForApi,
        bedrooms: Number(byId("bedrooms").value),
        bathrooms: Number(byId("bathrooms").value),
        covered_area: Number(byId("covered_area").value),
        total_area: Number(byId("total_area").value),
        latitude: Number(byId("latitude").value),
        longitude: Number(byId("longitude").value),
        neighborhood: byId("neighborhood").value.trim(),
      },
      publishedPrice,
    };
  }

  async function submitPrediction(event) {
    event.preventDefault();
    if (form && !form.checkValidity()) {
      form.reportValidity();
      return;
    }
    hideError();
    hideResult();
    submitBtn.disabled = true;
    submitBtn.textContent = "Calculando…";

    const { payload, publishedPrice } = collectPayload();
    let response;
    let body = null;
    try {
      response = await fetch(ENDPOINTS.predict, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify(payload),
      });
    } catch (_) {
      submitBtn.disabled = false;
      submitBtn.textContent = "Calcular precio";
      showError(humanReadableError(0, null));
      return;
    }
    try {
      body = await response.json();
    } catch (_) {
      body = null;
    }
    submitBtn.disabled = false;
    submitBtn.textContent = "Calcular precio";

    if (!response.ok) {
      showError(humanReadableError(response.status, body));
      return;
    }
    renderResult(body, publishedPrice);
  }

  function renderResult(body, publishedPrice) {
    if (!body || typeof body.prediction !== "number") {
      showError("La respuesta de la API no tiene el formato esperado.");
      return;
    }
    setText(byId("result-price"), formatCurrency(body.prediction, body.currency));
    setText(byId("result-currency"), body.currency || "USD");
    setText(byId("result-model"), body.model_type || "—");
    setText(byId("result-version"), body.model_version || "—");
    setText(byId("result-timestamp"), body.prediction_timestamp || "—");

    const comparison = classifyComparison(publishedPrice, body.prediction);
    const comparisonCard = byId("comparison");
    if (comparison) {
      comparisonCard.hidden = false;
      const badge = byId("comparison-badge");
      badge.dataset.state = comparison.state;
      setText(badge, comparison.label);
      setText(byId("diff-absolute"), formatCurrency(comparison.diffAbs, body.currency));
      setText(byId("diff-percent"), `${comparison.diffPct.toFixed(1)} %`);
      setText(
        byId("comparison-note"),
        comparison.diffAbs >= 0
          ? "El precio publicado supera al valor estimado."
          : "El precio publicado está por debajo del valor estimado."
      );
    } else {
      comparisonCard.hidden = true;
    }

    resultCard.hidden = false;
    resultCard.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  // ---- model info (from /version) -----------------------------------

  async function loadModelInfo() {
    if (!modelInfoRoot) return;
    try {
      const response = await fetch(ENDPOINTS.version, { headers: { Accept: "application/json" } });
      if (!response.ok) return;
      const data = await response.json();
      const map = {
        model_type: data.model_type,
        model_version: data.model_version,
        trained_at: data.trained_at,
        bundle_sha256: data.bundle_sha256,
        api_version: data.api_version,
      };
      Object.entries(map).forEach(([field, value]) => {
        const node = modelInfoRoot.querySelector(`[data-field="${field}"]`);
        if (node) setText(node, value || "—");
      });
    } catch (_) {
      // Silent: the header status indicator will already reflect
      // whether the API is reachable.
    }
  }

  // ---- health + ready polling --------------------------------------

  async function refreshStatus() {
    let healthOk = false;
    let readyOk = false;
    try {
      const res = await fetch(ENDPOINTS.health, { headers: { Accept: "application/json" } });
      healthOk = res.ok;
    } catch (_) {
      healthOk = false;
    }
    if (!healthOk) {
      setStatus("error", "● Error — API no disponible");
      return;
    }
    try {
      const res = await fetch(ENDPOINTS.ready, { headers: { Accept: "application/json" } });
      readyOk = res.ok;
    } catch (_) {
      readyOk = false;
    }
    if (readyOk) {
      setStatus("ok", "● Online");
    } else {
      setStatus("init", "● Inicializando…");
    }
  }

  // ---- bootstrap ----------------------------------------------------

  function bootstrap() {
    if (form) form.addEventListener("submit", submitPrediction);
    if (errorDismiss) errorDismiss.addEventListener("click", hideError);
    loadModelInfo();
    refreshStatus();
    // Refresh the status pill every 30 seconds so a temporary blip
    // does not leave the user with a stale indicator.
    setInterval(refreshStatus, 30000);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bootstrap);
  } else {
    bootstrap();
  }
})();
