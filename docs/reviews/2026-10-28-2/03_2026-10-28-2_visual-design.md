# 03 — Visual Design review (run 2026-10-28-2)

**Reviewer:** Design Director, independent 360 board
**Commit reviewed:** `94fcd3f` (`origin/main`, 1.37.72 + PR #188). All CSS citations come from `git show 94fcd3f:<path>`. They are not working-tree line numbers.
**Live surface:** QA `http://10.10.1.202:8792` (Path A build of `94fcd3f`). Batch 1 stills `qa_*.png` plus a signed-in Play/Live walk on 2026-10-29 (`ux_youth_explore_1440.png`, `ux_youth_watch_mister_rogers_1440.png`, `ux_owner_watch_endcard_1440.png`). Did not touch prod `:8788` or smartmap `:8790`.
**Inputs read:** `00_2026-10-28-2_platform-map.md`, `_status.md`, `docs/DESIGN.md` @ 94fcd3f, `frontend/src/styles/**` @ 94fcd3f, and selected TSX classNames @ 94fcd3f. No other department document was read.

---

# Part A — Executive

## Bottom line

**Grade: C.**

The brand idea is strong. Lights Down is a well-tuned cinema chamber. Amber `#ffb800` measures **10.79:1** on its surface, and the Fraunces display face gives the app a voice no other self-hosted Plex tool has. The system around that idea has drifted, though:

- **16 stylesheets totalling 20,598 lines.**
- **97 distinct font-size values** across 691 declarations.
- **41 distinct border radii.**
- **53 distinct shadows** across 62 declarations, with no shadow token.
- **25 z-index values**, with no z-index token.
- **16 width breakpoints.**
- **11 custom properties that are referenced but never defined.**

Lights Up, which is what every light-mode OS user gets by default, is a second-class theme. Its amber text measures **3.04:1** and appears in 99 declarations. The first screen a household member sees, local sign-in, ships **unstyled browser-default inputs**. On the signed-in Explore hub, the shelves themselves were blank: 234 poster wells, zero images, a single initial in each frame (VIS-027).

None of this needs a redesign. It needs one token pass, one primitives sheet, and a lint guard. It does not need a big-bang rewrite.

## Key conclusions

1. **Lights Up fails text contrast wherever amber is used as ink.** `--accent: #b8860b` measures 3.04:1 on `--bg` and 2.81:1 on `--surface-2`. It is used as text color 99 times: links, ghost hover, context tag, footer hover. Split the token into a fill and an ink (`--accent-ink: #735c00`, 5.56–6.44:1). See **VIS-001** and **VIS-005**.
2. **The front door looks broken.** The local sign-in form has no input styling at all, and the inner `<form>` has no gap, so the Password field touches the Sign in button (`qa_login_local_1440.png`). This is the highest-scoring fix in the review (15.00) and takes one line of CSS to start. See **VIS-002**.
3. **The default is backwards.** Every bare `<button>` renders as a gold primary (`02-nav-chrome.css`, `button { background: var(--accent) }`), so roughly 25 button classes exist mostly to undo it. Meanwhile, no base input exists. See **VIS-003** and **VIS-021**.
4. **The type scale is irregular, too small, and only half tokenized.** At the Medium root (15px), `--text-sm` is 12.19px and `--text-xs` is 11.25px. About 417 of 691 font-size declarations (≈60%) resolve below 12.5px. 142 px literals ignore the user's font-size preference. See **VIS-006**.
5. **Self-hosted, credentials-stay-home branding still loads three Google Fonts families,** including the full Material Symbols font, on every page. PRIVACY.md does not disclose this. See **VIS-014**.
6. **Theme-specific dark-first leftovers show up in owner screens.** A hardcoded `#16130f` radial paints a grey smudge behind every Admin and Settings title in Lights Up (`qa_owner_admin_overview_1440.png`, `qa_owner_newsletters_1440.png`). Live and Watch carry 85 `lights-up` override selectors. See **VIS-004** and **VIS-008**.
7. **Keep the sacred cow, but amend it.** Lights Down, amber, and Fraunces stay as the brand. Amber becomes a fill/ink pair per theme. Fraunces is restricted to display sizes of 20px and up. Lights Up becomes a co-equal default rather than "the other one". See **VIS-015**, **VIS-030**, and **VIS-033**.
8. **The library has no pictures.** A live owner walk of `/explore` on QA rendered 234 `.poster-fallback` initials and requested zero poster images. `/api/library/feeds/hub` returned `poster_url: ""` for in-library For you titles. Ratio discipline does not help when the art never arrives. See **VIS-027**.

## Foundations table (as shipped at 94fcd3f)

| Foundation | Declarations | Distinct values | Tokenized | Worst offenders |
|---|---:|---:|---:|---|
| Hex color literals | 190 | 76 | 53 live in `01-tokens.css` | `10-explore-delight.css` has 62 literals; `#c4a35a` fallback ×20 |
| rgba() / hsl() | 135 / 2 | 82 / 2 | 0 | `rgba(212,165,116,…)`, `rgba(251,191,36,…)` off-palette ambers |
| color-mix() | 314 | — | built on tokens | good pattern, overused for one-off tints |
| Font family | 126 | 15 stacks | 101 use `var(--font-*)` | 6 different monospace stacks; Fraunces fallback is Times in tokens but Georgia in 8 literals |
| Font size | 691 | 97 | 391 (57%) | 142 px, 127 rem literals, 24 bespoke `clamp()` |
| Font weight | 196 | 9 | 0 | 650 ×10, 560, 550, 800 (none loaded) |
| Line height | 177 | 20 | 14 (8%) | 1.45 ×35, 1 ×35, 1.4 ×22 |
| Letter spacing | 109 | 17 | 0 | 0.04em ×36; 0.01–0.22em spread |
| Spacing (padding/margin/gap) | 2,190 | 65 literal | 839 (38%) | 12px ×104, 8px ×99, 0.35rem ×80 (scales with font pref) |
| Border radius | 387 | 41 | 183 (47%) | 999px ×68, `--radius-md` undefined with 4 different fallbacks |
| Box shadow | 62 | 53 | 0 | 24px/64px, 20px/50px, 18px/48px, 14px/34px… |
| z-index | 106 | 25 | 0 | 0…1200, no scale |
| Breakpoints | 76 `@media` | 24 conditions, 16 width thresholds | `--bp-*` defined, 0 uses | 720 / 760 / 768 / 769; 900 / 901 / 926 / 960 |
| Motion durations | ≈100 | 28 | 0 | 0.15s ×48, 140ms ×6, 160ms ×3, 0.12s ×4 |
| Keyframes | 22 | — | — | 4 infinite loops not covered by reduced motion |
| `prefers-reduced-motion` | 16 blocks | — | — | no global guard |
| Theme override selectors | 88 `lights-up`, 1 `lights-down` | — | — | `12-live.css` ×64, `13-watch.css` ×21 |
| Phantom custom props | 11 | — | — | `--radius-md`, `--warning`, `--warning-text`, `--gold`, `--foreground`, `--text-muted`, `--text-secondary`, `--surface-3`, `--surface-elevated`, `--accent-strong`, `--fg` |

Commands used: `git show 94fcd3f:frontend/src/styles/<file>` concatenated to `all.css`, followed by `grep -oE` counts. Five more referenced properties (`--coverage-pct`, `--guide-hour-px`, `--guide-slot-px`, `--media-list-columns`, `--title-backdrop`) are runtime-inline, so they are excluded from the phantom count.

## If we built it today

- **One tokens file with three layers:** primitives (raw hex and px), semantic aliases (`--text`, `--accent-fill`, `--accent-ink`, `--border-field`, `--status-*`), and component tokens. No hex outside the token file, enforced by Stylelint.
- **A primitives sheet** (`.btn`, `.field`, `.card`, `.chip`, `.badge`, `.dialog`, `.sheet`, `.tabs`, `.data-table`, `.skeleton`, `.toast`) imported immediately after tokens. Feature sheets compose these primitives and do not restyle bare elements.
- **A 1.2-ratio type scale with a 12px floor**, in rem, scaling with the user preference. Fraunces is reserved for display through h3.
- **Self-hosted WOFF2 fonts** and an SVG icon sprite. No third-party requests from a "stays home" product.
- **Both themes visually regression-tested** on five key screens.
- **Admin gets `data-density="compact"` on purpose,** not by accident.

## Findings by surface

### Public (`/login`, `/join`, `/help`, `/about`, `/privacy`)

| ID | Title | Severity | Score |
|---|---|---|---:|
| VIS-002 | Style the local sign-in fields and stack | High | 15.00 |
| VIS-010 | Lay out the Privacy shortcut row | Medium | 6.00 |
| VIS-018 | Cap reading measure at 68ch of the article font | Medium | 4.80 |
| VIS-025 | Unify the three header chromes | Medium | 1.60 |
| VIS-032 | Protect the glass-door join card | Strength | 6.00 |

### Consumer (chat, Explore, settings, Live, Watch)

| ID | Title | Severity | Score |
|---|---|---|---:|
| VIS-027 | Show real posters, or a designed missing-art state | High | 7.50 |
| VIS-005 | Use the on-accent ink on Explore Search | Medium | 6.00 |
| VIS-011 | Replace five loading idioms with one skeleton | Medium | 4.00 |
| VIS-013 | Retire emoji and Unicode glyph icons | Medium | 3.00 |
| VIS-008 | Fold Live/Watch theme patches into tokens | Medium | 2.00 |
| VIS-017 | Stop the profile avatar from squashing | Low | 2.00 |
| VIS-019 | Give chat markdown headings a real hierarchy | Low | 2.00 |
| VIS-026 | Drop monospace from the composer context tag | Low | 2.00 |

### Owner (`/admin/*`)

| ID | Title | Severity | Score |
|---|---|---|---:|
| VIS-004 | Remove the hardcoded dark radial from Admin/Settings | Medium | 8.00 |
| VIS-009 | Give the fixed footer a home | Medium | 3.00 |
| VIS-022 | Add a warning hue; stop using amber for warn | Medium | 3.00 |
| VIS-016 | Replace rotated admin group labels | Low | 1.60 |
| VIS-040 | Ship an intentional Admin density mode | Opportunity | 1.60 |

### Admin / platform

There is no separate platform-admin surface. The owner is the operator (see the platform map). Owner findings apply.

### Cross-cutting

| ID | Title | Severity | Score |
|---|---|---|---:|
| VIS-001 | Split amber into fill and ink per theme | High | 7.50 |
| VIS-014 | Self-host fonts and subset icons | High | 6.00 |
| VIS-012 | Add a global reduced-motion guard | Medium | 6.00 |
| VIS-003 | Invert the button default; add a field primitive | High | 4.00 |
| VIS-015 | Treat Lights Up as a co-equal default | Medium | 4.00 |
| VIS-024 | Give form fields a 3:1 boundary | Medium | 4.00 |
| VIS-007 | Define the phantom tokens and kill literals | Medium | 2.67 |
| VIS-006 | Rebuild the type scale with a 12px floor | High | 2.40 |
| VIS-020 | Collapse 16 breakpoints to 4 | Medium | 2.00 |
| VIS-023 | Use only loaded font weights | Low | 2.00 |
| VIS-021 | Consolidate component variants | Medium | 1.60 |

## Themes

1. **Dark-first, light-patched.** Lights Up was added as a token swap, but literal fallbacks (`#16130f`, `var(--bg)` as text on accent, `#c45c5c`) and 88 override selectors prove the dark theme is the real design.
2. **Additive CSS without primitives.** Each feature sheet invents its own card, chip, button, and loader: 40 card roots, 24 chip roots, and 5 loading idioms.
3. **Amber does too many jobs.** It is the brand, primary fill, link, focus ring, active nav, hover, *and* warning.
4. **Small type everywhere.** Most chrome sits at 11–12px, and px literals do not scale with the font preference.
5. **Third-party dependence in a sovereignty product.** Google Fonts carries the brand and the icons.

## Stop doing

- Styling bare elements (`button { … }`) as a variant.
- Writing `var(--token, #literal)` fallbacks. These 60+ fallbacks hide phantom tokens and paint the wrong color when a token is missing.
- Adding `html[data-theme="lights-up"] .x { … }` patches. Fix the token instead.
- Inventing a `-card` or `-chip` class per feature.
- Using text-only "Loading…" for poster content.
- Using emoji as UI icons.
- Claiming "Lights Down (default)" in `docs/DESIGN.md` when `index.html` defaults to `system`.

## Strengths

- **VIS-030:** Lights Down contrast is excellent. Text measures 12.59–15.01:1, muted 5.47–6.52:1, amber 9.40–11.21:1, and on-accent 10.68:1.
- **VIS-031:** The theme architecture is right. `html[data-theme]` token swaps plus a pre-paint FOUC script in `index.html` give no theme flash.
- **VIS-033:** The Fraunces + DM Sans pairing is a distinctive editorial voice (`qa_about_1440.png`, `qa_owner_chat_1440.png`).
- **VIS-034:** Phone primitives are deliberate: `--tap-min: 44px`, `--font-size-input: 16px`, rail peek tokens, and safe-area insets.
- **VIS-035:** Poster ratio discipline holds. 10 of 11 `aspect-ratio` declarations are 2/3.
- **VIS-036:** The "one gold primary" rule and the locked Material Symbols table in DESIGN.md are already strong governance.
- **VIS-032:** The glass-door join card is the most polished public surface (`qa_join_empty_1440.png`).

## Risks

- **Changing the root font size** (15px → 16px at Medium) shifts every rem-based layout by 6.7%. It must ship behind visual diffs (VIS-043).
- **Inverting `button`** could unstyle unlabeled buttons app-wide. Ship the `.btn` primitive first, migrate call sites, and only then neutralize the element rule.
- **Self-hosting fonts** adds roughly 250–400 KB to the image. That is acceptable, but verify the Docker layer size.
- **Lint guard churn.** Start Stylelint in warn mode with a baseline file.

## 90-day direction

| Window | Outcome |
|---|---|
| Days 0–14 (Now) | VIS-002, 004, 027, 005, 010, 012, 017 shipped. Amber ink split (VIS-001). Fonts self-hosted (VIS-014). |
| Days 15–45 (Next) | `01a-primitives.css` with `.btn`, `.field`, `.card`, `.skeleton`. Type scale v2 behind visual diff. Phantom tokens defined. Stylelint in warn mode. Playwright theme screenshots for 5 screens. |
| Days 46–90 (Later) | Live/Watch theme patches folded into tokens. Component consolidation to target counts. Breakpoints collapsed to 4. Admin compact density. Stylelint in error mode. DESIGN.md rewritten as a token-first spec. |

## Scorecard (1–5)

| Dimension | Score | Why |
|---|:-:|---|
| Tokens / system | 2 | 57% of type tokenized, 38% of spacing, 0% of shadow / z / motion; 11 phantoms |
| Color — Lights Down | 4 | All text pairs AA; field borders 1.44:1 |
| Color — Lights Up | 2 | Amber ink 3.04:1 across 99 uses; Search 3.04:1; success 4.33:1 on surface-2 |
| Typography | 3 | Great pairing; irregular, sub-12px scale; unloaded weights |
| Layout / spacing | 3 | Good phone tokens; footer overlap; measure too long on Help/About |
| Components | 2 | ~25 button, 40 card, and 24 chip roots; no input primitive |
| Iconography / imagery | 2 | Ratio discipline holds; QA Explore showed 234 letter tiles and no art (VIS-027) |
| Motion | 3 | Restrained durations; reduced-motion coverage patchy |
| Brand consistency | 4 | Recognizable across surfaces; three header chromes |
| Polish | 2 | Login inputs, smudge, footer overlap, TOC concatenation |

---

# Part B — Detail

## Scope

**In scope:** visual craft of `94fcd3f` SPA stylesheets, `frontend/index.html` font loading, and the screenshots `qa_login_local_1440`, `qa_owner_chat_1440`, `qa_owner_explore_1440`, `qa_owner_admin_overview_1440`, `qa_owner_admin_nav_1440`, `qa_owner_newsletters_1440`, `qa_member_chat_390`, `qa_member_settings_1440`, `qa_youth_nav_1440`, `qa_about_1440`, `qa_help_guest_1440`, and `qa_join_empty_1440`. A later parent walk on the same QA host added `ux_owner_explore_1440.png` (Lights Up, posters missing) and `ux_youth_nav_1440.png` (Lights Down).

**Out of scope:** UX information architecture (02), the WCAG program (04), Lobby Theater `:8795`, and Play/Live runtime (not captured). Contrast ratios here use WCAG 2.x relative luminance. Translucent layers are composited over the stated surface.

**Screenshot caveats:**
- `qa_member_chat_390.png` repeats the top bar three times. This is likely a full-page stitch artifact of a fixed header, not a product bug, so it is not scored.
- `qa_member_settings_1440.png` is captured at about 605px wide.

### Contrast reference (current tokens)

| Pair | Lights Down | Lights Up |
|---|---:|---:|
| `--text` on `--bg` | 15.01:1 | 15.99:1 |
| `--text` on `--surface-raised` | 12.59:1 | 17.12:1 |
| `--muted` on `--bg` | 6.52:1 | 8.74:1 |
| `--muted` on `--surface-raised` | 5.47:1 | 9.36:1 |
| `--accent` (as text) on `--bg` | **11.21:1** | **3.04:1 ✗** |
| `--accent` on `--surface` | 10.79:1 | 3.09:1 ✗ |
| `--accent` on `--surface-2` | 10.03:1 | **2.81:1 ✗** |
| `--accent-text` on `--accent` (primary button) | 10.68:1 | 5.69:1 |
| `--bg` on `--accent` (Explore Search) | 11.21:1 | **3.04:1 ✗** |
| `--accent-text` on `--accent-2` | 8.23:1 | 2.87:1 ✗ (1 fill use, `12-live.css`) |
| `--danger` on `--surface` | 7.89:1 | 6.14:1 |
| `--success` on `--surface` | 8.33:1 | 4.77:1 (4.33:1 on surface-2 ✗) |
| `--border` vs `--surface` (field boundary) | **1.44:1 ✗** | **1.62:1 ✗** |
| Footer link (muted @ 0.6 opacity) on bg | 3.05:1 ✗ | 3.11:1 ✗ |
| `#c45c5c` literal (05/10 sheets) on surface | 4.49:1 ✗ | 3.97:1 ✗ |
| `var(--warning, #c9a227)` fallback | — | 2.30:1 ✗ |
| White on `#ffb800` (if anyone tries) | 1.73:1 ✗ | — |

---

## Weaknesses (sorted by priority score)

| Rank | ID | Score |
|---:|---|---:|
| 1 | VIS-002 | 15.00 |
| 2 | VIS-004 | 8.00 |
| 3 | VIS-027 | 7.50 |
| 4 | VIS-001 | 7.50 |
| 5 | VIS-005 | 6.00 |
| 6 | VIS-010 | 6.00 |
| 7 | VIS-012 | 6.00 |
| 8 | VIS-014 | 6.00 |
| 9 | VIS-018 | 4.80 |
| 10 | VIS-003 | 4.00 |
| 11 | VIS-011 | 4.00 |
| 12 | VIS-015 | 4.00 |
| 13 | VIS-024 | 4.00 |
| 14 | VIS-009 | 3.00 |
| 15 | VIS-013 | 3.00 |
| 16 | VIS-022 | 3.00 |
| 17 | VIS-007 | 2.67 |
| 18 | VIS-006 | 2.40 |
| 19 | VIS-008 | 2.00 |
| 20 | VIS-017 | 2.00 |
| 21 | VIS-019 | 2.00 |
| 22 | VIS-020 | 2.00 |
| 23 | VIS-023 | 2.00 |
| 24 | VIS-026 | 2.00 |
| 25 | VIS-016 | 1.60 |
| 26 | VIS-021 | 1.60 |
| 27 | VIS-025 | 1.60 |

### VIS-002: Style the local sign-in fields and stack

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Public |
| Persona(s) | First-time household member, Returning consumer, Older / low vision |
| Category | Components |
| Severity | High |
| Impact | 5 |
| Effort | XS |
| Confidence | Confirmed |
| Priority score | 15.00 |
| Verdict | Fix |
| Dependencies | none (VIS-003 later generalizes it) |
| Labels | login, glass-door, forms, polish, first-impression |

**Evidence**
- `qa_login_local_1440.png` shows square browser-default inputs with a 1px dark UA border and about 2px padding. The placeholder "Username" sits flush against the border. The Password input touches the Sign in button with 0px gap. The label-to-input gap (about 26px) is larger than the field-to-next-label gap (0px), so each label reads as belonging to the field above it.
- `94fcd3f:frontend/src/styles/05-chat-responsive.css`: `.login-field input { width: 100%; }` is the *only* desktop rule. There is no padding, border, radius, background, or font rule.
- `94fcd3f:frontend/src/pages/LoginPage.tsx` (local section) nests a bare `<form onSubmit={handleLocalLogin}>` inside `.login-form`. The `display:grid; gap` lives on the outer div, so children of the inner form get no gap.
- There is no global `input {}` rule in any sheet. The only field styles are `.settings-field input…` (06) and a phone-only rule (05).

**Current state:** The glass-door card (`15-glass-door.css`) is crafted: blur, 520px max, `--radius-lg`, and a 24/64 shadow. The form inside it is raw HTML.

**Root cause:** There is no field primitive. The login form was assembled from page-local classes, and the local-password path was added after the Plex-PIN path, which has no text fields.

**Recommendation**
```css
.login-form > form { display: grid; gap: var(--space-4); }          /* 16px between fields */
.login-field { display: grid; gap: var(--space-2); }                  /* 8px label→control */
.login-field > span { font-size: var(--text-sm); font-weight: 600; }  /* 14px label (v2 scale) */
.login-field input {
  min-height: 44px; padding: 10px 14px;
  font: inherit; font-size: var(--font-size-input);                   /* 16px, no iOS zoom */
  color: var(--text); background: var(--surface-raised);
  border: 1px solid var(--border-field); border-radius: var(--radius-sm);
}
.login-field input::placeholder { color: var(--muted); }
.login-field input:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: 2px; }
.login-primary { min-height: 44px; margin-top: var(--space-2); }
```
Drop `placeholder="Username"` because it duplicates the label.

**Rationale:** This is the first pixel a household member sees. A crafted card with raw inputs reads as "unfinished" or "phishing".

**User story:** As a household member opening an invite, I want the sign-in form to look as deliberate as the card around it, so that I trust it with my password.

**Acceptance criteria**
- [ ] Inputs are 44px or taller, have a 6px radius, and use a `--border-field` boundary of at least 3:1 in both themes.
- [ ] Gaps are 8px between label and input and 16px between field groups. The button never touches a field.
- [ ] No placeholder duplicates a visible label.
- [ ] The same styles apply on `/join` and `/setup` fields.

**Success metric:** Zero UA-default inputs on public routes (Playwright computed-style check for `border-radius > 0` and `padding-left ≥ 12px`).

**Validation:** Compare Playwright screenshots of `/login` before and after in both themes at 1440 and 390, and check `getComputedStyle` on `[data-testid=local-username]`.

### VIS-004: Remove the hardcoded dark radial from Admin/Settings

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Owner |
| Persona(s) | New owner, Established owner at scale, Household member (Settings) |
| Category | Color |
| Severity | Medium |
| Impact | 4 |
| Effort | XS |
| Confidence | Confirmed |
| Priority score | 8.00 |
| Verdict | Fix |
| Dependencies | none |
| Labels | lights-up, admin, settings, theme-leak |

**Evidence**
- `qa_owner_admin_overview_1440.png` and `qa_owner_newsletters_1440.png` show a grey-brown smear about 400px wide, fanning from the top-left behind "Overview" and "Newsletters".
- `94fcd3f:frontend/src/styles/06-reading-admin-settings.css`, `.admin-shell, .settings-shell { background: radial-gradient(ellipse 70% 40% at 10% -5%, #16130f 0%, transparent 50%), var(--bg); }`. `#16130f` is a Lights Down literal.

**Current state:** In Lights Down the radial is a subtle warm wash. In Lights Up it is a dirty thumbprint on paper.

**Root cause:** A literal hex sits where a token belongs.

**Recommendation:** Replace `#16130f` with `var(--workspace-wash-a)`. That gives `#1a1612` in Lights Down and `#f0ebe0` in Lights Up, which is the same wash `body` already uses in `01-tokens.css`.

**Rationale:** The wash should be atmosphere, not dirt. The token already exists.

**User story:** As an owner on a light-mode Mac, I want Admin pages to look as clean as Explore, so that the console feels cared for.

**Acceptance criteria**
- [ ] No hex literal in `.admin-shell` or `.settings-shell` backgrounds.
- [ ] A Lights Up screenshot of `/admin/overview` shows no region darker than `--surface-2` (`#f0eee9`) behind the title.

**Success metric:** 0 hex literals in `06-reading-admin-settings.css` backgrounds (down from 1 here; 18 hex literals file-wide).

**Validation:** Pixel sample at (120, 140) on a 1440 Lights Up screenshot shows luminance of at least L\* 93.

### VIS-027: Show real posters, or a designed missing-art state

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Consumer |
| Persona(s) | Returning consumer, Power consumer, Older / low vision |
| Category | Iconography |
| Severity | High |
| Impact | 5 |
| Effort | S |
| Confidence | Confirmed |
| Priority score | 7.50 |
| Verdict | Fix |
| Dependencies | none |
| Labels | posters, explore, empty-state, imagery |

**Evidence**
- `ux_owner_explore_1440.png` (QA `:8792`, Lights Up, owner, 2026-10-29): For you cards are gray 2:3 wells with a play glyph and a single capital letter. Kinship sentences render under the wells. No poster bitmap is visible.
- Same session, `document.querySelectorAll('.poster-fallback').length === 234`, `img` count 0, and `performance` resource list contained no poster or image requests.
- `GET /api/library/feeds/hub?limit=2` returned For you item "Moon Landing: The Lost Tapes" with `poster_url: ""`.
- `94fcd3f:frontend/src/components/TitleCard.tsx:334-337` renders `<div class="poster-fallback">` plus `title.slice(0, 1)` when `poster_url` is falsy. `.poster-fallback` is `font-size: 48px; color: var(--muted)` at `94fcd3f:frontend/src/styles/03-browse-controls.css:842`. Explore wells keep `aspect-ratio: 2 / 3` at `94fcd3f:frontend/src/styles/09-title-detail-home.css` (`.explore-poster`).

**Current state:** The ratio holds, so the shelf does not collapse. It also does not look like a library. A 48px muted initial is the entire hero of For you, Continue Watching, and the other rails.

**Root cause:** The hub feed emits an empty `poster_url` for titles that are in the library, and the card treats "no URL" as a one-letter monogram instead of a designed missing-art state. Loading skeletons (VIS-011) do not cover the arrived-but-blank case. *(Corrected 2026-10-30, see Changelog.)* The empty URL comes from two causes. First, browser payloads keep only TMDB CDN art: `94fcd3f:projectionist/privacy/schema.py:96-108,157-168` drops any non-TMDB poster, including Plex thumbs that carry `X-Plex-Token`, and returns `""`. Second, on this QA sidecar the TMDB key could not be decrypted (secrets MAC mismatch; Tasks report "TMDB API key not configured", OPS-010/OPS-011), so no TMDB art was available. The QA blank shelf is partly an environment fault. The product defect is still real: any install without a working TMDB key, including a Plex-only household, gets letter tiles. The main app has no same-origin poster proxy. The only one is the Lobby Theater's `/api/theater/poster` (`projectionist/theater/app.py:188`).

**Recommendation:** Two layers, ship the first without waiting on the second.
1. **Art must be requested.** For every in-library item with a `rating_key` or `tmdb_id`, `poster_url` is a same-origin path, never `""`. Empty string is a bug, not a variant. The main app needs a token-hiding poster proxy for Plex thumbs, modelled on the Lobby Theater's `/api/theater/poster`. There is no main-app proxy at `94fcd3f`.
2. **Missing art has a spec.** When the URL is genuinely absent, the well is `--surface-2`, radius `--radius-sm`, and stacks the title (DM Sans 14px/600, `--text`, max 3 lines) over the year (12px, `--muted`). No 48px initial. `min-height` stays the 2:3 box. Alt text on a real image remains `""` only when the visible title is in the same card; the monogram is removed so it cannot be the accessible name of the art.

**Rationale:** Posters are the product's imagery. Kinship copy underneath a blank well reads as a broken shelf, which undercuts the "honest why" the rails are built to show. A monogram does not identify a title at rail size. Filling `poster_url` is the fix; the designed fallback is what users see when metadata is actually missing.

**User story:** As a member opening Explore, I want each title to show its poster so that I can recognize it before I read the reason.

**Acceptance criteria**
- [ ] On a library of at least 100 indexed titles, `/explore` For you renders `<img>` for every item whose hub payload includes a non-empty `poster_url`.
- [ ] A fixture item with `poster_url: ""` renders the title and year inside the 2:3 well, and does not render a single-letter `.poster-fallback`.
- [ ] `ux_owner_explore_1440.png` is replaced by a shot where at least the first rail shows poster bitmaps.

**Success metric:** 0 `.poster-fallback` nodes on `/explore` when the hub feed includes poster URLs for those items. Missing-art fixtures show title + year, not an initial.

**Validation:** Reload `/explore` as `qa-owner` on `:8792` after the feed fix. Count `img` inside `.explore-poster` and confirm each `naturalWidth > 0`.

### VIS-028: Give the Play end card a designed frame, not a right-hug crop

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Consumer |
| Persona(s) | Returning consumer, Older / low vision |
| Category | Layout |
| Severity | Medium |
| Impact | 3 |
| Effort | S |
| Confidence | Confirmed |
| Priority score | 3.00 |
| Verdict | Fix |
| Dependencies | UX-012, UX-043, VIS-008 |
| Labels | play, end-card, composition |

**Evidence:** Owner end card on Don't Look Up (`ux_owner_watch_endcard_1440.png`): black stage, gold kicker "THAT'S THE REEL" and body copy hugging the **bottom-right**, cropped by the viewport ("That's the last episode in yo…", "BACK TO…" ghost cut off). Gold **BACK TO TITLE** is the only complete control. Youth Resume gate (`ux_youth_watch_mister_rogers_1440.png`) used the same right-hug composition: "CONTINUE WATCHING" / title / "From 17:01" clipped. `13-watch.css` is 21 Lights Up overrides on a dark-first theater (VIS-008).

**Current state:** The last screen of Play, and the Resume gate, do not hold a 45–75ch measure or a 16px inset from the viewport. They look like a poster title card designed for 1920×1080 and then windowed.

**Root cause:** Theater chrome is positioned against the stage edge without a max-width column or safe-area padding that survives a ~900px embedded browser (the 900px nav breakpoint is also the live Cursor pane).

**Recommendation:** End card and Resume gate sit in a **max-width 28rem** column, **bottom-left** on desktop (thumb-left on phone is optional; prefer bottom-center at ≤900px), padding `max(24px, env(safe-area-inset-*))`. One gold primary, one ghost, both fully visible. Title wraps to 2 lines; kicker stays 12px tracking. Do not crop buttons.

**Rationale:** Play is the brand's cinema moment. A cropped gold pill at the end of a film reads as unfinished craft, which is the opposite of Lights Down's job.

**User story:** When the reel ends, I want the next action fully on screen so that I can leave or rate without hunting.

**Acceptance criteria:**
- [ ] At 1440, 900, and 390, both end-card buttons are fully visible with ≥16px inset
- [ ] Resume gate title is not clipped
- [ ] Lights Up theater still uses token surfaces, not a leftover dark wash

**Success metric:** 0 end-card screenshots with clipped button labels in visual regression (VIS-043).

**Validation:** Replay Don't Look Up to the end card at 1440 and 390 on `:8792`.

### VIS-001: Split amber into fill and ink per theme

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Cross-cutting |
| Persona(s) | All in Lights Up; Older / low vision; Screen-reader sighted helpers |
| Category | Color |
| Severity | High |
| Impact | 5 |
| Effort | S |
| Confidence | Confirmed |
| Priority score | 7.50 |
| Verdict | Fix |
| Dependencies | VIS-015 |
| Labels | contrast, tokens, lights-up, accent, brand |

**Evidence**
- `01-tokens.css` Lights Up sets `--accent: #b8860b`. It measures **3.04:1** on `--bg #f9f7f2`, **3.09:1** on `--surface`, **2.81:1** on `--surface-2`, and 3.25:1 on white.
- 99 declarations use `color: var(--accent)` as text, including `a { color: var(--accent) }` in `01-tokens.css`, `.message-title-link`, `button.ghost:hover`, `.app-footer-link:hover`, `.help-jump-nav a:hover`, `.knowledge-coverage-help-link`, and `.owner-health-tile.tone-warn .owner-health-tile-value`.
- Visible in `qa_owner_newsletters_1440.png` (links "Mail", "Settings → Notifications") and `qa_owner_chat_1440.png` (gold "General Exploration" tag on `--surface-raised`, 3.25:1).
- Focus rings use the same token: 2.81:1 on `--surface-2` is below the 3:1 non-text minimum.

**Current state:** One `--accent` per theme serves as fill, text, ring, and border. The Lights Down value works for all of these roles. The Lights Up value only works as a fill under dark text (5.69:1).

**Root cause:** Lights Up was derived as a hue-preserving swap without role separation.

**Recommendation:** Introduce role tokens and migrate by role:

| Token | Lights Down | Lights Up | Use |
|---|---|---|---|
| `--accent-fill` | `#ffb800` | `#b8860b` | primary button, selected chip fill |
| `--accent-fill-hover` | `#ffc533` | `#c4920f` | hover |
| `--accent-fill-press` | `#e0a200` | `#a67908` | active |
| `--on-accent` | `#1a1208` | `#1a1208` | text on fill (10.68 / 11.72 / 8.23 and 5.69 / 6.58 / 4.73:1) |
| `--accent-ink` | `#ffb800` | `#735c00` | links, active labels, icon accents (DN 9.40–11.21; UP 5.56–6.44:1) |
| `--focus-ring` | `#ffb800` | `#735c00` | outlines (DN ≥10.03; UP ≥5.56:1) |

Keep `--accent` as a deprecated alias of `--accent-ink` for one release, then sweep. `#735c00` is already the Lights Up `--accent-2`, so no new hue is introduced.

**Rationale:** Amber stays the brand. Only its *ink* in Lights Up darkens to a bronze that reads.

**User story:** As a member who keeps macOS in light mode, I want links and labels I can actually read, so that I do not mistake them for disabled text.

**Acceptance criteria**
- [ ] Every text use of amber resolves to `--accent-ink`.
- [ ] Lights Up ink is at least 4.5:1 on bg, surface, surface-2, and raised.
- [ ] The focus ring is at least 3:1 on all four surfaces in both themes.
- [ ] Lights Down is visually unchanged.

**Success metric:** Lights Up failing text pairs from accent drop from 99 to 0 (Stylelint or grep `color:\s*var\(--accent\)` = 0).

**Validation:** Run axe on `/admin/newsletters`, `/chat`, and `/help` in Lights Up with 0 color-contrast violations from link or tag nodes, and check computed color with a script.

### VIS-005: Use the on-accent ink on Explore Search

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Consumer |
| Persona(s) | Returning consumer, Power consumer |
| Category | Color |
| Severity | Medium |
| Impact | 3 |
| Effort | XS |
| Confidence | Confirmed |
| Priority score | 6.00 |
| Verdict | Fix |
| Dependencies | VIS-001 (token name) |
| Labels | contrast, explore, lights-up, button |

**Evidence**
- `10-explore-delight.css`, `.explore-search-submit { color: var(--bg, #10141b); background: var(--accent, #c4a35a); }`. In Lights Up that is `#f9f7f2` on `#b8860b` = **3.04:1**. White text on gold is visible in `qa_owner_explore_1440.png`.
- Two more `color: var(--bg)` rules sit on accent fills (`02-nav-chrome.css`, `08-dashboard-coverage-cards.css`). The login primary correctly uses `--accent-text` (5.69:1), so 17 rules do it right and 3 do it wrong.

**Current state:** The same gold button has two different text colors depending on which sheet drew it.

**Root cause:** The "on" color is chosen per component instead of per role.

**Recommendation:** Replace `color: var(--bg…)` with `color: var(--on-accent)` in all three rules, and remove the `#c4a35a` and `#10141b` fallbacks.

**Rationale:** Dark text on gold is the brand's primary button. It already reads at 10.68:1 and 5.69:1.

**User story:** As a member searching my library, I want the Search button label to be readable in both themes.

**Acceptance criteria**
- [ ] 0 `color: var(--bg` declarations on accent backgrounds.
- [ ] Search label is at least 4.5:1 in both themes.

**Success metric:** `git grep -c "color: var(--bg"` on accent-filled selectors = 0.

**Validation:** Computed-style contrast check in the Playwright theme spec.

### VIS-010: Lay out the Privacy shortcut row

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Public |
| Persona(s) | First-time visitor, Household member, Owner |
| Category | Polish |
| Severity | Medium |
| Impact | 3 |
| Effort | XS |
| Confidence | Confirmed |
| Priority score | 6.00 |
| Verdict | Fix |
| Dependencies | none |
| Labels | privacy, toc, layout-bug |

**Evidence**
- `94fcd3f:frontend/src/pages/PrivacyPage.tsx` renders `<nav className="privacy-jump-nav help-jump-nav">` with six adjacent `<a>`/`<Link>` children on separate JSX lines. JSX strips that whitespace, so the anchors abut.
- `06-reading-admin-settings.css` gives the flex/gap layout only to `.help-page .help-jump-nav`. On `.privacy-page` only `margin-bottom: var(--space-4)` applies, so the labels concatenate to "HouseholdOwnersMCPHelpAboutLogin". The platform map flags this as known; no PNG was saved.

**Current state:** The shortcut row is unreadable on Privacy and fine on Help.

**Root cause:** A shared class was styled under a page-scoped selector.

**Recommendation:** Promote the rule to `.help-jump-nav { display:flex; flex-wrap:wrap; gap: var(--space-3) var(--space-4); font-size: var(--text-sm); }` (unscoped), and move the link color to `--muted` with hover set to `--accent-ink`.

**Rationale:** Privacy is a trust surface. A broken TOC there undercuts the content.

**User story:** As a household member reading what is shared, I want clear section shortcuts.

**Acceptance criteria**
- [ ] Six links render with at least 12px gaps.
- [ ] Links wrap at 390px without overflow.

**Success metric:** No sibling anchors in `.help-jump-nav` with a horizontal gap under 12px (Playwright bounding boxes).

**Validation:** Screenshot `/privacy` at 1440 and 390 in both themes.

### VIS-012: Add a global reduced-motion guard

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Cross-cutting |
| Persona(s) | Vestibular-sensitive users, Older / low vision, Keyboard-only |
| Category | Motion |
| Severity | Medium |
| Impact | 3 |
| Effort | XS |
| Confidence | Confirmed |
| Priority score | 6.00 |
| Verdict | Fix |
| Dependencies | none |
| Labels | motion, reduced-motion, a11y-adjacent |

**Evidence**
- There are 16 scattered `@media (prefers-reduced-motion: reduce)` blocks: `02-nav-chrome.css` ×2, `03` ×1, `04` ×2, `05`, `07`, `08`, `09`, `10` ×1 each, `12-live.css` ×3, `13`, `14`, `15` ×1 each.
- Infinite animations with **no** coverage:
  - `typing-bounce 1.2s ease-in-out infinite` (`02-nav-chrome.css`)
  - `projectionist-lamp-pulse 1.6s ease-in-out infinite` (`04-config-onboarding.css`)
  - `dash-shimmer 1.4s ease-in-out infinite` (`07-persona-editorial.css`)
  - `poster-rail-spin 0.8s linear infinite` (`10-explore-delight.css`)
- Entrance animations with no coverage: `app-nav-slide 160ms`, `portal-menu-in 0.14s`, `menu-action-flash-in 0.18s`.

**Current state:** Coverage is opt-in per component, so new animations ship uncovered by default.

**Root cause:** There is no global guard and no motion tokens.

**Recommendation:** Add the following to `01-tokens.css`:
```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
    scroll-behavior: auto !important;
  }
}
```
Keep the bespoke blocks only where they swap in a *static* alternative (for example, the `browse-grid-pending-card` tint). Spinners should become a static 3-dot or a determinate bar under reduced motion.

**Rationale:** One guard covers future work. The cinema mood does not depend on looping motion.

**User story:** As a member with motion sensitivity, I want the app to stop pulsing and spinning when I have asked my OS to reduce motion.

**Acceptance criteria**
- [ ] With `prefers-reduced-motion: reduce` emulated, no element reports a running CSS animation longer than 10ms (`document.getAnimations()`).
- [ ] Loading states still communicate progress with a static indicator.

**Success metric:** `document.getAnimations().filter(a => a.playState === 'running').length === 0` on chat, Explore, and Admin under emulation.

**Validation:** Playwright `emulateMedia({ reducedMotion: 'reduce' })` spec.

### VIS-014: Self-host fonts and subset icons

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Cross-cutting |
| Persona(s) | Owner (privacy), Low-bandwidth mobile, All |
| Category | Brand |
| Severity | High |
| Impact | 4 |
| Effort | S |
| Confidence | Confirmed |
| Priority score | 6.00 |
| Verdict | Fix |
| Dependencies | none |
| Labels | fonts, privacy, performance, brand, icons |

**Evidence**
- `94fcd3f:frontend/index.html` preconnects to `fonts.googleapis.com` and `fonts.gstatic.com`. It loads DM Sans (opsz 9–40, weights 400/500/600/700, italic 400) and Fraunces (opsz 9–144, weights 500/600/700) with `display=swap`, plus **Material Symbols Outlined** (full glyph set, opsz 24 / wght 400) with no `icon_names` subset.
- `git grep` for "fonts.googleapis" and "Google Fonts" in `docs/PRIVACY.md`, `docs/*.md`, and `README.md` returns 0 hits.
- The About copy in `qa_about_1440.png` says "credentials that stay home".

**Current state:** Every page view sends the visitor's IP and referrer to Google. With `display=swap`, the first paint is in Times New Roman or system-ui and then reflows. Material Symbols ligature text can flash as words (for example, "expand_more") before the font loads.

**Root cause:** The CDN is a convenience default that was never revisited.

**Recommendation**
- Ship WOFF2 files from `frontend/public/fonts/`:
  - DM Sans variable (wght 400–700, opsz 9–40), Latin subset, about 60 KB.
  - Fraunces variable (wght 500–700, opsz 9–144), Latin subset, about 90 KB.
- Declare them with `@font-face { font-display: swap; }` in `01-tokens.css`. Add `<link rel="preload" as="font" type="font/woff2" crossorigin>` for the two text faces.
- Add metric-matched fallbacks (`size-adjust`, `ascent-override`) to kill reflow:
  - `"DM Sans Fallback"`: Arial with `size-adjust: 104%`.
  - `"Fraunces Fallback"`: Georgia with `size-adjust: 103%`.
- Replace Material Symbols with an SVG sprite of the glyphs actually used. DESIGN.md locks 12 title glyphs, and there are 38 call sites across 18 files.

**Rationale:** The product sells sovereignty. Its typography should not phone home. Self-hosting also removes the icon-word flash.

**User story:** As an owner who chose a self-hosted curator for privacy, I want zero third-party requests on page load.

**Acceptance criteria**
- [ ] 0 requests to `*.googleapis.com` and `*.gstatic.com` on `/login`, `/chat`, and `/explore`.
- [ ] Cumulative Layout Shift from the font swap is under 0.02.
- [ ] The icon payload is under 20 KB.

**Success metric:** Third-party origins in a HAR file = 0.

**Validation:** Playwright `page.on('request')` origin allowlist test, plus a Lighthouse CLS check.

### VIS-018: Cap reading measure at 68ch of the article font

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Public |
| Persona(s) | Older / low vision, Non-native-language, First-time visitor |
| Category | Type |
| Severity | Medium |
| Impact | 3 |
| Effort | XS |
| Confidence | Likely |
| Priority score | 4.80 |
| Verdict | Fix |
| Dependencies | VIS-006 |
| Labels | help, about, reading, measure |

**Evidence**
- `qa_help_guest_1440.png`: the first body line "Projectionist is a private cinema companion for the library you already own. It talks to" is **89 characters**.
- `qa_about_1440.png`: "Projectionist grew out of living with a big personal library and wanting a curator who knew it" is about **93 characters**.
- `qa_owner_newsletters_1440.png`: the intro wraps at about 83 characters.
- `06-reading-admin-settings.css`, `.help-page .help-main { width: min(65ch, 100%) }`. `ch` is computed from the *container* font size (15px root), while the article renders larger, so the effective measure exceeds 65 characters. `.about-page .about-main { width: min(720px, 100%) }` is px-based.

**Current state:** Long-form text runs 83–93 characters per line, beyond the 45–75 comfort band.

**Root cause:** The measure is set on the wrong element, in mixed units.

**Recommendation:** Set `max-width: 68ch` on `.help-article p, .help-article li, .about-page .explore-section p, .admin-page-intro`, all of which use the body font at `--text-base`. Set the long-form `line-height` to 1.65 (`--leading-relaxed`).

**Rationale:** Help and About are the product's teaching voice, and they must be comfortable to read.

**User story:** As an older member reading Help on a tablet, I want lines short enough to track without losing my place.

**Acceptance criteria**
- [ ] Body lines are 75 characters or fewer at 1440 on Help, About, Privacy, and Newsletters intros.
- [ ] No change at 390.

**Success metric:** Median characters per line ≤ 70 (script: `Range.getClientRects` per paragraph).

**Validation:** Screenshot comparison plus a JS measurement in the Playwright visual spec.

### VIS-003: Invert the button default; add a field primitive

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Cross-cutting |
| Persona(s) | All; engineers extending UI |
| Category | Components |
| Severity | High |
| Impact | 4 |
| Effort | M |
| Confidence | Confirmed |
| Priority score | 4.00 |
| Verdict | Rethink |
| Dependencies | VIS-001, VIS-024 |
| Labels | components, buttons, inputs, primitives |

**Evidence**
- `02-nav-chrome.css`: `button, .btn-link { background: var(--accent); color: var(--accent-text); padding: 9px 14px; border-radius: var(--radius-sm); font-size: var(--text-sm); font-weight: 600; … }`. **Every** `<button>` is a gold primary unless overridden.
- There are 22 button-variant roots: `.btn-primary`, `.btn-danger`, `.login-primary`, `.login-secondary`, `.title-cta-primary`, `-secondary`, `-ghost`, `-danger`, `.title-detail-cta-primary`, `-secondary`, `.recommendation-cta-primary`, `.explore-search-submit`, `.explore-section-toolbar-primary`, `.media-browse-secondary`, `.live-chrome-secondary`, `.theater-osd-secondary`, `.dash-purge-btn--danger`, `.app-topbar-icon`, and others. On top of these sit `button.ghost`, `.btn-link`, and `.primary`.
- Hover is `filter: brightness(1.06)`, which shifts the hue of amber and does nothing to transparent buttons.
- There is no base `input`, `select`, or `textarea` rule (see VIS-002).

**Current state:** "Primary" is the default, which contradicts DESIGN.md's "one gold primary" rule. The many neutral icon and ghost buttons each restate `background: transparent`.

**Root cause:** The element selector was used as a component.

**Recommendation:** Create `.btn` with `data-variant` and `data-size` attributes (specs in the consolidation plan below). Then change the element rule to a neutral reset: `button { font: inherit; color: inherit; background: none; border: 0; padding: 0; cursor: pointer; }`. Ship the reset only *after* `git grep -n "<button"` call sites carry a class. Create `.field`, `.input`, `.select`, and `.textarea` with 44px height, a 6px radius, `--border-field`, and `--focus-ring`.

**Rationale:** A neutral default plus explicit variants is the only way the "one gold primary" rule survives growth.

**User story:** As an engineer adding a control, I want a plain button by default, so that I do not accidentally add a second gold primary.

**Acceptance criteria**
- [ ] `.btn` has five variants and three sizes, documented in DESIGN.md.
- [ ] Bare `<button>` renders neutral.
- [ ] No screen has more than one `[data-variant=primary]` per action group.

**Success metric:** Button-variant roots drop from about 25 to 5 variants × 3 sizes.

**Validation:** A Playwright count of elements with an `--accent-fill` background per route is ≤ 1 per CTA region, plus a visual diff.

### VIS-011: Replace five loading idioms with one skeleton

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Consumer |
| Persona(s) | Returning consumer, Low-bandwidth mobile |
| Category | Components |
| Severity | Medium |
| Impact | 4 |
| Effort | S |
| Confidence | Confirmed |
| Priority score | 4.00 |
| Verdict | Fix |
| Dependencies | VIS-012 |
| Labels | loading, skeleton, explore, perceived-performance |

**Evidence**
- `qa_owner_explore_1440.png` shows "Filling in shelves…" as 14px muted text above a blank band of about 80px, with "For you" cut off below. The platform map notes a long "Loading titles…" before For you filled.
- There are five idioms at 94fcd3f:
  - Text in `ExplorePage.tsx` ("Filling in shelves…", "Loading titles…").
  - A spinner in `PosterRailLoader.tsx` (`poster-rail-spin 0.8s`).
  - `.dash-skeleton` (`07-persona-editorial.css`, `dash-shimmer 1.4s`).
  - `.live-guide-skeleton` (`12-live.css`).
  - `.browse-grid-pending-card` shimmer (`03-browse-controls.css`).

**Current state:** The wait looks different on every page. The poster surfaces, which are the most visual, get the least visual loading state.

**Root cause:** There is no loading primitive.

**Recommendation:** Build `.skeleton` with modifiers `--line` (12px tall, radius 4), `--block`, and `--poster` (`aspect-ratio: 2/3; width: var(--rail-card-width)` on phone or 160px on desktop; radius `--radius-sm`). Use a fill of `color-mix(in srgb, var(--text) 6%, var(--surface))` and a 1.4s shimmer that is static under reduced motion. Explore hub loading renders three rails × 6 poster skeletons plus a 20px × 160px title bar. Keep a single visually-hidden live text: "Loading your shelves".

**Rationale:** A skeleton preserves layout (no CLS when rails arrive) and promises posters.

**User story:** As a member opening Explore after dinner, I want to see shelves forming, not a sentence.

**Acceptance criteria**
- [ ] One `.skeleton` primitive, with the four old idioms removed or aliased.
- [ ] Explore hub CLS is under 0.05 from skeleton to content.

**Success metric:** Loading-idiom class roots drop from 5 to 1.

**Validation:** Throttled Playwright run (Slow 3G) with screenshots at 300ms and at completion.

### VIS-015: Treat Lights Up as a co-equal default

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Cross-cutting |
| Persona(s) | Older / low vision, Owner, All light-OS users |
| Category | Brand |
| Severity | Medium |
| Impact | 4 |
| Effort | S |
| Confidence | Confirmed |
| Priority score | 4.00 |
| Verdict | Rethink |
| Dependencies | VIS-001, VIS-004, VIS-008 |
| Labels | brand, theme, docs, sacred-cow |

**Evidence**
- `docs/DESIGN.md` says "Lights Down `lights_down` (default)".
- `94fcd3f:frontend/index.html` FOUC script: `stored = stored || "system"`, which resolves to Lights Up when `prefers-color-scheme: light`.
- 6 of the 12 run screenshots render in Lights Up: all five `qa_owner_*` captures plus `qa_login_local_1440.png`. Member, youth, and guest captures are Lights Down.
- Theme overrides are 88 `lights-up` selectors versus 1 `lights-down`.

**Current state:** The design is reviewed and tuned in Lights Down, while a large share of real users run Lights Up.

**Root cause:** The brand doc and the runtime default disagree.

**Recommendation:** Keep `system` as the runtime default. It respects users and serves the low-vision persona. Change DESIGN.md to "Lights Down is the *signature*; Lights Up is co-equal and must pass the same contrast table." Require both-theme screenshots in every UI PR, as in VIS-043.

**Rationale:** You cannot protect a brand that only half your users see.

**User story:** As an owner on a light-mode laptop, I want the app to look intentional, not inverted.

**Acceptance criteria**
- [ ] DESIGN.md is corrected.
- [ ] The token contrast table below passes for both themes.
- [ ] PR template has a "both themes" checkbox.

**Success metric:** Lights Up-only override selectors drop from 88 to ≤ 10.

**Validation:** A doc diff plus a grep count.

### VIS-024: Give form fields a 3:1 boundary

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Cross-cutting |
| Persona(s) | Older / low vision, Owner (dense forms) |
| Category | Color |
| Severity | Medium |
| Impact | 4 |
| Effort | S |
| Confidence | Confirmed |
| Priority score | 4.00 |
| Verdict | Fix |
| Dependencies | VIS-003 |
| Labels | contrast, inputs, borders, tokens |

**Evidence:** Field rules (`.settings-field input…`, `.library-search--hero`, composer) draw boundaries with `--border`. That is `#2c313c` on `#101218` = **1.44:1** in Lights Down, and `#d0c5af` on `#fbf9f4` = **1.62:1** in Lights Up. In `qa_owner_chat_1440.png` the composer box edge is barely distinguishable from the surface.

**Current state:** One border token is used for both decorative dividers and interactive boundaries.

**Root cause:** There is no field-specific token.

**Recommendation:** Add `--border-field`: `#6a7181` in Lights Down (3.33–3.97:1 on all four surfaces) and `#857a68` in Lights Up (3.64–4.22:1). Use it on inputs, selects, textareas, checkboxes, and the composer. Keep `--border` and `--border-subtle` for decoration.

**Rationale:** Field edges are affordances, not ornament.

**User story:** As a member with low contrast sensitivity, I want to see where I type.

**Acceptance criteria**
- [ ] All text-entry boundaries are at least 3:1 against their adjacent surface in both themes.

**Success metric:** Field-boundary contrast failures drop from all fields to 0.

**Validation:** A computed-style script over all `input, textarea, select` on `/settings/profile`, `/admin/connections`, and `/chat`.

### VIS-009: Give the fixed footer a home

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Owner |
| Persona(s) | Owner, Member (Settings) |
| Category | Layout |
| Severity | Medium |
| Impact | 3 |
| Effort | S |
| Confidence | Confirmed |
| Priority score | 3.00 |
| Verdict | Fix |
| Dependencies | none |
| Labels | footer, overlap, layout |

**Evidence**
- `08-dashboard-coverage-cards.css`, `.app-footer { position: fixed; bottom: 0; right: 0; z-index: 4; … pointer-events: none; }`. There is no background. Links are `--muted` at `opacity: 0.6`, which measures **3.11:1** in Lights Up and **3.05:1** in Lights Down.
- In `qa_owner_admin_overview_1440.png`, "Help · Privacy · About" sits *inside* the "5,391 Indexed" tile, overlapping "4594 movies · 797 shows". The same overlap appears over the Weekly household letter card in `qa_owner_newsletters_1440.png`.

**Current state:** The footer floats over content on every scrolling Admin page.

**Root cause:** A fixed position was chosen to keep the footer visible on the chat living room and then applied everywhere.

**Recommendation:** On AppShell and Admin pages, make the footer static (`position: static; padding: var(--space-6) var(--space-5); border-top: 1px solid var(--border-subtle)`) at the end of `main`. Keep the fixed variant only on `.app-root.workspace` (chat), with `background: color-mix(in srgb, var(--bg) 85%, transparent)` and `backdrop-filter: blur(8px)`. Remove `opacity: 0.6` and use `--muted` at full strength (5.47–9.36:1).

**Rationale:** Legal and help links should never collide with data.

**User story:** As an owner reading stats, I want nothing written on top of my numbers.

**Acceptance criteria**
- [ ] The footer bounding box intersects no `.owner-health-tile` or `.config-section` at any scroll position on Admin pages.
- [ ] Footer link contrast is at least 4.5:1.

**Success metric:** Overlap count = 0 in a Playwright intersection test.

**Validation:** Scroll-step screenshots of `/admin/overview` and `/admin/newsletters`.

### VIS-013: Retire emoji and Unicode glyph icons

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Consumer |
| Persona(s) | All; Screen-reader users (hidden glyph reliance) |
| Category | Iconography |
| Severity | Medium |
| Impact | 3 |
| Effort | S |
| Confidence | Confirmed |
| Priority score | 3.00 |
| Verdict | Fix |
| Dependencies | VIS-014 (sprite) |
| Labels | icons, emoji, consistency |

**Evidence**
- `MessageReactions.tsx` renders `👍` and `👎` as emoji. They appear in full-color OS yellow in `qa_member_chat_390.png` and `qa_youth_nav_1440.png`, the only saturated non-amber color on the page.
- `AppNav.tsx` uses `☰`. `ChatWorkspace.tsx` and `StatusDock.tsx` use `⧉` (rendered as a 10px glyph before "General Exploration" in `qa_owner_chat_1440.png`). `PersonaSelector.tsx` uses `★` and `☆`. `ReviewPromptCard.tsx` uses `★`. The chat sidebar collapse uses `«`.
- Elsewhere the app uses Material Symbols (38 uses in 18 files) and 15 inline `<svg>`s.

**Current state:** Four icon systems are in use: Material ligatures, Unicode text, emoji, and SVG. Weight and baseline vary. The emoji ignore the theme.

**Root cause:** Icons were picked per component, with no icon component.

**Recommendation:** Build one `<Icon name size>` component backed by the SVG sprite from VIS-014. Sizes are 16 / 20 / 24px, strokes 1.5px at 24px. Color is always `currentColor`. Map the glyphs as follows:

| Current | Replacement |
|---|---|
| 👍 / 👎 | `thumb_up` / `thumb_down` |
| ☰ | `menu` |
| ⧉ | `label` |
| ★ / ☆ | `star` (filled) / `star` (outline) |
| « | `left_panel_close` |
| × | `close` |

**Rationale:** Icons in the cinema chamber should be quiet ink, not stickers.

**User story:** As a member, I want reactions and controls that look like they belong to Projectionist.

**Acceptance criteria**
- [ ] 0 emoji code points in `frontend/src/components/*.tsx` UI chrome. Message content is exempt.
- [ ] All icons inherit `currentColor`.

**Success metric:** Icon systems in use drop from 4 to 1.

**Validation:** `git grep -P "[\x{1F300}-\x{1FAFF}]|☰|⧉|★|☆"` across components returns 0 chrome hits.

### VIS-022: Add a warning hue; stop using amber for warn

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Owner |
| Persona(s) | Owner, Established owner at scale |
| Category | Color |
| Severity | Medium |
| Impact | 3 |
| Effort | S |
| Confidence | Confirmed |
| Priority score | 3.00 |
| Verdict | Add |
| Dependencies | VIS-007 |
| Labels | semantic-color, status, admin |

**Evidence**
- `10-explore-delight.css`, `.owner-health-tile.tone-warn .owner-health-tile-value { color: var(--accent); }`.
- `var(--warning, #c9a227)` (10) and `var(--warning-text, #c9842a)` (06) reference **undefined** tokens. Their fallbacks measure 2.30:1 and 2.93:1 on Lights Up surface.
- `.streak-chip` uses `rgba(251,191,36,…)`, an off-palette amber.

**Current state:** A warning reads as "brand highlight". Status has success and danger tokens but no warning or info token.

**Root cause:** The semantic palette is incomplete.

**Recommendation:** Add `--status-warning` (`#f2a65a` Lights Down at 8.06–9.60:1; `#8f4a00` Lights Up at 5.75–6.67:1) and `--status-info` (`#8fb4d9` at 7.53–8.98:1; `#2b5a8a` at 6.18–7.16:1). Each gets a `-soft` background at 14% mix. Warnings pair with a `warning` icon so color is not the only cue.

**Rationale:** Amber means "Projectionist", not "attention".

**User story:** As an owner scanning health tiles, I want warnings that look like warnings.

**Acceptance criteria**
- [ ] `tone-warn` uses `--status-warning`.
- [ ] 0 references to undefined `--warning*`.

**Success metric:** Semantic status tokens go from 2 to 4, all AA in both themes.

**Validation:** Token contrast script plus a visual check of `/admin/overview` with a forced warn tile.

### VIS-007: Define the phantom tokens and kill literals

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Cross-cutting |
| Persona(s) | Engineers; all users indirectly |
| Category | Tokens |
| Severity | Medium |
| Impact | 4 |
| Effort | M |
| Confidence | Confirmed |
| Priority score | 2.67 |
| Verdict | Fix |
| Dependencies | none |
| Labels | tokens, drift, lint |

**Evidence**
- 11 referenced-but-undefined custom properties:
  - `--radius-md`: 11 uses, with fallbacks 8px ×4, 0.65rem ×3, 10px ×2, and 12px ×1.
  - `--foreground` ×3, with no fallback.
  - `--text-secondary` ×3, with no fallback.
  - `--gold` ×4 (`#c6a15b`).
  - `--warning`, `--warning-text`, `--text-muted`, `--surface-3`, `--surface-elevated`, `--accent-strong`, `--fg`.
- 137 hex literals sit outside `01-tokens.css`, 62 of them in `10-explore-delight.css` (for example, `#c4a35a` ×20 as an `--accent` fallback that is a *different* gold).
- `--bp-phone`, `--bp-tablet`, and `--bp-desktop` are defined in `06` but have 0 uses (custom properties cannot be used in `@media`).
- 0 shadow, z-index, or motion tokens.

**Current state:** The token file is a suggestion, not a contract.

**Root cause:** There is no lint rule and the fallback habit masks misses.

**Recommendation:** Define every phantom, or rename its call sites to an existing token (`--foreground` → `--text`, `--text-secondary` → `--muted`, `--surface-elevated` → `--surface-raised`, `--gold` → `--accent-fill`). Define `--radius-md: 10px`. Remove all `var(--x, #hex)` fallbacks. Add the shadow, z, and motion tokens from the proposal below. Add Stylelint `scale-unlimited/declaration-strict-value` for `color`, `background-color`, `border-color`, `box-shadow`, `z-index`, and `font-size`.

**Rationale:** Drift compounds, and every fallback is a future Lights Up bug.

**User story:** As an engineer, I want a missing token to fail lint, not silently paint the wrong gold.

**Acceptance criteria**
- [ ] 0 undefined custom properties (script: used minus defined, after excluding the runtime-inline allowlist).
- [ ] Hex literals outside tokens drop from 137 to ≤ 10 (media and picture exceptions).

**Success metric:** Token adoption for font-size goes from 57% to ≥ 95%, spacing from 38% to ≥ 85%, and radius from 47% to ≥ 95%.

**Validation:** Stylelint in CI and the inventory script re-run.

### VIS-006: Rebuild the type scale with a 12px floor

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Cross-cutting |
| Persona(s) | Older / low vision, Low-bandwidth mobile, All |
| Category | Type |
| Severity | High |
| Impact | 4 |
| Effort | L |
| Confidence | Confirmed |
| Priority score | 2.40 |
| Verdict | Rethink |
| Dependencies | VIS-007, VIS-043 |
| Labels | typography, scale, tokens |

**Evidence**
- `01-tokens.css` scale: `--text-xs .75rem`, `-sm .8125rem`, `-md .9375rem`, `-base 1rem`, `-lg 1.125rem`, `-xl 1.375rem`, `-2xl 1.75rem`. Root is `--base-font-size` (13/15/17px via `uiPrefs.ts`).
- At Medium those resolve to 11.25 / 12.19 / 14.06 / 15 / 16.88 / 20.63 / 26.25px. Step ratios are 1.083, 1.154, 1.067, 1.125, 1.222, and 1.273. That is not a scale.
- At Small, `--text-xs` is **9.75px** and `--text-sm` is 10.56px.
- Usage: `--text-sm` ×182 and `--text-xs` ×120 are the two most-used sizes. About 417 of 691 font-size declarations (≈60%) resolve below 12.5px at Medium.
- 97 distinct font-size values. 142 px literals (14px ×37, 12px ×27, 13px ×26, 11px ×23, 10px ×3) do not follow the user's size preference. There are 24 bespoke `clamp()` headlines.
- `markdown-body` headings are em-based at 1.35 / 1.2 / 1.05 (VIS-019).

**Current state:** UI chrome is mostly 11–12px. The Small preference makes it unreadable, and px literals break the Large preference.

**Root cause:** Steps were added as needed and never re-derived.

**Recommendation:** Adopt the v2 scale in the token proposal: a 1.2 ratio on a 16px Medium root, with Small at 15px and Large at 18px. Set `--text-xs: max(12px, 0.75rem)` as a hard floor. Replace all px and rem literal font-sizes with tokens, and allow `clamp()` only via `--text-display`. Migrate in two passes (see the migration path) behind visual diffs.

**Rationale:** A real scale gives hierarchy for free, and the floor protects the font-size preference that already exists.

**User story:** As an older member who picks "Small" by mistake, I want text that is still legible.

**Acceptance criteria**
- [ ] ≤ 12 distinct font-size values in CSS, all via tokens.
- [ ] No computed font-size below 12px on any route at any preference.

**Success metric:** Distinct font-size values drop from 97 to ≤ 12.

**Validation:** A computed-style sweep (`document.querySelectorAll('*')`) on 10 routes × 3 preferences.

### VIS-008: Fold Live/Watch theme patches into tokens

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Consumer |
| Persona(s) | Power consumer, Returning consumer |
| Category | Tokens |
| Severity | Medium |
| Impact | 3 |
| Effort | M |
| Confidence | Confirmed |
| Priority score | 2.00 |
| Verdict | Fix |
| Dependencies | VIS-007 |
| Labels | live, watch, theme, tokens |

**Evidence:** `html[data-theme="lights-up"]` selectors: `12-live.css` ×64, `13-watch.css` ×21, `01`, `03`, and `10` ×1 each. `13-watch.css` also has 14 hex literals. `--live-bg`, `--live-panel`, and `--live-line` exist but cover only three roles.

**Current state:** Live was built dark, then patched for light selector by selector.

**Root cause:** Component tokens are missing for the "stage" (guide grid, OSD, cells).

**Recommendation:** Add `--stage-bg`, `--stage-panel`, `--stage-cell`, `--stage-cell-active`, `--stage-line`, `--stage-ink`, and `--stage-muted` per theme in `01-tokens.css`, then delete the override selectors. The picture itself stays `--picture-black` in both themes, by design.

**Rationale:** One fix in tokens replaces 85 fixes in selectors.

**User story:** As a member on Lights Up, I want the guide to feel like the same product as Explore.

**Acceptance criteria**
- [ ] `lights-up` selectors in `12-live.css` and `13-watch.css` drop from 85 to ≤ 6.

**Success metric:** Override count, measured by grep.

**Validation:** Both-theme screenshots of `/live` (guide) once Live is enabled on QA.

### VIS-017: Stop the profile avatar from squashing

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Consumer |
| Persona(s) | Household member |
| Category | Polish |
| Severity | Low |
| Impact | 2 |
| Effort | XS |
| Confidence | Confirmed |
| Priority score | 2.00 |
| Verdict | Fix |
| Dependencies | none |
| Labels | avatar, settings, flex |

**Evidence:** `qa_member_settings_1440.png` shows the "QA" avatar as a vertical oval, about 50 × 86px. In `06-reading-admin-settings.css`, `.settings-avatar { width: 56px; height: 56px; border-radius: 50% }` sits inside `.settings-identity { display:flex }` with no `flex-shrink: 0`, so the wrapping text column compresses it.

**Current state:** The avatar is distorted at narrow widths.

**Root cause:** A flex child is missing its shrink guard.

**Recommendation:** Add `flex: 0 0 56px; aspect-ratio: 1;` and `align-self: flex-start`.

**Rationale:** An avatar is identity, and distortion reads as broken.

**User story:** As a member, I want my avatar to stay round.

**Acceptance criteria**
- [ ] The avatar's bounding box is 56 × 56 at 320–1440px widths.

**Success metric:** Width equals height in Playwright.

**Validation:** Screenshot at 390.

### VIS-019: Give chat markdown headings a real hierarchy

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Consumer |
| Persona(s) | Power consumer |
| Category | Type |
| Severity | Low |
| Impact | 2 |
| Effort | XS |
| Confidence | Confirmed |
| Priority score | 2.00 |
| Verdict | Fix |
| Dependencies | VIS-006 |
| Labels | chat, markdown, typography |

**Evidence:** In `02-nav-chrome.css`, `.markdown-body h1 { 1.35em } h2 { 1.2em } h3 { 1.05em }`, all DM Sans 600 with `line-height: 1.3`. Meanwhile `.privacy-prose h1–h3` use Fraunces, so the same markdown looks different in chat and in docs.

**Current state:** An h3 at 1.05em is barely distinct from bold body text.

**Root cause:** These were ad-hoc em steps.

**Recommendation:** In curator replies, set h1 and h2 to Fraunces 600 at `--text-xl` (20px) and `--text-lg` (18px), and h3 and h4 to DM Sans 600 at `--text-base` with `--tracking-caps` small caps. Set margins to `var(--space-5) 0 var(--space-2)`.

**Rationale:** The curator's voice should carry the brand display face for section heads.

**User story:** As a power user reading a long comparison, I want scannable sections.

**Acceptance criteria**
- [ ] Each heading step is at least 1.125× the next.

**Success metric:** Heading sizes in replies come from tokens only.

**Validation:** A fixture message rendered in a unit or visual test.

### VIS-020: Collapse 16 breakpoints to 4

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Cross-cutting |
| Persona(s) | Low-bandwidth mobile, tablet users |
| Category | Layout |
| Severity | Medium |
| Impact | 3 |
| Effort | M |
| Confidence | Confirmed |
| Priority score | 2.00 |
| Verdict | Fix |
| Dependencies | VIS-007 |
| Labels | responsive, breakpoints |

**Evidence:** The 76 `@media` rules use 16 width thresholds: 390, 560, 640, 720, 760, 768, 769, 840, 900, 901, 926, 960, 1024, 1100, 1280, and 1440. Near-duplicates are 720/760/768/769 and 900/901/926/960. Defined `--bp-*` tokens have 0 uses.

**Current state:** Components reflow at different widths, so an iPad in portrait shows mixed phone and desktop chrome.

**Root cause:** Each sheet picked its own threshold.

**Recommendation:** Use four tiers: **sm 640**, **md 768**, **lg 1024**, **xl 1440**. Map 560 and 640 to sm, 720 / 760 / 768 / 769 to md, and 840 / 900 / 901 / 926 / 960 / 1024 / 1100 to lg, auditing each. Map 1280 and 1440 to xl. Keep the phone-landscape `(orientation: landscape) and (max-height: 500px)` and the `(hover: none)` queries. Enforce with Stylelint `media-feature-range-notation` and an allowlist, or `postcss-custom-media` (`@custom-media --md (max-width: 768px)`).

**Rationale:** Four tiers can be tested, and sixteen cannot.

**User story:** As a member on an iPad, I want one coherent layout per orientation.

**Acceptance criteria**
- [ ] ≤ 4 width thresholds in CSS, plus the two orientation and hover exceptions.

**Success metric:** Distinct width thresholds drop from 16 to 4.

**Validation:** A grep count plus screenshots at 390, 768, 1024, and 1440.

### VIS-023: Use only loaded font weights

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Cross-cutting |
| Persona(s) | All |
| Category | Type |
| Severity | Low |
| Impact | 2 |
| Effort | XS |
| Confidence | Confirmed |
| Priority score | 2.00 |
| Verdict | Fix |
| Dependencies | VIS-014 |
| Labels | typography, weights |

**Evidence:** Weights in use are 600 ×119, 500 ×30, 700 ×27, 650 ×10, 400 ×6, and 800, 560, 550, and `normal` ×1 each. `index.html` loads DM Sans at 400/500/600/700 and Fraunces at 500/600/700 only. 650 snaps to 700, 550 and 560 snap to 600, and 800 snaps to 700. `.app-nav-heading-side` asks Fraunces for 650.

**Current state:** The intended nuance never renders, and the declared values mislead.

**Root cause:** The CSS assumes variable fonts, but static instances are loaded.

**Recommendation:** Limit tokens to `--weight-regular 400`, `--weight-medium 500`, `--weight-semibold 600`, and `--weight-bold 700`. If VIS-014 ships variable files, still restrict to these four for consistency.

**Rationale:** What you declare should be what you see.

**User story:** As a designer, I want weight tokens that match rendering.

**Acceptance criteria**
- [ ] 0 font-weight values outside {400, 500, 600, 700}.

**Success metric:** Distinct weights drop from 9 to 4.

**Validation:** Grep.

### VIS-026: Drop monospace from the composer context tag

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Consumer |
| Persona(s) | Returning consumer |
| Category | Type |
| Severity | Low |
| Impact | 2 |
| Effort | XS |
| Confidence | Confirmed |
| Priority score | 2.00 |
| Verdict | Fix |
| Dependencies | VIS-001, VIS-013 |
| Labels | chat, composer, mono |

**Evidence:** `qa_owner_chat_1440.png` and `qa_youth_nav_1440.png` show "⧉ General Exploration" in a gold monospace face above the composer. There are 6 monospace stacks in CSS. `--font-mono` is used 9 times, plus 7 literal stacks.

**Current state:** A developer-console texture in the living-room composer. It reads as a code label, not a context, and measures 3.25:1 in Lights Up.

**Root cause:** Mono was used to mean "system metadata".

**Recommendation:** Render the tag in DM Sans 500, `--text-xs` (12px), `--tracking-caps` 0.08em, uppercase, color `--accent-ink`, with a 16px `label` icon. Restrict mono to code, MCP keys, and logs.

**Rationale:** Living-room chrome should speak the house type.

**User story:** As a member, I want the context label to feel like part of the conversation.

**Acceptance criteria**
- [ ] `--font-mono` appears only on `code`, `pre`, `.mcp-key-*`, and `.logs-*`.

**Success metric:** Mono stacks drop from 6 to 1 token.

**Validation:** Grep plus a chat screenshot.

### VIS-016: Replace rotated admin group labels

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Owner |
| Persona(s) | New owner, Established owner at scale |
| Category | Layout |
| Severity | Low |
| Impact | 2 |
| Effort | XS |
| Confidence | Likely |
| Priority score | 1.60 |
| Verdict | Rethink |
| Dependencies | none |
| Labels | admin-nav, drawer, typography |

**Evidence**
- `qa_owner_admin_nav_1440.png` shows "PLATFORM" and "…MUNICATIONS" set vertically, rotated 180°, in Fraunces small caps beside the link lists.
- `02-nav-chrome.css`, `.app-nav-heading-side { writing-mode: vertical-rl; transform: rotate(180deg); font-size: 0.78rem; font-weight: 650; letter-spacing: 0.12em }`. "COMMUNICATIONS" (14 characters) at 11.7px + 0.12em is about 150px, longer than a two-link band (about 112px), so it overflows its band.

**Current state:** The labels are clever but hard to read: bottom-to-top, serif at about 12px, and an unloaded weight.

**Root cause:** A decorative choice was made at the expense of legibility.

**Recommendation:** Use horizontal eyebrows: DM Sans 600, `--text-xs` (12px), uppercase, `--tracking-caps` 0.08em, `--muted`, with `padding: var(--space-4) var(--space-3) var(--space-1)`. Keep the tinted group bands.

**Rationale:** Admin is a tool, so legibility beats flourish.

**User story:** As an owner hunting for Mail, I want to read group names at a glance.

**Acceptance criteria**
- [ ] No `writing-mode` in nav.
- [ ] Group labels fit on one line at 280px drawer width.

**Success metric:** 0 rotated labels.

**Validation:** Drawer screenshot.

### VIS-021: Consolidate component variants

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Cross-cutting |
| Persona(s) | Engineers; all users (consistency) |
| Category | Components |
| Severity | Medium |
| Impact | 4 |
| Effort | L |
| Confidence | Confirmed |
| Priority score | 1.60 |
| Verdict | Rethink |
| Dependencies | VIS-003, VIS-007, VIS-011 |
| Labels | components, sprawl |

**Evidence:** Root counts at 94fcd3f:

| Component | Roots |
|---|---:|
| Card | 40 |
| Chip | 24 |
| Badge | 21 (including `.badge`) |
| Modal | 10 |
| Backdrop / scrim / overlay | 13 |
| Table | 9 |
| Tab set | 8 |
| Popover | 6 |
| Toast | 1 (`.undo-toast`) |
| Button-ish | ≈25 |

Radii on cards vary between `--radius` (10), 12px literal (`.owner-health-tile`), and `--radius-lg` (14). `qa_owner_explore_1440.png` shows hub link cards with amber 1px borders. `qa_owner_admin_overview_1440.png` shows tiles with `--border`. `qa_owner_newsletters_1440.png` shows a `--surface-2` panel. These are three card looks on owner screens alone.

**Current state:** Each feature owns its look.

**Root cause:** There is no primitives layer.

**Recommendation:** See the component consolidation plan below.

**Rationale:** Fewer, better components equal coherence plus faster features.

**User story:** As an engineer, I want to compose a page from five well-made parts, not invent a sixth card.

**Acceptance criteria**
- [ ] Target counts in the plan are reached.
- [ ] No new `-card` or `-chip` root without a design review.

**Success metric:** Total component roots drop from about 157 to about 30.

**Validation:** Re-run the inventory script.

### VIS-025: Unify the three header chromes

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Public |
| Persona(s) | First-time visitor, Household member |
| Category | Brand |
| Severity | Medium |
| Impact | 3 |
| Effort | M |
| Confidence | Likely |
| Priority score | 1.60 |
| Verdict | Rethink |
| Dependencies | VIS-015 |
| Labels | chrome, topbar, brand |

**Evidence**
- **Chat** (`qa_owner_chat_1440.png`) has a grey top bar and grey sidebar (`--surface` 88% over the workspace gradient) with an amber hairline under the bar.
- **AppShell pages** (`qa_owner_explore_1440.png`, `qa_owner_admin_overview_1440.png`) have a paper top bar with a grey hairline.
- **Help and About** (`qa_help_guest_1440.png`, `qa_about_1440.png`) have no brand mark. Instead they show a Fraunces page title, a subtitle, and "← Back to chat".
- On 390 Lights Down (`qa_member_chat_390.png`) the bar hairline is amber. At 1440 Lights Down (`qa_youth_nav_1440.png`) it is grey.

**Current state:** Three header treatments carry the same brand.

**Root cause:** Separate shells (workspace, AppShell, reading page) evolved separately.

**Recommendation:** Use one `.app-topbar` with: 64px height (56px under 640px), `--surface` at 92% with `backdrop-filter: blur(12px)`, a 1px `--border-subtle` bottom border (no amber hairline), and the brand mark always on the left. Reading pages put their title *below* the bar as a page header (Fraunces `--text-3xl`). "Back to chat" becomes a BackLink in the page header.

**Rationale:** The brand mark should always be in the same place.

**User story:** As a guest landing on Help from a link, I want to know which product I am in.

**Acceptance criteria**
- [ ] All authenticated and public reading routes render the same top bar component.

**Success metric:** Top-bar variants drop from 3 to 1.

**Validation:** Screenshot set of five routes.

---

## Strengths

### VIS-030: Protect Lights Down contrast tuning

| Field | Value |
|---|---|
| Type | Strength |
| Surface | Cross-cutting |
| Persona(s) | All; Older / low vision |
| Category | Color |
| Severity | High |
| Impact | 5 |
| Effort | XS |
| Confidence | Confirmed |
| Priority score | 15.00 |
| Verdict | Protect |
| Dependencies | none |
| Labels | color, brand, contrast |

**Evidence:** Lights Down `--text #e6e2d6` measures 15.01:1 on bg, 14.45:1 on surface, 13.43:1 on surface-2, and 12.59:1 on raised. `--muted #9a958a` is 5.47–6.52:1. `--accent #ffb800` is 9.40–11.21:1. `--accent-text` on accent is 10.68:1. Danger and success are 7.89 and 8.33:1. `qa_join_empty_1440.png`, `qa_about_1440.png`, and `qa_youth_nav_1440.png` read cleanly.

**Current state:** The warm cream ink on near-black blue-grey is cinematic *and* compliant.

**Root cause:** Careful token choices.

**Recommendation:** Freeze these values. Any change must keep every pair in the token table at or above its current ratio.

**Rationale:** This palette is the brand's best asset.

**User story:** As a member watching at night, I want comfortable contrast without glare.

**Acceptance criteria**
- [ ] A token contrast test in CI fails if any Lights Down pair drops below the proposed table.

**Success metric:** 0 regressions.

**Validation:** A unit test computing the ratios from `01-tokens.css`.

### VIS-031: Protect the theme architecture and FOUC guard

| Field | Value |
|---|---|
| Type | Strength |
| Surface | Cross-cutting |
| Persona(s) | All |
| Category | Tokens |
| Severity | High |
| Impact | 4 |
| Effort | XS |
| Confidence | Confirmed |
| Priority score | 12.00 |
| Verdict | Protect |
| Dependencies | none |
| Labels | theme, architecture |

**Evidence:** Colors live only on `html[data-theme]` in `01-tokens.css`. The inline script in `index.html` resolves `system` against `prefers-color-scheme`, migrates the `curatorx.ui_theme` legacy key, and sets `colorScheme` before first paint. `color-mix()` is used 314 times to derive tints from tokens.

**Current state:** Theme swaps cost zero JavaScript and do not flash.

**Root cause:** A good early decision.

**Recommendation:** Keep it. Extend it with semantic and component layers (see the token proposal) rather than per-selector theme overrides.

**Rationale:** This is the right foundation to scale on.

**User story:** As a member, I want my theme to apply instantly on load.

**Acceptance criteria**
- [ ] No new `html[data-theme]` selectors outside `01-tokens.css`. Enforce with lint.

**Success metric:** Override selectors trend toward 0.

**Validation:** Grep in CI.

### VIS-033: Protect the Fraunces + DM Sans voice

| Field | Value |
|---|---|
| Type | Strength |
| Surface | Cross-cutting |
| Persona(s) | All |
| Category | Brand |
| Severity | High |
| Impact | 4 |
| Effort | XS |
| Confidence | Confirmed |
| Priority score | 12.00 |
| Verdict | Protect |
| Dependencies | VIS-014 |
| Labels | typography, brand |

**Evidence**
- `qa_owner_chat_1440.png`: "Good to meet you — I'm Curator…" in Fraunces at about 32px is warm and editorial.
- `qa_about_1440.png`: "The story" heading.
- `qa_join_empty_1440.png`: "Join this household".
- DM Sans body text is neutral and readable.
- `--font-display` is used 63 times plus 8 literal stacks, so Fraunces is concentrated on headings, as intended.

**Current state:** The pairing is distinctive in a category of Plex-clone sans-serif UIs.

**Root cause:** Deliberate brand choice.

**Recommendation:** Keep it. Constrain Fraunces to ≥ 20px (display through h3, persona avatar initial, brand wordmark). Optical sizing is automatic. Use letter-spacing −0.02em at ≥ 28px and −0.01em at 20–24px.

**Rationale:** The serif is the curator's voice.

**User story:** As a member, I want Projectionist to feel like a cinema journal, not a dashboard.

**Acceptance criteria**
- [ ] Fraunces appears at no computed size below 18px except the 40px-avatar initial.

**Success metric:** 0 sub-18px Fraunces nodes.

**Validation:** Computed-style sweep.

### VIS-034: Protect the phone primitives

| Field | Value |
|---|---|
| Type | Strength |
| Surface | Consumer |
| Persona(s) | Low-bandwidth mobile, Returning consumer |
| Category | Layout |
| Severity | Medium |
| Impact | 4 |
| Effort | XS |
| Confidence | Confirmed |
| Priority score | 8.00 |
| Verdict | Protect |
| Dependencies | none |
| Labels | mobile, touch |

**Evidence:** `01-tokens.css` defines `--tap-min: 44px`, `--font-size-input: 16px` (iOS zoom floor), `--rail-card-width: 132px`, and `--rail-peek: 56px`. `.app-topbar` uses `env(safe-area-inset-*)`, and the viewport meta sets `interactive-widget=resizes-content`. `qa_member_chat_390.png` shows 44px nav and threads buttons and a comfortable message card padding of about 20px.

**Current state:** Mobile was considered, not an afterthought.

**Root cause:** Deliberate HIG alignment.

**Recommendation:** Keep these. Extend `--tap-min` to every `.btn[data-size=sm]` on `(pointer: coarse)`.

**Rationale:** The couch phone is a primary device.

**User story:** As a member on the couch, I want controls I can hit with a thumb.

**Acceptance criteria**
- [ ] All interactive targets are at least 44×44 on coarse pointers.

**Success metric:** 0 sub-44 targets on a 390 audit.

**Validation:** Playwright bounding-box sweep.

### VIS-035: Protect poster ratio discipline

| Field | Value |
|---|---|
| Type | Strength |
| Surface | Consumer |
| Persona(s) | All |
| Category | Iconography |
| Severity | Medium |
| Impact | 3 |
| Effort | XS |
| Confidence | Confirmed |
| Priority score | 6.00 |
| Verdict | Protect |
| Dependencies | none |
| Labels | imagery, posters |

**Evidence:** 11 `aspect-ratio` declarations: `2 / 3` ×9, `2/3` ×1, `16 / 9` ×1 (trailer and backdrop).

**Current state:** Posters keep shape across rails, grids, and cards.

**Root cause:** Consistent use of aspect-ratio.

**Recommendation:** Tokenize as `--ratio-poster: 2 / 3`, `--ratio-backdrop: 16 / 9`, and `--ratio-still: 16 / 9`. Add `object-fit: cover` and `background: var(--surface-2)` to the poster primitive so missing art never collapses.

**Rationale:** The library's own art is the hero imagery.

**User story:** As a member, I want shelves that look like shelves.

**Acceptance criteria**
- [ ] All poster images use `--ratio-poster`.

**Success metric:** Ratio literals drop from 11 to 0 (tokens).

**Validation:** Grep.

### VIS-036: Protect the "one gold primary" rule and locked glyphs

| Field | Value |
|---|---|
| Type | Strength |
| Surface | Consumer |
| Persona(s) | All |
| Category | Components |
| Severity | Medium |
| Impact | 3 |
| Effort | XS |
| Confidence | Confirmed |
| Priority score | 6.00 |
| Verdict | Protect |
| Dependencies | VIS-003 |
| Labels | governance, cta |

**Evidence:** `docs/DESIGN.md` @ 94fcd3f, "Title surfaces": "One gold primary… Never two competing primaries". There is a locked terms table and a locked Material Symbols table (12 glyphs), with `chat` versus `rate_review` explicitly distinguished.

**Current state:** The best design governance in the repo, limited to title CTAs.

**Root cause:** Good practice applied to one surface.

**Recommendation:** Generalize it to every action group (VIS-003 acceptance criteria), and make the glyph table the seed of the SVG sprite (VIS-014).

**Rationale:** It already works, so scale it.

**User story:** As a member, I want one obvious next step on every card.

**Acceptance criteria**
- [ ] The DESIGN.md "one primary per action group" rule applies app-wide.

**Success metric:** ≤ 1 primary per region (Playwright).

**Validation:** As in VIS-003.

### VIS-032: Protect the glass-door join card

| Field | Value |
|---|---|
| Type | Strength |
| Surface | Public |
| Persona(s) | First-time household member |
| Category | Brand |
| Severity | Medium |
| Impact | 3 |
| Effort | XS |
| Confidence | Confirmed |
| Priority score | 6.00 |
| Verdict | Protect |
| Dependencies | VIS-002 |
| Labels | glass-door, public, polish |

**Evidence**
- `qa_join_empty_1440.png` shows:
  - A 520px card with `--radius-lg` 14px and a `0 24px 64px` 35% black shadow over a drifting amber wash (`glass-door-drift 28s`, covered by reduced motion in `15-glass-door.css`).
  - An eyebrow "YOU'RE INVITED" with tracked caps.
  - A Fraunces title.
  - A danger callout at `--danger` with a 45% border.
  - A "Sign in" link in amber at 11.21:1.
- Spacing is a consistent 16px grid gap (`gap: var(--space-4)`).

**Current state:** The most finished public screen.

**Root cause:** A self-contained sheet with tokens used properly.

**Recommendation:** Make it the reference for all public screens. Bring `/login` fields up to it (VIS-002).

**Rationale:** It proves the brand works.

**User story:** As an invitee, I want the door to feel like a theater, not a router admin.

**Acceptance criteria**
- [ ] `/login`, `/join`, and `/setup` share the same field and button primitives inside this card.

**Success metric:** Visual parity across the three routes.

**Validation:** A triptych screenshot.

---

## Opportunities

### VIS-041: Guard tokens with Stylelint

| Field | Value |
|---|---|
| Type | Opportunity |
| Surface | Cross-cutting |
| Persona(s) | Engineers |
| Category | Tokens |
| Severity | Medium |
| Impact | 4 |
| Effort | S |
| Confidence | Confirmed |
| Priority score | 4.00 |
| Verdict | Add |
| Dependencies | VIS-007 |
| Labels | lint, ci, tokens |

**Evidence:** `frontend/package.json` @ 94fcd3f has `lint: eslint src`, with no Stylelint and no CSS lint at all.

**Current state:** Nothing stops drift.

**Root cause:** A JavaScript-only lint culture.

**Recommendation:** Add `stylelint`, `stylelint-config-standard`, and `stylelint-declaration-strict-value`. Rules:
- `scale-unlimited/declaration-strict-value: [["/color$/","fill","stroke","box-shadow","z-index","font-size","border-radius","transition-duration"], { ignoreValues: ["transparent","inherit","currentColor","none","0"] }]`
- `selector-disallowed-list: ["/^html\\[data-theme/"]` outside `01-tokens.css`.
- `declaration-property-value-disallowed-list: { "font-weight": ["/^(?!400|500|600|700).*/"] }`.

Start in warn mode with a baseline, and switch to error in the Later phase.

**Rationale:** Cheap enforcement beats expensive audits.

**User story:** As a reviewer, I want CI to catch a literal hex before I do.

**Acceptance criteria**
- [ ] `npm run lint:css` runs in CI.
- [ ] Baseline warnings only go down release over release.

**Success metric:** Warning count is monotonically non-increasing.

**Validation:** CI job output.

### VIS-043: Add both-theme visual regression for five screens

| Field | Value |
|---|---|
| Type | Opportunity |
| Surface | Cross-cutting |
| Persona(s) | Engineers, All |
| Category | Polish |
| Severity | Medium |
| Impact | 4 |
| Effort | S |
| Confidence | Confirmed |
| Priority score | 4.00 |
| Verdict | Add |
| Dependencies | none |
| Labels | testing, playwright, themes |

**Evidence:** `e2e/theme.spec.ts` exists, but `git grep toHaveScreenshot` on 94fcd3f `e2e/` returns 0. No visual diffs exist, which is how VIS-002, VIS-004, and VIS-009 shipped.

**Current state:** Visual regressions are caught by humans with screenshots.

**Root cause:** There is no visual test layer.

**Recommendation:** Add `e2e/visual-themes.spec.ts`: 5 routes (`/login`, `/chat`, `/explore`, `/admin/overview`, `/help`) × 2 themes × 2 viewports (1440×900, 390×844) = 20 snapshots, run on the mocked e2e server (`:8799`) with fonts self-hosted (VIS-014) for determinism. Use `maxDiffPixelRatio: 0.01`.

**Rationale:** It is a precondition for the type-scale change (VIS-006).

**User story:** As a maintainer, I want to see every pixel a CSS change moves.

**Acceptance criteria**
- [ ] 20 baselines committed.
- [ ] CI fails on an unreviewed diff.

**Success metric:** Visual bugs reported from QA screenshots trend toward 0 per release.

**Validation:** CI.

### VIS-040: Ship an intentional Admin density mode

| Field | Value |
|---|---|
| Type | Opportunity |
| Surface | Owner |
| Persona(s) | Established owner at scale |
| Category | Layout |
| Severity | Medium |
| Impact | 3 |
| Effort | M |
| Confidence | Likely |
| Priority score | 1.60 |
| Verdict | Add |
| Dependencies | VIS-003, VIS-006, VIS-021 |
| Labels | admin, density |

**Evidence:** `qa_owner_admin_overview_1440.png` shows about 300px of vertical space before the first data tile (title, rule, eyebrow, H2, lede). Tiles are 2-up at 1024px with roughly 40px numerals. `qa_owner_newsletters_1440.png` shows about 340px of prose before the first control. Admin uses consumer spacing throughout.

**Current state:** Admin is as airy as the living room, which suits members but costs owners scroll.

**Root cause:** There is a single density.

**Recommendation:** Should admin be denser on purpose? **Yes.** Apply `[data-density="compact"]` on `.admin-shell`:
- Body text `--text-sm` (14px) at 1.45 line height.
- Section gap `--space-5` (20px) instead of 32px.
- Card padding 12px 16px.
- Tables: 36px rows and `font-variant-numeric: tabular-nums`.
- Tile numerals `--text-2xl` (24px), Fraunces off.
- Page intro capped at 2 lines, with "More" disclosure.

Keep the brand: the same tokens, top bar, and amber.

**Rationale:** The owner's Monday pass is a work session, not an evening.

**User story:** As an owner with 5,000 titles, I want the health picture above the fold.

**Acceptance criteria**
- [ ] The first data tile on `/admin/overview` appears within 200px of the top bar at 1440×900.

**Success metric:** Content above the fold improves by ≥ 40%.

**Validation:** Before/after screenshot measurement.

### VIS-042: Use Fraunces optical size and softness for brand moments

| Field | Value |
|---|---|
| Type | Opportunity |
| Surface | Consumer |
| Persona(s) | All |
| Category | Brand |
| Severity | Low |
| Impact | 2 |
| Effort | S |
| Confidence | Likely |
| Priority score | 0.80 |
| Verdict | Add |
| Dependencies | VIS-014 |
| Labels | typography, delight |

**Evidence:** `index.html` loads Fraunces opsz 9..144 but not the `SOFT` or `WONK` axes. There are 2 `opsz` or `font-optical-sizing` mentions in CSS.

**Current state:** Fraunces renders at default softness everywhere.

**Root cause:** Unused variable axes.

**Recommendation:** When self-hosting, include `SOFT 0–100`. Use `font-variation-settings: "SOFT" 50` for the welcome headline, Year in Review numerals, and the Lobby. Use `"SOFT" 0` for admin and page titles.

**Rationale:** It adds warmth where the curator speaks and crispness where the owner works.

**User story:** As a member, I want the curator's greeting to feel personal.

**Acceptance criteria**
- [ ] Two softness settings are documented in the specimen.

**Success metric:** Qualitative brand review.

**Validation:** Specimen page.

### VIS-044: Publish a living specimen page

| Field | Value |
|---|---|
| Type | Opportunity |
| Surface | Owner |
| Persona(s) | Engineers, Owner-contributors |
| Category | Components |
| Severity | Low |
| Impact | 2 |
| Effort | S |
| Confidence | Likely |
| Priority score | 1.00 |
| Verdict | Add |
| Dependencies | VIS-003, VIS-021 |
| Labels | docs, components |

**Evidence:** The design system lives only in CSS and prose (platform map, "Design system"). There is no rendered catalogue.

**Current state:** Contributors read 20,598 lines of CSS to find a card.

**Root cause:** There is no component gallery.

**Recommendation:** Add a dev-only route, `/admin/advanced/specimen`, gated behind `import.meta.env.DEV` or an owner flag. It renders the tokens table, type specimen, and every primitive in both themes. It doubles as the visual-regression target.

**Rationale:** It makes the system discoverable.

**User story:** As a contributor, I want to see the button variants before I add one.

**Acceptance criteria**
- [ ] The specimen page renders all primitives × both themes.

**Success metric:** New component roots per release drop to 0 without review.

**Validation:** A screenshot in VIS-043.

---

## Sacred cow ruling: "Lights Down cinema + amber + Fraunces as brand"

**Ruling: KEEP, with two amendments.**

| Element | Ruling | Evidence |
|---|---|---|
| Lights Down cinema | **Keep** as the signature theme | All text pairs AA, 12.59–15.01:1 (VIS-030). The most polished screens are Lights Down (`qa_join_empty_1440.png`, `qa_about_1440.png`). |
| Amber `#ffb800` | **Keep in Lights Down; change its role model** | 10.79:1 on surface and 10.68:1 under dark text. In Lights Up, `#b8860b` as text is 3.04:1, so split into fill and ink (VIS-001). Stop using it for warning (VIS-022). |
| Fraunces | **Keep, constrained** to 20px and above | Distinctive voice (VIS-033). Below 18px and at an unloaded 650 weight it degrades (VIS-016, VIS-023). |
| "Lights Down is the default" | **Change** | The runtime default is `system`, and owners on light OSes see Lights Up (VIS-015). The brand must hold in both themes. |
| Ambient washes | **Keep, tokenized** | Lovely in Lights Down, but a literal leak smudges Lights Up (VIS-004). |

---

## Required deliverable 1 — Proposed design tokens

### Token table

**Color: primitives and semantic aliases**

| Token | Lights Down | Lights Up | Role |
|---|---|---|---|
| `--bg` | `#0d0d0d` | `#f9f7f2` | page |
| `--surface` | `#101218` | `#fbf9f4` | panels, top bar |
| `--surface-2` | `#171a22` | `#f0eee9` | sidebar, inset |
| `--surface-raised` | `#1c2029` | `#ffffff` | cards, inputs, popovers |
| `--border-subtle` | `#22262f` | `#e5e2da` | decorative dividers |
| `--border` | `#2c313c` | `#d0c5af` | card outlines (decorative) |
| `--border-field` | `#6a7181` | `#857a68` | **new**: interactive boundaries |
| `--text` | `#e6e2d6` | `#1b1c19` | primary ink |
| `--muted` | `#9a958a` | `#4d4635` | secondary ink |
| `--accent-fill` | `#ffb800` | `#b8860b` | **new**: primary fill |
| `--accent-fill-hover` | `#ffc533` | `#c4920f` | **new** |
| `--accent-fill-press` | `#e0a200` | `#a67908` | **new** |
| `--on-accent` | `#1a1208` | `#1a1208` | text on fill (renamed from `--accent-text`) |
| `--accent-ink` | `#ffb800` | `#735c00` | **new**: links, active labels |
| `--accent-soft` | `rgba(255,184,0,.14)` | `rgba(184,134,11,.12)` | selected tint |
| `--focus-ring` | `#ffb800` | `#735c00` | **new** |
| `--status-success` | `#7dba98` | `#256b4a` | changed in Lights Up (was `#2e7d57`, 4.33:1 on surface-2) |
| `--status-danger` | `#e8918a` | `#ba1a1a` | unchanged |
| `--status-warning` | `#f2a65a` | `#8f4a00` | **new** |
| `--status-info` | `#8fb4d9` | `#2b5a8a` | **new** |
| `--picture-black` | `#000` | `#000` | video stage |
| `--ink-on-media` | `#e6e2d6` | `#e6e2d6` | text over posters / video |

**Contrast for every defined text/background pairing**

| Text token | on `--bg` | on `--surface` | on `--surface-2` | on `--surface-raised` |
|---|---|---|---|---|
| `--text` (DN) | 15.01 | 14.45 | 13.43 | 12.59 |
| `--text` (UP) | 15.99 | 16.27 | 14.76 | 17.12 |
| `--muted` (DN) | 6.52 | 6.28 | 5.83 | 5.47 |
| `--muted` (UP) | 8.74 | 8.90 | 8.07 | 9.36 |
| `--accent-ink` (DN `#ffb800`) | 11.21 | 10.79 | 10.03 | 9.40 |
| `--accent-ink` (UP `#735c00`) | 6.02 | 6.12 | 5.56 | 6.44 |
| `--status-success` (DN) | 8.65 | 8.33 | 7.74 | 7.26 |
| `--status-success` (UP `#256b4a`) | 5.98 | 6.08 | 5.52 | 6.40 |
| `--status-danger` (DN) | 8.19 | 7.89 | 7.33 | 6.87 |
| `--status-danger` (UP) | 6.03 | 6.14 | 5.57 | 6.46 |
| `--status-warning` (DN `#f2a65a`) | 9.60 | 9.25 | 8.60 | 8.06 |
| `--status-warning` (UP `#8f4a00`) | 6.23 | 6.34 | 5.75 | 6.67 |
| `--status-info` (DN `#8fb4d9`) | 8.98 | 8.65 | 8.03 | 7.53 |
| `--status-info` (UP `#2b5a8a`) | 6.69 | 6.81 | 6.18 | 7.16 |
| `--border-field` (DN, non-text, 3:1 target) | 3.97 | 3.83 | 3.55 | 3.33 |
| `--border-field` (UP, non-text) | 3.94 | 4.01 | 3.64 | 4.22 |
| `--focus-ring` (DN / UP, non-text) | 11.21 / 6.02 | 10.79 / 6.12 | 10.03 / 5.56 | 9.40 / 6.44 |

**Text on fills**

| Pair | Lights Down | Lights Up |
|---|---:|---:|
| `--on-accent` on `--accent-fill` | 10.68 | 5.69 |
| on `--accent-fill-hover` | 11.72 | 6.58 |
| on `--accent-fill-press` | 8.23 | 4.73 |
| `--text` on `--accent-soft` (over surface) | 11.12 | 14.42 |
| `--accent-ink` on `--accent-soft` | 8.30 | 4.95 |
| `--ink-on-media` on `--picture-black` | 16.0 | 16.0 |
| `--muted-on-media` on `--picture-black` | 11.83 | 11.83 |

Text over posters must sit on a veil of at least 55% `--picture-black`, so that worst-case bright art keeps `--ink-on-media` at 4.5:1 or better.

**Type scale** (rem relative to the root; Medium = 16px, Small = 15px, Large = 18px)

| Token | rem | px @ Medium | Notes |
|---|---|---:|---|
| `--text-xs` | `max(12px, .75rem)` | 12 | floor |
| `--text-sm` | .875rem | 14 | |
| `--text-base` | 1rem | 16 | body |
| `--text-lg` | 1.125rem | 18 | lead |
| `--text-xl` | 1.25rem | 20 | h4 |
| `--text-2xl` | 1.5rem | 24 | h3 |
| `--text-3xl` | 1.875rem | 30 | h2 |
| `--text-4xl` | 2.375rem | 38 | h1 |
| `--text-display` | `clamp(2.5rem, 2rem + 2vw, 3.5rem)` | 40–56 | display |

**Spacing** (px; it does not scale with the font preference): 0, 2, 4, 8, 12, 16, 20, 24, 32, 40, 48, 64. Existing `--space-1…8` are kept; `--space-0-5: 2px`, `--space-7-5: 40px`, and `--space-9: 64px` are added.

**Radius:** `--radius-xs` 4px, `--radius-sm` 6px, `--radius-md` (= `--radius`) 10px, `--radius-lg` 14px, `--radius-xl` 20px, `--radius-pill` 999px, `--radius-round` 50%.

**Shadow:**

| Token | Lights Down | Lights Up |
|---|---|---|
| `--shadow-1` | `0 1px 2px rgba(0,0,0,.30)` | `0 1px 2px rgba(27,28,25,.08)` |
| `--shadow-2` | `0 8px 24px rgba(0,0,0,.35)` | `0 8px 24px rgba(27,28,25,.10)` |
| `--shadow-3` | `0 24px 64px rgba(0,0,0,.45)` | `0 24px 64px rgba(27,28,25,.16)` |
| `--shadow-drawer` | `8px 0 32px rgba(0,0,0,.45)` | `8px 0 32px rgba(27,28,25,.14)` |

**Motion:**

| Token | Value |
|---|---|
| `--dur-instant` | 100ms |
| `--dur-fast` | 150ms |
| `--dur-base` | 220ms |
| `--dur-slow` | 320ms |
| `--dur-theme` | 300ms |
| `--dur-ambient` | 28s |
| `--ease-standard` | `cubic-bezier(.2,0,0,1)` |
| `--ease-enter` | `cubic-bezier(0,0,.2,1)` |
| `--ease-exit` | `cubic-bezier(.4,0,1,1)` |

**z-index:** `--z-base` 0, `--z-raised` 2, `--z-sticky` 40, `--z-topbar` 50, `--z-drawer` 90, `--z-modal` 100, `--z-popover` 1000, `--z-toast` 1200.

**Breakpoints:** sm 640, md 768, lg 1024, xl 1440. These are documented constants for `@custom-media`, because custom properties cannot be used in `@media`.

**Ratios:** `--ratio-poster` 2 / 3, `--ratio-backdrop` 16 / 9.

### Ready-to-paste CSS (`01-tokens.css` approach)

```css
:root {
  /* Layout */
  --sidebar-width: 280px;
  --reading-column-max: 1200px;
  --measure: 68ch;
  --gutter: 24px;
  --margin-mobile: 16px;
  --card-gap: 20px;
  --tap-min: 44px;
  --font-size-input: 16px;
  --rail-card-width: 132px;
  --rail-peek: 56px;
  --ratio-poster: 2 / 3;
  --ratio-backdrop: 16 / 9;

  /* Type families (self-hosted, metric-matched fallbacks) */
  --font-display: "Fraunces", "Fraunces Fallback", Georgia, serif;
  --font-body: "DM Sans", "DM Sans Fallback", system-ui, sans-serif;
  --font-mono: ui-monospace, "SF Mono", "Cascadia Code", Menlo, monospace;

  /* Type scale — 1.2 ratio, 12px floor; root = --base-font-size (15/16/18) */
  --base-font-size: 16px;
  --text-xs: max(12px, 0.75rem);
  --text-sm: 0.875rem;
  --text-base: 1rem;
  --text-md: var(--text-base); /* deprecated alias */
  --text-lg: 1.125rem;
  --text-xl: 1.25rem;
  --text-2xl: 1.5rem;
  --text-3xl: 1.875rem;
  --text-4xl: 2.375rem;
  --text-display: clamp(2.5rem, 2rem + 2vw, 3.5rem);
  --weight-regular: 400;
  --weight-medium: 500;
  --weight-semibold: 600;
  --weight-bold: 700;
  --leading-none: 1;
  --leading-tight: 1.15;
  --leading-snug: 1.3;
  --leading-body: 1.55;
  --leading-relaxed: 1.65;
  --tracking-tight: -0.02em;
  --tracking-snug: -0.01em;
  --tracking-normal: 0;
  --tracking-wide: 0.04em;
  --tracking-caps: 0.08em;

  /* Spacing (px — does not scale with font preference) */
  --space-0-5: 2px;
  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-5: 20px;
  --space-6: 24px;
  --space-7: 32px;
  --space-7-5: 40px;
  --space-8: 48px;
  --space-9: 64px;

  /* Radius */
  --radius-xs: 4px;
  --radius-sm: 6px;
  --radius-md: 10px;
  --radius: var(--radius-md);
  --radius-lg: 14px;
  --radius-xl: 20px;
  --radius-pill: 999px;
  --radius-round: 50%;

  /* Motion */
  --dur-instant: 100ms;
  --dur-fast: 150ms;
  --dur-base: 220ms;
  --dur-slow: 320ms;
  --dur-theme: 300ms;
  --dur-ambient: 28s;
  --ease-standard: cubic-bezier(0.2, 0, 0, 1);
  --ease-enter: cubic-bezier(0, 0, 0.2, 1);
  --ease-exit: cubic-bezier(0.4, 0, 1, 1);

  /* Layers */
  --z-base: 0;
  --z-raised: 2;
  --z-sticky: 40;
  --z-topbar: 50;
  --z-drawer: 90;
  --z-modal: 100;
  --z-popover: 1000;
  --z-toast: 1200;

  /* Breakpoints (documentation; use @custom-media in sheets)
     sm 640px · md 768px · lg 1024px · xl 1440px */

  font-family: var(--font-body);
  font-size: var(--base-font-size);
  line-height: var(--leading-body);
}

/* Lights Down — signature cinema chamber */
:root,
html[data-theme="lights-down"] {
  color-scheme: dark;
  --bg: #0d0d0d;
  --surface: #101218;
  --surface-2: #171a22;
  --surface-raised: #1c2029;
  --border-subtle: #22262f;
  --border: #2c313c;
  --border-field: #6a7181;          /* 3.33–3.97:1 */
  --text: #e6e2d6;                  /* 12.59–15.01:1 */
  --muted: #9a958a;                 /* 5.47–6.52:1 */
  --accent-fill: #ffb800;
  --accent-fill-hover: #ffc533;
  --accent-fill-press: #e0a200;
  --on-accent: #1a1208;             /* 10.68 / 11.72 / 8.23:1 */
  --accent-ink: #ffb800;            /* 9.40–11.21:1 */
  --accent-soft: rgba(255, 184, 0, 0.14);
  --focus-ring: #ffb800;
  --status-success: #7dba98;        /* 7.26–8.65:1 */
  --status-danger: #e8918a;         /* 6.87–8.19:1 */
  --status-warning: #f2a65a;        /* 8.06–9.60:1 */
  --status-info: #8fb4d9;           /* 7.53–8.98:1 */
  --status-success-soft: color-mix(in srgb, var(--status-success) 14%, transparent);
  --status-danger-soft: color-mix(in srgb, var(--status-danger) 14%, transparent);
  --status-warning-soft: color-mix(in srgb, var(--status-warning) 14%, transparent);
  --status-info-soft: color-mix(in srgb, var(--status-info) 14%, transparent);
  --shadow-1: 0 1px 2px rgba(0, 0, 0, 0.3);
  --shadow-2: 0 8px 24px rgba(0, 0, 0, 0.35);
  --shadow-3: 0 24px 64px rgba(0, 0, 0, 0.45);
  --shadow-drawer: 8px 0 32px rgba(0, 0, 0, 0.45);
  --ambient-accent: hsl(36 18% 22%);
  --workspace-wash-a: #1a1612;
  --workspace-wash-b: #12151c;
  --workspace-base: #0c0d11;
  --ink-on-media: #e6e2d6;
  --muted-on-media: #c8c2b4;
  --picture-black: #000;
  --stage-bg: var(--workspace-base);
  --stage-panel: color-mix(in srgb, var(--surface) 92%, transparent);
  --stage-line: color-mix(in srgb, var(--text) 12%, transparent);
  /* deprecated aliases — remove after sweep */
  --accent: var(--accent-ink);
  --accent-2: var(--accent-fill-press);
  --accent-text: var(--on-accent);
  --danger: var(--status-danger);
  --success: var(--status-success);
}

/* Lights Up — gallery paper, co-equal */
html[data-theme="lights-up"] {
  color-scheme: light;
  --bg: #f9f7f2;
  --surface: #fbf9f4;
  --surface-2: #f0eee9;
  --surface-raised: #ffffff;
  --border-subtle: #e5e2da;
  --border: #d0c5af;
  --border-field: #857a68;          /* 3.64–4.22:1 */
  --text: #1b1c19;                  /* 14.76–17.12:1 */
  --muted: #4d4635;                 /* 8.07–9.36:1 */
  --accent-fill: #b8860b;
  --accent-fill-hover: #c4920f;
  --accent-fill-press: #a67908;
  --on-accent: #1a1208;             /* 5.69 / 6.58 / 4.73:1 */
  --accent-ink: #735c00;            /* 5.56–6.44:1 */
  --accent-soft: rgba(184, 134, 11, 0.12);
  --focus-ring: #735c00;
  --status-success: #256b4a;        /* 5.52–6.40:1 */
  --status-danger: #ba1a1a;         /* 5.57–6.46:1 */
  --status-warning: #8f4a00;        /* 5.75–6.67:1 */
  --status-info: #2b5a8a;           /* 6.18–7.16:1 */
  --status-success-soft: color-mix(in srgb, var(--status-success) 12%, transparent);
  --status-danger-soft: color-mix(in srgb, var(--status-danger) 12%, transparent);
  --status-warning-soft: color-mix(in srgb, var(--status-warning) 12%, transparent);
  --status-info-soft: color-mix(in srgb, var(--status-info) 12%, transparent);
  --shadow-1: 0 1px 2px rgba(27, 28, 25, 0.08);
  --shadow-2: 0 8px 24px rgba(27, 28, 25, 0.1);
  --shadow-3: 0 24px 64px rgba(27, 28, 25, 0.16);
  --shadow-drawer: 8px 0 32px rgba(27, 28, 25, 0.14);
  --ambient-accent: hsl(40 28% 78%);
  --workspace-wash-a: #f0ebe0;
  --workspace-wash-b: #e8e4d8;
  --workspace-base: #f5f2ea;
  --picture-black: #000;
  --stage-bg: var(--bg);
  --stage-panel: var(--surface);
  --stage-line: var(--border-subtle);
}

@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
    scroll-behavior: auto !important;
  }
}
```

`frontend/src/lib/uiPrefs.ts` `FONT_SIZES` becomes `{ small: "15px", medium: "16px", large: "18px" }`. Ship this in step 6 of the migration, not step 1.

---

## Required deliverable 2 — Typography specimen spec

| Style | Family | Size (Medium) | Weight | Line height | Letter spacing | Usage |
|---|---|---|---|---|---|---|
| Display | Fraunces (SOFT 50) | `--text-display` 40–56px | 600 | 1.1 | −0.02em | Chat welcome, Year in Review, glass-door hero |
| H1 | Fraunces | `--text-4xl` 38px | 600 | 1.15 | −0.02em | Page title (Overview, Newsletters, Profile, Help) |
| H2 | Fraunces | `--text-3xl` 30px | 600 | 1.2 | −0.015em | Section title; glass-door card title |
| H3 | Fraunces | `--text-2xl` 24px | 600 | 1.25 | −0.01em | Panel title (Identity, Weekly household letter), rail titles ("For you") |
| H4 | DM Sans | `--text-xl` 20px | 600 | 1.3 | 0 | Card titles, curator-reply h1/h2 |
| H5 | DM Sans | `--text-lg` 18px | 600 | 1.35 | 0 | Sub-panel heads, dialog titles |
| H6 / Eyebrow | DM Sans | `--text-xs` 12px | 600 | 1.3 | 0.08em, uppercase | "AT A GLANCE", "YOU'RE INVITED", nav group labels |
| Body | DM Sans | `--text-base` 16px | 400 | 1.55 | 0 | Chat messages, forms, prose (max 68ch) |
| Lead | DM Sans | `--text-lg` 18px | 400 | 1.55 | 0 | Page ledes, Help intro |
| Small | DM Sans | `--text-sm` 14px | 400 | 1.45 | 0 | Meta lines, helper text, table cells (compact admin) |
| Caption | DM Sans | `--text-xs` 12px | 500 | 1.4 | 0.01em | Timestamps ("70d ago"), footer, poster sublabels |
| Label | DM Sans | `--text-sm` 14px | 600 | 1.3 | 0 | Field labels, button text (md), tabs |
| Numeric / stat | DM Sans, `tabular-nums` | `--text-2xl` 24px (admin) / `--text-3xl` 30px (consumer) | 700 | 1.1 | −0.01em | Health tiles, counts, durations, progress % |
| Code | `--font-mono` | 0.875em of context | 400 | 1.5 | 0 | `code`, `pre`, MCP keys, logs only |

**Rules**
- Fraunces never renders below 18px. The 40px persona avatar initial is the only exception.
- All numbers that change or align use `font-variant-numeric: tabular-nums`. That is 17 uses today; it should cover every stat, time, %, and table cell.
- Long-form measure is 68ch. Chat column measure is 72ch.
- Font loading: self-hosted WOFF2 with `font-display: swap`, preloads for DM Sans 400 and Fraunces 600, and metric-matched fallbacks (VIS-014).

---

## Required deliverable 3 — Component consolidation plan

| Component | Current variants (94fcd3f) | Target variants | Spec |
|---|---|---|---|
| Button | Element `button` (gold), `.ghost`, `.btn-link`, `.primary`, `.btn-primary`, `.btn-danger`, `.login-primary` / `-secondary`, `.title-cta-primary` / `-secondary` / `-ghost` / `-danger`, `.title-detail-cta-primary` / `-secondary`, `.recommendation-cta-primary`, `.explore-search-submit`, `.explore-section-toolbar-primary`, `.media-browse-secondary`, `.live-chrome-secondary`, `.theater-osd-secondary`, `.dash-purge-btn--danger`, `.app-topbar-icon`, … **≈25** | **`.btn` × 5 variants** (`primary`, `secondary`, `ghost`, `danger`, `icon`) **× 3 sizes** | Sizes: sm 32px / md 40px / lg 48px (coarse pointer min 44). Padding 0 12 / 0 16 / 0 20px. Radius `--radius-sm`. Label 14px/600. Primary: `--accent-fill` / `--on-accent`. Secondary: `--surface-raised` + 1px `--border-field`. Ghost: transparent, `--text`, hover `--accent-soft`. Danger: `--status-danger` fill with `#1a0b09` text in Lights Down (8.08:1) and white in Lights Up (6.46:1). Icon: square, 40px, 20px glyph. States: hover (`--accent-fill-hover`, no `filter`), active (`-press`), focus-visible (2px `--focus-ring` + 2px offset), disabled (opacity .5, no hover), loading (spinner replaces icon, width locked). |
| Text field | UA default (login), `.settings-field input…`, `.library-search--hero input`, composer textarea, phone media rule | **`.field` + `.input` / `.select` / `.textarea`**, sizes md and lg | md 44px, lg 56px (hero search). Padding 10 14px. `--surface-raised` background, `--border-field` border, `--radius-sm` (lg: `--radius-lg`). Font 16px. States: hover border `--muted`, focus ring, invalid border `--status-danger` plus message, disabled `--surface-2`. |
| Card | **40 roots** (`.title-card`, `.explore-card`, `.explore-section-card`, `.service-card`, `.journey-card`, `.dash-stat-card`, `.owner-health-tile`, `.wizard-card`, `.whisper-card`, `.recommendation-card`, …) | **5**: `.card`, `.card--interactive`, `.poster-card`, `.stat-tile`, `.glass-card` | `.card`: `--surface-raised`, 1px `--border`, `--radius-md`, padding 20px, `--shadow-1`. Interactive: hover border `--accent-ink` 40% mix, translateY(−1px) at `--dur-fast`. Poster: `--ratio-poster`, `--radius-sm`, caption below. Stat: numeric spec. Glass: glass-door only. |
| Chip | **24 roots** (`.welcome-starter-chip`, `.suggested-reply-chip`, `.explore-motif-chip`, `.explore-theme-chip`, `.taste-quiz-chip`, `.title-plot-chip`, `.stat-chip`, `.streak-chip`, …) | **3**: `.chip` (selectable filter), `.chip--suggestion` (starter or reply), `.tag` (static metadata) | Height 32px (coarse 44), padding 0 12px, `--radius-pill`, 14px/500. Selected: `--accent-soft` background + `--accent-ink` text + 1px `--accent-ink` border. |
| Badge | **21** (`.badge`, `.inbox-unread-badge`, `.persona-mode-badge`, `.certified-badge`, `.title-card-match-badge`, …) | **2**: `.badge` (count/dot), `.status-badge` (tone) | Count: min 18px, 11–12px/700 tabular, `--accent-fill` / `--on-accent`. Status: 12px/600, tone `-soft` background + tone ink + leading icon. |
| Modal / dialog | 10 modals (`.confirm-modal`, `.persona-modal`, `.recommend-modal`, `.trailer-modal`, `.media-issue-modal`, `.bulk-delete-modal`, `.removal-summary-modal`, …) | **`.dialog`** sm 400 / md 560 / lg 800 / fullscreen | `--surface-raised`, `--radius-lg`, `--shadow-3`, padding 24px, header H5, footer right-aligned `.btn`s, `--z-modal`. Enter: 220ms opacity + scale .98→1. |
| Backdrop / scrim | **13** (`.app-nav-backdrop`, `.persona-modal-backdrop`, `.whats-new-backdrop`, `.title-detail-drawer-scrim`, …) | **1**: `.scrim` | `rgba(0,0,0,.55)` Lights Down, `rgba(27,28,25,.35)` Lights Up, 150ms fade. |
| Drawer / sheet | `.app-nav`, `.workspace-sidebar` drawer, `.settings-drawer`, `.title-detail-drawer-panel` (+ phone) | **`.sheet`** side (left/right) and bottom | Width 320px (nav) / 480px (detail); bottom sheet max 88vh, top radius `--radius-xl`; `--shadow-drawer`; `--z-drawer`. |
| Popover / menu | 6 (`.share-action-popover`, `.portal-menu`, poster action menu, …) | **1**: `.popover` | min-width 200, padding 8, `--radius-md`, `--shadow-2`, `--z-popover`, 140ms enter. |
| Table | **9** (`.dash-table`, `.user-management-table`, `.scheduled-tasks-table`, `.llm-usage-table`, `.privacy-table`, `.markdown-table`, …) | **`.data-table`** + `--dense` | Header 12px/600 caps `--muted`; rows 44px (dense 36px); tabular-nums; zebra off, 1px `--border-subtle` row dividers; sticky header `--z-sticky`. |
| Tabs | **8** sets (`.health-tabs`, `.library-hub-tabs`, `.live-channels-tabs`, `.explore-media-tabs`, `.knowledge-ops-tabs`, …) | **2**: `.tabs` (underline), `.segmented` | Tabs: 14px/600, 44px tall, active 2px `--accent-ink` underline (`inset 0 -2px 0`). Segmented: `--surface-2` track, selected `--surface-raised` + `--shadow-1`. |
| Toast | **1** (`.undo-toast`) | **`.toast`** × 4 tones + `.toast-region` | Bottom-center (phone) / bottom-right (desktop), max 400px, `--surface-raised`, tone left bar 3px, `--z-toast`, 5s auto-dismiss (pauses on hover/focus). |
| Loading | **5** idioms | **2**: `.skeleton` (line/block/poster), `.spinner` (inline only) | See VIS-011. |
| Banner / callout | 8 banners + `.glass-door--halt` + `.status-*` | **`.callout`** × 4 tones | Padding 12 16, `--radius-md`, tone `-soft` background, 1px tone border at 45%, leading icon. |

**Target: about 157 roots down to about 30 primitives.**

---

## Required deliverable 4 — Before / after for the five most important screens

### 1. Login (`qa_login_local_1440.png`)

**Before:** A crafted glass card around raw UA inputs. Labels float 26px above fields while fields touch the next label (0px). The Password input touches the button. The placeholder duplicates the label. The page background is a paper wash without the amber drift visible in Lights Up.

```
BEFORE                                         AFTER
┌──────────────────────────────────┐           ┌──────────────────────────────────┐
│ PROJECTIONIST                    │           │ ◎ PROJECTIONIST   (12px caps .08em)│
│ Sign in            (26px Fr)     │           │ Sign in            (30px Fraunces) │
│ Sign in to open your…            │           │ Sign in to open your conversations │
│ Username                          │           │  and watchlist.   (16px muted)     │
│                                   │           │                       ↕ 24px       │
│[Username______________________]  │           │ Username           (14px/600)      │
│ Password                          │           │ ┌──────────────────────────────┐  │
│[______________________________]  │           │ │                              │44│
│[########## Sign in ###########]  │           │ └──────────────────────────────┘  │
│ ───────── or ─────────           │           │                       ↕ 16px       │
└──────────────────────────────────┘           │ Password                           │
                                               │ ┌──────────────────────────────┐  │
                                               │ │ ••••••••                 [👁]│44│
                                               │ └──────────────────────────────┘  │
                                               │                       ↕ 24px       │
                                               │ ┌──────── Sign in ─────────────┐  │
                                               │ └──────────────────────────────┘48│
                                               │ ───────── or ─────────             │
                                               │ Need an invite?  Help · Privacy    │
                                               └──────────────────────────────────┘
```

**Precise changes**
- Apply the VIS-002 CSS. Padding 10 14, radius 6, `--border-field`, 44px inputs, 48px primary (lg).
- Title moves to H2 30px.
- Inner form uses `gap: 16px` between fields and 24px before the button.
- Remove the duplicate placeholder. Add a password reveal icon button (`.btn[data-variant=icon]`, 40px).
- Card padding becomes 32px 32px. Add `--shadow-3` per theme (Lights Up uses 0.16 alpha, not 35% black).

### 2. Chat (`qa_owner_chat_1440.png`, `qa_member_chat_390.png`)

**Before:**
- The grey top bar and sidebar differ from other pages.
- Starter chips are clipped by the composer edge with no fade.
- The context tag "⧉ General Exploration" is in gold mono at 3.25:1.
- Thread close × buttons sit outside the cards, in two different weights.
- The send button is disabled grey with no affordance hint.
- Emoji 👍 and 👎 are full-color.

```
AFTER (1440)
┌──────────────────────────────────────────────────────────────────────────┐
│ ≡  Projectionist ◎                               ☀  (QA)     64px bar    │ ← same bar as AppShell
├──────────────┬───────────────────────────────────────────────────────────┤
│ CONVERSATIONS│  Good to meet you — I'm Curator.        (Display 48px)    │
│ [+] [⟨]      │  Which thread of your library shall we pull on?           │
│ ┌──────────┐ │  Try a starter, or just ask — I'm here.  (18px lead)      │
│ │🔍 Search │ │  ( Tonight under 2h ) ( Continue watching ) ( Compare… )  │ ← chips wrap, never clipped
│ └──────────┘ │  ░░░░░░░░░░░░░░ 24px fade mask above composer ░░░░░░░░░░ │
│ ▌New conv.  ×│ ┌───────────────────────────────────────────────────────┐ │
│  70d ago     │ │ 🏷 GENERAL EXPLORATION (12px caps, accent-ink)         │ │
│  New conv.  ×│ │ Compare two directors in my library…                  │ │
│  70d ago     │ │ (● The Professor ⌄)                       [🎲] [↑]    │ │ ← send: --border-field ring when empty
│ plexomat ·…  │ └───────────────────────────────────────────────────────┘ │
│ [Watchlist]  │                                                           │
└──────────────┴───────────────────────────────────────────────────────────┘
```

**Precise changes**
- Top bar is unified (VIS-025): 64px height, `--surface` 92%, 1px `--border-subtle`, no amber hairline at 390.
- Sidebar background is `--surface-2` with no extra grey veil. Thread items are `.card--interactive` with the × *inside* at 32px (one style). Active thread gets a 3px `--accent-ink` left bar.
- Starter chips use `.chip--suggestion` with `flex-wrap: wrap`. The scroll region gets `mask-image: linear-gradient(to bottom, #000 calc(100% - 24px), transparent)`.
- Context tag follows VIS-026.
- Composer border is `--border-field`. The send button is `.btn[data-variant=icon]` with the `--accent-fill` background only when text is present; otherwise ghost with a `--border-field` ring.
- Reactions use SVG `thumb_up` and `thumb_down` at 20px in `currentColor` `--muted`, with a selected state in `--accent-ink`.
- Message body is 16px/1.55 with a 72ch measure.

### 3. Explore (`qa_owner_explore_1440.png`)

**Before:** "Search" is white on gold (3.04:1). The four hub link cards have amber borders (a fourth card look). "Filling in shelves…" is plain text in a blank band, and "For you" is cut off.

```
AFTER
┌──────────────────────────────────────────────────────────────────────────┐
│ ≡  Projectionist ◎                                        ☀  (QA)        │
├──────────────────────────────────────────────────────────────────────────┤
│ ┌───────────────────────────────────────────────────┐ ┌──────────┐      │
│ │ 🔍  Search your library by title or plot…   56px  │ │  Search  │ 56px │ ← on-accent ink 5.69:1
│ └───────────────────────────────────────────────────┘ └──────────┘      │
│ ┌ Movies ─────┐ ┌ TV ─────────┐ ┌ Related ────┐ ┌ Tags ───────┐  (card--interactive,
│ │ Every film  │ │ Shows & eps │ │ Follow one  │ │ Keywords    │   --border, hover ink)
│ └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘         │
│                                                     ↕ 32px              │
│ For you                                   (H3 Fraunces 24px)             │
│ ▭▭▭▭▭▭▭▭▭▭▭▭▭▭▭▭ (skeleton line 12px × 240px)                            │
│ ┌──┐ ┌──┐ ┌──┐ ┌──┐ ┌──┐ ┌──┐   ← 6 × .skeleton--poster 160×240 (2:3)   │
│ │░░│ │░░│ │░░│ │░░│ │░░│ │░░│                                           │
│ └──┘ └──┘ └──┘ └──┘ └──┘ └──┘                                           │
│ Continue watching                                                       │
│ ┌──┐ ┌──┐ ┌──┐ …                                                        │
└──────────────────────────────────────────────────────────────────────────┘
```

**Precise changes**
- VIS-005: `.explore-search-submit` uses `color: var(--on-accent)`. Input and button are both 56px (lg) with `--radius-lg`.
- Hub link cards switch from amber borders to `.card--interactive` (`--border` at rest, `--accent-ink` 40% on hover/focus). Title 16px/600, sub 14px muted.
- Loading uses VIS-011 skeleton rails that reserve real rail height (title 24px + 240px posters + 8px gap). "Filling in shelves…" becomes visually hidden live text.
- Arrived rails show poster bitmaps (VIS-027). A missing URL renders title + year inside the 2:3 well, not a 48px initial.
- Rail gap is `--space-7` (32px).

### 4. Admin overview (`qa_owner_admin_overview_1440.png`, `qa_owner_admin_nav_1440.png`)

**Before:**
- A grey smudge behind "Overview" (VIS-004).
- About 300px before the first tile.
- The footer overlaps the "5,391" tile (VIS-009).
- The "Connected" tile value is in success green, but the "warn" tone would be amber (VIS-022).
- Vertical rotated group labels in the drawer (VIS-016).

```
AFTER (data-density="compact")
┌──────────────────────────────────────────────────────────────────────────┐
│ ≡  Projectionist ◎   Admin › Overview                     ☀  (QA)        │
├──────────────────────────────────────────────────────────────────────────┤
│ Overview                      (H1 Fraunces 38px, SOFT 0)  [Re-run setup] │
│ Stack readiness for the living room — Plex, library, and Live. (14px)    │
│                                                   ↕ 20px                 │
│ HOUSEHOLD HEALTH (?)   (eyebrow 12px caps)                               │
│ ┌──────────────┐┌──────────────┐┌──────────────┐┌──────────────┐┌─────┐ │
│ │ ● Connected  ││ 5,391        ││ 88%          ││ 0%           ││ Off │ │ ← 24px/700 tabular
│ │ Plex         ││ Indexed      ││ Unwatched    ││ Rated  ⚠     ││Live │ │
│ │ 5 libraries  ││ 4594 · 797   ││              ││ (warning tone)││     │ │
│ └──────────────┘└──────────────┘└──────────────┘└──────────────┘└─────┘ │
│  5-up at ≥1024 (minmax(180px,1fr)), padding 12/16, radius 10             │
│ ...                                                                      │
│ ──────────────────────────────────────────────────────────────────────── │
│ Help · Privacy · About   (static footer, 12px muted, 5.47:1+)            │
└──────────────────────────────────────────────────────────────────────────┘

DRAWER group label (after):   SETUP            ← 12px DM Sans 600 caps .08em, horizontal
                              Overview
                              Connections …
```

**Precise changes**
- `.admin-shell` background becomes `var(--workspace-wash-a)`.
- Compact density per VIS-040: tile padding 12 16px, numerals 24px/700 tabular-nums, grid `repeat(auto-fit, minmax(180px, 1fr))` so five tiles fit on one row at 1024+.
- `tone-warn` uses `--status-warning` plus a ⚠ icon. `tone-good` uses `--status-success` plus a ● dot.
- Footer is static at the end of `main` (VIS-009).
- A breadcrumb "Admin › Overview" in the top bar replaces the need for the giant title-plus-rule stack. The rule under the title is removed.
- Drawer group labels are horizontal eyebrows (VIS-016).

### 5. Help (`qa_help_guest_1440.png`), with the Privacy TOC fix

**Before:**
- A separate reading chrome with no brand mark ("Help" + subtitle + "← Back to chat").
- TOC links in muted 14px with a duplicate "Related titles".
- About 90px of dead space between the TOC and the body.
- Body lines of 89 characters.
- On Privacy, the same TOC concatenates (VIS-010).

```
AFTER
┌──────────────────────────────────────────────────────────────────────────┐
│ ≡  Projectionist ◎                                        ☾  Sign in     │ ← unified bar, guest variant
├──────────────────────────────────────────────────────────────────────────┤
│        ← Back to chat                                                    │
│        Help                                  (H1 Fraunces 38px)          │
│        Chat, Explore, Related titles, and idle curation  (18px lead)     │
│        ┌ Viewing as Guest — ask the owner about sync. (callout info) ┐  │
│        └─────────────────────────────────────────────────────────────┘  │
│        Start · Chat · Related titles · Plot knowledge · About · Privacy │ ← .help-jump-nav, 12/16 gap,
│                                                   ↕ 32px                 │   no duplicate, wraps
│        Projectionist is a private cinema companion for the library     │
│        you already own. It talks to your Plex catalog — not a          │ ← max-width 68ch,
│        Netflix top-10 — so every recommendation is grounded in         │   16px/1.65
│        titles you actually have.                                        │
│        ## Chat                               (H2 Fraunces 30px)          │
└──────────────────────────────────────────────────────────────────────────┘
```

**Precise changes**
- Shared top bar (VIS-025). The page header moves below it.
- "Viewing as Guest" becomes `.callout[data-tone=info]`.
- The jump nav is unscoped (VIS-010), with 12px row and 16px column gaps, link `--muted` 14px/500, hover `--accent-ink` with a 1px underline at 0.15em offset. The duplicate "Related titles" entry is removed (content fix).
- Article paragraphs are capped at 68ch, 16px/1.65 (VIS-018). Inline links use `--accent-ink` with a 1px underline (Lights Up 6.02:1).
- Gap from TOC to body is 32px instead of about 90px.
- About and Privacy use the identical template.

---

## Required deliverable 5 — Migration path (incremental, no big-bang)

Each step is an independently shippable PR, with both-theme screenshots attached.

| Step | Files to touch (in order) | Change | Risk control |
|---:|---|---|---|
| 1 | `frontend/src/styles/01-tokens.css` | **Additive only.** New tokens (`--accent-fill*`, `--accent-ink`, `--on-accent`, `--focus-ring`, `--border-field`, `--status-*`, `--radius-md/xs/xl/pill`, shadow, motion, z, ratios) plus deprecated aliases. Global reduced-motion guard (VIS-012). No visual change except reduced motion. | Inventory script diff; zero screenshot diffs expected |
| 2 | `e2e/visual-themes.spec.ts` (new), `playwright.config.*` | VIS-043 baselines (20 snapshots) before any visual edit. | CI gate |
| 3 | `frontend/src/styles/05-chat-responsive.css`, `frontend/src/styles/15-glass-door.css`, `frontend/src/pages/LoginPage.tsx` | VIS-002 login fields and stack; remove duplicate placeholder. | `/login`, `/join`, `/setup` snapshots |
| 4 | `frontend/src/styles/06-reading-admin-settings.css` | VIS-004 (wash token), VIS-010 (unscoped jump nav), VIS-017 (avatar), VIS-018 (measure). | Admin, Settings, Help, Privacy snapshots |
| 5 | `frontend/src/styles/08-dashboard-coverage-cards.css`, `frontend/src/styles/10-explore-delight.css`, `frontend/src/styles/02-nav-chrome.css` | VIS-009 static footer; VIS-005 on-accent ink; VIS-022 warning tone; remove `#c4a35a` and `#9aa3ad` fallbacks; VIS-016 horizontal labels; VIS-019 markdown heads. | Snapshots |
| 6 | All sheets (sweep), in order 02 → 16 | VIS-001: `color: var(--accent)` → `var(--accent-ink)` (99 sites); fills → `--accent-fill`; outlines → `--focus-ring`. | Lights Up axe run; Lights Down zero-diff expected |
| 7 | `frontend/index.html`, `frontend/public/fonts/*` (new), `01-tokens.css` `@font-face`, new `frontend/src/components/Icon.tsx` + `frontend/public/icons.svg` | VIS-014 self-host and subset; VIS-013 icon component; swap emoji and Unicode glyphs in `MessageReactions.tsx`, `AppNav.tsx`, `ChatWorkspace.tsx`, `StatusDock.tsx`, `PersonaSelector.tsx`, `ReviewPromptCard.tsx`. Update `docs/PRIVACY.md` third-party section. | Network allowlist test; CLS check |
| 8 | `frontend/src/styles/01a-primitives.css` (new; imported in `frontend/src/styles.css` between 01 and 02) | `.btn`, `.field` / `.input`, `.card*`, `.chip*`, `.badge`, `.status-badge`, `.callout`, `.skeleton`, `.spinner`, `.scrim`, `.dialog`, `.sheet`, `.popover`, `.tabs`, `.segmented`, `.data-table`, `.toast`. Primitives only; no call-site changes yet. | Specimen page (VIS-044) |
| 9 | `frontend/.stylelintrc.json` (new), `frontend/package.json` (`lint:css`), `.github/workflows/ci.yml` | VIS-041 in **warn** mode with a baseline. | CI |
| 10 | Feature components, highest traffic first: `LoginPage.tsx` → `ChatWorkspace.tsx` → `ExplorePage.tsx` / `PosterRailLoader.tsx` → `pages/admin/OverviewSection.tsx` → settings pages → title surfaces (`TitleCtaBar`) | Adopt primitives (VIS-003, VIS-011, VIS-021). Delete the replaced classes from feature sheets in the same PR. | Per-route snapshots |
| 11 | `frontend/src/styles/02-nav-chrome.css` (element `button` rule) | Neutralize the bare `button` only after `git grep "<button"` shows every call site has a class. | Full snapshot run |
| 12 | `frontend/src/styles/01-tokens.css` (type scale v2), `frontend/src/lib/uiPrefs.ts` (`FONT_SIZES` 15/16/18), then px → token sweep of the 142 px font-sizes | VIS-006. Two PRs: (a) scale plus root, re-baselined deliberately; (b) literal sweep. | Snapshot review of all 20; computed-size sweep at 3 preferences |
| 13 | `frontend/src/styles/12-live.css`, `frontend/src/styles/13-watch.css` | VIS-008 `--stage-*` tokens; delete 85 override selectors. | Live/Watch snapshots once Live is on QA |
| 14 | All sheets | VIS-020 breakpoints to 4 tiers (`postcss-custom-media` in `vite.config.js`). | 390 / 768 / 1024 / 1440 snapshots |
| 15 | `frontend/src/styles/06-reading-admin-settings.css` + `.admin-shell` | VIS-040 compact density. | Admin snapshots |
| 16 | `.stylelintrc.json` → **error**; remove deprecated aliases from `01-tokens.css`; rewrite `docs/DESIGN.md` "Visual language" as a token-first spec with the contrast table and specimen | Lock-in. | CI |

---

## Remediation

### Now (0–14 days)
VIS-002, VIS-004, VIS-027 (poster URL plus missing-art spec), VIS-005, VIS-010, VIS-012, VIS-017, VIS-001 (token add plus sweep), VIS-014, and VIS-043 (baselines).

### Next (15–45 days)
VIS-003 (primitives, not yet the element reset), VIS-007, VIS-009, VIS-011, VIS-013, VIS-015 (doc plus PR template), VIS-016, VIS-018, VIS-019, VIS-022, VIS-023, VIS-024, VIS-026, and VIS-041 (warn mode).

### Later (46–90 days)
VIS-006 (type scale v2), VIS-008, VIS-020, VIS-021, VIS-025, VIS-040, VIS-042, VIS-044, and the Stylelint error flip.

## Quick wins (XS, under 1 hour each)

1. VIS-002: `.login-form > form { display:grid; gap:16px }` plus the input rule.
2. VIS-004: `#16130f` → `var(--workspace-wash-a)`.
3. VIS-005: `color: var(--bg…)` → `var(--accent-text)` in 3 rules.
4. VIS-010: unscope `.help-jump-nav`.
5. VIS-012: global reduced-motion guard.
6. VIS-017: `flex: 0 0 56px` on `.settings-avatar`.
7. VIS-023: snap 650 → 600 and 550 / 560 → 600 and 800 → 700.
8. VIS-009 (partial): remove `opacity: 0.6` from `.app-footer-link`, which takes it from 3.1:1 to ≥ 5.47:1.

## Open questions

1. **Root font change (15 → 16px Medium):** is the owner willing to re-baseline every screen once, or should v2 keep 15px and only fix the scale steps? The recommendation is 16px.
2. **Material Symbols:** is the icon set expected to grow? If so, a subset build step (`icon_names`) with a self-hosted file beats a hand-made sprite.
3. **Lobby Theater (`:8795`)** was not reviewed. Should it share tokens, or stay a deliberately separate kiosk language?
4. **Persona accent colors** (purple dot on "The Professor" in `qa_owner_chat_1440.png`): is there a persona palette? It is not in tokens, so it needs a defined set of 6–8 hues, each ≥ 3:1 as a non-text dot on both surfaces.
5. **Live and Watch** were not captured on QA (Live Off), so VIS-008 is code-only. Enable Live on `:8792` before step 13.
6. **Should `system` remain the default**, or should first-run pick Lights Down and let users opt into light? This review recommends keeping `system` and making Lights Up pass (VIS-015). Product may disagree.

---

### Counts

| Type | Critical | High | Medium | Low | Total |
|---|---:|---:|---:|---:|---:|
| Weakness | 0 | 6 | 16 | 5 | 27 |
| Strength | 0 | 3 | 4 | 0 | 7 |
| Opportunity | 0 | 0 | 3 | 2 | 5 |
| **All** | **0** | **9** | **23** | **7** | **39** |

---

## Changelog

- 2026-10-29: Parent walk added **VIS-027** after the Design Director pass. The original pass judged Explore from `qa_owner_explore_1440.png` and did not open a browser. A same-day QA walk (`ux_owner_explore_1440.png`) showed every poster well as a letter fallback because `poster_url` was empty. Scorecard imagery moved from 3 to 2. No other finding was rewritten.
- 2026-10-29: Signed-in Play walk added **VIS-028** (end-card / Resume gate right-hug crop on `ux_owner_watch_endcard_1440.png` and `ux_youth_watch_mister_rogers_1440.png`). Grade stays C.
- 2026-10-30 (Chief Skeptic, Phase 4 red team): Corrected the **VIS-027** root cause and recommendation step 1. The recommendation pointed to "the existing poster proxy", but at `94fcd3f` only the Lobby Theater has one (`/api/theater/poster`). Browser payloads drop non-TMDB art by design (`privacy/schema.py`), and on QA the TMDB key could not be decrypted (OPS-010/OPS-011). So the 234-tile QA shelf is partly an environment fault, and it should not be read as "every install has no posters". The finding stays High, because installs without TMDB (including Plex-only, the persona UX-009 is built around) hit the same blank shelf. The grade (C) and scorecard are unchanged.
