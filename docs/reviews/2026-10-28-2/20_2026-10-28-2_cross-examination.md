# 20 · Cross-examination — run 2026-10-28-2

**Phase:** 3 (Batch 6, first synthesis document). **Run:** `2026-10-28-2` (from `docs/reviews/ACTIVE_RUN`).
**Inputs read:** `_status.md`, `00_2026-10-28-2_platform-map.md`, and Part A plus the finding index (ID, title, type, severity, score, verdict) for all ten department documents, with the full Recommendation text pulled for each finding cited as a conflict below. The red-team document (`21_*`) was not read; it does not exist yet, and Phase 4 is independent by design.
**Department coverage:** all ten documents (`01`–`10`) exist and are substantive (814–2,558 lines each). This was not run with `force`, and no department is missing.
**Commit:** every batch in `_status.md` records `94fcd3f`, so the batches reviewed the same code. The laptop checkout has moved on since then (it is now at `c7fb5ee`), but no department cited it. Nothing in this document was re-verified against the newer checkout.
**No department document was edited.** Disagreements are recorded here for Phase 4 and Phase 5 to resolve.

---

## How to read this

Each department reads the other nine and answers four questions:

- **Conflicts:** a recommendation from another team that would hurt this domain, and a proposed resolution.
- **Reinforcements:** findings elsewhere that share a root cause with this domain's findings.
- **Blind spots:** something another team missed or underweighted.
- **Re-ranking:** priorities this department would change, and why.

The closing sections collect the cross-department conflicts, the shared root causes, and the duplicate tickets that the backlog in Phase 5 should merge.

---

## 1. Product (PRD)

### Conflicts

1. **PRIV-012 + PRIV-008 (chat retention defaults: 12 months for adults, 90 days for youth) vs. the "tonight" continuity loop.** Product has no objection to deleting history. The harm is that a silent purge breaks "continue that conversation" and empties the thread list that members return to (PRD-006, UX-030). **Resolution:** keep the defaults. Show the retention window in the thread list ("Kept for 12 months · change"), and never purge a thread that has a pinned or saved reply (`Saved curator responses`) without a notice in the Inbox.
2. **SEC-007 (owner step-up password for "crown jewel" routes in single-owner mode) vs. the zero-friction single-owner install** that Product kept as a sacred cow (PRD Foundations: "Multi-user opt-in: Keep"). **Resolution:** accept SEC-007 as written. It covers only reveal, backup, settings write, MCP keys, user admin, and the multi-user toggle, uses a 15-minute step-up, and leaves browsing login-free. Product's Keep verdict also rested on a false premise: SEC confirms that the setup wizard already forces `multi_user = True` (`setup_mode.py:276`). The single-owner default is legacy behaviour, not the current install path.
3. **GRO-025 (Household Pulse: "nights with a pick per active member") vs. two-sided fairness.** In a household of 2–6 people, a per-member tile shows the owner each person's viewing habits. That repeats the owner-overreach pattern that PRIV-002 and PRIV-003 criticize. **Resolution:** the owner sees household totals and the active-member count. Each member sees their own numbers in My Journey (or in PRIV-024's "What Projectionist knows about me"). No per-member breakdown goes to the owner unless the member opts in.
4. **UX-014 (bottom tab bar with five fixed peers) and UX-019 (promote Library to a primary peer) vs. PRD-005 and PRD-013 (park modules, shrink the map).** These agree on direction but differ on what goes in the bar. **Resolution:** treat UX's tab set (Explore · Ask · Search · Library · Inbox) as Product's activation map too. Live joins only when ready. My Journey drops out of primary navigation, which both teams want.

### Reinforcements

- **Activation (first Play) is one root cause across five teams.** These findings are one epic, with "first Play in under 60 seconds without an LLM" as the metric: PRD-006, PRD-008, PRD-016, UX-010, UX-031, UX-009, UX-011, GRO-006, A11Y-020, and OPS-023.
- **Ratings are uncollected for one reason: there is no moment to rate.** PRD-007, UX-012, UX-043, UX-038, VIS-028 (end card frame), A11Y-023 (the end-card OSD is `aria-hidden` when idle), and GRO-014 (no attribution) all describe the same failed loop at the end of a film.
- **The Youth "contract" is the most-cited root cause in the run.** See PRD-011, UX-044, GRO-008, SEC-002, SEC-009, SEC-018, PRIV-007, PRIV-008, and ARCH-015. Product's ruling ("labeling without enforcement is theater") is confirmed by six other teams' evidence.
- **The About changelog appears in five documents:** PRD-009, UX-020, A11Y-015, GRO-023, and PERF-014.

### Blind spots in other teams

- **Everyone treats posters as cosmetic, but they are the product.** VIS-027 found 234 letter tiles and zero poster requests on the owner's Explore. Product's own "best minute" (PRD-001, the For you kinship rail) was judged with no art, and so was the UX journey grade. A "tonight" picker without key art loses to Plex's own home screen. VIS-027 is an activation bug, not a style bug.
- **Local-password members have no Plex identity, and several recommendations quietly assume one.** SEC-010 and PRIV-006 scope Continue Watching to the viewer's own `watch_sessions`, and UX-038 seeds taste from "the member's Plex watch history." On QA, every member is local-password only. Once the scoping is done correctly, those members get an empty Continue Watching, an empty seed set, and no attribution (GRO-014 relies on Plex `session_progress`). Someone has to decide: either ask members to link Plex at join (PRD-012 foyer), or make in-app Play the canonical watch signal for local accounts. That decision belongs in `31`.
- **No team priced chat tools as a product liability.** SEC-002 shows that with an LLM connected, a member or Youth account can mark files bad, approve Seerr requests, and self-confirm `remove_from_arr`. Product's feature inventory counts chat tools as value only. Until SEC-002 lands, turning on the LLM, which Product's activation plan encourages, raises household risk.

### Re-ranking

- **Raise PRD-008 from Medium to Critical so it matches UX-010.** It is the same defect, and UX's evidence (`curator.py:385-414` sends "recommend" to `find_collection_gaps`, answering with titles the household does not own) is stronger than Product's.
- **Lower PRD-005 (collapse Experience modules) below SEC-002 and PERF-008.** Parking Live costs owners little if they cannot see it, and the backend stall (PERF-008) hurts every member nightly.
- **Raise VIS-027 into Product's Now list** for the reason given in Blind spots.

---

## 2. UX (UX)

### Conflicts

