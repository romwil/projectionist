# 05 · Growth, Content & Analytics — Projectionist 360° review, run 2026-11-01

**Reviewer:** Growth, Content & Analytics Lead (`GRO`) · **Code:** `05274cf` (v1.38.0), read from `/tmp/review360-05274cf` · **Live:** QA `http://10.10.1.202:8792` (owner session, read-only; one newsletter preview viewed, nothing sent) · **Public pages:** Docker Hub and GitHub API for `romwil/projectionist` (WebFetch, 2026-11-02).

> **Adaptation note.** Projectionist is a private, self-hosted household app. It has no marketing site, pricing, or indexable pages. For this lens, "public site / SEO" means the **acquisition surfaces an owner meets before installing** (GitHub README, Docker Hub listing, Unraid Community Applications template, docs) and the **conversion surfaces a member meets before using it** (invite email, `/join`, `/login`, link previews). "Analytics" means **on-box measurement only**: nothing leaves the server, by design.

---

# Part A — Conclusions & findings

## 1. Bottom line

Projectionist writes better than most self-hosted software, but almost nobody sees that writing before they install it. Inside the app, member copy is warm and honest, and the 1.38.0 measurement work is principled. Login says plainly what the product is (GRO-002). Newsletters skip quiet weeks instead of sending filler (GRO-003). Play attribution counts only picks the server can verify (GRO-001). Everything before that falls short. The Docker Hub page, with 19,298 pulls, is a one-line stub pointing to a repo name that no longer exists (GRO-006). The product describes itself four different ways across README, Hub, Unraid CA, and login (GRO-007). Lifecycle email has no clickable way back into the app and no way out (GRO-008). The invite flow, the single most important growth moment in 1.38.0, has generic, sometimes wrong copy (GRO-009). Measurement has a structural blind spot: the headline "plays from a pick" metric only sees in-browser Play, but most households watch in native Plex apps (GRO-010). **Grade: C.** **Fix first:** the acquisition and invite surfaces (GRO-006, GRO-007, GRO-009, GRO-011), which are cheap. **Protect:** the verified, text-free, on-box attribution model (GRO-001) and the "only write when there is something worth opening" newsletter rule (GRO-003).

## 2. Key conclusions

1. **Distribution copy is the weakest link, and the cheapest to fix.** Docker Hub's full description is literally "Canonical image for Projectionist (formerly CuratorX). See https://github.com/romwil/curatorx", with no categories and zero stars (GRO-006). The Unraid CA Overview spends its card on MIT license history, legacy `curatorx` paths, and a `rollout.sh` workaround (GRO-011). The README leads with "cinema intelligence engine … vector mapping, multi-signal taste modeling … hardened multi-tenant roles" and has no screenshot (GRO-007, GRO-017). These are the only surfaces a prospective owner reads before pulling, and all of them describe an engineering artifact rather than a household benefit. The root cause is that release discipline (Hub-first, CHANGELOG Highlights) covers the *image*, but nothing covers the *listing*. Roadmap: one "listing copy" ticket in **Now**, plus a release-checklist line that keeps it current.

2. **The product has four names for itself and several for its parts.** The four positioning lines are: "Agentic Plex collection curator" (`pyproject.toml:8`), "Cinema intelligence for your personal archive" (README, Hub, CA), "Cinema intelligence for self-hosted Plex: LLM curator, Explore, Lobby Theater kiosks…" (GitHub description), and "your household's private movie and TV companion" (login). Inside the app, the chat agent is "Curator", "The Professor", and "CURATOR" on the same screen. The owner's people page is "Members" in the rail and "Household" as its heading. A "Shelf" is created on a page called "Lists" (GRO-007, GRO-014). The root cause is that no canonical glossary exists. `DOCS_STYLE.md` says to match in-app labels but never fixes what those labels are. Roadmap: adopt the voice guide and glossary in §B-Appendix and treat them as a lint target.

3. **Lifecycle messaging is principled in what it sends but broken in how it lets people respond.** The good part is real: opt-in defaults, quiet weeks skipped, picks must bridge to something the member watched, and a Youth gate on seeds (GRO-003, GRO-005). The broken part: every email body is plain text that ends "go to Settings → Notifications" with no link, because the mailer has no app base URL. Messages carry no `List-Unsubscribe` header. Three different programs (member newsletter, owner weekly letter, owner monthly) share `kind="digest"`, so they cannot be measured or muted separately (GRO-008, GRO-013). On QA only 1 of 5 members has opted in to the newsletter, and nothing in the product invites the other four (GRO-016). Roadmap: fix links and headers (**Now**), split kinds (**Next**), and add one in-context, privacy-safe opt-in prompt (**Next**).

4. **The invite moment, which is what 1.38.0 was for, is under-written.** The invite email subject is "You're invited to join Projectionist", with no inviter and no household name (`invites.py:120`). The join page's lede always says "Sign in with Plex to join", even on installs where Plex sign-in is off, which is the QA configuration. A dead invite says only "This invite is not available." After joining, members are hard-redirected to `/chat`, which bypasses the 1.38.0 default-page logic that sends LLM-less households to Explore (GRO-009). Nobody can see how many invites convert, even though `invite_create` and `invite_redeem` are already written to the security log (GRO-022). Roadmap: **Now** for copy, **Next** for the funnel card.

5. **On-box measurement is now honest but too narrow to steer the product.** Version 1.38.0 added `chat_turn` and `play_start` with server-verified pick attribution. This is the right design, and it is documented truthfully in `PRIVACY.md` (GRO-001). The headline "N plays from a pick", however, only counts in-browser Play. Native-Plex watching, which arrives through webhooks and history ingest, never joins back to what Projectionist recommended. The metric will therefore read near zero in households where Projectionist is working well (GRO-010). Explore, Search, the inbox, newsletters, and invites emit no product events at all. One telemetry table is pruned but never written (GRO-020). Roadmap: the tracking plan in §B-Appendix, built as an owner-visible "Household pulse" (GRO-018) in **Next**.

6. **Voice is an asset for members and a tax for owners.** Member strings mostly follow `DOCS_STYLE.md` and read warmly. Owner surfaces lean on coined jargon: "Named kinship" is the Monday north-star, a "turnstyle view" is a misspelt metaphor exposed to members, and the owner letter talks of "dead weight" and "I will not send a fleet at them". The same letter renders "Tracker (2024) (2024)" and "28885 hours" (GRO-015, GRO-019). The idiom is charming once, but it is opaque to new owners and non-native readers (SC-20). Roadmap: keep the editorial voice for curator replies and letters, and use plain labels for every control and KPI.

7. **A/B testing is the wrong goal here; release-over-release comparison is the right one.** Feature flags are static booleans in `settings.json` (`config_store.py:486-511`). With one household of about five people per install, no experiment will reach significance, and splitting a family into arms is hostile. The useful substitute is a before/after view keyed on `app_version`, which `chat_turn` and `play_start` already carry (GRO-023). Roadmap: **Later**, after the pulse exists.

## 3. Foundations challenged

| Assumption | Evidence for | Evidence against | Verdict | Cost of change | Rationale |
|---|---|---|---|---|---|
| SC-18 Telemetry stays on the box and is enough to steer the product | `ingestion.py:12-15` privacy contract; `attribution.py:1-7`; `PRIVACY.md:245` honest | Maintainer has zero cross-install signal beyond Hub pull count (19,298); on-box counts miss native-Plex watching (GRO-010) | **Keep on-box; Change scope** (widen events, add likely-watch join). **Investigate** an explicit opt-in "count my install" ping (GRO-024) | M | On-box is a brand promise and a moat. Fix coverage before touching the boundary. |
| README "zero-telemetry by design" | No phone-home (`owner_ops.py:3-4`) | `system_telemetry_stream`, `llm_usage`, `security_audit_log` all exist; Admin shows activity counts | **Change** wording to "no phone-home; activity counted on your server only" | XS | An accurate claim survives scrutiny on r/selfhosted; "zero" invites a gotcha thread. |
| SC-17 Weekly comms are welcome, opt-in per channel | Opt-in defaults (`_schema.py:1004`, `service.py:44-64`); quiet-week skip | Programs share `kind="digest"` (GRO-013); no link/unsubscribe (GRO-008); 1/5 opted in (GRO-016) | **Keep opt-in; Change** mechanics | S | Respectful defaults are right; the reach problem is a prompt problem, not a default problem. |
| SC-20 Editorial, idiomatic voice is an asset for all | Curator replies and letters are distinctive; `DOCS_STYLE.md` warm standard | Owner KPIs and controls use coined terms ("Named kinship", "turnstyle", "Purge pressure"); non-native persona (`00` §2.2) | **Change**: voice in content, plain words in controls | S | Voice sells; jargon on buttons costs support time. |
| SC-06 Invite-only 7-day links are the right onboarding | HMAC tokens, one-use, Youth flag shown on join (`JoinPage.tsx:181-184`) | Invite email/join copy is generic or wrong (GRO-009); no funnel visibility (GRO-022) | **Keep model; Change** copy and measurement | S | The mechanism is sound; the words around it decide whether a relative taps through. |
| SC-01 Chat is the front door | Chat drives attributed picks; starters exist | Join redirect hard-codes `/chat` even without an LLM (`JoinPage.tsx:96,153`) | **Keep**, but route joins through `resolveDefaultHome` | XS | First minute after joining is the activation moment. |
| SC-16 Gamification fits | Badges/streaks moved to Settings → Profile (BD-2) | No event shows badges change behaviour | **Investigate** via pulse (badge_earned → next-week return) | S | Measure before cutting or expanding. |
| (added) A/B testing infrastructure is needed for growth | Spec lens asks for experimentation readiness | ~5 people per install; flags are static (`config_store.py:486-511`) | **Remove from roadmap**; use release-over-release comparison (GRO-023) | — | Statistical power is impossible; family members shouldn't be test arms. |
| (added) Docker Hub description can stay a pointer | GitHub README is the "real" doc | Hub is where Unraid/Compose users land; pointer is to a dead repo name (GRO-006) | **Change** | XS | 19k pulls see the stub. |

## 4. If we built it today

Starting from zero, the growth system for a self-hosted household app has three layers:

