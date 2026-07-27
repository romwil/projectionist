#!/bin/sh
set -e

# If running as root (normal Docker), fix /config ownership when needed and drop privileges.
# This handles existing installs where /config was owned by root from pre-1.7.3
# containers that used USER root. UID/GID stay 1000 across the curatorx→projectionist
# username rename so bind-mounted appdata ownership remains valid.
#
# H7: skip recursive chown when /config is already UID/GID 1000 — unconditional
# chown -R on every start delays Unraid Force Update / recreate for large DBs.
if [ "$(id -u)" = "0" ]; then
    cfg_uid="$(stat -c '%u' /config 2>/dev/null || echo 0)"
    cfg_gid="$(stat -c '%g' /config 2>/dev/null || echo 0)"
    if [ "$cfg_uid" != "1000" ] || [ "$cfg_gid" != "1000" ]; then
        chown -R projectionist:projectionist /config
    fi
    exec gosu projectionist "$@"
fi

# Already non-root (e.g. Kubernetes with runAsUser) — run directly
exec "$@"
