# 04 · Accessibility & inclusive design — 2026-11-01

Reviewed `05274cf` (v1.38.0) against WCAG 2.2 AA. Code was read from `/tmp/review360-05274cf`. Live observations come from this run's owner walk on QA `:8792` (`00_2026-11-01_platform-map.md`, `map_*` screenshots). The coordinator's replacement pass did not run axe in a browser: the original accessibility subagent was cut off before it wrote anything, and this pass was code-first so it would not wait on the shared browser. Automated checks would catch only a fraction of these issues in any case. No member, youth, or screen-reader session was available.

## Part A: Conclusions & findings

### 1. Bottom line

**Grade: C.** The foundations are better than most self-hosted apps. Both themes' text tokens clear AA by a wide margin (body 15.0:1 dark, 16.0:1 light), focus styles are explicit (91 `:focus-visible` rules), modals that use the shared focus trap behave, and route titles are announced. The single most important fix is the new Live guide. Its channel names are inside an `aria-hidden` rail that still holds focusable Tune buttons, and each program cell's accessible name omits the channel. A screen-reader user hears "Show title, 8:00 to 8:30 PM, TV-14" with no way to know which station it is (A11Y-001). The single most important thing to protect is the token contrast work and the shared `useFocusTrap` hook (A11Y-010, A11Y-011).

### 2. Key conclusions

1. **The 1.38.0 Live guide is the least accessible screen in the product.** It is new, it is keyboard-driven (arrow keys on a focusable container), and its semantics hide the one fact that makes a guide usable: which channel you are on. The container is focusable with `outline: none` (A11Y-001, A11Y-004).

2. **Landmarks depend on which page component you open.** Seventeen `<main>` elements exist, spread across pages and three layouts (Chat, Settings, Admin). `AppShell` provides none, so pages built on it, including Title detail, have no main landmark. Recon confirmed `main` count 0 on `/title/movie/348` (A11Y-002).

3. **Document titles are generic on the most specific pages.** `routeTitles.ts` maps `/title/:mediaType/:itemId` to "Title" and episodes to "Episode". Every film in the history menu or tab strip reads "Title · Projectionist" (A11Y-003, WCAG 2.4.2).

4. **Trailers autoplay with sound, and modal discipline is inconsistent.** Three YouTube embeds use `?autoplay=1`. Two dialogs (`PosterOverlayControls` trailer and the Title page trailer) set `role="dialog"` without the shared focus trap (A11Y-005, A11Y-006).

5. **Lint knows the rules and is not allowed to enforce them.** `eslint-plugin-jsx-a11y`'s recommended set is enabled and every rule is downgraded to `warn`. No e2e spec imports axe (A11Y-007, A11Y-012).

6. **There is no skip link.** Every keyboard user tabs through the top bar on every page. A grep for skip links found none (A11Y-008, WCAG 2.4.1).

7. **Status messaging is partly built.** 21 components use `aria-live` and route changes are announced, but the chat composer is silently disabled at first load, and the inbox count reads "12 unread" while the phone badge says "9+" (A11Y-009).

### 3. Foundations challenged

| Assumption | Evidence for | Evidence against | Verdict | Cost of change | Rationale |
|---|---|---|---|---|---|
| SC-13 Live belongs in the product | Arrow-key guide, per-cell names with times | Rail hidden from AT; channel missing from cell names (A11Y-001) | Change | S | Keep Live. Name the channel in each cell and stop hiding the rail. |
| SC-20 Editorial idiomatic voice | Warm copy | "turnstyle view", "Named kinship" are hard for non-native and cognitive-load users | Change | S | Keep voice in marketing copy. Plain labels on controls (WCAG 3.3.2, cognitive). |
| SC-21 Bespoke CSS with tokens | Tokens meet AA; focus-visible everywhere | Each partial reinvents `outline: none` exceptions | Keep | — | Tokens are the reason contrast is good. Add a lint rule, not a library. |
| SC-25 Phone-first consumer | 390px captures exist | Live guide clips times at 390; reflow at 320 not verified | Investigate | M | Test 320px and 200% zoom on Live and Title before calling this phone-first. |
| SC-14 In-browser playback | Players exist | Captions, OSD focus, and Escape not verified this pass | Investigate | M | Do not ship more player surface until captions and OSD focus are tested. |
| SC-01 Chat is the front door | Composer, starters, announcements | Disabled composer with an invitation placeholder | Keep | XS | Keep. Fix the status text (A11Y-009). |

