# 10 · Operations & Customer Support Lead

Run: **2026-10-28-2**. Commit reviewed: **`94fcd3f`**. Live survey: QA `http://10.10.1.202:8792` as `qa-owner` only (never prod `:8788`, smartmap `:8790`, VIP). Path A image of this SHA — not CA/Hub proof. Working tree on the reviewer laptop was ~36 commits behind; all code cites are `git grep -n` / `git show 94fcd3f:path`. Snapshot zip and taste-data export buttons were **observed but not downloaded** (household data).

There is **no separate platform-admin or support-agent role**. Support = household owner (or Automat maintainer). This review judges the owner’s daily/weekly maintenance, not a SaaS helpdesk.

---

# Part A: Conclusions & findings

## 1. Bottom line

**Grade: C+.** Projectionist treats owner operations as a first-class product more than most self-hosted media tools: the Monday pass hero, confirm-gated *arr writes, in-app Help with an owner half, and graceful Mail-off newsletter delivery are real. The single most important fix is **ending false “Connected ✓” confidence when secrets cannot decrypt** (and the MAC-mismatch log flood that hides every other signal) — an owner cannot run a Monday pass if Connections lies while Tasks silently skip enrichment. The single most important thing to protect is the **Monday pass ritual itself** (Named kinship → issues → purge → Tasks catch-up) plus **confirm-before-*arr** and **Help as the support center**, without inventing impersonation or a ticket product.

## 2. Key conclusions

1. **The Monday pass is the right ops model — and it is only half executable today.** Health narrates a ~20 minute order and tiles deep-link into Issues / Storage / Tasks (`OwnerHealthHero`, `ownerHealth.ts`). On QA, kinship on opened titles sat at **17%**, purge buffer at **100**, rating coverage **0%**, with Tasks still listing dozens of jobs including an “unused future path.” The ritual is sacred; the execution surface is still a raw scheduler console, and the hero is narrative-only — nothing records that Monday was finished. Ship the interactive checklist (OPS-030) so the four steps have done states and a one-click catch-up (OPS-001, OPS-012, OPS-021, OPS-030).

2. **Diagnostics currently lie to the operator.** Logs were a wall of `Settings secret MAC mismatch (wrong PROJECTIONIST_SECRETS_KEY?)` (hundreds of identical WARNINGs). Connections still showed **TMDB Connected ✓** (and Plex/Radarr/Sonarr Connected) while the research readiness line and Tasks skips said the TMDB key was missing. Certification rows outlive decryptability. Overview and Health never show a secrets card, so the fault is only visible if the owner already knows to open Logs. Add that card (OPS-031) next to the badge and log fixes (OPS-010, OPS-011, OPS-020, OPS-031).

3. **Admin is a product, not an afterthought — with dangerous dense tables.** Eighteen multi-user admin destinations are grouped (Setup / Experience / Platform / Communications / System). Members and Access are real queues. But Members exposes role / Disable / Remove on every row (including a confusing non-self “Owner” row), and Access still shows months-old pentest-shaped pending requests with no age, bulk deny, or SLA (OPS-014, OPS-015).

4. **Support load is member→owner, not ticket→agent.** Drivers observed or inferred: Live Off copy that tells people to “ask the owner,” LLM unset (“Configure an LLM provider…”), Youth / Play 403s, join links without tokens, Mail-off email checkboxes, and Help labels that still say **Dashboard / Issues** while the rail says **Health** (OPS-013, OPS-023, OPS-016).

5. **Self-serve recovery is missing for local accounts.** Invite + Access approve covers join; there is no forgot-password / owner-forced reset UI for local-password members. Owner recovery is env/script territory — pure toil for Automat-class support (OPS-016).

6. **Escalation & safety correctly reject SaaS impersonation.** Youth moderation is scoped to Youth accounts only; *arr writes stay confirm-gated; grooming has an undo log. Do **not** add view-as. Do add a non-impersonating troubleshooting export and a broader owner action trail (OPS-004, OPS-005, OPS-017, OPS-033).

7. **Maintainer release toil is an ops tax, not a security finding.** This QA sidecar is Path A `projectionist-qa:wip` of `94fcd3f` while health still reports `1.37.72`. Hub-first vs host-build confusion burns owner/maintainer time every campaign (OPS-018).

8. **Communication surfaces exist and degrade honestly when Mail is off.** Newsletters, inbox letter, What’s New, and Help are present; Newsletters correctly disables email checkboxes until Mail is configured. There is still no household-visible “stack status” when Live is Off or LLM is unset (OPS-006, OPS-023, OPS-034).

## 3. Foundations challenged

| Assumption | Evidence for | Evidence against | Verdict | Cost of change | Rationale |
|---|---|---|---|---|---|
| Owner Monday pass as stewardship ritual | Help § Monday pass; Health hero “About 20 minutes…”; `ownerHealth.ts` | Ritual not on Overview; Tasks still a flat dump; kinship 17% after idle | **Keep** (deepen) | M | Best ops idea in the product; make it a checklist, not only copy |
| Owner is the only admin | No platform-admin role; members redirected from `/admin` | Dense Members/Access tables invite mistakes | **Keep** | — | Household product; do not invent staff roles |
| Confirm before *arr writes | Help; chat confirm tools; MarkBadMediaDialog | None against for ops | **Keep** | — | Core safety; never silent grabs |
| Help is the support center | `/help` role-aware; owner half under `## For owners` | Stale “Dashboard / Issues” labels vs Health rail | **Keep** (fix drift) | S | Correct architecture; naming must match UI |
| No impersonation / view-as | No UI or routes found for impersonation | Harder remote support | **Keep** | — | Privacy > SaaS support convenience; use exports instead |
| Live and Mail are optional operator surfaces | Live Off on Overview; Mail provider Off; Newsletters inbox-still-works | Members generate “ask the owner” tickets when Off | **Keep** | S | Optional is right; add honest household status, not mandatory Mail |
| Connected ✓ certification is trustworthy | Persisted `service_integrations` after Test | MAC mismatch + Tasks skip TMDB while badge stays Connected | **Change** | S–M | Badge must reflect decryptability + last live probe, not forever-certified |
| Full scheduled-task console is owner-facing | Tasks page with Warm Explore / Optimize rates | Unused future paths, 30+ rows, Advanced noise | **Change** | M | Keep power console under Advanced; Monday pass needs a shortlist |
| Snapshot / taste export on Overview | Buttons present with copy | Easy to leak household data in support chats | **Keep** (harden copy / confirm) | XS | Useful; never silent; grade the warning |

## 4. If we built it today

Zero-based owner ops would be **three surfaces**:

1. **Monday** — a single checklist page (kinship / issues / purge / catch-up) with one-click actions and done states.
2. **People** — Members + Access + Youth as one household desk with search, age, bulk deny, and no accidental Remove.
3. **Trust** — Connections health that always answers “will the next idle run work?” (secrets key OK, last probe, next skip reason).

