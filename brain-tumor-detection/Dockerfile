# BrainScan AI — brain tumor detection (Flask + PyTorch)
#
# Build:  docker build -t brainscan-ai .
# Run:    docker run --rm -p 5000:5000 -v "$PWD/data:/app/data" brainscan-ai
#
# The model checkpoint is expected at /app/data/models/model.pt — mount your
# `data/` directory (or a named volume) so the image stays small and stateless.

FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TORCH_HOME=/tmp/torch

WORKDIR /app

# System packages needed by Pillow/scipy wheels is minimal; curl is for healthchecks.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-prod.txt ./
# CPU-only PyTorch keeps the image ~1.5 GB smaller than the CUDA build.
RUN pip install --index-url https://download.pytorch.org/whl/cpu torch torchvision \
    && pip install -r requirements.txt -r requirements-prod.txt

COPY app/ ./app/
COPY training/ ./training/
COPY static/ ./static/
COPY templates/ ./templates/
COPY run.py wsgi.py ./

# Non-root user
RUN useradd --create-home --uid 10001 brainscan \
    && mkdir -p /app/data/models /app/data/uploads \
    && chown -R brainscan:brainscan /app
USER brainscan

ENV BTD_HOST=0.0.0.0 \
    BTD_PORT=5000 \
    BTD_ENV=production \
    BTD_DATA_DIR=/app/data \
    BTD_MODEL_DIR=/app/data/models \
    BTD_DB_PATH=/app/data/history.db \
    BTD_LOG_LEVEL=INFO

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:5000/api/health || exit 1

# One worker per core is a good start; each worker holds its own copy of the model.
CMD ["gunicorn", "-w", "2", "-b", "0.0.0.0:5000", "--timeout", "120", "--access-logfile", "-", "wsgi:app"]
