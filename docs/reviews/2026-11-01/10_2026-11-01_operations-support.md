# 10 · Operations & Customer Support — Projectionist 360° review, run 2026-11-01

**Reviewer:** Operations & Customer Support Lead (`OPS`) · **Code:** `05274cf` (tag `v1.38.0`) · **Survey host:** QA `http://10.10.1.202:8792` (read-only, owner session) · **Grade: C+**

**Who "support" is here.** Projectionist has no support organization. Support is done by two people:
1. **The household owner.** They run the Unraid/Docker container and answer family questions such as "why can't I see X?", "I'm locked out", or "my invite doesn't work".
2. **The project maintainer.** They handle GitHub issues from owners, cut releases, and run the rollout scripts.

Throughout this document, "support agent" means one of those two people. "Admin" means the owner wearing an ops hat.

---

# Part A: Conclusions & findings

## 1. Bottom line

The 1.38.0 owner console is better than most self-hosted companions at telling an owner what's wrong with the *server*. The weak spot is the *household*: people waiting to get in, people locked out, and the safety of the youngest members. Grade: **C+**.

The most important thing to fix is the set of escalation paths, which are missing or misdocumented:
- Access requests can sit unanswered for months without ever reaching "Needs attention". On QA, 4 requests are 75–76 days old (OPS-006).
- Owner lockout recovery depends on an environment variable that silently does nothing if the username doesn't match. Meanwhile Help tells members to "reset it from the login page", and no such control exists (OPS-007).
- An owner can turn Youth mode on for an adult, read that adult's private curator memory, and turn it off again. Nothing records the read (OPS-008).

Backups are a one-time checkbox rather than a habit, and there is no rollback story (OPS-009).

The most important thing to protect is the **server-verified "Needs attention" model plus the scrubbed Security log** (OPS-001, OPS-002). Both are the right foundation to extend; neither needs replacing.

## 2. Key conclusions

1. **"Needs attention" watches the machine, not the people.** The feed is built from four sources only: secrets health, failed tasks, required setup steps, and the Monday pass (`05274cf:projectionist/web/owner_ops.py:451-528`). It skips the queues where a human is waiting: pending access requests, open media issues, expired invites, stale library sync, and a disconnected Plex. Live on QA, the feed showed five items (two Radarr/Sonarr key badges, secrets key, backup, Monday pass), while four access requests sat 75–76 days old. Inbox notifications were not enough to get them handled. The root cause is that the feed was designed as a setup and stewardship checklist (UX-036 lineage), not as a support queue. Roadmap implication: add household queues to the existing feed now. It is a small change on a good base (OPS-006, OPS-001).

2. **Account recovery is the most likely real support ticket, and both the product and the docs get it wrong.** Member-side, the password-reset path is sound: an owner reset bumps the session epoch (`05274cf:projectionist/library/db/_users.py:125-137`). But Help promises "reset it from the login page" (`05274cf:docs/HELP.md:336`), and `LoginPage.tsx` has no forgot or reset control. Owner-side, the only lockout recovery is restarting with `PROJECTIONIST_OWNER_PASSWORD`. That works only when `PROJECTIONIST_OWNER_USERNAME` matches the existing owner's display name. If the owner was created by the wizard under another name, the path logs a warning and skips (`05274cf:projectionist/web/auth.py:319-350`), with no CLI fallback. The root cause is that recovery was designed for the env-seeded install, not for installs set up in the wizard. Fix it before more households onboard through the new invite flow (OPS-007, OPS-019).

3. **The only "view-as"-like tool is the youth memory review, and it has a privacy bypass with no audit trail.** Owners can read a member's curator memory whenever that member's `is_youth` flag is on at read time (`05274cf:projectionist/memory/service.py:18-25`, route `05274cf:projectionist/web/auth_routes.py:135-143`). The flag toggles in one click with no confirmation in either direction (`05274cf:frontend/src/pages/ConfigPage.tsx:803-811`). The memory read writes no Security log row. The page itself promises "adult members' private memory is not shown to owners" (`05274cf:frontend/src/pages/YouthReviewPage.tsx:72-78`). The root cause is that authorization keys off a mutable flag instead of a recorded youth period, and there is no audit on read. Meanwhile the support need that "view as" normally serves ("why can't my kid see this film?") has no tool at all (OPS-008, OPS-017).

4. **Backups are a checkbox you tick once in a lifetime.** The setup step counts as "verified" if *any* backup was *ever* downloaded (`05274cf:projectionist/web/owner_ops.py:166-169,238-244`). Other gaps:
   - No scheduled backup and no snapshot taken before a migration runs on upgrade.
   - Restore means manually replacing files (`05274cf:projectionist/web/backup.py:76`).
   - No doc in `docs/RELEASE.md`, `docs/DOCKER.md`, `docs/ops/AUTOMAT.md`, or `scripts/unraid-rollout.sh` mentions rollback or downgrade (grep for "rollback|roll back|downgrade" returns nothing).

   With 60 forward-only migrations, an owner who has a bad upgrade has no supported way back. The root cause is that backup was treated as an owner chore rather than a platform guarantee (OPS-009).

5. **The invite flow (new in 1.38.0) is secure, but rough to operate.** Tokens are HMAC-signed, stored hashed, used once, revocable, and rate-limited (OPS-004). The operational gaps:
   - Expired invites keep status `pending` and stay under "Pending invites" with a past date (`05274cf:projectionist/library/db/_invites.py:102-120`, `05274cf:frontend/src/pages/AccessRequestsPage.tsx:300-301`).
   - Invites carry no label, so an invite created without an email shows only "member".
   - The UI hard-codes a 7-day expiry even though the API accepts `expires_in_seconds`.
   - The link is shown "copy once".
   - The invite email doesn't name the household or the inviter (`05274cf:projectionist/invites.py:120-130`).
   - Rotating the session secret silently invalidates every outstanding link as "Invite not found" (`05274cf:projectionist/invites.py:32-51`).

   Each of these turns into an "it says my link doesn't work" message (OPS-010).

6. **Owner docs carry maintainer infrastructure, and some fixes require shell or SQL.** The owner-rendered Help tells every owner to `curl http://10.10.1.202:8788/...` with the comment "Automat LAN (authoritative)" (`05274cf:docs/HELP.md:409-412`). That is the maintainer's private prod host. Turning off on-box telemetry needs a `sqlite3` INSERT on the host (`05274cf:docs/HELP.md:443-448`). Docs also say "Admin → Users" (`05274cf:docs/CONFIGURATION.md:160`) where the product says "Members", and "404s for Plex/SSO accounts" where the code returns 400 (`05274cf:projectionist/web/auth_routes.py:885-889`). The root cause is that maintainer runbooks and owner docs share one file with no audience lint (OPS-012, OPS-016).

7. **The maintainer has no intake channel.** The repo has issues enabled, but no issue templates, no `SUPPORT.md`, no diagnostics bundle, and zero filed issues (`gh issue list` returned none; the 9 "open issues" in the repo count are PRs). The maintainer is therefore blind to field failures. When an owner does report one, there is no standard "version + flags + failed tasks + redacted log tail" bundle to ask for (OPS-011).

8. **The routine owner cadence is tuned to library-knowledge metrics.** The weekly "Monday pass" (about 20 minutes) is four steps: Named kinship %, open issues, purge pressure, and task catch-up (`05274cf:docs/HELP.md:395-405`, `05274cf:projectionist/web/owner_ops.py:327-390`). Three of the four are compute-pipeline health. None of them asks "did anyone ask to join, get locked out, or report a problem?". That is a defensible maintainer view. For a typical household owner it is the wrong 20 minutes (OPS-014, OPS-006).

## 3. Foundations challenged

