#!/bin/sh
# Refresh Codegraph after git changes. Skip clones/worktrees with no index.
# Never runs `codegraph init`. Failures must not block git.
PATH="${HOME}/.local/bin:${PATH}"
command -v codegraph >/dev/null 2>&1 || exit 0
test -f .codegraph/codegraph.db || exit 0
codegraph sync --quiet >/dev/null 2>&1 || true