1. **One positioning sentence**, reused verbatim on GitHub, Hub, CA, the login page, and `pyproject`: *"Projectionist is a private movie-and-TV companion for your Plex household: ask for something to watch, browse your library by mood and connection, and keep everyone's picks separate."* Owner-facing listings add one line about what you need (Plex, Docker; LLM optional). Below that sit a screenshot strip and a 3-step quick start.
2. **An activation path built around the invite.** The owner sends a named invite ("Sam invited you to the Rompala household on Projectionist") with a rich link preview. The member lands on a join page that offers only the configured sign-in methods, then arrives at the right home with three starter actions. Each step emits one on-box event.
3. **An on-box "Household pulse"** with one north-star (picks watched per week) and four guardrails. Every lifecycle program has its own kind, link-back, one-click mute, and seen/click measurement.

The gap is moderate. Layer 1 is mostly copy (XS–S). Layer 2 is copy plus two redirects (S). Layer 3 extends instrumentation that already exists (M). All three are worth closing: together they cost less than one Live Channels feature and they decide whether the 1.38.0 household launch is measurable at all.

## 5. Findings by surface

**Public (acquisition and conversion).** What works: the login page states the product plainly and adapts its lede to the enabled methods (GRO-002). The GitHub topics (`plex`, `self-hosted`, `unraid`, `homelab`, …) are well chosen. What doesn't work: the Docker Hub stub (GRO-006), the CA Overview written as an ops note (GRO-011), and a README that describes the architecture before the benefit, with no screenshot (GRO-007, GRO-017). `index.html` ships only `<title>Projectionist</title>`: no description, no Open Graph tags, no `noindex` (GRO-012). Invite links pasted into a family group chat therefore render as bare URLs, and a public-profile household can be indexed. The invite email and join page are generic or wrong (GRO-009). **Grade: D+.** IDs: GRO-002, 006, 007, 009, 011, 012, 017.

**Consumer (member / youth).** What works: warm, plain member copy in most places; consent-first notifications with clear help text (`NotificationsSettingsPage.tsx:314-336`); newsletters that only write when they have a real bridge (GRO-003, GRO-005). What doesn't work: naming drift (Curator / The Professor; Shelves vs Lists) (GRO-014); member-visible jargon ("Expand N titles in turnstyle view", `beyondSearch.ts:134`) (GRO-015); a Live empty state that tells members to "enable Live Channels in Admin" (`liveChannelsCopy.ts:31`); emails with no link back (GRO-008); and almost no members opted in (GRO-016). **Grade: C+.** IDs: GRO-003, 005, 008, 013, 014, 015, 016.

**Owner.** What works: the Newsletters page explains every send and states opt-in counts honestly ("1 of 5 loaded members currently opted in", live `gro_admin-newsletters-letter-preview_owner.png`). On-box activity appears on Overview (GRO-001). What doesn't work: the KPI vocabulary ("Named kinship", "Purge pressure"), letter render defects (GRO-015, GRO-019), no invite funnel (GRO-022), and a "plays from a pick" number that will read near zero for households that watch on TVs (GRO-010). **Grade: C.** IDs: GRO-001, 010, 015, 018, 019, 022.

**Admin / Ops.** Telemetry plumbing is split across `system_telemetry_stream` (product events), `telemetry_events` (closed-loop augmentation), and a dead `interaction_telemetry` table that is pruned but never written. `telemetry_enabled` is a hidden config key with no UI (GRO-020). Release notes leak internal review IDs (`SEC-001`, `GRO-007`, …) into public CHANGELOG sections (GRO-021). **Grade: C.** IDs: GRO-020, 021, 023, 024.

## 6. Findings by theme

**Positioning & listings.** Best: the login product statement (`loginScreen.ts:28-29`). Worst: Docker Hub (GRO-006). Direction: one sentence everywhere (GRO-007), a CA card written for the store (GRO-011), and a README with a screenshot and a "what you need" box (GRO-017).

**Microcopy & voice.** Best: notification toggles' help text, and the "Quiet week" honesty. Worst: "Expand 12 titles in turnstyle view", and the owner letter's "dead weight … send a fleet". Direction: the voice & tone guide and the 10 rewrites in §B-Appendix (GRO-014, GRO-015).

**Lifecycle messaging.** Best: opt-in plus skip-empty (GRO-003). Worst: no clickable path back or out (GRO-008). Direction: base URL, deep links, `List-Unsubscribe`, per-program kinds (GRO-013), and an in-context opt-in card (GRO-016).

**Analytics & instrumentation.** Best: verified attribution (GRO-001). Worst: the native-Plex blind spot (GRO-010). Direction: the tracking plan, surfaced as the Household pulse (GRO-018) and an invite funnel (GRO-022).

**Experimentation.** Static flags; no A/B. Direction: don't build A/B; compare releases (GRO-023).

## 7. Stop doing

- **Stop claiming "zero-telemetry".** Say "no phone-home; activity is counted on your server and shown to you" (GRO-007).
- **Stop using the Docker Hub description and CA Overview as changelogs or ops notes.** MIT history, legacy paths, and `rollout.sh` belong in the wiki (GRO-006, GRO-011).
- **Stop putting internal review IDs in public release notes.** Keep them in commit messages and PRs (GRO-021).
- **Stop adding coined terms to controls and KPIs.** No new "kinship"/"turnstyle"-style labels without a glossary entry (GRO-015).
- **Stop reusing `kind="digest"` for new programs** (GRO-013).
- **Stop carrying dead telemetry plumbing** (`interaction_telemetry`) (GRO-020).
- **Do not build A/B infrastructure** (GRO-023).

## 8. Strengths worth protecting

- **Verified, text-free attribution** (GRO-001). A pick only counts when the server can prove the card was shown to that viewer. Never infer picks from Plex history *as verified*. GRO-010 adds a separate, clearly labelled "likely" tier and does not loosen this one.
- **The login product statement** (GRO-002). It survives custom domains and white-label households.
- **Newsletter honesty rules** (GRO-003): skip empty weeks, require a specific watched bridge, apply the Youth gate.
- **The docs standard and benefit-led Highlights** (GRO-004). The 1.38.0 Highlights are a model of release copy.
- **Consent-first defaults** (GRO-005): newsletter, nudges, and Year in Review are opt-in; email needs both a channel toggle and a program opt-in.

## 9. Risks of inaction (6–12 months)

- **Acquisition stalls at the listing.** CA and Hub browsers bounce off a stub and a jargon card. Pull counts keep rising from existing installs auto-updating, which masks the problem.
- **The household launch can't be judged.** Without an invite funnel or a pick-watched metric, the maintainer can't tell whether 1.38.0 grew active members or just added accounts. Product decisions on Live, gamification, and newsletters stay opinion-based.
- **Email reputation and trust erode.** Unlinked, header-less newsletters get flagged as spam by Gmail and Yahoo, whose bulk-sender rules expect one-click unsubscribe, and members who can't find the off switch mark them as junk. Owners then disable mail entirely.
- **"Zero-telemetry" becomes a credibility incident** once someone finds `system_telemetry_stream` in the schema.

## 10. Recommended direction

**Sequence:** (1) Fix every acquisition and invite string (copy only, one PR, **Now**). (2) Fix email links and headers and split notification kinds (**Now/Next**). (3) Ship the Household pulse with the north-star and guardrails, plus the invite funnel (**Next**). (4) Release-over-release comparison and a decision on an opt-in install count (**Later**).

**Success in 90 days:**
- Docker Hub, CA Overview, GitHub, README, and login all open with the same sentence: 5 of 5 surfaces.
- Invite redemption rate is visible on Admin and is ≥ 70% within 7 days on the maintainer household.
- Every lifecycle email has a working deep link and `List-Unsubscribe`, with a 0% "can't find unsubscribe" support rate.
- Newsletter opt-in is ≥ 50% of active members on prod, through the in-context prompt, without changing the default.
- "Picks watched / week" (verified + likely) is reported on Overview and is non-zero on prod.

## 11. Scorecard (1–5)

| Surface | Positioning clarity | Microcopy & voice | Lifecycle messaging | Measurement | Experimentation | Reason |
|---|---|---|---|---|---|---|
| Public | 2 | 3 | 2 | 1 | n/a | Strong login line; weak Hub/CA/README; invite copy generic; no invite funnel |
| Consumer | 3 | 4 | 2 | 2 | n/a | Warm copy; drift and jargon; emails can't be acted on |
| Owner | 3 | 2 | 3 | 3 | 1 | Honest newsletter console; jargon KPIs; pick metric undercounts |
| Admin/Ops | n/a | 3 | n/a | 2 | 1 | Split/dead telemetry tables; IDs in release notes |

---

# Part B — Detailed findings

## 12. Scope & method

- **Read:** README, CHANGELOG 1.38.0, `docs/DOCS_STYLE.md`, `docs/PRIVACY.md` telemetry sections, `templates/projectionist.xml`, `frontend/index.html`, login/join/notifications/lists/live copy, `projectionist/notifications/*`, `projectionist/mail/transport.py`, `projectionist/invites.py`, `projectionist/telemetry/*`, `projectionist/library/db/_owner_ops.py`, `scheduler/tasks/*` comms cadences, `config_store.py` feature flags.
- **Live (QA :8792, owner, read-only):** `/admin/newsletters`, where the weekly letter preview is rendered inline on page load. Screenshot `screenshots/gro_admin-newsletters-letter-preview_owner.png`. Nothing was sent, saved, or triggered. No chat prompt was used.
- **Web:** Docker Hub repository API and GitHub repository API for `romwil/projectionist`.
- **Not reviewed:** actual delivered emails (mail is not configured on QA), Apprise rendering, a member or youth session, the Unraid CA store rendering, real usage data (QA shows 0 activity in 7 days), and the What's New modal generator.

## 13. Strengths

### GRO-001: Protect verified, text-free on-box attribution

| Field | Value |
|---|---|
| Type | Strength |
| Surface | Cross-cutting |
| Persona(s) | Established owner, all members |
| Category | Analytics & instrumentation |
| Severity | High |
| Impact | 5 |
| Effort | XS |
| Confidence | Confirmed |
| Priority score | 15 |
| Verdict | Protect |
| Dependencies | Basis for GRO-010, GRO-018 |
| Labels | telemetry, privacy, attribution |