| Assumption | Evidence for | Evidence against | Verdict | Cost of change | Rationale |
|---|---|---|---|---|---|
| SC-19 Owner wants a dense, cinephile Admin with 20 sections and a Monday pass | Needs attention + setup checklist + secrets health are excellent (`owner_ops.py:114-260,451-528`) | Monday pass is 3/4 pipeline metrics; household queues missing; 20 rail items for a 3–10 person household | **Change** — keep the Overview as the one place to look, make the Monday pass household-first, and fold low-traffic sections | S–M | The owner's weekly time should go to people first, then pipelines (OPS-006, OPS-014) |
| SC-04 Two roles + youth flag is enough | Last-owner guards, confirm dialogs (OPS-003) | Youth is a mutable flag that also unlocks memory reads (OPS-008); no co-admin with limited scope | **Keep roles; Change youth semantics** (youth period recorded; memory reads audited) | S | Roles are fine at household scale; the flag doing double duty as an authorization key is the problem |
| SC-06 Invite-only, 7-day signed links | HMAC + hashed + once + revocable (OPS-004) | Expired-as-pending, no labels, secret-bound, copy-once (OPS-010) | **Keep**, fix lifecycle | S | Right model; finish the operations around it |
| SC-23 Secrets keyed to session secret unless pinned | Needs-attention nags to pin `PROJECTIONIST_SECRETS_KEY` | Invites are also bound to session secret; restore onto new box breaks keys and links | **Change** — default-generate a dedicated secrets key file on first boot | S | Removes a whole "keys can't be read" ticket class |
| SC-26 Hub-first + Unraid CA is the only channel worth supporting | Pull-only `unraid-rollout.sh`; documented 0 B Force Update root cause (`DOCKER.md:208-248`) | No rollback or pre-upgrade backup | **Keep**, add rollback | S | One channel is right for a solo maintainer; it needs a way back |
| (OPS-added) Backup is an owner chore | Manual zip with README (`backup.py:31-79`) | One-time checkbox; no schedule; no pre-migration snapshot | **Change** — the platform takes scheduled and pre-upgrade snapshots | M | Data loss is the one unrecoverable support event |
| (OPS-added) Host shell/SQL is an acceptable admin interface | Self-hosted owners can SSH | Telemetry off via `sqlite3`; owner recovery via env+restart; no CLI | **Change** — add `projectionist-admin` CLI for break-glass tasks | S | Break-glass should be one documented command, not SQL |
| (OPS-added) Owners don't need "view as" | Privacy-first stance | "Why can't my kid see X?" has no tool; the youth memory read is the only peek and is unaudited | **Investigate → Add** a read-only, audited *access preview* (not memory) | M | Answers the top household support question without exposing private data |

## 4. If we built it today

A household-ops console would start from **queues with owners and ages**, not checklists:
- One "Household inbox" holding access requests, invites about to expire, media issues, failed newsletter sends, failed tasks, and backup age. Each item shows how many days it has been waiting and offers a one-click action.
- **Recovery would be designed first.** A one-time owner-issued reset link for members (same signed-token machinery as invites), plus a `projectionist-admin reset-owner` CLI inside the container.
- **Backups would be automatic.** Nightly WAL-safe snapshots with retention, plus a snapshot taken before any migration runs; rollback would mean "pin the previous tag and restore the pre-upgrade snapshot".
- **Support context would be one click.** An "access preview" for a member (role, youth ceiling, enabled libraries, why title X is hidden), recorded in the Security log, and a redacted "Copy support info" bundle for GitHub issues.

The gap from today is moderate. The Overview feed, the audit log, the invite token machinery, and the backup zip builder already exist and are well built. Closing the gap is mostly **wiring existing parts together** (S–M effort each), so it is worth doing in the next two cycles.

## 5. Findings by surface

### Public (login, `/join`, request access)
What works: the invite redeem and validate endpoints are rate-limited, and they fail closed with neutral copy (`05274cf:projectionist/web/auth_routes.py:569-615`). What doesn't:
- The login page has no recovery affordance, even though Help promises one (OPS-007).
- Every token failure reads "Invite not found", including a link truncated by an email client or one invalidated by a secret rotation. Members can't tell "ask for a new link" apart from "this was never valid" (OPS-010).
- The invite email names neither the household nor the inviter, so it reads like phishing (OPS-010).

**Grade: C.** IDs: OPS-004, OPS-007, OPS-010, OPS-019.

### Consumer (members, youth)
Members get good self-service: change password, sign out everywhere, and data export and purge (per HELP). The gaps are support-shaped:
- No self-service recovery (OPS-007).
- A youth member's protections can be removed by a single unconfirmed click (OPS-008).
- Members can't see *why* a title is hidden from them, so they ask the owner (OPS-017).

**Grade: C+.** IDs: OPS-007, OPS-008, OPS-017.

### Owner (household admin)
**Routine-task inventory.** Steps were counted from code and docs. Times are estimates for a 5-member, 5k-title household.

| Task | Frequency | Steps today | Est. time | Should be |
|---|---|---|---|---|
| Monday pass (kinship, issues, purge, catch-up) | Weekly | Overview → 4 steps, each opens another page → Mark reviewed → Mark week done | ~20 min (HELP:397) | Household-first, auto-ticks; ~5 min (OPS-014) |
| Answer an access request | Ad hoc | Inbox or Admin → Access → choose youth/methods → Approve → copy link → send via text | 2–3 min, **if noticed** | Surfaced in Needs attention with its age (OPS-006) |
| Invite a family member (no mail configured) | Ad hoc | Admin → Access → Create → copy-once link → paste into a message | 2 min; lost link = revoke + recreate | Label, TTL choice, "re-issue" (OPS-010) |
| Reset a member's local password | Ad hoc | Members → Reset password → type the new password → tell them out of band | 2 min | Owner issues a one-time reset link (OPS-019) |
| Recover own owner login | Rare, stressful | SSH/Unraid → edit env → restart → hope the username matches | 10–30 min, may fail silently | `projectionist-admin reset-owner` (OPS-007, OPS-018) |
| Back up | "Once" per the checklist | Overview → Download zip → store it somewhere | 1 min, then forgotten | Nightly automatic + pre-upgrade (OPS-009) |
| Upgrade | Per release | CA Force Update, or SSH `rollout.sh`; 0 B pull workaround documented | 5–15 min | Plus a pre-upgrade snapshot and a rollback recipe (OPS-009) |
| Turn off on-box telemetry | Rare | Host shell → `sqlite3` INSERT | 5–10 min, error-prone | In-app toggle (OPS-016) |
| Investigate "why can't X see Y" | Ad hoc | No tool; reason from role, youth ceiling, and content rating by hand | 10+ min | Access preview (OPS-017) |

What works: one Overview that ranks issues by severity and links to the fixing page; server-verified setup steps; secrets health that distinguishes "can't decrypt" from "never tested" (OPS-001). **Grade: C+.** IDs: OPS-001, OPS-006, OPS-007, OPS-009, OPS-010, OPS-014, OPS-016, OPS-019.

### Admin / Ops (support tooling, audit, logs, release)
What works:
- The Security log covers 19 event types with secret-name scrubbing and a 20k-row cap (OPS-002).
- Guardrails on destructive member actions (OPS-003).
- A log viewer with level, logger, and query filters plus a live stream (`05274cf:frontend/src/pages/LogsPage.tsx:4-38`).
- A pull-only release path with an honest root-cause doc for Unraid's 0 B Force Update (OPS-005).

What doesn't:
- The Members table lacks support context: no sign-in method, no last-active time, no per-member "sign out everywhere", and no link to that member's audit rows. "Remove" says "cannot be undone" but not that it purges chats and memory (OPS-013).
- The memory read is unaudited (OPS-008).
- There is no maintainer intake or diagnostics bundle (OPS-011).
- Maintainer LAN commands are shipped in owner Help (OPS-012).
- No "update available" signal (OPS-015).

The QA Security log total was **0** even though 8 invites exist (6 redeemed, 2 revoked). Those predate the 1.38.0 log, so this is expected, but it means the log can't yet be validated against real history. **Grade: B-.** IDs: OPS-002, OPS-003, OPS-005, OPS-008, OPS-011, OPS-012, OPS-013, OPS-015.

## 6. Findings by theme

- **Owner maintenance.** The best example is server-verified setup steps that tick themselves (OPS-001). The worst is a backup step that stays "done" forever after one download (OPS-009). Direction: automate the things that protect data, and make the weekly pass about people (OPS-014).
- **Admin tooling.** Admin is a first-class product for *pipeline* health (Tasks has stage-level counters, catch-up, quarantine) and a second-class one for *people* (OPS-013, OPS-017). Direction: add support context to the Members row and an audited access preview.
- **Support load drivers.** In ranked order, the likely tickets are: (1) "My invite link doesn't work" (OPS-010); (2) "I forgot my password" with a promised login-page reset that doesn't exist (OPS-007); (3) "Why can't I or my kid see this film?" (OPS-017); (4) "I asked to join and nobody answered" (OPS-006); (5) after a restore, "all my keys say can't be read" (SC-23, nagged but not defaulted).
- **Manual toil.** Telemetry off by SQL, owner recovery by env and restart, rollback by hand (OPS-016, OPS-007, OPS-009). Direction: one `projectionist-admin` CLI (OPS-018).
- **Communication.** In-app Help is deep and honest, and What's New surfaces release Highlights. But owner Help is about 100k characters and includes maintainer infrastructure (OPS-012). There is no "update available" signal or status for the owner (OPS-015). There is no channel from owner to maintainer (OPS-011).
- **Escalation & safety.** The last-owner guards, deny soft-blocking, and reset epoch bump are solid (OPS-003). The youth flag and memory-read loophole (OPS-008), the brittle owner recovery (OPS-007), and the lack of any abuse or report path beyond media issues are not. The last is acceptable at household scale, as long as Remove and Disable stay this easy.