1. **SEC-007 step-up and SEC-011 (password change, reset, sign out everywhere) add steps to owner flows that UX is trying to shorten (UX-016, UX-036).** **Resolution:** step-up appears only inside the six crown-jewel actions, once per 15 minutes, as an inline password field in the same panel with no redirect to `/login`. Sign-out-everywhere sits in Settings → Profile, not in the account menu.
2. **PRIV-012 retention, PRIV-016, and SEC-015 (clear the client thread id on sign-out) vs. UX-008 (stale-while-revalidate session cache) and the "keep the user's place" theme.** **Resolution:** UX agrees for shared devices. The cache has to be keyed by user id so a sign-out never shows the previous person (UX-039), and clearing it must not wipe the theme or text-size preferences, which are device-level.
3. **PRD-005 (hide Live, Lobby, and Holidays until ready) vs. UX-017 (owner `/live` Off should say "Turn on Live Channels").** Hiding the module from owners removes the only path to turning it on. **Resolution:** hide Off modules from members and youth. Owners see them as locked rows on one Experience page with a "Turn on" CTA, which PRD-005 already allows. UX-017's member copy becomes moot because members never see `/live` while it is Off.
4. **A11Y-001 (never disable the focused composer while a reply streams) vs. UX's double-send concern.** No team flagged this, but it is a conflict. **Resolution:** use `aria-disabled` and a guarded submit handler that ignores a second send while streaming, as A11Y specifies. Show the Stop control in the same position.
5. **VIS-006 (root font size 15px → 16px at Medium) vs. UX layout density on phone rails** (UX-014, rail peek tokens VIS-034). A 6.7% rem shift changes how many posters peek on a 390px screen. **Resolution:** ship only behind VIS-043's visual diffs at 390px and 1440px, and keep `--rail-peek` in px.

### Reinforcements

- **"Optional integrations behave as required."** UX-009, UX-010, UX-013, UX-016, and UX-025 share one root cause with OPS-011 ("Connected ✓" while secrets cannot decrypt), OPS-023, GRO-006, and PRD-008. The UX doesn't model integration state, so it either blocks (wizard) or lies (badge).
- **Explore warming of up to 36 seconds (UX-021) is mostly a backend problem.** PERF-008 shows the synchronous Movies query blocking the shared event loop. PERF-019 measures uncached Plex on-deck at 0.75–1.6 s per view. PERF-017 adds about 55 ms of settings reload to every authenticated call. UX-021's Retry button is correct, but the 36 seconds will not shrink until PERF-008 and PERF-019 ship.
- **Deep links that land on JSON (ARCH-010)** are the server half of UX-011. Fix both together, or `next=/whisper` will land on `{"detail":"Not Found"}`.
- **Naming drift:** UX-015, GRO-009, GRO-017, A11Y-014, OPS-013, and UX-028 come from one root cause, the absence of a glossary (GRO-026).

### Blind spots in other teams

- **The `next=` redirect needs a security owner.** UX-011 already restricts `next` to same-origin relative paths that don't start with `//`. SEC did not review it. Add backslash and encoded-slash variants (`/\evil`, `%2F%2F`) to SEC-017's matrix test.
- **ARCH and PERF do not mention Suspense fallbacks.** ARCH-012 and PERF-011 add route-level code splitting. Every lazy route needs a fallback, and with nothing specified it will be another blank "Loading…" (VIS-011 counts five loading idioms already). The fallback should be VIS-011's skeleton and should fire A11Y-004's route announcement after the chunk resolves.
- **UX-038's own taste seeding collides with PRIV-006.** UX proposed seeding with "8 posters from the member's Plex watch history." For members on the server account, or with no Plex link, that history belongs to someone else. **Correction to UX-038:** seed only from the member's own `watch_sessions` or in-app Play. If there are none, fall back to "popular in the library," which UX-038 already names. Never seed from server-account history.

### Re-ranking

- **Lower UX-039 (sign-out shell shows the previous member) from High/7.50 to Medium, but keep it in Now.** SEC-015 and PRIV-016 rate the same bug Low because the server session does end and the leftover Admin link is client-only. UX observed a real shared-device exposure (header, toolbar, thread list), so Medium is honest. The fix is XS.
- **Raise UX-044 (gate Continue Watching like Play) to the top of UX's Now list.** Five teams found it independently (UX-044, SEC-010, PRIV-007, ARCH-015, GRO-008), and it is the most likely screenshot in a household trust incident.
- **Move UX-034 (household request queue when Seerr is off) to Later, behind SEC-002 and SEC-017.** A new member-to-*arr request path before the policy kernel exists would be a third unguarded path (ARCH-022 already counts three).

---

## 3. Visual design (VIS)

### Conflicts

1. **VIS-001 vs. A11Y-002 propose different hex values for the same Lights Up `--accent-ink` token.** VIS-001 specifies `#735c00` (5.56–6.44:1, already the Lights Up `--accent-2`). A11Y-002 specifies `#866200` (5.22:1 on bg, **4.82:1 on `--surface-2`**). **Resolution: adopt `#735c00`.** It introduces no new hue, and its margin over 4.5:1 on `--surface-2` survives hover tints and `color-mix()` blending. `#866200` has only 0.32 of headroom on `--surface-2`. Both teams agree on the fill/ink split, the `--focus-ring` alias, and keeping `#b8860b` for fills. Phase 5 should file one ticket with both IDs.
2. **VIS-006 vs. A11Y-017 disagree on how the type scale scales.** VIS-006 sets a 16px Medium root with Small at 15px and Large at 18px. A11Y-017 sets percentages of the user's browser default: 93.75%, 100%, 118.75%, and a new 137.5% X-large. **Resolution:** use A11Y's percentages, which render exactly as VIS's 15px and 16px at the default browser size. Take Large at 118.75% (19px) because the low-vision persona needs the bigger step. Keep VIS's floor as `max(12px, 0.75rem)` so Small never drops below 12px. Add X-large. VIS-043's visual diffs must cover all four sizes.
3. **PERF-016 (replace the Material Symbols font with inline SVGs of about 60 icons) vs. VIS-036 (the locked Material Symbols table in `docs/DESIGN.md` is strong governance).** **Resolution:** keep the governance and change the delivery. Generate an SVG sprite from the locked table at build time, so `DESIGN.md` stays the single list and the 316 KB font goes away. This also resolves A11Y's offline-ligature risk, where "play_circle" renders as visible text, and PRIV-009's request to Google.
4. **UX-014 (fixed bottom tab bar at ≤900px) adds a fourth chrome while VIS-025 asks to unify three header chromes.** **Resolution:** design the tab bar in the same primitives pass (`01a-primitives.css`) as the header, sharing tokens for height, blur, and border, instead of building it as a feature sheet. Sequence it after VIS-003, not before.
5. **ARCH-004 (CSS tokens are "well kept": only 7 raw hex values outside `01-tokens.css`) vs. VIS's foundations table (190 hex literals, 76 distinct; 11 phantom properties).** Both cannot be true as stated. The likely explanation is that ARCH counted `#rrggbb` outside the token file excluding `var(--x, #literal)` fallbacks, while VIS counted everything. **Resolution:** Phase 4 should check the counts. Until then, treat VIS's inventory as authoritative for migration planning, because it names files (`10-explore-delight.css`: 62 literals) and the fallbacks it flags (`#c4a35a` ×20) are real paint risks.

