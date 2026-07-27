# AGENTS.md

## Cursor Cloud specific instructions

Projectionist is a **single service**: a Python 3.12 FastAPI backend (`python -m projectionist.web`) that
also serves the pre-built React SPA from `frontend/dist`. Optional stdio/HTTP MCP server
(`python -m projectionist.mcp.server`). There is **no separate database/cache/queue** to run — state is
SQLite under `DATA_DIR` (WAL). Plex / Radarr / Sonarr / TMDB / LLM are all optional integrations and
are **not** required to boot, run, or test the app (it starts in single-owner mode with no login).

### Environment (already provisioned by the update script)
- Python venv at `.venv` (created with `python3.12 -m venv`; needs the `python3.12-venv` apt package,
  which the VM image provides). Package installed editable with `.[web,dev,mcp]` extras.
- Frontend deps installed in `frontend/`. The SPA must be **built** (`frontend/dist`) before the
  backend can serve the UI and before e2e runs — the update script does this.

### Run the dev server (single service)
```bash
DATA_DIR=./config PORT=8788 PROJECTIONIST_SKIP_DOTENV=1  # CURATORX_SKIP_DOTENV still accepted .venv/bin/python -m projectionist.web
```
Serves on http://127.0.0.1:8788 (`GET /api/health` → `{"status":"ok"}`). `PROJECTIONIST_SKIP_DOTENV=1  # CURATORX_SKIP_DOTENV still accepted`
avoids picking up a stray `.env`. Generated files land in `DATA_DIR` (`config/`, gitignored).
Backend has **no hot reload** (`reload=False`); restart the process after Python changes. After
editing frontend source, re-run `cd frontend && npm run build` (or use `npm run dev` / Vite on its
own port, which proxies `/api` to `:8788`).

### Lint / test / build (commands live in README.md, TESTING.md, docs/TESTING.md)
- **Lint:** there is no dedicated linter (no ruff/eslint/flake8 config, and CI has no lint step).
  The build/compile gate for the SPA is the production build `cd frontend && npm run build`.
- **Backend tests:** `.venv/bin/python -m pytest tests/` (coverage is auto-enabled via `pyproject.toml`,
  `--cov-fail-under=10`). Full suite ~2.5 min.
- **Frontend unit:** `cd frontend && npm run test:unit`.
- **Mocked e2e:** `npm run test:e2e` (needs `npx playwright install chromium` once). Playwright starts
  its **own** temp server via `node scripts/start-e2e-server.mjs` on **port 8799** (NOT 8788 — see
  `.cursor/rules/e2e-port-8788.mdc`) using the `.venv` python; no live Plex/LLM needed.

### Known non-obvious gotcha (not an environment problem)
`tests/test_api_authz.py` has 2 tests (`test_system_config_blocked_for_guest`,
`test_system_config_blocked_for_member`) that **fail when the whole file/suite runs** but pass in
isolation or as a pair. Cause: the module-global rate limiter in `projectionist/web/rate_limit.py` is not
reset between tests, so the file's cumulative `POST /api/auth/plex` calls exceed the 10/60s limit and
return 429 (the login response then lacks a `user` key → `KeyError`). This is a pre-existing
test-isolation flake, unrelated to dependencies/setup — do not treat it as a broken environment.