## 7. Stop doing

- **Stop shipping maintainer runbook commands in owner Help.** Move the `10.10.1.202` and "Automat" blocks to `docs/ops/AUTOMAT.md` (OPS-012).
- **Stop treating "downloaded a backup once" as a completed setup step** (OPS-009).
- **Stop telling members about a login-page reset that doesn't exist** (OPS-007).
- **Stop putting pipeline metrics (Named kinship %, purge pressure) first in the owner's weekly ritual.** Demote them under "Library health (optional)" (OPS-014).
- **Stop letting one flag both restrict content and grant owner read access to memory** without recording it (OPS-008).

## 8. Strengths worth protecting

- **Needs attention + setup checklist + secrets health** (OPS-001): checked against the server, ranked by severity, deep-linked, and showing an empty state when clear. Extend it; don't fork a second dashboard.
- **Security log** (OPS-002): scrubbing by name, records actor and target, owner-only, bounded size. Every new admin action must add an event constant here.
- **Destructive-action guardrails** (OPS-003): last-owner checks on demote, disable, and remove; confirm dialogs that name the person; password reset bumps the session epoch.
- **Invite token design** (OPS-004): HMAC verified before any DB lookup, only the token hash stored, one-time use, method-scoped, rate-limited.
- **Pull-only, documented rollout** (OPS-005): `unraid-rollout.sh` never builds or wipes `./config`, and the 0 B Force Update root cause is written down honestly.

## 9. Risks of inaction (6–12 months)

- **Silent backlog of people waiting.** As invites become the onboarding path, access requests age invisibly. The family member gives up and the owner never notices (OPS-006). This is already observed on QA.
- **An unrecoverable lockout.** An owner who set up through the wizard forgets their password and has no Plex sign-in. They follow the env-var docs, it silently fails, and they file an issue or reinstall, losing data (OPS-007, OPS-009).
- **A household trust incident.** A teenager's Youth flag is toggled off and on (by accident or not), or an adult's memory is read through the Youth loophole, and the log can't say who read what (OPS-008).
- **A bad migration with no way back.** Without pre-upgrade snapshots or a rollback recipe, one bad migration across the installed base means data loss for anyone without a recent manual backup (OPS-009).
- **The maintainer flying blind.** With zero structured issues and no diagnostics bundle, field failures get fixed only when the maintainer happens to see them on their own prod (OPS-011).

## 10. Recommended direction

Sequence by **who is waiting and what is unrecoverable**:

1. **Now (0–2 weeks).**
   - Add household queues and backup age to Needs attention (OPS-006).
   - Fix the recovery docs and the env-owner silent skip, and ship the CLI reset (OPS-007, OPS-018).
   - Audit memory reads and require confirmation for Youth toggles (OPS-008).
   - Move maintainer commands out of owner Help (OPS-012).
2. **Next (2–6 weeks).**
   - Automatic and pre-upgrade backups plus a rollback doc (OPS-009).
   - Invite lifecycle fixes (OPS-010).
   - Issue templates and "Copy support info" (OPS-011).
   - Members row support context (OPS-013).
   - Owner-issued reset links (OPS-019).
3. **Later (6+ weeks).**
   - Audited access preview (OPS-017).
   - Household-first Monday pass redesign (OPS-014).
   - "Update available" signal (OPS-015).

**What success looks like at 90 days:**
- Median age of a pending access request under 3 days.
- 100% of installs have a backup less than 7 days old.
- Zero Help strings that reference controls that don't exist.
- 100% of memory reads produce a Security log row.
- At least 80% of GitHub bug issues arrive with the support bundle attached.

## 11. Scorecard (1–5)

| Surface | Self-service | Admin tooling | Recovery & safety | Toil | Communication | Reason |
|---|---|---|---|---|---|---|
| Public | 2 | — | 2 | — | 3 | No recovery path; generic invite errors; phish-looking email |
| Consumer | 3 | — | 2 | — | 3 | Good password and session self-service; youth protections one click from removal |
| Owner | 3 | 3 | 2 | 2 | 3 | Strong Overview; people queues missing; backups manual; SQL/env break-glass |
| Admin/Ops | — | 4 | 3 | 3 | 2 | Security log and guardrails good; memory read unaudited; no intake or diagnostics |

---

# Part B: Detailed findings

## 12. Scope & method

- **Code read** (snapshot `/tmp/review360-05274cf` = `05274cf`): `projectionist/web/owner_ops.py`, `owner_ops_routes.py`, `auth_routes.py`, `auth.py` (seed-owner, local login), `invites.py`, `library/db/_invites.py`, `_users.py`, `security_audit.py`, `memory/service.py`, `web/backup.py`, `web/log_viewer.py`; frontend `AccessRequestsPage.tsx`, `admin/HouseholdSection.tsx`, `ConfigPage.tsx` (member action handlers), `YouthReviewPage.tsx`, `JoinPage.tsx`, `LoginPage.tsx`, `LogsPage.tsx`, `MailSettingsPage.tsx`, `routes/AdminRoutes.tsx`. Docs: `docs/HELP.md` owner section, `docs/CONFIGURATION.md`, `docs/DOCKER.md`, `docs/SECURITY.md`, `docs/RELEASE.md` and `docs/ops/AUTOMAT.md` (grep), `scripts/unraid-rollout.sh`.
- **Live (QA `:8792`, owner session, read-only GETs from the page context):**
  - `GET /api/admin/ops/overview` returned Needs attention = `secrets-radarr`, `secrets-sonarr`, `setup-secrets_key`, `setup-backup`, `monday-pass`, and 0 failed tasks.
  - `GET /api/admin/access-requests?status=pending` returned **4 pending, aged 75, 76, 76, 76 days**.
  - `GET /api/admin/invites` returned 8 invites (6 redeemed, 2 revoked, 0 pending, so the expired-as-pending case was not observable live).
  - `GET /api/admin/security-audit?limit=1` returned total 0.
  - Only counts and statuses were extracted. No names or emails were read into this document.
- **GitHub:** `gh issue list --repo romwil/projectionist --state all` returned no issues. The repo reports `has_issues: true` and `open_issues_count: 9`, which are PRs (Likely). There is no `.github/ISSUE_TEMPLATE`.
- **Screenshots:** none new (`ops_*` not created). The Access, Members, and Security log pages show member names and emails, so I relied on `map_admin-overview_owner_1440.png` and `map_admin-tasks_owner_1440.png` from recon.
- **Not reviewed:** member and youth sessions, actual invite redemption, owner lockout on a real install, mail and newsletter sends, restore from a backup zip, Unraid CA upgrade, MCP. No settings saves, runs, invites, or member edits were made.

## 13. Strengths

### OPS-001: Protect the server-verified "Needs attention" Overview

| Field | Value |
|---|---|
| Type | Strength |
| Surface | Owner |
| Persona(s) | Established owner, platform admin |
| Category | Admin tooling |
| Severity | High |
| Impact | 4 |
| Effort | XS |
| Confidence | Confirmed |
| Priority score | 12.0 |
| Verdict | Protect |
| Dependencies | Extended by OPS-006, OPS-009, OPS-014 |
| Labels | owner-ops, overview, stewardship |

**Evidence:** `05274cf:projectionist/web/owner_ops.py:114-160` (secrets health per service), `:181-255` (setup items verified against server state), `:451-528` (severity-ranked feed with `to` deep-links). Live: `map_admin-overview_owner_1440.png` shows "5 things need attention", each row with an Open button. `05274cf:docs/HELP.md:391-393`.

**Current state:** One feed, ranked high to medium to low, each row linking to the fixing page, with an explicit empty state. Setup steps are checked against the server rather than ticked by hand. Secrets health distinguishes "can't decrypt", "marked connected but no key", and "never tested".

**Root cause:** Deliberate Phase 6 design (UX-036) that consolidated scattered panels.

**Recommendation:** Keep the single-feed model and the `{id, kind, severity, title, detail, to}` contract. Extend it with new `kind`s (OPS-006) rather than adding new dashboards.

**Rationale:** Owners check one place, which is the cheapest possible support tool. Forking it would split attention again.

**User story:** As an owner, I want one list of what needs me so that I don't have to tour 20 admin pages.