### 4. If we built it today

Every page renders inside one shell that owns `<main id="main">`, a skip link to it, and a route title computed from the page's real heading. Dialogs come from one component that always uses the focus trap. The Live guide is a `grid` with row headers (channels) and cells, so a screen reader can say "Comedian, 100, 8:00 to 8:30, Show title". CI runs axe on ten routes in Lights Up and Lights Down and fails on serious violations. jsx-a11y errors fail lint.

The gap is mechanical. Tokens and focus styles are already right. Closing it is a week of work spread over the shell, the guide, and CI. It is worth it.

### 5. Findings by surface

**Public.** Login and join have labelled fields and readable errors. No skip link (A11Y-008). Unknown URLs render JSON, which a screen reader reads as punctuation. Grade: **C+.**

**Consumer.** Chat has live regions and a labelled composer; the disabled state is unannounced (A11Y-009). Title detail lacks a main landmark and a specific title, and its trailer autoplays (A11Y-002, A11Y-003, A11Y-005). Live guide is the worst screen (A11Y-001, A11Y-004). Grade: **D+.**

**Owner.** Settings and Admin layouts render `<main>`. Bulk delete uses the focus-trapped dialog, which is the right pattern for a destructive action (A11Y-011). Grade: **B-.**

**Admin.** Same layout as Owner. Tasks is a dense table; header semantics were not verified this pass. Grade: **B-.**

### 6. Findings by theme

**Keyboard and focus.** Best: 91 `:focus-visible` rules; `useFocusTrap` on Keyboard help, Recommend, Report issue, and Bulk delete. Worst: the guide container is focusable with no outline; two trailer dialogs have no trap; no skip link (A11Y-004, A11Y-006, A11Y-008).

**Semantics.** Best: route announcements via `useRouteAnnounce`. Worst: `aria-hidden` on focusable controls, missing main, generic titles (A11Y-001, A11Y-002, A11Y-003).

**Contrast.** Best: computed from tokens. Dark: text/bg 15.01, muted/bg 6.52, muted/surface-2 5.83, muted/raised 5.47, accent/bg 11.21, field border/surface 3.60. Light: text/bg 15.99, muted/bg 8.74, muted/surface-2 8.07, accent-ink/bg 6.02, field border/bg 3.96. All pass 1.4.3 and 1.4.11 at token level. Usage does not always respect that: in Lights Up the gold accent fill is used as a text color in places, including Explore's primary Search button at about 3.04:1 (see the Visual design review, VIS-003). Recon's other low-contrast captures were likely mid-fade (A11Y-010).

**Motion and media.** 16 reduced-motion blocks against 58 animation declarations; coverage is partial but present. Trailers autoplay (A11Y-005, WCAG 1.4.2 when sound plays over three seconds without a stop control outside the embed).

**Cognitive.** Idiomatic labels ("Named kinship", "turnstyle view") and a 100k-character owner Help page raise memory load. Treated in the foundations table, not ticketed separately here.

**Preventive.** Warn-only lint and no axe in e2e (A11Y-007, A11Y-012).

### 7. Stop doing

- Stop putting `aria-hidden="true"` on containers that hold buttons (A11Y-001).
- Stop building dialogs without `useFocusTrap` (A11Y-006).
- Stop appending `autoplay=1` to trailer embeds (A11Y-005).
- Stop downgrading every jsx-a11y rule to a warning (A11Y-007).

### 8. Strengths worth protecting

- Token contrast in both themes, with the comment trail explaining `--accent-ink` (A11Y-010).
- The shared focus trap: focus in on open, Tab cycles, Escape closes, focus returns (A11Y-011).
- Route titles and announcements as a single module (`routeTitles.ts`, `useRouteAnnounce.ts`).
- Per-cell accessible names in the guide already include time and rating. Adding the channel is one argument (A11Y-001).

