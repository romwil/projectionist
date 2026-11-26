#!/bin/sh
set -e

# If running as root (normal Docker), fix /config ownership when needed and drop privileges.
# This handles existing installs where /config was owned by root from pre-1.7.3
# containers that used USER root. UID/GID stay 1000 across the curatorx→projectionist
# username rename so bind-mounted appdata ownership remains valid.
#
# H7: skip a full recursive chown when /config is already UID/GID 1000.
# Unconditional chown -R on every start rewrites large databases. A file inside
# that directory can still be root-owned: docker exec defaults to root, and
# sqlite3.connect on a missing path creates a 0-byte file before any write.
# That stray file is chowned on its own and named in a warning. This script
# never creates a database file.
#
# This script never writes settings.json. It only repairs ownership, then
# drops to uid 1000. Settings migrations run in the app after that drop.
#
# Tests set PROJECTIONIST_CONFIG_DIR. The container uses /config.
config_dir="${PROJECTIONIST_CONFIG_DIR:-/config}"

if [ "$(id -u)" = "0" ]; then
    cfg_uid="$(stat -c '%u' "$config_dir" 2>/dev/null || echo 0)"
    cfg_gid="$(stat -c '%g' "$config_dir" 2>/dev/null || echo 0)"
    if [ "$cfg_uid" != "1000" ] || [ "$cfg_gid" != "1000" ]; then
        echo "projectionist: fixing ownership of ${config_dir} (uid ${cfg_uid}, gid ${cfg_gid})" >&2
        chown -R projectionist:projectionist "$config_dir"
    else
        stray="$(mktemp)"
        find "$config_dir" ! -user 1000 > "$stray" 2>/dev/null || true
        while IFS= read -r path; do
            [ -n "$path" ] || continue
            echo "projectionist: fixing ownership of ${path}" >&2
            chown projectionist:projectionist "$path"
        done < "$stray"
        rm -f "$stray"
    fi
    exec gosu projectionist "$@"
fi

# Already non-root (e.g. Kubernetes with runAsUser) — run directly
exec "$@"