**Acceptance criteria:**
- [ ] Any new owner-actionable condition is added as a `needs_attention` kind, not a new panel.
- [ ] Every item has a `to` route that resolves to an existing admin page.

**Success metric:** Share of owner sessions that start on Overview and end with zero high-severity items (target ≥ 70%).

**Validation:** Unit test `build_needs_attention` for each kind; Playwright: each Open button navigates to its `to`.

**Protect this:** Do not replace the feed with a static checklist. Do not let items lack a deep-link.

### OPS-002: Protect the scrubbed, owner-only Security log

| Field | Value |
|---|---|
| Type | Strength |
| Surface | Admin |
| Persona(s) | Platform admin, support agent |
| Category | Audit |
| Severity | High |
| Impact | 4 |
| Effort | XS |
| Confidence | Confirmed |
| Priority score | 12.0 |
| Verdict | Protect |
| Dependencies | Extended by OPS-008, OPS-013, OPS-017 |
| Labels | audit, security-log |

**Evidence:** `05274cf:projectionist/security_audit.py:15-57` (19 events), `:59-76` (drops keys that look like secrets, truncates values), `:79-98` (never raises into the request). Invite, user, and reset routes call `sa.audit` (`05274cf:projectionist/web/auth_routes.py:613,662-669,739-746,764,801-808,822-828,834-840,865,891`). Owner-only route `05274cf:projectionist/web/owner_ops_routes.py:114`. `05274cf:docs/HELP.md:427-437`.

**Current state:** Who did what to whom, and when, for auth and admin actions, with field *names* only for settings saves.

**Root cause:** SEC-012 delivered in Phase 6.

**Recommendation:** Keep it. Require any new admin mutation or privileged read to add an event constant here, enforced by a test that scans `require_role("owner")` mutation routes for an `sa.audit` call.

**Rationale:** This is the only forensic tool a household owner has.

**User story:** As an owner, I want to see who changed a member's access so that I can answer "who turned this off?".

**Acceptance criteria:**
- [ ] A test fails if an owner-only POST/PATCH/DELETE route lacks an audit call.
- [ ] No detail value contains a secret (existing scrub test retained).

**Success metric:** 100% of owner mutation routes are audited.

**Validation:** Run the route-scan test; manually trigger a role change on QA and see the row.

**Protect this:** Never log message text or secret values. Keep the 20k cap.

### OPS-003: Protect destructive-action guardrails on members

| Field | Value |
|---|---|
| Type | Strength |
| Surface | Admin |
| Persona(s) | Owner, support agent |
| Category | Escalation & safety |
| Severity | Medium |
| Impact | 4 |
| Effort | XS |
| Confidence | Confirmed |
| Priority score | 8.0 |
| Verdict | Protect |
| Dependencies | — |
| Labels | guardrails, members |

**Evidence:** Last-owner and self guards: `05274cf:projectionist/web/auth_routes.py:788-792,810-814,850-857`. Reset bumps the session epoch: `05274cf:projectionist/library/db/_users.py:131-133`. Confirm dialogs that name the person: `05274cf:frontend/src/pages/ConfigPage.tsx:725-747,749-774,776-801,813-832`. Deny soft-blocks the identity: `05274cf:projectionist/invites.py:166-174`.

**Current state:** You can't lock yourself out or orphan the household from the UI. A reset signs the member out everywhere.

**Root cause:** Deliberate design (OPS-016 in an earlier run, SEC work).

**Recommendation:** Keep it. Extend the same confirm pattern to Youth toggles (OPS-008).

**Rationale:** These guards prevent the worst self-inflicted tickets.

**User story:** As an owner, I want the app to stop me from removing the last owner so that I never lose admin access.

**Acceptance criteria:**
- [ ] Existing guard tests remain green.
- [ ] Any new destructive member action uses `confirm()` with the member named.

**Success metric:** Zero "locked out after demote/remove" reports.

**Validation:** Existing tests in `tests/test_api_authz.py` / `test_phase2_trust_core.py`.

**Protect this:** Do not remove the epoch bump on reset.

### OPS-004: Protect the invite token design

| Field | Value |
|---|---|
| Type | Strength |
| Surface | Public |
| Persona(s) | Invited member, owner |
| Category | Escalation & safety |
| Severity | Medium |
| Impact | 3 |
| Effort | XS |
| Confidence | Confirmed |
| Priority score | 6.0 |
| Verdict | Protect |
| Dependencies | Operational fixes in OPS-010 |
| Labels | invites |

**Evidence:** `05274cf:projectionist/invites.py:24-51` (HMAC verified before any DB lookup, only the SHA-256 hash stored), `:147-163` (revoked, redeemed, and expired states), `:177-180` (method-scoped). Rate limits: `05274cf:projectionist/web/auth_routes.py:572,589`. Join intersects server methods with invite methods: `05274cf:frontend/src/pages/JoinPage.tsx:72-75`.

**Current state:** Secure, one-time, revocable links.

**Root cause:** Careful 1.38.0 design.

**Recommendation:** Keep the cryptography. Fix the lifecycle (OPS-010) without weakening it.

**Rationale:** A secure invite model with weak operations is far easier to fix than the reverse.

**User story:** As an owner, I want leaked old links to be useless so that only the person I invited gets in.

**Acceptance criteria:**
- [ ] Token remains single-use and hash-stored after OPS-010 changes.
- [ ] Revoked and expired tokens continue to fail redeem.

**Success metric:** Zero redeems of revoked or expired invites.

**Validation:** Existing invite tests plus a new expired-redeem test.

**Protect this:** Never store or log raw tokens; keep rate limits.

### OPS-005: Protect the pull-only, documented rollout path

| Field | Value |
|---|---|
| Type | Strength |
| Surface | Admin |
| Persona(s) | Maintainer, owner upgrading |
| Category | Release operations |
| Severity | Medium |
| Impact | 3 |
| Effort | XS |
| Confidence | Confirmed |
| Priority score | 6.0 |
| Verdict | Protect |
| Dependencies | Rollback added in OPS-009 |
| Labels | release, unraid |

**Evidence:** `05274cf:scripts/unraid-rollout.sh:1-31` (pull-only, never wipes `./config`, tag pinning); `05274cf:docs/DOCKER.md:208-248` (Force Update 0 B root cause and supported path).

**Current state:** A predictable upgrade that preserves config, with an honest explanation of an Unraid quirk.

**Root cause:** Hub-first release discipline.

**Recommendation:** Keep it. Add a rollback section and a pre-upgrade snapshot (OPS-009).

**Rationale:** One reliable path beats many half-supported ones for a solo maintainer.

**User story:** As an owner, I want upgrades that never touch my data so that I upgrade promptly.

**Acceptance criteria:**
- [ ] Script remains pull-only.
- [ ] `./config` is never removed.

**Success metric:** Zero data-loss reports attributed to rollout.

**Validation:** Dry-run review of the script on each release.

**Protect this:** No host `docker build` path for owners.

## 14. Weaknesses (sorted by priority score)

### OPS-006: Put people-waiting queues into "Needs attention"

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Owner |
| Persona(s) | Established owner, support agent, invited member |
| Category | Admin tooling |
| Severity | High |
| Impact | 4 |
| Effort | S |
| Confidence | Confirmed |
| Priority score | 6.0 |
| Verdict | Fix |
| Dependencies | Builds on OPS-001; feeds OPS-014 |
| Labels | owner-ops, access-requests, media-issues, queues |

**Evidence:** `05274cf:projectionist/web/owner_ops.py:451-528` only emits `secrets`, `tasks`, `setup`, `monday` kinds. Live QA: `GET /api/admin/ops/overview` lists 5 items, none about access requests, while `GET /api/admin/access-requests?status=pending` returns **4 requests aged 75–76 days**. Access requests are only signalled via inbox and email (`05274cf:docs/HELP.md:822`).

**Current state:** A would-be member can wait indefinitely. Open media issues show only as a Monday-pass number. Stale sync and Plex disconnects are not flagged.

**Root cause:** The feed was designed as stewardship of the stack, not as a support queue.

**Recommendation:** Add these kinds to `build_needs_attention`:
- `access-requests`, severity **high** if any pending request is older than 2 days, otherwise medium. Title: "N people asked to join". Detail: "Oldest waiting X days." Link: `/admin/access`.
- `invites-expiring`, medium. Pending invites that expire within 24h or have already expired. Link: `/admin/access`.
- `media-issues`, medium. Open member reports older than 7 days. Link: `/admin/health?tab=issues`.
- `sync-stale`, medium. Last library sync more than 48h ago while the sync interval is 24h. Link: `/admin/libraries`.
- `plex-down`, high. Plex connection test failed or the service is unreachable. Link: `/admin/connections`.

