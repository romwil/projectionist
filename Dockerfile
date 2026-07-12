FROM node:20-alpine AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim

LABEL org.opencontainers.image.title="CuratorX" \
      org.opencontainers.image.description="Chat-first Plex collection curator for self-hosted homelabs" \
      org.opencontainers.image.version="1.0.4" \
      org.opencontainers.image.source="https://github.com/romwil/curatorx" \
      org.opencontainers.image.licenses="MIT"

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md LICENSE ./
COPY curatorx ./curatorx
COPY --from=frontend /frontend/dist ./frontend/dist

RUN pip install --no-cache-dir ".[web]"

ENV DATA_DIR=/config
ENV PORT=8788

EXPOSE 8788

VOLUME ["/config"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8788/api/health')" || exit 1

CMD ["python", "-m", "curatorx.web"]