### 9. Risks of inaction

Live is the feature the 1.38.0 release just invested in, and it is unusable with a screen reader. A blind household member cannot tell channels apart. Keyboard users will keep tabbing through the top bar. Each new page built on `AppShell` will ship without a main landmark. Warn-only lint means a missing `alt` will reach `main` unnoticed.

### 10. Recommended direction

Now: fix the guide's semantics and focus ring, add the skip link and `<main>` in `AppShell`, give Title pages real titles, drop trailer autoplay. Next: put the trailer dialogs on the focus trap, promote five jsx-a11y rules to errors, add axe to e2e on ten routes. Later: 320px and 200% zoom pass on Live and Title, and player caption and OSD review.

Success in 90 days: a screen reader announces the channel for every guide cell, every route has one `main`, axe e2e has zero serious violations on the ten routes, and lint fails on missing alt, interactive non-interactive elements, and aria-hidden focusables.

### 11. Scorecard

| Surface | Keyboard | Screen reader | Contrast | Motion/media | Overall |
|---|---|---|---|---|---|
| Public | 3 — no skip link | 3 — labelled form | 5 | 4 | 3 |
| Consumer | 2 — guide focus invisible | 1 — guide hides channels | 5 | 2 — trailer autoplay | 2 |
| Owner | 4 — trapped dialogs | 3 | 5 | 4 | 4 |
| Admin | 4 | 3 — table headers unverified | 5 | 4 | 4 |

Scores are 1–5.

**Screen-reader narration, Live guide today** (from `LiveGuide.tsx:191-305`): focus lands on an unlabeled group (the container has no role or name). Arrow keys move a visual highlight. Each cell announces "{title}, {start} to {end}, {episode}, {rating}". Channel buttons in the rail are reachable by Tab but are inside `aria-hidden`, so a reader may announce nothing or announce them inconsistently. Proposed: "Live guide, grid. Row 100 Comedian. {title}, 8:00 to 8:30 PM, TV-14, button."

---

## Part B: Detailed findings

### 12. Scope and method

Code inspection of `frontend/src` at `05274cf`: landmarks, `aria-*`, focus handling, modals, reduced motion, lint config, e2e. Token contrast computed with the WCAG relative-luminance formula from `styles/01-tokens.css`. Live evidence is the platform map's owner walk (P-3 title and main, P-4 inbox count, P-8 low contrast mid-fade, P-13 disabled composer). Not done: axe in a browser, NVDA/VoiceOver, 320px reflow, 200% zoom, captions, member and youth sessions.

### 13. Strengths

### A11Y-010: Keep token contrast at AA or better in both themes

| Field | Value |
|---|---|
| Type | Strength |
| Surface | Cross-cutting |
| Persona(s) | Older user with low vision, all |
| Category | Contrast |
| Severity | High |
| Impact | 5 |
| Effort | S |
| Confidence | Confirmed |
| Priority score | 7.5 |
| Verdict | Protect |
| Dependencies | none |
| Labels | contrast, 1.4.3, 1.4.11 |

**Evidence:** `05274cf:frontend/src/styles/01-tokens.css:41-56` (Lights Down) and `:110-123` (Lights Up). Computed: text/bg 15.01 and 15.99; muted/bg 6.52 and 8.74; muted on raised 5.47; accent ink on bg 11.21 and 6.02; field border 3.60 and 3.96 (1.4.11 needs 3:1). The comment at line 47 documents why `--border-field` exists.

**Current state:** Every text token pair clears 4.5:1 and every field outline clears 3:1. Recon's faint captures (P-8) are most likely animations caught mid-fade, since the tokens themselves pass.

**Root cause:** Prior contrast work split fill from ink and gave fields a dedicated border.

**Recommendation:** New colors are added as tokens with a stated ratio in the comment. Do not use `opacity` below 1 on text to "soften" it. Verify fades with `prefers-reduced-motion: reduce` so the end state is what ships.