Sort by severity, then age.

**Rationale:** Real people waiting is the highest-value owner action. Otherwise the invite launch (1.38.0) creates silent drop-off. Alternatives rejected: relying on the inbox (already shown to fail on QA) and a separate "Requests" page (fragments attention, contrary to OPS-001).

**User story:** As an owner, I want to see who is waiting on me and for how long so that nobody gives up on joining.

**Acceptance criteria:**
- [ ] With ≥1 pending access request older than 2 days, Overview shows a high-severity "people asked to join" row with the oldest age.
- [ ] With an expired pending invite, a row appears linking to Access.
- [ ] With 0 pending items, no rows are added (empty state unchanged).

**Success metric:** Median pending access-request age under 3 days (QA baseline: 76 days).

**Validation:** Unit tests per kind; on QA, the Overview feed must show the 4 existing requests.

### OPS-007: Make owner and member recovery real and documented correctly

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Cross-cutting |
| Persona(s) | Member (local password), new owner (wizard-created), support agent |
| Category | Escalation & safety / account recovery |
| Severity | High |
| Impact | 4 |
| Effort | S |
| Confidence | Confirmed |
| Priority score | 6.0 |
| Verdict | Fix |
| Dependencies | OPS-018 (CLI), OPS-019 (reset links) |
| Labels | recovery, lockout, docs-drift |

**Evidence:**
- Help: "Forgot your password? … reset it from the login page, or ask another owner" (`05274cf:docs/HELP.md:336`). `LoginPage.tsx` has no forgot or reset control (grep `forgot|reset` returns no matches; the only recovery-adjacent element is "Need an invite?" at `:428`).
- Owner env recovery only matches by display name and otherwise skips with a log warning (`05274cf:projectionist/web/auth.py:308-350`).
- Docs promise "Rotating the password and restarting resets it (recovery path — no lockout)" (`05274cf:docs/CONFIGURATION.md:61,160`; `05274cf:docs/SECURITY.md:138`).
- There is no admin CLI (`pyproject.toml` scripts are only `projectionist-web` and `projectionist-mcp`).
- The env reset path writes no `PASSWORD_RESET` audit row.

**Current state:** A member with a local password has no self-service path and is told one exists. An owner created in the wizard (any username other than `owner`/env) who forgets their password follows the docs, restarts, and nothing changes. The only sign is a warning in container logs.

**Root cause:** Recovery was designed around the env-seeded install; Help copy was written ahead of a feature that never shipped.

**Recommendation:**
1. Change `docs/HELP.md:336` to: "Forgot your password? Ask the household owner. They can reset it from **Admin → Members → Reset password**."
2. Add `PROJECTIONIST_OWNER_RESET=1`. When set together with `PROJECTIONIST_OWNER_PASSWORD`, the server resets the password of the *sole* owner (refusing if there are several) regardless of username, logs at WARNING, writes `sa.PASSWORD_RESET` with `method="env"`, and refuses unless the env is removed on the next boot. A boot-banner reminds the owner to unset it.
3. When the env owner is skipped, surface a **high** Needs-attention item: "PROJECTIONIST_OWNER_PASSWORD is set but did not match an owner".
4. Ship `projectionist-admin reset-owner` (OPS-018).

**Rationale:** Lockout is the one ticket an owner can't solve inside the app. Alternatives rejected: an email reset link (mail is optional and often off) and a recovery-key file (more for owners to lose).

**User story:** As a locked-out owner, I want one documented command to regain access so that I don't reinstall and lose the household's data.

**Acceptance criteria:**
- [ ] HELP no longer references a login-page reset.
- [ ] With `PROJECTIONIST_OWNER_RESET=1`, a wizard-created owner named "will" can sign in with the env password after restart.
- [ ] A skipped env owner produces a Needs-attention row and an audit row.

**Success metric:** Zero "locked out, had to reinstall" issues.

**Validation:** Integration test that seeds an owner with a non-default name, boots with the reset env, and asserts login succeeds and an audit row exists.

### OPS-008: Close the Youth-flag memory loophole and audit the read

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Admin |
| Persona(s) | Youth member, adult member, owner |
| Category | Escalation & safety / view-as |
| Severity | High |
| Impact | 4 |
| Effort | S |
| Confidence | Confirmed |
| Priority score | 6.0 |
| Verdict | Fix |
| Dependencies | OPS-002; relates to OPS-017 |
| Labels | youth-safety, privacy, audit, view-as |

**Evidence:**
- Access is granted when the target's `is_youth` is true at read time (`05274cf:projectionist/memory/service.py:18-25`).
- The read route `GET /api/users/{id}/memory` makes no `sa.audit` call (`05274cf:projectionist/web/auth_routes.py:135-143`).
- The Youth toggle has no confirm in either direction (`05274cf:frontend/src/pages/ConfigPage.tsx:803-811`), while the YOUTH_CHANGE audit exists (`auth_routes.py:829-840`).
- The page promise reads "adult members' private memory is not shown to owners" (`05274cf:frontend/src/pages/YouthReviewPage.tsx:72-78`).

**Current state:** An owner can turn Youth on for an adult, read up to 500 memory notes, and turn it off. The log shows two Youth toggles and no read. Separately, a misclick removes a child's content ceiling instantly.

**Root cause:** A mutable flag serves both as a content restriction and as an authorization grant for a privileged read. Privileged reads were not in the audit scope.

**Recommendation:**
1. Add `sa.YOUTH_MEMORY_READ` (`actor_id`, `target_id`, `count`) on every successful read.
2. Authorize the read only if the account has been continuously youth for at least 7 days, or was created as youth (store `youth_since` on `set_user_youth`). Otherwise return 403 "Youth mode was turned on recently; memory review opens after 7 days".
3. Show a member-visible notice in the youth member's Settings → Profile: "The household owner can review what the curator remembers for you."
4. Require `confirm()` for Youth **off**: "Remove Youth mode for {name}? They'll see titles above {max rating} and unrated titles immediately." For Youth **on**, mention that memory review becomes available after 7 days.

**Rationale:** Household trust breaks if an adult's private memory is readable through a toggle. Parental oversight of real youth accounts stays intact. Alternatives rejected: removing youth review entirely (loses a legitimate safety tool), and audit-only (detects but doesn't prevent).

**User story:** As an adult member, I want my private memory to stay private even from the owner so that I trust the curator with my taste.

**Acceptance criteria:**
- [ ] A read of youth memory writes a `youth_memory_read` audit row.
- [ ] Turning Youth on and reading immediately returns 403 until `youth_since + 7d`.
- [ ] Turning Youth off opens a confirm naming the member and rating ceiling.

**Success metric:** 100% of memory reads audited; zero reads within 7 days of a Youth flip.

**Validation:** API tests for flip-then-read (403) and read on a long-standing youth account (200 + audit row); Playwright confirm-dialog test.

### OPS-012: Remove maintainer infrastructure and drift from owner docs

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Owner |
| Persona(s) | New owner, established owner |
| Category | Communication / docs |
| Severity | Medium |
| Impact | 3 |
| Effort | XS |
| Confidence | Confirmed |
| Priority score | 6.0 |
| Verdict | Fix |
| Dependencies | — |
| Labels | help, docs-drift, content |

**Evidence:**
- `05274cf:docs/HELP.md:409-412`: `# Automat LAN (authoritative)` plus `curl -s http://10.10.1.202:8788/api/library/knowledge-coverage`, rendered to owners at `/help`.
- `:364`: "Unraid/Automat defaults".
- `docs/CONFIGURATION.md` has 8 Automat/`10.10.1.202` mentions and `docs/DOCKER.md` has 6 (grep count).
- "Admin → Users" (`05274cf:docs/CONFIGURATION.md:160`) versus the product label "Members".
- HELP's reset curl comment says "404s for Plex/SSO accounts" (`05274cf:docs/HELP.md:826-836`), but the code returns **400** (`05274cf:projectionist/web/auth_routes.py:885-889`).

**Current state:** Owners see the maintainer's private LAN address as "authoritative" and copy commands that point to someone else's server.

**Root cause:** Maintainer runbooks and owner docs share files; no lint checks the audience.

**Recommendation:**
- Replace the host with `http://<your-server>:8788` and delete the "Automat LAN (authoritative)" comment. Move Automat specifics to `docs/ops/AUTOMAT.md`.
- Fix "Admin → Users" → "Admin → Members" and "404s" → "returns 400".
- Add a CI grep that fails on `10\.10\.1\.202|[Aa]utomat` in `docs/HELP.md`, `docs/PRIVACY.md`, `docs/CONFIGURATION.md`, and `docs/DOCKER.md`.

