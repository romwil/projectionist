# 05 · Growth, Content & Analytics — Projectionist

Run **2026-10-28-2** · Commit reviewed **`94fcd3f`** (`origin/main`, 1.37.72 + PR #188) · Reviewer: Growth, Content & Analytics Lead (`GRO`)

All code citations are `path:line` at `94fcd3f`, taken from `git grep -n 94fcd3f` / `git show 94fcd3f:path`. The local working tree was ~36 commits behind and was **not** used for line numbers. Live observations are from QA `http://10.10.1.202:8792` only (`/api/health` → `{"status":"ok","version":"1.37.72"}`). Prod `:8788`, smartmap `:8790`, theater `:8791`, and the VIP hostname were not touched. No credentials, tokens, emails, or real names appear in this document or its screenshots.

---

# Part A — Conclusions & findings

## 1. Bottom line

**Grade: C−.** Projectionist writes better than most self-hosted tools. Help and Privacy teach instead of listing features (GRO-004), every lifecycle channel is off until the member turns it on (GRO-001), and the "why" sentence on recommendations is honest and specific (GRO-005). But the product **cannot measure its own core loop**. The main chat path emits no interaction event (GRO-007). Nothing links a recommendation to a play (GRO-014). Member-facing copy uses three or four names for the same curator, including a database migration suffix shown in the inbox (GRO-009). And the weekly newsletter and nudges skip the youth rating gate that the whisper channel already applies (GRO-008).

**Single most important fix:** add the local, metadata-only event spine in the tracking plan (§ Part B, "Tracking plan"). Start with `chat_turn` on `POST /api/chat/stream` and a `rec_id` that carries from impression to play (GRO-007, GRO-014). Every other department's success metrics depend on it.

**Single most important thing to protect:** opt-in-by-default lifecycle plus the metadata-only telemetry privacy contract (GRO-001, GRO-002). Whatever we add to measurement must stay on the box, carry no message text, and never become phone-home.

## 2. Key conclusions

1. **The interaction telemetry exists, but it is wired to the road nobody drives on.** `TelemetryIngester` defines six interaction events (`projectionist/telemetry/ingestion.py:58-63`). The one that matters most, `chat_message`, fires only from legacy `POST /api/chat` (`projectionist/web/chat_routes.py:131`). The SPA only calls `POST /api/chat/stream` (`frontend/src/api/client.ts:1239`; callers `frontend/src/hooks/useChatSession.ts:844`, `frontend/src/components/SeasonalPickChatPane.tsx:84`), and that route records nothing (`projectionist/web/chat_routes.py:341-415`). On QA, the 90-day owner summary shows **`chat_message: 1`, `tool_invocation: 13`, `llm_usage: 128`**, and zero `chat_feedback`, `review_saved`, `playback_event`, or `preference_signal` events, even though the member account alone has eight-plus threads. The root cause is that telemetry was added endpoint by endpoint rather than as a contract on the user action. Roadmap: one `chat_turn` event emitted by the agent itself (not the route), so any transport is covered (GRO-007, GRO-018).

2. **There is no north-star metric because nothing ties a recommendation to a night of watching.** `watch_events` sources are Plex-only (`projectionist/watch_tracker/models.py:11-21`). For you, chat cards, inbox picks, newsletters, and nudges carry no impression or recommendation id, and the frontend sends no analytics at all (`git grep` for analytics, beacon, or track events in `frontend/src` returns nothing). The owner can see LLM cost to the cent (`frontend/src/pages/LlmUsagePage.tsx`) but cannot answer "did anything we suggested get watched?" Roadmap: `rec_id` on every surfaced card, `play_start` joined within 24 hours, and an owner **Household Pulse** view (GRO-014, GRO-025).

3. **The curator has an identity crisis on every member surface.** On QA, the `qa-member` thread list and composer say **"The Professor"**, the message avatar right next to them says **"CURATOR"** (`frontend/src/App.tsx:464` falls back to `"Curator"`), the weekly newsletter in the inbox says **"Curator (migrated) put together a few notes for you."** (from the migration naming at `projectionist/library/db/_schema.py:1600` plus the default-persona voice at `projectionist/notifications/newsletters.py:29-53`), and nudges say **"Enthusiastic Scout here: you have to see…"** (`projectionist/notifications/nudges.py:126`). The handoff note is confirmed. The root cause is that lifecycle copy uses the *household default template* and chat uses the *thread persona*, with no single "speaking persona" resolver. Roadmap: one resolver, and never show storage names (GRO-009, GRO-026).

4. **The lifecycle program is opt-in and respectful, but it has a youth hole and sends empty letters.** Defaults are correct: inbox on, and email, newsletter, nudge, Apprise, and Year in Review all off (`projectionist/library/db/_schema.py:1002-1006`, `:1844`). However, `build_member_newsletter` chooses picks through `specific_bridge` with no youth filter (`projectionist/notifications/newsletters.py:141-195`, `projectionist/notifications/recommendation_reasons.py:843-853`), and the nudges have no youth check either, while whisper explicitly excludes youth (`projectionist/notifications/whisper.py:113`). The newsletter also sends when nothing connects ("Nothing new this week shares a subject…", `projectionist/notifications/newsletters.py:194`). Emails are plain text with no unsubscribe link (`projectionist/notifications/service.py:130`; no "unsubscribe" anywhere in `projectionist/`). Roadmap: run the youth gate on every channel, skip empty sends, and add a one-click opt-out link (GRO-008, GRO-011, GRO-016).

5. **The public routes are honest but unfinished as conversion pages, and they are indexable.** `/login` is clean and the request-access form is well built (honeypot, optional email). But `/join` with a missing or bad token is a dead end under a "You're invited" eyebrow (`frontend/src/pages/JoinPage.tsx:44`, `:163`, `:170`). Login copy has three names for the operator ("household admin" `LoginPage.tsx:374`, "the owner" `:389`, "Configuration" `:230`). And no HTML route sends `noindex`: `/robots.txt` returns 404 on QA, and `frontend/index.html` has no robots meta, while the Lobby Theater already has one (`projectionist/theater/static/index.html:6`). For households on the `public` ingress profile (`projectionist/config_store.py:497` `household_profile`), `/about` exposes the exact running version to crawlers (GRO-010, GRO-012, GRO-017).

6. **Acquisition is real but unmanaged: the Docker Hub page points at a dead name and nobody can see the funnel.** Docker Hub reports 19,203 pulls, 0 stars, and a 93-character full description: "Canonical image for Projectionist (formerly CuratorX). See https://github.com/romwil/curatorx". GitHub reports 1 star, 0 forks, 6 views from 6 unique visitors in 14 days, and Discussions turned off. The Unraid CA overview is mostly ops instructions ("if Force Update shows 0 B pulled, SSH `docker pull`…", `unraid/projectionist.xml:14`) and has no screenshots. Pull counts are inflated by maintainer rollouts, so they are not a usable metric (GRO-013, GRO-027).

7. **Members are told to fix things only the owner can fix.** The no-LLM chat fallback says "Configure an LLM provider for richer conversation." to every member and youth (`projectionist/agent/curator.py:414`; seen on QA as `qa-member`). Notifications settings tell members to "reinstall with web extras" (`frontend/src/pages/settings/NotificationsSettingsPage.tsx:296`). Year in Review shows the raw API detail "Year in Review not available yet" (`projectionist/web/app.py:3081`) instead of the friendlier opt-in state at `frontend/src/pages/YearInReviewPage.tsx:160`. Root cause: there is no microcopy glossary and no audience rule enforced on UI strings. `docs/DOCS_STYLE.md` covers docs, but nothing lints `frontend/src` (GRO-006, GRO-019, GRO-020, GRO-026).

8. **Experimentation is not a gap to close with A/B testing.** A household has two to six people, so splitting them yields noise. What is missing is the ability to compare *before and after a release* on the box, and to compare *persona templates* that already carry `persona_id` on `llm_usage` (`projectionist/library/db/_schema.py:1638-1657`). Static `FeatureFlags` (`projectionist/config_store.py:486`) are owner toggles, not experiments, and that is fine. Roadmap: local release-over-release deltas and a maintainer dogfood cohort, not a flag vendor (GRO-028).

## 3. Foundations challenged

| Assumption | Evidence for | Evidence against | Verdict | Cost of change | Rationale |
|---|---|---|---|---|---|
| #5 "Zero telemetry SaaS" | No phone-home; no frontend analytics; CA/README promise (`README.md:204-206`) | A local interaction stream exists, is default **on** (`ingestion.py:77-85`), and is not named in `docs/PRIVACY.md` (only "Watch telemetry", `:291`) | **Keep** no phone-home; **Change** the wording to "no telemetry leaves your server" and disclose the local stream | XS–S | The promise is the brand. The current wording is technically false locally, which is exactly the kind of gap that destroys trust (GRO-015) |
| "We can't measure because it's self-hosted" (implicit) | No SaaS backend to collect into | SQLite already stores impressions-adjacent data; owner-only dashboards exist (`LlmUsagePage.tsx`) | **Remove** | M | Measure locally, show the owner, export nothing (GRO-014, GRO-025) |
| #1 Chat is the primary product | Nav order, landing `/` → `/chat`, Help "Start with Chat" (`docs/HELP.md:5`) | Unmeasurable today: chat turns aren't recorded (GRO-007) | **Investigate** | S once GRO-007 ships | We may be right; we can't currently know |
| Persona "village" names in member UI (added) | Personality is a differentiator (`projectionist/agent/village.py:36-60`) | Four names for one voice on one screen (GRO-009) | **Change** — one speaking name per surface | S | Personality works only if it is consistent |
| #18 Help/Privacy as first-class in-app docs | Strong role-split docs (`frontend/src/pages/HelpPage.tsx`, `docs/DOCS_STYLE.md`) | Guest TOC duplicates; repo filenames in member intro (GRO-022) | **Keep** | — | Best content asset in the product |
| #22 About ships the entire CHANGELOG | Full transparency | 7,048 DOM nodes for a guest About page on QA; version dropdown of ~250 releases | **Change** — latest 5 + link | S | About is a trust page, not an archive (GRO-023) |
| #21 What's New modal even on `/login` | Release benefit surfacing | Not observed this run | **Investigate** | — | Need `whats_new_seen` event to judge (tracking plan) |
| #19 Invite-only join | Household safety default (`config_store.py:492`) | Join dead-ends hurt the only member acquisition step (GRO-012) | **Keep** policy; **Fix** copy | XS | Policy is right; the failure state is not |
| Lifecycle opt-in by default | `_schema.py:1002-1006`, `:1844` | Low reach (1 of 5 QA members opted into the newsletter per Batch 1) | **Keep** | — | Reach is a copy and timing problem, not a default problem (GRO-001) |
| A/B testing as the experimentation model (added) | Industry default | N ≤ 6 per household | **Remove** from consideration | — | Use release-over-release and persona comparison instead (GRO-028) |

## 4. If we built it today

From zero, the growth and analytics layer would be **one local event contract**. That means a single `events` table with a typed schema (`name`, `user_id`, `surface`, `item_id`, `rec_id`, `props_json`, `ts`), written by domain code (agent, play, notifications), never by route handlers, with message text banned at the type level. On top of it would sit one **owner Household Pulse page**: nights with a pick, week-2 return of newly invited members, lifecycle read-to-play, chat answer quality, and youth-gate violations. It would hold 90 days and export nothing.

Content would sit on a **glossary-backed string layer**: one name for the operator ("the owner"), one speaking persona name per surface, and a lint rule that blocks `Admin →`, `SMTP`, `extras`, `token`, and `(migrated)` from member-visible strings. Lifecycle would be a single scheduler that applies three gates to every channel before it writes: opt-in, youth rating, and "has something to say".

Today we have three overlapping telemetry stores (`system_telemetry_stream`, `telemetry_events`, `llm_usage`), only the quality loop and cost loop are wired well, and the curator speaks in four names. Closing the gap is **worth it and cheap**. Most of the data already exists in SQLite, and what's missing is attribution and the chat event. The estimate is roughly two to three engineer-weeks for the event spine plus Pulse, and one week for the copy pass.

## 5. Findings by surface

### Public (`/login`, `/join`, `/help`, `/about`, `/privacy`; plus GitHub / Docker Hub / Unraid CA)

What works: the glass-door login is calm and focused, with one heading, one form, and a request-access path that asks for little (name required; email and note optional) and is protected by a honeypot (`frontend/src/pages/LoginPage.tsx:404-415`). The success message tells you where the request goes ("The owner will see it in their inbox.", `:389`). Help and Privacy are public, warm, and specific (GRO-004).

What doesn't: `/join` without a valid token shows "You're invited" above "This invite is not available." and a red "This join link is missing a token.", with only "Already a member? Sign in" as a way out (`gro_join_no_token_1440.png`, `gro_join_bad_token_1440.png`; GRO-012). Login names the operator three ways (GRO-017). About tells guests "Household members sign in with Plex" while the QA login offers only a local password, offers guests "← Back to chat" they cannot use, and loads ~250 versions of release notes (GRO-023). No route is `noindex`, and every route is titled "Projectionist" (GRO-010, GRO-024). Off-site, the Docker Hub description points to the old repo name and has no README (GRO-013; the wider listing work is GRO-027).

**Grade: C.** IDs: GRO-004, GRO-010, GRO-012, GRO-013, GRO-017, GRO-022, GRO-023, GRO-024, GRO-027.

### Consumer (member / youth: chat, explore, inbox, settings, Year in Review)

What works: the named-kinship sentence is the best microcopy in the product: "You watched Don't Look Up (2021); Ant-Man (2015) — adam McKay worked on both." It is specific, checkable, and reused across For you, inbox, and newsletter (GRO-005). Notification settings explain every channel and badge which ones need the owner (`gro_member_notifications_1440.png`). Opt-ins are explicit, with a save button.

What doesn't: the curator's name changes from line to line (GRO-009, `gro_member_chat_1440.png`, `gro_member_inbox_1440.png`). Members are told to configure LLM providers (GRO-006). Inbox reasons start "qa-member, You watched…" with a mid-sentence capital (GRO-021). Year in Review shows a raw API string (GRO-020). Fourteen unread inbox items pile up as weekly "This week for you" notes stack, some saying nothing (GRO-011). Youth accounts can receive ungated newsletter and nudge picks (GRO-008).

**Grade: C−.** IDs: GRO-001, GRO-005, GRO-006, GRO-008, GRO-009, GRO-011, GRO-016, GRO-019, GRO-020, GRO-021.

### Owner (household operator in the product: setup, weekly letter, newsletters, inbox)

What works: owners control every channel from Admin → Newsletters with previews. The weekly letter promises restraint ("It never starts a purge", `frontend/src/components/admin/WeeklyLetterPanel.tsx:76`). The cost view is accurate and filterable (GRO-002).

What doesn't: the owner cannot see whether any of this works. There is no read rate, no newsletter-to-play, no invite-to-active, and no "nights with a pick" (GRO-014, GRO-025). The weekly letter's "dead weight" framing (`WeeklyLetterPanel.tsx:76`, `projectionist/notifications/weekly_letter.py:317`) fits the steward persona but reads as judgment of what the household watches. It is fine for owners only, and must never leak into member copy. The owner surface was assessed from code and from owner API reads, **not** a fresh owner browser walk (see Scope).

**Grade: C−.** IDs: GRO-002, GRO-014, GRO-025, GRO-028.

### Admin (`/admin/*` analytics and telemetry tooling)

What works: Library knowledge (`/admin/taxonomy`, `StagedAugmentationsPage.tsx:483-484`) turns closed-loop telemetry into reviewable work, the best "measure → act" loop in the codebase (GRO-003). Health → Usage shows LLM tokens and cost by purpose, model, and persona.

What doesn't: the interaction stream has owner APIs (`projectionist/web/app.py:1720`, `:1733`) but **no UI**. `telemetry_enabled` has no toggle anywhere in the app, only a DB config key (`projectionist/telemetry/ingestion.py:77-85`). Owners can't see or switch off what's collected (GRO-018, GRO-015).

**Grade: C.** IDs: GRO-003, GRO-015, GRO-018.

## 6. Findings by theme

**Content & microcopy.** At its best the copy is specific, warm, and honest: the kinship sentence, the Help opener ("not a Netflix top-10"), "This link works once." At its worst it leaks the machine: `(migrated)`, "web extras", "Admin → Mail (SMTP or Resend)", "Configuration", and raw API details. Direction: adopt the voice guide below, a ten-term glossary, and a lint (GRO-026), then rewrite the ten strings listed in Part B.

**Analytics & instrumentation.** The quality loop is excellent (GRO-003), the cost loop is good (GRO-002), and the product loop is missing (GRO-007, GRO-014). Direction: one event spine, attribution through `rec_id`, and an owner Pulse view.

**Lifecycle messaging.** Defaults and channel logic are right (GRO-001). Content gating, empty-send suppression, and email hygiene are not (GRO-008, GRO-011, GRO-016). Direction: three gates on every channel, plus a link back into the app in every email.

**Public conversion & SEO.** For a private app the right SEO answer is "nothing indexed." Today that answer is accidental, through obscurity rather than headers (GRO-010). Conversion means *invite redeemed → first night with a pick*. The invite failure states are the weak link (GRO-012).

**Acquisition (off-site).** GitHub, Hub, and CA are the real marketing site. The Hub listing is broken and the CA blurb is a troubleshooting note (GRO-013, GRO-027).

**Experimentation.** Not ready, and A/B is the wrong tool. Use release deltas and persona comparison (GRO-028).

## 7. Stop doing

- **Stop emitting telemetry from route handlers.** Emit from the domain action so new transports (SSE, MCP, voice) don't silently fall out of measurement (GRO-007).
- **Stop showing members instructions for owners.** "Configure an LLM provider", "reinstall with web extras", "check Configuration" (GRO-006, GRO-019).
- **Stop sending newsletters that say nothing.** Skip the send instead (GRO-011).
- **Stop shipping the full CHANGELOG to guests on `/about`.** Show the latest five plus a link (GRO-023).
- **Stop saying "zero-telemetry" without the qualifier.** Say "nothing leaves your server" and disclose what stays local (GRO-015).
- **Stop treating Docker Hub pull counts as adoption.** They include maintainer rollouts and CI (GRO-027).
- **Don't build A/B infrastructure** for households (GRO-028).

## 8. Strengths worth protecting

- **Opt-in-first lifecycle** (GRO-001). Never flip a default to on in order to raise reach.
- **Metadata-only telemetry contract and always-on cost accounting** (GRO-002). Any new event must pass `scrub_closed_loop_payload` and must never carry message text.
- **Closed-loop quality telemetry → staged augmentations → owner review** (GRO-003).
- **Role-split, teaching Help and Privacy** (GRO-004).
- **One explanation object reused across surfaces** (GRO-005). The newsletter, For you, and inbox all say the same honest "why".

## 9. Risks of inaction (6–12 months)

- Every department's success metrics stay unprovable. We will keep shipping chat, Live, and Play changes with no evidence that nights with a pick went up or down (GRO-007, GRO-014).
- A youth account gets an R-rated pick in a newsletter or nudge. For a household app that is the trust-ending incident, and it is avoidable with code that already exists (GRO-008).
- Members learn to ignore the inbox. The unread count grows by one empty or off-voice note a week, and when the meaningful note arrives nobody reads it (GRO-011, GRO-009).
- A public-profile household's `/help`, `/about` (with exact version), and `/login` get indexed under its custom domain, which is a privacy embarrassment and a version-fingerprinting aid (GRO-010).
- New installers bounce from a Hub page that points at the old name, and we never find out (GRO-013, GRO-027).

## 10. Recommended direction

**Sequence:** fix what members see this week (copy and youth gate), then instrument, then show the owner.

1. **Now (0–2 weeks):** GRO-008 youth gate on newsletter and nudges; GRO-006 / GRO-009 / GRO-012 / GRO-017 / GRO-020 copy fixes; GRO-011 skip empty sends; GRO-010 `noindex`; GRO-013 Hub description.
2. **Next (2–6 weeks):** GRO-007 `chat_turn` event; GRO-014 `rec_id` attribution and `play_start`; GRO-016 email opt-out link; GRO-015 / GRO-018 telemetry disclosure and toggle; GRO-026 glossary and lint.
3. **Later (6+ weeks):** GRO-025 Household Pulse; GRO-028 release-over-release comparison.

**What success looks like in 90 days:**
- On QA and Automat, `chat_turn` counts are within ±5% of `chat_messages` user-role rows for the same window. Today it is 1 against dozens.
- At least 80% of surfaced cards carry a `rec_id`.
- The owner Pulse shows "nights with a pick" per active member per week.
- Zero youth-gate violations across every channel, verified by test.
- Zero member-visible strings matching the banned-term lint.
- The weekly newsletter read rate (`read_at` set within 7 days) is measured and above 40%.
- The Docker Hub page shows a full README linking to `romwil/projectionist`.

## 11. Scorecard (1–5)

| Surface | Copy clarity | Voice consistency | Measurability | Lifecycle quality | Discoverability & index hygiene |
|---|---|---|---|---|---|
| Public | 3 — clean login; join and About failure states muddy | 3 — "owner / admin / server owner" drift | 1 — nothing measured | n/a | 2 — no `noindex`; one title for all routes; Hub stale |
| Consumer | 3 — kinship "why" excellent; LLM and ops leaks | 2 — four curator names on one screen | 1 — chat, search, and rec→play invisible | 3 — opt-in right; youth gap; empty sends | n/a |
| Owner | 3 — previews and restraint copy good | 3 — steward voice coherent | 2 — cost yes, outcomes no | 3 — rich channels; no read-to-play | n/a |
| Admin | 3 — dense but labeled | 3 | 3 — knowledge ops and LLM usage strong; interaction stream has no UI | n/a | n/a |

---

# Part B — Detailed findings

## 12. Scope & method

**Walked on QA `:8792` (headless Chromium, 1440×900 and 390×844):**
- Guest: `/login`, the "Need an invite?" request form, `/join` (no token), `/join?token=not-a-real-token`, `/about`, `/help`, `/privacy` (text capture only).
- Signed in as `qa-member`: `/chat`, `/settings/notifications`, `/inbox`, `/year-in-review/2026`, `/explore`, `/help`.

**Owner reads (curl, `qa-owner`, read-only):** `GET /api/admin/telemetry/summary?hours=2160` and `GET /api/admin/llm/usage`. A later owner read returned `Authentication required` (session dropped). No further owner calls were made.

**Browser tooling limit:** the shared `cursor-ide-browser` tab was locked on a private tab, but screenshots timed out and the tab list then emptied on every retry (four attempts). Per the stop-after-four rule, the walk switched to a **local headless Playwright Chromium** against QA `:8792`. It used a separate browser context, so no other agent's tab was touched. Passwords were read from the QA host env file into process environment variables only. They were not logged or written to this document. The one temporary login request body used for the owner API read was deleted right after use.

**Code:** every citation is `94fcd3f`. Telemetry: `projectionist/telemetry/*`, `projectionist/library/db/_telemetry.py`, `_schema.py`. Lifecycle: `projectionist/notifications/*`. Public pages: `frontend/src/pages/{Login,Join,About,Help}Page.tsx`, `frontend/index.html`, `projectionist/web/spa_routes.py`. Off-site: Docker Hub API, `gh api` repo traffic (read-only), `unraid/projectionist.xml`, `README.md`.

**Not reviewed:**
- A valid invite redeem, because creating an invite would mutate QA.
- Owner browser walk of Admin → Newsletters (the owner surface was assessed from code and API).
- The youth account in the browser. The youth newsletter gap is proved from code; whether QA's library currently produces an over-rated pick for `qa-youth` was not observed.
- Real email delivery (Mail is not configured on QA).
- What's New modal (did not appear).
- Live On.
- An LLM-configured chat (QA LLM unset).

**Screenshots (this department):** `gro_login_1440.png`, `gro_login_request_access_1440.png`, `gro_login_390.png`, `gro_join_no_token_1440.png`, `gro_join_bad_token_1440.png`, `gro_about_guest_1440.png`, `gro_help_guest_1440.png`, `gro_member_chat_1440.png`, `gro_member_explore_1440.png`, `gro_member_inbox_1440.png`, `gro_member_notifications_1440.png`, `gro_member_yir_1440.png`.

**Persona handoff note: verified.** In `gro_member_chat_1440.png` the thread list and persona chip read "The Professor" while the message header reads "CURATOR". The inbox newsletter reads "Curator (migrated)…" (`gro_member_inbox_1440.png`).

---

## Voice & tone guide (short)

**Who's talking.** The household's curator, a knowledgeable friend in the aisle who knows *this* library. One name per surface: the persona the member chose for chat, or the household default for letters. The name is never a storage name.

**Principles**
1. **Specific beats clever.** Name the title, the person, and the link ("Adam McKay worked on both"). Never write "you might like".
2. **Speak to the reader's power.** Members get things they can do. Owner-only fixes become "The owner can turn this on." Members never see `Admin →` paths, package names, protocols, or settings keys.
3. **One word per thing.** Use the glossary: **owner** (not admin, household admin, or server owner), **invite link** (not join link or token), **sign in** (not log in), **Inbox**, **curator** (lowercase as a role; the persona name as a name).
4. **Honest about limits, in one breath.** Say what didn't happen, then the next step: "This link is incomplete — ask whoever invited you to send it again."
5. **Warm, not cute.** One flourish per screen at most. No inside jokes about SaaS or about the stack.
6. **Errors are sentences, not codes.** Never show an API `detail` raw.
7. **Youth-safe by default.** Copy shown to youth never names a blocked title or rating.

**Tone by moment:** sign-in is brief and reassuring. Recommendations are specific and confident. Empty states say what's coming and when. Errors are calm and give one next step. Owner letters are candid stewardship, and that candour stays in owner channels.

## The 10 most important strings: rewrites

| # | Current string (exact) | Where at `94fcd3f` | Proposed replacement | Why |
|---|---|---|---|---|
| 1 | "Here's what I found in your library. Configure an LLM provider for richer conversation." | `projectionist/agent/curator.py:414` | Member/youth: "Here's what I found in your library." Owner only (separate muted line): "Tip: connect an AI provider in Admin → Connections for fuller answers." | Members can't act on it; it appears on every no-LLM reply (GRO-006) |
| 2 | "Hi — I'm {curator_name}. What should we dig into today?" with fallback name `"Curator"` | `frontend/src/components/WelcomePanel.tsx:1`; fallback `frontend/src/App.tsx:464` | "Hi, I'm {persona_display_name}. What are you in the mood for tonight?" (resolved from the thread's persona; never the literal "Curator") | Sets the single speaking name; ties to the nightly job (GRO-009) |
| 3 | `f"{name} (migrated)"` (renders as "Curator (migrated) put together a few notes for you.") | `projectionist/library/db/_schema.py:1600`; voice line `projectionist/notifications/newsletters.py:53` | Persona name stays `{name}`; mark migration in a separate column. Voice line: "{persona_display_name} picked a few for you this week." | Storage artifact leaks into member inbox (GRO-009) |
| 4 | "Nothing new this week shares a subject, a creator, or a franchise with what you have watched." | `projectionist/notifications/newsletters.py:194` | Don't send. In the in-app preview only: "Quiet week — nothing new connects to what you've watched yet. We'll write when something does." | Empty sends teach members to ignore the inbox (GRO-011) |
| 5 | "Ask the household admin for a join link, or send a request below." | `frontend/src/pages/LoginPage.tsx:374` | "Ask the owner for an invite link — or send a request and it'll land in their inbox." | One noun; matches the success message at `:389` (GRO-017) |
| 6 | "No sign-in methods are enabled. Ask the owner to check Configuration." | `frontend/src/pages/LoginPage.tsx:230` | "Sign-in isn't set up yet. If you run this server, open Admin → Access. Otherwise, let the owner know." | "Configuration" doesn't exist as a label; splits the audience correctly (GRO-017) |
| 7 | "This join link is missing a token." (under eyebrow "You're invited" and lede "This invite is not available.") | `frontend/src/pages/JoinPage.tsx:44`, `:163`, `:170` | Eyebrow "Invite"; title "This invite link didn't work"; body "It may be incomplete, already used, or expired. Ask whoever invited you to send a fresh link." Plus a secondary "Request access" button when access requests are on. | Dead end on the only member acquisition step (GRO-012) |
| 8 | "Owners configure the stack once. Household members sign in with Plex. Nobody has to pretend this is a SaaS marketing site." | `frontend/src/pages/AboutPage.tsx:96` | "The person who runs this server sets it up once. Everyone else in the house just signs in — no account with us, no cloud." | False on local-only installs; inside joke to guests (GRO-023) |
| 9 | "Apprise package is not installed on this server yet — ask the owner to reinstall with web extras." | `frontend/src/pages/settings/NotificationsSettingsPage.tsx:296` | "Push alerts (Discord, Telegram, phone) aren't available on this server yet. The owner can turn them on." | Package jargon to members (GRO-019) |
| 10 | "Year in Review not available yet" (raw API detail rendered as the page) | `projectionist/web/app.py:3081`; intended copy `frontend/src/pages/YearInReviewPage.tsx:160` ("…then ask the owner to generate.") | "Your {year} reel isn't ready. Turn on Year in Review in Settings → Notifications, then tap **Generate & send to me**." Link to `/settings/notifications`. | Raw API string; and the intended copy contradicts the self-serve button at `NotificationsSettingsPage.tsx:406` (GRO-020) |

---

## Tracking plan

### What the code emits today (at `94fcd3f`)

| Store | Event / row | Emitted from | Properties | Gate | Retention | Owner UI | QA 90-day count |
|---|---|---|---|---|---|---|---|
| `system_telemetry_stream` | `chat_message` | `projectionist/web/chat_routes.py:131` — **legacy `POST /api/chat` only** | session_id, lens_id, message_length, persona_id, user_id | `telemetry_enabled` (default true) `ingestion.py:77-85` | 90 d (`scheduler/tasks/data_retention.py:8`) | none (API `app.py:1720`, `:1733`) | **1** |
| same | `chat_feedback` | `chat_routes.py:267` | message_id, feedback_type, session_id, user_id | same | same | none | 0 |
| same | `preference_signal` | `projectionist/web/app.py:3737` | signal_type, media_reference_count, user_id | same | same | none | 0 |
| same | `review_saved` | `app.py:4126` | rating_key, stars, prompted_by, user_id | same | same | none | 0 |
| same | `playback_event` | `projectionist/web/webhooks.py:204` (Plex webhook only) | event, rating_key, completion_pct, media_type | same | same | none | 0 |
| same | `tool_invocation` | `projectionist/agent/curator.py:547`, `:905` | tool_name, duration_ms, result_count, session_id | same | same | none | 13 |
| `llm_usage` (+ mirror event) | per LLM call | `telemetry/llm_track.py:42` via `curator.py`, `village.py:814`, `embeddings.py:85`, `seasonal_curation.py:223`, `llm_logline_enrichment.py:90`, `library_routes.py:1769` | purpose (8 values, `llm_usage.py:18-36`), model, provider, tokens, latency, estimated_usd, persona_id, session_id, user_id | **always** (`tests/test_llm_usage.py:91-92`) | 90 d (`data_retention.py:38`) | Health → Usage (`LlmUsagePage.tsx`) | 128 (mirror) |
| `telemetry_events` (closed loop) | `coverage_deficit`, `metadata_demand`, `explore_miss`, `bad_neighbor_match`, `kinship_miss`, `unmapped_token` | `telemetry/coverage.py:14`, `demand.py:15`, `explore.py:14-15`, `kinship_miss.py:21`, `facets/closed_loop.py:68`; fired from `app.py:1109`, `library_routes.py:126`, `library/feeds.py:1470`, `library/relations.py:739`, `recommendation_reasons.py:1235` | entity_type, entity_key, scrubbed payload, hit_count | independent of flag | cap 10,000 rows (`_telemetry.py:29`) | Library knowledge (`StagedAugmentationsPage.tsx:483-484`) | not read |
| Derived (not events) | `watch_events` / `watch_sessions` | Plex sources only (`watch_tracker/models.py:11-21`) | — | — | — | Overview %s | — |
| Derived | `user_notifications.read_at` / `seen_at` | `library/db/_notifications.py:100-102`, `:293` | — | — | — | none | — |
| Frontend | nothing | `git grep` for analytics, beacon, or track events in `frontend/src` returns **0** | — | — | — | — | — |
| Search | nothing | no telemetry in search routes; `telemetry/` has no search event | — | — | — | — | — |

### Blind spots (named)

1. **Streaming chat**, which is the primary product loop (GRO-007).
2. **Search queries and zero results**, both library and "beyond".
3. **Impressions and opens** for For you, rails, chat cards, inbox, newsletter, nudges, and Live.
4. **Recommendation → play attribution.** In-app Play likely surfaces only as a Plex session with no Projectionist source flag (Likely; `models.py:11-21`) (GRO-014).
5. **Setup funnel** (wizard steps), **invite funnel** (created → redeemed → first sign-in), and **access request → approved**.
6. **Lifecycle outcomes**: delivered → read → item opened → played. `read_at` exists, but nothing joins it.
7. **Opt-in changes** and their reasons.
8. **Errors shown to users** (`formatApiError` paths), youth 403s, and player errors.
9. **What's New** seen and dismissed.
10. **Acquisition**: the box can't know how it was installed. Off-site signals (GitHub traffic, Hub pulls, CA installs) are polluted by maintainer automation.

### Proposed events (local only, metadata only, one table)

All events: `{name, ts, user_id, role, is_youth, surface, client: web|mcp|theater}`. No message text, no query text beyond length and a hashed normalized form for repeat detection, and no titles in props (use `item_id`).

| Event | When | Key properties |
|---|---|---|
| `session_start` | first authenticated request after 30 min idle | device_class (phone/tablet/desktop), theme |
| `chat_turn` | agent finishes a turn (any transport) | session_id, persona_id, lens_id, message_length, tool_count, cards_returned, llm_configured, first_token_ms, outcome (`cards`/`text_only`/`fallback`/`error`) |
| `chat_feedback` | thumbs set or cleared | message_id, value (`up`/`down`/`cleared`) |
| `search` | results rendered | query_len, query_hash, scope (`library`/`beyond`), result_count, zero_result |
| `rec_impression` | card visible ≥ 1 s (batched) | rec_id, item_id, surface (`for_you`/`rail:<id>`/`chat_card`/`inbox`/`newsletter`/`nudge`/`live`), position, reason_kind (`named_kinship`/`because_watched`/`seasonal`/…) |
| `rec_open` | title sheet opened from a card | rec_id, item_id, surface |
| `play_start` | in-app Play begins, or Plex session correlated to a rec within 24 h | item_id, rec_id?, source (`in_app`/`plex`) |
| `play_complete` | ≥ 90% or end card | item_id, rec_id?, completion_pct |
| `rate` | stars saved | item_id, stars, prompted_by |
| `watchlist_add` / `watchlist_remove` | — | item_id, rec_id?, surface |
| `notification_delivered` | inbox/email/Apprise write | notification_id, kind, channel |
| `notification_read` | `read_at` set | notification_id, kind, age_hours |
| `notification_item_open` | open from inbox card | notification_id, item_id, rec_id |
| `optin_changed` | Settings → Notifications save | kind (`newsletter`/`nudge`/`yir`/`email`/`apprise`/`inbox`), value |
| `setup_step_completed` | wizard step | step, duration_s |
| `invite_created` / `invite_redeemed` / `access_request_created` / `access_request_resolved` | — | invite_id, is_youth, method, outcome |
| `error_shown` | user-visible error | code, surface, http_status |
| `whats_new_seen` | modal shown or dismissed | version, action |
| `youth_gate_block` | any channel filtered a title for youth | channel, rating |

### Funnels

- **Installer activation (local):** setup started → Plex connected → first library indexed → first `chat_turn` with `cards_returned > 0` → second-week `session_start`. Off-box steps (GitHub → Hub/CA → pull) are reported separately from GitHub traffic and Hub, labeled as polluted.
- **Member activation:** `invite_created` → `invite_redeemed` → first `session_start` → first `rec_open` → first `play_start` → `session_start` in week 2.
- **Nightly loop (core):** `session_start` → `rec_impression` → `rec_open` → `play_start` → `play_complete` → `rate`.
- **Lifecycle:** `notification_delivered` → `notification_read` → `notification_item_open` → `play_start` (same `rec_id`).
- **Chat quality:** `chat_turn` → `outcome=cards` → `rec_open` from chat → `play_start`.

### North star and guardrails

- **North star: Nights with a pick.** The weekly count of distinct (member, local date) where a title carrying a Projectionist `rec_id` was played ≥ 20 minutes within 24 hours of its impression or open. Report it per active member.
- **Guardrails:**
  - `youth_gate_violations` = 0. A blocked-rating title reaching any youth channel counts as a violation; the target is zero.
  - Lifecycle opt-out rate < 10% per 4 weeks.
  - Median unread inbox backlog ≤ 5.
  - Chat `outcome=error|fallback` < 5% when an LLM is configured.
  - p95 `first_token_ms` < 4 s.
  - Weekly LLM spend within the owner-set budget.
  - Kinship-miss rate on opened titles (existing `opened_explainable_coverage`, `telemetry/kinship_miss.py:299`) trending down.

---

## 13. Strengths

### GRO-001: Keep every lifecycle channel opt-in by default

| Field | Value |
|---|---|
| Type | Strength |
| Surface | Consumer |
| Persona(s) | Returning consumer, youth, power consumer |
| Category | Lifecycle messaging |
| Severity | Medium |
| Impact | 4 |
| Effort | XS |
| Confidence | Confirmed |
| Priority score | 8.0 |
| Verdict | Protect |
| Dependencies | GRO-008, GRO-016 |
| Labels | lifecycle, consent, defaults |

**Evidence:** Column defaults `notify_channel_inbox` 1, `notify_channel_email` 0, `newsletter_opt_in` 0, `nudge_opt_in` 0, `notify_channel_apprise` 0 (`projectionist/library/db/_schema.py:1002-1006`); `year_in_review_opt_in` 0 (`:1844`). Channel logic requires opt-in for nudge and Year in Review on every channel, and newsletter opt-in for digest email and Apprise (`projectionist/notifications/service.py:39-66`). `deliver_weekly_newsletters` skips non-opted users and counts them (`projectionist/notifications/newsletters.py:249-251`). The settings help text says "Opt in to…" for each (`NotificationsSettingsPage.tsx:318`, `:326`, `:334`; `gro_member_notifications_1440.png`).

**Current state:** No member gets email, push, nudges, newsletters, or a reel without choosing it. Inbox is the only default-on channel and stays inside the app.

**Root cause:** A deliberate consent-first design.

**Recommendation:** Protect this. Never default a new channel or kind to on. Any new kind added to `NOTIFICATION_KINDS` (`_notifications.py:15-25`) must ship with an explicit opt-in column defaulting to 0, or be inbox-only. Raise reach through copy and timing (a single post-first-play "Want a weekly note?" prompt), not defaults.

**Rationale:** In a household app every message comes from someone the reader lives with. Unwanted mail damages the relationship, not just the product.

**User story:** As a household member, I want to choose what Projectionist sends me so that it never feels like spam from my own house.

**Acceptance criteria:**
- [ ] A test asserts every opt-in column defaults to 0 for a new user.
- [ ] A new notification kind without an opt-in path fails a unit test.

**Success metric:** Opt-out rate < 10% per 4 weeks once `optin_changed` exists.

**Validation:** Create a fresh member on QA; confirm all toggles except In-app inbox are off.

### GRO-002: Preserve the metadata-only telemetry contract and always-on cost accounting

| Field | Value |
|---|---|
| Type | Strength |
| Surface | Admin |
| Persona(s) | Owner, platform admin |
| Category | Analytics & instrumentation |
| Severity | Medium |
| Impact | 4 |
| Effort | XS |
| Confidence | Confirmed |
| Priority score | 8.0 |
| Verdict | Protect |
| Dependencies | GRO-007, GRO-015 |
| Labels | telemetry, privacy, llm-cost |

**Evidence:** Module contract: "callers MUST NOT pass raw message text or secrets… Credential-like keys are stripped" (`projectionist/telemetry/ingestion.py:12-15`). `chat_message` records `message_length`, not text (`chat_routes.py:131-137`). `record_llm_usage` drops `prompt`, `messages`, `content`, `text`, and `usage` from meta (`ingestion.py:275-280`). `llm_usage` is recorded even when interaction telemetry is off (`tests/test_llm_usage.py:91-92`). 90-day retention (`scheduler/tasks/data_retention.py:8-10`, `:38`). The owner view is filterable by model, purpose, and persona (`frontend/src/pages/LlmUsagePage.tsx:130`).

**Current state:** Owners can see spend without the system storing what anyone said.

**Root cause:** A privacy-first engineering norm.

**Recommendation:** Protect this. Every event in the tracking plan must go through the same scrub. Add a type-level guard: event props of type `str` longer than 64 characters are rejected unless whitelisted. Keep cost accounting independent of the interaction toggle, since cost is operational, not behavioral.

**Rationale:** The measurement program in this review is only acceptable if this contract holds.

**User story:** As an owner, I want to see what the curator costs without anyone's conversations being logged twice.

**Acceptance criteria:**
- [ ] A test fails if any event payload contains a key in the banned set.
- [ ] `llm_usage` still records when `telemetry_enabled=false`.

**Success metric:** 0 events with free text > 64 characters in a 30-day audit.

**Validation:** Query `system_telemetry_stream.payload_json` on QA for long string values.

### GRO-003: Keep closed-loop quality telemetry feeding owner-reviewed augmentation

| Field | Value |
|---|---|
| Type | Strength |
| Surface | Admin |
| Persona(s) | Established owner at scale |
| Category | Analytics & instrumentation |
| Severity | Medium |
| Impact | 3 |
| Effort | XS |
| Confidence | Confirmed |
| Priority score | 6.0 |
| Verdict | Protect |
| Dependencies | — |
| Labels | closed-loop, quality, knowledge-ops |

**Evidence:** Unified `telemetry_events` with dedupe on `(event_type, entity_type, entity_key)` and `hit_count` (`_schema.py:1669-1684`). Six event types fired at the point of failure (`telemetry/explore.py:14-15`, `kinship_miss.py:21`, `coverage.py:14`, `demand.py:15`, `facets/closed_loop.py:68`). Funnel observed → threshold → staged → approved/rejected (`_telemetry.py:373-415`). Surfaced in Library knowledge (`StagedAugmentationsPage.tsx:483-484`). Bounded at 10,000 rows (`_telemetry.py:29`).

**Current state:** When Explore returns empty or a title has no named kinship, the system remembers, enriches in idle time, and asks the owner to approve. That is measurement that changes the product.

**Root cause:** Designed as an observe → stage → promote loop (SPEC-2026-AUG-001 per `_schema.py:1662-1665`).

**Recommendation:** Protect this. Model the product event spine on this: emit at the domain point, dedupe, show the owner, act. Don't merge it into the behavioral stream. Entity-level quality signals and user-level behavior have different privacy profiles.

**Rationale:** It is the one loop where data already becomes better recommendations.

**User story:** As an owner, I want to know which titles show blank "related" shelves so that I can fix them in my Monday pass.

**Acceptance criteria:**
- [ ] Event types remain entity-scoped (no `user_id` in payload).
- [ ] The cap and pruning remain.

**Success metric:** Approve rate and pending count stay visible; kinship-miss rate on opened titles falls release over release.

**Validation:** Open `/admin/taxonomy` on QA as owner; confirm the 30-day trend and top events render.

### GRO-004: Keep Help and Privacy as teaching, role-split, public docs

| Field | Value |
|---|---|
| Type | Strength |
| Surface | Public |
| Persona(s) | First-time household member, installer, older/low-vision user |
| Category | Content & help |
| Severity | Medium |
| Impact | 3 |
| Effort | XS |
| Confidence | Confirmed |
| Priority score | 6.0 |
| Verdict | Protect |
| Dependencies | GRO-022 |
| Labels | help, privacy, content |

**Evidence:** Help opens with a value statement grounded in ownership ("It talks to *your* Plex catalog — not a Netflix top-10", `docs/HELP.md:3`), then a "Start here" goal→where table (`:11-30`), then worked prompts. Role split via `markdownForRole` with the guest view labeled "Viewing as Guest" (`frontend/src/pages/HelpPage.tsx:210-213`; `gro_help_guest_1440.png`). Privacy opens "written for the people who use the app — not only for operators" with a "short version" (QA `/privacy` text capture). `docs/DOCS_STYLE.md` defines audience, voice, and a definition of done.

**Current state:** This is the closest thing Projectionist has to a marketing site, and it's good. It explains *why*, not just *where*.

**Root cause:** Docs treated as a first-class deliverable.

**Recommendation:** Protect this. Keep both public without login. Keep anchors stable. Extend `DOCS_STYLE.md` with the UI voice guide in this document so the same bar applies to `frontend/src` strings (GRO-026).

**Rationale:** For a self-hosted product the help page is the onboarding, the sales pitch, and the support desk.

**User story:** As a newly invited member, I want a plain-language guide before I sign in so that I know what this is.

**Acceptance criteria:**
- [ ] `/help` and `/privacy` return 200 for guests.
- [ ] Member render contains no owner-section headings.

**Success metric:** Once `error_shown` and session events exist, a falling share of members who open Help in their first session and then send no chat turn.

**Validation:** Load `/help` as guest and as `qa-member`; diff headings.

### GRO-005: Keep one honest "why" sentence reused across For you, inbox, and newsletter

| Field | Value |
|---|---|
| Type | Strength |
| Surface | Consumer |
| Persona(s) | Returning consumer, power consumer |
| Category | Content & microcopy |
| Severity | Medium |
| Impact | 4 |
| Effort | XS |
| Confidence | Confirmed |
| Priority score | 8.0 |
| Verdict | Protect |
| Dependencies | GRO-021 |
| Labels | explainability, recommendations, copy |

**Evidence:** `specific_bridge` returns the shared `watched_bridge` sentence (`projectionist/notifications/recommendation_reasons.py:843-853`). For example, `f"{creator} worked on both"` (`:745`). The newsletter uses it as the body line: "Body line is the shared watched_bridge sentence (same object as For you)" (`projectionist/notifications/newsletters.py:185`). QA inbox: "You watched Don't Look Up (2021); Ant-Man (2015) — adam McKay worked on both." (`gro_member_inbox_1440.png`).

**Current state:** Recommendations explain themselves with a checkable fact, the same way everywhere.

**Root cause:** One explanation object, not per-surface copy.

**Recommendation:** Protect this. Never fall back to generic "you might like" when no bridge exists. The newsletter already drops picks without a `why` (`newsletters.py:183-184`); keep that. Fix casing at the join points (GRO-021) without forking the sentence.

**Rationale:** Explainability is the product's main differentiator against blended-profile recommenders (benchmarks: Diskovarr reason tags, Vanguarr manifests).

**User story:** As a member, I want to know why a title was picked so that I can trust the next pick.

**Acceptance criteria:**
- [ ] Every surfaced pick in inbox, newsletter, and For you has a non-empty `why`.
- [ ] A test asserts the newsletter and For you return the same sentence for the same pair.

**Success metric:** `rec_open` rate on `reason_kind=named_kinship` ≥ 1.5× generic rails.

**Validation:** Compare For you card text with the inbox card for the same title on QA.

---

## 14. Weaknesses (sorted by priority score)

### GRO-006: Stop telling members to configure an LLM provider

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Consumer |
| Persona(s) | Household member, youth |
| Category | Content & microcopy |
| Severity | Medium |
| Impact | 4 |
| Effort | XS |
| Confidence | Confirmed |
| Priority score | 8.0 |
| Verdict | Fix |
| Dependencies | GRO-026 |
| Labels | copy, audience, chat |

**Evidence:** `projectionist/agent/curator.py:414`: "Here's what I found in your library. Configure an LLM provider for richer conversation."; also `:405-408` ("…or configure an LLM provider for richer conversation."). On QA as `qa-member`, every reply in the visible thread ends with it (`gro_member_chat_1440.png`).

**Current state:** The no-LLM fallback addresses the owner but renders to everyone, so each member reply ends with an instruction they cannot follow.

**Root cause:** The agent fallback has no audience context and the copy was written for the single-owner default.

**Recommendation:** Return `"Here's what I found in your library."` for every role. Emit an owner-only `notice` block (`{kind:"owner_hint", text:"Tip: connect an AI provider in Admin → Connections for fuller answers.", href:"/admin/connections"}`) rendered only when `role=owner`. Apply the same change to `:405-408`.

**Rationale:** It undermines the curator's voice on every turn and makes the household feel broken. Rejected alternative: hiding the fallback entirely, which would leave members with no explanation for thin answers.

**User story:** As a member, I want the curator to answer me without chores I can't do.

**Acceptance criteria:**
- [ ] Member and youth fallback replies contain no "LLM" or "provider".
- [ ] Owner sees one dismissible hint linking to Connections.

**Success metric:** 0 member-visible strings matching `/LLM|provider/i` in chat (lint, GRO-026).

**Validation:** QA with LLM unset: send a chat as `qa-member` and as `qa-owner`; compare.

### GRO-007: Emit a chat turn event from the agent so streaming chat is measured

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Cross-cutting |
| Persona(s) | Owner, maintainer, every department relying on chat metrics |
| Category | Analytics & instrumentation |
| Severity | High |
| Impact | 4 |
| Effort | S |
| Confidence | Confirmed |
| Priority score | 6.0 |
| Verdict | Fix |
| Dependencies | Blocks GRO-014, GRO-025, GRO-028 |
| Labels | telemetry, chat, north-star |

**Evidence:** `chat_message` is emitted only in `POST /api/chat` (`projectionist/web/chat_routes.py:106-137`). `POST /api/chat/stream` (`:341-415`) records only scheduler activity (`:362`). The SPA uses `sendChatStream` exclusively (`frontend/src/api/client.ts:1217-1239`; callers `useChatSession.ts:844`, `SeasonalPickChatPane.tsx:84`, `InboxPage.tsx:11`). QA owner `GET /api/admin/telemetry/summary?hours=2160` → `detail: {llm_usage: 128, tool_invocation: 13, chat_message: 1}`, while `qa-member` alone shows eight-plus threads (`gro_member_chat_1440.png`).

**Current state:** The interaction stream undercounts the core loop by roughly two orders of magnitude. Any "chat engagement" metric built on it is wrong.

**Root cause:** Telemetry attached to route handlers. When streaming replaced the JSON route, measurement didn't move with it.

**Recommendation:** Emit `chat_turn` from `CuratorAgent` at turn completion, on both the stream and non-stream paths and MCP. Properties: `session_id, persona_id, lens_id, message_length, tool_count, cards_returned, llm_configured, first_token_ms, outcome`. Keep `record_chat_message` as a deprecated alias for one release, then remove it. Add a test that a streamed turn writes exactly one `chat_turn`.

**Rationale:** Chat is sacred cow #1. Without this it can be neither defended nor challenged. Rejected alternative: deriving counts from `chat_messages`, which gives no outcome, latency, or cards data, and mixes in assistant rows.

**User story:** As the maintainer, I want to know how many chat turns produce cards so that I can tell whether chat is the right front door.

**Acceptance criteria:**
- [ ] One `chat_turn` per user message on `/api/chat/stream`.
- [ ] Count within ±5% of user-role `chat_messages` over 7 days.
- [ ] No message text in payload.

**Success metric:** `chat_turn` coverage ≥ 95% of user turns.

**Validation:** Send three streamed messages on QA; query the stream table for three `chat_turn` rows.

### GRO-008: Apply the youth rating gate to newsletters and nudges

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Consumer |
| Persona(s) | Youth, owner (parent) |
| Category | Lifecycle messaging |
| Severity | High |
| Impact | 4 |
| Effort | S |
| Confidence | Confirmed |
| Priority score | 6.0 |
| Verdict | Fix |
| Dependencies | GRO-001 |
| Labels | youth, lifecycle, safety |

**Evidence:** `build_member_newsletter` picks from the household `new_this_week` digest and explains via `specific_bridge(db, row, watched)` with no rating check (`projectionist/notifications/newsletters.py:141-195`). `specific_bridge` has no youth parameter (`recommendation_reasons.py:843-853`), while the sibling `named_bridge_for_item` accepts `youth_max_rating` and filters (`:931-949`, `_youth_row_allowed` `:1158-1163`). `projectionist/notifications/nudges.py` has no youth or rating check (grep at `94fcd3f`). Whisper explicitly excludes youth (`projectionist/notifications/whisper.py:113`). There is no youth reference in `projectionist/digest/service.py`.

**Current state:** A youth account that opts into the weekly newsletter or nudges can be sent a newly added title above its rating ceiling, with a title, poster, and "you have to see" copy. Play may still 403, but the recommendation itself is the harm.

**Root cause:** The youth gate is applied per surface instead of in the delivery pipeline.

**Recommendation:** In `deliver_notification` (`service.py:69`), when `user.is_youth` and the notification carries `rating_key`, `tmdb_id`, or `payload.picks`, drop items that fail `content_rating_allowed(..., max_rating=user.youth_max_rating)` and record `youth_gate_block`. Also switch the newsletter to `named_bridge_for_item(..., youth_max_rating=...)`. If a youth newsletter ends up empty, skip it (GRO-011).

**Rationale:** This is the most trust-damaging lifecycle failure possible in a family product, and the filter already exists. Rejected alternative: excluding youth from newsletters entirely like whisper, which is safe but removes a feature youth can legitimately enjoy.

**User story:** As a parent owner, I want every message my kid's account receives to respect their rating limit.

**Acceptance criteria:**
- [ ] Unit test: youth user + R-rated new title → newsletter contains 0 picks with that title.
- [ ] Same test for nudges.
- [ ] `youth_gate_block` event recorded.

**Success metric:** `youth_gate_violations` = 0 across all channels.

**Validation:** On QA, opt `qa-youth` into newsletter, seed an R title in "new this week", run the newsletter task, and inspect the inbox.

### GRO-009: Give the curator one speaking name and never show storage names

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Consumer |
| Persona(s) | Every member, youth |
| Category | Voice & tone |
| Severity | High |
| Impact | 4 |
| Effort | S |
| Confidence | Confirmed |
| Priority score | 6.0 |
| Verdict | Fix |
| Dependencies | GRO-026 |
| Labels | persona, brand, copy, lifecycle |

**Evidence:**
- QA `qa-member` chat: the thread list and composer chip read "The Professor", and the message header reads "CURATOR" (`gro_member_chat_1440.png`). Name fallbacks are hard-coded `"Curator"` in `frontend/src/App.tsx:464`, `ChatThread.tsx:288`, `:304`, `:451`, `AgentAvatar.tsx:9-10`, `WelcomePanel.tsx:19`, and `useChatSession.ts:645`, `:792`.
- QA inbox: "Hi qa-member, Curator (migrated) put together a few notes for you." (`gro_member_inbox_1440.png`). The name comes from `f"{name} (migrated)"` (`projectionist/library/db/_schema.py:1600`) via `_persona_voice_line` choosing the household default template (`newsletters.py:29-53`).
- Nudges: "Enthusiastic Scout here: you have to see September 5 (2024)." (`nudges.py:126`; inbox).
- Village display names (`agent/village.py:36-60`).

**Current state:** A member meets three or four names for one voice in one session, one of which exposes a migration artifact.

**Root cause:** There is no single "speaking persona" resolver. Chat uses the thread persona, letters use the household default template, and the UI falls back to a literal string. Template `name` doubles as display name and storage key.

**Recommendation:**
1. Add `resolve_speaking_persona(user, surface)` → `{display_name, avatar}`. Chat uses the thread persona. Letters and nudges use the member's default persona (Settings → Voice), then the household default.
2. Add `display_name` to persona templates; migrations set `display_name = original name` and keep `(migrated)` only in an internal `origin` column.
3. Remove every `"Curator"` literal fallback in favor of the resolver.
4. Render the message header from the same resolver as the chip.

**Rationale:** Personality only works if it is consistent. Today it reads as broken. Rejected alternative: removing personas, which would throw away a differentiator.

**User story:** As a member, I want the curator I chose to be the one who talks to me everywhere.

**Acceptance criteria:**
- [ ] No member-visible string contains "(migrated)".
- [ ] The chat header name equals the composer persona chip in the same thread.
- [ ] The newsletter voice line uses the member's chosen persona.

**Success metric:** Lint: 0 hard-coded `"Curator"` display fallbacks in `frontend/src` outside the resolver.

**Validation:** QA: `qa-member` with "The Professor" selected; check the chat header, the next newsletter, and the next nudge.

### GRO-010: Mark every household page noindex and add a robots.txt

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Public |
| Persona(s) | Owner on the public ingress profile, household members |
| Category | SEO & index hygiene |
| Severity | Medium |
| Impact | 3 |
| Effort | XS |
| Confidence | Confirmed |
| Priority score | 6.0 |
| Verdict | Fix |
| Dependencies | GRO-024 |
| Labels | seo, privacy, public |

**Evidence:** QA `/robots.txt` → 404 JSON; `/sitemap.xml` → 404. `/login`, `/about`, `/help`, `/privacy`, `/join` all → 200 HTML with `<title>Projectionist</title>` and no robots meta (`frontend/index.html`). No `X-Robots-Tag` header on QA `/login` (CSP present, robots absent). The theater already sets `<meta name="robots" content="noindex" />` (`projectionist/theater/static/index.html:6`). `household_profile` supports `"public"` (custom domain / tunnel) (`projectionist/config_store.py:496-497`). The About page shows the running version to guests ("Version 1.37.72", `gro_about_guest_1440.png`).

**Current state:** A household that exposes Projectionist on a domain is indexable. That publishes the existence of a private media server, its Help content, and its exact version.

**Root cause:** The SPA shell was built for LAN, and the theater got the fix while the app didn't.

**Recommendation:**
- Add `<meta name="robots" content="noindex, nofollow, noarchive" />` to `frontend/index.html`.
- Send `X-Robots-Tag: noindex, nofollow` on every HTML response from `spa_routes.py`.
- Serve `/robots.txt` as `User-agent: *\nDisallow: /`.
- When `household_profile=public`, hide the version string from unauthenticated `/about` (show it after sign-in).
- **What should be indexed:** nothing on household instances. Discovery belongs on GitHub, Docker Hub, Unraid CA, and the docs/wiki.

**Rationale:** For a private app, being invisible to search engines is a feature. Rejected alternative: auth-walling `/help` and `/privacy`, which would break the honest pre-sign-in disclosure (GRO-004).

**User story:** As an owner on a custom domain, I want search engines to ignore my household app.

**Acceptance criteria:**
- [ ] `/robots.txt` returns `Disallow: /`.
- [ ] Every HTML route carries the robots meta and header.
- [ ] Public-profile `/about` hides the version for guests.

**Success metric:** 0 indexed pages for test domains after 60 days (site: search).

**Validation:** `curl -sI http://10.10.1.202:8792/login | grep -i x-robots`; `curl -s …/robots.txt`.

### GRO-011: Skip newsletters that have nothing to say

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Consumer |
| Persona(s) | Returning consumer |
| Category | Lifecycle messaging |
| Severity | Medium |
| Impact | 3 |
| Effort | XS |
| Confidence | Confirmed |
| Priority score | 6.0 |
| Verdict | Fix |
| Dependencies | GRO-008 |
| Labels | newsletter, inbox, relevance |

**Evidence:** When no linked picks exist, the body becomes "Nothing new this week shares a subject, a creator, or a franchise with what you have watched." and is still delivered (`projectionist/notifications/newsletters.py:190-197`, `:252-267`). The QA `qa-member` inbox shows four weekly "This week for you, qa-member" items and a 14-unread badge (`gro_member_inbox_1440.png`).

**Current state:** Members can receive a weekly note whose content is "nothing for you". It raises the unread count and teaches people to ignore the inbox.

**Root cause:** Delivery doesn't check content value before sending.

**Recommendation:** In `deliver_weekly_newsletters`, `continue` when `content["picks"]` is empty and count `skipped_empty` in the result. Show the "quiet week" line only in the owner preview. Optionally send at most one "quiet" note per 4 weeks, with the copy in rewrite #4.

**Rationale:** Relevance is the only currency an opt-in newsletter has. Rejected alternative: padding with generic picks, which would break GRO-005.

**User story:** As a member, I want the weekly note only when there's something for me.

**Acceptance criteria:**
- [ ] No `digest` notification is created when picks = 0.
- [ ] The result includes `skipped_empty`.

**Success metric:** Newsletter read rate ≥ 40% within 7 days.

**Validation:** Unit test with an empty `new_this_week`; on QA, run the task and confirm no new inbox row.

### GRO-012: Turn the join failure state into a recovery path

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Public |
| Persona(s) | First-time household member |
| Category | Public conversion |
| Severity | Medium |
| Impact | 3 |
| Effort | XS |
| Confidence | Confirmed |
| Priority score | 6.0 |
| Verdict | Fix |
| Dependencies | GRO-017 |
| Labels | join, invite, copy |

**Evidence:**
- `/join` with no token: eyebrow "You're invited", title "Join this household", lede "This invite is not available.", error "This join link is missing a token." (`frontend/src/pages/JoinPage.tsx:44`, `:163-171`; `gro_join_no_token_1440.png`).
- Bad token: the error reads "Invite not found" (`gro_join_bad_token_1440.png`).
- The only action is "Already a member? Sign in" (`:174`). There is no request-access link even though login offers one when `access_requests_enabled` (`LoginPage.tsx:359`).
- The valid-invite lede is static: "Sign in with Plex to join. Username and password is a fallback on the same link." (`:169`), regardless of whether Plex is enabled. On QA, Plex sign-in is not offered at `/login`, so the lede would likely be wrong for a valid invite (Likely; a valid invite was not created).

**Current state:** The only member acquisition step dead-ends in jargon ("token") under a celebratory eyebrow.

**Root cause:** Error copy was written from the code's point of view, and no failure-specific layout exists.

**Recommendation:** Use rewrite #7. Add a secondary "Request access" button linking to `/login?request=1` when access requests are on. Make the lede depend on `plexEnabled`: if Plex is enabled, "Sign in with Plex to join."; if only local, "Choose a username and password to join."

**Rationale:** Invite links break in SMS, email, and chat apps all the time. The failure state must recover. Rejected alternative: auto-redirecting to `/login`, which hides why it failed.

**User story:** As someone whose invite link broke, I want to know what to do next.

**Acceptance criteria:**
- [ ] No member-visible "token".
- [ ] The failure state offers Request access when enabled.
- [ ] The lede matches enabled methods.

**Success metric:** `invite_redeemed / invite_created` ≥ 85%.

**Validation:** Load `/join`, `/join?token=x`, and a valid token on QA; check copy and buttons.

### GRO-013: Fix the Docker Hub listing that points to the old repo name

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Public |
| Persona(s) | First-time visitor (installer) |
| Category | Acquisition |
| Severity | Medium |
| Impact | 3 |
| Effort | XS |
| Confidence | Confirmed |
| Priority score | 6.0 |
| Verdict | Fix |
| Dependencies | GRO-027 |
| Labels | docker-hub, acquisition, listing |

**Evidence:** Docker Hub API for `romwil/projectionist`: `description` "Cinema intelligence for your personal archive (Projectionist).", `full_description` (93 characters) "Canonical image for Projectionist (formerly CuratorX). See https://github.com/romwil/curatorx", `pull_count` 19,203, `star_count` 0, `last_updated` 2026-10-28. `README.md:5` links the badge to that Hub page as the "recommended" install (`README.md:82`).

**Current state:** The Hub page is the first thing many installers see, and it has no README, no quick start, no screenshot, and a link to the deprecated name (it redirects on GitHub today, but reads as abandoned).

**Root cause:** Hub description isn't part of the release script.

**Recommendation:** Push `README.md` (or a trimmed `docs/DOCKERHUB.md`: pitch, quick start, volumes and ports, screenshots, privacy line, links) to Hub on every `scripts/docker-release.sh`. Use `docker pushrm` or the Hub API `PATCH /v2/repositories/romwil/projectionist/` with `full_description`. Set the short description to "Chat-first curator for your Plex library — local-first, BYO LLM, Unraid-ready."

**Rationale:** It is a cheap fix on the highest-traffic acquisition surface. Rejected alternative: leaving Hub minimal, since installers judge maintenance by the listing.

**User story:** As a homelabber browsing Hub, I want to understand the image in ten seconds.

**Acceptance criteria:**
- [ ] Hub `full_description` ≥ 1,500 characters with a quick start.
- [ ] No `curatorx` URL.
- [ ] The release script updates it.

**Success metric:** GitHub referrals from `hub.docker.com` appear in repo traffic within 30 days.

**Validation:** `curl -s https://hub.docker.com/v2/repositories/romwil/projectionist/ | jq .full_description`.

### GRO-014: Attribute plays to recommendations so a north star exists

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Cross-cutting |
| Persona(s) | Owner, maintainer, returning consumer (indirectly) |
| Category | Analytics & instrumentation |
| Severity | High |
| Impact | 5 |
| Effort | M |
| Confidence | Confirmed |
| Priority score | 5.0 |
| Verdict | Fix |
| Dependencies | GRO-007; blocks GRO-025, GRO-028 |
| Labels | attribution, north-star, telemetry |

**Evidence:**
- Watch sources are Plex-only kinds (`projectionist/watch_tracker/models.py:11-21`).
- No impression, attribution, or `rec_id` identifiers exist anywhere. `git grep` for `impression` or `attribution` in `frontend/src` and `projectionist` returns only unrelated `rel="noreferrer"` hits.
- No frontend analytics.
- `playback_event` is emitted only from the Plex webhook (`projectionist/web/webhooks.py:204`) and is 0 on QA.
- Newsletter payload carries picks without an id linking back (`newsletters.py:255-263`).

**Current state:** There is no way to say whether For you, chat, inbox, newsletter, nudges, or Live led to anything being watched. Product, UX, and Performance success metrics that say "more plays" are unmeasurable.

**Root cause:** Recommendations are rendered as items, not as tracked offers.

**Recommendation:**
1. Generate `rec_id = uuid4` server-side for every surfaced item (feeds, chat cards, notification picks) and include it in the item JSON.
2. Frontend logs batched `rec_impression` (visible ≥ 1 s) and `rec_open` to `POST /api/events` (same-origin, authenticated, metadata-only, rate-limited).
3. `/watch/:ratingKey?rec=<id>` carries it; in-app Play emits `play_start` with `source=in_app`.
4. A correlator joins Plex `session_progress` within 24 hours to the latest `rec_open` for the same user and item.
5. Store in the event spine; 90-day retention.

**Rationale:** This is the only way to measure "did the curator help us pick something tonight". Rejected alternatives: inferring from `view_count` deltas (no surface, no user split) and third-party analytics (breaks the privacy promise).

**User story:** As an owner, I want to see how many nights a Projectionist pick got watched so that I know it's worth running.

**Acceptance criteria:**
- [ ] ≥ 80% of surfaced cards carry `rec_id`.
- [ ] `play_start` rows link to `rec_id` for in-app plays.
- [ ] No titles or text in event props.

**Success metric:** The "Nights with a pick" weekly value is computable on QA and Automat.

**Validation:** On QA, open a For you card, play it in-app, and query for a joined `rec_open` → `play_start`.

### GRO-015: Say "nothing leaves your server" and disclose the local interaction stream

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Cross-cutting |
| Persona(s) | Installer, privacy-minded member |
| Category | Content & trust |
| Severity | Medium |
| Impact | 3 |
| Effort | S |
| Confidence | Confirmed |
| Priority score | 3.0 |
| Verdict | Fix |
| Dependencies | GRO-018 |
| Labels | privacy-copy, telemetry, readme |

**Evidence:**
- `README.md:10` "local-first, zero-telemetry"; `README.md:204-206` "zero-telemetry by design — no phone-home analytics".
- The interaction stream is default on (`ingestion.py:77-85`) and records per-user chat, feedback, review, and playback metadata.
- `docs/PRIVACY.md` mentions only "Watch telemetry (detailed)" (`:291`); `git grep telemetry` finds nothing about `system_telemetry_stream`, `tool_invocation`, or `llm_usage` per user.

**Current state:** The claim is true about phone-home and false about collection. A careful reader of the schema will notice.

**Root cause:** Marketing phrase predates the local BI stream.

**Recommendation:** Replace with "**No telemetry leaves your server.** Projectionist keeps a small local activity log (no message text) so the owner can see costs and what's working; the owner can turn it off." Add a PRIVACY row for "Activity log (local)", listing the fields, the 90-day retention, owner-only visibility, and the toggle. Do the same in the CA overview.

**Rationale:** Precise claims survive scrutiny; absolute ones don't. Rejected alternative: deleting local telemetry, which would make GRO-014 and GRO-025 impossible.

**User story:** As a privacy-minded installer, I want the README to match what the database stores.

**Acceptance criteria:**
- [ ] README, CA XML, and PRIVACY use the same sentence.
- [ ] PRIVACY lists every local event store.

**Success metric:** No "zero-telemetry" absolute claims in repo docs.

**Validation:** `git grep -n -i "zero-telemetry"` returns 0 after the change.

### GRO-016: Add an opt-out link and a way back into the app to every lifecycle email

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Consumer |
| Persona(s) | Member with email alerts on |
| Category | Lifecycle messaging |
| Severity | Medium |
| Impact | 3 |
| Effort | S |
| Confidence | Confirmed |
| Priority score | 3.0 |
| Verdict | Fix |
| Dependencies | GRO-001 |
| Labels | email, unsubscribe, lifecycle |

**Evidence:** `send_mail(..., subject=..., body_text=body or title)` sends plain text only (`projectionist/notifications/service.py:125-131`). `git grep -i unsubscribe` and `List-Unsubscribe` in `projectionist/` return nothing. The newsletter body is a greeting, a voice line, and reason lines (`newsletters.py:197-198`), with no title links or settings link.

**Current state:** Email recipients can't opt out from the email, and can't tap through to the pick. Gmail and Yahoo bulk-sender rules expect `List-Unsubscribe` even at small volume, so this also hurts deliverability.

**Root cause:** Email treated as a mirror of the inbox row.

**Recommendation:**
- Append a footer: "Open in Projectionist: {base_url}/inbox · Change what you get: {base_url}/settings/notifications".
- Add headers `List-Unsubscribe: <{base_url}/api/notifications/unsubscribe?k={signed_kind_token}>` and `List-Unsubscribe-Post: List-Unsubscribe=One-Click`, where the signed token flips only that kind's opt-in.
- Link each pick to `/title/...?rec=<rec_id>`.

**Rationale:** Granular, one-click opt-out preserves trust and deliverability. Rejected alternative: HTML templates first, which are more work than value until the links exist.

**User story:** As a member, I want to stop the weekly email from the email itself.

**Acceptance criteria:**
- [ ] Every lifecycle email has a footer and `List-Unsubscribe`.
- [ ] One-click flips only that kind.

**Success metric:** Email-originated `rec_open` is measurable; opt-out rate < 10%.

**Validation:** Configure Mail on QA (when available), send a newsletter test, and inspect headers.

### GRO-017: Use one noun for the operator: "the owner"

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Cross-cutting |
| Persona(s) | Members, first-time visitors |
| Category | Content & microcopy |
| Severity | Medium |
| Impact | 3 |
| Effort | S |
| Confidence | Confirmed |
| Priority score | 3.0 |
| Verdict | Fix |
| Dependencies | GRO-026 |
| Labels | glossary, copy |

**Evidence:**
- On one login screen: "household admin" (`LoginPage.tsx:374`), "The owner will see it in their inbox." (`:389`), and "Ask the owner to check Configuration." (`:230`), a label that doesn't exist; the nav says Admin.
- Help: "Ask the server owner about sync and scheduled tasks." (`HelpPage.tsx:213`).
- Live: "household owner" (`frontend/src/lib/liveChannelsCopy.ts:26`).
- Counts in `frontend/src`: "the owner" 31, "household owner" 2, "household admin" 1.

**Current state:** A member can't tell whether the admin, the owner, and the server owner are one person.

**Root cause:** No glossary.

**Recommendation:** Standardize on **"the owner"** in member copy, **"Admin"** only as the nav label (owners only), and never "Configuration". Apply rewrites #5 and #6. Change Help to "Ask the owner about sync and scheduled tasks." Add the term list to the GRO-026 lint.

**Rationale:** Consistent nouns reduce support questions ("who do I ask?").

**User story:** As a member, I want to know exactly who to ask.

**Acceptance criteria:**
- [ ] 0 occurrences of "household admin", "server owner", or "Configuration" in member-visible `frontend/src` strings.

**Success metric:** Lint passes.

**Validation:** `git grep -n -i "household admin\|server owner\|check Configuration" -- frontend/src`.

### GRO-018: Give owners a view and a switch for the local activity log

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Admin |
| Persona(s) | Owner |
| Category | Analytics & instrumentation |
| Severity | Medium |
| Impact | 3 |
| Effort | M |
| Confidence | Confirmed |
| Priority score | 2.0 |
| Verdict | Fix |
| Dependencies | GRO-007, GRO-015; feeds GRO-025 |
| Labels | telemetry, admin-ui, consent |

**Evidence:** Owner APIs `GET /api/admin/telemetry/summary` (`projectionist/web/app.py:1720-1730`) and `/events` (`:1733-1742`). No frontend caller (`git grep "telemetry/summary\|telemetry/events" -- frontend/src` returns 0). `telemetry_enabled` is read from DB config (`ingestion.py:77-85`) with no setting in `config_store.py` or any UI (it appears only in tests).

**Current state:** The owner can neither see nor disable the interaction stream without SQL.

**Root cause:** Built as a maintainer tool, not an owner feature.

**Recommendation:** Add Admin → Health → **Activity** tab: event counts by type over 7, 30, and 90 days, plus a toggle "Keep a local activity log (no message text)" bound to `telemetry_enabled`, with help text linking to Privacy. Promote `telemetry_enabled` into `Settings` so it survives backup and restore.

**Rationale:** Transparency is the price of local measurement. Rejected alternative: keeping it hidden, which contradicts GRO-015.

**User story:** As an owner, I want to see and control what my server logs about my household.

**Acceptance criteria:**
- [ ] Toggle persists and stops interaction writes.
- [ ] `llm_usage` unaffected.
- [ ] Tab renders counts.

**Success metric:** Owners can answer "what's logged?" in one click.

**Validation:** Toggle off on QA, send a chat, and confirm no new stream rows; `llm_usage` still increments.

### GRO-019: Remove ops jargon from member settings

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Consumer |
| Persona(s) | Member, older/low-vision user, non-native-language user |
| Category | Content & microcopy |
| Severity | Low |
| Impact | 2 |
| Effort | XS |
| Confidence | Confirmed |
| Priority score | 2.0 |
| Verdict | Fix |
| Dependencies | GRO-026 |
| Labels | copy, settings, jargon |

**Evidence:** `NotificationsSettingsPage.tsx:279` "Email needs the owner to configure Admin → Mail (SMTP or Resend) first."; `:295` "…Optional household URLs come from the owner under Admin → Mail."; `:296` "Apprise package is not installed on this server yet — ask the owner to reinstall with web extras." (`gro_member_notifications_1440.png`).

**Current state:** Members see admin paths, protocols, and Python packaging terms.

**Root cause:** Owner-facing copy reused in member settings.

**Recommendation:** Use rewrite #9. Change `:279` to "Email isn't set up on this server yet. The owner can turn it on." and `:295` to "Send alerts to Discord, Telegram, or your phone. The owner may also add household-wide destinations." Keep the "Needs owner setup" badge, which works.

**Rationale:** Plain language is a core accessibility requirement.

**User story:** As a member, I want settings that tell me what I can do, not how the server is built.

**Acceptance criteria:**
- [ ] No "SMTP", "Resend", "extras", or "Admin →" in member-visible settings text.

**Success metric:** Lint passes.

**Validation:** Load `/settings/notifications` as `qa-member`.

### GRO-020: Make the Year in Review empty state match the self-serve button

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Consumer |
| Persona(s) | Member |
| Category | Lifecycle messaging |
| Severity | Low |
| Impact | 2 |
| Effort | XS |
| Confidence | Confirmed |
| Priority score | 2.0 |
| Verdict | Fix |
| Dependencies | — |
| Labels | year-in-review, empty-state, copy |

**Evidence:** QA `qa-member` `/year-in-review/2026` renders "Year in Review not available yet" and "Back to chat" (`gro_member_yir_1440.png`). That is the raw API detail from `projectionist/web/app.py:3081`. The intended empty state, "Your reel isn't ready yet. Opt in under Settings → Notifications, then ask the owner to generate." (`frontend/src/pages/YearInReviewPage.tsx:160-161`), isn't shown, and it contradicts the member's own "Generate & send to me" button (`NotificationsSettingsPage.tsx:406`).

**Current state:** The member gets neither the reason nor the next step.

**Root cause:** The 404 error path renders `detail` instead of the designed empty state, and the copy predates self-serve generation.

**Recommendation:** Map 404 to the designed empty state using rewrite #10, linking to `/settings/notifications#year-in-review`.

**Rationale:** Year in Review is the most shareable lifecycle moment; its empty state should convert.

**User story:** As a member, I want to know how to get my reel.

**Acceptance criteria:**
- [ ] 404 shows the designed state with a working link.
- [ ] No "ask the owner to generate".

**Success metric:** `optin_changed(kind=yir)` within 1 day of a YIR page view ≥ 30%.

**Validation:** As `qa-member` with YIR off, load the page.

### GRO-021: Fix casing where names are joined to reason sentences

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Consumer |
| Persona(s) | Member |
| Category | Content & microcopy |
| Severity | Low |
| Impact | 2 |
| Effort | XS |
| Confidence | Confirmed |
| Priority score | 2.0 |
| Verdict | Fix |
| Dependencies | GRO-005 |
| Labels | copy, inbox, polish |

**Evidence:** QA inbox: "qa-member, You watched Don't Look Up (2021); Ant-Man (2015) — adam McKay worked on both." (`gro_member_inbox_1440.png`). The join is `f"{name}, {specific}"` (`projectionist/notifications/whisper.py:96`). The lowercase "adam" comes from credit data passed through `f"{creator} worked on both"` (`recommendation_reasons.py:745`). The data-casing source is Likely TMDB/Plex credit text, not verified.

**Current state:** Small errors in the product's best sentence.

**Root cause:** String joins with no sentence-case handling, and credit names not normalized.

**Recommendation:** Lower-case the first character of `specific` when prefixing a name (`"{name}, you watched…"`), and title-case credit names only when they are all lowercase (do not touch "McKay"-style names).

**Rationale:** The sentence carries trust; typos erode it.

**User story:** As a member, I want the curator's notes to read like a person wrote them.

**Acceptance criteria:**
- [ ] Unit test: prefix join yields a lowercase "you".
- [ ] A lowercase credit is normalized.

**Success metric:** —

**Validation:** Inspect the next whisper on QA.

### GRO-022: Clean the guest Help header and table of contents

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Public |
| Persona(s) | First-time household member |
| Category | Content & help |
| Severity | Low |
| Impact | 2 |
| Effort | XS |
| Confidence | Confirmed |
| Priority score | 2.0 |
| Verdict | Fix |
| Dependencies | GRO-004 |
| Labels | help, toc, copy |

**Evidence:**
- QA guest `/help` TOC: "Start · Chat · Related titles · Plot knowledge · **Related titles** · About · Privacy · Knowledge guide". "Related titles" appears twice.
- The intro shows "Deep dive: PRODUCT.md · CURATOR_KNOWLEDGE.md" (`docs/HELP.md:7`) to guests and members.
- The header reads "Viewing as Guest", although guest is not a household role.
- "← Back to chat" appears for guests (`HelpPage.tsx:205`, `:210-213`; `gro_help_guest_1440.png`).

**Current state:** The first public page shows a duplicate, repo filenames, and a back link to a place guests can't go.

**Root cause:** The TOC is built from headings without dedupe, and the intro links target contributors.

**Recommendation:**
- Dedupe TOC entries by label.
- Move the "Deep dive" line below `## For owners`, or relabel it "Product guide · Curator knowledge guide (GitHub)".
- For guests, show "Not signed in", and use "← Sign in" as the back action.

**Rationale:** The page is otherwise the product's best public asset (GRO-004).

**User story:** As a guest, I want Help to look finished.

**Acceptance criteria:**
- [ ] No duplicate TOC labels.
- [ ] No `.md` link text above "For owners".
- [ ] The guest back link goes to `/login`.

**Success metric:** —

**Validation:** Load `/help` signed out.

### GRO-023: Make About a trust page, not a changelog dump

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Public |
| Persona(s) | First-time visitor, low-bandwidth mobile user |
| Category | Public conversion |
| Severity | Low |
| Impact | 2 |
| Effort | S |
| Confidence | Confirmed |
| Priority score | 1.0 |
| Verdict | Rethink |
| Dependencies | GRO-010 |
| Labels | about, copy, performance |

**Evidence:**
- `frontend/src/pages/AboutPage.tsx:96-97`: "Owners configure the stack once. Household members sign in with Plex. Nobody has to pretend this is a SaaS marketing site." QA `/login` offers local sign-in only, so "sign in with Plex" is false there.
- The guest sees "← Back to chat" (`:77`).
- Release notes are the "Full history from CHANGELOG — newest first." (`:119`). On QA the guest About page has **7,048 DOM elements** and a jump list of roughly 250 versions (`gro_about_guest_1440.png`).

**Current state:** The story paragraph is good, but the page ends in an archive, an inside joke, and a factual error on some installs.

**Root cause:** About is doing double duty as the release-notes browser.

**Recommendation:** Use rewrite #8. Show the latest 5 releases' Highlights, then a "Full release history on GitHub" link. Show the guest back link as "← Sign in". Keep the License and Links sections as they are.

**Rationale:** About is where a skeptical new member decides whether this is trustworthy.

**User story:** As a newly invited member, I want About to tell me what this is and who runs it.

**Acceptance criteria:**
- [ ] ≤ 1,500 DOM elements for guest About.
- [ ] No "Plex" claim when Plex sign-in is disabled.

**Success metric:** —

**Validation:** Count `document.querySelectorAll('*').length` on QA `/about`.

### GRO-024: Give each route its own document title

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Cross-cutting |
| Persona(s) | Every user, screen-reader user |
| Category | SEO & wayfinding |
| Severity | Low |
| Impact | 2 |
| Effort | S |
| Confidence | Confirmed |
| Priority score | 1.0 |
| Verdict | Fix |
| Dependencies | GRO-010 |
| Labels | title, history, a11y |

**Evidence:** `frontend/index.html` `<title>Projectionist</title>`. No `document.title` assignment in `frontend/src` (`git grep` finds only a test fixture). On QA the titles of `/help`, `/privacy`, and `/chat` all read "Projectionist" (walk capture).

**Current state:** Browser history, tabs, bookmarks, and screen-reader page announcements can't tell pages apart.

**Root cause:** No title hook.

**Recommendation:** Add `useDocumentTitle(label)` used by `AppShell` and `GlassDoor`, with the format `"{Page} · {household name or Projectionist}"`, e.g. "Sign in · Projectionist", "Inbox (14) · Projectionist".

**Rationale:** Cheap wayfinding and WCAG 2.4.2. Not about SEO, since the pages are noindex (GRO-010).

**User story:** As a member with several tabs open, I want to tell them apart.

**Acceptance criteria:**
- [ ] Every top-level route sets a unique title.

**Success metric:** —

**Validation:** Navigate QA routes and read `document.title`.

---

## 15. Opportunities

### GRO-025: Add an owner Household Pulse view built on the local event spine

| Field | Value |
|---|---|
| Type | Opportunity |
| Surface | Owner |
| Persona(s) | Owner, established owner at scale |
| Category | Analytics & instrumentation |
| Severity | Medium |
| Impact | 5 |
| Effort | M |
| Confidence | Confirmed |
| Priority score | 3.33 |
| Verdict | Add |
| Dependencies | GRO-007, GRO-014, GRO-018 |
| Labels | dashboard, north-star, owner |

**Evidence:** The owner has cost (Health → Usage), library state (Overview: Indexed / Unwatched / Rated), and quality loops (Library knowledge), but no outcome view. The data to compute outcomes partly exists: `user_notifications.read_at` (`_notifications.py:293`), `watch_events`, `chat_messages`, `user_title_reviews`.

**Current state:** The owner runs the house blind on whether anyone uses what Projectionist sends or suggests.

**Root cause:** Measurement stopped at cost and quality.

**Recommendation:** Add Admin → Health → **Pulse** with five tiles (last 4 weeks versus the prior 4):
1. Nights with a pick per active member.
2. Invite → active in week 2.
3. Lifecycle read rate and read-to-play by kind.
4. Chat turns with cards / total.
5. Youth-gate blocks (should be shown, and should be 0 violations).

Each tile links to the page that fixes it, like the Monday-pass hero. There is no export and no comparison across households.

**Rationale:** It turns measurement into the owner's weekly ritual (sacred cow #17).

**User story:** As an owner, I want one screen that tells me whether the house is getting value.

**Acceptance criteria:**
- [ ] Five tiles render from local data.
- [ ] Empty states explain what's missing.
- [ ] No per-message content shown.

**Success metric:** The owner opens Pulse ≥ 3 of 4 weeks.

**Validation:** QA owner walk after GRO-007 and GRO-014 ship.

### GRO-026: Adopt a microcopy glossary and lint member-visible strings

| Field | Value |
|---|---|
| Type | Opportunity |
| Surface | Cross-cutting |
| Persona(s) | All members; contributors |
| Category | Content & microcopy |
| Severity | Medium |
| Impact | 3 |
| Effort | S |
| Confidence | Confirmed |
| Priority score | 3.0 |
| Verdict | Add |
| Dependencies | Enables GRO-006, GRO-009, GRO-017, GRO-019 |
| Labels | glossary, lint, voice |

**Evidence:** `docs/DOCS_STYLE.md` governs docs and states the member/owner split, but there is no UI string glossary or check. Leaks found in this review: `curator.py:414`, `_schema.py:1600`, `LoginPage.tsx:230`, `:374`, `NotificationsSettingsPage.tsx:279`, `:296`, `app.py:3081` (raw detail).

**Current state:** Every new feature can reintroduce jargon.

**Root cause:** The voice rule has no enforcement.

**Recommendation:**
- Add a "UI voice & glossary" section to `docs/DOCS_STYLE.md` (the voice guide above plus a ten-term glossary).
- Add `scripts/lint-copy.mjs`, run in `npm run lint`. It scans JSX text and string literals in `frontend/src/pages`, `frontend/src/components` (excluding `admin/`) and the agent fallback strings for banned terms: `/\b(LLM|provider|SMTP|Resend|extras|token|Configuration|household admin|server owner|\(migrated\))\b/` with an allowlist file.
- Never render API `detail` directly; route it through `formatApiError` with surface-specific maps.

**Rationale:** It fixes the root cause, not the instances.

**User story:** As a contributor, I want the linter to tell me when member copy leaks owner jargon.

**Acceptance criteria:**
- [ ] Lint runs in CI.
- [ ] Current violations are fixed or allowlisted with an owner-only reason.

**Success metric:** 0 new violations per release.

**Validation:** CI lint job output.

### GRO-027: Treat GitHub, Hub, and Unraid CA as the marketing site, and measure them honestly

| Field | Value |
|---|---|
| Type | Opportunity |
| Surface | Public |
| Persona(s) | First-time visitor (installer) |
| Category | Acquisition |
| Severity | Medium |
| Impact | 3 |
| Effort | S |
| Confidence | Confirmed |
| Priority score | 3.0 |
| Verdict | Add |
| Dependencies | GRO-013, GRO-015 |
| Labels | acquisition, unraid-ca, github |

**Evidence:**
- GitHub (`gh api`, read-only): 1 star, 0 forks, 9 open issues, Discussions disabled. 14-day views 6 / 6 uniques; referrers aocr.org (2), Google (1), github.com (1). Clones 2,459 / 350 uniques (CI and automation dominated).
- CA overview (`unraid/projectionist.xml:14`) spends half its length on Force Update troubleshooting and paths, and has no `<Screenshot>` entries. `templates/projectionist.xml` duplicates `unraid/projectionist.xml` (identical at `94fcd3f`).
- README has no screenshot.
- The README Quick start says the wizard is "Name → Connections → Libraries" (`README.md:92`).

**Current state:** The real storefronts are text-only and ops-first. The only numbers (pulls, clones) are inflated by the maintainer's own pipelines.

**Root cause:** Distribution is treated as packaging, not acquisition.

**Recommendation:**
- CA overview: lead with two sentences of value ("Ask for tonight's movie in plain language — answered from your own Plex library. Family-safe youth mode, Live channels, BYO AI."). Move troubleshooting to the wiki link. Add 3–4 `<Screenshot>` URLs (chat, Explore For you, Live guide, Year in Review).
- README: add a hero screenshot and a 30-second GIF.
- Turn on GitHub Discussions (Q&A plus Show-and-tell) as the community and support channel.
- Keep one CA template file.
- Track monthly: GitHub uniques, stars, Discussions posts, and Hub pulls minus known maintainer pulls (log rollout pulls in `scripts/unraid-rollout.sh` to subtract).

**Rationale:** You can't grow what you can't see, and these surfaces cost nothing to improve.

**User story:** As an Unraid user browsing CA, I want to see what this looks like before I install.

**Acceptance criteria:**
- [ ] CA XML has ≥ 3 screenshots and a value-first overview.
- [ ] README has a hero image.
- [ ] Discussions enabled.

**Success metric:** GitHub 14-day uniques ≥ 50 within 90 days.

**Validation:** `gh api repos/romwil/projectionist/traffic/views`; CA template diff.

### GRO-028: Use release-over-release and persona comparison instead of A/B tests

| Field | Value |
|---|---|
| Type | Opportunity |
| Surface | Cross-cutting |
| Persona(s) | Maintainer, owner |
| Category | Experimentation readiness |
| Severity | Medium |
| Impact | 3 |
| Effort | M |
| Confidence | Likely |
| Priority score | 1.6 |
| Verdict | Add |
| Dependencies | GRO-007, GRO-014, GRO-025 |
| Labels | experimentation, flags, releases |

**Evidence:**
- `FeatureFlags` holds static owner booleans (`projectionist/config_store.py:486-511`), with no per-user bucketing or exposure logging. `git grep` for experiment or variant code returns nothing relevant.
- Persona templates already act as natural variants, with `persona_id` recorded on `llm_usage` and `chat_message` (`_schema.py:1649`, `ingestion.py:137`).
- A household has 2–6 accounts (QA newsletter panel: 5 members, per Batch 1).

**Current state:** No way to know whether a release made things better, and no persona comparison.

**Root cause:** No outcome metrics (GRO-014), so nothing to compare.

**Recommendation:**
1. Store `app_version` on every event. Pulse shows "since 1.38.0 vs the 4 weeks before".
2. Add a "Labs" section in Admin → Advanced for owner-opt-in features (`labs.<name>: bool`) and log `labs_exposure` events.
3. Add a persona comparison table: chat turns with cards, `rec_open`, and thumbs-up rate by `persona_id`.
4. Use the maintainer's Automat household as the dogfood cohort before Hub publish.

No randomization, no remote flags.

**Rationale:** It gives the evidence that A/B testing gives SaaS, sized for a house. Rejected alternatives: a hosted flag vendor (breaks local-first) and per-user randomization (N too small).

**User story:** As the maintainer, I want to know whether a release improved nights with a pick on my own household before shipping it wider.

**Acceptance criteria:**
- [ ] Events carry `app_version`.
- [ ] Pulse shows a release delta.
- [ ] Labs toggles log exposure.

**Success metric:** Each minor release notes a Pulse delta in its CHANGELOG Highlights.

**Validation:** Upgrade QA between two tags and compare Pulse.

---

## 16. Remediation plan

### Now (0–2 weeks)

| ID | Title | Effort | Owner role | Dependencies |
|---|---|---|---|---|
| GRO-008 | Apply the youth rating gate to newsletters and nudges | S | Backend engineer | — |
| GRO-006 | Stop telling members to configure an LLM provider | XS | Backend + content | — |
| GRO-009 | One speaking name; no storage names | S | Full-stack + content | — |
| GRO-011 | Skip empty newsletters | XS | Backend | GRO-008 |
| GRO-012 | Join failure recovery copy | XS | Frontend + content | — |
| GRO-010 | noindex + robots.txt | XS | Backend | — |
| GRO-013 | Fix Docker Hub listing | XS | Maintainer | — |
| GRO-017 | One noun: "the owner" | S | Content | — |
| GRO-020 | Year in Review empty state | XS | Frontend | — |
| GRO-021 | Name/sentence casing | XS | Backend | — |
| GRO-022 | Guest Help header/TOC | XS | Frontend | — |

### Next (2–6 weeks)

| ID | Title | Effort | Owner role | Dependencies |
|---|---|---|---|---|
| GRO-007 | `chat_turn` from the agent | S | Backend | — |
| GRO-014 | `rec_id` attribution + `play_start` | M | Full-stack | GRO-007 |
| GRO-016 | Email footer + List-Unsubscribe | S | Backend | — |
| GRO-015 | "Nothing leaves your server" + Privacy row | S | Content + maintainer | GRO-018 |
| GRO-018 | Activity tab + toggle | M | Full-stack | GRO-007 |
| GRO-026 | Glossary + copy lint | S | Frontend + content | — |
| GRO-019 | Settings jargon | XS | Content | GRO-026 |
| GRO-027 | CA / README / Discussions | S | Maintainer | GRO-013 |

### Later (6+ weeks)

| ID | Title | Effort | Owner role | Dependencies |
|---|---|---|---|---|
| GRO-025 | Household Pulse | M | Full-stack + design | GRO-007, GRO-014, GRO-018 |
| GRO-028 | Release deltas, Labs, persona comparison | M | Full-stack | GRO-025 |
| GRO-023 | About as trust page | S | Frontend + content | GRO-010 |
| GRO-024 | Per-route titles | S | Frontend | — |

**Sequencing rationale:** member-visible harm and embarrassment first: youth safety, then the copy every member sees on every turn. Instrumentation comes next because it is the dependency for every success metric in this run. Dashboards and experiments come last because they need weeks of clean data to say anything.

## 17. Quick wins (high impact, XS–S)

- **GRO-006**: one-line change to the fallback; removes the most-seen bad string.
- **GRO-008**: reuse the existing `_youth_row_allowed`; closes the worst lifecycle risk.
- **GRO-009** (resolver + `display_name`): removes "(migrated)" and "CURATOR" mismatches.
- **GRO-011**: a single `continue`; stops empty newsletters.
- **GRO-010**: one meta tag, one header, one route.
- **GRO-013**: paste the README into Hub.
- **GRO-007**: one emit call in the agent; unlocks measurement for every department.

## 18. Open questions needing product/business input

1. **Is "nights with a pick" the north star you want?** The alternative is "weekly active members". The proposed one rewards the curator's actual job, while the alternative is easier to compute today.
2. **Should youth accounts receive newsletters and nudges at all** (with the gate), or be excluded like whisper?
3. **Which persona speaks in household-wide letters**: the member's chosen persona, or the house default? This review recommends the member's choice.
4. **Should the local activity log stay default on** once it is disclosed and toggleable (recommended), or default off and be enabled during setup?
5. **Is GitHub Discussions acceptable as the community channel**, given the maintainer's support load?
6. **Should public-profile households hide the version from guests** (recommended), given that the CA overview and `/api/health` also expose it? This needs coordination with Security.
7. **Does the maintainer want an opt-in, off-by-default anonymous "I installed this" ping** for acquisition measurement? This review recommends **no** for now (sacred cow #5). Revisit only if off-site signals prove useless after the GRO-027 cleanup.