**Rationale:** Contrast is the most common AA failure and it is solved here. A designer's "lighter muted" would undo it in one line.

**User story:** As an older member with low vision, I want body and secondary text to stay readable in both themes.

**Acceptance criteria:**
- [ ] A unit test computes the ratios above from the token file and fails under 4.5:1 for text and 3:1 for borders.
- [ ] No text rule uses opacity under 1.

**Success metric:** Zero contrast violations from axe on the ten routes in A11Y-012.

**Validation:** Token test plus axe.

### A11Y-011: Keep the shared focus trap for every dialog

| Field | Value |
|---|---|
| Type | Strength |
| Surface | Cross-cutting |
| Persona(s) | Keyboard-only user, screen-reader user |
| Category | Focus |
| Severity | Medium |
| Impact | 4 |
| Effort | S |
| Confidence | Confirmed |
| Priority score | 4.0 |
| Verdict | Protect |
| Dependencies | none |
| Labels | focus, 2.4.3 |

**Evidence:** `05274cf:frontend/src/hooks/useFocusTrap.ts:31`. Used by `KeyboardHelpModal.tsx:24-26` (comment: focus in, Tab cycles, Escape closes, focus returns), `RecommendModal.tsx`, `ReportMediaIssueModal.tsx`, and `BulkLibraryDeleteDialog.tsx:74`. Dialogs set `role="dialog"`, `aria-modal`, and `aria-labelledby`.

**Current state:** Where the hook is used, dialogs meet 2.4.3 and 2.1.2.

**Root cause:** A single hook was written once and reused.

**Recommendation:** Every `role="dialog"` uses the hook. A lint check (grep in CI is enough) fails when `role="dialog"` appears in a file that does not import `useFocusTrap`.

**Rationale:** The two dialogs without it (A11Y-006) are the proof that convention is not enough.

**User story:** As a keyboard user, I want focus to stay in a dialog and return when it closes.

**Acceptance criteria:**
- [ ] Every file with `role="dialog"` imports `useFocusTrap`.
- [ ] Escape closes and focus returns to the opener.

**Success metric:** CI grep passes.

**Validation:** Keyboard walk of each dialog.

### 14. Weaknesses

### A11Y-001: Name the channel in every Live guide cell and stop hiding the rail

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Consumer |
| Persona(s) | Screen-reader user, keyboard-only user |
| Category | Semantics |
| Severity | High |
| Impact | 5 |
| Effort | S |
| Confidence | Confirmed |
| Priority score | 7.5 |
| Verdict | Fix |
| Dependencies | none |
| Labels | live, 1.3.1, 4.1.2 |

**Evidence:** `05274cf:frontend/src/components/live/LiveGuide.tsx:199` `<div className="live-guide-rail" aria-hidden="true">` contains `<button>` elements at `:205-224` with `aria-label="Tune {number} {name}"`. Program cells at `:267-297` build `aria-label` from `guideProgramAccessibleName(title, timeRange, episodeLabel, rating)`, which takes no channel. WCAG 1.3.1 (relationships) and 4.1.2 (name, role, value); ARIA forbids focusable descendants of `aria-hidden`.

**Current state:** A screen-reader user can move through programs and never hear the station. The station buttons can take focus while being hidden from the accessibility tree.

**Root cause:** The rail was hidden to avoid double-announcing channel names, and the cell names were not given the channel in exchange.

**Recommendation:** Remove `aria-hidden` from the rail. Pass the channel label as the first argument: `guideProgramAccessibleName(channelLabel, title, timeRange, episodeLabel, rating)`, where `channelLabel` is "100 Comedian". Give the container `role="grid"` and `aria-label="Live guide"`, each row `role="row"`, the station `role="rowheader"`, and each cell `role="gridcell"` wrapping its button.

**Rationale:** A guide without channels is a list of shows at unknown times on unknown stations. Hiding the rail was the wrong fix for duplicate speech. Rejected: a separate "screen-reader table", which would drift from the visual grid.

**User story:** As a screen-reader user, I want to hear which channel a program is on so I can choose a station.