**Rationale:** Copy-paste docs that target the wrong host generate confused issues. They also leak maintainer topology. The fix is XS.

**User story:** As a new owner, I want every command in Help to work on my server so that I trust the docs.

**Acceptance criteria:**
- [ ] No `10.10.1.202`/Automat strings in owner-facing docs.
- [ ] The CI grep is in place.
- [ ] Label and status-code drift corrected.

**Success metric:** Zero owner-doc references to maintainer hosts.

**Validation:** Run the grep; open `/help` as owner and search the page.

### OPS-009: Make backups automatic and add a rollback path

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Owner |
| Persona(s) | Owner upgrading, platform admin, maintainer |
| Category | Owner maintenance / data safety |
| Severity | High |
| Impact | 5 |
| Effort | M |
| Confidence | Confirmed |
| Priority score | 5.0 |
| Verdict | Fix |
| Dependencies | OPS-005; OPS-006 (backup-age item) |
| Labels | backup, upgrade, rollback, migrations |

**Evidence:**
- `_backup_downloaded` returns true if *any* backup log row exists (`05274cf:projectionist/web/owner_ops.py:166-169`), and that marks the setup step verified forever (`:238-244`).
- Backup is on demand only (`05274cf:projectionist/web/app.py:2917-2925`). Restore is "stop Projectionist, replace files under DATA_DIR /config, restart" (`05274cf:projectionist/web/backup.py:76`).
- Manual `sqlite3 .backup` recipe in `05274cf:docs/DOCKER.md:320-338`.
- No pre-migration snapshot (`projectionist/library/db/migrations.py` has no backup step) and no downgrade guard.
- No "rollback", "roll back", or "downgrade" text in `docs/RELEASE.md`, `docs/DOCKER.md`, `docs/ops/AUTOMAT.md`, or `scripts/unraid-rollout.sh`.
- Live QA: the backup step is pending (never downloaded).

**Current state:** Data protection depends on the owner remembering. An upgrade that applies a bad migration has no supported recovery.

**Root cause:** Backup was framed as an owner chore and a one-time setup step, not as a platform guarantee.

**Recommendation:**
1. Add a `household_backup` scheduled task that writes `DATA_DIR/backups/projectionist-YYYYMMDD.zip` nightly via the existing `build_admin_snapshot_zip`. Keep 7 daily and 4 weekly copies. Owners can turn it off but are warned.
2. On boot, when `schema_version < target`, write `backups/pre-migrate-v{from}-to-{to}.zip` before migrating.
3. Change the setup step to "verified if a backup (manual or automatic) is younger than 7 days". Add a Needs-attention `backup-stale` item (medium if older than 7 days, high if older than 30).
4. Add "Roll back an upgrade" to `docs/DOCKER.md`: `./rollout.sh <previous-tag>` plus restoring the `pre-migrate-*` zip. Refuse to boot with a clear error when the DB schema is newer than the code.

**Rationale:** Data loss is the one unrecoverable support event. The zip builder already exists, so this is wiring. Alternative rejected: relying on Unraid appdata backup plugins (not universal, and they copy the WAL unsafely).

**User story:** As an owner, I want the server to keep recent backups and snapshot before upgrades so that a bad release never costs my household's history.

**Acceptance criteria:**
- [ ] A nightly zip appears in `DATA_DIR/backups` and retention prunes older ones.
- [ ] An upgrade with pending migrations writes a `pre-migrate-*` zip first.
- [ ] Booting older code on a newer schema exits with an actionable message.
- [ ] The setup step turns pending again after 7 days without a backup.

**Success metric:** 100% of installs with a backup younger than 7 days.

**Validation:** Scheduler unit test; migration test with a temp DATA_DIR; doc review.

### OPS-010: Finish the invite lifecycle (expiry, labels, TTL, re-issue, email)

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Owner / Public |
| Persona(s) | Owner, invited member |
| Category | Support load driver |
| Severity | Medium |
| Impact | 3 |
| Effort | S |
| Confidence | Confirmed |
| Priority score | 3.0 |
| Verdict | Fix |
| Dependencies | OPS-004, OPS-006 |
| Labels | invites, join, email |

**Evidence:**
- Status never transitions on expiry: `list_invites` returns stored status (`05274cf:projectionist/library/db/_invites.py:102-120`), and expiry is checked only at lookup (`05274cf:projectionist/invites.py:161-162`).
- The UI filters `status === "pending"` (`05274cf:frontend/src/pages/AccessRequestsPage.tsx:294,300-301`).
- No label field. The UI fixes the TTL even though the API takes `expires_in_seconds` (`auth_routes.py:729`, `AccessRequestsPage.tsx:148-153`).
- "Join link (copy once)" (`:224`).
- The email doesn't name the household or the inviter (`05274cf:projectionist/invites.py:120-130`).
- The HMAC uses the session secret, so rotating it fails every link with "Invite not found" (`05274cf:projectionist/invites.py:32-51`).
- `revoked_by` is discarded (`_invites.py:123`).
- QA had 0 pending invites, so the expired-as-pending case was code-confirmed, not seen live.

**Current state:** Owners can't tell which invite is whose, see dead invites as pending, and must revoke and recreate to resend. Members get a generic failure.

**Root cause:** v1 lifecycle ("status alone is enough for v1").

**Recommendation:**
- In `public_invite_view` and the list, derive `status="expired"` when `expires_at < now`. Show "Expired" with a **Re-issue** button that revokes and recreates with the same options, showing a fresh link.
- Add an optional `label` (≤ 60 chars, e.g. "Grandma's iPad") to the create form and list.
- Add a TTL select: 24h / 7d (default) / 30d.
- Distinguish errors: "This link has expired — ask {household} for a new one" and "This link was replaced or revoked".
- Email subject: "{inviter} invited you to {household_name} on Projectionist".
- Store `revoked_at` / `revoked_by`.

**Rationale:** These are the most likely member-to-owner tickets after launch.

**User story:** As an owner, I want to see which invite is for whom and re-send expired ones in one click so that onboarding doesn't stall.

**Acceptance criteria:**
- [ ] Expired invites show "Expired" with a Re-issue button and drop out of Pending.
- [ ] Label and TTL are settable and shown.
- [ ] `/join` shows a distinct message for expired versus revoked.
- [ ] The invite email names the inviter and household.

**Success metric:** Invite redeem rate ≥ 80% within TTL; zero "pending" rows with a past expiry.

**Validation:** API test with a past `expires_at`; Playwright on the Access page.

### OPS-011: Give the maintainer an intake channel and a support bundle

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Admin |
| Persona(s) | Maintainer, owner reporting a bug |
| Category | Support tooling / communication |
| Severity | Medium |
| Impact | 3 |
| Effort | S |
| Confidence | Confirmed |
| Priority score | 3.0 |
| Verdict | Fix |
| Dependencies | — |
| Labels | github, diagnostics, support |

**Evidence:** No `.github/ISSUE_TEMPLATE/`, no `SUPPORT.md`, no root `SECURITY.md` (`ls` of `05274cf`). `gh issue list --state all` returned no issues; `has_issues: true`. No diagnostics or support-bundle feature in the web routes or pages (grep `diagnostic|support bundle` hits only the Live channels routes).

**Current state:** Owners have no guided way to report problems. The maintainer can't ask for a standard bundle.

**Root cause:** Single-maintainer project that dogfoods on its own prod.

**Recommendation:**
- Add `.github/ISSUE_TEMPLATE/bug.yml` with fields: version (from `/api/health`), install method (CA / Compose / other), multi-user on/off, LLM provider, steps, and "Support info" paste.
- Add **Admin → Health → Copy support info**. It produces a redacted text block: version, schema version, feature flags, enabled integrations (names only), failed or quarantined tasks, last sync time, and the last 50 ERROR/WARNING log lines passed through `sanitize_log_message`. No member names, emails, tokens, or titles.
- Add `SUPPORT.md` that links both, plus a root `SECURITY.md` pointing to `docs/SECURITY.md` for private disclosure.

**Rationale:** Cheap, and it converts silent failures into actionable reports.

**User story:** As an owner hitting a bug, I want one button that gives the maintainer what they need so that I don't paste secrets or guess.

**Acceptance criteria:**
- [ ] Issue template exists and requires version.
- [ ] "Copy support info" output contains no `@`, no `token=`, and no display names (test with seeded data).

**Success metric:** ≥ 80% of bug issues include the bundle.

**Validation:** Unit test the redaction; open a test issue from the template.

