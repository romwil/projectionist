# Letter to the Maintainer — Architecture & Code Review

**Date:** 2026-07-26  
**Subject:** Deep-dive review for self-hosted Docker / Unraid fitness  
**Scope:** Full codebase (backend, frontend, Docker/ops, security, data model, tests)  
**Reviewed version:** `1.8.32` (`main` @ time of review; pre-rebrand `curatorx/` paths)  
**Current package:** `projectionist/` (rebrand; remote still `romwil/curatorx`)  
**Verdict:** **Evolve — do not rewrite.** The architecture matches the product. Concentrate effort on a small set of correctness bugs, structural god-modules, and operator-hardening gaps.

---

## 0. Remediation progress

Ported onto Projectionist `main` (post-rebrand v1.27.x) after cloud-agent PRs #1–#6 targeted pre-rebrand `curatorx/` on v1.8.32. PR #7 landed the remaining ported Critical/High/cheap Medium items.

### Already fixed (evidence on trunk)

| ID | Status | Evidence |
|----|--------|----------|
| C1 `search_library` | Done | `ToolRegistry._tool_search_library` returns JSON (`projectionist/agent/tools/__init__.py`); was already fixed on Projectionist trunk before the port |
| C2 bind exposure | Done | `HOST` / `PROJECTIONIST_HOST` + startup warning in `projectionist/web/__main__.py` |
| H2 first-owner race | Done | Env-seeded owner (`PROJECTIONIST_OWNER_*`) in `projectionist/web/auth.py` / app startup |
| H3 MCP self-confirm | Done | Per-key active-curation scope (`mcp_full_confirm_enabled` / `PROJECTIONIST_MCP_FULL_CONFIRM`) |
| M11 constant-time key compare | Done | `hmac.compare_digest` in `projectionist/mcp/mode.py` |
| H1 (partial) | In progress | `library/db.py` → package; `agent/tools.py` → package; `styles.css` → `frontend/src/styles/*` (v1.17). `web/app.py`, `App.jsx`, `ConfigPage.jsx` still large |
| M8 (partial) | In progress | CSS split done; AuthProvider / god-component extraction still open |
| M9 (partial) | In progress | Backend coverage fail-under raised to **74%** in CI/`pyproject.toml` |

Design deltas vs original letter:

- **H2** uses an env-injected owner credential (Unraid CA field, no lockout) rather than a claim code.
- **H3** scopes active curation at key creation rather than mandating a human in the loop for every confirm.

### Still open — path to letter grade A

| ID | Severity | Effort | Status | Primary files / notes |
|----|----------|--------|--------|------------------------|
| H6 | High | M | **Kicking off** | `.github/workflows/ci.yml` — PR job: `docker build` + tmp `/config` + `curl /api/health` |
| H7 | High | S | **Kicking off** | `scripts/docker-entrypoint.sh`, `docs/DOCKER.md` — conditional chown; document UID 1000 |
| H1 | High | L | Open (partial) | Finish router/tool/repo splits; carve `web/app.py`, `App.jsx`, `ConfigPage.jsx` |
| H4 | High | L | Needs decision | Secrets at rest (`settings.json`); `api_token_encrypted` is a marker only |
| H5 | High | M | Needs decision | Gate watchlist/lists/reviews/memory writes under multi-user / prompt-injection |
| H8 | High | L | Open | Embeddings as JSON TEXT; `get_embeddings()` O(n); prefilter before marketing 10k+ |
| M1 | Medium | M | Needs decision | Enable `PRAGMA foreign_keys` after orphan audit (`_open_connection`) |
| M2 | Medium | L | Open | `schema_version` + ordered migration module |
| M3 | Medium | S | Open | Jittered retry for idempotent connector GETs |
| M4 | Medium | M | Needs decision | Privacy-mode watch-biased tools → full-only or document intentional |
| M5 | Medium | M | Open | Protocol v1.1 prompt red-team (TC-PROMPT-01 deferred) |
| M6 | Medium | M | Open | Persist quarantine; absolute wall-clock task deadline |
| M7 | Medium | M | Needs decision | Delete or finish stubs; collapse lens vs ambient narrative |
| M8 | Medium | M | Open (partial) | AuthProvider; finish god-component extraction |
| M9 | Medium | M | Open (partial) | Household authz e2e; continue raising coverage culture |
| M10 | Medium | S | Open | WAL-safe backup docs (+ optional Admin snapshot download) |
| M12 | Medium | S | Open / in flight | Compose ↔ Unraid rollout env parity (parallel Unraid kit may close this) |
| L1–L6 | Low | S–M | Backlog | A11y Modal, naming, cycles, version drift, CSP, session TTL |

