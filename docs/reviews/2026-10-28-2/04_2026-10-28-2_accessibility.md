# 04 — Accessibility & Inclusive Design review

**Run:** 2026-10-28-2 · **Written:** 2026-10-29 · **Reviewer:** Accessibility & Inclusive Design Lead (independent 360 board)
**Code truth:** `94fcd3f` (`origin/main` = 1.37.72 + PR #188). Citations are `git show 94fcd3f:<path>` line numbers.
**Live truth:** QA sidecar `http://10.10.1.202:8792` only (health `{"status":"ok","version":"1.37.72"}`). Public HTML via `curl`, plus a signed-in keyboard session on Play (youth Mister Rogers `/watch/182044`, owner Don't Look Up `/watch/84250`, youth rating 403 on the same R-rated URL). No prod `:8788`, no smartmap `:8790`. No VoiceOver, axe, or 200% zoom.
**Target:** WCAG 2.2 Level AA. AAA quick wins flagged.

> **Read this first — coverage gap.** Apart from a short keyboard check on Play (Space pauses; Escape does not leave `/watch`), nothing in this review was exercised with a real screen reader, a full keyboard session, browser zoom, or axe. Evidence is (a) source at `94fcd3f`, (b) `git grep` counts, (c) contrast ratios **computed** from the design tokens with the WCAG relative-luminance formula, (d) the attached QA screenshots, and (e) `curl` of the SPA shell on `:8792`. Automated checks typically catch roughly a third of WCAG failures; static code reading catches more of the structural ones but cannot prove runtime focus order, announcement timing, or rendered contrast over images. Screen-reader transcripts below are **predicted** from code and marked *Likely*.

---

# Part A — Executive view

## Bottom line

Projectionist has the bones of an accessible app — real forms with wrapped labels, `role="alert"` errors, a properly focus-trapped title drawer, a well-labelled player OSD, a WCAG-AA-clean **Lights Down** palette, and a native text-size control — but **the primary loop is not usable by a screen-reader user without heroic effort**, and the **light theme fails AA text contrast** everywhere the brand amber is used as text. Chat (the product's sacred centre) drops keyboard focus on every send and never announces the reply. Explore's poster icons have an effectively invisible focus indicator. Every route is titled "Projectionist". Eight of eighteen dialog files ship `aria-modal="true"` without moving, trapping, or restoring focus, including the `?` shortcut help that cannot be closed with Escape. There is no lint rule, no axe run, and no CI job that would catch any of this, and the project's own UI-testing rule scopes axe to "Lights Down contrast" — exactly the theme that already passes.

No single finding is a hard blocker (I found no Critical), but the High findings stack on the same journeys: sign in → chat → explore → open title → play.

## Grade: **C−**

Keyboard-only users can complete most tasks with friction. Screen-reader users can sign in and browse, but chat — the reason the app exists — is silent and disorienting. Low-vision users on Lights Up (the default for anyone whose OS is in light mode, because the default theme is "system") read 3.04:1 amber links and labels.

## Most important fix

**A11Y-001 + A11Y-008 together: make the chat send loop keep focus and announce the reply.** Stop setting `disabled` on the focused composer while a reply streams (`ChatWorkspace.tsx:607`), and add a polite completion announcement ("Curator replied — 6 titles") in a dedicated live region. Without these two, a blind household member cannot use the curator.

## Most important protect

**A11Y-101: the TitleDetailDrawer / ConfirmModal focus contract** (`TitleDetailDrawer.tsx:99-140`, `ConfirmModal.tsx:107-134`) — focus moves in, Tab is trapped, Escape closes, focus returns to the trigger. It is the only correct dialog pattern in the codebase. Extract it into a shared primitive (A11Y-202) instead of letting new dialogs copy the broken ones.

## Conclusions

1. **The chat loop is the least accessible part of the product.** The composer is disabled during streaming, which drops focus to `<body>` (A11Y-001); the transcript has no live region so replies are never announced (A11Y-008); the composer's only name is a rotating placeholder (A11Y-016). Chat being "the primary product" makes this the top priority.
2. **Lights Up uses a fill colour as an ink colour.** `--accent: #b8860b` is 3.04:1 on `--bg` and appears as text in 103 declarations plus every `<a>` (A11Y-002). A separate `--accent-ink` (e.g. `#866200`, 5.22:1) fixes it in one token without changing the brand fill.
3. **Focus visibility is inconsistent by design pattern, not by accident.** The topbar has a 2px accent outline (good), but poster overlay icons replace the outline with a 1.08–1.73:1 background darkening, and the composer swaps it for a 1px border that is 2.16:1 in Lights Up (A11Y-003). Forced-colours mode is unsupported (A11Y-025).
4. **The app has no page titles and no route announcements.** `index.html:57` is the only `<title>` and the bundle has zero `document.title` writes (A11Y-004). SPA navigation is invisible to screen readers.
5. **Dialogs, menus, and the player chrome were built one at a time, and most got the hard parts wrong.** 2 of 18 dialog files have a full focus contract (A11Y-009); `role="menu"` is used on popovers with no `menuitem` children and no arrow keys (A11Y-013); the hamburger drawer is portaled to the end of `<body>` without moving focus (A11Y-007). When Play's chrome idles, the whole OSD including Close is `aria-hidden`, and Escape does not leave the watch route (A11Y-023). A youth rating 403 offers only **Try again**, which cannot succeed (A11Y-027).
6. **Youth and caption needs are gated on one flag.** Youth members see "Ask"/"Browse" in the nav but "Chat"/"Explore" in Help (A11Y-014), and SDH captions are only preferred when `is_youth` is true — a Deaf adult cannot ask for them (A11Y-018).
7. **Nothing prevents regression.** No `eslint-plugin-jsx-a11y`, no `@axe-core/playwright`, and the `npm run lint` job that does run in CI (`.github/workflows/lint.yml`) has no a11y rules and does not block merges (ARCH-007), e2e has 0 `toBeFocused` and 3 `keyboard.press` calls (A11Y-005).
8. **Cognitive load is high in exactly the places nobody is maintaining for it**: a 272-release changelog wall in the About DOM (A11Y-015), "Configure an LLM provider" shown to members and youth who cannot act on it (A11Y-020), and duplicate "Related titles" links in Help (A11Y-006).

## Foundations challenged

| Sacred cow (platform map §3) | What accessibility says | Ruling |
|---|---|---|
| #1 Chat is the primary product | It is also the least accessible surface (A11Y-001, 008, 016). If chat is primary, its a11y is primary. | **Keep, but fund it** |
| #12 Lights Down + amber + Fraunces as brand | Amber works as ink only on dark (11.21:1). On Lights Up it is a fill, not an ink (3.04:1). Default theme is "system", so light-OS users get Lights Up. | **Rethink token split** (A11Y-002) |
| #21 What's New modal on version bump (even on `/login`) | A modal with no focus move or Escape (`WhatsNewModal.tsx:17-28`) sitting on the sign-in door is the worst place for a broken dialog. | **Rethink**: no modal on `/login`; dialog contract everywhere |
| #22 About ships the entire CHANGELOG into the DOM | 272 release articles, ~504 KB source, `h3`/`h4` per release; SR heading list becomes unusable; jump select does not move focus. | **Remove from default DOM** (A11Y-015) |
| #9 Youth is a flag, not a role | Fine for permissions; wrong for accessibility prefs. SDH, vocabulary, and Help copy all key off `is_youth`. | **Rethink**: separate a11y prefs from youth (A11Y-018, 201) |
| #18 Help/Privacy are first-class in-app docs | Good — but Help is owner/non-owner only, not youth-aware, and duplicates link names. | **Protect + fix** (A11Y-006, 014) |
| #20 Play and Live share one TheaterPlayer shell | One shell means one place to fix captions, OSD focus, shortcuts. Good for a11y. | **Protect** (A11Y-103) |
| #11 Lobby Theater is a LAN kiosk | Ambient signage auto-rotating at 12 s with no pause is acceptable for a kiosk (2.2.2 "essential" argument), but CSS honours reduced motion. | **Keep** |

## If we built it today

- One `<Dialog>` built on native `<dialog>.showModal()` (free focus trap, Escape, inert background) and one `<Menu>`/`<Disclosure>` primitive. No hand-rolled `role="dialog"` divs.
- A route announcer: on navigation, set `document.title = "<Page> · Projectionist"` and move focus to the page `<h1>`.
- Two accent tokens per theme: `--accent` (fill) and `--accent-ink` (text, ≥4.5:1).
- A global `:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: 2px }` that components may *add to* but never remove.
- Chat transcript as `role="log"` with per-message headings, plus a separate polite status region for "Curator replied".
- Never disable the control that holds focus; use `aria-disabled` + guarded handler.
- `rem` scale relative to the user's browser default (100% / 112.5% / 125%), not `13/15/17px`.
- Explore rails with roving tabindex (one tab stop per rail, arrows inside) and "Skip to next shelf".
- `eslint-plugin-jsx-a11y` + `@axe-core/playwright` (both themes) as CI gates from commit one.

## Findings by surface

| Surface | Grade | Why | Key IDs |
|---|---|---|---|
| **Public** (`/login`, `/join`, `/help`, `/about`, `/privacy`) | **C** | Real forms, labels, `role="alert"`. But no `<main>` in GlassDoor, focus drops on submit and on "Need an invite?", Lights Up footer links 3.09:1, About changelog wall, duplicate Help link names, every page titled "Projectionist". | 001, 002, 004, 006, 012, 015, 016 |
| **Consumer** (chat, explore, title, play, settings, youth) | **D+** | Chat silent + focus loss; Explore icon focus invisible; ~4–5 tab stops per poster with no bypass; repeated "Play"/"Trailer" names; dialogs without focus contract; youth vocabulary drift; SDH youth-only. Play hides its controls from the accessibility tree when the chrome idles, and Escape does not leave `/watch` (A11Y-023). Bright spots: title drawer, player OSD labels while visible, text-size radios. | 001, 003, 006, 008, 009, 010, 011, 013, 014, 018, 023 |
| **Owner** (owner tools on consumer surfaces, Lobby, Live studio) | **C−** | Owner tools live inside the broken `role="menu"` poster popover; bulk delete dialog has good fieldset/legend but no focus contract; destructive "Delete from index" sits in an unmanaged menu. | 009, 013, 019 |
| **Admin** (`/admin/*`) | **C** | Admin rail is the best nav in the app (NavLink `aria-current`, `section aria-labelledby`). But the hamburger drawer path (shown in screenshot) has vertical, clipped group labels as `<p>`, `li role="presentation"`, no focus management; wide tables force 2-D scroll at 320 px. | 007, 021, 026, 107 |

## Themes

1. **Async state is treated as a visual problem** — disable the control, show "Signing in…" — instead of a focus and announcement problem (001, 008, 016).
2. **ARIA added for test hooks or by analogy, not by pattern** — `role="menu"` without menu behaviour, `aria-label` on generic spans, `aria-live` on a `role="button"` (013).
3. **Lights Down is the tested theme; Lights Up is the shipped default for light-OS users** (002, 003, 005).
4. **Per-component fixes without primitives** — 18 dialog files, three different Escape strategies (009).
5. **Youth flag as a proxy for "needs"** (014, 018).

## Stop doing

- Setting `disabled` on the element that currently has focus during async work.
- Writing `outline: none` in a `:focus-visible` rule (7 instances cited in A11Y-003).
- Using `--accent` as a text colour in Lights Up.
- Adding `role="menu"` to popovers that are really disclosure lists.
- Shipping a new `role="dialog"` without the A11Y-101 contract.
- Tying accessibility preferences to `is_youth`.
- Saying "axe" in rules without a gate that fails the build.

## Strengths (summary)

Title drawer focus contract (101); poster card name computation with hidden duplicate link (102); labelled player OSD and input-safe shortcuts (103); login/join form basics (104); Lights Down palette passes AA with margin (105); zoom allowed, `lang="en"`, 44 px phone tap token (106); admin rail semantics (107); reduced-motion-aware Year in Review (108); native text-size radiogroup and stateful theme toggle name (109); inline delete confirmation (110).

## 6–12 month risks

- **Chat cards grow richer** (title cards, bulk confirm, suggested replies) while the transcript stays non-live — the SR gap widens with every feature.
- **Live goes on** for more households: guide grid keyboard model (`LiveGuide.tsx:152` arrow handling) and autoplay-on-tune are untested here.
- **Dialog drift**: each new modal copies the nearest neighbour, and 16 of 18 neighbours are wrong.
- **Material Symbols from Google Fonts** (`index.html` + CSP `font-src` at `projectionist/web/app.py:474`): on an offline LAN the ligature text ("play_circle") renders visibly. Icons are `aria-hidden`, so SR is safe, but sighted users see garbage text.
- **Regression without a gate**: every fix in this report can silently revert.
- **Youth growth**: younger readers and dyslexic kids are the users most hurt by inconsistent labels and long text.

## 90-day direction

| Weeks | Do | IDs |
|---|---|---|
| 1–2 | Token + CSS quick wins: `--accent-ink`, global focus ring, remove `outline:none` from focus rules, `document.title` + route focus, unique accessible names, Escape on KeyboardHelp | 002, 003, 004, 006, 009 (Escape only) |
| 2–4 | CI gates: add `jsx-a11y` to the existing `npm run lint` CI job and make it a required check; `@axe-core/playwright` on 8 routes × 2 themes; 5 keyboard journeys with `toBeFocused` | 005 |
| 4–8 | Chat: keep focus, live completion announcement, labelled composer, message headings. Shared `<Dialog>`; migrate 16 dialogs. Nav drawer focus. | 001, 007, 008, 009, 016, 202 |
| 8–12 | Accessibility preferences (SDH for anyone, caption size, reduce motion, single-key shortcuts off), rail roving tabindex + skip, About digest, youth Help variant. One VoiceOver + one NVDA manual pass on QA `:8792`. | 010, 011, 014, 015, 018, 201, 204 |

## Scorecard

| Dimension | Grade | Note |
|---|---|---|
| Keyboard operability | C− | Reachable, but focus loss, invisible icon focus, drawer order, no bypass |
| Focus management | D | 2/18 dialogs correct; async focus loss; no route focus |
| Semantics & landmarks | C | Good forms/admin rail; brand `h1` on every page; `<main>` missing on ~half of routes |
| Screen-reader experience | D | Chat silent; titles generic; ambiguous names |
| Forms & errors | C | Labels yes; `aria-invalid` 0 uses; status not live |
| Contrast (Lights Down) | A− | All text pairs ≥5.47:1 |
| Contrast (Lights Up) | D | Accent ink 3.04:1 across 103 rules |
| Target size | B | 44 px on phones; a few 21–22 px desktop targets |
| Reflow / zoom / text size | C | Zoom allowed; px root size; 142 px font declarations ignore the setting |
| Media | C+ | Labelled OSD, captions exist; SDH youth-only; no caption styling |
| Motion | B− | Reduced motion widely honoured in CSS; JS smooth scroll ignores it |
| Cognitive | C− | Chat/Ask drift, changelog wall, owner-only copy to members |
| Prevention / tooling | F | No a11y lint rule, no axe; the lint job that runs in CI has no a11y rules and is not a required check |

---

# Part B — Detail

## B.1 Scope and method

**In scope:** all SPA routes in `frontend/src/AppRoutes.tsx`, shared components, styles `frontend/src/styles/01–16`, the Lobby Theater static kiosk (`projectionist/theater/static/`), CI and test config.

**How evidence was gathered**

| Method | What it covers | What it cannot cover |
|---|---|---|
| `git show/grep 94fcd3f` | Structure, ARIA, handlers, CSS rules | Runtime focus order, timing, rendered layout |
| Computed contrast (WCAG 2.x luminance) from `01-tokens.css` | Token pairs, both themes | Text over posters/gradients; `color-mix` with transparency over unknown backgrounds |
| `curl :8792` | SPA shell: all public routes return the identical 2,607-byte shell, `<html lang="en">`, `<title>Projectionist`; served bundle `index-buFnxk8x.js` contains 0 `document.title` | Anything rendered by JS |
| QA screenshots `qa_*.png` | Visual confirmation (admin drawer clipped labels, Help duplicate link, youth Ask/Browse, LLM-unset copy to members) | Focus states, announcements |

**Automated coverage gap (explicit).** No axe/Lighthouse/pa11y run, no screen reader (VoiceOver/NVDA/TalkBack), no 200%/400% zoom, no text-spacing bookmarklet, no forced-colours mode. Live Channels stayed **Off** (desktop off-copy vs phone stall observed; no Live watch). LLM unset. **Play was exercised** (youth allowed + youth R-gate + owner autoplay + end card). Keyboard on Play: Space pauses; Escape does not leave `/watch` (A11Y-023). Anything still marked *Likely* or *Suspected* needs further live confirmation.

**WCAG 2.2 SCs I could not test live:** 1.2.2/1.2.4 (captions on real media), 1.3.4 Orientation, 1.4.3/1.4.11 over imagery, 1.4.4 Resize Text, 1.4.10 Reflow, 1.4.12 Text Spacing, 1.4.13 Content on Hover or Focus, 2.1.1/2.1.2 runtime keyboard traps, 2.2.1 Timing Adjustable (session expiry), 2.2.2 Pause/Stop/Hide (Lobby, Live OSD), 2.4.3 actual focus order, 2.4.7 rendered indicators, 2.4.11 Focus Not Obscured (player OSD, sticky composer), 2.5.7 Dragging Movements (drag-to-dock alternative), 2.5.8 measured target sizes, 3.3.1/3.3.3 live error flows, 3.3.8 Accessible Authentication (local password field allows paste — assumed, not tested), 4.1.3 Status Messages as actually announced.

### Contrast measurements (computed, not estimated)

| Pair | Ratio | AA normal (4.5) | AA large / UI (3.0) |
|---|---|---|---|
| LD `--text #e6e2d6` on `--bg #0d0d0d` | 15.01:1 | Pass | Pass |
| LD `--text` on `--surface-raised #1c2029` | 12.59:1 | Pass | Pass |
| LD `--muted #9a958a` on `--bg` | 6.52:1 | Pass | Pass |
| LD `--muted` on `--surface-raised` | 5.47:1 | Pass | Pass |
| LD `--accent #ffb800` on `--bg` (links, focus ring) | 11.21:1 | Pass | Pass |
| LD `--accent-text #1a1208` on `--accent` (primary button) | 10.68:1 | Pass | Pass |
| LD `--danger #e8918a` on `--surface` | 7.89:1 | Pass | Pass |
| LD `--success #7dba98` on `--surface` | 8.33:1 | Pass | Pass |
| LD `--border #2c313c` on `--surface` (input/card edge) | 1.44:1 | — | **Fail** if it is the only boundary |
| LD composer focus border `mix(accent 45%, border)` = `#8b6e21` on `--surface` | 3.88:1 | — | Pass |
| LU `--text #1b1c19` on `--bg #f9f7f2` | 15.99:1 | Pass | Pass |
| LU `--muted #4d4635` on `--bg` | 8.74:1 | Pass | Pass |
| LU `--accent #b8860b` on `--bg` (links, eyebrows, context tag) | **3.04:1** | **Fail** | Pass (barely) |
| LU `--accent` on `--surface #fbf9f4` / white | 3.09:1 / 3.25:1 | **Fail** | Pass |
| LU `--accent-2 #735c00` on `--bg` | 6.02:1 | Pass | Pass |
| LU `--accent-text` on `--accent` (Sign in button) | 5.69:1 | Pass | Pass |
| LU `--danger #ba1a1a` on `--surface` | 6.14:1 | Pass | Pass |
| LU `--success #2e7d57` on `--surface` | 4.77:1 | Pass | Pass |
| LU `--border #d0c5af` on `--surface` | 1.62:1 | — | **Fail** if only boundary |
| LU composer focus border `#c5a965` on `--surface` | **2.16:1** | — | **Fail** |
| LU episode link focus colour `#e6b422` on `--bg` (`09-title-detail-home.css:2095`) | **1.80:1** | **Fail** | **Fail** |
| Fallback gold `#c4a35a` on LU `--bg` (`10-explore-delight.css:721`) | 2.25:1 | Fail | Fail |
| Explore icon focus: `rgba(10,12,16,.42)` → `.62` over mid-grey poster | **1.43:1** (1.08 over dark, 1.73 over light) | — | **Fail** as focus indicator |
| Active nav marker `--accent-soft` vs bg (LU / LD) | 1.13:1 / 1.29:1 | — | Fail as sole indicator |
| **Proposed** LU `--accent-ink #866200` on `--bg` / white / `--surface-2` | 5.22 / 5.58 / 4.82 | Pass | Pass |
| **Proposed** LD `--muted #a8a397` (AAA 1.4.6) on `--bg` / `--surface` | 7.73 / 7.44 | AAA | — |

---

## B.2 Strengths

### A11Y-101: Protect the title-drawer and ConfirmModal focus contract

| Field | Value |
|---|---|
| Type | Strength |
| Surface | Consumer / Owner |
| Persona(s) | keyboard-only, screen-reader |
| Category | Keyboard |
| Severity | — |
| Impact | 5 |
| Effort | — |
| Confidence | Confirmed |
| Priority score | — (Strength) |
| Verdict | Protect |
| Dependencies | A11Y-202 |
| Labels | 2.1.2, 2.4.3, 4.1.2 |

**Evidence:** `frontend/src/components/TitleDetailDrawer.tsx:99-140` stores `previousFocus`, focuses the Close button (104), handles Escape with a guard for open sub-menus (108-118), and wraps Tab (120-134); `197-199` `role="dialog" aria-modal="true" aria-labelledby`. `frontend/src/components/ConfirmModal.tsx:107-134` focuses a preferred control, traps Tab, restores `previouslyFocused`; `151-153` adds `aria-describedby`.
**Current state:** Correct, tested pattern used by the most-used overlay (title detail).
**Root cause:** Written deliberately once.
**Recommendation:** Extract to `useDialogFocus()` / `<Dialog>` and make every other dialog consume it.
**Rationale:** The fix for A11Y-009 already exists in the codebase.
**User story:** As a keyboard user, when I open a title I land on its Close button and Escape returns me to the poster I came from.
**Acceptance criteria:** Behaviour preserved after extraction; Playwright asserts focus on open and on close.
**Success metric:** 18/18 dialog files use the primitive.
**Validation:** e2e `toBeFocused()` on trigger after Escape.

### A11Y-102: Protect poster-card name computation

| Field | Value |
|---|---|
| Type | Strength |
| Surface | Consumer |
| Persona(s) | screen-reader, keyboard-only |
| Category | Semantics |
| Severity | — |
| Impact | 4 |
| Effort | — |
| Confidence | Confirmed |
| Priority score | — (Strength) |
| Verdict | Protect |
| Dependencies | — |
| Labels | 1.1.1, 2.4.4, 1.3.1 |

**Evidence:** `frontend/src/components/LibraryMediaCard.tsx:57-58` decorative `alt=""` poster; `84-104` duplicate poster link `tabIndex={-1} aria-hidden="true"`; `109-122` the focusable link wraps `<h3>` title + year; `128` card is an `<article>`. `PosterActionMenu.tsx:249` grip named `Actions for ${item.title}`.
**Current state:** One tab stop, one name per title; posters are not double-announced.
**Root cause:** Thoughtful card design.
**Recommendation:** Keep; apply the same `for {title}` suffix to overlay icons (A11Y-006).
**Rationale:** This is the correct "redundant link" pattern.
**User story:** As a SR user I hear "The Thing (1982), heading level 3, link" once per card.
**Acceptance criteria:** No poster image announced; no duplicate link stop.
**Success metric:** axe `link-name`, `image-alt` zero violations on `/explore`.
**Validation:** axe + manual VO rotor Links list.

### A11Y-103: Protect the labelled player OSD and input-safe shortcuts

| Field | Value |
|---|---|
| Type | Strength |
| Surface | Consumer |
| Persona(s) | screen-reader, keyboard-only, motor |
| Category | Media |
| Severity | — |
| Impact | 4 |
| Effort | — |
| Confidence | Confirmed |
| Priority score | — (Strength) |
| Verdict | Protect |
| Dependencies | A11Y-011, A11Y-023 |
| Labels | 4.1.2, 1.2.2, 2.1.1 |

**Evidence:** `frontend/src/components/theater/LibraryPlayerOsd.tsx:137-143` seek `type="range" aria-label="Seek" aria-valuetext={formatClockMs(nowMs)}`; `155-200` buttons named "Skip back 15 seconds", "Pause"/"Play", "Skip forward 15 seconds"; `213` / `253-254` `aria-expanded` + `aria-haspopup="menu"`. `frontend/src/lib/theaterPlayer.ts:518-523` blocks shortcuts in `input/textarea/select/contenteditable`. `SubtitleOverlay.tsx:50` `aria-live="off"` (correct: captions must not spam SR).
**Current state:** Best-labelled control cluster in the app; one shell for Play and Live.
**Root cause:** Player was treated as a product.
**Recommendation:** Keep; add duration to `aria-valuetext` ("12:04 of 1:52:10").
**Rationale:** Shared TheaterPlayer means fixes land once.
**User story:** As a blind viewer I can skip, pause and seek by name.
**Acceptance criteria:** All OSD controls have unique names.
**Success metric:** axe `button-name` zero on `/watch/*`.
**Validation:** QA `:8792` VO pass when Play is exercised.

### A11Y-104: Protect login/join form fundamentals

| Field | Value |
|---|---|
| Type | Strength |
| Surface | Public |
| Persona(s) | screen-reader, cognitive, motor |
| Category | Forms |
| Severity | — |
| Impact | 4 |
| Effort | — |
| Confidence | Confirmed |
| Priority score | — (Strength) |
| Verdict | Protect |
| Dependencies | A11Y-016 |
| Labels | 1.3.1, 1.3.5, 3.3.2, 4.1.3, 3.3.8 |

**Evidence:** `frontend/src/pages/LoginPage.tsx:323-355` real `<form>`, wrapped `<label>`s with visible text "Username"/"Password", `autoComplete="username"` (332) and `"current-password"` (343); `227` errors via `InlineAlert` which is `role="alert"` (`InlineAlert.tsx:11-15`); honeypot hidden from AT (`404-415`, `.hp-field{display:none}` at `15-glass-door.css:123-125`). `GlassDoor.tsx:32` single `<h1>`.
**Current state:** Password managers and SR label computation work; errors are announced.
**Root cause:** —
**Recommendation:** Keep; fix focus loss (A11Y-001) and field association (A11Y-016).
**Rationale:** 1.3.5 and 3.3.8 (no cognitive test, paste-friendly) are satisfied by design.
**User story:** As a user with a password manager I sign in without typing.
**Acceptance criteria:** Autocomplete tokens unchanged.
**Success metric:** —
**Validation:** e2e `login.spec.ts`.

### A11Y-105: Protect the Lights Down palette

| Field | Value |
|---|---|
| Type | Strength |
| Surface | Cross-cutting |
| Persona(s) | low vision |
| Category | Contrast |
| Severity | — |
| Impact | 4 |
| Effort | — |
| Confidence | Confirmed |
| Priority score | — (Strength) |
| Verdict | Protect |
| Dependencies | — |
| Labels | 1.4.3, 1.4.11 |

**Evidence:** `frontend/src/styles/01-tokens.css:71-96`. Computed: text 15.01:1, muted 6.52:1 (5.47:1 on raised), accent 11.21:1, primary button 10.68:1, danger 7.89:1, success 8.33:1. Topbar focus ring `02-nav-chrome.css:353-357` (2px accent, 11.21:1).
**Current state:** AA everywhere for text; near-AAA for body.
**Recommendation:** Keep; for AAA 1.4.6 raise `--muted` to `#a8a397` (7.73:1 / 7.44:1).
**User story:** As a low-vision cinema-mode user I can read every label.
**Acceptance criteria / metric / validation:** Token test asserting ≥4.5:1 for every text pair in both themes (see A11Y-206).

### A11Y-106: Protect zoom, language, and phone target tokens

| Field | Value |
|---|---|
| Type | Strength |
| Surface | Cross-cutting |
| Persona(s) | low vision, motor, screen-reader |
| Category | Target size |
| Severity | — |
| Impact | 3 |
| Effort | — |
| Confidence | Confirmed |
| Priority score | — (Strength) |
| Verdict | Protect |
| Dependencies | — |
| Labels | 1.4.4, 3.1.1, 2.5.8, 2.5.5 |

**Evidence:** `frontend/index.html:2` `<html lang="en">`; `5-8` viewport has no `maximum-scale`/`user-scalable=no`; `01-tokens.css:22-23` `--tap-min: 44px`, `--font-size-input: 16px`; `05-chat-responsive.css:395-413` applies `min-height: var(--tap-min)` to buttons/inputs on phones.
**Recommendation:** Keep; extend `--tap-min` to icon buttons at all widths (A11Y-022).
**User story:** As a user with tremor I can hit buttons on my phone.
**Acceptance criteria / metric / validation:** Playwright mobile project asserts bounding boxes ≥44 px for primary controls.

### A11Y-107: Protect admin rail semantics

| Field | Value |
|---|---|
| Type | Strength |
| Surface | Admin |
| Persona(s) | screen-reader, keyboard-only |
| Category | Semantics |
| Severity | — |
| Impact | 3 |
| Effort | — |
| Confidence | Confirmed |
| Priority score | — (Strength) |
| Verdict | Protect |
| Dependencies | A11Y-007, A11Y-021 |
| Labels | 1.3.1, 2.4.8, 4.1.2 |

**Evidence:** `frontend/src/layouts/AdminLayout.tsx:166` `<nav aria-label="Admin sections">`; `168-173` each group is `<section aria-labelledby>`; `192-199` `NavLink` (React Router sets `aria-current="page"`); `239` `<main>`. `PrimaryTopbar.tsx:149-150` `aria-current` on topbar links.
**Recommendation:** Use this as the template for the hamburger drawer (A11Y-007/021).
**User story:** As an owner using NVDA I hear "Platform, region; Tasks, link, current page".

### A11Y-108: Protect reduced-motion handling in Year in Review and CSS

| Field | Value |
|---|---|
| Type | Strength |
| Surface | Consumer |
| Persona(s) | vestibular, cognitive |
| Category | Motion |
| Severity | — |
| Impact | 3 |
| Effort | — |
| Confidence | Confirmed |
| Priority score | — (Strength) |
| Verdict | Protect |
| Dependencies | A11Y-024 |
| Labels | 2.2.2, 2.3.3 |

**Evidence:** `frontend/src/lib/yearInReview.ts:49-51` `shouldAutoAdvance` returns false when `prefersReducedMotion`; `YearInReviewPage.tsx:19` media query, `99` guard. 16 `prefers-reduced-motion` blocks across 13 stylesheets (e.g. `15-glass-door.css:137-141`, `13-watch.css:530-536`, `10-explore-delight.css:1681-1686`). Lobby kiosk `projectionist/theater/static/theater.css:183`. No auto-advancing Explore rails (no `setInterval` in Explore).
**Recommendation:** Keep; close JS smooth-scroll gap (A11Y-024).

### A11Y-109: Protect the text-size control and stateful theme toggle

| Field | Value |
|---|---|
| Type | Strength |
| Surface | Consumer |
| Persona(s) | low vision, older |
| Category | Forms |
| Severity | — |
| Impact | 3 |
| Effort | — |
| Confidence | Confirmed |
| Priority score | — (Strength) |
| Verdict | Protect |
| Dependencies | A11Y-017 |
| Labels | 1.4.4, 4.1.2 |

**Evidence:** `frontend/src/pages/settings/ProfilePage.tsx:347-372` native radios in `role="radiogroup" aria-label="Text size"`; `PrimaryTopbar.tsx:166` theme button named `Theme: <state>. Click to change.`
**Recommendation:** Keep the control; fix its scale (A11Y-017).

### A11Y-110: Protect inline destructive confirmations

| Field | Value |
|---|---|
| Type | Strength |
| Surface | Consumer / Owner |
| Persona(s) | cognitive, motor |
| Category | Cognitive |
| Severity | — |
| Impact | 3 |
| Effort | — |
| Confidence | Confirmed |
| Priority score | — (Strength) |
| Verdict | Protect |
| Dependencies | A11Y-009 |
| Labels | 3.3.4, 3.3.6 |

**Evidence:** `frontend/src/components/ThreadList.tsx:95-111` Keep/Delete confirm before thread delete; `139` named "Delete conversation <title>". `BulkLibraryDeleteDialog.tsx:134-175` `<fieldset><legend>Removal scope</legend>` with plain-language consequences ("Does not delete Plex files…").
**Recommendation:** Keep; add focus contract to the bulk dialog (A11Y-009).

---

## B.3 Weaknesses (sorted by priority score)

| Rank | ID | Title | Sev | Score |
|---|---|---|---|---|
| 1 | A11Y-001 | Keep focus on the control during async send/submit | High | 6.00 |
| 2 | A11Y-002 | Split Lights Up accent into fill and ink | High | 6.00 |
| 3 | A11Y-003 | Restore visible focus on icons, composer, and border-only rules | High | 6.00 |
| 4 | A11Y-004 | Title every route and announce navigation | High | 6.00 |
| 5 | A11Y-005 | Add accessibility gates to lint, e2e, and CI | High | 6.00 |
| 6 | A11Y-023 | Name the player stage and keep OSD in the accessibility tree | High | 6.00 |
| 7 | A11Y-006 | Make repeated control names unique | Medium | 6.00 |
| 8 | A11Y-007 | Move focus into the hamburger drawer | High | 4.80 |
| 9 | A11Y-008 | Announce chat replies | High | 4.00 |
| 10 | A11Y-009 | Give every dialog the full focus contract | High | 4.00 |
| 11 | A11Y-010 | Add bypass for Explore rails and a skip link | Medium | 4.00 |
| 12 | A11Y-011 | Scope or allow disabling single-key shortcuts | Medium | 3.00 |
| 13 | A11Y-012 | Fix heading and landmark structure | Medium | 3.00 |
| 14 | A11Y-013 | Stop misusing `role="menu"` and prohibited ARIA | Medium | 3.00 |
| 15 | A11Y-014 | Align youth vocabulary across nav and Help | Medium | 3.00 |
| 16 | A11Y-015 | Remove the full changelog from the About DOM | Medium | 3.00 |
| 17 | A11Y-016 | Associate errors and labels with fields | Medium | 2.00 |
| 18 | A11Y-017 | Make text size relative and honoured | Medium | 2.00 |
| 19 | A11Y-018 | Decouple SDH captions from the youth flag | Medium | 2.00 |
| 20 | A11Y-019 | Expose current state without colour alone | Low | 2.00 |
| 21 | A11Y-020 | Stop showing owner-only fixes to members | Low | 2.00 |
| 22 | A11Y-021 | Fix clipped vertical admin group labels | Low | 2.00 |
| 23 | A11Y-022 | Raise sub-24 px targets | Low | 1.60 |
| 24 | A11Y-024 | Honour reduced motion in JS scrolling | Low | 1.00 |
| 25 | A11Y-025 | Support forced-colours mode | Low | 0.80 |
| 26 | A11Y-026 | Reflow wide list/table views at 320 px | Low | 0.53 |

### A11Y-001: Keep focus on the control during async send/submit

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Consumer / Public |
| Persona(s) | screen-reader, keyboard-only, cognitive |
| Category | Keyboard |
| Severity | High |
| Impact | 5 |
| Effort | S |
| Confidence | Likely |
| Priority score | 6.00 |
| Verdict | Fix |
| Dependencies | A11Y-008 |
| Labels | 2.4.3, 2.1.1, 3.2.1 |

**Evidence:**
- Chat composer: `frontend/src/components/ChatWorkspace.tsx:607` `disabled={loading || !threadsReady}` on the `<textarea>` that the user just pressed Enter in (`592-595`). `frontend/src/hooks/useChatSession.ts:775-780` `sendMessage` → `setLoading(true)`. The only `composerRef.current?.focus()` calls are for chip prefill and slash palette (`useChatSession.ts:765, 772`) — **never after a reply completes**.
- Login: `frontend/src/pages/LoginPage.tsx:333, 344, 351` inputs and submit button `disabled={loading …}`; `152-168` `handleLocalLogin` sets `loading` true before the request.
- "Need an invite?": `LoginPage.tsx:362-370` the button is replaced (unmounted) by the request form on click — the focused element disappears.
**Current state:** Disabling (or unmounting) the focused element blurs it; Chromium/WebKit move `document.activeElement` to `<body>`. After the reply, the keyboard user is at the top of the document; the SR virtual cursor is wherever the browser left it.
**Root cause:** Busy state modelled as `disabled` for visual feedback.
**Recommendation:**
- Composer: keep the textarea enabled; block submit in the handler (`canSubmit` already exists at `591`) and set `aria-busy="true"` on the form. If a disabled look is required, use `aria-disabled="true"` + `readOnly` only on the Send button, never on the textarea.
- Login: use `aria-disabled="true"` on the submit button and guard `handleLocalLogin` with `if (loading) return;`. On error, move focus to the first field and `select()` the password.
- Need an invite?: after `setShowRequest(true)`, focus the `<h2>` "Request access" (`tabIndex={-1}`) or the "Your name" input via ref in a `useEffect`.
**Rationale:** Focus loss is the single most disorienting failure for SR and keyboard users; it repeats on every chat turn.
**User story:** As a keyboard user, after I send a message I can type my follow-up without hunting for the composer.
**Acceptance criteria:** After Enter in composer, `document.activeElement` is the composer at send, during stream, and after completion. After a failed login, focus is on Username or Password. After "Need an invite?", focus is inside the revealed form.
**Success metric:** 0 focus-to-body transitions in the five keyboard journeys (A11Y-005).
**Validation:** Playwright `await expect(page.getByTestId("composer-input")).toBeFocused()` after send and after the mocked SSE completes; same for login error.

### A11Y-002: Split Lights Up accent into fill and ink

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Cross-cutting |
| Persona(s) | low vision, older, colour-vision deficiency |
| Category | Contrast |
| Severity | High |
| Impact | 4 |
| Effort | S |
| Confidence | Confirmed |
| Priority score | 6.00 |
| Verdict | Fix |
| Dependencies | — |
| Labels | 1.4.3, 1.4.11, 1.4.6 (AAA) |

**Evidence:** `frontend/src/styles/01-tokens.css:108` LU `--accent: #b8860b`; `194-196` global `a { color: var(--accent); }`; 103 declarations of `color: var(--accent)` across `frontend/src` (e.g. `04-config-onboarding.css:872-875` the chat "General Exploration" context tag, `05-chat-responsive.css:643-653` `.login-secondary-link`). `09-title-detail-home.css:2093-2098` episode link hover/focus `#e6b422`. Default theme is `system` (`index.html:36-44`), so light-OS users get Lights Up. Screenshots `qa_login_local_1440.png`, `qa_owner_chat_1440.png` show the amber context tag and links on paper.
**Current state (computed):** `#b8860b` on `#f9f7f2` = **3.04:1**; on `#fbf9f4` 3.09:1; on white 3.25:1; `#e6b422` on `#f9f7f2` = **1.80:1**. All below 4.5:1 for body-size text.
**Root cause:** One token serves fill (buttons, focus ring) and ink (links, labels).
**Recommendation:** In `html[data-theme="lights-up"]` add `--accent-ink: #866200;` (5.22:1 on bg, 5.58:1 on white, 4.82:1 on `--surface-2`). Set `a { color: var(--accent-ink, var(--accent)); }` and replace text uses of `var(--accent)` with `var(--accent-ink)`; in Lights Down `--accent-ink: var(--accent)`. Replace `#e6b422` with `var(--accent-ink)` and keep `text-decoration: underline`. Keep `#b8860b` for fills (Sign in button 5.69:1 with `--accent-text`).
**Rationale:** One-token fix, brand fill unchanged.
**User story:** As a low-vision reader in daylight I can read the Help and Privacy links on the sign-in page.
**Acceptance criteria:** Every text colour/background pair in LU ≥4.5:1 (≥3:1 for ≥24 px or ≥18.66 px bold).
**Success metric:** axe `color-contrast` = 0 on 8 routes in Lights Up.
**Validation:** A11Y-206 token test + axe with `colorScheme: "light"`.

### A11Y-003: Restore visible focus on icons, composer, and border-only rules

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Consumer / Admin |
| Persona(s) | keyboard-only, low vision, switch users |
| Category | Keyboard |
| Severity | High |
| Impact | 4 |
| Effort | S |
| Confidence | Confirmed |
| Priority score | 6.00 |
| Verdict | Fix |
| Dependencies | A11Y-002 |
| Labels | 2.4.7, 1.4.11, 2.4.13 (AAA) |

**Evidence:**
- `frontend/src/styles/10-explore-delight.css:488-492` `.explore-hover-icon:focus-visible { background: rgba(10,12,16,.62); outline: none; }` vs resting `.42` (`387-403`) — computed 1.08–1.73:1 change over posters. These are the Play / Trailer / Watch together icons on every poster.
- `02-nav-chrome.css:1893-1900` composer `textarea:focus { outline: none }` and `.composer-chrome:focus-within` border = `#c5a965` on `#fbf9f4` = **2.16:1** in LU (3.88:1 LD).
- Other `outline: none` inside focus rules: `10-explore-delight.css:28-33` (`.explore-hub-guide`), `1583-1588` (`.section-help-trigger`), `06-reading-admin-settings.css:1098-1102` (`.apprise-scheme-card`), `09-title-detail-home.css:2093-2098` (1.80:1 colour), `02-nav-chrome.css:2489-2495` box-shadow at 45% alpha, `12-live.css:938-942`.
**Current state:** Focus is visible on topbar and admin; near-invisible on the most-used consumer controls.
**Root cause:** Hover and focus styles share one rule; outline removed for aesthetics.
**Recommendation:** Add once in `01-tokens.css`:

```css
:root { --focus-ring: var(--accent); }
html[data-theme="lights-up"] { --focus-ring: #866200; } /* 5.22:1 on bg */
:where(a, button, [role="button"], input, select, textarea, summary, [tabindex]):focus-visible {
  outline: 2px solid var(--focus-ring);
  outline-offset: 2px;
}
.explore-hover-icon:focus-visible { outline: 2px solid #fff; outline-offset: 2px; box-shadow: 0 0 0 4px #000; }
.composer-chrome:focus-within { outline: 2px solid var(--focus-ring); outline-offset: 2px; }
```

Delete `outline: none` from the seven focus rules above. The double white/black ring on poster icons guarantees ≥3:1 against any poster.
**Rationale:** 2.4.7 requires a visible indicator; 2.4.13 (AAA) asks for ≥2 px and 3:1 change — this meets both.
**User story:** As a keyboard user on Explore I can see which poster action I am on.
**Acceptance criteria:** Every focusable element shows a ≥2 px outline with ≥3:1 contrast vs adjacent colours in both themes.
**Success metric:** 0 `outline: none` in `:focus`/`:focus-visible` rules (stylelint rule).
**Validation:** Playwright screenshot diff of focused states; `stylelint` `declaration-property-value-disallowed-list` for outline none in focus selectors.

### A11Y-004: Title every route and announce navigation

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Cross-cutting |
| Persona(s) | screen-reader, cognitive, multi-tab users |
| Category | SR |
| Severity | High |
| Impact | 4 |
| Effort | S |
| Confidence | Confirmed |
| Priority score | 6.00 |
| Verdict | Fix |
| Dependencies | A11Y-012 |
| Labels | 2.4.2, 4.1.3, 2.4.3 |

**Evidence:** `frontend/index.html:57` `<title>Projectionist</title>`; `git grep document.title 94fcd3f -- frontend/src` → 0 results; live `:8792` bundle `index-buFnxk8x.js` contains 0 `document.title`; `/login`, `/help`, `/about`, `/privacy`, `/join` return the identical 2,607-byte shell. No route-change focus in `frontend/src/layouts/*` or `App.tsx` (no `.focus()` on navigation).
**Current state:** Every tab, history entry and SR "page loaded" announcement says "Projectionist". Client-side navigation is silent.
**Root cause:** SPA without a route announcer.
**Recommendation:** Add `usePageTitle(title)` called from `AppShell`, `AdminLayout`, `SettingsLayout`, `GlassDoor`: `document.title = \`${title} · Projectionist\``. On `location.pathname` change (not hash), focus the page `<h1>` (`tabIndex={-1}`) or a visually hidden `<p role="status">Navigated to {title}</p>`. Title detail: `"<Title> (<year>) · Projectionist"`.
**Rationale:** Level A; cheap; unlocks history and tab switching for everyone.
**User story:** As a SR user, when I open Help I hear "Help · Projectionist".
**Acceptance criteria:** Unique title on every route in `AppRoutes.tsx`; focus lands on `h1` after nav.
**Success metric:** Playwright asserts `page.title()` per route.
**Validation:** e2e loop over routes; VO announcement check.

### A11Y-005: Add accessibility gates to lint, e2e, and CI

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Cross-cutting |
| Persona(s) | all |
| Category | Tooling |
| Severity | High |
| Impact | 4 |
| Effort | S |
| Confidence | Confirmed |
| Priority score | 6.00 |
| Verdict | Add |
| Dependencies | — |
| Labels | process (all SCs) |

**Evidence:** `frontend/package.json` devDependencies have no `eslint-plugin-jsx-a11y`; root `package.json` has only `@playwright/test`; no `axe` anywhere in `e2e/`, `package.json`, `.github`. `frontend/eslint.config.js:15-119` no a11y plugin. `.github/workflows/ci.yml:36-49` runs build, `test:unit`, `test:e2e`. `npm run lint` runs in a separate workflow (`.github/workflows/lint.yml:32-47`, job "Frontend (eslint + prettier)"), but the ESLint config has no a11y plugin and no workflow is a required check (ARCH-007). `.cursor/rules/ui-testing-architecture.mdc:40` "axe-core … **Not a CI job today**"; `:65` scopes axe to "Lights Down contrast". e2e: 52 `getByRole/getByLabel` vs 484 test-id references, 3 `keyboard.press`, 0 `toBeFocused`.
**Current state:** No automated signal for any finding in this report.
**Root cause:** A11y treated as manual/advisory.
**Recommendation (exact):**
1. `cd frontend && npm i -D eslint-plugin-jsx-a11y`; in `eslint.config.js` add `import jsxA11y from "eslint-plugin-jsx-a11y";` and a block `{ files: ["**/*.{jsx,tsx}"], ...jsxA11y.flatConfigs.recommended }` before `prettier`. Start with `"jsx-a11y/no-autofocus": "warn"`, everything else `error`.
2. Make the existing `Frontend (eslint + prettier)` job in `.github/workflows/lint.yml` a required status check so the new `jsx-a11y` errors block merges.
3. `npm i -D @axe-core/playwright` at root; add `e2e/a11y.spec.ts` that loops `/login`, `/join`, `/help`, `/about`, `/privacy`, `/chat`, `/explore`, `/admin` × `colorScheme: "dark" | "light"` (set `localStorage["projectionist.ui_theme"]` before load), running `new AxeBuilder({ page }).withTags(["wcag2a","wcag2aa","wcag21a","wcag21aa","wcag22aa"]).analyze()` and expecting `violations` to equal a checked-in baseline (shrink-only).
4. Root `package.json`: `"test:a11y": "playwright test e2e/a11y.spec.ts"`; frontend: `"lint:a11y": "eslint src --rule 'jsx-a11y/*: error'"` optional.
5. Add `e2e/keyboard-journeys.spec.ts`: login, chat send, explore → open title → Escape, nav drawer, `?` help → Escape — each with `toBeFocused()`.
6. Update `ui-testing-architecture.mdc` to WCAG 2.2 AA and both themes.
**User story:** As a maintainer I learn about a missing label in the PR, not from a household member.
**Acceptance criteria:** CI fails on new jsx-a11y errors and new axe violations.
**Success metric:** Baseline violations trend to 0 within 90 days.
**Validation:** Deliberately remove an `aria-label` in a test PR; CI must fail.

### A11Y-006: Make repeated control names unique

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Consumer / Public |
| Persona(s) | screen-reader, voice control |
| Category | SR |
| Severity | Medium |
| Impact | 3 |
| Effort | XS |
| Confidence | Confirmed |
| Priority score | 6.00 |
| Verdict | Fix |
| Dependencies | — |
| Labels | 2.4.4, 2.4.6, 2.5.3, 2.4.9 (AAA) |

**Evidence:** `frontend/src/components/PosterOverlayControls.tsx:118` `aria-label="Play"`, `141` `"Trailer"`, `155` `"Watch together"` — identical on every poster. `LibraryMediaCard.tsx:169` "Why?" per card. `HelpPage.tsx:218` `<a href="#related-titles">Related titles</a>` and `239` `<Link to={ROUTES.relatedTitles}>Related titles</Link>` — same name, different destinations (visible in `qa_help_guest_1440.png`). `ThreadList.tsx:139` "Delete conversation New conversation" repeated for unnamed threads (`qa_owner_chat_1440.png`).
**Current state:** SR Links/Buttons list shows 20× "Play".
**Recommendation:** `aria-label={\`Play ${item.title}\`}`, `\`Trailer for ${item.title}\``, `\`Watch ${item.title} together\``, "Why this pick: {title}". Help: rename 218 to "Related titles (guide)" and 239 to "Open Related titles". Thread delete: append relative time ("…New conversation, 70 days ago"). Keep visible text as is; names must *contain* the visible label for 2.5.3 (icons have none, so free).
**User story:** As a VoiceOver user scanning links I know which film "Play" will start.
**Acceptance criteria:** No two controls on one page share a name with different targets.
**Success metric:** axe `identical-links-same-purpose` (best-practice) 0.
**Validation:** VO rotor.

### A11Y-007: Move focus into the hamburger drawer

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Consumer / Admin |
| Persona(s) | keyboard-only, screen-reader |
| Category | Keyboard |
| Severity | High |
| Impact | 4 |
| Effort | S |
| Confidence | Likely |
| Priority score | 4.80 |
| Verdict | Fix |
| Dependencies | A11Y-202 |
| Labels | 2.4.3, 2.1.1, 1.3.1, 4.1.2 |

**Evidence:** `frontend/src/components/AppNav.tsx:176-207` drawer is `createPortal(..., document.body)` — appended after the whole app; `51-57` `useAnchoredPopover({ closeOnEscape: true })` which only handles outside-click/Escape (`hooks/useAnchoredPopover.ts:73-90`) — no focus move, no trap, no restore; `178-184` first child is a full-screen backdrop **button** "Close navigation"; `217-228` toggle has `aria-expanded` but no `aria-controls`; `104-111` active link class-only (no `aria-current`). Screenshots `qa_youth_nav_1440.png`, `qa_owner_admin_nav_1440.png` show the drawer is the nav path at 1440.
**Current state (predicted):** Enter on "Open navigation menu" → drawer appears, focus stays on the toggle; Tab walks through the entire page behind the drawer before reaching it.
**Root cause:** Drawer built as a popover, not a modal.
**Recommendation:** On open, focus the first link (or the Close button); trap Tab within `.app-nav-drawer`; mark the app root `inert` while open; on close, restore focus to `AppNavToggle`. Add `aria-controls="app-nav-drawer"` + `id`. Remove the backdrop from the tab order (`tabIndex={-1}`, `aria-hidden="true"`) — Escape and the ✕ already close it. Add `aria-current="page"` when `active`.
**User story:** As a keyboard owner I open the menu and press Tab once to reach "Tasks".
**Acceptance criteria:** First Tab after open lands inside the drawer; Escape returns focus to toggle.
**Success metric:** Keyboard journey test passes.
**Validation:** Playwright `toBeFocused`.

### A11Y-008: Announce chat replies

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Consumer |
| Persona(s) | screen-reader, youth |
| Category | SR |
| Severity | High |
| Impact | 5 |
| Effort | M |
| Confidence | Likely |
| Priority score | 4.00 |
| Verdict | Fix |
| Dependencies | A11Y-001 |
| Labels | 4.1.3, 1.3.1 |

**Evidence:** `frontend/src/components/ChatThread.tsx:483-498` transcript is plain `<div className="chat-thread">` / `<div className="message …">` — no `role="log"`, no `aria-live`, no per-message heading; user messages have no "You said" label (only assistant gets `message-agent-name` at `500-503`). `ChatWorkspace.tsx:430` scroll region has no role. Only live region is `TypingIndicator.tsx:82-93` — `aria-live="polite"` on an element that is also `role="button"`, which announces "Curator is thinking" but not the reply. `git grep` finds 57 `aria-live`/`role=status|alert|log` uses in the app, none on the transcript.
**Current state (predicted):** SR user sends, hears "Curator… thinking" (maybe), then silence. Must navigate blind to find the new message.
**Root cause:** Streaming token updates are noisy, so nothing was made live.
**Recommendation:** Keep the transcript non-live (streaming would spam). Add a separate visually hidden `<div role="status" aria-live="polite" aria-atomic="true">` and set its text **once on stream completion**: `"${curatorName} replied: ${firstSentence}. ${n} titles."`. Wrap each message in `<article aria-labelledby>` with an `h2.sr-only` "You" / "Curator" so H-key navigation jumps turns. Move `aria-live` off the `role="button"` TypingIndicator into a sibling status node. Add a "Skip to latest reply" link before the composer.
**User story:** As a blind household member I hear the curator's answer begin without leaving the composer.
**Acceptance criteria:** One polite announcement per completed reply; none per token; errors via `role="alert"` (already in `InlineAlert`).
**Success metric:** VO/NVDA test script passes 5/5 turns.
**Validation:** Playwright asserts status node text after mocked SSE; manual VO on `:8792` (LLM unset gives canned replies — still testable).

### A11Y-009: Give every dialog the full focus contract

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Cross-cutting |
| Persona(s) | keyboard-only, screen-reader |
| Category | Keyboard |
| Severity | High |
| Impact | 4 |
| Effort | M |
| Confidence | Confirmed |
| Priority score | 4.00 |
| Verdict | Fix |
| Dependencies | A11Y-101, A11Y-202 |
| Labels | 2.1.2, 2.4.3, 4.1.2, 1.3.1 |

**Evidence:** 19 `role="dialog"` in 18 files. Full contract only in `TitleDetailDrawer.tsx:99-140` and `ConfirmModal.tsx:107-134`; Escape-only in `TitleReviewModal.tsx:30`. No focus move/trap/restore/Escape in: `KeyboardHelpModal.tsx:26-38` (and `App.tsx:282` `overlayOpen` excludes `keyboardHelpOpen`, so **Escape does not close the `?` help**), `WhatsNewModal.tsx:17-28` (shown on `/login` per sacred cow #21), `RecommendModal.tsx:127`, `BulkLibraryDeleteDialog.tsx:96-109`, `ReportMediaIssueModal.tsx:54`, `PosterOverlayControls.tsx:176-190` (trailer, autoplaying YouTube iframe, not portaled), `TurnstyleResultsOverlay.tsx:57` (Escape via shortcuts hook only on chat). No shared trap utility (`git grep useFocusTrap|inert` → none).
**Current state:** `aria-modal="true"` tells AT the rest is inert while focus remains behind the dialog — the worst combination.
**Recommendation:** Ship `<Dialog>` (A11Y-202) on native `<dialog>.showModal()`; until then, wrap each in the A11Y-101 hook. Immediate XS fix: add `keyboardHelpOpen` to `overlayOpen` in `App.tsx:282` and close it in `onCloseOverlay`.
**User story:** As a keyboard user I press `?`, read the shortcuts, press Escape, and I'm back where I was.
**Acceptance criteria:** For each dialog: focus moves in on open, Tab cycles inside, Escape closes (unless destructive op running), focus returns to trigger.
**Success metric:** 18/18 dialog files.
**Validation:** Parametrised Playwright test per dialog.

### A11Y-010: Add bypass for Explore rails and a skip link

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Consumer |
| Persona(s) | keyboard-only, switch, motor |
| Category | Keyboard |
| Severity | Medium |
| Impact | 4 |
| Effort | S |
| Confidence | Confirmed |
| Priority score | 4.00 |
| Verdict | Fix |
| Dependencies | A11Y-204 |
| Labels | 2.4.1, 2.1.1 |

**Evidence:** `git grep -i "skip-link|skip to|#main-content" 94fcd3f -- frontend` → none. Per card tab stops: title link (`LibraryMediaCard.tsx:119`), Play (`PosterOverlayControls.tsx:114`), Actions grip (`PosterActionMenu.tsx:249`), Trailer (`136`), Watch together (`151`, multi-user), plus optional seed/Why? (`LibraryMediaCard.tsx:150-170`) = 4–7. Explore shows ~10+ rails (`qa_owner_explore_1440.png`, platform map §4). Rails use `h2` (`ExplorePage.tsx:106`) — good for SR, no help for keyboard.
**Current state:** Hundreds of Tab presses to reach the last shelf or the footer.
**Recommendation:** Add a first-focusable "Skip to main content" link in `PrimaryTopbar` targeting each layout's `<main id="main">`. Per rail, add a visually-hidden-until-focus "Skip to next shelf" link after the `h2`. Medium term: roving tabindex (A11Y-204).
**User story:** As a switch user I can jump from For you to Recently Added in one action.
**Acceptance criteria:** Skip link is first Tab stop on every authenticated page and visible on focus.
**Success metric:** Tab presses to reach rail N+1 ≤ 2.
**Validation:** Playwright count of Tab presses.

### A11Y-011: Scope or allow disabling single-key shortcuts

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Consumer |
| Persona(s) | speech-input, keyboard-only, motor (tremor) |
| Category | Keyboard |
| Severity | Medium |
| Impact | 3 |
| Effort | S |
| Confidence | Confirmed |
| Priority score | 3.00 |
| Verdict | Fix |
| Dependencies | A11Y-201 |
| Labels | 2.1.4, 2.1.1 |

**Evidence:** `frontend/src/hooks/useKeyboardShortcuts.ts:34-38` `?` and `46-49` `/` on `window`; correctly skipped in `input`/`textarea`/contenteditable (`3-7`) — **they do not steal keys while typing** — but `select` and ARIA widgets (e.g. combobox in `InvestigateShowCombobox.tsx`) are not excluded. `40-44` `Cmd/Ctrl+N` fires **even in editable fields** and overrides the browser's New Window. Play: `LibraryPlayer.tsx:741-750` window-level listener dispatching `theaterPlayer.ts:505-515` keys Space/K/S, J/A/←, L/D/→ whenever focus is **outside** the player — `isPlayShortcutBlockedTarget` (`518-523`) does not exclude buttons/links, so Space on a focused "Back" button or OSD-adjacent link toggles playback instead of activating it. No setting turns any of these off.
**Current state:** Fails 2.1.4 (no off/remap, not focus-scoped). Speech users saying "slash" or "ess" trigger actions.
**Recommendation:** Add a "Single-key shortcuts" toggle in Settings (default on), honoured by both hooks. Exclude `select`, `[role=combobox|listbox|menu|slider|grid]`, `button`, `a` from window-level Play keys (Space/Enter must activate the focused control). Require `!inEditable` for Cmd/Ctrl+N or move it to `Alt+Shift+N`.
**User story:** As a Dragon user I can turn single-letter shortcuts off.
**Acceptance criteria:** Toggle off → no action on `?`, `/`, letters; Space on a focused button activates that button on `/watch`.
**Success metric:** —
**Validation:** Unit tests on `isEditableTarget` / `isPlayShortcutBlockedTarget`.

### A11Y-012: Fix heading and landmark structure

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Cross-cutting |
| Persona(s) | screen-reader |
| Category | Semantics |
| Severity | Medium |
| Impact | 3 |
| Effort | S |
| Confidence | Confirmed |
| Priority score | 3.00 |
| Verdict | Fix |
| Dependencies | A11Y-004 |
| Labels | 1.3.1, 2.4.6, 2.4.10 (AAA) |

**Evidence:** `frontend/src/components/ProjectionistBrand.tsx:59-70` the topbar wordmark is an `<h1>` inside a link on every page using `PrimaryTopbar` — so admin has three `h1`s ("Projectionist", `AdminLayout.tsx:164` "Admin", `ConfigPage.tsx:1965` section) and Settings two. Chat's visual heading "Good to meet you — I'm Curator…" is a `<p>` (`WelcomePanel.tsx:33`). `<main>` exists in only 16 files; absent from `GlassDoor.tsx:24-38` (login/join/setup), `SearchPage`, `LivePage`, `TitleDetailPage`, `LibraryHubPage`, `LibraryWatchPage`, `ListsPage`. Every Explore rail with type links adds a `<nav>` landmark (`ExplorePage.tsx:120`), producing many "navigation" landmarks.
**Recommendation:** Brand: replace `<h1>` with `<span>`; each page owns one `<h1>`. Chat: render greeting as `<h1>` (or `h1.sr-only` "Chat" + greeting `<p>`). Add `<main id="main">` in `GlassDoor` and `AppShell` (pages that already have `<main>` drop theirs). Replace per-rail `<nav>` with a plain `<div>` or `<ul aria-label>`.
**User story:** As a SR user, pressing `1` takes me to the page's purpose, not the logo.
**Acceptance criteria:** Exactly one `h1` and one `main` per route.
**Success metric:** axe `page-has-heading-one`, `landmark-one-main`, `landmark-unique` = 0.
**Validation:** axe spec (A11Y-005).

### A11Y-013: Stop misusing `role="menu"` and prohibited ARIA

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Consumer / Owner / Admin |
| Persona(s) | screen-reader |
| Category | Semantics |
| Severity | Medium |
| Impact | 3 |
| Effort | S |
| Confidence | Confirmed |
| Priority score | 3.00 |
| Verdict | Rethink |
| Dependencies | A11Y-202 |
| Labels | 4.1.2, 1.3.1 |

**Evidence:** `PosterActionMenu.tsx:205` `role="menu"` whose children are plain links/buttons (`207-235`), zero `menuitem`; portaled to `<body>` (`204`) so it is also far from its trigger in focus order. Same in `ShareActionMenu.tsx:191`, `MediaBrowseControls.tsx:261, 286`. `TitleCtaBar.tsx:160-243` has `menuitem`s but no ArrowUp/Down handling (`git grep ArrowDown` → none in those files). `AppNav.tsx:138-143, 165` `<li role="presentation">` inside `<ul>` breaks list structure. `AppNav.tsx:114-118` and `AdminLayout.tsx:207-211` `aria-label` on a generic `<span>` badge (prohibited in ARIA 1.2; many SRs read just "3"). `TypingIndicator.tsx:84-88` `aria-live` on a `role="button"`.
**Current state:** SR announces "menu" then the user's arrow keys do nothing; owner "Delete from index" (`233`) lives in this unmanaged popover.
**Recommendation:** Convert these popovers to the **disclosure** pattern: trigger `aria-expanded` + `aria-controls`, popover is a `<div>` / `<ul>` of normal buttons/links, focus first item on open, Escape returns focus. Keep real `role="menu"` only where full arrow-key roving is implemented (TitleCtaBar — add it). Badges: `<span aria-hidden="true">3</span><span class="sr-only">, 3 open</span>`. Remove `role="presentation"` from `li`.
**User story:** As a NVDA user, "Actions for Alien" opens a list I can Tab through.
**Acceptance criteria:** axe `aria-required-children`, `aria-prohibited-attr`, `list`, `listitem` = 0.
**Success metric / Validation:** axe spec.

### A11Y-014: Align youth vocabulary across nav and Help

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Consumer |
| Persona(s) | youth, cognitive, screen-reader |
| Category | Cognitive |
| Severity | Medium |
| Impact | 3 |
| Effort | S |
| Confidence | Confirmed |
| Priority score | 3.00 |
| Verdict | Fix |
| Dependencies | — |
| Labels | 3.2.4, 3.2.3, 3.1.5 (AAA) |

**Evidence (fact verified):** `frontend/src/lib/primaryNav.ts:27-41` `youthLabel: "Ask"` / `"Browse"` for chat/explore; applied at `154`. Screenshot `qa_youth_nav_1440.png` shows Ask/Browse. But `HelpPage.tsx:143-153` is role-aware only owner vs not (fact verified: "Help is role-aware" — owner/non-owner only); `204` eyebrow "Chat, Explore, Related titles…"; `217` jump link "Chat"; `205` "Back to chat"; `188-196` youth is labelled "Household member" (or "Guest" before auth, as in `qa_help_guest_1440.png`). `docs/HELP.md` uses "Explore" 25× vs "Ask/Browse" 12× (mostly verbs).
**Current state:** A child told "tap Chat" in Help sees no Chat.
**Recommendation:** Pass `isYouth` into `HelpPage`; apply the same label map to eyebrow, jump nav and Back link; add a short youth preamble ("Ask is where you talk to the curator"). Alternatively drop the rename and keep Chat/Explore for all — consistency beats friendliness.
**User story:** As a 10-year-old, Help uses the same words as my buttons.
**Acceptance criteria:** For youth, no "Chat"/"Explore" nav nouns in Help chrome.
**Success metric:** Unit test on label map.
**Validation:** QA youth account on `:8792`.

### A11Y-015: Remove the full changelog from the About DOM

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Public |
| Persona(s) | screen-reader, keyboard-only, cognitive, low-bandwidth |
| Category | Cognitive |
| Severity | Medium |
| Impact | 3 |
| Effort | S |
| Confidence | Confirmed |
| Priority score | 3.00 |
| Verdict | Remove |
| Dependencies | — |
| Labels | 2.4.1, 2.4.3, 2.4.6, 3.2.2 |

**Evidence (fact verified):** `frontend/src/pages/AboutPage.tsx:110-136` renders `ReleaseNotesPanel` with "Full history from CHANGELOG — newest first"; `CHANGELOG.md` at `94fcd3f` has 272 `## ` releases, 504,167 bytes; `ReleaseNotesPanel.tsx:116-126` one `<article>` + `<h3>` per release, `130` `<h4>Highlights` each. Jump select `80-98` calls `scrollIntoView({behavior:"smooth"})` (`57`) but **does not move focus**, so keyboard/SR users stay on the select. Screenshot `qa_about_1440.png`.
**Current state:** Hundreds of headings in the SR heading list; Tab from the jump chips walks every release's content.
**Recommendation:** Show the latest 5 releases' Highlights only; "Full release history" links to a paged view (or GitHub). On jump, `target.setAttribute("tabindex","-1"); target.focus({preventScroll:true})` and honour reduced motion.
**User story:** As a SR user, About's heading list fits on one screen.
**Acceptance criteria:** ≤5 release articles in default DOM; jump moves focus.
**Success metric:** About DOM node count drop ≥90%.
**Validation:** Playwright count of `.release-notes-version`.

### A11Y-016: Associate errors and labels with fields

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Cross-cutting |
| Persona(s) | screen-reader, cognitive |
| Category | Forms |
| Severity | Medium |
| Impact | 3 |
| Effort | M |
| Confidence | Confirmed |
| Priority score | 2.00 |
| Verdict | Fix |
| Dependencies | A11Y-001 |
| Labels | 3.3.1, 3.3.3, 1.3.1, 4.1.3, 3.3.2 |

**Evidence:** Across `frontend/src` `.tsx`: `aria-invalid` **0**, `aria-describedby` **1** (`ConfirmModal.tsx:153`), `aria-errormessage` 0, `aria-required` 0. Login: `LoginPage.tsx:154-156` empty-field error is a general alert not tied to a field; inputs lack `required`. Access request: `451-458` status `<p>` has no `role` — success/failure not announced; `463` submit `disabled` until name ≥2 chars with no explanation. Chat composer `ChatWorkspace.tsx:543-605` has no `<label>`/`aria-label`; its name comes from a placeholder that changes per persona and becomes "Listening…" during dictation.
**Recommendation:** Field-level errors: `aria-invalid="true"` + `aria-describedby="<id>-error"` on the offending input. Add `required` to Username/Password and Name. Status `<p>` → `role="status"` (success) / `role="alert"` (error). Replace disabled submit with an enabled button that shows "Enter at least 2 characters" on submit. Composer: `aria-label="Message ${curatorName}"`; keep placeholder as a hint.
**User story:** As a SR user, after a failed request I hear why and where.
**Acceptance criteria:** Each form error is programmatically linked to its field.
**Success metric:** jsx-a11y `control-has-associated-label` clean; axe `label` clean without relying on placeholder.
**Validation:** Unit + axe.

### A11Y-017: Make text size relative and honoured

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Cross-cutting |
| Persona(s) | low vision, older, youth |
| Category | Contrast |
| Severity | Medium |
| Impact | 3 |
| Effort | M |
| Confidence | Confirmed |
| Priority score | 2.00 |
| Verdict | Rethink |
| Dependencies | A11Y-109 |
| Labels | 1.4.4, 1.4.12, 1.4.8 (AAA) |

**Evidence:** `frontend/src/lib/uiPrefs.ts:2-6` `small 13px / medium 15px / large 17px`, applied to `:root` (`18-25`; `01-tokens.css:29, 66`) — overrides the user's browser default (usually 16 px), so "Medium" is *smaller* than default and "Large" is only +13%. 142 `font-size: …px` declarations ignore the setting; 27 are under 12 px (e.g. `02-nav-chrome.css:392` 10 px); 17 rem values under 0.75rem (e.g. `12-live.css:785` 0.62rem ≈ 9.3 px at medium, 8.1 px at small).
**Recommendation:** Map to percentages of the user default: `small 93.75%`, `medium 100%`, `large 118.75%`, add `x-large 137.5%`. Convert px font sizes to rem (codemod), floor at `0.75rem`. Live guide micro-labels → `0.75rem`.
**User story:** As a grandparent on the iPad, "Large" actually makes everything larger.
**Acceptance criteria:** No px font sizes in `frontend/src/styles`; Large ≥ 1.18× browser default.
**Success metric:** stylelint `unit-disallowed-list: ["px"]` for `font-size`.
**Validation:** 200% zoom + Large on QA; screenshot review.

### A11Y-018: Decouple SDH captions from the youth flag

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Consumer |
| Persona(s) | Deaf / hard of hearing, non-native language, youth |
| Category | Media |
| Severity | Medium |
| Impact | 3 |
| Effort | M |
| Confidence | Confirmed |
| Priority score | 2.00 |
| Verdict | Rethink |
| Dependencies | A11Y-201 |
| Labels | 1.2.2, 1.2.4 (Live) |

**Evidence (fact verified):** `projectionist/web/library_routes.py:650` `prefer_sdh = bool(getattr(user, "is_youth", False))`; same in `projectionist/web/live_channels_routes.py:1568`; `projectionist/library/subtitles.py:178-188` prefers hearing-impaired when flag set. `SubtitleOverlay.tsx:28-54` custom overlay with no user styling (size, background, position). Captions are toggled per session (`LibraryPlayer.tsx:1180-1183`); no persisted "always captions on".
**Current state:** A Deaf adult member cannot request SDH or persist captions; only children get SDH preference.
**Recommendation:** Add per-user prefs `captions_default: off|on`, `captions_prefer_sdh: bool` (default true for youth), `captions_size: S|M|L|XL`, `captions_background: none|translucent|solid`. Server reads `user.captions_prefer_sdh` instead of `is_youth`.
**User story:** As a hard-of-hearing member, every film starts with SDH captions in a large size.
**Acceptance criteria:** Prefs persist and apply to Play and Live.
**Success metric:** —
**Validation:** API test + QA Play.

### A11Y-019: Expose current state without colour alone

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Consumer |
| Persona(s) | screen-reader, colour-vision deficiency |
| Category | Semantics |
| Severity | Low |
| Impact | 2 |
| Effort | XS |
| Confidence | Confirmed |
| Priority score | 2.00 |
| Verdict | Fix |
| Dependencies | — |
| Labels | 1.4.1, 1.3.1, 4.1.2 |

**Evidence:** `ThreadList.tsx:115-118` active thread = `className="active"` only (gold left bar in `qa_owner_chat_1440.png`); `AppNav.tsx:104-111` `is-active` only; active nav marker `--accent-soft` is 1.13:1 (LU) / 1.29:1 (LD) vs background.
**Recommendation:** `aria-current="true"` on active thread button; `aria-current="page"` on drawer links; keep the bar but ensure it is ≥3:1 (use `--accent` fill, 3.04:1 LU / 11.21:1 LD).
**User story:** As a SR user I know which conversation is open.
**Acceptance criteria / Validation:** axe + DOM assertion.

### A11Y-020: Stop showing owner-only fixes to members

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Consumer |
| Persona(s) | cognitive, youth |
| Category | Cognitive |
| Severity | Low |
| Impact | 2 |
| Effort | XS |
| Confidence | Confirmed |
| Priority score | 2.00 |
| Verdict | Fix |
| Dependencies | — |
| Labels | 3.3.3, 3.1.5 (AAA) |

**Evidence (fact verified: LLM unset):** `projectionist/agent/curator.py:414` "Here's what I found in your library. Configure an LLM provider for richer conversation." shown to members (`qa_member_chat_390.png`) and youth.
**Recommendation:** Role-aware copy: members/youth → "I'm in simple mode right now — ask your household owner to turn on full conversation."; owners keep the config hint with a link.
**User story:** As a member I am not told to do something I can't.
**Acceptance criteria / Validation:** Unit test on role branch.

### A11Y-021: Fix clipped vertical admin group labels

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Admin |
| Persona(s) | low vision, cognitive, screen-reader |
| Category | Cognitive |
| Severity | Low |
| Impact | 2 |
| Effort | XS |
| Confidence | Confirmed |
| Priority score | 2.00 |
| Verdict | Fix |
| Dependencies | A11Y-007 |
| Labels | 1.4.10, 1.4.12, 1.3.1 |

**Evidence:** `frontend/src/styles/02-nav-chrome.css:126-140` `.app-nav-heading-side { writing-mode: vertical-rl; transform: rotate(180deg); font-size: .78rem; line-height: 1.05 }`; screenshot `qa_owner_admin_nav_1440.png` shows "PLATFORM" and a clipped "MUNICATIONS". Group labels are `<p>` (`AppNav.tsx:146-151`) not headings, and the nested `<ul>` has no accessible name.
**Recommendation:** Horizontal eyebrow text; render as `<h2 class="app-nav-heading" id>` and `aria-labelledby` on the nested `<ul>` (copy `AdminLayout.tsx:168-183`).
**User story:** As an owner at 200% zoom I can read "Communications".
**Acceptance criteria / Validation:** Screenshot at 200%; axe.

### A11Y-022: Raise sub-24 px targets

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Cross-cutting |
| Persona(s) | motor, tremor, touch |
| Category | Target size |
| Severity | Low |
| Impact | 2 |
| Effort | XS |
| Confidence | Likely |
| Priority score | 1.60 |
| Verdict | Fix |
| Dependencies | A11Y-017 |
| Labels | 2.5.8, 2.5.5 (AAA) |

**Evidence:** `04-config-onboarding.css:1072-1078` `.inline-alert-dismiss` 18 px glyph + 2 px padding ≈ **22 px** tall; `10-explore-delight.css:1569-1572` `.section-help-trigger` 1.4rem = **21 px** at medium, 18.2 px at small; `.explore-hover-icon` 1.85rem = 27.8 px (24.1 px at small — passes by 0.1). Poster grip 30 px (`03-browse-controls.css:255-258`), reactions 32 px (`02-nav-chrome.css:2395-2401`) pass.
**Recommendation:** `min-width/min-height: 24px` (AA) on all icon buttons at desktop; `var(--tap-min)` (44 px, AAA) on touch.
**Acceptance criteria / Validation:** Playwright bounding-box check.

### A11Y-023: Name the player stage and keep OSD visible with focus

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Consumer |
| Persona(s) | screen-reader, keyboard-only |
| Category | Media |
| Severity | High |
| Impact | 4 |
| Effort | S |
| Confidence | Confirmed |
| Priority score | 6.00 |
| Verdict | Fix |
| Dependencies | A11Y-103 |
| Labels | 4.1.2, 2.4.11, 2.2.1 |

**Evidence:** `frontend/src/components/theater/TheaterPlayer.tsx:738-749` root `<div tabIndex={0}>` with no role or name; `871-873` the OSD root is `aria-hidden={!osdVisible}`. Live 2026-10-29: youth `/watch/182044` (Mister Rogers playing, `readyState` 4, blob src) and owner `/watch/84250` (Don't Look Up autoplay). After chrome idled, the accessibility tree was **one generic**; `.theater-osd` was `aria-hidden="true"` and `visibility: hidden`; **Escape left the URL on `/watch`**. Space paused (small center Play glyph). A click on the video restored named controls: Seek, Skip back 30/15, Play, Skip forward 15/30, CC, Shrink, Fullscreen, Close, More. Hold-to-rate (`750-773`) still has no confirmed keyboard path.
**Recommendation:** Never set `aria-hidden` on a focused control's ancestor. Keep the OSD in the accessibility tree while it contains focus, and keep it visible for `:focus-within`. Name the stage with `role="region"` and an accessible name of the title plus "player". Escape closes the player and returns to the title. The seek slider exposes "X of Y".
**Validation:** On `:8792`, start Play, wait for the chrome to hide, press Tab: focus must land on Play or Close, and Escape must leave `/watch`.

### A11Y-024: Honour reduced motion in JS scrolling

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Cross-cutting |
| Persona(s) | vestibular |
| Category | Motion |
| Severity | Low |
| Impact | 2 |
| Effort | S |
| Confidence | Confirmed |
| Priority score | 1.00 |
| Verdict | Fix |
| Dependencies | — |
| Labels | 2.3.3 (AAA), 2.2.2 |

**Evidence:** 22 `@keyframes` vs 16 reduced-motion blocks; JS `behavior: "smooth"` ignores preference at `ReleaseNotesPanel.tsx:57`, `TitleNeighborsRails.tsx:121`, `chatScroll.ts:126-128`, `ScheduledTasksPage.tsx:351`, `LibrariesSection.tsx:153`; CSS `scroll-behavior: smooth` at `07-persona-editorial.css:69` without a reduce guard. Lobby kiosk rotates every 12 s with no pause (`projectionist/theater/static/theater.js:308`) — acceptable for signage, CSS reduce at `theater.css:183`.
**Recommendation:** `const behavior = matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth"` helper; wrap the CSS rule in `@media (prefers-reduced-motion: no-preference)`. Audit the 6 un-guarded keyframes.

### A11Y-025: Support forced-colours mode

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Cross-cutting |
| Persona(s) | low vision (Windows High Contrast) |
| Category | Contrast |
| Severity | Low |
| Impact | 2 |
| Effort | S |
| Confidence | Likely |
| Priority score | 0.80 |
| Verdict | Add |
| Dependencies | A11Y-003 |
| Labels | 1.4.11, 2.4.7 |

**Evidence:** `git grep "forced-colors|prefers-contrast"` → 0. Focus indicators that rely on `box-shadow` (`02-nav-chrome.css:2492-2495`) or background change (`10-explore-delight.css:488-492`) disappear when the OS forces colours.
**Recommendation:** After A11Y-003 (outline-based), add `@media (forced-colors: active) { :focus-visible { outline: 2px solid CanvasText; } .explore-hover-icon { border: 1px solid ButtonText; } }`.

### A11Y-026: Reflow wide list/table views at 320 px

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Consumer / Admin |
| Persona(s) | low vision (zoom), mobile |
| Category | Contrast |
| Severity | Low |
| Impact | 2 |
| Effort | M |
| Confidence | Likely |
| Priority score | 0.53 |
| Verdict | Fix |
| Dependencies | — |
| Labels | 1.4.10 |

**Evidence:** `03-browse-controls.css:337-340` `.media-list-view { min-width: 720px }`, `487-490` 610 px at ≤760 px; `10-explore-delight.css:602-606` scheduled tasks table `min-width: 640px`. True data tables are exempt from 1.4.10; the media list view is a list, not a table.
**Recommendation:** Below 640 px render media list rows as stacked cards; keep the Tasks table scrollable but give the scroll container `tabIndex={0} role="region" aria-label="Scheduled tasks"`.
**Validation:** 320 px viewport + 400% zoom on QA.

---

## B.4 Opportunities

### A11Y-201: Add an Accessibility preferences panel

| Field | Value |
|---|---|
| Type | Opportunity |
| Surface | Consumer |
| Persona(s) | Deaf/HoH, vestibular, speech-input, low vision, youth |
| Category | Media |
| Severity | Medium |
| Impact | 4 |
| Effort | M |
| Confidence | Likely |
| Priority score | 2.13 |
| Verdict | Add |
| Dependencies | A11Y-011, A11Y-017, A11Y-018 |
| Labels | 1.2.2, 2.1.4, 2.3.3, 1.4.4 |

**Evidence:** Today prefs are spread across Profile (text size, theme) and implicit flags (`is_youth`).
**Recommendation:** `Settings → Accessibility`: captions default + SDH + size/background; reduce motion (override OS); single-key shortcuts on/off; text size (relative); "announce replies" verbosity (off / first sentence / full).
**User story:** As any member, I set my needs once and every surface honours them.
**Acceptance criteria:** Prefs persisted server-side, applied in Play, Live, Chat.
**Success metric:** Adoption ≥ 1 household member on Automat within 30 days.
**Validation:** QA `:8792` with all three accounts.

### A11Y-202: Build one Dialog and one Disclosure primitive

| Field | Value |
|---|---|
| Type | Opportunity |
| Surface | Cross-cutting |
| Persona(s) | keyboard-only, screen-reader |
| Category | Keyboard |
| Severity | Medium |
| Impact | 4 |
| Effort | M |
| Confidence | Confirmed |
| Priority score | 2.67 |
| Verdict | Add |
| Dependencies | A11Y-101 |
| Labels | 2.1.2, 2.4.3, 4.1.2 |

**Recommendation:** `components/Dialog.tsx` using `<dialog ref>.showModal()` (native trap, Escape, `::backdrop`, inert page), `aria-labelledby` required prop, `returnFocusRef` default `document.activeElement`. `components/Disclosure.tsx` for popovers (A11Y-013). Migrate 18 dialog files and 4 popovers; ESLint `no-restricted-syntax` banning `role="dialog"` outside `Dialog.tsx`.
**Acceptance criteria:** One implementation; lint ban in place.
**Success metric:** Dialog files using primitive = 18/18.
**Validation:** Parametrised e2e.

### A11Y-203: Make chat a first-class screen-reader experience

| Field | Value |
|---|---|
| Type | Opportunity |
| Surface | Consumer |
| Persona(s) | screen-reader, youth |
| Category | SR |
| Severity | Medium |
| Impact | 4 |
| Effort | S |
| Confidence | Likely |
| Priority score | 3.20 |
| Verdict | Add |
| Dependencies | A11Y-001, A11Y-008 |
| Labels | 4.1.3, 1.3.1, 2.4.1 |

**Recommendation:** Beyond the fix: per-turn `h2.sr-only`, title cards as `<ul>` with count ("6 titles"), `Alt+↑/↓` to move between turns (with off switch), "Read last reply" button, and a text-only reply mode for youth/cognitive users that hides card chrome.
**Success metric:** A blind tester completes "find a horror film and add it to watchlist" in <3 min.
**Validation:** Moderated session on QA.

### A11Y-204: Give Explore rails a roving-tabindex keyboard model

| Field | Value |
|---|---|
| Type | Opportunity |
| Surface | Consumer |
| Persona(s) | keyboard-only, switch, TV-remote |
| Category | Keyboard |
| Severity | Medium |
| Impact | 3 |
| Effort | M |
| Confidence | Likely |
| Priority score | 1.60 |
| Verdict | Add |
| Dependencies | A11Y-010 |
| Labels | 2.4.1, 2.1.1 |

**Recommendation:** Each rail is `role="list"` with one tab stop; ←/→ moves between cards, Enter opens, `.` / context-menu key opens Actions; Tab leaves the rail. This also prepares a "10-foot" remote mode for living-room TVs.
**Success metric:** Tab presses to traverse Explore ≈ number of rails.

### A11Y-205: Ship a changelog digest and plain-language pass

| Field | Value |
|---|---|
| Type | Opportunity |
| Surface | Public |
| Persona(s) | cognitive, youth, non-native language |
| Category | Cognitive |
| Severity | Low |
| Impact | 2 |
| Effort | S |
| Confidence | Confirmed |
| Priority score | 1.00 |
| Verdict | Add |
| Dependencies | A11Y-015 |
| Labels | 3.1.5 (AAA), 3.2.5 (AAA) |

**Recommendation:** Highlights-only digest; reading-level target grade 7 for member Help; mark external links ("opens GitHub in a new tab") for `target="_blank"` in `HelpPage.tsx:101, 242-249` and `PosterOverlayControls.tsx:182`.

### A11Y-206: Extend source-contract unit tests to accessibility

| Field | Value |
|---|---|
| Type | Opportunity |
| Surface | Cross-cutting |
| Persona(s) | all |
| Category | Tooling |
| Severity | Medium |
| Impact | 3 |
| Effort | S |
| Confidence | Confirmed |
| Priority score | 3.00 |
| Verdict | Add |
| Dependencies | A11Y-005 |
| Labels | 1.4.3, 2.4.7, 4.1.2 |

**Evidence:** The repo already asserts JSX shape in node tests (e.g. `frontend/src/lib/chatLayout.test.mjs:74` regex on `<main className="workspace-main"`; `exploreLayout.test.mjs:99`).
**Recommendation:** Add `frontend/src/lib/a11yContracts.test.mjs`: (1) parse `01-tokens.css`, compute contrast for every `--text|--muted|--accent-ink|--danger|--success` vs `--bg|--surface|--surface-2|--surface-raised` in both themes, fail <4.5; (2) fail if any `:focus`/`:focus-visible` rule contains `outline: none`; (3) fail if a file has `role="dialog"` without importing the Dialog primitive. Runs in existing `npm run test:unit` (already in CI).
**Success metric:** Contract test green; catches A11Y-002 regression.

---

## B.5 Screen-reader walkthroughs (predicted from code — *Likely*)

Predicted for VoiceOver + Safari on macOS, Lights Up. Wording approximate.

### Sign in (`/login`)

```
[Load] "Projectionist" (title — same as every page)          ← A11Y-004
VO+U Landmarks: (none)                                        ← no <main> in GlassDoor, A11Y-012
VO+U Headings: "Sign in, heading level 1"
[Read] "Projectionist" … "Sign in, heading level 1" … "Loading sign-in options…"
  (lede changes to "Sign in to open your conversations…" — not announced; inputs disabled meanwhile)
Tab  → "Username, edit text"            (placeholder "Username" duplicated as hint)
Tab  → "Password, secure edit text"
Tab  → "Sign in, button"
Enter→ button text becomes "Signing in…", button + inputs disabled → focus drops to page
       (VO may say nothing, or "Projectionist, web content")          ← A11Y-001
[Wrong password] "Invalid username or password" (role=alert, announced) ✓  ← A11Y-104
       Focus not on a field; no "invalid" state on inputs              ← A11Y-016
Tab  → (starts from top) "Help, link" …
"Need an invite?, button" → Enter → button removed; focus lost again; "Request access"
       heading appears, not announced                                  ← A11Y-001
"Send request, dimmed button" (until name ≥2 chars; no reason given)   ← A11Y-016
After send: "Request sent…" rendered in a plain <p>, not announced     ← A11Y-016
Footer links "Help · Privacy & data use · About" — 3.09:1 amber text   ← A11Y-002
```

### Chat send (`/chat`, owner, LLM unset)

```
[Load] "Projectionist"
Headings: "Projectionist, heading level 1" (logo)  — greeting is a paragraph   ← A11Y-012
Landmarks: banner, complementary (threads), main
Press "/" → "Compare two directors in my library…, edit text, multi-line"
            (name = placeholder; changes per persona/dictation)                ← A11Y-016
Type "Recommend a horror film" → Enter
  textarea disabled → focus to body; VO silent or "dimmed"                    ← A11Y-001
  "Curator is thinking…" (aria-live on role=button, may be read)              ← A11Y-013
  Reply streams into non-live div — nothing announced                          ← A11Y-008
  Reply done: textarea re-enabled, focus NOT restored                          ← A11Y-001
User must VO-navigate: no per-turn headings; user message has no "You said"
  "Curator" … "Here's what I found in your library. Configure an LLM provider…"  ← A11Y-020
  "Helpful, toggle button, not pressed" / "Not helpful, toggle button" ✓
Press "?" → shortcuts dialog renders; focus stays in page; Escape does nothing  ← A11Y-009
```

### Explore a rail → open title → play

```
Headings: "For you, heading level 2", "Continue Watching, heading level 2" … ✓
Per card: "Don't Look Up (2021), heading level 3, link" ✓ (A11Y-102)
          "Play, link"  "Actions for Don't Look Up, collapsed, button"
          "Trailer, button"  "Watch together, button"                     ← A11Y-006
Focus ring on icon buttons: barely visible darkening                       ← A11Y-003
Actions → "menu" announced; arrows do nothing; items far away in DOM      ← A11Y-013
Open title → drawer: "Close title detail, button"; focus trapped; Escape returns ✓ (A11Y-101)
Play → "Seek, slider, 0:12"  "Skip back 15 seconds, button"  "Pause, button" ✓ (A11Y-103)
        player root: "group" with no name                                   ← A11Y-023
```

### Admin nav (owner, hamburger at 1440)

```
"Open navigation menu, collapsed, button" → Enter → "expanded"
Focus stays on toggle; Tab moves through page content behind drawer        ← A11Y-007
Eventually: "Close navigation, button" (backdrop) → "Menu" → "Close menu, button"
"Platform" (plain text, vertical) "Tasks, link" … no group names, no current page ← A11Y-021, 019
On /admin itself: rail "Admin sections, navigation" with "Platform, region"
  "Tasks, link, current page" ✓ (A11Y-107)
```

### Youth Ask

```
Topbar: "Ask, link, current page" ✓   Drawer: "Ask, link" (no current)       ← A11Y-019
Help → eyebrow "Chat, Explore, Related titles…"; jump link "Chat"; "Back to chat" ← A11Y-014
Same chat silence and focus loss as above                                    ← A11Y-001/008
Captions in Play prefer SDH (only because is_youth)                          ← A11Y-018
```

---

## B.6 Remediation tables

### By owner area

| Area | IDs | Est. effort |
|---|---|---|
| Design tokens / CSS | 002, 003, 017, 021, 022, 024, 025, 026 | S–M |
| Chat | 001, 008, 016, 020, 203 | S–M |
| Shell / routing | 004, 007, 010, 012, 019 | S |
| Components | 006, 009, 013, 023, 202 | M |
| Content / Help / About | 014, 015, 205 | S |
| Backend prefs | 018, 201 | M |
| Tooling / CI | 005, 206 | S |

### WCAG SC → finding map (AA, failures only)

| SC | Findings |
|---|---|
| 1.3.1 Info and Relationships | 008, 012, 013, 016, 019, 021 |
| 1.4.1 Use of Color | 019 |
| 1.4.3 Contrast (Minimum) | 002 |
| 1.4.4 Resize Text | 017 |
| 1.4.10 Reflow | 021, 026 |
| 1.4.11 Non-text Contrast | 003, 025 |
| 2.1.4 Character Key Shortcuts | 011 |
| 2.4.1 Bypass Blocks | 010, 015 |
| 2.4.2 Page Titled | 004 |
| 2.4.3 Focus Order | 001, 007, 009, 015 |
| 2.4.4 / 2.4.6 Link purpose / Labels | 006, 012 |
| 2.4.7 Focus Visible | 003 |
| 2.4.11 Focus Not Obscured | 023 (suspected) |
| 2.5.8 Target Size (Minimum) | 022 |
| 3.2.4 Consistent Identification | 014 |
| 3.3.1 / 3.3.3 Error Identification / Suggestion | 016 |
| 4.1.2 Name, Role, Value | 007, 009, 013, 023 |
| 4.1.3 Status Messages | 008, 016 |

## B.7 Quick wins (≤ 1 day each)

| # | Change | Where | ID |
|---|---|---|---|
| 1 | `--accent-ink: #866200` in Lights Up; use it for `a` and text accent | `01-tokens.css:98-110, 194-196` | 002 |
| 2 | Global `:focus-visible` outline; delete 7 `outline: none` focus rules | `01-tokens.css`; cited lines | 003 |
| 3 | Add `keyboardHelpOpen` to `overlayOpen` and close it on Escape | `App.tsx:274-282` | 009 |
| 4 | `aria-label` with title on Play/Trailer/Watch together | `PosterOverlayControls.tsx:118,141,155` | 006 |
| 5 | Rename duplicate Help "Related titles" links | `HelpPage.tsx:218,239` | 006 |
| 6 | Brand `<h1>` → `<span>`; greeting → `<h1>` | `ProjectionistBrand.tsx:66`; `WelcomePanel.tsx:33` | 012 |
| 7 | `document.title` per route | `AppShell`, `GlassDoor`, layouts | 004 |
| 8 | Composer `aria-label`; stop disabling textarea | `ChatWorkspace.tsx:543-607` | 001, 016 |
| 9 | `role="status"` on access-request status | `LoginPage.tsx:452` | 016 |
| 10 | `aria-current` on active thread and drawer link | `ThreadList.tsx:116`; `AppNav.tsx:106` | 019 |
| 11 | Make the existing frontend lint job a required check | `.github/workflows/lint.yml`; repo ruleset | 005 |
| 12 | Role-aware LLM-unset copy | `projectionist/agent/curator.py:414` | 020 |

**AAA quick wins:** LD `--muted` → `#a8a397` (7.73:1, 1.4.6); 2 px 3:1 focus outline everywhere (2.4.13); `aria-label`s with titles (2.4.9); new-window cues (3.2.5); 44 px targets at all widths (2.5.5).

## B.8 Open questions

1. Is "system" the intended default theme? If most households are light-OS, Lights Up is the real primary theme and A11Y-002 is the highest-reach fix.
2. Drag-to-dock (`e2e/drag-to-dock.spec.ts`): is every drag outcome also available via a button (2.5.7)? Not verified.
3. Does the session expire while a user is composing (2.2.1)? Not tested.
4. Live guide (`LiveGuide.tsx:152` arrow handling) — grid or list semantics? Live is Off on QA; needs a campaign with Live on.
5. Should youth renames (Ask/Browse) stay at all, given the consistency cost (A11Y-014)?
6. Material Symbols on offline LANs: bundle the font locally?
7. Is there an owner appetite to run one moderated session with a blind household member or volunteer on QA `:8792` after the 90-day plan?

---

### A11Y-027: Don't offer Try again on a youth rating refusal

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Consumer |
| Persona(s) | Youth, screen-reader |
| Category | Errors |
| Severity | Medium |
| Impact | 3 |
| Effort | XS |
| Confidence | Confirmed |
| Priority score | 6.00 |
| Verdict | Fix |
| Dependencies | A11Y-103, UX-041 |
| Labels | 3.3.3, 2.2.1, youth |

**Evidence:** Youth `/watch/84250` on `:8792` announced **"This title is above your youth rating limit, or it doesn't have a rating we can allow."** The only control was **Try again**. Retrying cannot succeed; there is no Back, no Browse, no Close in that tree. The same recovery widget is correct for a stalled stream (A11Y-103).

**Current state:** Error recovery lies. A screen-reader user who activates the only button stays on the blocked route.

**Root cause:** Player 403 copy uses the generic stall actions (`Try again` ± Open in Plex) for every failure, including policy refusals.

**Recommendation:** Rating-limit failures: status message stays; primary action **Back to Browse** (`/explore`); no Try again. Keep Try again for network/Plex stall only.

**Rationale:** WCAG 3.3.3 Error Suggestion. Try again is not a suggestion that works.

**User story:** When Play is not allowed, I want a control that leaves the player so that I am not looping a 403.

**Acceptance criteria:**
- [ ] Youth over-ceiling `/watch` has no Try again
- [ ] The status role announces the rating limit
- [ ] Back to Browse moves to `/explore`

**Success metric:** `watch.youth-gate` PASS with Back, not retry.

**Validation:** Youth `/watch/84250` on `:8792`.

---

*Counts: 10 Strengths, 27 Weaknesses (0 Critical, 9 High, 11 Medium, 7 Low), 6 Opportunities. Grade C−. A11Y-023 re-confirmed on youth and owner Play; A11Y-027 added from the youth rating 403.*

---

## Changelog

- 2026-10-30 (Chief Skeptic, Phase 4 red team): Corrected the claim that `npm run lint` is not in CI. At `94fcd3f`, `.github/workflows/lint.yml:32-47` runs `cd frontend && npm run lint` in the "Frontend (eslint + prettier)" job. The real gap is that ESLint has no `jsx-a11y` rules and no workflow is a required check (ARCH-007). Updated Conclusion 7, the 90-day table, the Prevention/tooling scorecard note, the A11Y-005 evidence and step 2, and quick win 11. Also fixed the "Read this first" box, which said no keyboard session was run even though the header and B.1 describe the Play keyboard check. The grade (C−) and the Prevention/tooling F are unchanged, because there is still no a11y lint, no axe, and no blocking gate.