**Evidence:** `05274cf:projectionist/telemetry/attribution.py:1-7,83-110` (claim counts only if the stored assistant card or household recommendation carried that rating key for that viewer); `05274cf:projectionist/telemetry/ingestion.py:12-15,216-267` (`chat_turn` and `play_start` are counts and IDs, "no message text"); `05274cf:docs/PRIVACY.md:74,245` (accurately describes it, 90-day retention, included in export/purge); `05274cf:projectionist/library/db/_owner_ops.py:208-237`.

**Current state:** Chat turns and in-app plays are recorded without content, attribution can't be spoofed by the client, and owners see household totals only.

**Root cause:** Deliberate design from the previous review (GRO-007/014 of 2026-10-28) carried through carefully.

**Recommendation:** Protect. Any new event must follow the same contract: IDs, counts, durations, and enums only; no free text; a `user_id` that the member can export and purge; and owners see only aggregates.

**Rationale:** This is what lets Projectionist measure itself without breaking its privacy promise. Loosening it to "improve" numbers would cost more trust than it gains.

**User story:** As a member, I want my activity counted without my words being stored so that I can trust the household app.

**Acceptance criteria:**
- [ ] A test asserts that no `system_telemetry_stream` payload contains keys like `text`, `message`, `prompt`, or `content`.
- [ ] Every new event class is listed in `PRIVACY.md` in the same release.

**Success metric:** 0 privacy regressions in telemetry payloads per release.

**Validation:** Run the payload-key test; diff `PRIVACY.md` against `ingestion.py` event constants.

### GRO-002: Protect the login page's plain product statement

| Field | Value |
|---|---|
| Type | Strength |
| Surface | Public |
| Persona(s) | Invited member (first-time visitor) |
| Category | Positioning |
| Severity | Medium |
| Impact | 4 |
| Effort | XS |
| Confidence | Confirmed |
| Priority score | 8 |
| Verdict | Protect |
| Dependencies | GRO-007 reuses it |
| Labels | copy, login |

**Evidence:** `05274cf:frontend/src/lib/loginScreen.ts:22-49`. The statement reads "Projectionist is your household's private movie and TV companion — chat for recommendations, browse the library, and watch together.", followed by a method-aware action line.

**Current state:** The clearest value proposition in the whole product, and the only one written for a member.

**Root cause:** Explicit PRD-004 decision in the code comment.

**Recommendation:** Protect, and promote it to the canonical positioning line (see GRO-007).

**Rationale:** It works on a custom domain where the brand name may never appear.

**User story:** As an invited relative, I want to know what this page is before I type a password so that I trust it.

**Acceptance criteria:**
- [ ] Login renders the statement for every auth-method combination (existing unit test stays green).

**Success metric:** Same sentence reused on ≥ 4 external surfaces (GRO-007).

**Validation:** `npm run test:unit` for `loginScreen`.

### GRO-003: Protect the "only write when it's worth opening" newsletter rules

| Field | Value |
|---|---|
| Type | Strength |
| Surface | Consumer |
| Persona(s) | Returning member, youth |
| Category | Lifecycle messaging |
| Severity | Medium |
| Impact | 4 |
| Effort | XS |
| Confidence | Confirmed |
| Priority score | 8 |
| Verdict | Protect |
| Dependencies | — |
| Labels | newsletter, youth, relevance |

**Evidence:** `05274cf:projectionist/notifications/newsletters.py:180-205` (picks must be unwatched and carry a specific `watched_bridge` sentence; Youth gate on every row); `:266-273` (quiet weeks are skipped: "a 'nothing for you' note teaches members to ignore the inbox"); `05274cf:CHANGELOG.md:37`.

**Current state:** Relevance beats cadence, and members only hear from it when there is a real reason.

**Root cause:** Good editorial judgment, encoded in code.

**Recommendation:** Protect. Apply the same rule to the owner weekly letter and the owner monthly note, which today send regardless.

**Rationale:** Low-frequency, high-relevance messaging is what keeps opt-ins from churning.

**User story:** As a member, I want the newsletter only when it has something for me so that I keep reading it.

**Acceptance criteria:**
- [ ] The test for `skipped_empty` stays green.
- [ ] The Youth gate test covers newsletter picks.

**Success metric:** Opt-out rate < 10% per quarter among opted-in members.

**Validation:** Existing pytest coverage for `deliver_weekly_newsletters`.

### GRO-004: Protect the docs standard and benefit-led release Highlights

| Field | Value |
|---|---|
| Type | Strength |
| Surface | Cross-cutting |
| Persona(s) | New owner, members (What's New) |
| Category | Content |
| Severity | Medium |
| Impact | 3 |
| Effort | XS |
| Confidence | Confirmed |
| Priority score | 6 |
| Verdict | Protect |
| Dependencies | GRO-021 |
| Labels | docs, release-notes |

**Evidence:** `05274cf:docs/DOCS_STYLE.md:14-40` (rubric plus audience and voice matrix); `05274cf:CHANGELOG.md:7-13` ("Ready to invite your household…" plus four benefit-led Highlights).

**Current state:** A durable standard exists and is applied to release notes.

**Root cause:** Docs treated as a first-class deliverable.

**Recommendation:** Protect. Extend the standard with the glossary and voice guide in §B-Appendix, and with a "listing copy" checklist item (GRO-006, GRO-011).

**Rationale:** The standard is the lever that keeps every rewrite in this document from drifting back.

**User story:** As an owner upgrading, I want to know what changed for my household in one paragraph so that I can tell them.

**Acceptance criteria:**
- [ ] Every release has a lede paragraph plus `### Highlights`.

**Success metric:** 100% of releases.

**Validation:** Release checklist review.

### GRO-005: Protect consent-first notification defaults

| Field | Value |
|---|---|
| Type | Strength |
| Surface | Consumer |
| Persona(s) | All members, youth |
| Category | Lifecycle messaging |
| Severity | Medium |
| Impact | 3 |
| Effort | XS |
| Confidence | Confirmed |
| Priority score | 6 |
| Verdict | Protect |
| Dependencies | GRO-016 must not flip defaults |
| Labels | consent, notifications |

**Evidence:** `05274cf:projectionist/library/db/_schema.py:1004` (`newsletter_opt_in` defaults to 0); `05274cf:projectionist/notifications/service.py:39-64` (nudges and Year in Review need their own opt-in; email needs a channel toggle plus program opt-in); `05274cf:frontend/src/pages/settings/NotificationsSettingsPage.tsx:314-336` (clear help text).

**Current state:** Nothing promotional reaches a member who hasn't asked for it.

**Root cause:** Privacy-by-default stance.

**Recommendation:** Protect. Grow reach through an explicit prompt (GRO-016), not by flipping defaults.

**Rationale:** In a family app, an unwanted email costs the owner more trust than one more reader is worth.

**User story:** As a member, I want to choose what lands in my email so that the app never feels pushy.

**Acceptance criteria:**
- [ ] New accounts have newsletter, nudge, and Year in Review opt-ins off.

**Success metric:** 0 complaints about unsolicited email.

**Validation:** Create a member in a test; assert defaults.

## 14. Weaknesses (sorted by priority score)

### GRO-006: Replace the Docker Hub stub that points to the old repo

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Public |
| Persona(s) | New owner (homelabber) |
| Category | Positioning & listings |
| Severity | High |
| Impact | 4 |
| Effort | XS |
| Confidence | Confirmed |
| Priority score | 12 |
| Verdict | Fix |
| Dependencies | GRO-007 (sentence) |
| Labels | docker-hub, listing, acquisition |

**Evidence:** `GET https://hub.docker.com/v2/repositories/romwil/projectionist/` (2026-11-02): `description` = "Cinema intelligence for your personal archive (Projectionist).", `full_description` = "Canonical image for Projectionist (formerly CuratorX). See https://github.com/romwil/curatorx", `categories: []`, `star_count: 0`, `pull_count: 19298`, `last_modified: 2026-07-25` (never updated since registration).

**Current state:** The page most Compose/Unraid users land on has no description, quick start, screenshots, or tags guidance, and links to a renamed repo.

**Root cause:** `scripts/docker-release.sh` pushes images but never pushes the repository README. No release step owns the listing.

**Recommendation:** Add `docs/DOCKERHUB.md` (≤ 25 KB, Hub limit) containing the positioning sentence (GRO-007), a "What you need" box (Plex Media Server; Docker or Unraid; optional LLM key or Ollama), one screenshot, the 3-line `docker run` with `PROJECTIONIST_SESSION_SECRET`, the tag table, and links to the GitHub README and Unraid wiki. Push it on each release with `docker pushrm romwil/projectionist --file docs/DOCKERHUB.md` or the Hub API `PATCH /v2/repositories/romwil/projectionist/` (`full_description`), from `docker-release.sh`. Set the Hub category to the closest media category Hub offers. Short description, 100 characters: "Private movie & TV companion for your Plex household — chat picks, Explore, Live. Self-hosted."

**Rationale:** It's XS effort on the highest-traffic acquisition surface. Rejected alternative: "link to GitHub" (today's state), which loses users who never click through.

**User story:** As a homelabber browsing Docker Hub, I want to see what this does and how to run it so that I decide to pull it.

**Acceptance criteria:**
- [ ] Hub `full_description` matches `docs/DOCKERHUB.md` after a release.
- [ ] No reference to `romwil/curatorx` on the Hub page.
- [ ] The release checklist in `docs/RELEASE.md` includes "Hub description pushed".

**Success metric:** Hub stars > 0 and GitHub referral traffic from hub.docker.com visible in GitHub Insights within 60 days.

**Validation:** `curl` the Hub API and diff against the file.

### GRO-007: Adopt one positioning sentence and drop the "zero-telemetry / multi-tenant" claims

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Public |
| Persona(s) | New owner, invited member |
| Category | Positioning & listings |
| Severity | High |
| Impact | 4 |
| Effort | S |
| Confidence | Confirmed |
| Priority score | 6 |
| Verdict | Fix |
| Dependencies | Blocks GRO-006, GRO-011, GRO-017 |
| Labels | positioning, readme, trust |

