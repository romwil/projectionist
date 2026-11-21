#!/usr/bin/env bash
# Fail when the client OpenAPI snapshot is stale (NAT-003).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
exec "$ROOT/scripts/export-openapi.sh" --check