**Acceptance criteria:**
- [ ] No element inside `aria-hidden` is focusable.
- [ ] Every cell's accessible name begins with channel number and name.
- [ ] VoiceOver announces "Live guide, grid" on focus.

**Success metric:** A blind tester can tune the Youth Safe channel without sighted help.

**Validation:** axe rule `aria-hidden-focus` passes; manual VoiceOver walk (without tuning on QA, which is off-limits; use a local build).

### A11Y-002: Put one main landmark in AppShell

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Consumer |
| Persona(s) | Screen-reader user |
| Category | Landmarks |
| Severity | Medium |
| Impact | 4 |
| Effort | S |
| Confidence | Confirmed |
| Priority score | 4.0 |
| Verdict | Fix |
| Dependencies | none |
| Labels | landmarks, 1.3.1, 2.4.1 |

**Evidence:** 17 `<main>` occurrences across pages and layouts (`LibraryPage.tsx:59`, `PrivacyPage.tsx:132`, `ChatWorkspace.tsx:444`, `SettingsLayout.tsx:193`, `AdminLayout.tsx:239`, others). `layouts/AppShell.tsx` contains none. `TitleDetailPage.tsx:66-97` renders through `AppShell` and adds no `<main>`. Recon P-3: `document.querySelectorAll('main,[role=main]').length === 0` on `/title/movie/348`.

**Current state:** Whether a page has a main landmark depends on whether its author remembered.

**Root cause:** The landmark lives in pages, not in the shell that every page shares.

**Recommendation:** `AppShell` renders `<main id="main" tabIndex={-1}>` around its children. Remove page-level `<main>` elements that sit inside `AppShell`, converting them to `<div>` with the same class, so no page has two.

**Rationale:** Landmarks are how screen-reader users skip chrome. One owner prevents both zero and two.

**User story:** As a screen-reader user, I want to jump to the main content on every page.

**Acceptance criteria:**
- [ ] Every route has exactly one `main`.
- [ ] The Title page has one.

**Success metric:** axe `landmark-one-main` passes on all ten e2e routes.

**Validation:** DOM query in e2e.

### A11Y-003: Give Title and Episode pages their real names

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Consumer |
| Persona(s) | Screen-reader user, keyboard-only user |
| Category | Page titles |
| Severity | Medium |
| Impact | 3 |
| Effort | XS |
| Confidence | Confirmed |
| Priority score | 3.0 |
| Verdict | Fix |
| Dependencies | none |
| Labels | titles, 2.4.2 |

**Evidence:** `05274cf:frontend/src/lib/routeTitles.ts:53` `/title/episode/:ratingKey` → "Episode"; `:96` `/title/:mediaType/:itemId` → "Title". Recon: tab title stayed "Title · Projectionist" on Alien (1979).

**Current state:** Every film page has the same title. Browser history, tab switching, and screen-reader page announcements cannot tell them apart.

**Root cause:** Route titles are computed from the URL pattern, before the item loads.

**Recommendation:** After the item loads, set `document.title` to "{Title} ({year}) · Projectionist", and episodes to "{Show} S{n}E{m} · Projectionist". Keep "Title" only while loading.

**Rationale:** WCAG 2.4.2 asks for titles that describe topic or purpose. "Title" describes neither.

**User story:** As a member with several tabs open, I want each film's tab to show its name.

**Acceptance criteria:**
- [ ] Loaded title pages include the item name in `document.title`.
- [ ] Route announcement reads the same string.

**Success metric:** History menu lists film names.

**Validation:** Open two titles and compare tab text.

### A11Y-004: Show a focus ring on the Live guide container and player

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Consumer |
| Persona(s) | Keyboard-only user |
| Category | Focus visible |
| Severity | Medium |
| Impact | 4 |
| Effort | XS |
| Confidence | Likely |
| Priority score | 3.2 |
| Verdict | Fix |
| Dependencies | A11Y-001 |
| Labels | focus, 2.4.7, 2.4.11 |