### What “A or better” means here

Close the remaining **High** ops/trust items (**H6**, **H7**), decide **H4**/**H5**, keep modularizing (**H1**), and clear the integrity/ops Mediums that operators feel (**M1**/**M2**/**M10**/**M12**). Full god-file elimination and embedding scale (**H8**) can trail if sequenced honestly.

---

## Dear Maintainer,

I reviewed CuratorX (now Projectionist) end-to-end against its stated mission: a **self-hosted, Docker/Unraid-friendly, privacy-first agentic curator** for Plex libraries — single container, SQLite, BYO LLM, confirm-gated *arr writes, optional household multi-user, and dual-trust MCP over a local index.

That mission is not only coherent; it is **already largely realized**. The deployment model (one process, `/config` volume, non-root entrypoint, idle trickle enrichment, materialized neighbors) is the right shape for a homelab product. The security program (living `SECURITY.md`, Protocol v1.0 pentests, dual MCP keys, privacy sanitizers) is unusually mature for a project of this size. Documentation quality is a genuine competitive advantage.

What is *not* right is the **concentration of change risk** into a few megafiles, a handful of **latent correctness defects** (including one that silently broke a core agent tool — now fixed), and a few **operator-trust gaps** that matter the moment `:8788` is reachable beyond a single trusted admin.

This letter argues for **incremental evolution with surgical priority**, not a platform rewrite. Below: goals fit, what to keep, findings by severity across categories, and a recommended sequencing plan.

---

## 1. Goals fit — does the architecture serve the product?

| Project objective | Architectural choice | Fit |
|-------------------|----------------------|-----|
| Self-hosted Docker / Unraid | Single multi-stage image, `/config` volume, CA template, multi-arch publish | Excellent |
| Homelab ops simplicity | SQLite WAL, in-process migrations, idle scheduler, no mandatory Postgres/Redis | Excellent |
| Privacy-first agent over local data | Indexed SQLite + tool calls; LLM never bulk-exports; dual MCP keys | Excellent |
| Confirm before *arr mutation | Pending-action tokens in chat UI | Strong (MCP full mode weaker — see H3) |
| BYO LLM (cloud or Ollama) | Provider abstraction + SSE streaming | Strong |
| Intent / taste isolation | Lenses + ambient context + persona sliders | Mixed — product narrative drifted; APIs still dual-track |
| Household optional multi-user | Opt-in auth (Plex PIN / local / OIDC) + role gates | Good (first-owner race H2 remediated via env seed) |
| Explore + chat as one product | Shared library caches feed both agent tools and Explore rails | Strong |

**Non-goals you correctly rejected** (and should keep rejecting): cloud SaaS multi-tenancy, automatic destructive disk ops, generic streaming-service recommender UX. A rewrite toward microservices or Postgres would fight the Unraid audience without buying security or UX.

---

## 2. What to keep (do not “improve away”)

These are load-bearing design wins. Preserve them even while refactoring files:

1. **Single-process FastAPI + static SPA** — one origin, one port, one mental model for CA users.
2. **SQLite + WAL + busy timeout + trickle writers** — documented concurrency story matches reality; a write-queue is optional future, not overdue.
3. **Agent tools vs idle scheduler boundary** — chat stays under ~2s; batch work materializes caches (`item_neighbors`, motifs, embeddings).
4. **Honest provenance** — never invent release dates from year; empty rails with notes beat fake data.
5. **Dual MCP trust planes** — mode from key, not client flag; privacy sanitizers shared with member browse.
6. **Confirm tokens for chat *arr path** — human-in-the-loop for fleet mutation.
7. **Security docs + pentest harness** — treat them as product assets; keep findings IDs stable.
8. **Non-root Docker + gosu entrypoint** — S13 is fixed; keep the upgrade story for root-owned volumes.
9. **Value-based backend tests** — large suite with logic-level assertions; culture is right even where coverage was once performative.