Logs would be aggregated by fingerprint; Mail/Live would remain optional with a household status strip. Help would stay the support center. There would still be **no** ticket product and **no** impersonation.

**Gap vs today:** Health + Tasks + Overview already approximate (1); Members/Access approximate (2) without hygiene; Connections/Logs fail (3). Closing the gap is **worth it** in the Next horizon — it is mostly UX and health signals on existing data, not a new platform.

## 5. Findings by surface

### Public
Login, Help, About, Privacy, Join. Help and Privacy are genuine support doors for guests; Join without a token is a clear dead end (expected). No marketing site — acquisition is GitHub/CA. **Grade: B−.** IDs: OPS-003, OPS-013.

### Consumer
Members rely on owner for Live Off, LLM, Youth gates, and access. Inbox/newsletters work without Mail. No self-serve password recovery. Support tickets are Slack/text to the owner. **Grade: C.** IDs: OPS-016, OPS-023, OPS-006.

### Owner
Monday pass + Overview exports + Newsletters + Connections. Strong ritual copy; weak truthfulness on integrations; Tasks overload; Overview is “at a glance” without the Monday hero. The pass still needs a checklist with done states (OPS-030), and secrets health belongs on this surface as a card beside Plex (OPS-031). **Grade: C+.** IDs: OPS-001, OPS-010, OPS-011, OPS-012, OPS-021, OPS-019, OPS-030, OPS-031.

### Admin
Same persona as owner. Queues exist (Access, Issues-via-Health, Youth memory). No audit of role/invite actions; Access queue is unhygienic; log viewer is present but unusable under spam. **Grade: C.** IDs: OPS-014, OPS-015, OPS-017, OPS-020, OPS-004, OPS-005.

## 6. Findings by theme

**Owner maintenance.** Monday pass is the north star (OPS-001). Catch-up is buried in a full task table with skipped future paths (OPS-012). Overview should either host the hero or deep-link “Start Monday pass” (OPS-021). The missing piece is a checklist that records completion (OPS-030).

**Admin tooling.** Nav grouping is good (`adminNav.ts`). Members/Access need power-table hygiene (OPS-014, OPS-015). Youth moderation correctly fail-closes adult memory (OPS-004 strength). Secrets and connection truth should be a Health/Overview card, not a log scroll (OPS-031).

**Support load drivers.** Naming drift in Help (OPS-013), Live/LLM optional without household status (OPS-023), join/token errors, false Connected (OPS-011).

**Manual toil.** Secrets key mismatch diagnosis requires log archaeology + SSH; Path A vs Path B release confusion (OPS-018); password reset via env/DB (OPS-016).

**Communication.** Help, What’s New, Newsletters, weekly letter. Protect graceful Mail-off (OPS-006). Add status strip (OPS-034).

**Escalation & safety.** Keep no-impersonation (OPS-004). Expand audit beyond grooming (OPS-017). Confirm-before-*arr stays (OPS-005).

## 7. Stop doing

- Treating **Connected ✓** as durable truth after secrets-key changes.
- Shipping **unused future-path** tasks as first-class rows in the Monday-facing Tasks list.
- Leaving **Access requests** pending for months with no age or bulk actions.
- Documenting **Admin → Dashboard / Issues** after the rail renamed them to **Health**.
- Asking maintainers to treat **Path A host builds** as release/CA proof (ops confusion only).
- Adding **impersonation** “for support” — rejected.

## 8. Strengths worth protecting

- Monday pass narrative and tile deep-links (OPS-001).
- Confirm-before-*arr and typed DELETE / grooming undo (OPS-005).
- Role-aware Help with owner half (OPS-003).
- Owner-only admin; Youth memory scoped (OPS-004).
- Newsletters/Mail honest degradation (OPS-006).
- Live and Mail remaining optional (OPS-007).

## 9. Risks of inaction (6–12 months)

- Owners stop trusting Admin after one secrets-key incident and fall back to SSH/`settings.json` forever.
- Monday pass becomes theater: kinship stays low, purge buffer stays full, rating coverage stays 0%.
- Access/Members mistakes (wrong role, accidental Remove) create irreversible household harm without audit.
- Member→owner “tickets” increase as Live/LLM/Mail stay optional without status language.
- Maintainer burn from Path A/B confusion delays real Hub promotions.

## 10. Recommended direction (90 days)

1. **Now:** Secrets/certification honesty + log dedupe; Help label fix; Access age/bulk deny; Overview → Monday CTA.
2. **Next:** Monday checklist (OPS-030) + Tasks shortlist; Members table safety; owner password-reset/invite reissue; secrets health card (OPS-031).
3. **Later:** Broader admin action audit; household status strip; Path B-only QA campaign defaults in ops docs (already written — enforce habit).

**90-day success:** Zero false Connected when `*_api_key_set` is false; Monday pass completable in ≤20 minutes with kinship↑ and purge acted; Access pending age < 14 days; Help labels match rail; MAC warnings never dominate the log tail.

## 11. Scorecard

| Surface | Dimension | Score (1–5) | Reason |
|---|---|---|---|
| Public | Support doors | 4 | Help/Privacy/About present |
| Public | Self-serve join clarity | 3 | Empty token is clear but harsh |
| Consumer | Self-serve unstick | 2 | No password reset; Live/LLM status opaque |
| Consumer | Comms when Mail off | 4 | Inbox path works |
| Owner | Routine maintenance | 3 | Ritual strong; execution noisy |
| Owner | Integration truth | 2 | Connected vs skip contradiction |
| Admin | Queues & moderation | 3 | Exist; lack hygiene/audit |
| Admin | Observability | 2 | Logs drowned; no fingerprinting |
| Cross-cutting | Safety defaults | 5 | Confirm *arr; no impersonation |
| Cross-cutting | Docs as support | 3 | Excellent depth; naming drift |

---

# Part B: Detailed findings

## 12. Scope & method

- **Read:** `docs/reviews/2026-10-28-2/00_2026-10-28-2_platform-map.md`, `_status.md` handoff, `docs/ops/AUTOMAT.md` and `docs/HELP.md` via `git show 94fcd3f:…`, admin nav / health / connections via `git grep`/`git show` on `94fcd3f`.
- **Live (QA `:8792`, `qa-owner`):** Overview, Tasks, Health (Monday pass), Logs, Members, Access, Newsletters, Mail, Connections, Youth, Help. Screenshots under `docs/reviews/2026-10-28-2/screenshots/ops_*`.
- **Not done:** Did not download snapshot zip or taste export. Did not stop/deploy services. Did not exercise Live On, successful Mail send, or member/youth sign-in this pass (consumer support load inferred from owner surfaces + platform map). Did not read other department `0{1–9}_*` docs or `docs/reviews/2026-10-28/`.
- **Browser:** cursor-ide-browser lock held for the walk; unlocked after. Screenshot MCP timed out intermittently — CDP `Page.captureScreenshot` used as fallback for several `ops_*` files.