**Evidence:** `05274cf:frontend/src/components/live/LiveGuide.tsx:191-197` sets `tabIndex={0}` on `.live-guide`. `05274cf:frontend/src/styles/12-live.css:678-683` `.live-guide { outline: none; }` and `:236-240` `.live-player { outline: none; }`. Focus rules exist for `.live-guide-cell.is-focused` (`:887`) and the Lights Up `:focus-visible` cell (`:1578`), not for the container.

**Current state:** Tabbing to the guide lands on an element with no visible focus until arrow keys highlight a cell. Likely rather than Confirmed because a cell may receive `is-focused` immediately; not observed live this pass.

**Root cause:** The container was made focusable for arrow-key handling and its outline was removed to avoid a box around the whole grid.

**Recommendation:** `.live-guide:focus-visible { outline: 2px solid var(--accent-ink); outline-offset: -2px; }` and the same on `.live-player:focus-visible`. Better, move focus to the selected cell when the container receives focus (roving tabindex) and keep the cell ring.

**Rationale:** 2.4.7 requires visible focus. A grid with an invisible entry point looks broken to keyboard users.

**User story:** As a keyboard user, I want to see where focus is when I tab into the guide.

**Acceptance criteria:**
- [ ] Tabbing into the guide shows a ring on the container or the selected cell.
- [ ] The player shows a ring when focused.

**Success metric:** A keyboard-only recording shows a visible indicator at every step.

**Validation:** Local build, keyboard walk.

### A11Y-005: Stop autoplaying trailers

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Consumer |
| Persona(s) | Screen-reader user, cognitive-load users |
| Category | Media |
| Severity | Medium |
| Impact | 3 |
| Effort | XS |
| Confidence | Confirmed |
| Priority score | 3.0 |
| Verdict | Fix |
| Dependencies | none |
| Labels | media, 1.4.2 |

**Evidence:** `?autoplay=1` on YouTube embeds at `05274cf:frontend/src/pages/TitleDetailPage.tsx:174`, `components/TitleDetailDrawer.tsx:333`, and `components/PosterOverlayControls.tsx:187`.

**Current state:** Opening a trailer starts audio immediately. For screen-reader users, that audio covers the reader announcing the dialog.

**Root cause:** Autoplay was added because the user clicked "Watch trailer", which reads as consent to play.

**Recommendation:** Remove `autoplay=1`. Focus the iframe's play button area (the iframe itself) when the dialog opens so one Enter starts playback.

**Rationale:** 1.4.2 is about audio that starts automatically. The click is arguably consent, but the collision with the dialog announcement is real, and one extra keypress costs little.

**User story:** As a screen-reader user, I want to hear the dialog title before the trailer audio starts.

**Acceptance criteria:**
- [ ] No embed URL contains `autoplay=1`.
- [ ] Enter on the opened dialog starts the trailer.

**Success metric:** Grep finds zero autoplay parameters.

**Validation:** Grep plus a keyboard open of a trailer.

### A11Y-006: Put both trailer dialogs on the focus trap

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Consumer |
| Persona(s) | Keyboard-only user |
| Category | Focus |
| Severity | Medium |
| Impact | 3 |
| Effort | XS |
| Confidence | Confirmed |
| Priority score | 3.0 |
| Verdict | Fix |
| Dependencies | A11Y-011 |
| Labels | dialog, 2.4.3, 2.1.2 |

**Evidence:** `05274cf:frontend/src/components/PosterOverlayControls.tsx:177-187` has `role="dialog"`, `aria-modal="true"`, and no `useFocusTrap` (count 0 in file). `TitleDetailPage.tsx` has a `role="dialog"` trailer and no `useFocusTrap`; it installs its own `keydown` listener for Escape (`:55-62`).

**Current state:** Tab can leave the trailer dialog into the page behind it while `aria-modal` tells assistive tech the page is inert.

**Root cause:** These dialogs predate or bypassed the shared hook.

**Recommendation:** Use `useFocusTrap({ open: trailerOpen, onClose })` in both and delete the bespoke Escape listener.

**Rationale:** The hook exists and is proven elsewhere (A11Y-011).

**User story:** As a keyboard user, I want Tab to stay in the trailer until I close it.