**Evidence:** `05274cf:pyproject.toml:8` ("Agentic Plex collection curator with BYOP LLM, RAG, and Radarr/Sonarr integration"); `05274cf:README.md:8-10` ("Cinema intelligence for your personal archive… cinema intelligence engine… vector mapping, multi-signal taste modeling, MCP access, and hardened multi-tenant roles"); `05274cf:README.md:204-206` ("zero-telemetry by design"); GitHub description ("Cinema intelligence for self-hosted Plex: LLM curator, Explore, Lobby Theater kiosks, Live Channels, dual-key MCP"); `05274cf:templates/projectionist.xml:14`; `05274cf:frontend/src/lib/loginScreen.ts:28-29`.

**Current state:** Four framings. Two claims are inaccurate. "Multi-tenant" is wrong because the product has one household per install (SC-03). "Zero-telemetry" is wrong because on-box activity is recorded (GRO-001).

**Root cause:** No canonical positioning artifact. Each surface was written at a different time for a different audience.

**Recommendation:** Canonical sentence (all surfaces): **"Projectionist is a private movie-and-TV companion for your Plex household: ask for something to watch, browse your library by mood and connection, and keep everyone's picks their own."** Use it as the README H1 subtitle, the GitHub description (trimmed to "Private movie & TV companion for your Plex household — chat picks, Explore, Live channels. Self-hosted, Unraid/Docker."), the Hub short description, the CA Overview opener, and `pyproject` description. Replace "zero-telemetry by design" with "**No phone-home.** Activity (chat turn counts, plays started here) is counted on your server, shown only to you, and kept 90 days. See Privacy." Replace "hardened multi-tenant roles" with "owner, member, and Youth accounts for one household". Move the architecture paragraph and diagram below Quick start.

**Rationale:** Consistency compounds recognition. Accurate privacy claims are the brand's core asset with self-hosters. Rejected alternative: keep "cinema intelligence" as the hook. It is memorable but says nothing about who it's for.

**User story:** As a prospective owner, I want to understand in one sentence what this does for my family so that I install it.

**Acceptance criteria:**
- [ ] The same sentence (or the documented short form) appears on README, Hub, CA, GitHub, `pyproject`.
- [ ] `rg -i "zero-telemetry|multi-tenant" README.md docs/` returns nothing.

**Success metric:** 5/5 surfaces aligned. README → Quick start click-through visible in GitHub traffic.

**Validation:** Grep plus a manual check of the Hub and GitHub pages.

### GRO-008: Give every lifecycle email a working link back and a one-click way out

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Consumer |
| Persona(s) | Returning member, owner |
| Category | Lifecycle messaging |
| Severity | High |
| Impact | 4 |
| Effort | S |
| Confidence | Confirmed |
| Priority score | 6 |
| Verdict | Fix |
| Dependencies | GRO-013 |
| Labels | email, unsubscribe, deliverability |

**Evidence:** `05274cf:projectionist/notifications/newsletters.py:61-65,212` (footer "To change or stop these notes, go to Settings → Notifications." as plain text, no URL); `05274cf:projectionist/mail/transport.py:64-94` (HTML is the escaped text in a `<p>`; no links unless a caller passes `body_html`); `:97-110` (SMTP headers: Subject, From, To only; no `List-Unsubscribe`); `rg -n "List-Unsubscribe" projectionist` returns nothing. No app base URL setting exists for mail (only `household_domain` for invites, `05274cf:projectionist/invites.py:108-113`).

**Current state:** A member reading the newsletter on a phone can't tap a pick or the settings page. Gmail and Yahoo bulk-sender rules expect `List-Unsubscribe` plus `List-Unsubscribe-Post`, and missing them pushes mail toward spam.

**Root cause:** The mail layer was built as a transport. Nothing owns the "rendered lifecycle email" template, and the server doesn't know its public URL.

**Recommendation:**
1. Resolve `app_base_url` from `household_domain` (already used for invites), else the request origin captured at owner's last admin visit, else omit links with a visible "Open Projectionist on your home network" line.
2. Add `render_lifecycle_email(kind, title, picks, footer)` that outputs HTML with one deep link per pick (`{base}/title/{media_type}/{id}?rec=digest:{notification_id}`), an "Open your inbox" button (`{base}/inbox`), and a footer link to `{base}/settings/notifications#{kind}`.
3. Add headers `List-Unsubscribe: <{base}/api/notifications/unsubscribe?t={signed}>` and `List-Unsubscribe-Post: List-Unsubscribe=One-Click`, using an HMAC token scoped to (user, kind) with no session needed. Add the endpoint to the unauthenticated allowlist; POST flips only that program's opt-in.
4. Mirror the same links into Apprise bodies.

**Rationale:** Email is the only re-engagement channel that reaches a member who isn't in the app. Rejected alternative: tell owners to add footer text in Mail settings. That isn't per-user, isn't one-click, and isn't measurable.

**User story:** As a member reading the newsletter on my phone, I want to tap a pick or turn the newsletter off so that email is useful, not noise.

**Acceptance criteria:**
- [ ] Newsletter, Year in Review, arrival, and nudge emails contain ≥ 1 absolute link when `app_base_url` is set.
- [ ] SMTP and Resend messages carry `List-Unsubscribe` and `List-Unsubscribe-Post`.
- [ ] One-click POST turns off only that program for that user, and is recorded in the security log.
- [ ] Tokens are rejected after a purge or for another user.

**Success metric:** Email click-through rate (GRO-018) ≥ 15% of delivered newsletters. Spam-folder reports: 0.

**Validation:** pytest renders an email and asserts headers and links. Send a test to a Gmail account and check "Unsubscribe" appears beside the sender.

### GRO-009: Rewrite the invite email and join page around who invited you and how you'll sign in

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Public |
| Persona(s) | Invited member, youth's parent |
| Category | Activation / microcopy |
| Severity | High |
| Impact | 4 |
| Effort | S |
| Confidence | Confirmed |
| Priority score | 6 |
| Verdict | Fix |
| Dependencies | GRO-012 (link preview), GRO-022 |
| Labels | invite, join, activation |

**Evidence:**
- `05274cf:projectionist/invites.py:117-130`: subject "You're invited to join Projectionist", body "You've been invited to join a Projectionist household." No inviter, no household name, no expiry date.
- `05274cf:projectionist/invites.py:54-64`: `public_invite_view` exposes no inviter display name or household label, so `/join` can't show one.
- `05274cf:frontend/src/pages/JoinPage.tsx:163-171`: lede is always "Sign in with Plex to join. Username and password is a fallback on the same link.", even when `plexEnabled` is false (QA is local-only per `00` §1). Invalid state: "This invite is not available." with no next step.
- `05274cf:frontend/src/pages/JoinPage.tsx:96,153`: `navigate("/chat")` after joining, bypassing `resolveDefaultHome` (Explore when no LLM, `CHANGELOG.md:25`).

**Current state:** The 1.38.0 launch moment reads like a system notification, may tell users to use a method that isn't offered, and may drop them into a chat with no provider.

**Root cause:** Invite copy was written in the security/trust phases, focused on correctness. Nothing in the flow is written from the relative's point of view.

