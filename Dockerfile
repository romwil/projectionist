FROM node:20-alpine AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install
COPY frontend/ ./
# PrivacyPage / HelpPage import @docs/*.md (alias → /docs in this stage)
COPY docs/PRIVACY.md /docs/PRIVACY.md
COPY docs/HELP.md /docs/HELP.md
# release-notes.json is generated on the host by docker-release.sh / generate-release-notes.sh
# before build; Vite copies public/ into dist. Fail fast if missing so About / What's New work.
RUN test -f public/release-notes.json \
  || (echo "frontend/public/release-notes.json missing — run scripts/generate-release-notes.sh" >&2 && exit 1)
RUN npm run build

FROM python:3.12-slim

# Build-time identity (passed by scripts/docker-release.sh). These must land in
# LABEL + a file layer so every release has a unique image config digest.
ARG CURATORX_VERSION=dev
ARG BUILD_DATE=unknown
ARG VCS_REF=unknown

LABEL org.opencontainers.image.title="CuratorX" \
      org.opencontainers.image.description="Chat-first Plex collection curator for self-hosted homelabs" \
      org.opencontainers.image.version="${CURATORX_VERSION}" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.source="https://github.com/romwil/curatorx" \
      org.opencontainers.image.licenses="MIT"

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates gosu \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md LICENSE ./
COPY curatorx ./curatorx
COPY --from=frontend /frontend/dist ./frontend/dist

# File-level cache bust: guarantees layer content differs every release even when
# only labels would change. Does NOT make Unraid Force Update pull by itself —
# Dockerman still depends on Docker Engine re-resolving the tag (see docs/DOCKER.md).
RUN echo "${CURATORX_VERSION} built ${BUILD_DATE} rev ${VCS_REF}" > /app/.build-info

RUN pip install --no-cache-dir ".[web,mcp]"

# Non-root user (security finding S13). UID/GID 1000 — entrypoint script
# auto-chowns /config and drops to this user via gosu.
RUN addgroup --system --gid 1000 curatorx \
    && adduser --system --uid 1000 --ingroup curatorx curatorx \
    && mkdir -p /config && chown curatorx:curatorx /config

ENV DATA_DIR=/config
ENV PORT=8788

EXPOSE 8788

VOLUME ["/config"]

COPY scripts/docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8788/api/health')" || exit 1

ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["python", "-m", "curatorx.web"]
