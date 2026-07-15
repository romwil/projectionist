#!/bin/sh
set -e

# If running as root (normal Docker), fix /config ownership and drop privileges.
# This handles existing installs where /config was owned by root from pre-1.7.3
# containers that used USER root.
if [ "$(id -u)" = "0" ]; then
    chown -R curatorx:curatorx /config
    exec gosu curatorx "$@"
fi

# Already non-root (e.g. Kubernetes with runAsUser) — run directly
exec "$@"