### Reinforcements

- **Self-hosting fonts is a single fix that four teams want for four reasons:** brand, cited as VIS-014; privacy, cited as PRIV-009; performance, cited as PERF-016 (render-blocking third-party CSS); and accessibility (offline icon ligatures). This is the cheapest multi-department win in the run.
- **The poster gap (VIS-027) shapes several departments' evidence.** PERF's Explore LCP of 860 ms was measured with no images. A11Y's poster-card naming (A11Y-102 strength) was judged on monogram tiles. PRD-001's "best minute" had no art.
- **Lights Up is under-tested.** VIS-015, A11Y-002, A11Y-003, and A11Y-005 all note that `ui-testing-architecture.mdc` scopes axe to Lights Down, the theme that already passes.

### Blind spots in other teams

- **PERF has not accounted for the cost of fixing posters.** When VIS-027 lands, Explore will request about 234 poster images through the same-origin poster proxy. The `async`/sync boundary (PERF-008), gzip (PERF-007, which correctly leaves images alone), and `Cache-Control` must cover the poster proxy route too, or Explore LCP goes from 860 ms to several seconds. Add the proxy to PERF-007's immutable-caching rule (posters are content-addressed by `rating_key` plus `thumb`), and give PERF-020 a poster-heavy Explore budget.
- **PRIV-009's "zero third-party requests on `/chat` cold load" metric must stay true after VIS-027.** That requires posters from the same-origin proxy, not `image.tmdb.org`. VIS-027 already specifies same-origin, which is correct. Lock it in as an acceptance criterion so a future shortcut doesn't point posters straight at the TMDB CDN.
- **ARCH-012's route splitting will move CSS.** Vite splits CSS per lazy chunk. Global sheets that rely on cascade order (`02-nav-chrome.css` → `16-live-studio.css`) can reorder when chunks load late. Keep `01-tokens.css`, the planned `01a-primitives.css`, and nav chrome in the entry chunk.

### Re-ranking

- **VIS-002 (style local sign-in fields) has the highest score in the run (15.00), but it only affects installs that use local-password login.** Plex-PIN installs never see that form. Keep it in Now, since it is XS, and bundle it with PRD-004 (value prop on the same screen) and UX-028 (copy) as one login-door ticket.
- **Raise VIS-043 (both-theme visual regression) from Opportunity to Now, ahead of VIS-006 and VIS-003.** Both of those are flagged as risky in VIS's own Risks section, and ARCH-007 shows CI is not currently a gate at all.
- **Downgrade VIS-016, VIS-019, VIS-023, and VIS-026 to Later.** They are low-value polish while the default theme fails contrast (VIS-001).

---

## 4. Accessibility (A11Y)

### Conflicts

1. **UX-010 and PRD-006 move the default landing from Chat to Explore, which shifts which surface has to be accessible first.** Explore has invisible icon focus (A11Y-003) and 4–5 tab stops per poster with no bypass (A11Y-010, A11Y-204). **Resolution:** if Explore becomes home, A11Y-003, A11Y-010, and A11Y-204 move into the same release as the landing change. Chat's A11Y-001 and A11Y-008 stay Now anyway, because chat remains a first-class peer.
2. **UX-012 (5-star rating row on the Play end card) vs. A11Y-023 (the OSD becomes `aria-hidden` when idle) and WCAG 2.2.1 timing.** **Resolution:** the end card is a separate landmark that is not `aria-hidden` and does not auto-dismiss. Focus moves to the "How was *Title*?" group when the card appears. Stars are a `radiogroup` with arrow keys. Escape leaves (UX-042).
3. **PRIV-008's `YouthPolicy` object and SEC-018's consolidated Youth enforcement could absorb accessibility preferences.** Today SDH captions are keyed on `is_youth` (A11Y-018). **Resolution:** the policy object covers content and data (rating ceiling, channels, retention, LLM route). Accessibility preferences (`captions_prefer_sdh`, caption size, reduce motion) are a separate per-user preference set (A11Y-201), and youth only changes their *defaults*. Write this boundary into the `YouthPolicy` docstring.
4. **PERF-014, UX-020, GRO-023, and PRD-009 propose different About lengths.** UX and GRO say the last 5 releases, PERF says 10, and PRD says latest plus a link. **Resolution:** render 5 Highlights blocks in the DOM, then "Show older releases" fetches the next page into a region that moves focus to its first heading. The version combobox goes away. Fetch `/release-notes.json?limit=5` so What's New stays under UX's 20 KB target.
5. **ARCH-012 and PERF-011 (lazy routes)** can leave focus on `<body>` during chunk load. **Resolution:** A11Y-004's route announcer runs after the lazy component mounts, not on `history.push`.

### Reinforcements

- **A gate that does not block can't protect anything.** A11Y-005 (add jsx-a11y and axe) sits on top of ARCH-007 and PERF-010 (CI red for days, no required checks). An axe gate added today would be red-and-ignored like the rest. ARCH-007 has to come first, then A11Y-005.
- **The dialog primitive (A11Y-202) and VIS's primitives sheet (VIS-003, VIS-021) are the same project** with a markup half and a style half. ARCH-026 (component tests) supplies the harness.
- **Owner-only remedies shown to members:** A11Y-020, GRO-006, UX-010, UX-017, and OPS-023 are one copy rule.
- **Per-route titles:** A11Y-004 and GRO-024 are the same ticket.

### Blind spots in other teams

- **Low bandwidth is an accessibility issue too, and A11Y's own persona set includes the low-bandwidth mobile user.** PERF-007 measured a 12.6 s first paint on slow 4G. No accessibility finding covers time-to-usable for that persona or for older devices. PERF-007 and PERF-011 should be tagged `a11y` in the backlog.
- **OPS's Members and Access tables (OPS-014, OPS-015) and UX-027's consolidated People desk** are dense data tables with bulk actions. A11Y-026 (reflow at 320px) covers only their layout. Bulk select needs `aria-selected` and a live count, and the destructive row actions OPS-015 wants hardened need the A11Y-101 confirm contract.
- **GRO-016 (one-click unsubscribe link in emails)** produces a landing page outside the SPA chrome. It needs a `<title>`, `<main>`, and a plain-language confirmation, which nobody specified.

### Re-ranking

- **Raise A11Y-001 + A11Y-008 + A11Y-016 to one Now ticket** ("chat send loop is usable with a screen reader"). Splitting them yields three half-fixes.
- **Raise A11Y-003 (focus visibility) to Now alongside the landing change** (Conflict 1).
- **Lower A11Y-025 (forced colours) and A11Y-022 (sub-24px targets) to Later.** They are real, but no persona in the platform map depends on them more than on chat announcements.

---

## 5. Growth, content & analytics (GRO)

### Conflicts