### OPS-016: Move break-glass host chores into the app

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Owner |
| Persona(s) | Owner, platform admin |
| Category | Manual toil |
| Severity | Medium |
| Impact | 3 |
| Effort | S |
| Confidence | Confirmed |
| Priority score | 3.0 |
| Verdict | Fix |
| Dependencies | OPS-018 |
| Labels | toil, telemetry, settings |

**Evidence:**
- Telemetry off requires `sqlite3 ./config/projectionist.db "INSERT OR REPLACE INTO curator_system_config …"` ("There is no in-app switch for this yet", `05274cf:docs/HELP.md:441-448`).
- The secrets key is env only, nagged in-app (`05274cf:projectionist/web/owner_ops.py:214-224`).
- Owner recovery is env only (OPS-007).

**Current state:** Privacy-relevant and recovery-relevant settings need shell access and SQL. The stock container may not ship `sqlite3` on the host.

**Root cause:** Features shipped before their owner controls.

**Recommendation:**
- Add an **Admin → Advanced → On-box activity** toggle backed by `telemetry_enabled`, with an audit `settings_save` row.
- On first boot, if `PROJECTIONIST_SECRETS_KEY` is unset, generate `DATA_DIR/secrets.key` (0600) and use it, so a dedicated key exists by default. Keep the env var as an override.
- Document both.

**Rationale:** Each SQL step in docs is a potential corruption ticket. A default-generated key removes the "keys can't be read after restore" class (as long as `/config` is restored together).

**User story:** As an owner, I want privacy and security switches in Admin so that I never run SQL against my live database.

**Acceptance criteria:**
- [ ] A telemetry toggle exists and takes effect without a restart.
- [ ] Fresh installs have a dedicated key, and the setup step auto-verifies.
- [ ] HELP no longer instructs `sqlite3`.

**Success metric:** Zero SQL commands in owner docs.

**Validation:** Unit test on the toggle; fresh-install test checking `key_source == "dedicated"`.

### OPS-014: Make the Monday pass household-first

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Owner |
| Persona(s) | Established owner |
| Category | Owner maintenance |
| Severity | Medium |
| Impact | 3 |
| Effort | S |
| Confidence | Likely |
| Priority score | 2.4 |
| Verdict | Rethink |
| Dependencies | OPS-006 |
| Labels | monday-pass, owner-ritual |

**Evidence:** Steps are kinship, issues, purge, and catch-up (`05274cf:projectionist/web/owner_ops.py:327-390`). "About 20 minutes" (`05274cf:docs/HELP.md:397`). The jargon includes "Named kinship (opened) 33%" (`map_admin-tasks_owner_1440.png`). Likely: no usage data exists to show whether owners complete the pass (QA shows 0 activity).

**Current state:** The weekly ritual prioritizes compute-pipeline health over people.

**Root cause:** It is the maintainer's own tuning loop, promoted to the product.

**Recommendation:** Reorder the pass to:
1. **People:** access requests, expiring invites, locked or disabled accounts.
2. **Reports:** open media issues.
3. **Safety:** backup age, failed sends.
4. **Library health (optional, collapsed):** kinship, purge, catch-up.

Steps 1–3 auto-tick when empty. Target under 5 minutes when all is well. Rename "Named kinship" for owners to "Titles with explained matches".

**Rationale:** Owners who aren't the maintainer will skip a 20-minute jargon pass and miss the people items.

**User story:** As a busy owner, I want a 5-minute weekly check focused on my family so that I keep it up.

**Acceptance criteria:**
- [ ] People steps appear first and auto-tick when empty.
- [ ] Library steps are collapsible and don't block "Mark week done" when optional.

**Success metric:** Weekly pass completion ≥ 60% of weeks (needs on-box counting).

**Validation:** Unit test on step order and auto-tick; UX review.

### OPS-013: Add support context to the Members table

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Admin |
| Persona(s) | Support agent (owner) |
| Category | Admin tooling |
| Severity | Medium |
| Impact | 3 |
| Effort | M |
| Confidence | Confirmed |
| Priority score | 2.0 |
| Verdict | Fix |
| Dependencies | OPS-002 |
| Labels | members, support-context |

**Evidence:**
- Columns are Name, Email, Role, Youth mode, Seerr, Status, Actions (`05274cf:frontend/src/pages/admin/HouseholdSection.tsx:233-241`). There is no sign-in method column; reset shows only for `auth_method === "local"` (`:317-326`).
- There is no owner-side "sign out everywhere" for a member. Only self-service exists (`05274cf:projectionist/web/auth_routes.py:508-517`).
- Remove copy says "This cannot be undone" (`05274cf:frontend/src/pages/ConfigPage.tsx:813-823`), while the action purges memory and chats (`05274cf:projectionist/library/db/_users.py:205-212`) and offers no export first.

**Current state:** To answer "why can't they sign in?", the owner must infer the method, has no last-active signal, and can't kill a lost device's session without disabling the account.

**Root cause:** The table was built for role management, not support.

**Recommendation:**
- Add columns: **Sign-in** (Plex / Password / SSO) and **Last active** (relative, from session or last request).
- Add a row action **Sign out everywhere** (calls a new `POST /api/users/{id}/sign-out-everywhere` that bumps the epoch and audits `sign_out_everywhere` with the actor).
- Add a row link **Activity**, which opens Security log filtered to `target_id`.
- Change the Remove copy to: "Remove {name}? Their chats, curator memory, lists, and watch history in Projectionist are deleted. Plex is not affected." Offer "Download their data first" (existing member export).

**Rationale:** Most household tickets start with "what's going on with this person?".

**User story:** As an owner, I want each member's sign-in method, last activity, and a session kill switch so that I can solve "lost phone" and "can't sign in" in one place.

**Acceptance criteria:**
- [ ] Sign-in and Last active columns render for all members.
- [ ] The owner can sign a member out everywhere, and an audit row is written.
- [ ] The Remove dialog lists what is deleted.

**Success metric:** Median time to resolve "can't sign in" under 3 minutes (owner self-report).

**Validation:** API test for the new endpoint plus audit; Playwright on the row actions.

### OPS-015: Tell owners when an update is available

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Admin |
| Persona(s) | Owner |
| Category | Communication |
| Severity | Low |
| Impact | 2 |
| Effort | S |
| Confidence | Confirmed |
| Priority score | 1.0 |
| Verdict | Add |
| Dependencies | OPS-009 (rollback first) |
| Labels | updates, release |

**Evidence:** No update or latest-version check in `projectionist/` or `frontend/src` (grep `update available|latest_version|check_for_update` returns nothing; only a Hub link in `AboutPage.tsx:12`). What's New appears only after upgrading.

**Current state:** Owners learn of fixes (including security fixes) only via Unraid CA or GitHub.

**Root cause:** Privacy-first stance: no outbound calls by default.

**Recommendation:** Add an opt-in (default **off**) "Check for updates weekly" toggle that GETs the GitHub releases API once a week and shows a low-severity Needs-attention row: "1.38.1 is available — release notes". Never send instance data.

**Rationale:** A small, consent-based outbound call closes the security-patch gap while respecting the privacy promise.

**User story:** As an owner, I want to know when a fix ships so that I'm not running a vulnerable version.

**Acceptance criteria:**
- [ ] The toggle is off by default and documented in PRIVACY.
- [ ] When on, a row appears within 7 days of a release.

**Success metric:** Median version lag under 14 days for opted-in installs (needs maintainer signal; otherwise qualitative).

**Validation:** Unit test with a mocked releases response.

## 15. Opportunities

### OPS-018: Ship a `projectionist-admin` break-glass CLI

| Field | Value |
|---|---|
| Type | Opportunity |
| Surface | Admin |
| Persona(s) | Platform admin, locked-out owner, maintainer |
| Category | Manual toil / recovery |
| Severity | Medium |
| Impact | 3 |
| Effort | S |
| Confidence | Confirmed |
| Priority score | 3.0 |
| Verdict | Add |
| Dependencies | Enables OPS-007, OPS-016 |
| Labels | cli, recovery |

**Evidence:** Only `projectionist-web` and `projectionist-mcp` console scripts exist (`05274cf:pyproject.toml:64-69`). Recovery and telemetry need env edits or SQL (OPS-007, OPS-016).

**Current state:** Break-glass tasks are ad-hoc.

**Root cause:** No admin entry point.

**Recommendation:** Add a `projectionist-admin` console script, run via `docker exec projectionist projectionist-admin …`:
- `reset-owner [--username U]`: prompts for the password and audits with `method="cli"`.
- `list-owners`.
- `backup [--out PATH]`.
- `telemetry on|off`.
- `invites expire-all`.
- `doctor`: prints the same redacted bundle as OPS-011.

