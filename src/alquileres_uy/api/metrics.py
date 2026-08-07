"""Prometheus instrumentation for the prediction API.

All collectors live on a dedicated :class:`CollectorRegistry` so tests
can reset them and so we never collide with any other library that
registers on the default global registry. The public helpers
(``record_request``, ``set_model_loaded``, ``render_latest``) keep the
middleware and the endpoint free of prometheus-client boilerplate.

Available metrics:

* ``prediction_requests_total`` — Counter labelled by ``endpoint``,
  ``method`` and ``status_code``. Increments on every completed request.
* ``prediction_errors_total`` — Counter labelled by ``endpoint``,
  ``method`` and ``status_code``. Increments only when ``status_code``
  is ``>= 500`` (or when the middleware catches an exception before a
  status is set).
* ``prediction_latency_seconds`` — Histogram labelled by ``endpoint``
  and ``method``. Observes wall-clock duration of each request.
* ``model_loaded`` — Gauge (no labels). Set to 1 by the lifespan when
  the serving bundle is loaded, back to 0 on shutdown or when the
  loader fails.
"""

from __future__ import annotations

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

# Dedicated registry — never touches the default REGISTRY.
REGISTRY: CollectorRegistry = CollectorRegistry(auto_describe=True)

prediction_requests_total: Counter = Counter(
    "prediction_requests_total",
    "Total number of API requests received, labelled by endpoint / method / status.",
    labelnames=("endpoint", "method", "status_code"),
    registry=REGISTRY,
)

prediction_errors_total: Counter = Counter(
    "prediction_errors_total",
    "Total number of API requests that ended in a 5xx response.",
    labelnames=("endpoint", "method", "status_code"),
    registry=REGISTRY,
)

prediction_latency_seconds: Histogram = Histogram(
    "prediction_latency_seconds",
    "Request duration in seconds, labelled by endpoint / method.",
    labelnames=("endpoint", "method"),
    registry=REGISTRY,
    buckets=(
        0.005,
        0.01,
        0.025,
        0.05,
        0.1,
        0.25,
        0.5,
        1.0,
        2.5,
        5.0,
        10.0,
    ),
)

model_loaded: Gauge = Gauge(
    "model_loaded",
    "1 when the serving bundle is loaded and ready, 0 otherwise.",
    registry=REGISTRY,
)


def record_request(
    *,
    endpoint: str,
    method: str,
    status_code: int,
    duration_seconds: float,
) -> None:
    """Update the counters + histogram for one completed request."""
    method_norm = method.upper()
    status_str = str(status_code)
    prediction_requests_total.labels(
        endpoint=endpoint, method=method_norm, status_code=status_str
    ).inc()
    if status_code >= 500:
        prediction_errors_total.labels(
            endpoint=endpoint, method=method_norm, status_code=status_str
        ).inc()
    prediction_latency_seconds.labels(endpoint=endpoint, method=method_norm).observe(
        duration_seconds
    )


def set_model_loaded(is_loaded: bool) -> None:
    model_loaded.set(1.0 if is_loaded else 0.0)


def render_latest() -> tuple[bytes, str]:
    """Return ``(body, content_type)`` for the Prometheus exposition."""
    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST


def reset_for_tests() -> None:
    """Reset every collector. Test-only helper — never call in production."""
    # prometheus_client does not expose a public reset API, but the
    # internal metric families each keep an ``_metrics`` dict of
    # per-label children with ``_value``s we can zero.
    for collector in (prediction_requests_total, prediction_errors_total):
        collector._metrics.clear()  # type: ignore[attr-defined]
    prediction_latency_seconds._metrics.clear()  # type: ignore[attr-defined]
    model_loaded.set(0.0)


__all__ = [
    "REGISTRY",
    "model_loaded",
    "prediction_errors_total",
    "prediction_latency_seconds",
    "prediction_requests_total",
    "record_request",
    "render_latest",
    "reset_for_tests",
    "set_model_loaded",
]