1. **PRIV-001 and PRIV-012 (a per-user data registry, retention, erasure) vs. GRO-007, GRO-014, and GRO-025 (a new event spine with `user_id`, `rec_id`, `play_start`, 90-day retention).** Privacy will say a new per-user behavioural store arrives exactly as the team admits purge misses about 20 tables. **Resolution:** GRO's `events` table is the first store registered in PRIV-001's registry, with `export=True`, `erase=True`, `retention_days=90`, `owner_visible="aggregate"`. GRO-007 and GRO-014 depend on the registry (or at least on its CI guard) existing first, which costs GRO about one week.
2. **SEC-012 and OPS-017 (security and owner action audit logs) vs. GRO's single event spine.** Three teams want three append-only tables. **Resolution:** one `events` table with a `stream` column (`product | security | owner_action`), per-stream retention (product 90 days, security 365 days, owner_action 365 days), and per-stream visibility. GRO's "write from domain code, never route handlers" rule applies to all three.
3. **PRD-004 (sell the product on `/login`) vs. GRO-010 (`noindex` every household page).** These don't truly conflict, but a value prop on a crawlable login of a public-profile household advertises the install and its version (GRO-010 already notes `/about` exposes the version). **Resolution:** ship PRD-004's copy with GRO-010's `noindex` and `robots.txt` in the same release. Show no version string and no library counts on unauthenticated pages.
4. **PRIV-008 (youth defaults: no YIR, no streaks, inbox only) vs. GRO's lifecycle reach.** Youth are a real share of household members, and these defaults remove them from YIR and nudges. **Resolution:** accept PRIV-008. GRO's Pulse should count youth separately so the reduced reach is not read as a lifecycle failure.

### Reinforcements

- **GRO-008 (youth gate on newsletters and nudges) is a youth leak five other teams also found:** PRIV-007, UX-044, SEC-010, ARCH-015, and PRD-011. GRO's evidence (`newsletters.py:141-195` with no youth filter, `whisper.py:113` with one) is the cleanest proof that the gate is opt-in per channel, which is ARCH-015's root cause.
- **GRO-009 ("The Professor" / "CURATOR" / "Curator (migrated)") has its accessibility half in A11Y-008.** A11Y's proposed live-region text ("Curator replied — 6 titles") needs GRO's speaking-persona resolver, or it will announce a fourth name.
- **GRO-015 (say "nothing leaves your server") pairs with PRIV-009 and VIS-014.** Google Fonts on every page, including `/privacy`, makes even GRO's corrected sentence false until fonts are self-hosted. Ship PRIV-009 before or with GRO-015.
- **GRO-012 (join failure recovery) = UX-022 = PRD-012 (first-run foyer).**

### Blind spots in other teams

