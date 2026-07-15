FROM node:20-alpine AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install
COPY frontend/ ./
# PrivacyPage imports @docs/PRIVACY.md (alias → /docs in this stage)
COPY docs/PRIVACY.md /docs/PRIVACY.md
RUN npm run build

FROM python:3.12-slim

LABEL org.opencontainers.image.title="CuratorX" \
      org.opencontainers.image.description="Chat-first Plex collection curator for self-hosted homelabs" \
      org.opencontainers.image.version="1.3.0" \
      org.opencontainers.image.source="https://github.com/romwil/curatorx" \
      org.opencontainers.image.licenses="MIT"

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md LICENSE ./
COPY curatorx ./curatorx
COPY --from=frontend /frontend/dist ./frontend/dist

RUN pip install --no-cache-dir ".[web,mcp]"

# Non-root user (security finding S13). UID/GID 1000 — bind-mount volumes
# for /config should be owned by 1000:1000 or world-writable.
RUN addgroup --system --gid 1000 curatorx \
    && adduser --system --uid 1000 --ingroup curatorx curatorx \
    && mkdir -p /config && chown curatorx:curatorx /config

ENV DATA_DIR=/config
ENV PORT=8788

EXPOSE 8788

VOLUME ["/config"]

USER curatorx

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8788/api/health')" || exit 1

CMD ["python", "-m", "curatorx.web"]