---

## 3. Architecture as it actually runs

```text
Browser (Vite React SPA)
    |  same-origin /api + SSE
    v
Uvicorn :8788  --- FastAPI (web/app.py — still a gravity well)
    |- Auth middleware (no-op unless multi_user_enabled)
    |- JobManager (library sync, jobs_state.json)
    |- IdleScheduler (sequential tasks, quarantine, autotune)
    |- CuratorAgent -> ToolRegistry (~57 tools) -> DB / connectors / LLM
    +- Optional MCP /mcp (privacy key | full key)
           |
           v
    /config  ->  settings.json + SQLite DB (WAL) + jobs_state.json
```

**Coupling reality (review-time anchors; see Appendix A for post-split sizes):** `library/db` and `config_store.py` are imported across nearly the whole tree. `agent/tools` and `web/app.py` are the other gravity wells. Frontend risk mirrors this: `App.jsx` and `ConfigPage.jsx` (CSS was later split into partials).

This is **not** a wrong topology. It is a **modular monolith that forgot to stay modular**.

---

## 4. Findings by severity

Severities assume the documented threat model: **trusted LAN single-owner by default**; multi-user = household identity, not internet multi-tenant. “Critical” means ship-blocking for product correctness or for any deploy that exceeds that model.

### Critical

| ID | Category | Finding | Evidence / notes |
|----|----------|---------|------------------|
| C1 | Correctness / Agent | `search_library` agent tool was broken: `_tool_search_library` awaited search then returned `None`. Card-extension + JSON body was dead code after `return` inside `_tool_suggest_follow_ups`. Chat tool rounds got null content; no-LLM fallback failed silently. | **Fixed.** Was `curatorx/agent/tools.py` ~1738–1780; now `projectionist/agent/tools/__init__.py` |
| C2 | Security / Ops | Default bind `0.0.0.0:8788` + no auth = full admin on any reachable interface. Documented (S3) and accepted for trusted LAN, but still Critical the moment Unraid shares L2 with guests/IoT or someone port-forwards. | **Mitigated** via `HOST` / `PROJECTIONIST_HOST` + warning (`web/__main__.py`); threat model unchanged |

C1 was a pure paste/indent regression with an obvious regression test — correctly treated as patch-train priority.

### High

