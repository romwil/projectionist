#!/usr/bin/env bash
# Write docs/api/openapi.json for the client-tagged routes (NAT-003).
#
# Uses a throwaway DATA_DIR. PROJECTIONIST_EXPOSE_OPENAPI is set only for this
# process; production leaves it unset so /openapi.json stays off.
#
#   ./scripts/export-openapi.sh
#   ./scripts/export-openapi.sh --check
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT
export DATA_DIR="$tmpdir"
export PROJECTIONIST_SKIP_DOTENV=1
export PROJECTIONIST_EXPOSE_OPENAPI=1
export LLM_PROVIDER="${LLM_PROVIDER:-ollama}"
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"

if [[ -x "$ROOT/.venv/bin/python" ]]; then
  PYTHON="$ROOT/.venv/bin/python"
elif command -v python >/dev/null 2>&1; then
  PYTHON=python
elif command -v python3 >/dev/null 2>&1; then
  PYTHON=python3
else
  echo "python is required to export the OpenAPI snapshot" >&2
  exit 1
fi

"$PYTHON" -c "from projectionist.web.client_contract import main; raise SystemExit(main())" "$@"
