# syntax=docker/dockerfile:1
# BuildKit required for --mount=type=cache (default on Docker 23+ / buildx).
# Older engines: DOCKER_BUILDKIT=1 docker build ...
# Hub releases use scripts/docker-release.sh (buildx — always BuildKit).
#
# Before building, run ./scripts/docker-dep-manifests.sh (docker-release.sh does).
# That writes .docker-deps/ with the version pinned to 0.0.0 so a patch bump
# does not reinstall npm or pip dependencies.

# Frontend is TypeScript. Build it once on the builder's own architecture.
# Hub `npm run build` is `tsc --noEmit && vite build` — tsconfig.json must be
# in this stage or tsc prints usage and the image never ships.
# A multi-arch release otherwise runs Vite under QEMU for amd64, where esbuild
# either crawls or dies ("The service was stopped"). The runtime stages still
# follow the target platform so wheels and ffmpeg match the image.
FROM --platform=$BUILDPLATFORM node:20-alpine AS frontend
WORKDIR /frontend

# Dependency manifests first — npm layer stays warm when only app source or
# the release version changes. Real package.json is not copied here on purpose.
COPY .docker-deps/frontend/package.json .docker-deps/frontend/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm \
    npm ci

COPY frontend/index.html frontend/vite.config.js frontend/tsconfig.json ./
COPY frontend/src ./src
COPY frontend/public/favicon.svg ./public/favicon.svg
# PrivacyPage / HelpPage import @docs/*.md (alias → /docs in this stage)
COPY docs/PRIVACY.md /docs/PRIVACY.md
COPY docs/HELP.md /docs/HELP.md
RUN --mount=type=cache,target=/frontend/node_modules/.vite \
    npm run build

# release-notes.json is generated on the host by docker-release.sh /
# generate-release-notes.sh before build. Copied after Vite so a notes-only
# change does not rebuild the SPA. Fail fast if missing.
COPY frontend/public/release-notes.json ./dist/release-notes.json

FROM python:3.12-slim

WORKDIR /app

# Investigate stills / Identify clips: Debian `ffmpeg` ships ffmpeg + ffprobe
# on PATH for the app user. Override with FFMPEG_PATH / FFPROBE_PATH.
# Early RUN (before any COPY) so app edits never bust this layer. Cache mounts
# keep .debs/lists across rebuilds when the slim FROM line does change.
# slim images delete downloaded packages unless docker-clean is removed.
RUN rm -f /etc/apt/apt.conf.d/docker-clean \
    && echo 'Binary::apt::APT::Keep-Downloaded-Packages "true";' > /etc/apt/apt.conf.d/keep-cache
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates gosu ffmpeg

# Install Python deps from manifests only (stub package). Real sources come next so
# app edits do not re-download wheels. Version ARG/LABEL intentionally come AFTER
# this layer — otherwise every release would bust pip. The manifests in
# .docker-deps/ also drop the patch version and the README badge, which change
# every release and used to invalidate this layer.
COPY .docker-deps/pyproject.toml .docker-deps/README.md .docker-deps/LICENSE ./
RUN mkdir -p projectionist && printf '# build stub\n' > projectionist/__init__.py
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install ".[web,mcp]"

# Real metadata (version badge, license text) after wheels are installed.
COPY pyproject.toml README.md LICENSE ./

# Real package tree; --no-deps keeps the warm wheel layer when only sources change.
COPY projectionist ./projectionist
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-deps --force-reinstall .

COPY --from=frontend /frontend/dist ./frontend/dist

# Non-root user (security finding S13). UID/GID 1000 — entrypoint script
# auto-chowns /config and drops to this user via gosu.
RUN addgroup --system --gid 1000 projectionist \
    && adduser --system --uid 1000 --ingroup projectionist projectionist \
    && mkdir -p /config && chown projectionist:projectionist /config

ENV DATA_DIR=/config
ENV PORT=8788
ENV PROJECTIONIST_THEATER_PORT=8791

EXPOSE 8788 8791

VOLUME ["/config"]

COPY scripts/docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

# Build-time identity (passed by scripts/docker-release.sh). Declared late so
# version / date / VCS bumps do not invalidate apt or pip layers.
# PROJECTIONIST_VERSION is canonical; CURATORX_VERSION remains an alias for one release.
ARG PROJECTIONIST_VERSION=dev
ARG CURATORX_VERSION=
ARG BUILD_DATE=unknown
ARG VCS_REF=unknown

LABEL org.opencontainers.image.title="Projectionist" \
      org.opencontainers.image.description="Cinema intelligence for your personal archive" \
      org.opencontainers.image.version="${PROJECTIONIST_VERSION}" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.source="https://github.com/romwil/projectionist" \
      org.opencontainers.image.licenses="AGPL-3.0-only"

# File-level cache bust for release uniqueness (labels alone are not enough for
# some consumers). Does NOT make Unraid Force Update pull by itself — Dockerman
# still depends on Docker Engine re-resolving the tag (see docs/DOCKER.md).
RUN VERSION="${PROJECTIONIST_VERSION}"; \
    if [ "$VERSION" = "dev" ] && [ -n "$CURATORX_VERSION" ]; then VERSION="$CURATORX_VERSION"; fi; \
    echo "${VERSION} built ${BUILD_DATE} rev ${VCS_REF}" > /app/.build-info

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8788/api/health')" || exit 1

ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["python", "-m", "projectionist.web"]
