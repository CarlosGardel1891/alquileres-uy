# syntax=docker/dockerfile:1.7
#
# alquileres-uy — production API image.
#
# * Python 3.12 slim base — matches the pins in requirements-api.txt.
# * Only the API dependencies are installed (no ingest, ETL, torch or
#   training toolchain).
# * The serving bundle is copied from the build context so a downstream
#   consumer can build a specific model into the image without runtime
#   downloads. Point the container at another bundle by mounting a
#   volume + ALQUILERES_API_MODEL_BUNDLE_PATH.
FROM python:3.12-slim AS runtime

# APP_VERSION is passed in by the release workflow / release-check job
# so the wheel version, the OCI label and the /build endpoint all agree.
# When building locally you can override with:
#   docker build --build-arg APP_VERSION=$(python -c "import alquileres_uy;print(alquileres_uy.__version__)") .
ARG APP_VERSION=0.10.0

LABEL org.opencontainers.image.version="${APP_VERSION}" \
      org.opencontainers.image.source="https://github.com/CarlosGardel1891/alquileres-uy" \
      org.opencontainers.image.description="alquileres-uy — rental price prediction API for Montevideo" \
      org.opencontainers.image.licenses="MIT"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    ALQUILERES_API_HOST=0.0.0.0 \
    ALQUILERES_API_PORT=8000 \
    ALQUILERES_API_LOG_LEVEL=INFO \
    ALQUILERES_API_MODEL_BUNDLE_PATH=/app/artifacts/serving_bundle

WORKDIR /app

# Install runtime deps first so the layer is cacheable across code edits.
COPY requirements-api.txt ./requirements-api.txt
RUN python -m pip install --upgrade pip \
    && pip install --no-cache-dir -r requirements-api.txt

# Copy the project source + entrypoint script.
COPY pyproject.toml README.md ./
COPY src/ ./src/
COPY scripts/run_api.py ./scripts/run_api.py
COPY scripts/generate_build_info.py ./scripts/generate_build_info.py

# Copy the serving bundle (may be an empty placeholder during CI builds).
COPY artifacts/models/ ./artifacts/models/

# Regenerate build_info.json inside the image so ``git_commit`` reflects
# whatever the build context was (may be "unknown" for tarball builds
# without a .git directory — that is intentional).
RUN python scripts/generate_build_info.py

# Install the project itself so the module resolver finds alquileres_uy.
RUN pip install --no-cache-dir .

EXPOSE 8000

# Run uvicorn via the project entrypoint. The script reads HOST / PORT /
# LOG_LEVEL / MAX_WORKERS / REQUEST_TIMEOUT from the environment.
CMD ["python", "scripts/run_api.py"]
