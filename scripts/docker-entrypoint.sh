#!/bin/sh
set -e

# If running as root (normal Docker), fix /config ownership when needed and drop privileges.
# This handles existing installs where /config was owned by root from pre-1.7.3
# containers that used USER root. UID/GID stay 1000 across the curatorx→projectionist
# username rename so bind-mounted appdata ownership remains valid.
#
# H7: skip recursive chown when /config is already UID/GID 1000 — unconditional
# chown -R on every start delays Unraid Force Update / recreate for large DBs.
#
# Do not create a database file here. sqlite3.connect (and the sqlite3 CLI)
# on a missing path creates a 0-byte file before any migration write. docker
# exec runs as root and does not pass through this script, which is how a
# root-owned empty projectionist.db appeared beside the real curatorx.db.
# When /config is already uid 1000 the chown below does not run, so that
# empty file stays root:root mode 644 and the app user cannot write it.
# Startup skips an empty or invalid candidate. It does not delete it.
if [ "$(id -u)" = "0" ]; then
    if [ -f /config/projectionist.db ]; then
        db_size="$(stat -c '%s' /config/projectionist.db 2>/dev/null || echo 0)"
        if [ "$db_size" = "0" ]; then
            echo "projectionist: /config/projectionist.db is empty; leaving it in place and not using it" >&2
        fi
    fi
    cfg_uid="$(stat -c '%u' /config 2>/dev/null || echo 0)"
    cfg_gid="$(stat -c '%g' /config 2>/dev/null || echo 0)"
    if [ "$cfg_uid" != "1000" ] || [ "$cfg_gid" != "1000" ]; then
        chown -R projectionist:projectionist /config
    fi
    exec gosu projectionist "$@"
fi

# Already non-root (e.g. Kubernetes with runAsUser) — run directly
exec "$@"
