# BISense: one image, one process (FastAPI serves the API and the built web app).
#
#   docker build -t bisense .
#   docker run -p 8000:8000 --env-file .env -v "$PWD/data:/app/data" bisense
#
# The index is built at container start from the mounted ./data (Tier A PDFs you supply privately,
# Tier B pages, the Tier C demo pack). Never bake copyrighted standards into a public image.

# ---- 1. build the web app ------------------------------------------------------------------------
FROM node:22-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

# ---- 2. python runtime -----------------------------------------------------------------------------
FROM python:3.12-slim AS runtime
ENV PYTHONUNBUFFERED=1 PYTHONIOENCODING=utf-8 PIP_NO_CACHE_DIR=1 \
    HOST=0.0.0.0 PORT=8000 APP_ENV=production DATA_DIR=/app/data MODEL_CACHE_DIR=/app/models
WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
COPY server/pyproject.toml server/uv.lock server/.python-version ./server/
RUN cd server && uv sync --frozen --no-dev --no-install-project
COPY server/ ./server/
RUN cd server && uv sync --frozen --no-dev
COPY --from=web /web/dist ./web/dist
COPY data/demo ./seed/demo
COPY data/public_sources.yaml data/sources.yaml ./seed/
# Pre-download the ONNX models at build time so the container works offline.
RUN cd server && uv run --no-dev bisense models
RUN useradd -m bisense && mkdir -p /app/data && chown -R bisense /app
USER bisense
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s CMD python -c "import urllib.request,os;urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",\"8000\")}/api/health')"
# Seed the demo pack if the mounted data folder is empty, (re)build the index, then serve.
CMD sh -c "mkdir -p $DATA_DIR && [ -d $DATA_DIR/demo ] || cp -r /app/seed/demo /app/seed/*.yaml $DATA_DIR/ ; cd server && uv run --no-dev bisense ingest && uv run --no-dev uvicorn bisense.main:app --host $HOST --port $PORT"