Every command writes a Security log row.

**Rationale:** One documented command replaces several fragile procedures.

**User story:** As a locked-out owner, I want `docker exec … projectionist-admin reset-owner` so that recovery takes 1 minute.

**Acceptance criteria:**
- [ ] Each subcommand has a test and an audit row.
- [ ] HELP and DOCKER document `docker exec` usage.

**Success metric:** Recovery time under 5 minutes.

**Validation:** CLI tests against a temp DATA_DIR.

### OPS-019: Let owners issue one-time password-reset links

| Field | Value |
|---|---|
| Type | Opportunity |
| Surface | Owner / Public |
| Persona(s) | Member (local password), owner |
| Category | Account recovery |
| Severity | Medium |
| Impact | 4 |
| Effort | M |
| Confidence | Likely |
| Priority score | 2.13 |
| Verdict | Add |
| Dependencies | OPS-004 token machinery, OPS-007 |
| Labels | recovery, self-service |

**Evidence:** Today the owner types a new password for the member (`05274cf:frontend/src/pages/ConfigPage.tsx:749-774`) and must share it out of band. Invite token machinery exists (`05274cf:projectionist/invites.py:24-51`).

**Current state:** The owner knows the member's new password, and members can't choose their own at reset.

**Root cause:** Reset was built as an owner-sets-password action.

**Recommendation:** Add **Members → Send reset link**. It creates a signed single-use token with a 24h TTL (same HMAC/hash pattern as invites) and a `/reset?token=…` page where the member sets a password (≥ 8 chars). Redeeming bumps the epoch and audits `password_reset` with `method="link"`. Emailed when Mail is on; otherwise there is a copy button. Keep the direct reset as a fallback.

**Rationale:** The owner never knows the password, the HELP promise becomes true, and the infrastructure is reused. Likely rather than Confirmed because ticket volume is inferred.

**User story:** As a member who forgot my password, I want a link to set a new one myself so that the owner never sees it.

**Acceptance criteria:**
- [ ] Token is single-use, expires in 24h, and is hash-stored.
- [ ] Redeem signs out other sessions and writes an audit row.

**Success metric:** ≥ 70% of local-password resets via link within 60 days.

**Validation:** API tests for redeem, expiry, and reuse; Playwright on `/reset`.

### OPS-017: Add an audited, read-only "access preview" for a member

| Field | Value |
|---|---|
| Type | Opportunity |
| Surface | Admin |
| Persona(s) | Support agent (owner), youth member, parent |
| Category | View-as tooling |
| Severity | Medium |
| Impact | 4 |
| Effort | M |
| Confidence | Likely |
| Priority score | 2.13 |
| Verdict | Add |
| Dependencies | OPS-002, OPS-008 |
| Labels | view-as, support, youth-safety |

**Evidence:** No impersonation or "view as" exists (grep `impersonat|view_as` returns no relevant hits). The youth gate is fail-closed on rating (`05274cf:projectionist/youth/rating_gate.py`; HELP:796-800). The platform map (§2.1) says of the support-agent persona: "No 'view as member' tool exists."

**Current state:** "Why can't my kid see *Alien*?" must be reasoned out by hand.

**Root cause:** Full impersonation was (rightly) avoided for privacy, and no narrower tool replaced it.

**Recommendation:** Add **Members → row → Access preview**. It shows the member's role, youth ceiling, nav items they see, and libraries visible. A title search returns visible / hidden plus the reason (e.g. "Hidden: rated R, above PG-13 ceiling", "Hidden: unrated"). The preview does **not** render chats, memory, history, or recommendations. Each open writes `sa.ACCESS_PREVIEW` (actor, target).

**Rationale:** It answers the top household support question without breaching member privacy. Full session impersonation was rejected: it exposes private data and creates audit and consent problems.

**User story:** As an owner, I want to check whether a specific title is visible to a specific member, and why, so that I can answer in seconds.

**Acceptance criteria:**
- [ ] Preview shows the visibility and reason for a searched title using the same `rating_gate` code path.
- [ ] No personal data (chats, memory, watch history) appears.
- [ ] Each open writes an audit row.

**Success metric:** Owner-reported time to answer "why can't X see Y" under 1 minute.

**Validation:** API test that preview results match the member's actual browse results for 20 seeded titles.

## 16. Remediation plan

**Now (0–2 weeks)**

| ID | Title | Effort | Owner role | Dependencies |
|---|---|---|---|---|
| OPS-012 | Remove maintainer infra and drift from owner docs | XS | Maintainer (docs) | — |
| OPS-006 | People-waiting queues in Needs attention | S | Backend + frontend | OPS-001 |
| OPS-007 | Real owner/member recovery + correct docs | S | Backend + docs | OPS-018 |
| OPS-018 | `projectionist-admin` CLI | S | Backend | — |
| OPS-008 | Close Youth memory loophole + audit | S | Backend + frontend | OPS-002 |

**Next (2–6 weeks)**

| ID | Title | Effort | Owner role | Dependencies |
|---|---|---|---|---|
| OPS-009 | Automatic + pre-upgrade backups, rollback doc | M | Backend + maintainer | OPS-005 |
| OPS-010 | Invite lifecycle fixes | S | Backend + frontend | OPS-004 |
| OPS-011 | Issue templates + Copy support info | S | Maintainer + backend | — |
| OPS-016 | Telemetry toggle + default secrets key | S | Backend | OPS-018 |
| OPS-019 | Owner-issued reset links | M | Backend + frontend | OPS-004, OPS-007 |
| OPS-013 | Members table support context | M | Frontend + backend | OPS-002 |

**Later (6+ weeks)**

| ID | Title | Effort | Owner role | Dependencies |
|---|---|---|---|---|
| OPS-017 | Audited access preview | M | Backend + frontend | OPS-008 |
| OPS-014 | Household-first Monday pass | S | Product + frontend | OPS-006 |
| OPS-015 | Opt-in update check | S | Backend | OPS-009 |

**Sequencing rationale:** people waiting and lockouts first, because they are invisible and have no workaround. Then data safety. Then invite polish, which reduces ticket volume. Then tooling that speeds up answers. The update check comes after rollback exists, so that "update now" is safe advice.

## 17. Quick wins (high impact, XS–S)

- **OPS-012** (XS): fix owner Help hosts, labels, and status codes, plus a CI grep.
- **OPS-006** (S): five new Needs-attention kinds. QA would immediately surface the 4 requests waiting 75+ days.
- **OPS-007, step 1** (XS): correct the HELP line about a login-page reset today. The env fix follows.
- **OPS-008, steps 1 and 4** (XS each): audit row on memory read, and a confirm dialog on Youth off.
- **OPS-010** (S): derive "expired" status and the Re-issue button.

## 18. Open questions needing product/business input

1. Should youth memory review exist at all, or should youth accounts simply not have long-term memory? (This decides the OPS-008 design.)
2. Is a default-on nightly backup acceptable for disk use on small Unraid arrays? What retention is right (7 daily + 4 weekly proposed)?
3. Is an opt-in outbound update check consistent with the "nothing leaves your server" promise, or should it live only in Unraid CA? (OPS-015)
4. Should there be a "co-owner lite" role (manage members and invites, no secrets) for two-parent households? This would revisit SC-04.
5. Does the maintainer want GitHub as the owner support channel, or a Discussions board or forum? (OPS-011)

---

## Phase 6 department self-check

- [x] Document opens with Part A, and every conclusion cites finding IDs.
- [x] Every High finding (OPS-006, OPS-007, OPS-008, OPS-009) appears in the narrative (§1, §2). There are no Critical findings.
- [x] Foundations challenged table, "If we built it today", and "Stop doing" are complete.
- [x] All four surfaces are covered with grades (§5).
- [x] Strengths (OPS-001–005) are documented in the full finding format with "Protect this" notes.
- [x] Recommendations include exact specs: kinds and severities, TTLs, copy strings, CLI subcommands, retention counts.
- [x] Every finding has evidence, root cause, rationale, and acceptance criteria.
- [x] IDs OPS-001–OPS-019 are unique. (Numbering follows priority grouping, not creation order.)
- [x] No application code was modified. Only this file was written; no `ops_` screenshots were needed because of member PII on the relevant pages.
- [ ] Status file not updated. Per instructions, the coordinator owns `_status.md`.

**Counts:** 5 Strengths, 11 Weaknesses, 3 Opportunities, 19 in total. Severity across all 19: Critical 0, High 6 (4 weaknesses + 2 strengths), Medium 12, Low 1. Weaknesses and opportunities only: High 4, Medium 9, Low 1.