**Recommendation:**
- Add `inviter_name` (the owner's display name) and `household_label` (`household_domain` or a new "Household name" setting, default "{owner}'s household") to `public_invite_view` and the email.
- Email subject: **"{Inviter} invited you to {Household} on Projectionist"**. Body: the positioning sentence, then "Your link works once and expires {date}.", then the button "Accept invite".
- Join lede, computed from methods: the Plex-only version is "Use your Plex account to join — it takes about a minute." The local-only version is "Choose a username and password to join." With both enabled, show the Plex version plus "No Plex account? Choose a username and password instead."
- Invalid invite: "This invite has expired or was already used. Ask {inviter|the person who sent it} for a new link — it takes them a few seconds." Show "Request access" if `access_requests_enabled`.
- Post-join: `navigate(resolveDefaultHome(features, user))` with the `?welcome=1` first-run hint.

**Rationale:** A named sender is the strongest open-rate signal for personal invites. Correct method copy prevents the most likely "it doesn't work" text to the owner. Rejected alternative: a generic welcome tour. It adds steps before value.

**User story:** As a relative who got a link in a text, I want to see who invited me and exactly how to get in so that I join without calling them.

**Acceptance criteria:**
- [ ] With local-only auth, the join page never mentions Plex.
- [ ] The email subject contains the inviter's display name.
- [ ] An expired invite shows the inviter name and a next step.
- [ ] After joining on an install without an LLM, the member lands on `/explore`.

**Success metric:** Invite redeem rate within 7 days ≥ 70% (GRO-022); "how do I join" owner support pings → 0.

**Validation:** Playwright join specs for plex-only, local-only, and both; a unit test on the email builder.

### GRO-011: Rewrite the Unraid CA Overview as a store card

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Public |
| Persona(s) | New owner (Unraid) |
| Category | Positioning & listings |
| Severity | Medium |
| Impact | 3 |
| Effort | XS |
| Confidence | Confirmed |
| Priority score | 6 |
| Verdict | Fix |
| Dependencies | GRO-007 |
| Labels | unraid, ca, listing |

**Evidence:** `05274cf:templates/projectionist.xml:14`. The Overview runs ~90 words: the first sentence is good, then come "Keep port 8788 on a trusted LAN…", "Releases through 1.36.2 were MIT", "legacy …/curatorx/config OK if never migrated", and "if Force Update shows 0 B pulled, SSH `docker pull`… or appdata `./rollout.sh`". `templates/` and `unraid/` copies are identical (`diff -q` clean), so both need the change.

**Current state:** CA search results show the start of Overview. Most of the card is migration and ops trivia.

**Root cause:** Overview is used as a changelog for existing installers.

**Recommendation:** Overview (≤ 450 characters): "**Private movie & TV companion for your Plex household.** Ask for something to watch in plain words, browse your library by mood and connection, run your own Live channels, and send a weekly newsletter — each family member gets their own picks. Needs Plex; an LLM key (or Ollama) is optional. Keep it on your LAN or behind an authenticated proxy." Move license history, legacy paths, and update tips into `docs/wiki/Unraid.md` (already the `<Readme>`). Add `<Screenshot>` entries (two PNGs under `unraid/`) and `<Requires>Plex Media Server</Requires>`.

**Rationale:** The CA card is the Unraid storefront. Rejected alternative: keep the trivia for existing users. They read release notes, not the store card.

**User story:** As an Unraid user browsing CA, I want to know in two lines what this does so that I click Install.

**Acceptance criteria:**
- [ ] Overview ≤ 450 chars and contains the positioning sentence.
- [ ] No "MIT", "curatorx", or "rollout.sh" in Overview.
- [ ] ≥ 2 `<Screenshot>` tags resolve over HTTPS.

**Success metric:** CA installs per month (from Hub pull deltas on new tags) trend up after change.

**Validation:** XML lint, plus CA preview on the QA Unraid.

### GRO-012: Add share-preview metadata and `noindex` to the app shell

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Public |
| Persona(s) | Invited member, owner on public profile |
| Category | SEO / link previews |
| Severity | Medium |
| Impact | 3 |
| Effort | XS |
| Confidence | Confirmed |
| Priority score | 6 |
| Verdict | Fix |
| Dependencies | — |
| Labels | og, robots, privacy |

**Evidence:** `05274cf:frontend/index.html` contains only charset, viewport, favicon, theme script, and `<title>Projectionist</title>`. There is no `meta name="description"`, no `og:*` or `twitter:*` tags, no `robots`, and no web manifest. `frontend/public/` holds only `favicon.svg` and `release-notes.json`. `rg -n "noindex|X-Robots"` over `projectionist/web` returns nothing.

**Current state:** An invite link pasted into iMessage, WhatsApp, or Slack previews as a bare URL. A "public" household profile (custom domain, `household_profile="public"`) has nothing telling crawlers to stay out.

**Root cause:** The SPA shell was never treated as a public surface.

**Recommendation:** In `index.html`, add `<meta name="description" content="Your household's private movie and TV companion.">`, `<meta name="robots" content="noindex, nofollow">`, and neutral Open Graph tags: `og:title="Projectionist"`, `og:description` = same as description, `og:image="/og-card.png"` (1200×630, wordmark on cream, no library posters), `og:type="website"`. Also send header `X-Robots-Tag: noindex, nofollow` on all HTML responses in `spa_routes.py`. Add `manifest.webmanifest` (name, short_name "Projectionist", theme colors from tokens) so "Add to Home Screen" gets the right icon.

**Rationale:** A rich preview raises tap-through on family-chat invites, and `noindex` protects household privacy. Rejected alternative: a per-invite dynamic OG image. That needs server-side rendering, and it would leak the household name to the messaging app's crawlers.

**User story:** As a relative receiving a link, I want a recognisable preview so that I trust it isn't spam.

**Acceptance criteria:**
- [ ] `curl -sI /login` shows `X-Robots-Tag: noindex, nofollow`.
- [ ] HTML contains description, `og:title`, `og:image`, robots meta.
- [ ] The OG image contains no library or member data.

**Success metric:** Invite redeem rate (GRO-022) before/after.

**Validation:** Paste a QA join URL into a messaging app's link debugger.

### GRO-010: Count picks watched in native Plex, as a separately labelled "likely" tier

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Owner |
| Persona(s) | Established owner, maintainer |
| Category | Analytics & instrumentation |
| Severity | High |
| Impact | 5 |
| Effort | M |
| Confidence | Likely |
| Priority score | 4.0 |
| Verdict | Fix |
| Dependencies | GRO-001 (keep verified tier), GRO-018 |
| Labels | north-star, attribution, plex |

**Evidence:** `05274cf:projectionist/telemetry/attribution.py:4-6` ("never inferred from Plex history"); `play_start` is emitted only by in-app Play (`05274cf:projectionist/web/playback_routes.py`, the only caller of `record_play_start`); `record_playback_event` (from Plex webhooks, `05274cf:projectionist/web/webhooks.py`) carries no `user_id` and no rec link (`ingestion.py:197-214`). Overview shows "0 chat turns · 0 plays in Projectionist · 0 from a pick" (`00` §4.2). Confidence is **Likely** because it assumes most households watch on TV apps (`00` §5, Plex benchmark). Validate on prod by comparing `play_start` counts with `watch_events` from history ingest for the same week.

**Current state:** The only success metric for recommendations ignores the main way people watch.

**Root cause:** Attribution was (rightly) scoped to what can be proven. No second, honestly-labelled tier exists.

**Recommendation:** Keep `verified` as is. Add a nightly on-box job that writes `pick_watched_likely` rows when a `watch_events` row for member M and title T occurs within **7 days** after T was surfaced to M by a chat card, For you rail, newsletter pick, or household recommendation (all already stored). Properties: `surface`, `lag_hours`, `app_version`. No text. Show on Overview as "**Picks watched this week: 3 confirmed · 11 likely**", with an info tip explaining both. Per-member rows are visible only to that member (export/purge).

**Rationale:** Without it, the product can't tell whether the curator works. Rejected alternatives: count any Plex watch of any recommended title ever (inflates), or drop the metric (blind).

**User story:** As an owner, I want to know if the household actually watched what Projectionist suggested so that I know it's worth running.

**Acceptance criteria:**
- [ ] The job joins only surfaced→watched within 7 days for the same user.
- [ ] Overview shows confirmed and likely separately.
- [ ] `PRIVACY.md` documents the new event.
- [ ] Rows are included in export/purge and kept 90 days.

**Success metric:** On prod, likely + confirmed > 0 weekly within 2 weeks of shipping. The ratio is tracked per release.

**Validation:** pytest with synthetic surfaced and watch rows (in window, out of window, other user).

### GRO-013: Give each lifecycle program its own notification kind

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Cross-cutting |
| Persona(s) | Members, owner |
| Category | Lifecycle messaging / measurement |
| Severity | Medium |
| Impact | 3 |
| Effort | S |
| Confidence | Confirmed |
| Priority score | 3 |
| Verdict | Fix |
| Dependencies | Enables GRO-008 per-program unsubscribe, GRO-018 |
| Labels | notifications, schema |

**Evidence:** `05274cf:projectionist/notifications/newsletters.py:278` (member newsletter) and `:389` (owner monthly) and `05274cf:projectionist/notifications/weekly_letter.py:475` (owner weekly letter) all use `kind="digest"`. The `user_notifications.kind` CHECK allows only `recommendation, arrival, access-request, digest, nudge, library-share` (`05274cf:projectionist/library/db/_schema.py:1014-1025`). Whispers aren't a kind at all. Task description says opt-in is "in Account settings" (`scheduler/tasks/member_newsletter.py:40-43`), but the UI says Settings → Notifications.

**Current state:** Seen rates, click rates, and mutes can't distinguish the three programs, and per-program unsubscribe (GRO-008) has nothing to key on.

**Root cause:** Programs were added over time and reused the nearest kind.

**Recommendation:** A migration widens the CHECK to add `newsletter`, `owner-letter`, `owner-monthly`, `year-in-review`, and `whisper`, and backfills from `payload_json.newsletter`. `user_wants_channel` maps the new kinds to the existing opt-ins. Fix the task description string.

**Rationale:** It's a cheap schema change that unlocks measurement and respectful muting. Rejected alternative: infer the program from payload at query time. That's fragile and invisible to members.

**User story:** As a member, I want to mute arrivals without losing the newsletter so that I control what I get.

**Acceptance criteria:**
- [ ] Each program writes a distinct `kind`.
- [ ] Existing rows are backfilled.
- [ ] Settings → Notifications lists each program once.

**Success metric:** Seen rate reported per program on the pulse.

**Validation:** Migration test, plus a delivery test per program.

### GRO-014: Fix naming drift with a canonical glossary

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Cross-cutting |
| Persona(s) | All members, new owner, non-native reader |
| Category | Microcopy |
| Severity | Medium |
| Impact | 3 |
| Effort | S |
| Confidence | Confirmed |
| Priority score | 3 |
| Verdict | Fix |
| Dependencies | — |
| Labels | glossary, naming |

**Evidence:** Chat agent is "Curator", "The Professor" (persona picker), and "CURATOR" on replies (`00` P-11). Admin rail "Members" vs h1 "Household" (`00` P-11). The Shelves empty state links "Create a shelf" to `/settings/lists` (`05274cf:frontend/src/pages/ListsPage.tsx:136-138`). The weekly letter signs "— your curator" (`weekly_letter.py:362`). The task description says "Account settings" while the UI says "Settings → Notifications" (GRO-013).

**Current state:** Members have to learn several names for one thing.

**Root cause:** No glossary. `DOCS_STYLE.md` defers to "actual in-app labels" without fixing them.

**Recommendation:** Add the glossary in §B-Appendix to `DOCS_STYLE.md`. Apply: the agent is "**your curator**" generically and the persona's name when one is set ("The Professor"). Reply label shows the persona name, not "CURATOR". Admin rail and h1 both say "**Household**". "Shelves" is the member noun; rename `/settings/lists` heading to "Your shelves" and keep the route. Add a unit test asserting `adminNav` labels equal page h1s.

**Rationale:** Consistent nouns reduce support questions and help the non-native persona. Rejected alternative: rename the routes. That breaks links for no user gain.

**User story:** As a member, I want one name for each thing so that Help and the UI match.

**Acceptance criteria:**
- [ ] Admin rail label equals page h1 for every admin route.
- [ ] No member-facing "CURATOR" label when a persona name exists.
- [ ] "Create a shelf" lands on a page titled "Your shelves".

**Success metric:** Glossary terms used consistently in `rg` checks (0 violations).

**Validation:** Unit test plus a manual walk.

### GRO-015: Use plain words for controls and KPIs; keep the voice for content

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Owner |
| Persona(s) | New owner, non-native reader, members (turnstyle) |
| Category | Microcopy / jargon |
| Severity | Medium |
| Impact | 3 |
| Effort | S |
| Confidence | Confirmed |
| Priority score | 3 |
| Verdict | Fix |
| Dependencies | GRO-014 |
| Labels | jargon, owner-kpi |

**Evidence:** `05274cf:frontend/src/lib/beyondSearch.ts:134` ("Expand ${count} titles in turnstyle view", member-visible, misspelt "turnstile"); `05274cf:frontend/src/lib/ownerHealth.ts:60,91` ("Named kinship", "About 20 minutes, in order: Named kinship → open issues → purge pressure → Scheduled Tasks catch-up."); `05274cf:frontend/src/pages/ScheduledTasksPage.tsx:631`; `05274cf:projectionist/notifications/weekly_letter.py:310-330` ("dead weight", "I will not send a fleet at them"); `05274cf:projectionist/persona/presets.py:244` ("Which thread of your library shall we pull on?").

**Current state:** Owners must learn coined terms to read their own dashboard, and members meet a misspelt metaphor on a button.

**Root cause:** Internal vocabulary leaked into labels. There is no rule separating voice (content) from labels (controls).

**Recommendation:** Rule: **controls, KPIs, and status are plain; curator replies, letters, and newsletters may carry voice.** Rename: "Named kinship" → "**Titles with explained matches**" (tooltip: "Share of titles where we can say *why* two titles are related."); "Purge pressure" → "**Removal candidates**"; "turnstyle view" → "**Expand all {count} titles**"; and in the owner letter, "dead weight" → "**unwatched for 90+ days**". See the 10 rewrites in §B-Appendix.

**Rationale:** The editorial voice is a differentiator in content. On a control it costs comprehension. Rejected alternative: a glossary tooltip on every coined term. That treats the symptom.

**User story:** As a new owner, I want my Monday checklist in plain words so that I know what to do without reading Help.

**Acceptance criteria:**
- [ ] No member-facing string contains "turnstyle".
- [ ] Overview KPI labels match the glossary.
- [ ] The owner letter uses no "dead weight" or "fleet" phrasing.

**Success metric:** Help page visits from Admin Overview drop (pulse event `help_open{from}`).

**Validation:** `rg` plus a snapshot test of `ownerHealth` labels.

### GRO-016: Invite members to the newsletter in context, without changing the default

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Consumer |
| Persona(s) | Returning member |
| Category | Lifecycle reach |
| Severity | Medium |
| Impact | 3 |
| Effort | S |
| Confidence | Confirmed |
| Priority score | 3 |
| Verdict | Fix |
| Dependencies | GRO-005 (keep default), GRO-013 |
| Labels | newsletter, opt-in |

**Evidence:** Live QA `/admin/newsletters`: "1 of 5 loaded members currently opted in" (`screenshots/gro_admin-newsletters-letter-preview_owner.png`, page text). The only opt-in surface is a toggle in Settings → Notifications (`NotificationsSettingsPage.tsx:314-319`). No inbox card, chat chip, or post-rating prompt offers it.

**Current state:** The newsletter's careful relevance logic (GRO-003) reaches about 20% of the household.

**Root cause:** Opt-in is correct, but discovery is buried.

**Recommendation:** After a member's **third** active day (or first rating), drop one inbox item (kind `recommendation`, system-authored): "**Want a short note each week with picks that connect to what you've watched?** We only write when there's something new for you." Buttons: "Yes, send it to my inbox" (sets `newsletter_opt_in`, inbox only) and "No thanks" (stamps `newsletter_prompt_dismissed_at`; never ask again). Email is a second step on the Settings page.

**Rationale:** It's a timely, single, dismissible ask. Rejected alternatives: opt-in by default (breaks GRO-005), or a modal (interrupts).

**User story:** As a member who's started using the app, I want to be offered the weekly note once so that I can choose it without hunting.

**Acceptance criteria:**
- [ ] The prompt appears at most once per member.
- [ ] "No thanks" never re-prompts.
- [ ] Youth members get the prompt only if the owner allows newsletters for Youth.

**Success metric:** Opt-in ≥ 50% of members active in the last 28 days.

**Validation:** pytest on prompt eligibility; manual check on QA.

### GRO-017: Make the README sell before it explains

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Public |
| Persona(s) | New owner |
| Category | Positioning & listings |
| Severity | Medium |
| Impact | 3 |
| Effort | S |
| Confidence | Confirmed |
| Priority score | 3 |
| Verdict | Fix |
| Dependencies | GRO-007 |
| Labels | readme, screenshots |

**Evidence:** `05274cf:README.md` has no images apart from 4 badges (`rg "png|!\["`). The architecture diagram (`:24-53`) and "natural language surgeon" pull-quote (`:20`) come before Quick start (`:80`). The `docker run` example (`:85-89`) omits `PROJECTIONIST_SESSION_SECRET`, which Compose includes. The README lists `PROJECTIONIST_GUEST_TOUR_ENABLED` (`:195`) although the tour is retired (`00` §1.6). The "Config path (existing installs) `/mnt/user/appdata/curatorx/config`" row comes first (`:171`).

**Current state:** A visitor scrolls past architecture to learn what it looks like and what they need.

**Root cause:** README grew as a developer index, which matches the DOCS_STYLE "developer" audience, but it is also the primary owner acquisition page.

**Recommendation:** Order: H1 + positioning sentence → a 3-image strip (Chat reply, Explore "For you", Live guide at 1440px, from Lights Up) → "**What you need**" (Plex Media Server; Docker/Unraid; optional: LLM key or Ollama, Radarr/Sonarr, SMTP) → Quick start (`docker run` with `-e PROJECTIONIST_SESSION_SECRET=$(openssl rand -hex 32)`) → "What your household gets" (5 bullets, benefit-first) → Privacy (GRO-007 wording) → everything else. Remove the retired env var row. Put the new-install path first.

**Rationale:** Owners decide from the first screen. Rejected alternative: a separate marketing site. It's overkill for a self-hosted project.

**User story:** As a homelabber on GitHub, I want to see it and know the prerequisites in 10 seconds so that I try it.

**Acceptance criteria:**
- [ ] ≥ 3 screenshots above the fold.
- [ ] "What you need" precedes Quick start.
- [ ] `docker run` sets a session secret.

**Success metric:** GitHub README → Docker Hub click-through and stars trend (GitHub Insights).

**Validation:** Render on GitHub; run the `docker run` verbatim on a scratch host.

### GRO-019: Fix weekly-letter render defects (doubled year, ungrouped numbers)

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Owner |
| Persona(s) | Established owner |
| Category | Content quality |
| Severity | Low |
| Impact | 2 |
| Effort | XS |
| Confidence | Confirmed |
| Priority score | 2 |
| Verdict | Fix |
| Dependencies | — |
| Labels | letter, formatting |

**Evidence:** Live QA preview: "There are 28885 hours of film and television… — 4737 titles", "4424 titles have been here more than 90 days… The heaviest is Tracker (2024) (2024) at 73.2 GB." Source: `05274cf:projectionist/notifications/weekly_letter.py:305-330` (raw ints interpolated; `_title_label` at `:241` appends the year to a title that already ends in "(2024)", likely).

**Current state:** Small errors in the owner's most personal message undercut the "your curator" voice.

**Root cause:** No shared number/title formatter for lifecycle copy.

**Recommendation:** Use `f"{n:,}"` for counts and hours. In `_title_label`, skip appending the year when the title already ends with `(YYYY)`. Add the same formatter to newsletter and Year in Review builders.

**Rationale:** XS fix to a credibility leak.

**User story:** As an owner, I want my weekly letter to read cleanly so that I trust it.

**Acceptance criteria:**
- [ ] Numbers ≥ 1,000 render with separators.
- [ ] No title renders "(YYYY) (YYYY)".

**Success metric:** Snapshot test passes.

**Validation:** Unit test with a title "Tracker (2024)" and year 2024.

### GRO-021: Keep internal review IDs out of public release notes

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Public |
| Persona(s) | Owner reading CHANGELOG / GitHub release |
| Category | Content |
| Severity | Low |
| Impact | 2 |
| Effort | XS |
| Confidence | Confirmed |
| Priority score | 2 |
| Verdict | Fix |
| Dependencies | GRO-004 |
| Labels | changelog |

**Evidence:** `05274cf:CHANGELOG.md:16-45` ("SEC-001 `/api/chat/stream`…", "GRO-007 `chat_turn`…", "BD-5 default page", "OPS-030 Monday pass").

**Current state:** The technical sections read as an internal tracker. Outsiders can't decode the IDs.

**Root cause:** Review IDs are used as commit and changelog anchors.

**Recommendation:** In CHANGELOG, write the change in words. Put IDs in an HTML comment (`<!-- SEC-001 -->`) or in the PR description only.

**Rationale:** Public notes are read by prospective owners evaluating maturity.

**User story:** As an owner, I want release notes in plain language so that I know what changed.

**Acceptance criteria:**
- [ ] `rg -n "\b(SEC|PRIV|GRO|UX|OPS|ARCH|PERF|BD)-\d+" CHANGELOG.md` finds no hits in new release sections outside comments.

**Success metric:** 100% of new releases.

**Validation:** CI grep on the newest section.

### GRO-020: Remove dead telemetry plumbing and surface the telemetry switch

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Admin |
| Persona(s) | Platform admin, contributor |
| Category | Instrumentation hygiene |
| Severity | Low |
| Impact | 2 |
| Effort | S |
| Confidence | Likely |
| Priority score | 0.8 |
| Verdict | Remove |
| Dependencies | — |
| Labels | telemetry, cleanup |

**Evidence:** `interaction_telemetry` is pruned (`05274cf:projectionist/scheduler/tasks/data_retention.py:9,85`) and defined in migrations, but no code outside `library/db` writes to it (`rg "interaction_telemetry" projectionist --glob '!**/db/**'` lists only `data_retention.py`). `telemetry_enabled` is read from DB config (`ingestion.py:79-87`) with no UI or `settings.json` key (`rg telemetry_enabled frontend/src` → none). The `telemetry_events` table (closed-loop augmentation) and the `system_telemetry_stream` table (product events) have confusingly similar names.

**Current state:** Contributors can't tell where to add an event, and owners can't switch activity counting off.

**Root cause:** Accreted telemetry designs.

**Recommendation:** Drop `interaction_telemetry` in a migration. Document in `docs/DATA_MODEL.md`: "`system_telemetry_stream` = product events; `telemetry_events` = library-knowledge demand signals". Expose "Count household activity on this server (never leaves it)" as an owner toggle under Admin → Advanced, default on, wired to `telemetry_enabled`.

**Rationale:** Less surface area, and an owner-visible control strengthens the privacy claim (GRO-007).

**User story:** As an owner, I want one switch for on-box activity counting so that I'm in control.

**Acceptance criteria:**
- [ ] The table is dropped and the prune code is removed.
- [ ] The toggle persists and stops `system_telemetry_stream` writes.

**Success metric:** n/a (hygiene).

**Validation:** Migration test; toggle off, then a chat turn writes no row.

## 15. Opportunities

### GRO-018: Build an on-box "Household pulse" from the tracking plan

| Field | Value |
|---|---|
| Type | Opportunity |
| Surface | Owner |
| Persona(s) | Established owner, maintainer |
| Category | Analytics & instrumentation |
| Severity | High |
| Impact | 5 |
| Effort | M |
| Confidence | Confirmed |
| Priority score | 5 |
| Verdict | Add |
| Dependencies | GRO-001, GRO-010, GRO-013 |
| Labels | tracking-plan, north-star, guardrails |

**Evidence:** Today, only `chat_turn`, `play_start`, `chat_message`, `chat_feedback`, `preference_signal`, `review_saved`, `playback_event`, `tool_invocation`, and `llm_usage` are emitted (`ingestion.py:57-65`). Overview shows three 7-day counts (`_owner_ops.py:208-237`). There are no events for session start, Explore/Search use, pin, inbox seen/click, newsletter click, or invite lifecycle. `user_notifications.seen_at` exists (`_schema.py:1039`) but is not reported.

**Current state:** Owners and the maintainer can't see activation, weekly engagement, or lifecycle effectiveness.

**Root cause:** Instrumentation was added per feature, not from a plan.

**Recommendation:** Implement the tracking plan in §B-Appendix as one `owner_pulse` endpoint and an Overview card. The card shows the north-star plus four guardrails, with week-over-week arrows and a 4-week sparkline, at household totals only.

**Rationale:** Every other department's success metrics depend on it. Rejected alternative: a third-party analytics SDK. That breaks the on-box promise.

**User story:** As an owner, I want a one-glance weekly pulse so that I know whether the household is getting value.

**Acceptance criteria:**
- [ ] All events in the plan are emitted with the listed properties only.
- [ ] The pulse card renders north-star and guardrails.
- [ ] No per-member breakdown is visible to the owner.
- [ ] `PRIVACY.md` is updated.

**Success metric:** The pulse is used: `owner_pulse_view` ≥ 1/week on prod.

**Validation:** pytest per event; Playwright mocked Overview.

### GRO-022: Show an invite funnel from data already in the security log

| Field | Value |
|---|---|
| Type | Opportunity |
| Surface | Owner |
| Persona(s) | Owner |
| Category | Activation measurement |
| Severity | Medium |
| Impact | 3 |
| Effort | S |
| Confidence | Confirmed |
| Priority score | 3 |
| Verdict | Add |
| Dependencies | GRO-009 |
| Labels | invite, funnel |

**Evidence:** `05274cf:projectionist/security_audit.py:20-22` (`invite_create`, `invite_revoke`, `invite_redeem`); `invites` table with `expires_at`/status (`_schema.py:1431`).

**Current state:** The owner can't see sent vs accepted vs expired, or who joined but never came back.

**Root cause:** The audit log is designed for security review, not activation.

**Recommendation:** On Admin → Household, add a strip: "**Invites (last 90 days): 6 sent · 4 joined · 1 expired · 1 pending**", plus "Joined but not back in 7 days: 1", showing names (the owner already sees member names there). Add a "Resend" action on expired or pending invites.

**Rationale:** It makes the 1.38.0 launch outcome visible at near-zero cost.

**User story:** As an owner, I want to see who hasn't accepted their invite so that I can nudge them.

**Acceptance criteria:**
- [ ] Counts match the `invites` table.
- [ ] "Resend" creates a new invite and revokes the old one.

**Success metric:** Redeem rate ≥ 70% in 7 days.

**Validation:** pytest on counts; manual check on QA (read-only view).

### GRO-023: Replace A/B ambitions with release-over-release comparison

| Field | Value |
|---|---|
| Type | Opportunity |
| Surface | Admin |
| Persona(s) | Maintainer, owner |
| Category | Experimentation |
| Severity | Low |
| Impact | 2 |
| Effort | S |
| Confidence | Confirmed |
| Priority score | 1 |
| Verdict | Add |
| Dependencies | GRO-018 |
| Labels | experimentation, versions |

**Evidence:** `app_version` already on `chat_turn` and `play_start` (`ingestion.py:242,264`). Flags are static booleans (`05274cf:projectionist/config_store.py:486-511`).

**Current state:** No way to tell whether a release improved outcomes.

**Root cause:** No versioned comparison view.

**Recommendation:** On the pulse, add "Since you upgraded to {version} ({n} days): north-star/week vs the 4 weeks before". Don't build per-user randomization.

**Rationale:** It gives the maintainer a qualitative signal from their own household, and owners can report it in issues.

**User story:** As the maintainer, I want to see if a release moved the north-star in my household so that I can judge it.

**Acceptance criteria:**
- [ ] The comparison only shows when ≥ 14 days exist on each side.

**Success metric:** Used in ≥ 1 release retro.

**Validation:** pytest with synthetic versions.

### GRO-024: Decide on an explicit, opt-in "count my install" ping

| Field | Value |
|---|---|
| Type | Opportunity |
| Surface | Admin |
| Persona(s) | Maintainer, owner |
| Category | Analytics (cross-install) |
| Severity | Medium |
| Impact | 3 |
| Effort | S |
| Confidence | Suspected |
| Priority score | 1.5 |
| Verdict | Add (pending decision) |
| Dependencies | GRO-007 (claim wording) |
| Labels | decision-required, privacy |

**Evidence:** The only cross-install signal is the Hub pull count (19,298), which mixes new installs, auto-updates, and CI. GitHub shows 1 star, 0 forks (API, 2026-11-02).

**Current state:** The maintainer can't tell how many active households exist or which versions they run.

**Root cause:** The no-phone-home promise (correct) leaves no consented alternative.

**Recommendation:** **Leadership decision.** If approved: off by default. A setup-wizard checkbox reads "Help the maintainer count active installs (sends version and a random install ID once a week; no library, member, or usage data)". It sends to a Cloudflare Worker that stores only `{install_id, version, week}`. If rejected, keep relying on Hub pulls and GitHub issues. Confidence is Suspected because the value depends on uptake (validate by polling 10 owners in the issue tracker).

**Rationale:** It's the only way to learn version spread and retention without breaking trust. Rejected alternative: on-by-default. It breaks the brand promise.

**User story:** As the maintainer, I want an honest count of active households so that I prioritise wisely.

**Acceptance criteria:**
- [ ] Default off; payload documented verbatim in `PRIVACY.md`.
- [ ] One toggle disables it permanently.

**Success metric:** ≥ 20% opt-in among new installs.

**Validation:** Inspect outbound requests with the toggle on and off.

## 16. Remediation plan

**Now (0–2 weeks)**: copy and listings, all cheap, no schema.

| ID | Title | Effort | Owner role | Dependencies |
|---|---|---|---|---|
| GRO-007 | One positioning sentence; fix privacy/tenant claims | S | Content lead | — |
| GRO-006 | Docker Hub description pushed on release | XS | Maintainer | GRO-007 |
| GRO-011 | Unraid CA Overview as store card | XS | Maintainer | GRO-007 |
| GRO-009 | Invite email + join page copy and redirect | S | FE + content | — |
| GRO-012 | OG/description/noindex + manifest | XS | FE | — |
| GRO-019 | Letter number/title formatting | XS | BE | — |
| GRO-021 | No review IDs in CHANGELOG | XS | Maintainer | — |
| GRO-008 (part 1) | Base URL + deep links + `List-Unsubscribe` header | S | BE | — |

**Next (2–6 weeks)**: measurement and lifecycle mechanics.

| ID | Title | Effort | Owner role | Dependencies |
|---|---|---|---|---|
| GRO-013 | Per-program notification kinds | S | BE | — |
| GRO-008 (part 2) | One-click per-program unsubscribe endpoint | S | BE + security | GRO-013 |
| GRO-014 / GRO-015 | Glossary, plain-label pass | S | Content + FE | GRO-007 |
| GRO-016 | In-context newsletter opt-in card | S | FE + BE | GRO-013 |
| GRO-010 | Likely-watched tier | M | BE | GRO-001 |
| GRO-018 | Household pulse | M | BE + FE | GRO-010, GRO-013 |
| GRO-022 | Invite funnel strip | S | FE + BE | GRO-009 |
| GRO-017 | README restructure with screenshots | S | Content | GRO-007 |

**Later (6+ weeks)**

| ID | Title | Effort | Owner role | Dependencies |
|---|---|---|---|---|
| GRO-020 | Drop dead telemetry; owner toggle | S | BE | — |
| GRO-023 | Release-over-release comparison | S | BE + FE | GRO-018 |
| GRO-024 | Opt-in install count (if approved) | S | Maintainer | Decision |

**Sequencing rationale:** Copy first, because it is cheap and unblocks acquisition immediately. Kinds before unsubscribe and pulse, because both key on kind. The likely-watched tier comes before the pulse, because the north-star needs it.

## 17. Quick wins (high impact, XS–S)

GRO-006 (score 12), GRO-007 (6), GRO-009 (6), GRO-008 part 1 (6), GRO-011 (6), GRO-012 (6), GRO-019 (2).

## 18. Open questions for product/business

1. Is a "Household name" setting acceptable (used in invites and the login eyebrow), or should it stay `household_domain`?
2. Should Youth members ever receive the newsletter prompt (GRO-016), or only with owner consent per Youth account?
3. GRO-024: will leadership permit any outbound ping, even opt-in?
4. What is the canonical short name for the agent: "your curator", or the persona name only?
5. Is Live Channels part of the positioning sentence, or a secondary feature (depends on the Product ruling on SC-13)?

---

## Appendix B1 — Voice & tone guide (one page)

**Voice:** a knowledgeable friend who runs the family movie night. Warm, specific, and honest about limits. Never salesy, never cute at the cost of clarity.

| Principle | Do | Don't |
|---|---|---|
| **Plain labels, voiced content** | Buttons and KPIs: "Expand all 12 titles", "Titles with explained matches" | "turnstyle view", "Named kinship", "Purge pressure" |
| **Say who and why** | "Sam invited you to the Rompala household" | "You've been invited to join a Projectionist household" |
| **Give the next step** | "Ask Sam for a new link — it takes them a few seconds." | "This invite is not available." |
| **Honest limits** | "We only write when there's something new for you." | "Stay up to date with weekly updates!" |
| **Role-appropriate** | Members: "Live isn't on yet — the person who runs Projectionist can turn it on." | Members: "…enable Live Channels in Admin." |
| **Numbers read like prose** | "28,885 hours", "about 88%" | "28885 hours", "87.9%" in a letter |
| **One name per thing** | See glossary | Curator / The Professor / CURATOR on one screen |

**Tone by moment:** errors are calm and actionable (what happened, then what to do). Empty states are inviting and give one action. Letters and newsletters carry personality, signed by the persona name. Admin copy is precise and uses no metaphors in labels.

**Glossary (canonical member/owner terms):** **Projectionist** (the app) · **your curator** (the chat agent generically; use the persona name when set) · **Household** (people page; owners, members, Youth) · **Shelf** (a member-built list) · **Watchlist** · **For you** (the personal rail) · **Live** (household channels) · **Inbox** · **Weekly newsletter** (member) · **Weekly letter** (owner) · **Titles with explained matches** (formerly Named kinship) · **Removal candidates** (formerly purge candidates/pressure) · **Weekly check-in** (formerly Monday pass; the day may vary).

## Appendix B2 — The 10 most important strings rewritten

| # | Where (`05274cf:`) | Current | Proposed | Why |
|---|---|---|---|---|
| 1 | Docker Hub `full_description` (Hub API) | "Canonical image for Projectionist (formerly CuratorX). See https://github.com/romwil/curatorx" | Full listing from `docs/DOCKERHUB.md`, opening: "**Projectionist is a private movie-and-TV companion for your Plex household.** Ask for something to watch, browse your library by mood and connection, and keep everyone's picks their own." | Highest-traffic acquisition surface; dead link (GRO-006) |
| 2 | `README.md:10` | "…open-source, self-hosted cinema intelligence engine and agentic companion… local-first, zero-telemetry, with vector mapping, multi-signal taste modeling, MCP access, and hardened multi-tenant roles (Owner / Member / Youth)." | "Projectionist is a private movie-and-TV companion for your Plex household: ask for something to watch, browse your library by mood and connection, and keep everyone's picks their own. Self-hosted on Docker or Unraid; no phone-home." | Benefit first; removes inaccurate claims (GRO-007) |
| 3 | `templates/projectionist.xml:14` | "Cinema intelligence for your personal archive. Chat-first companion… Releases through 1.36.2 were MIT… legacy …/curatorx/config OK… SSH `docker pull`…" | See GRO-011 (≤ 450 chars, store-card copy) | CA storefront (GRO-011) |
| 4 | `projectionist/invites.py:120` | Subject: "You're invited to join Projectionist" | "{Inviter} invited you to {Household} on Projectionist" | Named sender drives opens (GRO-009) |
| 5 | `frontend/src/pages/JoinPage.tsx:168` | "Sign in with Plex to join. Username and password is a fallback on the same link." | Plex only: "Use your Plex account to join — it takes about a minute." · Local only: "Choose a username and password to join." · Both: Plex line + "No Plex account? Choose a username and password instead." | Wrong when Plex is off (GRO-009) |
| 6 | `frontend/src/pages/JoinPage.tsx:170` | "This invite is not available." | "This invite has expired or was already used. Ask {inviter} for a new link — it takes them a few seconds." | Dead end → next step (GRO-009) |
| 7 | `projectionist/notifications/newsletters.py:62-65` | "Open Projectionist to see these picks in your inbox. To change or stop these notes, go to Settings → Notifications." | HTML: "[Open your picks]({base}/inbox) · [Stop these weekly notes]({base}/settings/notifications#newsletter)". Plain text: the same with absolute URLs. Plus a `List-Unsubscribe` header. | Way back in and out must be tappable (GRO-008) |
| 8 | `frontend/src/lib/beyondSearch.ts:134` | "Expand ${count} titles in turnstyle view" | "Expand all ${count} titles" | Misspelt metaphor on a member button (GRO-015) |
| 9 | `frontend/src/lib/ownerHealth.ts:91` | "About 20 minutes, in order: Named kinship → open issues → purge pressure → Scheduled Tasks catch-up." | "About 20 minutes: improve explained matches, clear reported problems, review removal candidates, then let background tasks catch up." | Plain owner KPIs (GRO-015) |
| 10 | `frontend/src/lib/liveChannelsCopy.ts:30-31` | "Not on the air yet" / "Ask the household owner to enable Live Channels in Admin." | "Live isn't on yet" / "Live channels play shows from your library like TV. The person who runs Projectionist can turn them on." | Member copy shouldn't name Admin; explains the feature (DOCS_STYLE member rule) |

Runners-up: `useChatSession.ts:663` "Describe what you're hunting for…" → "What are you in the mood for?"; `presets.py:244` keep the persona greeting (it is voiced content) but add the plain starter chip "Something for tonight"; `weekly_letter.py:328-330` "I will not send a fleet at them." → "Nothing will be removed unless you choose to."; `ListsPage.tsx:136-138` → "Shelves are lists you build — a director run, a holiday stack. Start one from any title's ⋮ menu, or [create a shelf]."

## Appendix B3 — Privacy-respecting on-box tracking plan

**Contract (applies to every event):** written to `system_telemetry_stream` on this server only. Properties are IDs, enums, counts, and durations; **never free text**, search queries, or titles typed by users. `user_id` rows are in that member's export and purge, and are kept 90 days (`data_retention.py`). **Owners see household totals only**, except their own rows. Every event carries `app_version`. The owner toggle `telemetry_enabled` turns all of it off (GRO-020).

### Events

| Event | When | Properties (only these) | Exists today? |
|---|---|---|---|
| `session_start` | First authenticated request after 30 min idle | `user_id`, `role`, `is_youth`, `entry` (`direct`/`notification`/`email`/`invite`), `device_class` (`phone`/`tablet`/`desktop` from viewport) | No |
| `invite_created` / `invite_redeemed` / `invite_expired` | Invite lifecycle | `invite_id`, `method` (`plex`/`local`/`oidc`), `is_youth`, `hours_to_redeem` | Partly (security log) |
| `first_value` | First `pick_acted` per user | `user_id`, `surface`, `minutes_since_join` | No |
| `chat_turn` | Turn completed | existing (`outcome`, `card_count`, `tool_count`, `duration_ms`, `persona_id`) | Yes |
| `pick_shown` | Cards rendered from chat / For you / newsletter / recommendation | `user_id`, `surface`, `count`, `rec_id` | No (cards stored, not counted) |
| `pick_acted` | Play, pin, rate, or open detail from a pick | `user_id`, `surface`, `action` (`play`/`pin`/`rate`/`open`), `rec_id` | Partly (`play_start` verified) |
| `pick_watched_likely` | Nightly join: surfaced → Plex watch ≤ 7 days | `user_id`, `surface`, `lag_hours` | No (GRO-010) |
| `explore_open` / `search_run` | Explore hub view; search submitted | `user_id`, `result_count_bucket` (`0`/`1-10`/`11+`), no query | No |
| `notification_delivered` | Inbox row or email created | `user_id`, `kind` (after GRO-013), `channel` | No (inferable from rows) |
| `notification_seen` | `seen_at` set | `user_id`, `kind` | Column exists |
| `notification_clicked` | Deep link with `?rec=…` opened | `user_id`, `kind`, `channel` | No (needs GRO-008 links) |
| `program_opt_change` | Opt-in/out per program | `user_id`, `kind`, `to` (`on`/`off`), `via` (`settings`/`prompt`/`one_click`) | No |
| `owner_pulse_view` / `monday_done` | Owner views pulse; marks check-in done | `user_id` | Partly (checklist marks) |

### Funnels

1. **Activation (member):** `invite_created` → `invite_redeemed` (≤ 7 d) → `session_start` → `first_value` (≤ 7 d) → second-week `session_start`. Target: 70% → 60% → 50% end-to-end.
2. **Weekly core loop:** `session_start` → `pick_shown` → `pick_acted` → `pick_watched_likely`/verified play. Target: ≥ 25% of shown picks acted on, ≥ 10% watched.
3. **Lifecycle:** `notification_delivered` → `notification_seen` → `notification_clicked` → `pick_acted`, reported per `kind`. Target: newsletter seen ≥ 60%, clicked ≥ 15%.
4. **Owner setup:** setup checklist steps → first `invite_created` → ≥ 2 members with `first_value` within 14 days of install.

### North-star metric

**Picks watched per week** = distinct (member, title) pairs where Projectionist surfaced the title to that member and the member watched it within 7 days. Reported as *confirmed* (in-app Play, verified `rec_id`) plus *likely* (Plex watch join). This captures the product's promise ("something good to watch tonight"), works without an LLM (For you counts), and can't be gamed by chat volume.

### Guardrails (must not regress while chasing the north-star)

| Guardrail | Definition | Threshold |
|---|---|---|
| Chat failure rate | `chat_turn.outcome != ok` / all turns | ≤ 5% weekly |
| Reply speed | p95 `chat_turn.duration_ms` | ≤ 12 s |
| LLM spend | `llm_usage.estimated_usd` per week | No > 50% WoW jump without a usage jump |
| Program opt-out rate | `program_opt_change{to=off}` / opted-in, per kind | ≤ 10% per quarter |
| Youth gate breach | Youth `pick_shown` above ceiling | **0**, alert as Needs attention |
| Dormancy | Members with no `session_start` in 28 days | Shown as a count; no per-person shaming |

---

## Phase 6 self-check (department level)

- [x] Opens with Part A; every conclusion cites finding IDs.
- [x] Every High finding (GRO-006, 007, 008, 009, 010, 018) appears in the narrative (§1, §2).
- [x] Foundations challenged table, "If we built it today", and "Stop doing" are present.
- [x] All four surfaces are covered (§5) with grades.
- [x] Strengths documented in full finding format (GRO-001–005) with Protect notes.
- [x] Recommendations carry exact strings, headers, thresholds, and event schemas.
- [x] Every finding has evidence, root cause, rationale, and acceptance criteria.
- [x] IDs GRO-001–GRO-024 are unique.
- [x] No application code modified; only this file and `gro_*` screenshots were written. No settings saved, nothing sent, no chat prompt used.
- [ ] Status file: not updated by this agent (forbidden by the handoff rules; the coordinator owns `_status.md`).
