#!/bin/sh
set -e

# If running as root (normal Docker), fix /config ownership and drop privileges.
# This handles existing installs where /config was owned by root from pre-1.7.3
# containers that used USER root. UID/GID stay 1000 across the curatorx→projectionist
# username rename so bind-mounted appdata ownership remains valid.
if [ "$(id -u)" = "0" ]; then
    chown -R projectionist:projectionist /config
    exec gosu projectionist "$@"
fi

# Already non-root (e.g. Kubernetes with runAsUser) — run directly
exec "$@"
