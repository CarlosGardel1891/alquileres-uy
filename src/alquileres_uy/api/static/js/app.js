// alquileres-uy web UI — vanilla JS (no framework, no bundler).
// All XHR through fetch() against the same origin.

(function () {
  "use strict";

  const ENDPOINTS = {
    predict: "/predict",
    version: "/version",
    health: "/health",
    ready: "/ready",
  };

  const STORAGE_KEYS = {
    form: "alquileres-uy:form-values:v1",
    history: "alquileres-uy:history:v1",
  };

  const HISTORY_LIMIT = 10;

  // Form-value persistence includes the model-feature fields plus the
  // optional published price. We do not persist derived data
  // (predictions, comparisons) — the history list covers that.
  const PERSISTED_FIELDS = [
    "neighborhood",
    "property_type",
    "bedrooms",
    "bathrooms",
    "total_area",
    "covered_area",
    "latitude",
    "longitude",
    "price",
  ];

  const EXAMPLE_VALUES = {
    neighborhood: "Pocitos",
    property_type: "apartment",
    bedrooms: "2",
    bathrooms: "1",
    total_area: "65",
    covered_area: "58",
    latitude: "-34.9067",
    longitude: "-56.1553",
    price: "950",
  };

  // ---- DOM ----------------------------------------------------------

  const byId = (id) => document.getElementById(id);
  const form = byId("predict-form");
  const submitBtn = byId("submit-btn");
  const resetBtn = byId("reset-btn");
  const loadExampleBtn = byId("load-example-btn");
  const copyResultBtn = byId("copy-result-btn");
  const copyFeedback = byId("copy-feedback");
  const retryBtn = byId("retry-btn");
  const historyList = byId("history-list");
  const historyEmpty = byId("history-empty");
  const historyClearBtn = byId("history-clear-btn");
  const formStatus = byId("form-status");
  const resultCard = byId("result-card");
  const errorCard = byId("error-card");
  const errorMessage = byId("error-message");
  const errorDismiss = byId("error-dismiss");
  const modelInfoRoot = byId("model-info");
  const statusIndicator = byId("status-indicator");

  let lastPayload = null;
  let lastPublishedPrice = null;
  let lastResult = null;

  // ---- helpers ------------------------------------------------------

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

  function formatTimestamp(iso) {
    if (!iso) return "—";
    try {
      const date = new Date(iso);
      if (isNaN(date.getTime())) return iso;
      return new Intl.DateTimeFormat("es-UY", {
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
      }).format(date);
    } catch (_) {
      return iso;
    }
  }

  function setStatus(state, label) {
    if (!statusIndicator) return;
    const dot = statusIndicator.querySelector(".status-dot");
    const text = statusIndicator.querySelector(".status-label");
    if (dot) dot.dataset.state = state;
    if (text) text.textContent = label;
  }

  function setFormStatus(state, message) {
    if (!formStatus) return;
    formStatus.dataset.state = state || "";
    setText(formStatus, message || "");
  }

  function setSubmitBusy(busy) {
    if (!submitBtn) return;
    submitBtn.disabled = busy;
    submitBtn.dataset.state = busy ? "loading" : "";
    submitBtn.setAttribute("aria-busy", busy ? "true" : "false");
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

  // ---- storage ------------------------------------------------------

  function safeStorage() {
    try {
      const test = "__alquileres_uy_probe__";
      window.localStorage.setItem(test, "1");
      window.localStorage.removeItem(test);
      return window.localStorage;
    } catch (_) {
      return null;
    }
  }

  const storage = safeStorage();

  function loadFormValues() {
    if (!storage) return;
    try {
      const raw = storage.getItem(STORAGE_KEYS.form);
      if (!raw) return;
      const values = JSON.parse(raw);
      if (!values || typeof values !== "object") return;
      PERSISTED_FIELDS.forEach((name) => {
        const el = byId(name);
        if (el && typeof values[name] === "string") {
          el.value = values[name];
        }
      });
    } catch (_) {
      // Ignore corrupt payloads — the form will keep its defaults.
    }
  }

  function saveFormValues() {
    if (!storage) return;
    try {
      const values = {};
      PERSISTED_FIELDS.forEach((name) => {
        const el = byId(name);
        if (el) values[name] = el.value;
      });
      storage.setItem(STORAGE_KEYS.form, JSON.stringify(values));
    } catch (_) {
      // Silently ignore quota / permission errors.
    }
  }

  function clearFormValues() {
    if (!storage) return;
    try {
      storage.removeItem(STORAGE_KEYS.form);
    } catch (_) {
      /* ignore */
    }
  }

  // ---- history ------------------------------------------------------

  function loadHistory() {
    if (!storage) return [];
    try {
      const raw = storage.getItem(STORAGE_KEYS.history);
      if (!raw) return [];
      const parsed = JSON.parse(raw);
      if (!Array.isArray(parsed)) return [];
      return parsed.slice(0, HISTORY_LIMIT);
    } catch (_) {
      return [];
    }
  }

  function saveHistory(entries) {
    if (!storage) return;
    try {
      storage.setItem(STORAGE_KEYS.history, JSON.stringify(entries.slice(0, HISTORY_LIMIT)));
    } catch (_) {
      /* ignore */
    }
  }

  function pushHistoryEntry(entry) {
    const entries = loadHistory();
    entries.unshift(entry);
    const trimmed = entries.slice(0, HISTORY_LIMIT);
    saveHistory(trimmed);
    renderHistory();
  }

  function clearHistory() {
    if (!storage) return;
    try {
      storage.removeItem(STORAGE_KEYS.history);
    } catch (_) {
      /* ignore */
    }
    renderHistory();
  }

  function renderHistory() {
    if (!historyList) return;
    const entries = loadHistory();
    historyList.innerHTML = "";
    if (entries.length === 0) {
      if (historyEmpty) historyEmpty.hidden = false;
      if (historyClearBtn) historyClearBtn.hidden = true;
      return;
    }
    if (historyEmpty) historyEmpty.hidden = true;
    if (historyClearBtn) historyClearBtn.hidden = false;

    entries.forEach((entry, index) => {
      const li = document.createElement("li");
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "history-item";
      btn.dataset.index = String(index);

      const header = document.createElement("div");
      header.className = "history-item-header";
      const title = document.createElement("span");
      title.className = "history-item-title";
      title.textContent = entry.neighborhood || "—";
      header.appendChild(title);

      const badge = document.createElement("span");
      badge.className = "history-item-badge";
      badge.dataset.state = entry.state || "success";
      badge.textContent = entry.state === "error" ? "error" : "ok";
      header.appendChild(badge);

      const meta = document.createElement("div");
      meta.className = "history-item-meta";
      const parts = [];
      if (entry.property_type) parts.push(entry.property_type === "house" ? "Casa" : "Apto");
      if (entry.total_area) parts.push(`${entry.total_area} m²`);
      parts.push(formatTimestamp(entry.timestamp));
      meta.textContent = parts.join(" · ");

      const price = document.createElement("div");
      price.className = "history-item-price";
      price.textContent =
        typeof entry.prediction === "number"
          ? formatCurrency(entry.prediction, entry.currency)
          : "—";

      btn.appendChild(header);
      btn.appendChild(price);
      btn.appendChild(meta);
      btn.addEventListener("click", () => replayHistoryEntry(entry));
      li.appendChild(btn);
      historyList.appendChild(li);
    });
  }

  function replayHistoryEntry(entry) {
    if (!entry) return;
    PERSISTED_FIELDS.forEach((name) => {
      const el = byId(name);
      if (!el || entry[name] === undefined || entry[name] === null) return;
      el.value = String(entry[name]);
    });
    saveFormValues();
    setFormStatus("", "Restauramos el formulario desde el historial.");
    hideError();
    const anchor = byId("form-card");
    if (anchor && anchor.scrollIntoView) {
      anchor.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }

  // ---- error messages ----------------------------------------------

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

  // ---- UI validation -----------------------------------------------

  const NUMERIC_FIELDS = {
    bedrooms: { min: 0, max: 20, message: "Ingresá un número entre 0 y 20." },
    bathrooms: { min: 0, max: 10, message: "Ingresá un número entre 0 y 10." },
    total_area: {
      min: 1,
      max: 10000,
      message: "La superficie total debe ser mayor a 0 (m²).",
    },
    covered_area: {
      min: 1,
      max: 10000,
      message: "La superficie cubierta debe ser mayor a 0 (m²).",
    },
    latitude: { min: -90, max: 90, message: "La latitud debe estar entre -90 y 90." },
    longitude: { min: -180, max: 180, message: "La longitud debe estar entre -180 y 180." },
  };

  function clearFieldErrors() {
    PERSISTED_FIELDS.forEach((name) => {
      const errorNode = byId(`${name}-error`);
      if (errorNode) {
        errorNode.hidden = true;
        errorNode.textContent = "";
      }
      const input = byId(name);
      if (input) input.removeAttribute("aria-invalid");
    });
  }

  function reportFieldError(name, message) {
    const errorNode = byId(`${name}-error`);
    if (errorNode) {
      errorNode.textContent = message;
      errorNode.hidden = false;
    }
    const input = byId(name);
    if (input) input.setAttribute("aria-invalid", "true");
  }

  function validateForm() {
    clearFieldErrors();
    const errors = [];
    const neighborhood = byId("neighborhood").value.trim();
    if (!neighborhood) {
      reportFieldError("neighborhood", "Ingresá el barrio de la propiedad.");
      errors.push("neighborhood");
    }
    Object.entries(NUMERIC_FIELDS).forEach(([name, spec]) => {
      const raw = byId(name).value;
      if (raw === "" || raw === null || raw === undefined) {
        reportFieldError(name, "Este campo es obligatorio.");
        errors.push(name);
        return;
      }
      const value = Number(raw);
      if (!isFinite(value) || value < spec.min || value > spec.max) {
        reportFieldError(name, spec.message);
        errors.push(name);
      }
    });
    // Cross-field sanity checks.
    const coveredArea = Number(byId("covered_area").value);
    const totalArea = Number(byId("total_area").value);
    if (
      isFinite(coveredArea) &&
      isFinite(totalArea) &&
      coveredArea > 0 &&
      totalArea > 0 &&
      coveredArea > totalArea
    ) {
      reportFieldError(
        "covered_area",
        "La superficie cubierta no puede superar la superficie total."
      );
      errors.push("covered_area");
    }
    const priceRaw = byId("price").value;
    if (priceRaw !== "") {
      const priceValue = Number(priceRaw);
      if (!isFinite(priceValue) || priceValue < 0) {
        reportFieldError("price", "El precio publicado no puede ser negativo.");
        errors.push("price");
      }
    }
    return errors;
  }

  // ---- comparison logic --------------------------------------------

  function classifyComparison(publishedPrice, estimatedPrice) {
    if (!publishedPrice || publishedPrice <= 0) return null;
    const diffAbs = publishedPrice - estimatedPrice;
    const diffPct = (diffAbs / estimatedPrice) * 100;
    let state;
    let label;
    let interpretation;
    if (diffPct <= -5) {
      state = "below";
      label = "🟢 debajo del valor estimado";
      interpretation =
        "El precio publicado está por debajo de lo que estimamos — buena oportunidad si el estado real coincide con lo declarado.";
    } else if (diffPct <= 10) {
      state = "near";
      label = "🟡 cercano al valor estimado";
      interpretation =
        "El precio publicado está en línea con nuestra estimación — dentro del margen habitual del mercado.";
    } else {
      state = "over";
      label = "🔴 muy por encima del valor estimado";
      interpretation =
        "El precio publicado supera nuestra estimación — vale la pena revisar comparables antes de negociar.";
    }
    return { diffAbs, diffPct, state, label, interpretation };
  }

  function updateComparisonBar(diffPct) {
    const marker = byId("comparison-bar-marker");
    if (!marker) return;
    // Map the diff percent to a 0–100 % scale, clamped to [-20, +20].
    const clamped = Math.max(-20, Math.min(20, diffPct));
    const percentInBar = ((clamped + 20) / 40) * 100;
    marker.style.left = `${percentInBar}%`;
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
    if (event) event.preventDefault();
    const errors = validateForm();
    if (errors.length > 0) {
      setFormStatus("error", "Revisá los campos marcados en rojo antes de enviar.");
      const firstErrorField = byId(errors[0]);
      if (firstErrorField && firstErrorField.focus) firstErrorField.focus();
      return;
    }
    hideError();
    hideResult();
    setSubmitBusy(true);
    setFormStatus("loading", "Calculando estimación…");

    const { payload, publishedPrice } = collectPayload();
    lastPayload = payload;
    lastPublishedPrice = publishedPrice;

    let response;
    let body = null;
    try {
      response = await fetch(ENDPOINTS.predict, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify(payload),
      });
    } catch (_) {
      setSubmitBusy(false);
      setFormStatus("error", "No pudimos conectar con la API.");
      showError(humanReadableError(0, null));
      pushHistoryEntry(buildHistoryEntry({ state: "error" }));
      return;
    }
    try {
      body = await response.json();
    } catch (_) {
      body = null;
    }
    setSubmitBusy(false);

    if (!response.ok) {
      setFormStatus("error", "El servicio no pudo calcular el precio.");
      showError(humanReadableError(response.status, body));
      pushHistoryEntry(buildHistoryEntry({ state: "error" }));
      return;
    }
    setFormStatus("success", "Listo — mostramos el resultado abajo.");
    lastResult = body;
    renderResult(body, publishedPrice);
    pushHistoryEntry(
      buildHistoryEntry({
        state: "success",
        prediction: body.prediction,
        currency: body.currency,
        timestamp: body.prediction_timestamp,
      })
    );
  }

  function buildHistoryEntry(extras) {
    const values = {};
    PERSISTED_FIELDS.forEach((name) => {
      const el = byId(name);
      if (el) values[name] = el.value;
    });
    return {
      neighborhood: values.neighborhood || "—",
      property_type: values.property_type,
      total_area: values.total_area,
      timestamp: extras.timestamp || new Date().toISOString(),
      prediction: typeof extras.prediction === "number" ? extras.prediction : null,
      currency: extras.currency || "USD",
      state: extras.state || "success",
    };
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
      setText(byId("comparison-interpretation"), comparison.interpretation);
      setText(byId("comparison-published"), formatCurrency(publishedPrice, body.currency));
      setText(byId("comparison-estimated"), formatCurrency(body.prediction, body.currency));
      setText(byId("diff-absolute"), formatCurrency(comparison.diffAbs, body.currency));
      setText(byId("diff-percent"), `${comparison.diffPct.toFixed(1)} %`);
      updateComparisonBar(comparison.diffPct);
    } else {
      comparisonCard.hidden = true;
    }

    resultCard.hidden = false;
    resultCard.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  // ---- retry --------------------------------------------------------

  async function retryPrediction() {
    if (!lastPayload) {
      hideError();
      return;
    }
    hideError();
    setSubmitBusy(true);
    setFormStatus("retrying", "Reintentando la predicción…");
    let response;
    let body = null;
    try {
      response = await fetch(ENDPOINTS.predict, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify(lastPayload),
      });
    } catch (_) {
      setSubmitBusy(false);
      setFormStatus("error", "Seguimos sin conexión con la API.");
      showError(humanReadableError(0, null));
      return;
    }
    try {
      body = await response.json();
    } catch (_) {
      body = null;
    }
    setSubmitBusy(false);
    if (!response.ok) {
      setFormStatus("error", "El servicio sigue devolviendo un error.");
      showError(humanReadableError(response.status, body));
      return;
    }
    setFormStatus("success", "Listo — mostramos el resultado abajo.");
    lastResult = body;
    renderResult(body, lastPublishedPrice);
  }

  // ---- copy result --------------------------------------------------

  async function copyResult() {
    if (!lastResult || !copyResultBtn) return;
    const lines = [
      `Precio estimado: ${formatCurrency(lastResult.prediction, lastResult.currency)}`,
      `Modelo: ${lastResult.model_type || "—"}`,
      `Versión: ${lastResult.model_version || "—"}`,
      `Timestamp: ${lastResult.prediction_timestamp || "—"}`,
    ];
    const text = lines.join("\n");
    let ok = false;
    if (navigator.clipboard && navigator.clipboard.writeText) {
      try {
        await navigator.clipboard.writeText(text);
        ok = true;
      } catch (_) {
        ok = false;
      }
    }
    if (!ok) {
      try {
        const textarea = document.createElement("textarea");
        textarea.value = text;
        textarea.setAttribute("readonly", "");
        textarea.style.position = "absolute";
        textarea.style.left = "-9999px";
        document.body.appendChild(textarea);
        textarea.select();
        ok = document.execCommand("copy");
        document.body.removeChild(textarea);
      } catch (_) {
        ok = false;
      }
    }
    if (copyFeedback) {
      copyFeedback.hidden = false;
      copyFeedback.textContent = ok ? "Copiado ✓" : "No pudimos copiar";
      setTimeout(() => {
        copyFeedback.hidden = true;
      }, 2000);
    }
  }

  // ---- example ------------------------------------------------------

  function loadExample() {
    Object.entries(EXAMPLE_VALUES).forEach(([name, value]) => {
      const el = byId(name);
      if (el) el.value = value;
    });
    saveFormValues();
    clearFieldErrors();
    setFormStatus("", "Cargamos un ejemplo — revisá los datos y calculá cuando quieras.");
  }

  // ---- model info (from /version) ----------------------------------

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
      // Silent: the header status indicator already reflects reachability.
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
    loadFormValues();
    renderHistory();
    if (form) {
      form.addEventListener("submit", submitPrediction);
      // Save on every change so a page reload / crash preserves the input.
      form.addEventListener("input", saveFormValues);
      form.addEventListener("change", saveFormValues);
    }
    if (resetBtn) {
      resetBtn.addEventListener("click", () => {
        clearFormValues();
        clearFieldErrors();
        setFormStatus("", "");
        hideError();
        hideResult();
      });
    }
    if (loadExampleBtn) loadExampleBtn.addEventListener("click", loadExample);
    if (copyResultBtn) copyResultBtn.addEventListener("click", copyResult);
    if (retryBtn) retryBtn.addEventListener("click", retryPrediction);
    if (historyClearBtn) historyClearBtn.addEventListener("click", clearHistory);
    if (errorDismiss) errorDismiss.addEventListener("click", hideError);
    loadModelInfo();
    refreshStatus();
    setInterval(refreshStatus, 30000);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bootstrap);
  } else {
    bootstrap();
  }
})();
