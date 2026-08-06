"""Run the prediction API with uvicorn.

At this stage the script only wires ``uvicorn`` to
``alquileres_uy.api.app:create_app``. No workers, no reload logic, no
gunicorn. Additional runtime knobs will be introduced in later
subphases together with the model loader.
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
    )


if __name__ == "__main__":
    main()