| ID | Category | Finding | Recommendation | Status |
|----|----------|---------|----------------|--------|
| H1 | Maintainability | Backend god modules + frontend god components dominate regression risk. | Split along existing domain lines (routers / tool packages / repositories / chat hooks). No framework change. | Partial (db/tools/styles split) |
| H2 | Security / Multi-user | First login/registration claimed `owner` with no invite lock. Neighbor on LAN could race ownership when multi-user was first enabled. | Require owner invite code / settings-seeded owner / claim window locked to setup wizard. | **Done** (env-seeded owner) |
| H3 | Security / MCP | Full MCP exposed `propose_*` and `confirm_pending_action`; same client/model could self-confirm. Pending pops with `user_id=None` matched any token. | Confirm only via authenticated web UI/API, or require a separate human confirm channel for MCP. | **Done** (key-scoped confirm) |
| H4 | Security / Secrets | S11 still Open: Plex/*arr/LLM/MCP keys in plaintext `settings.json`. `api_token_encrypted` is a misnomer (marker only). | Encrypt-at-rest with key from env/session secret, or stop persisting secrets already supplied via env. | Open — needs decision |
| H5 | Agent safety | Watchlist / lists / reviews / memory write without confirmation. Fine for single trusted owner; risky under prompt injection or multi-user. | Gate auto-writes behind role + optional “agent may mutate” setting; keep *arr path as the gold standard. | Open — needs decision |
| H6 | CI / Ops | CI never builds or smoke-tests the Docker image. Release notes file is a hard Dockerfile fail; entrypoint/HEALTHCHECK/static mount untested in PR. | PR job: generate notes → `docker build` → run with tmp `/config` → `curl /api/health`. | **In progress** |
| H7 | Ops | Entrypoint `chown -R /config` on every root start; large DBs delay Unraid recreate/Force Update. Fixed UID 1000 (no PUID/PGID). | Conditional chown; document UID clearly in CA template (or optional PUID/PGID). | **In progress** |
| H8 | Data / Scale | Embeddings stored as JSON TEXT; `get_embeddings()` loads all vectors; semantic search is O(n) pure Python. Fine to ~few thousand titles; painful at 10k+ with fat dims. | Binary blob storage + candidate prefilter; keep `item_neighbors` as read cache; sqlite-vec remains a good Future. | Open |

### Medium

| ID | Category | Finding | Recommendation | Status |
|----|----------|---------|----------------|--------|
| M1 | Data integrity | `PRAGMA foreign_keys` never enabled — FK clauses in schema are inert. | Enable after orphan audit; add to `_open_connection`. | Open — needs decision |
| M2 | Schema ops | Migrations are an ad-hoc `_migrate_*` chain on every boot; no schema version table; dual-call of `_migrate_multi_user_columns` historically. | Introduce `schema_version` + ordered migration module (still SQLite). | Open |
| M3 | Connectors | Shared HTTP helpers timeout but do not retry idempotent GETs (429/5xx). | Jittered retry for reads only. | Open |
| M4 | Privacy / MCP | Privacy mode still exposes watch-biased tools (`recommend_hidden_gems`, purge candidates, watch patterns) — raw fields stripped, but results encode household affinity. | Move those tools to full mode only, or document as intentional and tighten filters. | Open — needs decision |
| M5 | Prompt safety | TC-PROMPT-01 (LLM red-team) deferred. Tool JSON can carry internal ids to the model. | Protocol v1.1: confirm-token non-leak, secret non-leak, member sanitizer on tool paths. | Open |
| M6 | Scheduler | Quarantine is in-memory (clears on restart); heartbeat can extend a wedged task if `should_stop()` keeps getting called. | Persist quarantine; absolute wall-clock deadline even with heartbeats. | Open |
| M7 | Product debt | Dead / stub weight: `agent_blueprints` table with no CRUD; `lists/` stub; `llm_theme_tagging` stub; lens CRUD vs “ambient context / zero-touch” narrative. | Delete or finish; stop carrying dual product stories in APIs. | Open — needs decision |
| M8 | Frontend | No shared auth/features context — N× `/api/features` + `/api/auth/me`. CSS was one 9k-line file. | Thin AuthProvider; split CSS by surface without visual rewrite. | Partial (CSS split done) |
| M9 | Testing | Frontend unit tests are lib-only; e2e covers Plex login but not local/OIDC or member Admin deny. Coverage fail-under was **10**. | Add household authz e2e; raise backend cov gate gradually. | Partial (cov ≥74) |
| M10 | Ops / Backup | Guidance is “copy `/config`” without WAL-safe `sqlite3 .backup` procedure. | Document stop-or-backup API; optional Admin download of settings+DB snapshot. | Open |
| M11 | Auth crypto | MCP API key compare used `==`, not `hmac.compare_digest` (webhooks/passwords already did). | Align with webhook pattern. | **Done** |
| M12 | Compose drift | `docker-compose.yml` thinner than Unraid rollout env (TZ, MCP, session secret, healthcheck). | Align compose with rollout `ENV_KEYS`. | Open / Unraid kit in flight |

### Low

| ID | Category | Finding | Recommendation |
|----|----------|---------|----------------|
| L1 | A11y | Roles/aria/reduced-motion present; modals lack consistent focus trap / skip-link. | Shared `Modal` primitive. |
| L2 | Naming | `api_token_encrypted`, `integration_profiles` overstate encryption. | Rename or implement. |
| L3 | Layering | Lazy imports paper over cycles instead of fixing package boundaries. | Fix during router/repo split. |
| L4 | Versioning | README / Unraid XML comments lag `pyproject` version in places. | Generate template version from release script. |
| L5 | CSP | `style-src 'unsafe-inline'` SPA tradeoff. | Accept or move critical CSS. |
| L6 | Sessions | 30-day cookie TTL; `Secure` depends on forwarded proto + trust flag. | Document; optional shorter TTL for multi-user. |

---

## 5. Category scorecards

### Architecture & modularity — B− (trending up)

Right topology; file gravity improving (db/tools/styles split). Evolution path remains: FastAPI routers, thinner tool registry, DB repositories + versioned migrations, frontend hooks. Avoid introducing Redis/Postgres/service mesh.

### Security & privacy — B+ (for stated threat model)

Pentest remediation is real (S1–S2, S4–S10, S12–S15, P1–P6). Patch-train items H2/H3/C2 mitigations and M11 are closed. Remaining High items are secrets-at-rest (**H4**), agent auto-writes (**H5**), and operator bind exposure as a *documented* threat-model choice. **Do not rewrite for security** unless the product becomes internet multi-tenant SaaS.

### Data model & scale — B

Schema is rich and honest. Materialized neighbors / facets / FTS are the correct homelab pattern. Scale cliff is embeddings I/O and O(n) semantic search, not browse queries. Foreign keys off + unversioned migrations are the integrity debt.

### Agent / RAG — A− (was B before C1)

Tool surface is broad and mostly well-validated. Confirm-gated *arr is the crown jewel. `search_library` is fixed. Prompt-injection program incomplete (**M5**).

### Frontend / UX — B

Strong design system (Lights Up/Down, Fraunces/DM Sans, Explore hub, AppShell). Maintainability improved by CSS partials; still threatened by `App.jsx` / `ConfigPage.jsx`. Accessibility intent is good; dialog focus management incomplete.

### Docker / Unraid ops — A− (A after H6/H7)

Best-in-class honesty about Dockerman Force Update, multi-arch, CA template, rollout scripts, non-root. Gaps: CI image smoke, recursive chown, compose/XML parity, backup procedure depth.

### Testing & CI — B (was B−)

Backend test culture is excellent; coverage gate is now meaningful at 74%. Image build smoke still missing (**H6**). Frontend component risk and household auth paths in e2e remain thin.

### Documentation — A

ARCHITECTURE / DESIGN / DATA_MODEL / SECURITY / PRIVACY / wiki / pentest protocol are unusually clear. PRD correctly labeled historical. Keep ARCHITECTURE.md as living truth; prune dual narratives (lenses vs ambient) when APIs catch up.

---

## 6. Rewrite vs evolve — explicit recommendation

| Option | When it would make sense | Recommendation |
|--------|--------------------------|----------------|
| Full rewrite (new stack, new DB, microservices) | Internet SaaS, multi-region, hard multi-tenant isolation | **No.** Betrays Unraid audience and re-litigates solved problems. |
| Architecture redesign (Postgres + worker queue + reverse-proxy-mandatory auth) | Sustained write contention + WAN-first product | **Not yet.** Add only if SQLite locked warnings become measurable *and* libraries routinely exceed ~10–20k with heavy idle write load. |
| Modularize in place | Current pain: god files, migration opacity, CI gaps | **Yes — primary path.** |
| Nothing / status quo | If only shipping cosmetics | **No.** Remaining H6–H7 and H4–H5 still compound support cost. |

**Bottom line:** Projectionist should remain a **modular monolith on SQLite in one Docker container**. Invest in correctness, boundaries, and operator hardening. That meets the project objectives better than a redesign.

---

## 7. Recommended sequencing (technical priority, not calendar)

### Patch train (correctness + trust) — largely done

1. Fix **C1** `search_library` + regression test — **done**
2. **H2** first-owner lock when enabling multi-user — **done** (env seed)
3. **H3** MCP confirm semantics — **done** (key-scoped)
4. **M11** constant-time MCP key compare — **done**

### Ops train (self-hosted confidence) — next for grade A

5. **H6** CI Docker build + health smoke — **in progress**
6. **H7** conditional chown; CA docs for UID 1000 — **in progress**
7. **M10** WAL-safe backup docs (+ optional Admin backup download)
8. **M12** compose/env parity with Unraid rollout

### Structure train (velocity)

9. Split `web/app.py` → routers (`auth`, `library`, `chat`, `admin`, `explore`, `settings`)
10. Continue thinning `agent/tools` domain modules + registry
11. Carve remaining DB gravity + `schema_version` migrations; enable FKs (**M1/M2**) after audit
12. Extract `App.jsx` / `ConfigPage.jsx` hooks; AuthProvider (**M8**)

### Hardening & scale train

13. **H4** secrets at rest (encrypt or env-only persistence) — **needs product decision**
14. **H5** agent auto-write gates for multi-user — **needs product decision**
15. **H8** embedding storage + search prefilter (before marketing “works great at 10k+”)
16. **M4/M5** privacy-tool audit + prompt red-team Protocol v1.1
17. **M6** durable quarantine + absolute task deadline
18. **M7** delete or finish stubs; collapse lens vs ambient product story

### Optional later (only with evidence)

- sqlite-vec ANN prefilter (already sketched as Future)
- Single-writer asyncio queue if lock warnings appear in the wild
- PUID/PGID if Unraid support volume demands it
- Plex Lists publish when upstream API stabilizes

---

## 8. What “done” looks like for the self-hosted mission

A maintainer can declare the architecture healthy for the next major line when:

- Core agent library search works under tests (**C1** closed) — **met**
- Multi-user enablement cannot be raced by a LAN neighbor (**H2**) — **met** (env seed)
- Full MCP cannot silently self-confirm fleet writes (**H3**) — **met** (key scope)
- Every PR proves the shippable image boots and answers `/api/health` (**H6**) — **in progress**
- The three backend megafiles are split enough that a feature touches one domain package, not all three — **partial**
- Secrets on disk are encrypted or env-sourced (**H4** / S11) — **open**
- Docs tell one product story (ambient/chat-first) with APIs that match — **open**
- Backup + upgrade guidance includes WAL-safe DB snapshot steps operators can follow on Unraid — **open**

Until then, keep shipping the product you already built — just stop letting gravity wells quietly tax every release.

---

## 9. Closing

Projectionist is not a prototype that needs to be replaced. It is a **production-quality homelab agent** with an unusually clear thesis (MCP over structured + unstructured local media data) and packaging that respects Unraid users. The highest-leverage remaining work is unglamorous: prove Docker in CI, stop recursive chown tax, decide secrets-at-rest and agent auto-write posture, and keep carving the gods into modules.

Resist the rewrite urge. The architecture already meets the objectives. Make it *ownable* for the next two years of features.

Respectfully,  
**Architecture & Code Review (automated deep dive)**  
2026-07-26  
*(Remediation status updated 2026-07-27 / 2026-07-26 evening)*

---

## Appendix A — Size anchors

### Review snapshot (2026-07-26, pre-split)

| Artifact | Approx. size |
|----------|--------------|
| `curatorx/library/db.py` | 5,557 LOC |
| `curatorx/web/app.py` | 4,203 LOC |
| `curatorx/agent/tools.py` | 3,962 LOC |
| `frontend/src/styles.css` | 9,051 LOC |
| `frontend/src/pages/ConfigPage.jsx` | 2,263 LOC |
| `frontend/src/App.jsx` | 1,904 LOC |
| Backend Python total | ~37k LOC / 108 files |
| Frontend src total | ~33k LOC |
| Tests | ~96 modules / ~24k LOC |

### Post-split snapshot (Projectionist trunk, later)

| Artifact | Notes |
|----------|-------|
| `projectionist/library/db/` | Package of mixins (`_schema.py` ~1.5k, others smaller); public `Database` re-export |
| `projectionist/agent/tools/` | Package (`__init__.py` ~3k + `_definitions.py` ~1.3k) |
| `frontend/src/styles/` | 11 CSS partials; `styles.css` is import-only |
| `projectionist/web/app.py` | Still the largest single module (~5.6k LOC) |
| `ConfigPage.jsx` / `App.jsx` | Still large (~2.5k / ~1.9k) |

## Appendix B — Related living docs

- [ARCHITECTURE.md](../ARCHITECTURE.md)
- [SECURITY.md](../SECURITY.md)
- [PRIVACY.md](../PRIVACY.md)
- [DOCKER.md](../DOCKER.md)
- [DATA_MODEL.md](../DATA_MODEL.md)
- [Pentest 2026-07 findings](../security/pentests/2026-07-platform-full/05-findings.md)
- [TESTING.md](../../TESTING.md) / [docs/TESTING.md](../TESTING.md)