## 13. Strengths

### OPS-001: Protect the Monday pass as the owner ops ritual

| Field | Value |
|---|---|
| Type | Strength |
| Surface | Owner |
| Persona(s) | Established owner at scale; support agent (= owner) |
| Category | Owner maintenance |
| Severity | Low |
| Impact | 5 |
| Effort | S |
| Confidence | Confirmed |
| Priority score | 2.5 |
| Verdict | Protect |
| Dependencies | OPS-012, OPS-021, OPS-030 |
| Labels | monday-pass, ritual, health |

**Evidence:** QA `/admin/health` hero: “Monday pass / About 20 minutes, in order: Named kinship → open issues → purge pressure → Scheduled Tasks catch-up” with kinship **17%**, 0 open issues, 100 purge candidates (`ops_admin_health_monday_pass_1440.png`). `git show 94fcd3f:frontend/src/lib/ownerHealth.ts` (`buildLibraryHealthStory`). `git grep -n "Monday pass" 94fcd3f -- docs/HELP.md` → Help § Monday pass. Live Help as owner includes Monday pass (`ops_help_owner_monday_1440.png`).

**Current state:** The product names a weekly stewardship ritual and computes narrative + tiles from existing aggregations.

**Root cause:** Deliberate product decision (sacred cow #17) — keep it.

**Recommendation:** Protect copy and tile order. Any redesign of Health must keep the four-step order and opened-title kinship as the headline metric. Pair with OPS-030 checklist.

**Rationale:** Without a ritual, large libraries (5k+ titles) become endless Tasks scrolling. Alternatives (daily digest email only; no ritual) reject because owners need an in-app checklist.

**User story:** As an established owner, I want a named weekly pass so that library care is bounded and repeatable.

**Acceptance criteria:**
- [ ] Health still opens with Monday pass headline + four-step order.
- [ ] Named kinship on opened titles remains the primary coverage number (not Similar cache %).
- [ ] Each tile deep-links to a fix surface.

**Success metric:** ≥70% of multi-user owners who open Admin in a week hit Health; kinship-opened median rises quarter over quarter.

**Validation:** QA walk of `/admin/health` after UI changes; unit tests in `ownerHealth.test.mjs` stay green.

---

### OPS-003: Protect Help as the household support center

| Field | Value |
|---|---|
| Type | Strength |
| Surface | Public |
| Persona(s) | Guest, member, owner |
| Category | Communication |
| Severity | Low |
| Impact | 4 |
| Effort | S |
| Confidence | Confirmed |
| Priority score | 2.0 |
| Verdict | Protect |
| Dependencies | OPS-013 |
| Labels | help, docs, support |

**Evidence:** QA `/help` as owner: “Viewing as Owner — owner guidance included below” + Owners TOC (`ops_help_owner_monday_1440.png`). `docs/HELP.md` `## For owners` at line 316 (`git show 94fcd3f:docs/HELP.md`). Platform map: guest omits owner half.

**Current state:** In-app markdown is the support center; role-aware split is correct for a household product.

**Root cause:** Docs-as-product investment.

**Recommendation:** Keep `/help` canonical. Fix naming drift (OPS-013). Do not move owner runbooks exclusively to GitHub.

**Rationale:** Owner is the support agent; Help is their playbook. External-only docs would increase tickets.

**User story:** As an owner answering a member, I want one in-app guide so that I do not SSH or open the repo.

**Acceptance criteria:**
- [ ] Owner session still sees content below `## For owners`.
- [ ] Member/guest sessions omit owner depth.
- [ ] Monday pass / Mail / Access anchors remain deep-linkable.

**Success metric:** Owner Help pageviews remain ≥ Admin Logs pageviews for support-shaped sessions.

**Validation:** Role matrix on `/help` as guest/member/owner.

---

### OPS-004: Keep owner-only admin and reject impersonation

| Field | Value |
|---|---|
| Type | Strength |
| Surface | Admin |
| Persona(s) | Owner; support agent (= owner) |
| Category | Escalation & safety |
| Severity | Low |
| Impact | 5 |
| Effort | XS |
| Confidence | Confirmed |
| Priority score | 5.0 |
| Verdict | Protect |
| Dependencies | OPS-033 |
| Labels | roles, privacy, no-impersonation |

**Evidence:** Platform map: no platform-admin role. `git grep -n "impersonat\|view.as\|view_as" 94fcd3f -- frontend projectionist docs/HELP.md` → no impersonation product (only unrelated “view as owner-private” log copy). QA Youth: “Review is limited to accounts flagged as Youth… adult members’ private memory is never exposed.”

**Current state:** Correct trust model for a household app.

**Root cause:** Local-first / privacy product stance.

**Recommendation:** Keep. Support via invite reissue, logs (redacted), and optional troubleshooting bundle (OPS-033) — never session takeover.

**Rationale:** Impersonation would create the highest-risk support footgun in a multi-user home. Alternatives rejected: SaaS “login as user.”

**User story:** As a household member, I want the owner unable to silently browse as me so that private taste stays private.

**Acceptance criteria:**
- [ ] No view-as / impersonate control in Admin.
- [ ] Youth moderation remains Youth-scoped.

**Success metric:** Zero impersonation features shipped; support playbooks document export-based debugging.

**Validation:** Admin nav + route inventory audit each release.

---

### OPS-005: Protect confirm-before-*arr and grooming undo

| Field | Value |
|---|---|
| Type | Strength |
| Surface | Owner |
| Persona(s) | Owner |
| Category | Escalation & safety |
| Severity | Low |
| Impact | 5 |
| Effort | S |
| Confidence | Confirmed |
| Priority score | 2.5 |
| Verdict | Protect |
| Dependencies | — |
| Labels | arr, confirm, purge-undo |

**Evidence:** Help owner sections on confirm / purge undo (`git show 94fcd3f:docs/HELP.md` around Delete / grooming). `grooming_action_log` in DB schema (`git grep -n "grooming_action_log" 94fcd3f -- projectionist/library/db`). Health copy: “Full removes are not undoable” / index-only undo panel observed on QA Health text.

**Current state:** Destructive disk ops require confirmation; index-only deletes are reversible.

**Root cause:** Explicit safety model.

**Recommendation:** Never add silent *arr writes from reports or agent tools without confirm tokens.

**Rationale:** One silent delete destroys trust permanently.

**User story:** As an owner, I want to confirm before Radarr/Sonarr deletes so that a chat suggestion cannot wipe disk.

**Acceptance criteria:**
- [ ] Member reports never invoke *arr directly.
- [ ] Full remove remains non-undoable and labeled as such.
- [ ] Index-only undo remains available after index-only purge.

**Success metric:** Zero silent *arr deletes in production incident reviews.

**Validation:** Interactive UI QA on purge confirm + unit coverage for confirm-gated tools.

---

### OPS-006: Protect Mail-off newsletter degradation

| Field | Value |
|---|---|
| Type | Strength |
| Surface | Owner |
| Persona(s) | Owner; member |
| Category | Communication |
| Severity | Low |
| Impact | 4 |
| Effort | XS |
| Confidence | Confirmed |
| Priority score | 4.0 |
| Verdict | Protect |
| Dependencies | OPS-007 |
| Labels | mail, newsletters, inbox |

**Evidence:** QA `/admin/newsletters`: “Outbound email is not configured yet… email will send once you enable SMTP or Resend under Mail”; email checkboxes disabled; inbox still works (`ops_admin_newsletters_1440.png`). Mail page provider Off (`/admin/mail` live text).

**Current state:** Communications work without SMTP — correct for optional Mail.

**Root cause:** Inbox-first notification design.

**Recommendation:** Keep disabled email controls + explicit copy. Do not soft-enable email without Mail.

**Rationale:** Forces honest operator state; avoids bouncing mail.

**User story:** As an owner without SMTP, I still want weekly letters in the inbox so that stewardship continues.

**Acceptance criteria:**
- [ ] Email toggles disabled when Mail off.
- [ ] Inbox delivery paths remain available.
- [ ] Copy names Admin → Mail as the fix.

**Success metric:** Newsletter task delivers inbox >0 when opted-in even if emailed=0 (as on QA Member Newsletter run: 1 delivered · 0 emailed).

**Validation:** Newsletters page with Mail off/on matrix.

---

### OPS-007: Keep Live and Mail as optional operator surfaces

| Field | Value |
|---|---|
| Type | Strength |
| Surface | Cross-cutting |
| Persona(s) | Owner; member |
| Category | Owner maintenance |
| Severity | Low |
| Impact | 3 |
| Effort | XS |
| Confidence | Confirmed |
| Priority score | 3.0 |
| Verdict | Protect |
| Dependencies | OPS-023, OPS-034 |
| Labels | live, mail, optional |

**Evidence:** Overview Live **Off** card (`ops_admin_overview_1440.png`); Mail provider Off; primary nav hid Live when not ready (platform map). Sacred cows #10-ish / product reality.

**Current state:** Optional features do not brick the core curator loop.

**Root cause:** BYO / progressive household setup.

**Recommendation:** Keep optional. Pair with household status copy (OPS-034) so optionality does not become silent breakage.

**Rationale:** Mandating Live/Mail would raise setup cost for solo owners.

**User story:** As a new owner, I want chat and Explore to work before I configure Live or SMTP.

**Acceptance criteria:**
- [ ] Core chat/explore usable with Live Off and Mail Off.
- [ ] Overview still surfaces Live Off as an optional CTA.

**Success metric:** Setup completion without Mail/Live remains a supported path in HELP.

**Validation:** QA flags Live Off + Mail Off still allow Explore/Chat shell.

## 14. Weaknesses

### OPS-011: Stop showing Connected ✓ when secrets are not usable

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Owner |
| Persona(s) | Owner; Automat maintainer |
| Category | Admin tooling |
| Severity | High |
| Impact | 5 |
| Effort | S |
| Confidence | Confirmed |
| Priority score | 7.5 |
| Verdict | Fix |
| Dependencies | OPS-010, OPS-031 |
| Labels | connections, certifications, secrets, false-confidence |

**Evidence:** QA Connections: Plex/Radarr/Sonarr/TMDB **Connected ✓** while research line said **“TMDB needs an API key”** and Tasks skipped metadata/gap/research with **“TMDB API key not configured”** (`ops_admin_connections_1440.png`, Tasks live text). Certifications persisted via `build_certifications_status` / `_integration_certified` (`git show 94fcd3f:projectionist/web/setup.py` ~339–366; `CERTIFIED_SERVICES` includes `tmdb`). UI badge from `CertifiedBadge` when `certified` (`git show 94fcd3f:frontend/src/pages/ConfigPage.tsx` ~250–278). `tmdb_api_key_set` drives research copy (`ConnectionsSection.tsx` ~334).

**Current state:** Last successful Test stamps certified forever until settings fields change; decrypt failure returning empty secrets does not clear the badge.

**Root cause:** Certification is decoupled from runtime secret readability / live probe.

**Recommendation:** Connected ✓ requires `certified && *_api_key_set` (or equivalent decrypt OK) **and** last probe age < N days (e.g. 7). If `api_key_set` is false, force badge to “Needs key” / “Unverified” and show a Health/Overview alert. Invalidate certifications when secrets MAC mismatches are detected at settings load.

**Rationale:** False Connected is the highest-leverage ops bug — owners skip re-test and enrichment stays skipped. Alternative (always re-test on page load) is heavier; pairing set-bit + stale probe is enough.

**User story:** As an owner, I want Connected to mean “the next idle run can use this service” so that Monday pass catch-up is not a ghost chase.

**Acceptance criteria:**
- [ ] When `tmdb_api_key_set` is false, TMDB cannot show Connected ✓.
- [ ] Overview/Health shows a single “Secrets / connections need attention” alert if any certified service fails the set-bit check.
- [ ] Re-Test success restores Connected.

**Success metric:** 0 observed cases in QA where Connected ✓ coexists with Tasks skip reason `TMDB API key not configured`.

**Validation:** Reproduce with mismatched `PROJECTIONIST_SECRETS_KEY` on a disposable QA config; confirm badge + Tasks agree.

---

### OPS-014: Add age, search, and bulk deny to Access requests

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Admin |
| Persona(s) | Owner |
| Category | Admin tooling |
| Severity | High |
| Impact | 4 |
| Effort | S |
| Confidence | Confirmed |
| Priority score | 6.0 |
| Verdict | Fix |
| Dependencies | OPS-017 |
| Labels | access, queue, hygiene |

**Evidence:** QA `/admin/access` pending requests dated **8/18–8/19/2026** including pentest-shaped names (`ops_admin_access_stale_requests_1440.png`). Live text listed multiple pending rows + one denied. Help documents approve/deny (`docs/HELP.md` Invites & access requests) but no aging UX.

**Current state:** Access is a real queue without triage affordances; stale noise trains owners to ignore it.

**Root cause:** Queue shipped for correctness, not operator throughput.

**Recommendation:** Show relative age + sort by oldest; **Deny all older than 14 days** with confirm; filter pending/denied; collapse obvious injection-test payloads behind “show raw.” Inbox already notifies on new requests — add a badge count on Access nav when pending >0.

**Rationale:** Stale pending requests are both clutter and a social-engineering surface if an owner eventually Approves the wrong row.

**User story:** As an owner, I want to clear old access requests in one pass so that only real household asks remain.

**Acceptance criteria:**
- [ ] Each pending row shows age (e.g. “72d”).
- [ ] Bulk deny-by-age action exists with confirm.
- [ ] Pending count visible on Admin → Access.

**Success metric:** Median pending age < 14 days on Automat-class installs.

**Validation:** Seed stale requests on QA; exercise bulk deny; confirm denied cannot redeem.

---

### OPS-010: Deduplicate secrets MAC mismatch and surface a single health fault

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Admin |
| Persona(s) | Owner; Automat maintainer |
| Category | Manual toil |
| Severity | High |
| Impact | 5 |
| Effort | M |
| Confidence | Confirmed |
| Priority score | 5.0 |
| Verdict | Fix |
| Dependencies | OPS-011, OPS-020, OPS-031 |
| Labels | logs, secrets, observability |

**Evidence:** QA `/admin/logs` live tail dominated by `projectionist.secrets_crypto` / `Settings secret MAC mismatch (wrong PROJECTIONIST_SECRETS_KEY?)` — **400+** matches in a single viewport sample (`ops_admin_logs_mac_mismatch_1440.png`). Logger warning at `git show 94fcd3f:projectionist/secrets_crypto.py` ~127. Overview still advertised snapshot download reminding to keep secrets key (`OverviewSection.tsx` ~155–191).

**Current state:** Every decrypt attempt logs WARNING; Admin Logs becomes useless for real incidents.

**Root cause:** Per-field decrypt logs without rate limit / fingerprint aggregation; no promotion to a durable health fault.

**Recommendation:** Log MAC mismatch **once per process boot** (plus counter), expose `secrets_key_status` on `/api/health` or admin health payload, and show a red card on Overview/Health/Logs. Point Help to Automat runbook restore of `PROJECTIONIST_SECRETS_KEY` with the snapshot.

**Rationale:** Without this, OPS-011 cannot be diagnosed from the UI the product already ships.

**User story:** As a maintainer, I want one actionable secrets alert so that I do not scroll thousands of identical lines.

**Acceptance criteria:**
- [ ] Repeated MAC mismatches do not append unbounded identical lines per request.
- [ ] Admin Overview or Health shows a persistent secrets-key fault when mismatches occur.
- [ ] ERROR+ filter is not required to notice the fault.

**Success metric:** After fix, Logs WARNING sample contains ≤1 MAC mismatch fingerprint per hour under load.

**Validation:** QA with wrong secrets key; confirm single card + sparse log.

---

### OPS-012: Replace Monday-facing Tasks dump with a catch-up shortlist

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Owner |
| Persona(s) | Established owner |
| Category | Owner maintenance |
| Severity | High |
| Impact | 4 |
| Effort | M |
| Confidence | Confirmed |
| Priority score | 4.0 |
| Verdict | Rethink |
| Dependencies | OPS-001, OPS-030 |
| Labels | tasks, monday-pass, toil |

**Evidence:** QA `/admin/tasks`: knowledge strip (kinship opened **17%**, vectors “local hash embeddings”), then full table including **“LLM theme tagging… unused future path”**, Gift Queue Advanced, many Skipped (LLM unset / TMDB) (`ops_admin_tasks_1440.png`). Warm Explore / Optimize rates exist (`ScheduledTasksPage.tsx`). Help still tells owners to open Scheduled Tasks after Monday pass.

**Current state:** Power users get everything; Monday pass users get noise and “Due now” futures that should be hidden.

**Root cause:** One console serves ritual catch-up and engineering scheduler duty.

**Recommendation:** Default Tasks tab = **Catch-up** (failed/skipped-with-fixable-precondition, demand-prioritized, Warm Explore). Move full table + unused/disabled future paths under **All tasks** or Advanced. Auto-hide tasks marked unused future path from Catch-up. Surface skip reasons as Connections CTAs when precondition is missing key.

**Rationale:** 20-minute Monday pass cannot include reading 30 rows. Removing unused tasks entirely is alternative — prefer hide-from-default to avoid breaking power users.

**User story:** As an owner on Monday, I want the five tasks that unblock kinship so that I finish in twenty minutes.

**Acceptance criteria:**
- [ ] Default Tasks view ≤10 actionable rows for a healthy install.
- [ ] Unused future-path tasks are not in the default list.
- [ ] Warm Explore remains one click from Catch-up.

**Success metric:** Median time from Health → first catch-up Run now ≤ 60 seconds in moderated usability tests.

**Validation:** QA Tasks default screenshot + unit tests for shortlist filter.

---

### OPS-015: Harden Members table against accidental role/remove actions

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Admin |
| Persona(s) | Owner |
| Category | Admin tooling |
| Severity | High |
| Impact | 4 |
| Effort | M |
| Confidence | Confirmed |
| Priority score | 4.0 |
| Verdict | Fix |
| Dependencies | OPS-017 |
| Labels | members, destructive, ux |

**Evidence:** QA `/admin/household` table: rows for Owner, qa-owner, qa-member, qa-youth, qa-guest with Role selects, Disable, Remove (`ops_admin_members_1440.png`; live DOM: non-self Owner row still offered Remove). `HouseholdSection.tsx` ~260–323 (`git show 94fcd3f:frontend/src/pages/admin/HouseholdSection.tsx`).

**Current state:** Dense spreadsheet of destructive controls; easy mis-click on shared tablets.

**Root cause:** CRUD completeness prioritized over operator safety.

**Recommendation:** Put Remove behind a per-row ⋮ menu + typed confirm (username). Disable role demotion of last owner. Hide or clearly label bootstrap “Owner” vs `qa-owner`. Add last-active column. Confirm Youth toggle.

**Rationale:** Accidental Remove is a high-severity household incident with no impersonation recovery path.

**User story:** As an owner on an iPad, I want Remove hard to hit so that I do not erase a member while changing Youth mode.

**Acceptance criteria:**
- [ ] Remove requires typed confirm of username.
- [ ] Last owner cannot be demoted/removed.
- [ ] Youth toggle asks confirm when enabling/disabling.

**Success metric:** Zero accidental removals reported in maintainer support notes next quarter.

**Validation:** UI QA on Members destructive paths; API still enforces last-owner server-side.

---

### OPS-016: Add owner-mediated local password recovery

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Consumer |
| Persona(s) | Member; owner; support agent (= owner) |
| Category | Support load drivers |
| Severity | High |
| Impact | 4 |
| Effort | M |
| Confidence | Likely |
| Priority score | 3.2 |
| Verdict | Add |
| Dependencies | OPS-014 |
| Labels | auth, recovery, local-accounts |

**Evidence:** QA login is local username/password only (handoff). `git grep` on `94fcd3f` shows local password create/reset helpers in DB/auth for env-seeded owner (`projectionist/library/db/_users.py` reset helper) but no member-facing forgot-password UI in `auth_routes` / pages (no forgot-password route hits). Support path today: owner deletes/re-invites or SSH.

**Current state:** Local-password households have join but not recovery — top ticket class for any multi-user LAN app.

**Root cause:** Plex-primary auth assumed; local accounts added for QA/LAN without a recovery product.

**Recommendation:** Owner action on Members: **Reset password** → one-time invite link or temporary password shown once. Optional: member “Need help signing in?” creates an Access-style owner inbox item. Do not email reset tokens unless Mail configured.

**Rationale:** Re-invite works but destroys continuity (lists, youth flag). Env reset is maintainer-only toil.

**User story:** As an owner, I want to reset a member’s local password without SSH so that a forgotten password is a two-minute Admin task.

**Acceptance criteria:**
- [ ] Owner can issue a single-use reset for a local-password member.
- [ ] Action is logged (ties OPS-017).
- [ ] No reset tokens emailed when Mail is off.

**Success metric:** Owner-handled local login recovery without host SSH in Interactive UI QA script.

**Validation:** Create local member on QA; reset; sign in with new secret; old secret fails.

---

### OPS-013: Align Help labels with Admin → Health

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Public |
| Persona(s) | Owner |
| Category | Support load drivers |
| Severity | Medium |
| Impact | 3 |
| Effort | S |
| Confidence | Confirmed |
| Priority score | 3.0 |
| Verdict | Fix |
| Dependencies | OPS-003 |
| Labels | help, naming, drift |

**Evidence:** Admin rail label **Health** (`adminNav.ts:25`). Help still says **Admin → Dashboard**, **Admin → Issues**, “Library intelligence” in multiple owner sections (`git grep -n "Admin → Dashboard\|Admin → Issues" 94fcd3f -- docs/HELP.md`). Live owner Help TOC still lists “Dashboard”.

**Current state:** Support playbook points at renamed rooms.

**Root cause:** Nav rename without full HELP sweep.

**Recommendation:** Replace Dashboard→Health, Issues→Health → Issues/media tab; keep legacy redirects documented once. Update in-app anchors if needed.

**Rationale:** Every mismatched label generates an owner “where did it go?” loop.

**User story:** As an owner reading Help, I want labels to match the Admin rail so that I do not hunt.

**Acceptance criteria:**
- [ ] No owner-facing HELP string says Admin → Dashboard or Admin → Issues as primary.
- [ ] Health tabs referenced correctly.

**Success metric:** Zero HELP hits for “Dashboard” as an Admin destination after ship.

**Validation:** `git grep` gate in docs CI optional; manual HELP skim.

---

### OPS-018: Treat Path A QA as recon-only in operator habit

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Cross-cutting |
| Persona(s) | Automat maintainer |
| Category | Manual toil |
| Severity | Medium |
| Impact | 3 |
| Effort | S |
| Confidence | Confirmed |
| Priority score | 3.0 |
| Verdict | Fix |
| Dependencies | — |
| Labels | release, hub-first, qa |

**Evidence:** `_status.md` / platform map: QA is Path A `projectionist-qa:wip` of `94fcd3f`, health `1.37.72`, Hub tag lacks #188. `docs/RELEASE.md` + `docs/ops/AUTOMAT.md` already forbid Path A as CA proof (`git grep -n "Path A\|Path B" 94fcd3f -- docs/ops/AUTOMAT.md docs/RELEASE.md`).

**Current state:** Docs are clear; operator practice still burns time reconciling version strings.

**Root cause:** Convenient host builds vs Hub pull discipline.

**Recommendation:** Ops habit only (no security review): Overview or Health footer show **image digest / build-info** next to version when present; QA lifecycle scripts default Path B when tag exists. Do not claim CA proof from Path A.

**Rationale:** Version `1.37.72` on a wip image is an operator footgun during Monday pass (“am I on the fix?”).

**User story:** As a maintainer, I want the running image identity obvious so that I do not promote the wrong mental model.

**Acceptance criteria:**
- [ ] QA health or Admin footer distinguishes Hub tag vs wip/Path A when `.build-info` exists.
- [ ] AUTOMAT QA-LIFECYCLE remains Path B preferred (already) and is followed for release candidates.

**Success metric:** Zero release notes claiming CA proof from Path A in the next two Hub ships.

**Validation:** Compare `GET /api/health` vs `docker inspect` digest on Path A vs Path B sidecars.

---

### OPS-019: Grade warnings on snapshot and taste export buttons

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Owner |
| Persona(s) | Owner; support agent |
| Category | Escalation & safety |
| Severity | Medium |
| Impact | 3 |
| Effort | XS |
| Confidence | Confirmed |
| Priority score | 6.0 |
| Verdict | Fix |
| Dependencies | OPS-033 |
| Labels | export, privacy, support |

**Evidence:** Overview sections “Download taste data” / “Download snapshot zip” (`OverviewSection.tsx` ~155–191; `ops_admin_overview_1440.png`). This review **did not download** them. Copy mentions secrets key for snapshot but not “contains household chat/reviews / do not share in tickets.”

**Current state:** Useful backups sit one click from support panic.

**Root cause:** Backup affordance without support-context warning.

**Recommendation:** Confirm modal: “Contains household data — do not attach to public issues.” Prefer redacted troubleshooting bundle (OPS-033) for support.

**Rationale:** Prevents accidental PII/taste leakage into GitHub/Discord.

**User story:** As an owner seeking help, I want a clear warning before exporting household data so that I do not overshare.

**Acceptance criteria:**
- [ ] Both buttons require confirm acknowledging household data.
- [ ] Snapshot still reminds to keep secrets key.

**Success metric:** Support channels stop receiving raw snapshot zips (maintainer observation).

**Validation:** UI confirm present; buttons still function after confirm.

---

### OPS-021: Put Monday pass on the Admin landing path

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Owner |
| Persona(s) | Owner |
| Category | Owner maintenance |
| Severity | Medium |
| Impact | 3 |
| Effort | S |
| Confidence | Confirmed |
| Priority score | 3.0 |
| Verdict | Fix |
| Dependencies | OPS-001, OPS-030 |
| Labels | overview, ia, monday-pass |

**Evidence:** `/admin/overview` shows household health cards + Live Off + exports but **not** the Monday pass hero (`ops_admin_overview_1440.png`). Hero lives on `/admin/health`. Owners landing on Overview miss the ritual unless they know.

**Current state:** Split brain between Overview and Health.

**Root cause:** Overview kept as setup glance; Monday pass added to Health later.

**Recommendation:** Add “Start Monday pass” primary CTA on Overview linking to Health, or embed the same hero above exports.

**Rationale:** Rituals die when they are one click off the default Admin home.

**User story:** As an owner opening Admin on Monday, I want the pass in front of me without hunting Health.

**Acceptance criteria:**
- [ ] Overview presents Monday pass CTA or embedded hero.
- [ ] Health remains the full ritual surface.

**Success metric:** Share of Monday Admin sessions that reach Health ≥ 80%.

**Validation:** Overview screenshot + link target test.

---

### OPS-020: Aggregate repeated log lines in Admin → Logs

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Admin |
| Persona(s) | Owner |
| Category | Admin tooling |
| Severity | Medium |
| Impact | 4 |
| Effort | M |
| Confidence | Confirmed |
| Priority score | 2.67 |
| Verdict | Fix |
| Dependencies | OPS-010 |
| Labels | logs, ux |

**Evidence:** Same as OPS-010 flood; Filters exist (Level/Logger/Contains) but default Following still paints identical WARNINGs (`/admin/logs` live).

**Current state:** Tail is correct for unique lines; unusable for spammy loggers.

**Root cause:** No client/server aggregation by message fingerprint.

**Recommendation:** UI collapse: `WARNING secrets_crypto MAC mismatch × 424 (first… last…)`. Optional server-side sampling.

**Rationale:** Complements OPS-010; helps all noisy loggers.

**User story:** As an owner debugging Play failures, I want unique errors visible without fighting spam.

**Acceptance criteria:**
- [ ] Identical consecutive (or windowed) lines collapse with count.
- [ ] Expanding a group shows timestamps.

**Success metric:** Distinct fingerprints visible in first screenful during MAC mismatch incident.

**Validation:** Synthetic repeated logger lines in QA.

---

### OPS-023: Publish household stack status when Live/LLM/Mail are off

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Consumer |
| Persona(s) | Member; youth; owner |
| Category | Support load drivers |
| Severity | Medium |
| Impact | 3 |
| Effort | M |
| Confidence | Confirmed |
| Priority score | 2.0 |
| Verdict | Fix |
| Dependencies | OPS-007, OPS-034 |
| Labels | status, live, llm, tickets |

**Evidence:** Handoff + Overview: Live Off, LLM unset (chat copy about configuring LLM from platform map). Live Off owner copy historically tells members to ask the owner (platform map UX note). Newsletters/Mail honest; consumer surfaces less so.

**Current state:** Optionality without a shared status story → member pings owner.

**Root cause:** Operator-only visibility of stack readiness.

**Recommendation:** Lightweight status on Settings or Inbox empty state: “Live is off,” “Curator AI needs owner setup,” “Email alerts off — inbox still works.” Owner controls verbosity.

**Rationale:** Converts tickets into self-serve understanding without forcing features on.

**User story:** As a member, I want to know Live is intentionally off so that I do not ping the owner every evening.

**Acceptance criteria:**
- [ ] Members see non-alarmist status for Live Off / LLM unset / Mail off.
- [ ] No Admin deep links required for members.

**Success metric:** Owner-reported “is Live broken?” asks down after ship.

**Validation:** Member session screenshots for the three Off states.

---

### OPS-017: Extend owner action audit beyond grooming

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Admin |
| Persona(s) | Owner |
| Category | Escalation & safety |
| Severity | Medium |
| Impact | 3 |
| Effort | L |
| Confidence | Confirmed |
| Priority score | 1.2 |
| Verdict | Add |
| Dependencies | OPS-015, OPS-016 |
| Labels | audit, compliance, support |

**Evidence:** `grooming_action_log` exists (`projectionist/library/db/_grooming.py`). No general admin audit for role changes, invites, Youth toggles, Access approve/deny found in owner UI. Youth page is review-only for memory.

**Current state:** Disk/index destructive acts are auditable; people-desk acts are not.

**Root cause:** Audit built for purge first.

**Recommendation:** Append-only `admin_action_log` for invite create/revoke, access approve/deny, role/youth/disable/remove, password reset. Surface last 50 on Members or Advanced.

**Rationale:** Without this, household disputes (“who removed X?”) become SQLite archaeology.

**User story:** As an owner, I want a trail of people-desk actions so that I can explain what changed last week.

**Acceptance criteria:**
- [ ] Listed action types are recorded with actor + timestamp.
- [ ] Owner can view recent actions in Admin.

**Success metric:** Support questions about “who changed Youth” answered from UI without DB queries.

**Validation:** Perform Access deny + Youth toggle; see rows.

## 15. Opportunities

### OPS-030: Ship an interactive Monday pass checklist

| Field | Value |
|---|---|
| Type | Opportunity |
| Surface | Owner |
| Persona(s) | Established owner |
| Category | Owner maintenance |
| Severity | High |
| Impact | 4 |
| Effort | M |
| Confidence | Likely |
| Priority score | 3.2 |
| Verdict | Add |
| Dependencies | OPS-001, OPS-012, OPS-021 |
| Labels | monday-pass, checklist |

**Evidence:** Hero is narrative-only today (`OwnerHealthHero.tsx`); Delight wishlist already sketches opened-kinship observables (`docs/DELIGHT-WISHLIST.md` Monday pass notes via `git grep`).

**Current state:** Owner must remember the order; nothing records completion.

**Root cause:** Story shipped before checklist.

**Recommendation:** Checklist with four steps, each Done when metric crosses threshold or owner marks reviewed; “Run catch-up” triggers Warm Explore. Persist last completed Monday per install.

**Rationale:** Turns sacred cow into measurable habit.

**User story:** As an owner, I want to check off Monday steps so that I know when I can stop.

**Acceptance criteria:**
- [ ] Four steps with done/pending states.
- [ ] Catch-up action queues Warm Explore tasks.
- [ ] Completion timestamp visible.

**Success metric:** ≥50% of weeks show a completed Monday pass marker on Automat.

**Validation:** Health checklist UI test + task queue assertion.

---

### OPS-031: Add a Secrets & connections health card

| Field | Value |
|---|---|
| Type | Opportunity |
| Surface | Owner |
| Persona(s) | Owner; maintainer |
| Category | Admin tooling |
| Severity | High |
| Impact | 4 |
| Effort | S |
| Confidence | Confirmed |
| Priority score | 6.0 |
| Verdict | Add |
| Dependencies | OPS-010, OPS-011 |
| Labels | secrets, health |

**Evidence:** Same MAC mismatch + Connected contradiction. Snapshot copy already mentions secrets key (`OverviewSection.tsx`). QA Overview and Health showed Plex/index/Live tiles and the Monday pass hero, not a secrets-key or certification-disagreement card (`ops_admin_overview_1440.png`, `ops_admin_health_monday_pass_1440.png`).

**Current state:** The owner can download a snapshot that says to keep `PROJECTIONIST_SECRETS_KEY`, and can open Logs or Connections, but no Admin home surface answers “is the secrets key usable, and which Connected badges disagree with the key that is actually set?”

**Root cause:** Certification, decrypt warnings, and backup copy were built as separate features. Nothing aggregates them into one operator card.

**Recommendation:** Card on Overview/Health: secrets key OK/fail; per-service set-bit vs certified vs last probe; CTA to Connections Test.

**Rationale:** Makes OPS-010/011 visible without opening Logs.

**User story:** As an owner, I want secrets health beside Plex health so that backups and keys stay paired.

**Acceptance criteria:**
- [ ] Card reflects MAC mismatch state.
- [ ] Lists services where certified XOR key-set disagree.

**Success metric:** Secrets incidents detected from Overview without Logs.

**Validation:** Wrong key on QA → card red.

---

### OPS-033: Prefer troubleshooting bundles over impersonation

| Field | Value |
|---|---|
| Type | Opportunity |
| Surface | Admin |
| Persona(s) | Owner; maintainer |
| Category | Escalation & safety |
| Severity | Medium |
| Impact | 3 |
| Effort | M |
| Confidence | Likely |
| Priority score | 1.6 |
| Verdict | Add |
| Dependencies | OPS-004, OPS-019 |
| Labels | support, export, privacy |

**Evidence:** No impersonation (OPS-004). Full snapshot is too heavy/sensitive for chat support. Overview offers only “Download taste data” and “Download snapshot zip” (`OverviewSection.tsx`; `ops_admin_overview_1440.png`).

**Current state:** Remote help is either “look at my screen,” SSH, or a household snapshot/taste zip. There is no redacted bundle of versions, skip reasons, and error fingerprints.

**Root cause:** Backup exports were designed for the owner’s own restore, not for a maintainer who must not see chat text, tokens, or member emails. Impersonation was correctly never built, and nothing replaced it for diagnosis.

**Recommendation:** “Download troubleshooting bundle”: redacted settings (booleans/hosts only), recent ERROR fingerprints, task skip reasons, versions/digests — **no** chat text, tokens, or member emails.

**Rationale:** Solves remote support without view-as.

**User story:** As a maintainer helping an owner, I want a safe bundle so that I can diagnose without household chat logs.

**Acceptance criteria:**
- [ ] Bundle contains no raw secrets or message bodies.
- [ ] Documented in HELP owner half.

**Success metric:** Bundle used in ≥3 maintainer assists without snapshot zips.

**Validation:** Inspect zip contents in QA.

---

### OPS-034: Add a household status strip for optional surfaces

| Field | Value |
|---|---|
| Type | Opportunity |
| Surface | Consumer |
| Persona(s) | Member; owner |
| Category | Communication |
| Severity | Medium |
| Impact | 3 |
| Effort | S |
| Confidence | Likely |
| Priority score | 2.4 |
| Verdict | Add |
| Dependencies | OPS-023, OPS-007 |
| Labels | status, live, mail, llm |

**Evidence:** Overview already encodes Live Off for owners; members lack parity (OPS-023). QA Overview showed an Off Live card; Mail and Newsletters explained email-off only inside Admin (`ops_admin_overview_1440.png`, `ops_admin_newsletters_1440.png`). Primary nav hides Live when stations are not ready rather than saying why.

**Current state:** Owners see Live Off, LLM unset, and Mail off on Admin pages. Members get an empty or missing Live entry and chat copy that tells them to ask the owner, with no shared strip for Live / Curator AI / Email.

**Root cause:** Optional surfaces were designed as owner setup, not as household status. Member chrome omits Admin, so the only status that exists never reaches the people who generate the tickets.

**Recommendation:** Compact strip under primary nav or Inbox: Live / Curator AI / Email — On, Off, or Needs owner. Owner can disable strip.

**Rationale:** Cheap ticket deflection.

**User story:** As a member, I want a glanceable stack status so that I understand empty Live without asking.

**Acceptance criteria:**
- [ ] Strip reflects Live ready, LLM configured, Mail enabled.
- [ ] Owner can hide it.

**Success metric:** Reduction in Live Off “is it broken?” owner pings.

**Validation:** Member screenshots for Off/On matrices.

## 16. Remediation plan

### Now (0–2 weeks)

| ID | Title | Effort | Owner role | Dependencies |
|---|---|---|---|---|
| OPS-011 | Connected ✓ honesty | S | Eng | OPS-010 |
| OPS-010 | MAC mismatch single fault | M | Eng | — |
| OPS-014 | Access age + bulk deny | S | Eng | — |
| OPS-013 | HELP Health naming | S | Docs | — |
| OPS-019 | Export confirm warnings | XS | Eng | — |
| OPS-021 | Overview Monday CTA | S | Eng | OPS-001 |

### Next (2–6 weeks)

| ID | Title | Effort | Owner role | Dependencies |
|---|---|---|---|---|
| OPS-031 | Secrets health card | S | Eng | OPS-010/011 |
| OPS-012 | Tasks catch-up shortlist | M | Eng | OPS-030 |
| OPS-030 | Monday checklist | M | Eng/Product | OPS-001 |
| OPS-015 | Members destructive hardening | M | Eng | OPS-017 |
| OPS-016 | Owner password reset | M | Eng | — |
| OPS-020 | Log aggregation | M | Eng | OPS-010 |
| OPS-023/034 | Household status | S–M | Eng | OPS-007 |
| OPS-018 | Image identity in footer | S | Eng/Ops | — |

### Later (6+ weeks)

| ID | Title | Effort | Owner role | Dependencies |
|---|---|---|---|---|
| OPS-017 | Admin action audit | L | Eng | OPS-015 |
| OPS-033 | Troubleshooting bundle | M | Eng | OPS-004 |

**Sequencing:** Truth (011/010/031) before ritual polish (012/030); people-desk safety (014/015/016) before audit (017).

## 17. Quick wins

| ID | Why |
|---|---|
| OPS-019 | XS confirm modal |
| OPS-013 | Docs string sweep |
| OPS-021 | One Overview CTA |
| OPS-014 | Age label + bulk deny |
| OPS-011 | Gate badge on `*_api_key_set` |

## 18. Open questions

1. Should local-password recovery create a new invite (revoking old sessions) or set a temporary password displayed once?
2. Is auto-expire of Access requests at 14 days acceptable, or deny-only?
3. Should Overview **replace** Health as Monday home, or only deep-link?
4. For Automat, is showing image digest on prod Overview desirable, or maintainer-only via Logs/Advanced?
5. When LLM is unset, should member chat hide entirely or keep library-grounded non-LLM replies with status strip?

---

## Limits

- Code cites only via `git show`/`git grep` on **`94fcd3f`** (laptop tree ~36 commits behind).
- QA Path A — not Hub CA proof; Live stayed Off; LLM unset; Mail off.
- Snapshot/taste exports not downloaded.
- No other department review docs read.
- No application code and no `_status.md` edits in this department pass.