- **Every department wrote success metrics that depend on GRO's spine, and none listed it as a dependency.** Examples: PRD's "first Play in under 60 s", UX's "≥1 rating per completed play", A11Y's (none instrumented), PERF-025's chat first-token SLO, and OPS's "Monday pass completable in ≤20 minutes". Phase 5 should add GRO-007 or GRO-014 as a dependency on those metrics, or mark them "manual QA script" as UX did.
- **PERF-026 (Web Vitals beacon to `/api/telemetry/vitals`) is a second, separate telemetry path.** It should write to the same spine with `stream=perf` and must be covered by GRO-015's disclosure and GRO-018's owner toggle.
- **Nobody has accounted for attribution on local accounts.** GRO-014 joins Plex `session_progress` to `rec_open` within 24 hours. Local-password members (all of QA) can only be attributed through in-app Play. That limits the north star to in-app Play households unless members link Plex (see Product's blind spot).

### Re-ranking

- **Raise GRO-008 above GRO-006 at the top of GRO's Now list.** GRO-006 scores 8.0 against GRO-008's 6.0, but GRO-008 is a child-safety defect and GRO-006 is a copy annoyance.
- **Keep GRO-007 in Next, not Now**, because of Conflict 1's registry dependency.
- **Lower GRO-013 (Docker Hub listing) to Later for the product backlog, but keep it as an XS maintainer chore.** It is real, but it does not affect the households already installed.

---

## 6. Security (SEC)

### Conflicts

1. **PERF-007 (`GZipMiddleware` on all responses at `minimum_size=1024`) vs. compression side channels.** Compressed responses that contain both a secret and attacker-influenced input are the BREACH pattern. Here the exposure is narrow: there are no CSRF tokens in bodies, and the session is in a cookie. But `GET` settings reveal (`setup_routes.py:151-168`) returns plaintext secrets. **Resolution:** compress `/assets/*`, the HTML shell, and library and feed JSON. Exclude the reveal endpoints, `/api/auth/*`, and `/mcp` with an exclude-paths wrapper, the same mechanism PERF-007 already uses for SSE. This is low risk and costs nothing.
2. **PERF-012 (an unauthenticated `GET /api/health/ready`, "LAN-only via the existing WAN interlock") depends on an interlock that SEC-003 shows can be steered** through the leftmost `X-Forwarded-For` value, and that Docker-bridge peers pass by design. **Resolution:** ship SEC-003 first, or make `/ready` return only `200`/`503` with no check names unless the caller holds `PROJECTIONIST_METRICS_TOKEN`. Add `/api/health/ready` to `PUBLIC_HANDSHAKE_EXACT` explicitly so `tests/test_api_authz.py:430` covers it.
3. **PERF-009 (nightly SQLite backups into `DATA_DIR/backups/` with `settings.json` copied alongside) vs. secrets at rest.** The backups sit in the same volume as the session secret that the secrets key is derived from (SEC-006). Anyone with the backup and the volume has everything. **Resolution:** accept for the household threat model, but exclude `DATA_DIR/backups/` from the admin snapshot zip (ARCH-014's manifest) and set `0600` on the backup files. Document that off-box copies need the secrets key handled separately.
4. **UX-009 (unblock the wizard, rail always visible) and UX-036 (persistent setup checklist) vs. SEC-007 and SEC-027 (topology-aware setup).** **Resolution:** no conflict if "Finish later" keeps `multi_user = True`. UX-009 must not add a "skip sign-in" path.
5. **GRO-016 (one-click unsubscribe link in emails)** adds an unauthenticated mutating route. **Resolution:** HMAC-signed token bound to `(user_id, channel)`, single-purpose and idempotent, and listed explicitly in the handshake allowlist and SEC-017's matrix.
6. **SEC-006 (replace the hand-rolled secrets cipher with an AEAD and an independent key) vs. OPS-010 and OPS-011.** A secrets-key mismatch already floods logs and leaves "Connected ✓" showing on QA. A cipher migration for every install is the same failure at scale. **Resolution:** sequence SEC-006 after OPS-031 (the secrets health card) and ship a dual-read migration: decrypt with the old scheme, re-encrypt with the new one on the next save, and keep a one-release fallback.

### Reinforcements

- **One authorization kernel.** SEC-017 and SEC-018, ARCH-015 and ARCH-022, and PRIV-008 describe the same missing module from three angles: route, tool, and youth. ARCH also found `/api/actions/propose` and `/api/actions/confirm` let any signed-in user trigger *arr adds (ARCH-015), which adds a REST-side variant to SEC-002's agent-side finding. Phase 5 should make this one epic.
- **Sign-out residue:** SEC-015, PRIV-016, and UX-039 are one ticket. SEC-016 (an owner creating a local account gets that user's cookie) is adjacent and should ride along.
- **Python lockfile:** SEC-014, ARCH-013, and PERF-021 are three IDs for one fix.
- **Cross-member disclosure:** SEC-010, PRIV-006, and UX-044 are one root cause, "household" meaning the Plex server account.

### Blind spots in other teams (and in SEC's own document)

- **SEC missed the biggest auth failure mode in the run, ARCH-008.** A truncated or unparsable `settings.json`, from a non-atomic write and a power cut, falls back to defaults, and the default is `multi_user_enabled = False`, which means no login with everyone as owner. SEC reviewed single-owner exposure (SEC-007) but not the path where a multi-user install *becomes* single-owner on a crash. **Re-classify ARCH-008 as a joint ARCH/SEC High,** and make the fail-closed behaviour (refuse to serve and show a recovery page) the acceptance criterion, not only the atomic write.
- **PRIV-011 (`/api/users` returns plaintext Apprise URLs) is a credential exposure.** Apprise URLs often embed bot tokens and webhook secrets, so it belongs in SEC's secrets theme as well as PRIV's minimization theme. SEC-004 (Apprise SSRF) and PRIV-011 should share a "member-supplied outbound URL" policy.
- **PRIV-002's snapshot zip includes plaintext Apprise URLs and every member's data with no audit.** SEC's Admin section praised the zip for excluding the session secret. Both are true. SEC-012's audit trail should list snapshot download as a required event.
- **The Lobby Theater's now-playing display** is flagged by SEC as a disclosure ("Keep; Investigate"), but PRIV did not cover it. See Privacy below.

### Re-ranking

- **Treat SEC-002 as Critical-tier for sequencing, even though its severity is recorded as High.** It is Confirmed from code, the effect is destructive and irreversible (`remove_from_arr` with files, `mark_bad_media` forcing re-downloads), and the actors include Youth. It is latent only while the LLM is unset, and Product, UX, and Ops are all recommending that owners connect one. It goes to the top of Now with SEC-001.
- **Raise SEC-018 from 0.96 to a Next-horizon epic lead.** Its score is low because it is L effort, but seven departments' youth findings are symptoms of it. Ship the cheap per-surface gates (UX-044, GRO-008, PRIV-007) in Now and the policy object in Next, with an inventory test that fails when a list endpoint has no viewer context.
- **Lower SEC-006 (cipher) to Later** for the sequencing reason in Conflict 6.

---

## 7. Privacy & compliance (PRIV)

### Conflicts

1. **PERF-009 (nightly backups: 14 daily and 8 weekly copies) vs. PRIV-001's erasure test ("0 rows referencing the deleted user").** After an erasure, that member's chats, memory, and reviews persist in backups for up to 8 weeks, and a restore resurrects them. **Resolution:** keep PERF-009's schedule, which is right for recoverability. Disclose the backup window on `/privacy` ("Deleted data leaves backups within 8 weeks"). Store PRIV-005's tombstones outside the restored database, or re-apply them after restore, so `scripts/restore-db.sh` replays erasures. Add a test: erase, back up, restore, and assert 0 rows.
2. **ARCH-014 (put all durable state in the snapshot zip, including the Live lineup and taxonomy overlay) vs. PRIV-002 (the snapshot is already a whole-household personal-data dump).** ARCH-014 makes it more complete, which is good for restore and worse for exposure. **Resolution:** build one registry, not two. ARCH-014's `state_manifest.py` and PRIV-001's personal-data registry should be the same module, with per-entry `required_for_restore`, `export`, `erase`, `retention_days`, and `owner_visible` attributes. The snapshot iterates it. PRIV-002's confirm dialog lists the personal-data entries it contains.
3. **GRO-014 and GRO-025 (attribution and Pulse) vs. PRIV's owner-visibility matrix** (`docs/PRIVACY.md:293,296`: owners see "—" for preference facts). **Resolution:** as in Product Conflict 3, the owner sees household aggregates and members see their own.
4. **UX-038 (seed taste from Plex history) vs. PRIV-006.** **Resolution:** as in UX Blind spots. Never seed from server-account history.
5. **OPS-033 (troubleshooting bundle instead of impersonation) vs. PRIV-002's exposure lesson.** **Resolution:** build the bundle from the privacy MCP schema denylist (`privacy/schema.py:23-49`): counts, versions, task states, and fingerprinted log lines, with no titles, chat text, emails, or Apprise URLs. Show a preview before download.
6. **PERF-012's `/api/metrics` with `scheduler_task_last_success{task}` and route-group latency** is fine, but PERF-026's vitals beacon and any future label by title or user would not be. **Resolution:** forbid `user_id`, `rating_key`, and title labels in metrics by test.

### Reinforcements

- **Deletion is incomplete, and two teams proved it independently.** PRIV-001 found it by reading tables. ARCH-009 *ran* `Database.delete_user` against a temp database and found orphans in `user_title_reviews`, `pending_actions`, `llm_usage`, `rating_prompt_queue`, and `user_memory_events`. This is the strongest-evidenced Critical in the run.
- **Youth (PRIV-007, PRIV-008)** is reinforced by GRO-008, UX-044, SEC-009, SEC-010, SEC-018, ARCH-015, and PRD-011.
- **Fonts (PRIV-009)** are reinforced by VIS-014 and PERF-016.
- **Sign-out residue (PRIV-016)** is reinforced by SEC-015 and UX-039.
- **The owner's downloads (PRIV-002, PRIV-003)** are reinforced by OPS-019 (graded warnings) and PERF-018, whose streaming fix changes how the download is built but not what it contains.

### Blind spots in other teams (and in PRIV's own document)

- **PRIV did not cover the Lobby Theater.** SEC notes that "now playing discloses household viewing" on an unauthenticated LAN kiosk (`theater/app.py:36-53`). That is cross-member disclosure in physical form: whoever walks past the lobby screen sees what a member is watching, including a youth seeing an adult's title. Add it to PRIV-006's scope, with an owner toggle to hide over-ceiling titles on the theater display and a "show title / show 'Now playing'" choice.
- **Nobody has handled erasure requests as a support workflow.** OPS reviewed owner support but has no "a member asks to be forgotten" runbook. Today the only tool is account deletion, which PRIV-001 shows is incomplete. OPS should own the owner-side UI for PRIV-004 (Members → "Export this member's data" / "Delete this member's data").
- **ARCH-011 (the Vite dev proxy targets `127.0.0.1:8788`, often an SSH tunnel to prod)** is also a privacy defect. A contributor's local dev session can read and write a real household's data. ARCH rated it Medium as a DevEx issue. The privacy dimension supports keeping it in Now.
- **SEC-012's `security_events` will store IP addresses, usernames, and agent-confirmed *arr titles.** It needs a registry entry and retention (Conflict 2 in Growth).

### Re-ranking

- **Split PRIV-001 (Critical) into a false-promise fix in Now and a mechanism fix in Next.** The false promise (`docs/PRIVACY.md:328`, "we do not leave anything behind") can be corrected in a day via PRIV-010, which removes most of the Critical exposure immediately. The registry-driven erasure is M and should be Next with ARCH-009.
- **Raise PRIV-011 (secrets in `/api/users`) from Medium to High** for the credential reason in SEC Blind spots.
- **Raise PRIV-006 to the same Now ticket as UX-044 and SEC-010.**

---

## 8. Architecture (ARCH)

### Conflicts

1. **PERF-023 (move background work to a separate worker process if SLOs still burn) vs. ARCH-001 (single writer thread) and ARCH's "exactly one process" invariant** (22 module-level caches and an in-memory rate limiter). A second process breaks the write serializer unless it owns no writes. **Resolution:** keep PERF-023 deferred, as PERF already proposes. If it is ever needed, the worker sends writes through a single writer (a local socket or an `IMMEDIATE`-transaction queue) and the invariant changes in a written ADR. PERF-008, which moves sync work to the threadpool, should make it unnecessary.
2. **ARCH-007 (`docker-release.sh` refuses to publish unless CI is green) vs. PERF-010 (an explicit `--override-red-ci "<reason>"`).** **Resolution:** refuse by default, and allow the override with a reason that is written into the release's `CHANGELOG.md` technical section and the GitHub release body. One urgent security patch should not wait on a flaky e2e spec, and the override should be rare and visible.
3. **Gates are piling up on a slow CI.** A11Y-005 (axe on 8 routes × 2 themes), VIS-041 and VIS-043 (Stylelint, visual regression), SEC-017 and SEC-034 (authz matrix, injection corpus), PERF-020 and PERF-028 (byte budget, concurrency smoke), and ARCH-025 and ARCH-026 all add to a CI that already takes 15–25 minutes serially (ARCH-023). Added naively, they push CI past 40 minutes and recreate the "merge and fix later" pressure behind ARCH-007. **Resolution:** two lanes. The required lane must finish in under 10 minutes: ruff, mypy, eslint with jsx-a11y, unit tests, the SEC-017 matrix, the PERF-020 byte budget, and the ARCH-025 fitness tests. A nightly lane, which blocks the release but not the merge, runs full e2e, axe in both themes, visual regression, the injection corpus, and the concurrency smoke. ARCH-023 becomes a dependency of every gate ticket.
4. **SEC's ruling on `curatorx_*` (Change: rename the localStorage thread key, move to `__Host-projectionist_session`) vs. ARCH's ruling (Keep until a planned breaking minor).** SEC also found there is no twin, just one cookie named `curatorx_session` that is reused as the localStorage key. **Resolution:** rename the localStorage key now, since it is client-only and doesn't break CA. Defer the cookie rename to a planned minor, read both names for one release, and fold it into SEC-015's sign-out fix.
5. **ARCH-010 (serve the SPA for every non-API `GET`)** changes 404 behaviour for crawlers and probes. **Resolution:** keep `/api/*`, `/mcp`, and `/assets/*` as real 404s, serve the shell elsewhere, and have the SPA render a proper not-found route. GRO-010's `noindex` covers the indexing side.

### Reinforcements

- **ARCH-015 and ARCH-022 are the same kernel as SEC-017 and SEC-018** and as PRIV-008's youth policy (see Security).
- **ARCH-009 and ARCH-014 are the mechanism under PRIV-001, PRIV-004, and PRIV-005** (see Privacy Conflict 2).
- **ARCH-008 (settings fail-open, re-read and decrypted per request)** has the same root cause as PERF-017 (the ~55 ms authenticated-request floor), OPS-010 and OPS-011 (MAC mismatch floods, false "Connected ✓"), and SEC-007's single-owner blast radius. One settings module would fix four departments' findings.
- **ARCH-012 is PERF-011.**
- **ARCH-007 is PERF-010.**
- **ARCH-013 is SEC-014 and PERF-021.**

### Blind spots in other teams (and in ARCH's own document)

- **ARCH did not mention `async def` handlers doing blocking I/O.** It counted 292 *sync* handlers sharing the threadpool but missed the inverse problem that PERF-008 measured: `library_query_endpoint` is `async` and calls the synchronous `query_library`, pinning the event loop for about 650 ms. The "no sync I/O in `async def`" rule (PERF-023) should be one of ARCH-025's fitness tests.
- **VIS's token inventory contradicts ARCH-004** (see Visual Conflict 5). ARCH's "Protect" verdict on token discipline may be overstated.
- **UX-009 shows the god component costs users, not only developers.** ARCH-016 treats `ConfigPage.tsx` (38 `useState`) as a maintainability issue. UX-009 shows it causes the Critical onboarding block: `canAdvance` requires four services, and the rail is hidden in wizard mode. Decomposing ConfigPage should start with the wizard section.
- **OPS-011's false "Connected ✓"** comes from `service_integrations` certification rows that outlive decryptability. That is a data-model issue (derived state persisted as truth) that ARCH's data-model theme should own.

### Re-ranking

- **Raise ARCH-008 to joint ARCH/SEC High at the top of ARCH's Now list,** next to ARCH-007 (see Security Blind spots).
- **Raise ARCH-023 (parallel CI) from Low/1.5 to Now,** because every other department's gate depends on it (Conflict 3).
- **Keep ARCH-011 in Now** for the privacy reason in Privacy Blind spots.

---

## 9. Performance, reliability & cost (PERF)

### Conflicts

1. **SEC-010 and PRIV-006 (build Continue Watching from per-user `watch_sessions` and use Plex on-deck only for the owner) vs. PERF-019 (cache Plex on-deck by `(user_id, limit)`).** The recommendations sound compatible, but PERF-019 caches a call that SEC and PRIV want to remove for members. **Resolution:** ship SEC-010 first. Member Continue Watching then becomes a local SQLite read, so PERF-019's uncached 0.75–1.6 s Plex call disappears for members. PERF-019 shrinks to an owner-only cache. This saves effort.
2. **SEC-007 (step-up) and SEC-011 (session revocation)** add work per request only if implemented as extra DB reads. **Resolution:** check step-up against the same in-memory session-epoch cache SEC-020 already uses, and add no SQLite read to the hot path.
3. **PRIV-008's `llm_route = "local_only"` for youth** (Ollama recommended) will make youth chat first-token much slower than cloud on typical Unraid hardware. **Resolution:** keep it as a privacy-correct option. PERF-025's chat first-token SLO should be reported by provider class (the table already says "local LLM < 3 s / cloud < 2 s"). UX-010's Library mode is the fallback when local inference exceeds the SLO.
4. **VIS-014 (self-host fonts, which VIS estimates adds 250–400 KB to the image)** is fine for image size. Served bytes are what matter. **Resolution:** subset to Latin plus Latin-1 WOFF2 and preload only the DM Sans regular weight. Add them to PERF-020's byte budget so cold `/login` stays at or under 400 KB compressed.
5. **A11Y-005 and VIS-043 add Playwright runs to CI** (see ARCH Conflict 3). PERF-020's throttled cold run belongs in the nightly lane, not the required lane.

### Reinforcements

- **The event-loop stall (PERF-008)** is the hidden cause of UX-021 (36 s Explore warming), parts of PRD's "long Loading titles…" observation, and the lobby theater freezes (`__main__.py:152`, where both servers share one `asyncio.gather`).
- **PERF-017 (settings re-read per call) = ARCH-008's cache half.**
- **Bundle size (PERF-007, PERF-011)** has the same root cause as ARCH-012 and PERF-014 (About), and UX-020's What's New payload rides on the same JSON.
- **PERF-010 = ARCH-007.** PERF-021 = ARCH-013 = SEC-014.
- **PERF-022 (no LLM spend cap) pairs with UX-010.** Library mode is also the right behaviour when the cap is hit or the provider times out. Write it once as "LLM unavailable" and reuse it for unset, capped, and down.

### Blind spots in other teams (and in PERF's own document)

- **PERF measured Explore with no posters.** VIS-027 shows zero poster images were requested. The 860 ms Explore LCP and the 199 KB hub JSON describe a page that, once fixed, will load about 234 images. Re-measure after VIS-027, cover the poster proxy with immutable caching, and confirm the proxy handler is not another `async def` with blocking I/O.
- **PERF-009 needs a privacy note** (see Privacy Conflict 1) and a secrets note (see Security Conflict 3). Neither appears in PERF-009.
- **OPS's Monday pass has no "backups are OK" row.** PERF-009's `backup_last_success_ts` gauge should appear as a row on OPS-030's checklist and OPS-031's card. A backup that nobody looks at is the current state.
- **UX-031 ("Tonight" card) and UX-010 (Library mode chips)** add deterministic feed calls to the landing page. Budget them in PERF-015's boot fan-out work, which is already 24 calls on `/chat`, so the new landing doesn't repeat it.

### Re-ranking

- **Raise PERF-008 above PERF-007 at the top of PERF's Now list.** PERF-007 scores higher (15.0 against 7.5), but PERF-008 hurts every household member on the LAN every evening, while PERF-007 mainly hurts off-LAN and phone users.
- **Raise PERF-009 to Critical-tier for sequencing.** It is not a security or privacy finding, but there is no proven restore of the only copy of every household's ratings, chats, and taste.
- **Lower PERF-027 (prune Hub tags on the host) to a maintainer chore outside the product backlog.**

---

## 10. Operations & support (OPS)

### Conflicts

1. **Five departments each want a panel on Admin Overview or Health:** UX-016 (LLM, TMDB, and Mail tiles plus the Monday pass on Overview), OPS-021, OPS-030, and OPS-031 (the Monday checklist and a secrets card), SEC-033 (a security posture panel), PRIV-025 (a privacy posture panel with a household notice), GRO-025 (Household Pulse), and PERF-012 and PERF-025 (readiness and SLO indicators). PRD-005 is meanwhile trying to cut 18 admin destinations. Built separately, Overview becomes the sprawl problem moved into one page. **Resolution:** one Overview with a ranked **"Needs attention"** list, fed by every subsystem through one `attention_items` contract (`{source, severity, title, action_href}`). Below it sits the Monday checklist (OPS-030). Health holds detail tabs: Connections and Secrets (OPS-031), Security (SEC-033), Privacy (PRIV-025), Pulse (GRO-025), and Reliability (PERF-025). Nothing shows on Overview unless it needs action.
2. **SEC-011 and OPS-016 (owner-mediated password reset)** agree on the capability but differ in mechanism. OPS suggests a "temporary password shown once" as one option, while SEC's lifecycle wants revocation and audit. **Resolution:** use OPS's one-time reset link (invite-style HMAC, single-use, 24 h), not a temporary password. Redeeming it bumps the session epoch (SEC-020), which signs the member out everywhere, and writes a `security_events` row (SEC-012). Remove the setup wizard's unredeemable recovery key (SEC-007) in the same change.
3. **PRD-005 (hide Off modules) vs. OPS-034 (a household status strip for optional surfaces).** If Live is hidden from members, a "Live is off" strip is noise. **Resolution:** the strip shows only degradations of surfaces the member can see, such as "Chat is in library mode" when the LLM is unset, capped, or down. Hidden modules generate no strip.
4. **SEC-006 (cipher migration)** would reproduce OPS-010 and OPS-011 at scale. See Security Conflict 6. OPS-031 must ship first.

### Reinforcements

- **OPS-011 (false "Connected ✓") and OPS-010 (MAC-mismatch flood)** share a root cause with ARCH-008 and PERF-017 (the settings module) and UX-025 (Connections persists the LLM key only on a successful Test).
- **OPS-015 (Members table hardening)** pairs with UX-027 (consolidate People), SEC-016 (an owner creating a local account loses their session), and A11Y-101 (confirm contract).
- **OPS-014 (Access requests pending for months)** pairs with PRIV-012 (no retention on access requests) and SEC-013 (enumeration and throttling).
- **OPS-019 (graded warnings on snapshot and taste export) = PRIV-002 + PRIV-003.**
- **OPS-013 (Help says Dashboard / Issues)** belongs to the glossary root cause with GRO-017, GRO-026, and UX-018.

### Blind spots in other teams (and in OPS's own document)

- **OPS did not cover the agent-destruction support incident.** Once SEC-002 is reachable, the most likely owner support ticket is "who deleted the show?", and there is no answer today because SEC-012 has no audit trail. OPS-017's "owner action audit" must cover agent-confirmed *arr writes and who prompted them, not only owner clicks.
- **OPS did not cover backup and restore as an owner routine.** PERF-009 found weekly, unverified backups with no restore drill. That makes it an owner Monday-pass item ("last verified backup: 2 days ago ✓"), and `scripts/restore-db.sh` needs a Help entry under `## For owners`.
- **OPS did not cover erasure and export requests** (see Privacy Blind spots). Members → per-member Export and Delete is the support tool, and it depends on PRIV-001 and ARCH-009.
- **UX-018 (maintainer LAN IP `10.10.1.202:8788` shipped in owner Help)** is also an OPS defect: every owner who copies the `curl` example probes an address that is not theirs. OPS-013 should absorb it.
- **OPS-018 (treat Path A QA as recon-only)** is maintainer process, not product. It belongs in `docs/ops/AUTOMAT.md` and the release rule, not in the product backlog.

### Re-ranking

- **Raise OPS-031 (secrets health card) to Now with OPS-011.** The badge fix without the card leaves owners with "Needs key" and no explanation.
- **Raise OPS-016 to Next with SEC-011** as one ticket (Conflict 2).
- **Move OPS-018 out of the product backlog** (see Blind spots).

---

## Cross-department summary

### The sharpest conflicts (for Phase 4 and Phase 5)

| # | Conflict | IDs | Proposed resolution |
|---|---|---|---|
| 1 | Nightly backups keep deleted members' data for up to 8 weeks, and a restore resurrects it | PERF-009 vs PRIV-001, PRIV-005 | Keep the schedule. Disclose the backup window, keep tombstones outside the restored DB and replay them after restore, and test erase → backup → restore = 0 rows |
| 2 | Two hex values for the same Lights Up `--accent-ink` token | VIS-001 (`#735c00`) vs A11Y-002 (`#866200`, 4.82:1 on `--surface-2`) | Adopt `#735c00`: no new hue and safer margin. One ticket |
| 3 | Five Admin panels proposed independently vs. the admin-sprawl cut | UX-016, OPS-030/031, SEC-033, PRIV-025, GRO-025, PERF-025 vs PRD-005 | One Overview "Needs attention" list fed by an `attention_items` contract, with detail tabs under Health |
| 4 | Per-viewer Continue Watching vs. caching the household Plex on-deck call | SEC-010, PRIV-006 vs PERF-019 | Ship SEC-010 first. Members read local SQLite, and PERF-019 shrinks to an owner-only cache |
| 5 | Taste seeding and attribution from "the member's Plex history," which for local or server-account members is someone else's viewing | UX-038, GRO-014 vs PRIV-006 | Seed and attribute only from the member's own `watch_sessions` or in-app Play. Decide in `31` whether members must link Plex |
| 6 | New gates on a CI that is slow and not required | A11Y-005, VIS-043, SEC-017/034, PERF-020/028, ARCH-025 vs ARCH-007, ARCH-023 | ARCH-007 first. Then two lanes: a required lane under 10 minutes and a nightly lane that blocks releases |
| 7 | A cipher migration for every install vs. an existing secrets-mismatch failure that already confuses owners | SEC-006 vs OPS-010, OPS-011 | OPS-031 first, then a dual-read migration |
| 8 | Compressing responses that carry plaintext secrets | PERF-007 vs SEC (reveal routes) | Exclude reveal, auth, and `/mcp` paths from gzip |
| 9 | Event spine and audit logs as new per-user stores while erasure misses about 20 tables | GRO-007/014, SEC-012, OPS-017 vs PRIV-001, PRIV-012 | One `events` table with per-stream retention, registered in the personal-data registry before first write |
| 10 | Type scale in px vs. relative to the browser default | VIS-006 vs A11Y-017 | Percentages (93.75 / 100 / 118.75 / 137.5%) with a `max(12px, 0.75rem)` floor |

### Shared root causes (one epic each)

1. **No authorization and youth policy kernel.** SEC-001, SEC-002, SEC-009, SEC-010, SEC-017, SEC-018, ARCH-015, ARCH-022, PRIV-006, PRIV-007, PRIV-008, GRO-008, UX-044, PRD-011. The boundary with accessibility preferences is set by A11Y-018 and A11Y-201.
2. **No registry of what is stored and whose it is.** PRIV-001, PRIV-004, PRIV-005, PRIV-010, PRIV-012, ARCH-009, ARCH-014, and the new stores from GRO-007, GRO-014, and SEC-012.
3. **No single settings and integration-state module.** ARCH-008, PERF-017, OPS-010, OPS-011, OPS-031, UX-025, SEC-006, SEC-007.
4. **Gates that do not gate.** ARCH-007, PERF-010, ARCH-023, A11Y-005, VIS-041, VIS-043, SEC-014, ARCH-013, PERF-021.
5. **Optional integrations treated as required, or hidden failures.** UX-009, UX-010, UX-013, UX-016, UX-017, PRD-006, PRD-008, GRO-006, A11Y-020, OPS-023, OPS-034, PERF-022.
6. **One undifferentiated bundle and payload.** PERF-007, PERF-011, PERF-014, ARCH-012, UX-020, A11Y-015, GRO-023, PRD-009, VIS-014, PERF-016, PRIV-009.
7. **No rating moment.** PRD-007, UX-012, UX-038, UX-043, VIS-028, A11Y-023, GRO-014.
8. **No glossary.** GRO-009, GRO-017, GRO-026, UX-015, UX-018, UX-028, A11Y-014, OPS-013.

### Duplicate tickets Phase 5 should merge

| Keep as lead | Merge in | Note |
|---|---|---|
| ARCH-007 | PERF-010 | Adopt PERF's logged override (ARCH Conflict 2) |
| ARCH-013 | SEC-014, PERF-021 | Python lockfile plus audit gate; PERF-021 adds the react-router advisory |
| ARCH-012 | PERF-011 | Route splitting; add A11Y-004 and VIS-011 acceptance criteria |
| VIS-001 | A11Y-002 | `#735c00` |
| VIS-014 | PRIV-009, PERF-016 | Fonts plus an SVG sprite from the DESIGN.md table |
| PERF-014 | UX-020, A11Y-015, GRO-023, PRD-009 | 5 Highlights in the DOM, older releases on demand |
| UX-039 | SEC-015, PRIV-016 (+ SEC-016 adjacent) | Severity Medium, horizon Now |
| UX-044 | SEC-010, PRIV-006 (Continue Watching part), PRIV-007, GRO-008 | Per-surface youth gates now; kernel later |
| A11Y-004 | GRO-024 | Route titles and announcer |
| UX-022 | GRO-012, PRD-012 | Join recovery plus foyer |
| UX-010 | PRD-008, GRO-006, A11Y-020 | Library mode; severity Critical |
| UX-012 | PRD-007, UX-043 | End-card rating |
| SEC-011 | OPS-016 | Reset link, epoch bump, audit |
| SEC-012 | OPS-017 | One `events` stream for audit |
| PRIV-002 | OPS-019 | Snapshot label, confirm, audit |
| ARCH-014 | PRIV-001 (mechanism half) | One registry module |
| SEC-018 | ARCH-015, PRIV-008 | Policy kernel epic lead |

### Notes for the red team (Phase 4)

These are claims that cross-examination could not settle and that Phase 4 should test:

- VIS's hex-literal count (190) against ARCH-004's count (7).
- Whether SEC-002 should be recorded as Critical rather than High.
- Whether PRD's B− overall grade is defensible, given that every other department graded C+ or below and three graded the consumer surface D+ to C (A11Y, PRIV, UX).
- How Explore performs with posters loading (VIS-027 × PERF).
- Whether the "Multi-user opt-in: Keep" verdicts (PRD, UX, PRIV) survive SEC's evidence that the wizard already forces multi-user.
