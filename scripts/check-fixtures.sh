#!/usr/bin/env bash
# Fail when client response fixtures are stale (NAT-004).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
exec "$ROOT/scripts/export-fixtures.sh" --check
