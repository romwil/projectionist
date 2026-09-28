# Git hooks (Codegraph)

Repo-local hooks that run `codegraph sync --quiet` after merge, commit, and
checkout — only if `.codegraph/codegraph.db` already exists. Worktrees stay
unindexed. Never runs `codegraph init`.

Enable once (repo-local; does not touch `~/.gitconfig`):

```bash
git config core.hooksPath scripts/git-hooks
```

`codegraph serve --mcp` (Cursor) already file-watches and catch-up-syncs while
the MCP session is connected. These hooks cover git changes while the daemon
is idle. Cursor’s session tool catalog still needs a reconnect / new chat
after the first index.