**Acceptance criteria:**
- [ ] Both files import `useFocusTrap`.
- [ ] Focus returns to "Watch trailer" on close.

**Success metric:** The CI grep from A11Y-011 passes.

**Validation:** Keyboard walk.

### A11Y-008: Add a skip link to main content

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Cross-cutting |
| Persona(s) | Keyboard-only user, screen-reader user |
| Category | Bypass blocks |
| Severity | Medium |
| Impact | 3 |
| Effort | XS |
| Confidence | Confirmed |
| Priority score | 3.0 |
| Verdict | Fix |
| Dependencies | A11Y-002 |
| Labels | skip-link, 2.4.1 |

**Evidence:** Case-insensitive grep for "skip link" / "skip to" across `frontend/src` (`*.tsx`, `*.ts`, `*.css`) returns nothing at `05274cf`. The top bar has up to seven peers plus brand and hamburger (`primaryNav.ts`).

**Current state:** Keyboard users tab through the chrome on every page.

**Root cause:** No shell-level landmark existed to skip to (A11Y-002).

**Recommendation:** First focusable element in `AppShell` and the three layouts: `<a class="skip-link" href="#main">Skip to content</a>`, visually hidden until focused, then a 2px accent-ink outline on the surface color.

**Rationale:** 2.4.1. Landmarks help screen-reader users; the skip link is what sighted keyboard users get.

**User story:** As a keyboard user, I want to skip the top bar so I can reach the page quickly.

**Acceptance criteria:**
- [ ] First Tab on any route shows "Skip to content".
- [ ] Activating it moves focus into `#main`.

**Success metric:** Tabs-to-content drops from about eight to two.

**Validation:** Keyboard walk.

### A11Y-009: Announce why the chat composer is disabled, and make inbox counts agree

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Consumer |
| Persona(s) | Screen-reader user |
| Category | Status messages |
| Severity | Medium |
| Impact | 3 |
| Effort | S |
| Confidence | Confirmed |
| Priority score | 3.0 |
| Verdict | Fix |
| Dependencies | none |
| Labels | status, 4.1.3 |

**Evidence:** Recon P-13: composer disabled for several seconds with the placeholder "Describe what you're hunting for…". Recon P-4: top-bar accessible name "Inbox, 12 unread", desktop badge "12", bottom nav "9+".

**Current state:** A disabled field with an invitation reads as broken. The same count is spoken and shown three ways.

**Root cause:** Disabled state reuses the idle placeholder; badge formatting is per component.

**Recommendation:** While disabled, an `aria-live="polite"` line "Opening your library…" and no typing placeholder. One formatter for the unread count used by both badges and the accessible name.

**Rationale:** 4.1.3 (status messages) and 3.2.4 (consistent identification).

**User story:** As a screen-reader user, I want to hear that chat is loading instead of finding a dead field.

**Acceptance criteria:**
- [ ] Disabled composer announces a loading message once.
- [ ] All inbox representations show one value.

**Success metric:** A screen-reader recording announces the loading line.

**Validation:** VoiceOver on a local build.

### A11Y-007: Make five jsx-a11y rules fail lint

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Cross-cutting |
| Persona(s) | All assistive-technology users |
| Category | Prevention |
| Severity | Medium |
| Impact | 3 |
| Effort | S |
| Confidence | Confirmed |
| Priority score | 3.0 |
| Verdict | Fix |
| Dependencies | none |
| Labels | lint, prevention |

**Evidence:** `05274cf:frontend/eslint.config.js:16-25` maps every `jsx-a11y/` recommended rule to `"warn"` so `npm run lint` stays at zero errors.

**Current state:** The rules run and cannot block a merge.

**Root cause:** The plugin was added as a baseline over an existing tree.

**Recommendation:** Promote to `error`: `alt-text`, `aria-props`, `aria-role`, `no-aria-hidden-on-focusable`, `label-has-associated-control`. Fix the existing hits in the same PR. Leave the rest as warnings.

**Rationale:** Five high-signal rules catch the regressions that matter (A11Y-001 is one) without stopping the release train.

