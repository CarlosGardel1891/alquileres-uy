"""Runtime reliability layer around the raw :class:`Predictor`.

Adds three orthogonal concerns without touching the Predictor itself:

* **Concurrency limit** — an ``asyncio.Semaphore`` caps how many
  predictions may run at the same time (``MAX_CONCURRENT_PREDICTIONS``).
  Callers over the cap wait — they are never rejected. The semaphore
  is released in ``finally`` so an exception cannot leak a permit.
* **Per-request timeout** — ``asyncio.timeout`` bounds each call. The
  underlying ``predict`` runs on ``asyncio.to_thread`` so a cancelled
  wait actually returns control immediately (the pure-python model
  cannot be interrupted mid-work, but the coroutine wakes up and the
  client sees a 503 instead of hanging).
* **Graceful shutdown** — ``begin_shutdown`` flips a flag and
  ``wait_for_drain`` awaits the in-flight counter reaching zero. New
  predictions requested after shutdown started raise
  :class:`ServiceShuttingDownError` (HTTP 503). Predictions already
  in flight are never cancelled.

The service is stateful (shared across requests) so the lifespan
instantiates one and stashes it on ``app.state.prediction_service``.
"""

from __future__ import annotations

import asyncio
import contextlib

from .logging_config import get_logger
from .schemas.predict import PredictRequest
from .services.predictor import PredictionResult, Predictor


class PredictionTimeoutError(RuntimeError):
    """Raised when a single prediction exceeds ``PREDICT_TIMEOUT``."""


class ServiceShuttingDownError(RuntimeError):
    """Raised when a prediction is requested after graceful shutdown started."""


class PredictionService:
    """Concurrency + timeout + shutdown wrapper around a :class:`Predictor`."""

    def __init__(
        self,
        predictor: Predictor,
        *,
        max_concurrent: int,
        timeout_seconds: float,
    ) -> None:
        if max_concurrent < 1:
            raise ValueError("max_concurrent must be >= 1")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be > 0")
        self._predictor = predictor
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._timeout = float(timeout_seconds)
        self._in_flight = 0
        self._in_flight_lock = asyncio.Lock()
        self._all_done = asyncio.Event()
        self._all_done.set()  # initial state: nothing in flight
        self._shutting_down = False
        self._logger = get_logger()

    # ---- introspection ------------------------------------------------

    @property
    def predictor(self) -> Predictor:
        return self._predictor

    @property
    def max_concurrent(self) -> int:
        return self._semaphore._value + self._in_flight  # type: ignore[attr-defined]

    @property
    def timeout_seconds(self) -> float:
        return self._timeout

    @property
    def in_flight(self) -> int:
        return self._in_flight

    @property
    def is_shutting_down(self) -> bool:
        return self._shutting_down

    # ---- prediction path ---------------------------------------------

    async def predict(self, request: PredictRequest) -> PredictionResult:
        if self._shutting_down:
            raise ServiceShuttingDownError("service is shutting down")

        async with self._semaphore:
            if self._shutting_down:
                # Racy shutdown: refuse now that we hold a permit.
                raise ServiceShuttingDownError("service is shutting down")
            await self._enter()
            try:
                return await self._run_with_timeout(request)
            finally:
                await self._exit()

    async def _run_with_timeout(self, request: PredictRequest) -> PredictionResult:
        try:
            async with asyncio.timeout(self._timeout):
                return await asyncio.to_thread(self._predictor.predict, request)
        except TimeoutError as exc:
            self._logger.warning("prediction timeout | timeout_s=%.2f", self._timeout)
            raise PredictionTimeoutError("prediction timed out") from exc

    async def _enter(self) -> None:
        async with self._in_flight_lock:
            self._in_flight += 1
            self._all_done.clear()

    async def _exit(self) -> None:
        async with self._in_flight_lock:
            self._in_flight -= 1
            if self._in_flight == 0:
                self._all_done.set()

    # ---- graceful shutdown -------------------------------------------

    def begin_shutdown(self) -> None:
        """Flag the service so new predictions are refused."""
        self._shutting_down = True
        self._logger.info("shutdown waiting | in_flight=%d", self._in_flight)

    async def wait_for_drain(self, *, timeout: float | None = None) -> None:
        """Await in-flight predictions to finish (never cancels them)."""
        if self._in_flight == 0:
            self._logger.info("shutdown completed | in_flight=0")
            return
        try:
            if timeout is None:
                await self._all_done.wait()
            else:
                async with asyncio.timeout(timeout):
                    await self._all_done.wait()
        except TimeoutError:
            self._logger.warning("shutdown drain timeout | still_in_flight=%d", self._in_flight)
            return
        self._logger.info("shutdown completed | in_flight=0")


@contextlib.asynccontextmanager
async def prediction_service_lifecycle(service: PredictionService, *, drain_timeout: float):
    """Context manager helper for tests + lifespan."""
    try:
        yield service
    finally:
        service.begin_shutdown()
        await service.wait_for_drain(timeout=drain_timeout)


__all__ = [
    "PredictionService",
    "PredictionTimeoutError",
    "ServiceShuttingDownError",
    "prediction_service_lifecycle",
]
