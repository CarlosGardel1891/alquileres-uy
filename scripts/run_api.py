"""Run the prediction API with uvicorn.

Every runtime knob is read from :class:`ApiSettings` (env-driven) so
the container can be tuned without editing code.
"""

from __future__ import annotations

import uvicorn

from alquileres_uy.api.dependencies import get_settings


def main() -> None:
    settings = get_settings()
    uvicorn.run(
        "alquileres_uy.api.app:create_app",
        factory=True,
        host=settings.HOST,
        port=settings.PORT,
        log_level=settings.LOG_LEVEL.lower(),
        workers=settings.MAX_WORKERS,
        timeout_keep_alive=settings.REQUEST_TIMEOUT,
    )


if __name__ == "__main__":
    main()