**User story:** As a maintainer, I want lint to fail on a missing alt so it never reaches a member.

**Acceptance criteria:**
- [ ] The five rules are `error`.
- [ ] `npm run lint` exits 0 after fixes.

**Success metric:** No new warnings for those five rules.

**Validation:** Lint run in CI.

### 15. Opportunities

### A11Y-012: Run axe on ten routes in e2e

| Field | Value |
|---|---|
| Type | Opportunity |
| Surface | Cross-cutting |
| Persona(s) | All assistive-technology users |
| Category | Prevention |
| Severity | Medium |
| Impact | 3 |
| Effort | M |
| Confidence | Confirmed |
| Priority score | 2.0 |
| Verdict | Add |
| Dependencies | A11Y-002 |
| Labels | axe, e2e |

**Evidence:** No file under `e2e/` references axe at `05274cf`. CI already runs Playwright (`.github/workflows/ci.yml:71`).

**Current state:** Accessibility is checked by lint warnings only.

**Root cause:** No a11y step was added when e2e was.

**Recommendation:** Add `@axe-core/playwright` and one spec that visits `/login`, `/`, `/search?q=alien`, `/explore`, `/title/movie/<fixture>`, `/live`, `/inbox`, `/settings/profile`, `/admin`, `/privacy` in both themes against the mocked e2e server, failing on `serious` and `critical`.

**Rationale:** Automated checks catch perhaps a third of issues, and they catch them every time. The e2e server is already mocked, so this costs CI minutes, not infrastructure.

**User story:** As a maintainer, I want a new page with no landmark to fail CI.

**Acceptance criteria:**
- [ ] Twenty axe runs (ten routes, two themes) in CI.
- [ ] Zero serious or critical violations at merge.

**Success metric:** The spec stays green for a quarter.

**Validation:** CI log.

### 16. Remediation plan

| Horizon | ID | Title | Effort | Owner | Dependencies |
|---|---|---|---|---|---|
| Now | A11Y-001 | Channel in guide cells; unhide rail | S | Frontend | none |
| Now | A11Y-004 | Focus ring on guide and player | XS | Frontend | A11Y-001 |
| Now | A11Y-002 | One main in AppShell | S | Frontend | none |
| Now | A11Y-008 | Skip link | XS | Frontend | A11Y-002 |
| Now | A11Y-003 | Real title page names | XS | Frontend | none |
| Now | A11Y-005 | No trailer autoplay | XS | Frontend | none |
| Next | A11Y-006 | Trailer dialogs on focus trap | XS | Frontend | A11Y-011 |
| Next | A11Y-009 | Composer status; one inbox count | S | Frontend | none |
| Next | A11Y-007 | Five jsx-a11y errors | S | Frontend | none |
| Next | A11Y-012 | axe in e2e | M | Frontend | A11Y-002 |

Sequencing: the guide first because it is new and broken. Landmark before skip link because the link needs a target. Lint and axe after the fixes so they start green.

### 17. Quick wins

A11Y-003, A11Y-004, A11Y-005, A11Y-006, and A11Y-008 are each XS.

### 18. Open questions

- Should youth see the full guide grid with gated cells, or only allowed channels? This affects what the grid announces.
- Captions: does in-browser Play expose Plex subtitles as text tracks? Not verified; owner of the player should confirm before more player work ships.

### Phase 6 self-check

- [x] Part A first; conclusions cite IDs.
- [x] High findings A11Y-001 (weakness) and A11Y-010 (strength) are in the bottom line.
- [x] Foundations, "If we built it today", and "Stop doing" present.
- [x] All four surfaces in section 5.
- [x] Strengths use the full format.
- [x] WCAG criterion cited per finding; automated-check limit stated.
- [x] IDs A11Y-001 through A11Y-012 are unique.
- [x] No application code modified. Status file updated by the coordinator.

### Changelog

- 2026-11-02 (red team, `21_2026-11-01_red-team.md` RT-1): scoped the A11Y-010 contrast claim to token level and added the Lights Up gold-fill-as-text exception measured by Visual design (VIS-003). Grade and finding IDs unchanged.
