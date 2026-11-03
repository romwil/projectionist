# 03 · Visual design — Projectionist 360° review, run 2026-11-01

**Design Director (`VIS`) · independent pass.** Code `05274cf` (v1.38.0), read from `/tmp/review360-05274cf`. Live checks on QA `http://10.10.1.202:8792` (owner session, read-only, Lights Up, 1440 viewport). I read only the spec, `_status.md`, and `00` platform map; no other department document.

**Grade: C+.** Counts: 15 Weaknesses, 4 Strengths, 3 Opportunities (22 total). Severity: High 6 (4 weaknesses + 2 strengths), Medium 12, Low 4.

---

# Part A — Conclusions & findings

## 1. Bottom line

Projectionist has a real brand, not a template: Fraunces over DM Sans, one amber accent, a "cinema chamber / gallery paper" pair of themes, and core token pairs that clear WCAG AA with room to spare (VIS-016, VIS-017). The system under that brand is only half built. The token file defines colors and a short type and spacing ramp. It does not define elevation, layering, motion, or breakpoints. The new `Button` primitive has **zero** call sites, and 539 bespoke `<button>` elements carry the UI instead (VIS-001, VIS-006). The most important fix is cheap: wherever Lights Up uses the gold **fill** as a text or label color, it drops to about 3:1 contrast. That includes the primary Search button on Explore (light text on gold, 3.04:1) and about 40 hard-coded literals that never adapt to the light theme (VIS-003, VIS-002). The most important thing to protect is the token-first color architecture: 3,935 `var()` references and 317 `color-mix()` derivations, all swapped by one `html[data-theme]` attribute (VIS-018). Grade **C+**: the brand earns a B+, but the system behind it, and its legibility at the small sizes it mostly uses, earn a C.

## 2. Key conclusions

1. **The brand is distinctive and worth defending, but the system behind it stops at color.** Tokens cover color (72 defined custom properties), seven font sizes, eight spacings, and three radii. Shadows (53 distinct values in 62 declarations), z-index (26 values from 1 to 1200), durations (34 values), and breakpoints (16 widths, including off-by-one pairs 768/769 and 900/901) are all hand-typed (VIS-006, VIS-007, VIS-009). The root cause is that tokens were added reactively, finding by finding (the file comments cite VIS-001/002/003 from earlier runs), rather than designed as a complete set. Roadmap: finish the token set in one PR (section "Proposed design tokens") before any screen redesign.

2. **There is no component layer. There is a CSS layer that pretends to be one.** `Button.tsx` exists and is documented in `DESIGN.md`, but no file imports it. The default for a bare `<button>` is still the gold fill (`02-nav-chrome.css:1587-1603`). 50 buttons have no class and inherit that fill, and the other 489 each carry bespoke classes (about 30 `*-btn` / `*-button` families). Across 21k lines of CSS there are 2,090 distinct class selectors and 36 different `*-card` roots (VIS-001). Live, Explore renders 7 button style variants and Title detail renders 5, and none of them is the `.btn` primitive. Roadmap: invert the bare-button default and migrate by surface (Migration path, step 2).

3. **Lights Up is the household's default look, and it is where the system leaks.** The token pairs pass in both themes (VIS-016). The failures all come from places that bypass the ink/fill split: the Explore Search button (`#f9f7f2` on `#b8860b`, 3.04:1, measured live), 11 `color: var(--accent)` text rules (3.04:1), review stars `#f5c542` (1.51:1), log-warning text `#d4b84a` (1.82:1), task-error text `#e07070` (2.92:1), and `#c45c5c` errors (3.90:1) (VIS-002, VIS-003). There is no `--warning` or `--info` token, and `--success` drops to 4.33:1 on `--surface-2` (VIS-015). The root cause is that hard-coded fallbacks written for dark mode (`var(--accent, #c4a35a)`, `#9aa3ad`) are treated as if they were tokens. Roadmap: add semantic tokens and a stylelint gate (VIS-020) so this cannot recur.

4. **The type system reads as small and busy.** The root is 15px, so `--text-sm` renders at 12.19px and `--text-xs` at 11.25px. Those two tokens account for 362 of 710 `font-size` declarations. Live on Explore, 477 leaf text nodes render at 11.25–12.19px, against 6 at 15px body size (VIS-004). On top of that there are 89 distinct `font-size` values (38% literals), 21 line-heights, 17 letter-spacings, and 66 `text-transform: uppercase` rules. For the "older user with low vision" persona, the per-user Text size setting is the only defense. Roadmap: set a 12px floor and a modular scale (Typography specimen).

5. **Chrome and hierarchy are inconsistent across the five core screens.** Title detail drops the app top bar entirely (live: no `.app-topbar`), although `DESIGN.md` says leaf pages keep "BackLink *plus* AppShell — never BackLink instead of the shell" (VIS-008). Admin Overview shows five gold "Open" buttons stacked in one list, which breaks the project's own "one gold action per action group" rule (VIS-013). Chat shows three different chip styles above the fold (VIS-009). Each of these is small, but together they make the product feel like several apps. Roadmap: the five before/after wireframes below.

6. **Motion is mostly restrained, but it has no tokens and two real defects.** There are 22 keyframes, and 16 `prefers-reduced-motion` blocks are scattered across 12 files. Seven animated selectors have no reduced-motion override, including looping ones (the lamp pulse, typing dots, skeleton shimmer) (VIS-011). The 300 ms theme cross-fade on `html`/`body`, combined with a `:root` fallback that is dark, is the likely cause of the washed-out first-paint headings the platform map flagged (P-8; VIS-010).

7. **The iconography is mostly one system, with leaks.** Material Symbols Outlined (a self-hosted ~55-glyph subset) is the declared set, but the UI also renders 39 Unicode glyphs and emoji (★ ×19, ✕, ✓, ☰ for the hamburger, 👍/👎/🔔/🔕) and 15 inline SVGs (VIS-012). These render in different fonts and weights, and the stars fail non-text contrast in Lights Up (VIS-002).

## 3. Foundations challenged

| Assumption | Evidence for | Evidence against | Verdict | Cost of change | Rationale |
|---|---|---|---|---|---|
| SC-21 Bespoke CSS (17 partials, ~21k lines) beats a component library or utility framework | Strong brand; CSS variables theme cleanly (VIS-018); no runtime cost | 2,090 class selectors, 539 bespoke buttons, 0 primitive adopters (VIS-001); 89 font sizes; 53 shadows | **Change** (keep CSS, add a component layer) | M–L, incremental | A utility framework would be a rewrite with no user benefit. The missing piece is ~12 React primitives that own their CSS, plus lint gates. Keep plain CSS and variables. |
| Two themes (Lights Up / Lights Down) plus system | Token swap is clean; dark suits Live/Watch; light suits daytime reading | Lights Up is where every contrast failure lives (VIS-002/003) | **Keep** | — | Both earn their place. Lights Up needs the token discipline Lights Down already has. |
| One amber accent, no secondary hue | Distinctive; matches "projector lamp"; DESIGN.md "no blue→violet gradients" | Amber is also used for warnings and stars, so the warning state has no colour of its own (no `--warning` token) | **Change** (add warning/info semantics, keep one brand accent) | S | A status palette is not a brand palette. Users need to tell "attention" from "primary action". |
| Fraunces display + DM Sans body | Fits the cinephile and editorial voice; self-hosted variable fonts; no Google requests | Fraunces used 64× including small labels; display used for 11px eyebrows in places | **Keep**, restrict Fraunces to ≥18px | XS | The pairing is right; misuse at small sizes is the problem. |
| "Atmosphere from ambient washes, not glow stacks or pill chrome" (DESIGN.md §Visual language) | Washes exist; restrained glow | 71 `border-radius: 999px` pills; title detail action row is 7 uppercase pills | **Change** the doc or the UI | S | The principle and the UI disagree. Recommend allowing pills only for chips and filters, and using `--radius-sm` for buttons. |
| SC-19 A dense, cinephile Admin in the same visual language as consumer | One brand, one product | Admin uses consumer spacing; five gold CTAs per list | **Change**: same brand, compact density | M | Admin should feel like the same product with tighter, utilitarian density (VIS-022). |
| Per-user Text size via `--base-font-size` | Real accessibility lever; everything in rem scales | Default 15px root makes `--text-sm` 12.19px | **Keep**, raise floors | S | The lever is good. Fix the defaults, not the mechanism. |
| Per-route bespoke page chrome (title detail without top bar) | Full-bleed hero is cinematic | Breaks wayfinding; contradicts DESIGN.md | **Change** | S | Keep the hero, and restore the slim AppShell bar over it. |

## 4. If we built it today

From scratch I would keep exactly three things: the two-theme variable architecture, the Fraunces/DM Sans/amber identity, and plain CSS. Then I would build in this order:

1. **One `tokens.css`** with complete primitives (color, type, space, radius, elevation, z, motion) and semantic aliases. Breakpoints would live as `@custom-media` constants.
2. **About 12 primitives**, each owning its CSS: Button, IconButton, Field, Select, Chip, Badge, Card, Dialog, Sheet, Toast, Tabs, Skeleton.
3. **A single page frame** (`AppShell` + `PageHeader`) used by every route.
4. **Stylelint** that rejects raw colors, font sizes, z-index, and shadows outside `tokens.css`.
5. **A `/__design` gallery**, screenshot-tested in both themes.

The gap from today is large in line count (about 21k CSS lines and 539 buttons) but small in concept, because the brand and the variables already exist. Closing it is worth it. Do it incrementally, by surface, behind the lint gate, with no visual big bang (see Migration path).

## 5. Findings by surface

**Public** (`/login`, `/join`, `/setup`, `/help`, `/privacy`). The "glass door" login card is the most disciplined surface. It has a shared field primitive (44px fields, 16px input font, `--border-field` ≥3:1) and correct fill/ink use on the primary button (`#1a1208` on gold, 5.69:1). It is let down by the first-paint cross-fade that makes the "Sign in" heading and "Need an invite?" nearly invisible in captures (`map_login_signed-in-session_1440.png`; VIS-010). Grade **B-**. IDs: VIS-010, VIS-019.

**Consumer** (Chat, Explore, Search, Title, Library, Live, Settings). This surface carries the brand best: the title hero (`map_title-detail_owner_1440.png`) and the Explore rails are genuinely cinematic. It also carries most of the defects. The Explore Search CTA fails contrast (VIS-003). Text is small by default (VIS-004). Title detail has no top bar and an action row of 7 equal-weight uppercase pills (VIS-008). Chat has three chip dialects (VIS-009). Stars and badges use hard-coded hues (VIS-002, VIS-012). The Live guide is a well-crafted timeline (time-banded cells, rating badges), but at 1440 short cells stack their time text into letter columns (`map_live-guide_owner_1440.png`, channels 100/102). Top priorities: VIS-003, VIS-004, VIS-008. Grade **C+**. IDs: VIS-002, 003, 004, 008, 009, 011, 012, 017.

**Owner** (Admin Overview, Members, Live Studio, Persona). Overview is clean and readable, with strong status tiles (Connected in success green, Warming in accent ink). But it presents five identical gold "Open" buttons, so nothing is primary (VIS-013). It uses consumer spacing for a list that should be scannable. The scheduled-task and log views hold most of the hard-coded warning and error literals (`10-explore-delight.css:764-1071`, `06-reading-admin-settings.css:947-953,1672-1678`; VIS-002). Grade **C+**. IDs: VIS-002, 013, 022.

**Admin / Ops** (Tasks, Health, Logs, Mail). These are visually the same as Owner. The Tasks table uses `tabular-nums` (good; 18 uses in the codebase), but status colors are literals, and `--warning` does not exist, so warning rows use `#c9a227`/`#d4b84a`, which fail in Lights Up (VIS-002, VIS-015). No Admin-specific findings beyond those shared with Owner. Grade **C**. IDs: VIS-002, 015, 022.

## 6. Findings by theme

- **Color & contrast.** The best example is the token table itself: every core pair passes AA in both themes, and `--accent-ink` was correctly split from `--accent` (VIS-016). The worst is Explore's primary CTA (3.04:1) and the review stars in Lights Up (1.51:1). Direction: semantic tokens for every status, a ban on literals, and a rule that "fill tokens never set `color`" (VIS-002, 003, 015).
- **Typography.** The best example is the title headline `clamp(2.5rem, 7vw, 5.25rem)` in Fraunces 600 with −0.03em tracking: confident and editorial. The worst is pervasive 11–12px UI text with uppercase tracking. Direction: a 1.2-ratio scale with a 12px floor (VIS-004).
- **Layout & spacing.** The spacing tokens exist and are used (`var(--space-2)` is the most common gap), but there are 215 distinct padding values and 106 distinct margins, mixing px, rem, and tokens (VIS-007). Direction: lint-enforced tokens on new code, with codemods per partial.
- **Components.** No real primitive layer exists (VIS-001). There are 11 modal/drawer/sheet families with separate CSS, 36 card roots, a single toast (`UndoToast`), no tooltip component, and two spinners. Direction: the consolidation plan below.
- **Iconography.** Material Symbols is the declared set; Unicode and emoji leak in (VIS-012).
- **Motion.** Durations cluster around 150 ms (52 uses), which is good instinct, but there are no tokens and reduced-motion coverage has gaps (VIS-011, VIS-010).
- **Brand consistency.** Public, consumer, and admin share fonts and accent. What drifts is chrome (title detail) and density (admin) (VIS-008, VIS-013).
- **Polish.** There are 11 references to custom properties that are never defined. `--radius-md` is referenced 14 times with four different fallbacks (8px, 10px, 12px, 0.65rem), so "medium radius" means four things (VIS-005). `DESIGN.md` points at the wrong token file (VIS-014).

## 7. Stop doing

- **Stop writing `var(--token, #literal)` fallbacks.** Tokens are always defined, so the fallback only hides typos, and the literal is a dark-mode color (VIS-002, VIS-005).
- **Stop styling the bare `button` element globally** (`02-nav-chrome.css:1587`). It makes every unclassed button a primary (VIS-001).
- **Stop adding per-feature `@media (prefers-reduced-motion)` blocks.** Use one global rule (VIS-011).
- **Stop using Unicode/emoji as UI icons** (★ ☰ ✕ 👍) (VIS-012).
- **Stop adding new `*-card`, `*-modal`, and `*-btn` roots.** Extend the primitives instead (VIS-001).
- **Stop setting Fraunces below 18px** and stop uppercase-tracking body-size labels by default (VIS-004).

## 8. Strengths worth protecting

- **Token contrast baseline** (VIS-016): text 12.6–17.1:1, muted 5.5–9.4:1, accent-ink 5.6–6.4:1, `--border-field` ≥3.1:1 on all four surfaces in both themes. Any new token must meet the same bar.
- **Brand identity** (VIS-017): Fraunces/DM Sans, self-hosted, one amber accent, cinematic hero. Do not "modernize" this into a generic SaaS look.
- **Theme architecture** (VIS-018): one attribute swap, an FOUC script in `index.html`, `color-mix()` tints derived from tokens, and per-user rem scaling.
- **Focus and field contract** (VIS-019): a global `:focus-visible` with `--accent-ink`, and 44px fields with 16px input font (no iOS zoom).

## 9. Risks of inaction (6–12 months)

- Every new feature adds another bespoke button and card family. At the current rate (about 1,000 CSS lines per minor release, judging by partial sizes), a theme or brand change becomes a 25k-line audit.
- Lights Up contrast failures keep shipping, because nothing machine-checks literals. A11y reviews will re-find the same class of bug every run. The file comments already show three rounds of "VIS-00x" patching.
- The older and low-vision household members (persona 2.2) keep meeting 11–12px text by default. Text size "Large" becomes the de facto default without anyone deciding it.
- Admin keeps the consumer density while gaining features (20 sections today), so the Monday pass takes longer to scan.

## 10. Recommended direction

**Sequence: tokens, then gate, then primitives, then screens.**

1. **Now (0–2 weeks):** Ship the contrast quick fixes (VIS-003, VIS-002 light-mode literals, VIS-013 single primary). Land the complete `tokens.css` additions as **aliases only** (no visual change). Add a stylelint warning gate (VIS-020).
2. **Next (2–6 weeks):** Make the type floor and scale change behind QA screenshots (VIS-004). Invert the bare-button default and migrate Explore, Title, and Chat to `Button`/`Chip` (VIS-001, 009). Restore the AppShell on title detail (VIS-008). Add a global reduced-motion rule (VIS-011).
3. **Later (6+ weeks):** Run the elevation, z-index, and breakpoint codemods (VIS-006). Migrate spacing (VIS-007). Build the design gallery (VIS-021) and admin compact density (VIS-022).

**90-day success indicators:**

| Indicator | Today | 90-day target |
|---|---|---|
| Hex/rgba literals outside `tokens.css` | 196 + 134 | ≤ 20 (media veils only) |
| Distinct `font-size` values | 89 | ≤ 12 |
| Distinct `box-shadow` / `z-index` values | 53 / 26 | ≤ 6 / ≤ 9 |
| `Button` primitive adopters | 0 | ≥ 60% of buttons on Explore, Title, Chat, Admin Overview |
| Text/background pairs below 4.5:1 found by axe in both themes on the 5 key screens | ≥ 3 known | 0 |
| Leaf text nodes below 12px on Explore at default size | 157 | 0 |

## 11. Scorecard (1–5)

| Surface | Color & contrast | Typography | Layout & hierarchy | Components | Motion | Brand coherence | Reason |
|---|---|---|---|---|---|---|---|
| Public | 4 | 4 | 4 | 4 | 3 | 4 | Shared field primitive and correct CTA ink; first-paint fade (VIS-010) |
| Consumer | 2 | 2 | 3 | 2 | 3 | 4 | Strong hero and rails; CTA contrast, small type, chrome drift |
| Owner | 3 | 3 | 3 | 2 | 4 | 3 | Readable tiles; five primaries; literal status colors |
| Admin/Ops | 2 | 3 | 3 | 2 | 4 | 3 | Tabular numbers good; no warning token; consumer density |

---

# Part B — Detailed findings

## 12. Scope & method

- **Code measurement** over all 20 CSS files (`frontend/src/styles/*.css`, `styles.css`, two component CSS files; 21,164 lines) with comments stripped, plus a scan of all `.tsx`/`.jsx` (inline `style={{}}`: 34; hex in TS/TSX: 3). Counts are from Python and ripgrep over `/tmp/review360-05274cf/frontend/src`.
- **Contrast ratios** computed with the WCAG 2.x relative-luminance formula from the token hex values in `05274cf:frontend/src/styles/01-tokens.css:41-136` and from literal values found in partials.
- **Live verification** on QA `:8792` (Lights Up, 1440, owner session) using CDP `Runtime.evaluate` to read computed styles on `/explore` and `/title/movie/348`. No saves, no Watch/Play, no Live tune, no chat sends.
- **Screenshots:** reused the platform map `map_*` captures. I took no new `vis_` captures (time box), so every visual citation points at an existing `map_` file.
- **Not reviewed:** Lights Down live (code only); 390px live (from `map_*_390.png` only); member/youth sessions; the lobby theater `:8791` (off-limits); email templates; Year in Review rendering; print styles.

### 12.1 Measured design-system audit (all values from `05274cf`)

| Dimension | Declarations | Distinct values | Tokenized share | Top values | One-offs and near-duplicates |
|---|---|---|---|---|---|
| Colors: hex | 196 uses | 78 | n/a (all literals) | `#000` ×21, `#c4a35a` ×20 (as a fallback), `#9aa3ad` ×11 | 4 near-duplicate golds outside tokens: `#c4a35a`, `#c4a574`, `#c6a15b`, `#c9a227`. 5 reds: `#c45c5c`, `#c45c4a`, `#c44`, `#e07070`, `#ff6b6b`. 4 star/warn yellows: `#f5c542`, `#fbbf24`, `#d4a017`, `#d4b84a` |
| Colors: rgba | 134 uses | 81 | — | mostly `rgba(0,0,0,.25–.5)` shadows | — |
| `color-mix()` | 317 | — | derived from tokens (good) | — | — |
| `var()` references | 3,935 | 81 names | 72 names defined | — | **11 undefined**: `--radius-md`, `--foreground`, `--text-secondary`, `--text-muted`, `--warning`, `--warning-text`, `--gold`, `--accent-strong`, `--surface-3`, `--surface-elevated`, `--fg` |
| Font family | 131 | 16 | 77% via `var(--font-*)` | display 64, body 28 | 6 different literal monospace stacks; `"DM Sans"` literal ×2 (the non-variable name, which never loads) |
| Font size | 710 | **89** | 62% tokens | `--text-sm` 187, `--text-xs` 175, `14px` 37, `12px` 27, `13px` 26 | `0.78rem`, `0.8rem`, `0.85rem`, `0.9rem`, `0.92rem`, `0.95rem` all sit within 2px of each other |
| Font weight | 205 | 9 | 0% | 600 ×125 | `650`, `560`, `550` (variable-font one-offs) |
| Line height | 184 | 21 | 8% tokens | `1` ×36, `1.45` ×35, `1.4` ×22 | `1.05`, `1.1`, `1.15`, `1.2`, `1.25`, `1.3`, `1.35`, `1.4`, `1.45`, `1.5`, `1.55`, `1.6`, `1.65` |
| Letter spacing | 111 | 17 | 0% | `0.04em` ×37 | 0.01–0.22em in 13 steps |
| Uppercase | 66 rules | — | — | — | — |
| Spacing: gap | 714 | 63 | ~52% tokens | `--space-2` 156, `--space-3` 105 | `0.35rem` ×28, `0.15rem` ×16, `0.55rem` ×13, `0.45rem` ×9 |
| Spacing: padding | 603 | **215** | ~25% tokens | `0` 113 | `10px 12px`, `12px 14px`, `0.65rem 0.75rem`, `0.6rem 0.75rem` |
| Spacing: margin | 544 | 106 | ~20% tokens | `0` 256 | — |
| Border radius | 396 | 41 | ~45% tokens | `--radius` 82, `999px` 71, `--radius-sm` 63 | `8px` ×22, `10px` ×22, `12px` ×21 as literals next to tokens of 6/10/14 |
| Box shadow | 62 | **53** | 0% | — | 14 variants of "big dark drop shadow" between `0 8px 24px` and `0 24px 60px` |
| Border width | 338 | 3 | — | `1px` ×323 | Good |
| Z-index | 98 | **26** | 0% | `2` ×15, `1` ×13 | 40/41/45, 80/85/90, 1000/1200 |
| Breakpoints (`@media` width) | 55 | **16** | 0% | 720 ×13, 640 ×9, 768 ×9, 900 ×9 | 768/769, 900/901, 926, 960, 990 |
| Durations | 155 | **34** | 0% | `0.15s` ×52, `160ms` ×11, `300ms` ×11 | 140/150/160/180 ms all in use; ms and s units mixed |
| Easing | 132 | 4 | — | `ease` ×102 | No custom curves |
| Keyframes | 22 | 22 | — | — | 7 animated selectors lack reduced-motion overrides |
| `!important` | 11 | — | — | — | — |
| `backdrop-filter` | 19 | — | — | — | Performance-sensitive on low-end iPad |
| `tabular-nums` | 18 | — | — | — | Good |
| Class selectors | — | 2,090 | — | — | 36 `*-card` roots, 11 modal/drawer/sheet roots, ~30 button families |

### 12.2 Contrast of text/background pairs in use (WCAG ratio; AA = 4.5 for text, 3.0 for large text and UI)

**Tokens, Lights Down** (bg `#0d0d0d` / surface `#101218` / surface-2 `#171a22` / raised `#1c2029`):

| Foreground | bg | surface | surface-2 | raised | Verdict |
|---|---|---|---|---|---|
| `--text` `#e6e2d6` | 15.01 | 14.45 | 13.43 | 12.59 | AAA |
| `--muted` `#9a958a` | 6.52 | 6.28 | 5.83 | 5.47 | AA |
| `--accent` / ink `#ffb800` | 11.21 | 10.79 | 10.03 | 9.40 | AAA |
| `--danger` `#e8918a` | 8.19 | 7.89 | 7.33 | 6.87 | AAA |
| `--success` `#7dba98` | 8.65 | 8.33 | 7.74 | 7.26 | AAA |
| `--border-field` `#636d82` (UI) | 3.74 | 3.60 | 3.35 | 3.14 | AA non-text |
| `--border` `#2c313c` (UI) | 1.49 | 1.44 | 1.33 | 1.25 | Decorative only (correct) |
| literal `#c45c5c` | 4.66 | 4.49 | 4.17 | 3.91 | **Fails** on surface-2/raised |

**Tokens, Lights Up** (bg `#f9f7f2` / surface `#fbf9f4` / surface-2 `#f0eee9` / raised `#ffffff`):

| Foreground | bg | surface | surface-2 | raised | Verdict |
|---|---|---|---|---|---|
| `--text` `#1b1c19` | 15.99 | 16.27 | 14.76 | 17.12 | AAA |
| `--muted` `#4d4635` | 8.74 | 8.90 | 8.07 | 9.36 | AAA |
| `--accent-ink` `#735c00` | 6.02 | 6.12 | 5.56 | 6.44 | AA |
| `--accent` fill `#b8860b` **as text** | 3.04 | 3.09 | 2.81 | 3.25 | **Fails** (VIS-003) |
| `--danger` `#ba1a1a` | 6.03 | 6.14 | 5.57 | 6.46 | AA |
| `--success` `#2e7d57` | 4.68 | 4.77 | **4.33** | 5.02 | **Fails** on surface-2 (VIS-015) |
| `--border-field` `#857a62` (UI) | 3.96 | 4.03 | 3.65 | 4.24 | AA non-text |
| literal `#c45c5c` | 3.90 | 3.97 | 3.60 | 4.17 | **Fails** |
| literal `#e07070` (task error) | 2.92 | — | — | 3.12 | **Fails** |
| literal `#d4b84a` (log warning) | 1.82 | — | — | 1.95 | **Fails** |
| literal `#f5c542` (review star, non-text) | 1.51 | — | — | 1.62 | **Fails 3:1** |
| literal `#d4a017` (double-feature icon) | 2.22 | — | — | 2.38 | **Fails 3:1** |
| literal `#c99a57` (partial watch state) | 2.38 | — | — | 2.55 | **Fails** |
| literal `#9aa3ad` (as fallback only) | 2.39 | — | — | — | Not rendered while `--muted` is defined; latent |

**Inverse pairs (text on a fill):** `--accent-text` `#1a1208` on gold: 10.68 (dark) and 5.69 (light), both AA. **Explore Search button live: `#f9f7f2` on `#b8860b` = 3.04, which fails AA** (VIS-003). `--ink-on-media` `#e6e2d6` on black: 16.2. `--muted-on-media` `#c8c2b4` on black: 11.8.

## 13. Strengths

### VIS-016: Protect the token contrast baseline in both themes

| Field | Value |
|---|---|
| Type | Strength |
| Surface | Cross-cutting |
| Persona(s) | All; older user with low vision; screen-reader/low-vision users |
| Category | Color & contrast |
| Severity | High |
| Impact | 5 |
| Effort | XS |
| Confidence | Confirmed |
| Priority score | 15.0 |
| Verdict | Protect |
| Dependencies | Basis for VIS-003, VIS-015, VIS-020 |
| Labels | tokens, contrast, theming |

**Evidence:** `05274cf:frontend/src/styles/01-tokens.css:80-136`; ratios in §12.2 (text ≥12.59, muted ≥5.47, accent-ink ≥5.56, border-field ≥3.14 across 8 surface/theme pairs). The comments at `01-tokens.css:47-49,54-58,121-123` record the reasoning.

**Current state:** Every core pair passes AA in both themes, and text passes AAA. The fill/ink split (`--accent` vs `--accent-ink`) is a mature pattern.

**Root cause:** Earlier review cycles drove explicit contrast targets into the token comments.

**Recommendation:** Keep these values. Add a unit test (`frontend/src/lib/tokens.contrast.test.mjs`) that parses `01-tokens.css` and asserts every `--text*`/`--*-ink` token against every `--surface*`/`--bg` at ≥4.5:1, and every `--border-field`/`--focus` at ≥3:1.

**Rationale:** The baseline is good today, but nothing prevents regression. A test costs about one hour.

**User story:** As a low-vision member, I want every label to stay readable in both themes so that I never have to switch themes to read.

**Acceptance criteria:**
- [ ] The contrast test runs in `npm run test:unit` and fails on any pair below its threshold
- [ ] All existing tokens pass

**Success metric:** 0 token-pair regressions across releases.

**Validation:** Change `--muted` in Lights Up to `#8a8270` and confirm the test fails.

**Protect this:** Any new semantic token (warning, info) must enter with its contrast row in §12.2 and in the test.

### VIS-017: Protect the Fraunces/DM Sans/amber cinematic identity

| Field | Value |
|---|---|
| Type | Strength |
| Surface | Cross-cutting |
| Persona(s) | All members; power consumer |
| Category | Brand |
| Severity | High |
| Impact | 5 |
| Effort | XS |
| Confidence | Confirmed |
| Priority score | 15.0 |
| Verdict | Protect |
| Dependencies | — |
| Labels | brand, typography |

**Evidence:** `01-tokens.css:12-14`; `00-fonts.css:11-24` (self-hosted variable fonts and a Material subset); title hero `09-title-detail-home.css:195-198` (`clamp(2.5rem, 7vw, 5.25rem)`); live h1 measured at 78.75px / 600 / −2.36px tracking; `map_title-detail_owner_1440.png`, `map_explore_owner_1440.png`.

**Current state:** The product looks like a cinephile's private screening room, not a generic dashboard. The hero composition on title detail is the best screen in the product.

**Root cause:** A clear art direction, written down in `docs/DESIGN.md` §Visual language.

**Recommendation:** Keep the families, the single amber accent, and the full-bleed hero. Restrict Fraunces to ≥18px (headings h1–h4, display, hero) so its optical character shows. Keep DM Sans for all UI text.

**Rationale:** Brand distinctiveness is the product's main differentiator against native Plex apps (platform map §5). A redesign toward a neutral look would lose it.

**User story:** As a household member, I want Projectionist to feel like a special place, not another settings app, so that I choose it over the Plex home screen.

**Acceptance criteria:**
- [ ] The token proposal keeps `--font-display`/`--font-body` unchanged
- [ ] No Fraunces below 18px on the five key screens

**Success metric:** Qualitative: the brand is kept in every before/after wireframe below.

**Validation:** Computed-style audit: `font-family` Fraunces only on nodes with `font-size` ≥18px.

**Protect this:** No gradient accents and no second brand hue.

### VIS-018: Protect the single-attribute theme architecture

| Field | Value |
|---|---|
| Type | Strength |
| Surface | Cross-cutting |
| Persona(s) | All |
| Category | Theming |
| Severity | Medium |
| Impact | 4 |
| Effort | XS |
| Confidence | Confirmed |
| Priority score | 8.0 |
| Verdict | Protect |
| Dependencies | Enables VIS-002, VIS-020 |
| Labels | tokens, theming, architecture |

**Evidence:** `01-tokens.css:80-136` (`html[data-theme]`); FOUC script `05274cf:frontend/index.html:12-46`; `lib/uiPrefs.ts:22,97`; 3,935 `var()` references; 317 `color-mix()` uses; only 3 hex values in TS/TSX.

**Current state:** Themes swap by one attribute. Tints are derived from tokens rather than hard-coded. Per-user text size scales everything in rem through `--base-font-size`.

**Root cause:** Good early architectural decision.

**Recommendation:** Keep it. Extend the same pattern to density (`html[data-density="compact"]`, VIS-022) rather than adding new mechanisms.

**Rationale:** This architecture is what makes the whole token migration incremental and cheap.

**User story:** As a member, I want my theme and text size to apply everywhere instantly so that the app feels consistent.

**Acceptance criteria:**
- [ ] No new component introduces theme-specific selectors except in `tokens.css`, `12-live.css`, and `13-watch.css` (the media surfaces)

**Success metric:** The count of `[data-theme=` selectors outside those files stays at ≤2.

**Validation:** `rg -c 'data-theme' frontend/src/styles` in CI.

**Protect this:** Do not move to CSS-in-JS theming.

### VIS-019: Protect the focus ring and public field primitive

| Field | Value |
|---|---|
| Type | Strength |
| Surface | Public, Cross-cutting |
| Persona(s) | Keyboard-only user; first-time visitor; mobile user |
| Category | Components |
| Severity | Medium |
| Impact | 3 |
| Effort | XS |
| Confidence | Confirmed |
| Priority score | 6.0 |
| Verdict | Protect |
| Dependencies | Model for VIS-001 Field primitive |
| Labels | focus, forms |

**Evidence:** `01-tokens.css:306-319` (global `:focus-visible` 2px `--accent-ink`, offset 2px); `05-chat-responsive.css:595-632` (`.login-field input`: `min-height: var(--tap-min)` 44px, `font-size: 16px`, `--border-field`); `map_login_signed-in-session_1440.png`.

**Current state:** Every focusable element gets a visible ring that meets 3:1 on every surface. Public forms share one field style.

**Root cause:** A deliberate focus contract (`DESIGN.md` §Focus contract).

**Recommendation:** Promote `.login-field` into the `Field` primitive (the consolidation plan) unchanged.

**Rationale:** It is the only component in the product that already behaves like a design-system primitive.

**User story:** As a keyboard user, I want to always see where focus is so that I never get lost.

**Acceptance criteria:**
- [ ] The `Field` primitive reuses these exact values
- [ ] No `outline: none` without a replacement ring

**Success metric:** 0 `outline: none` without a sibling `:focus-visible` rule.

**Validation:** Stylelint rule plus a keyboard walk of `/login`.

**Protect this:** Do not swap the ring to `--accent` fill (2.81:1 on Lights Up surface-2).

## 14. Weaknesses (sorted by priority score)

### VIS-003: Stop using the gold fill as a text color in Lights Up

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Consumer, Admin |
| Persona(s) | All members in Lights Up; older user with low vision |
| Category | Color & contrast |
| Severity | High |
| Impact | 4 |
| Effort | XS |
| Confidence | Confirmed |
| Priority score | 12.0 |
| Verdict | Fix |
| Dependencies | — (quick win); reinforced by VIS-020 |
| Labels | contrast, lights-up, quick-win, a11y |

**Evidence:**
- Live `/explore` (Lights Up): `.explore-search-submit` computed `color: rgb(249,247,242)` on `background: rgb(184,134,11)` at 15px/600, which is **3.04:1**. Source: `05274cf:frontend/src/styles/10-explore-delight.css:306-315` (`color: var(--bg, #10141b); background: var(--accent, #c4a35a)`).
- There are 11 `color: var(--accent)` text rules (3.04:1 on bg, 2.81:1 on surface-2): `10-explore-delight.css:720,765,834,882,992,1067,2397`; `07-persona-editorial.css:439`; `06-reading-admin-settings.css:863`; `components/MessageText.css` (2).
- `map_explore_owner_1440.png` shows the Search button.

**Current state:** The fill/ink rule (`--accent` for fills, `--accent-ink` for text) exists in tokens but is not enforced. The primary CTA on the hub screen fails AA.

**Root cause:** Code written in Lights Down, where the fill doubles as ink (`--accent-ink: var(--accent)`), and never checked in Lights Up.

**Recommendation:**
1. In `10-explore-delight.css:311-312`, use `color: var(--accent-text); background: var(--accent);` (5.69:1 in Lights Up, 10.68:1 in Lights Down).
2. Replace all 11 `color: var(--accent…)` rules with `color: var(--accent-ink)`.
3. Delete the `#c4a35a` and `#10141b` fallbacks.

**Rationale:** This is the most-seen primary button in the consumer app. The fix is mechanical and matches the existing `.btn-primary` rule (`01-tokens.css:268-271`). I rejected darkening the global `--accent` fill, because it would dull the brand gold everywhere.

**User story:** As a member using Lights Up, I want the Search button label to be readable so that the primary action is obvious.

**Acceptance criteria:**
- [ ] `.explore-search-submit` computed contrast is ≥4.5:1 in both themes
- [ ] `rg "(^|[^-])color:\s*var\(--accent[,)]" frontend/src` returns 0
- [ ] No `var(--accent, #…)` fallbacks remain in `10-explore-delight.css`

**Success metric:** axe "color-contrast" violations on `/explore` (Lights Up) go to 0.

**Validation:** CDP computed-style check on `:8792/explore`, plus Playwright axe in both themes.

### VIS-013: Use one primary per action group on Admin Overview

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Owner |
| Persona(s) | Established owner at scale |
| Category | Visual hierarchy |
| Severity | Medium |
| Impact | 3 |
| Effort | XS |
| Confidence | Confirmed |
| Priority score | 6.0 |
| Verdict | Fix |
| Dependencies | VIS-001 (use `Button variant`) |
| Labels | admin, hierarchy, quick-win |

**Evidence:** `map_admin-overview_owner_1440.png` shows five gold "Open" buttons in "5 things need attention", plus a gold "Setup checklist" button. `docs/DESIGN.md:440` and `components/Button.tsx:8-9` say "Only one `variant="primary"` should exist per action group". The source is `components/OwnerOpsOverview.tsx` and `OwnerOpsOverview.css` (bare buttons inherit the gold default, `02-nav-chrome.css:1587`).

**Current state:** Six equal-weight gold buttons, so the eye has nowhere to land. The list reads as six alarms.

**Root cause:** The bare `<button>` defaults to gold (VIS-001).

**Recommendation:** Make each row clickable as a whole (`<a class="ops-attention-row">` with a trailing `chevron_right` icon). Use `Button variant="secondary" size="sm"` labelled with the verb ("Test connection", "Pin key", "Download backup", "Start pass"). Reserve one `primary` for the top item only if it is severity "action required". "Setup checklist" becomes `variant="ghost"`.

**Rationale:** The owner's weekly pass is a scan. Hierarchy should show what matters first. Verb labels also remove "Open" ambiguity.

**User story:** As an owner, I want the most urgent item to stand out so that my Monday pass takes less time.

**Acceptance criteria:**
- [ ] At most 1 gold-fill button visible in the Overview viewport at 1440
- [ ] Each attention row has a specific verb label

**Success metric:** The count of `.btn-primary` / gold-fill buttons on `/admin/overview` is ≤1.

**Validation:** A Playwright computed-style count of buttons with `background-color` = accent.

### VIS-002: Replace hard-coded status and decorative colors with semantic tokens

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Consumer, Owner, Admin |
| Persona(s) | All members in Lights Up; owner reading logs and tasks |
| Category | Color & contrast |
| Severity | High |
| Impact | 4 |
| Effort | M |
| Confidence | Confirmed |
| Priority score | 4.0 |
| Verdict | Fix |
| Dependencies | VIS-015 (needs `--warning`, `--star`), VIS-020 |
| Labels | tokens, contrast, lights-up |

**Evidence:**
- There are 78 distinct hex literals (196 uses) and 81 rgba literals (134 uses) outside `01-tokens.css` (§12.1). Only 3 partials have any `lights-up` overrides beyond the media surfaces (`12-live.css` 65, `13-watch.css` 22, the others ≤1).
- Failing in Lights Up (ratios in §12.2):
  - review stars `02-nav-chrome.css:2612,2698,2704` (`#f5c542`, 1.51:1)
  - double-feature icon `08-dashboard-coverage-cards.css:828` (`#d4a017`, 2.22:1)
  - task error `10-explore-delight.css:988` (`#e07070`, 2.92:1)
  - errors `10-explore-delight.css:770,1071`, `05-chat-responsive.css:918,933` (`#c45c5c`, 3.90:1)
  - log warning `06-reading-admin-settings.css:1678` (`#d4b84a`, 1.82:1)
  - partial watch state `03-browse-controls.css:422` (`#c99a57`, 2.38:1)
  - `03-browse-controls.css:612` (`#fbbf24`, 1.56:1)

**Current state:** Status, rating, and decorative colors were picked for Lights Down and never adapt.

**Root cause:** There is no semantic token for warning, info, rating/star, or "partial", so authors reached for hex.

**Recommendation:** Add `--warning`, `--warning-ink`, `--info`, `--info-ink`, `--star`, and soft variants (see the token block). Replace every literal above:

| Literal | Replace with |
|---|---|
| `#f5c542`, `#fbbf24`, `#d4a017` | `var(--star)` |
| `#e07070`, `#c45c5c`, `#c45c4a`, `#c44`, `#ff6b6b` | `var(--danger)` |
| `#d4b84a`, `#c9a227`, `#c9842a` | `var(--warning-ink)` |
| `#c99a57` | `var(--warning-ink)` |
| `#c4a35a`, `#c4a574`, `#c6a15b` | `var(--accent)` (fill) or `var(--accent-ink)` (text) |

Leave `#000`/`#fff` only on media veils (`--picture-black`, `--ink-on-media`).

**Rationale:** Fixing it at the token level fixes both themes at once and prevents recurrence. I rejected per-selector `lights-up` overrides: that doubles the CSS and repeats the original mistake.

**User story:** As a member in Lights Up, I want stars, warnings, and errors to be visible so that I can read ratings and problems at a glance.

**Acceptance criteria:**
- [ ] All literals in the table are replaced
- [ ] Hex count outside `tokens.css`, `12-live.css`, and `13-watch.css` is ≤10
- [ ] Every replaced pair is ≥4.5:1 (text) or ≥3:1 (icons/stars) in both themes

**Success metric:** The hex/rgba literal count falls from 330 to ≤40 in the first pass.

**Validation:** `rg -c '#[0-9a-fA-F]{3,8}\b' frontend/src/styles`; a visual diff of the review stars and the Tasks page in Lights Up.

### VIS-004: Raise the type floor and adopt a modular scale

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Cross-cutting (worst on Consumer: Explore, Chat, Live) |
| Persona(s) | Older user with low vision; phone user on the couch; all members |
| Category | Typography |
| Severity | High |
| Impact | 4 |
| Effort | M |
| Confidence | Confirmed |
| Priority score | 4.0 |
| Verdict | Fix |
| Dependencies | Token block; QA screenshots before and after |
| Labels | typography, legibility, tokens |

**Evidence:**
- The root is `--base-font-size: 15px` (`01-tokens.css:30,75`), so `--text-xs: 0.75rem` renders at 11.25px and `--text-sm: 0.8125rem` at 12.19px (`01-tokens.css:15-16`).
- Those two tokens make up 362 of 710 font-size declarations.
- Live `/explore` computed leaf-text sizes: 11.25px ×157, 12.19px ×320, 12.75px ×80, 15px ×6, 15.75px ×580 (mostly icons/rails), 20–20.6px headings.
- There are 89 distinct font-size values, 21 line-heights, 17 letter-spacings, 9 weights (`650`, `560`, `550` one-offs), and 66 uppercase rules.
- Title chips render at 11.25px uppercase with 0.9px tracking (live `/title/movie/348`).
- Rail explanations in `map_explore_owner_1440.png` are small grey text under each poster.

**Current state:** Most UI text is 11–12px. Small uppercase tracked labels repeat on every card. Hierarchy relies on many near-identical sizes (0.78/0.8/0.85/0.9/0.92/0.95rem).

**Root cause:** The rem tokens were designed against a 16px root, but the root was set to 15px. Literals then filled the gaps.

**Recommendation:** Adopt the specimen in "Typography specimen" (ratio 1.2 on a 15px root, 12px floor):
- `--text-xs` → `0.8rem` (12px)
- `--text-sm` → `0.875rem` (13.1px)
- `--text-md` → `0.9375rem` (14.1px, unchanged)
- body `1rem` (15px)
- Add `--text-3xl` / `--text-display`.
- Map every literal to the nearest step (codemod table in Migration path).
- Uppercase only for `label`/`eyebrow` styles, at ≥12px with 0.06em tracking.
- Weights limited to 400, 500, 600, 700.

**Rationale:** A one-token change lifts 362 declarations by about 0.8px each with near-zero risk, and the codemod removes the near-duplicates. I rejected changing the root to 16px: it shifts every rem-based layout at once, and the per-user "medium" contract depends on 15px.

**User story:** As an older household member, I want card text readable at the default size so that I don't need to hunt for Text size settings.

**Acceptance criteria:**
- [ ] No rendered text below 12px at the "medium" text size on the 5 key screens (computed-style audit)
- [ ] Distinct font-size values are ≤12 (tokens plus `clamp()` display)
- [ ] Line-heights limited to `--leading-tight` (1.25), `--leading-snug` (1.4), `--leading-body` (1.55), and `1` for icons

**Success metric:** Leaf text nodes below 12px on `/explore` go from 157 to 0.

**Validation:** A CDP `Runtime.evaluate` font-size histogram before and after on `:8792`; a Playwright screenshot diff at 390 and 1440.

### VIS-005: Define or remove the 11 phantom custom properties

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Cross-cutting |
| Persona(s) | Engineers; all users (inconsistent radii and colors) |
| Category | Token hygiene |
| Severity | Medium |
| Impact | 3 |
| Effort | S |
| Confidence | Confirmed |
| Priority score | 3.0 |
| Verdict | Fix |
| Dependencies | Token block; VIS-020 |
| Labels | tokens, polish |

**Evidence:**
- `--radius-md` is used 14×, with fallbacks `0.65rem` (`12-live.css:66,153,180`), `8px` (`04-config-onboarding.css:1286,1608,1718`), `10px` (`07-persona-editorial.css:448,464`), `12px` (`02-nav-chrome.css:834`), and none at all (`08-dashboard-coverage-cards.css:820`, which computes to 0 radius).
- `--foreground` has no fallback (`08-dashboard-coverage-cards.css:709,737,761`).
- `--text-secondary` has no fallback (`02-nav-chrome.css:2166`).
- `--gold` (`09-title-detail-home.css:2095`, `04-config-onboarding.css:1481`).
- `--warning`, `--warning-text` (`10-explore-delight.css:2387`, `06-reading-admin-settings.css:947-953`).
- `--accent-strong`, `--surface-elevated`, `--surface-3`, `--text-muted`, `--fg`.

**Current state:** Medium radius means four different things. Some rules fall back to inherited color or 0 radius silently.

**Root cause:** Names borrowed from other systems (shadcn's `--foreground`, Material's `--surface-3`) without adding them to the token file.

**Recommendation:**
- Define `--radius-md: 10px` (alias of `--radius`), `--warning`, `--warning-ink`, and `--surface-3: var(--surface-raised)`.
- Rename `--foreground`/`--fg` → `--text`, `--text-muted`/`--text-secondary` → `--muted`, `--gold`/`--accent-strong` → `--accent-ink` (when used as text) or `--accent`, `--surface-elevated` → `--surface-raised`.
- Then delete every fallback argument.

**Rationale:** Undefined variables fail silently. This is pure hygiene, but it is the precondition for the lint gate.

**User story:** As an engineer, I want every token name to resolve so that I can trust what I read in CSS.

**Acceptance criteria:**
- [ ] A script lists 0 `var(--x)` references without a definition
- [ ] 0 `var(--token, fallback)` forms remain outside `tokens.css`

**Success metric:** Undefined-variable count goes from 11 to 0.

**Validation:** Re-run the §12 audit script, or stylelint `no-unknown-custom-properties`.

### VIS-008: Keep the AppShell top bar on title detail

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Consumer |
| Persona(s) | Returning consumer; screen-reader and keyboard users; phone user |
| Category | Layout & brand consistency |
| Severity | Medium |
| Impact | 3 |
| Effort | S |
| Confidence | Confirmed |
| Priority score | 3.0 |
| Verdict | Fix |
| Dependencies | VIS-001 (action buttons) |
| Labels | layout, chrome, title-detail |

**Evidence:** Live `/title/movie/348`: `document.querySelector('.app-topbar')` is `null`; the header is only "☰" plus "← Back to chat" plus a "MOVIE" eyebrow (`map_title-detail_owner_1440.png`). `docs/DESIGN.md:83` says "Leaf pages … keep **BackLink *plus* AppShell** — never BackLink instead of the shell." The action row is 7 uppercase pill buttons with the same weight except Play (live: `999px` radius, 12.19px/700, uppercase, 50px tall). There are 5 button style variants on the page.

**Current state:** Users lose Search, Chat, Explore, and Inbox on the most visited leaf page. The action row reads as seven equal options.

**Root cause:** The hero was built as a standalone composition. The shell was dropped to give the hero space.

**Recommendation:**
- Render the standard top bar in an overlay variant (`.app-topbar--over-media`: transparent background, `--ink-on-media` icons, a `linear-gradient(to bottom, rgb(0 0 0/.55), transparent)` scrim 96px tall) that turns solid after 80px of scroll.
- Action row: Play as `Button primary lg`; Trailer, Watched, and Together as `Button secondary md`; Rate, Chat, and More collapse into a `More` menu.
- Labels in sentence case, not uppercase.

**Rationale:** It restores wayfinding without losing the cinematic hero, and cuts decision load from 7 to 4. I rejected a fully solid bar because it would cover the hero.

**User story:** As a member reading about a film, I want to jump to Search or Chat without going back so that browsing feels continuous.

**Acceptance criteria:**
- [ ] `.app-topbar` is present on `/title/*`, `/person/*`, and `/tag/*`
- [ ] At most 4 visible actions in the hero row; one primary
- [ ] Top bar icons are ≥4.5:1 against the scrim at the top of a light poster

**Success metric:** Navigation from title detail to Search/Chat without using Back (needs on-box telemetry; Growth to confirm).

**Validation:** A Playwright check for `.app-topbar` on `/title/movie/:id`, and screenshots over a light and a dark backdrop.

### VIS-015: Complete the semantic status palette

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Cross-cutting (Owner/Admin heaviest) |
| Persona(s) | Owner; all members |
| Category | Color semantics |
| Severity | Medium |
| Impact | 3 |
| Effort | S |
| Confidence | Confirmed |
| Priority score | 3.0 |
| Verdict | Fix |
| Dependencies | Blocks VIS-002 |
| Labels | tokens, status, contrast |

**Evidence:** `01-tokens.css` defines only `--danger` and `--success`; there is no `--warning` or `--info`. Lights Up `--success` `#2e7d57` measures 4.33:1 on `--surface-2` (§12.2). Amber `--accent` does double duty as brand and "Warming/attention" (Admin tile "Warming" in `map_admin-overview_owner_1440.png`). `InlineAlert` has only `-error`/`-success` variants (selectors `inline-alert-error`, `inline-alert-success`).

**Current state:** Warnings are either brand-gold (confusing) or hex literals (failing).

**Root cause:** The status palette was never designed. It grew with features.

**Recommendation:** Add the tokens in the token block:
- Lights Down: `--warning` `#f0a35e` (9.35:1 on bg), `--info` `#8db7e0` (9.24:1).
- Lights Up: `--warning` `#9a4a00` (5.40–6.26:1), `--info` `#2c5d8a` (5.96–6.91:1), and change `--success` to `#276b4a` (5.51–6.39:1).
- Each gets a `-soft` background via `color-mix(in srgb, var(--x) 12%, transparent)`.
- Add `InlineAlert` `warning` and `info` variants, each paired with an icon (`warning`, `info`) so color is never the only signal.

**Rationale:** Status must be distinct from brand, or "Warming" reads as a call to action.

**User story:** As an owner, I want warnings to look different from primary buttons so that I can tell "needs care" from "do this".

**Acceptance criteria:**
- [ ] All four status tokens pass ≥4.5:1 on all four surfaces in both themes (contrast test from VIS-016)
- [ ] `InlineAlert` supports `error | warning | info | success`

**Success metric:** 0 status literals in the CSS (see VIS-002).

**Validation:** Unit contrast test; a visual check of the Admin Tasks and Logs pages.

### VIS-001: Adopt the Button primitive and build the missing component layer

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Cross-cutting |
| Persona(s) | All; engineers |
| Category | Components |
| Severity | High |
| Impact | 4 |
| Effort | L |
| Confidence | Confirmed |
| Priority score | 2.4 |
| Verdict | Rethink |
| Dependencies | Token block; enables VIS-008, 009, 013 |
| Labels | components, design-system, consolidation |

**Evidence:**
- `05274cf:frontend/src/components/Button.tsx:1-34` is imported by **0** files (`rg "components/Button"`).
- There are 539 `<button>` elements in TSX. 50 have no `className` and inherit the global gold fill (`02-nav-chrome.css:1587-1603`); 489 carry bespoke classes (about 30 `*-btn`/`*-button` families, such as `dash-purge-btn`, `live-osd-btn`, `scheduled-task-icon-btn`).
- 2,090 distinct class selectors; 36 `*-card` roots; 11 modal/drawer/sheet roots (`confirm-modal`, `bulk-delete-modal`, `media-issue-modal`, `recommend-modal`, `removal-summary-modal`, `trailer-modal`, `persona-modal`, `journey-drawer`, `app-nav-drawer`, `chat-footnote-sheet`, `title-detail-drawer-panel--modal`); 1 toast; 0 tooltip.
- Live: 7 button variants on `/explore`, 5 on `/title/movie/348`, none using `.btn`.
- `DESIGN.md:444-452` documents the gap as follow-up work.

**Current state:** Every screen re-invents buttons, cards, and dialogs. State coverage (hover, focus, disabled, loading) varies per class. Changing the look of "a button" means editing dozens of selectors.

**Root cause:** The primitive was added without a migration plan or a lint rule, and the legacy global `button {}` rule makes the bare element "just work".

**Recommendation:** Follow the component consolidation plan below:
1. Change the global `button` rule to the neutral style, with `.btn-primary` opt-in. Do this per surface, behind visual diffs.
2. Add `IconButton`, `Chip`, `Badge`, `Card`, `Dialog` (wrapping `useFocusTrap`), `Sheet`, `Toast`, `Tabs`, and `Skeleton`.
3. Add a lint rule banning new `<button className="…-btn">` outside `components/`.

**Rationale:** This is the root cause behind VIS-008, VIS-009, and VIS-013, and behind the CSS growth. Incremental adoption keeps the product shippable. I rejected adopting Radix/shadcn wholesale: the brand styling would have to be re-authored anyway, and the variables already exist. Radix headless primitives *behind* our components are acceptable for Dialog and Popover if A11y prefers.

**User story:** As an engineer, I want one Button and one Dialog so that a visual change is a one-file edit.

**Acceptance criteria:**
- [ ] `Button` is used by ≥60% of buttons on Explore, Title detail, Chat, and Admin Overview
- [ ] The bare `button {}` element rule is neutral (no gold fill)
- [ ] The 11 modal families render through one `Dialog` primitive

**Success metric:** The count of `*-btn`/`*-button` CSS families drops from about 30 to ≤5; total CSS lines drop ≥10%.

**Validation:** `rg` counts in CI; Playwright screenshot diffs per migrated surface in both themes.

### VIS-010: Suppress the theme cross-fade on programmatic theme application

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Public, Consumer |
| Persona(s) | First-time visitor; all users on first load |
| Category | Motion & polish |
| Severity | Medium |
| Impact | 3 |
| Effort | S |
| Confidence | Likely |
| Priority score | 2.4 |
| Verdict | Fix |
| Dependencies | — |
| Labels | motion, theming, first-paint |

**Evidence:**
- `:root` declares the dark palette as a fallback (`01-tokens.css:39-73`).
- `html`, `body`, and `.app-root.workspace` all transition `color`/`background` over 300 ms (`01-tokens.css:139-147,171-183,360-369`).
- `applyUiTheme` runs again after the server profile loads (`App.tsx:317-318`, `UserMenu.tsx:129-132`, `lib/uiPrefs.ts:97`). When the server preference differs from the localStorage/system value used by the FOUC script (`index.html:12-46`), the page cross-fades.
- `map_login_signed-in-session_1440.png` shows the "Sign in" heading and "Need an invite?" at near-background color. The CSS for those (`05-chat-responsive.css:557-563`) inherits `--text` (16:1), so the faint state is transitional. This is platform-map pointer P-8.

**Current state:** On first load, headings can appear washed out for about 300 ms. Screenshots and screen recordings catch it, and so do users on slow devices.

**Root cause:** Theme transitions apply to every theme change, including the non-user-initiated one at boot.

**Recommendation:** Wrap programmatic theme changes in `document.documentElement.dataset.themeSwitching = "instant"` and add `html[data-theme-switching="instant"] *, html[data-theme-switching="instant"] *::before { transition: none !important; }`. Remove the attribute on the next `requestAnimationFrame`. Keep the 300 ms fade only for the user's own toggle click.

**Rationale:** The fade is a nice touch for a deliberate toggle, and noise everywhere else.

**User story:** As a first-time visitor, I want the sign-in page to appear crisp so that it looks trustworthy.

**Acceptance criteria:**
- [ ] On load with server theme ≠ local theme, `h1` computed color equals `--text` within one frame
- [ ] The user-initiated toggle still fades over 300 ms

**Success metric:** 0 captures with heading contrast below 4.5:1 in the Playwright first-paint check.

**Validation:** Playwright: set localStorage `lights_down` with a server `lights_up`, screenshot at 50 ms, and assert the h1 color.

### VIS-006: Tokenize elevation, layering, motion, and breakpoints

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Cross-cutting |
| Persona(s) | Engineers; all users (stacking bugs, inconsistent depth) |
| Category | Design-system foundations |
| Severity | Medium |
| Impact | 3 |
| Effort | M |
| Confidence | Confirmed |
| Priority score | 2.0 |
| Verdict | Fix |
| Dependencies | Token block; VIS-020 |
| Labels | tokens, elevation, z-index, motion, breakpoints |

**Evidence:** §12.1 counts: 53 distinct shadows in 62 declarations; 26 z-index values (1 to 1200; for example `.share-action-popover` uses `z-index: 1000` at `07-persona-editorial.css:448`, the top bar uses 50 at `01-tokens.css:388`); 34 durations; 16 breakpoints including 768/769 and 900/901 pairs; 2 JS `matchMedia` queries with their own values.

**Current state:** Depth looks different on each surface. Layering is a guess (the top bar comment at `01-tokens.css:384-387` documents an actual stacking bug fixed by hand). Responsive behavior changes at slightly different widths per partial.

**Root cause:** No token category exists for these dimensions.

**Recommendation:** Add the elevation (`--shadow-1…4`), `--z-*` (9 layers), `--dur-*`/`--ease-*`, and documented breakpoint constants from the token block. Run a codemod mapping table (Migration path, step 4). Because CSS variables cannot be used in media queries, adopt `postcss-custom-media` (Vite supports PostCSS natively) with `@custom-media --bp-tablet (max-width: 768px)`.

**Rationale:** Small scales make stacking predictable and depth coherent. It also matters for VIS-022 density.

**User story:** As an engineer, I want a named layer for popovers so that menus never hide under the top bar.

**Acceptance criteria:**
- [ ] ≤6 shadow values, ≤9 z-index values, ≤6 durations, ≤5 breakpoints in the CSS
- [ ] Off-by-one breakpoint pairs removed

**Success metric:** The audit counts in §12.1 meet these targets.

**Validation:** Re-run the audit; spot-check the drawer, popover, toast, and modal stacking on Chat and Explore.

### VIS-011: Make reduced motion global and complete

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Cross-cutting |
| Persona(s) | Vestibular-sensitive users; low-end device users |
| Category | Motion |
| Severity | Low |
| Impact | 2 |
| Effort | XS |
| Confidence | Confirmed |
| Priority score | 2.0 |
| Verdict | Fix |
| Dependencies | — |
| Labels | motion, a11y, quick-win |

**Evidence:**
- 22 keyframes across 11 files.
- 16 `prefers-reduced-motion` blocks across 12 files.
- 7 animated selectors are not covered: `.projectionist-brand-lamp.thinking` (`projectionist-lamp-pulse`), `.app-nav-drawer` (`app-nav-slide`), `.typing-dot` (`typing-bounce`), `.share-action-popover`, `.menu-action-flash`, `.dash-skeleton-bar` (`dash-shimmer`), and `.poster-rail-loader-spinner`.
- There is no global catch-all.

**Current state:** Looping pulses and bounces continue under reduced motion.

**Root cause:** Per-feature opt-out instead of a global default.

**Recommendation:** In `tokens.css`, add:

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

Keep spinners as a static icon with "Loading…" text. Delete the 16 scattered blocks once covered.

**Rationale:** One rule covers present and future animations.

**User story:** As a motion-sensitive user, I want no looping animation when I set reduced motion so that the app is comfortable.

**Acceptance criteria:**
- [ ] Under emulated `prefers-reduced-motion: reduce`, `document.getAnimations().length === 0` on Chat while the agent is thinking

**Success metric:** 0 running animations under reduced motion.

**Validation:** Emulate the media feature with CDP (`Emulation.setEmulatedMedia`) and count animations.

### VIS-014: Bring DESIGN.md back in sync with the code

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Cross-cutting |
| Persona(s) | Engineers and agents |
| Category | Documentation |
| Severity | Low |
| Impact | 2 |
| Effort | XS |
| Confidence | Confirmed |
| Priority score | 2.0 |
| Verdict | Fix |
| Dependencies | Token block |
| Labels | docs, design-system |

**Evidence:**
- `docs/DESIGN.md:420` says tokens are in `frontend/src/styles.css`; they are actually in `styles/01-tokens.css`.
- `DESIGN.md:52` says Lights Down is the "default", but the code defaults to `"system"` (`lib/uiPrefs.ts:32-35`, `index.html:27`).
- The nav description at `DESIGN.md:76` lists My Journey, Plot Lab, and `/watchlist`, which are now redirects (platform map §1.6).
- `DESIGN.md:58` says "no pill chrome", but there are 71 `999px` radii.

**Current state:** Agents and contributors follow the doc and produce drift.

**Root cause:** The doc is edited per feature, not per system change.

**Recommendation:** Replace §"UI design system" with the token table and the typography specimen from this document. Add a "Components" section listing the primitives and their variants. Fix the four statements above.

**Rationale:** It is cheap, and this repo relies heavily on agents reading docs.

**User story:** As a contributor, I want the design doc to match the code so that I build the right thing first time.

**Acceptance criteria:**
- [ ] The four mismatches are fixed
- [ ] The token table lives in DESIGN.md

**Success metric:** No doc/code mismatch found in the next review run.

**Validation:** Doc review against `tokens.css`.

### VIS-009: Unify chips and pills into one Chip primitive

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Consumer |
| Persona(s) | Returning consumer; phone user |
| Category | Components |
| Severity | Medium |
| Impact | 2 |
| Effort | M |
| Confidence | Confirmed |
| Priority score | 1.33 |
| Verdict | Fix |
| Dependencies | VIS-001 |
| Labels | components, chat, chips |

**Evidence:** `map_chat_owner_1440.png` above the fold shows starter pills (rounded, grey fill), idea prompts (rectangles, white, bordered), mood chips (small pills, outlined), and the persona selector (pill with dot). The audit finds 35 `*chip*` selectors and 4 `*pill*` (`composer-mood-chip`, `explore-motif-chip`, `explore-theme-chip`, `holdable-shelf-chip`, `live-chip`, `scheduled-task-pill`, `user-status-pill`, `library-privacy-pill`…). Radius sprawl: 41 values, with `999px` ×71, `8px`, `10px`, and `12px` literals beside 6/10/14 tokens.

**Current state:** Similar interactive tokens look different, so users can't learn what is tappable.

**Root cause:** Each feature styled its own chip.

**Recommendation:** Create `Chip` with variants `suggestion` (filled `--surface-2`, `--radius-pill`, 32px tall, 13px text), `filter` (outlined, toggles `aria-pressed`, selected = `--accent-soft` fill with `--accent-ink` text and a check icon), and `status` (non-interactive, `Badge`). On Chat, starter and idea prompts both become `suggestion`, and mood chips become `filter`.

**Rationale:** One affordance, one look. It reduces visual noise on the front door.

**User story:** As a member, I want suggestion buttons to look alike so that I know they are all tappable prompts.

**Acceptance criteria:**
- [ ] Chat, Explore, and Search chips render through `Chip`
- [ ] ≤3 chip styles product-wide

**Success metric:** `*chip*`/`*pill*` selector roots drop from 39 to ≤6.

**Validation:** Visual diff of Chat home in both themes.

### VIS-012: Use one icon system

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Cross-cutting |
| Persona(s) | All; screen-reader users (emoji announced by name) |
| Category | Iconography |
| Severity | Low |
| Impact | 2 |
| Effort | S |
| Confidence | Confirmed |
| Priority score | 1.0 |
| Verdict | Fix |
| Dependencies | `scripts/subset_material_symbols.py` |
| Labels | icons, polish |

**Evidence:** There are 41 `material-symbols-outlined` spans in TSX, 15 inline `<svg>`, and 39 Unicode/emoji glyphs (★ ×19, ✕ ×5, ✓ ×3, ❚ ×2, ☆ ×2, ☰, ✎, ♥, ✗, 👍, 👎, 🔔, 🔕). The hamburger is "☰" (live accessible name "☰" on the toggle) and the poster grip is "⋮" at 30×30px (live `/explore`, `/title`). The font subset is about 55 glyphs (`00-fonts.css:15-17`).

**Current state:** Glyph weight, baseline, and color vary by platform font. Emoji render in color and ignore theme tokens.

**Root cause:** Quick additions without adding a glyph to the subset.

**Recommendation:** Map the glyphs to Material Symbols:

| Glyph | Material Symbol |
|---|---|
| ★ / ☆ | `star` (FILL 1/0) |
| ✕ / ✗ | `close` |
| ✓ | `check` |
| ☰ | `menu` |
| ⋮ | `more_vert` |
| ✎ | `edit` |
| ♥ | `favorite` |
| 👍 / 👎 | `thumb_up` / `thumb_down` |
| 🔔 / 🔕 | `notifications` / `notifications_off` |

Regenerate the subset. Icon sizes: 16, 20, 24 only (`--icon-sm/md/lg`). Make the poster grip a 36px hit area with a 20px glyph.

**Rationale:** Consistency and theme compliance at small cost (about 12 glyphs added to the subset).

**User story:** As a member, I want icons that match each other so that the interface feels finished.

**Acceptance criteria:**
- [ ] 0 emoji/dingbat glyphs used as icons in TSX (copy text excepted)
- [ ] Inline SVG only for charts and the brand mark

**Success metric:** The glyph count drops from 39 to 0.

**Validation:** `rg` with a Unicode range in CI.

### VIS-007: Converge spacing on the 4px token scale

| Field | Value |
|---|---|
| Type | Weakness |
| Surface | Cross-cutting |
| Persona(s) | All (rhythm); engineers |
| Category | Layout & spacing |
| Severity | Medium |
| Impact | 2 |
| Effort | L |
| Confidence | Confirmed |
| Priority score | 0.8 |
| Verdict | Fix |
| Dependencies | VIS-020 (gate first) |
| Labels | spacing, tokens, codemod |

**Evidence:** §12.1: 215 distinct padding values (about 25% tokens), 106 margins, 63 gaps. Off-grid values in frequent use: `0.35rem` (5.25px) ×28, `0.15rem` ×16, `0.55rem` ×13, `0.45rem` ×9, `10px 12px` ×9.

**Current state:** Vertical rhythm differs per partial. Cards with the same role have different insets (`12px 14px`, `0.65rem 0.75rem`, `var(--space-3) var(--space-4)`).

**Root cause:** Spacing tokens arrived after most partials were written.

**Recommendation:** Map literals to the nearest token:

| Literal range | Token |
|---|---|
| 2px, 0.1–0.15rem | `--space-0-5` (2px, new) |
| 4–6px, 0.25–0.4rem | `--space-1` |
| 8–10px, 0.5–0.65rem | `--space-2` |
| 12–14px, 0.75–0.9rem | `--space-3` |
| 16–18px, 1rem | `--space-4` |
| 20px, 1.25rem | `--space-5` |
| 24px, 1.5rem | `--space-6` |
| 32px, 2rem | `--space-7` |
| 48px, 3rem | `--space-8` |
| 64px | `--space-9` (new) |

Gate new code first (VIS-020). Migrate one partial per PR, with screenshots.

**Rationale:** Lower priority than color and type, because it is mostly invisible per screen. It is worth doing alongside primitive migration, since the primitives carry their own spacing.

**User story:** As a member, I want the layout to feel calm and even so that the product feels high-quality.

**Acceptance criteria:**
- [ ] Distinct padding values ≤40 after migration
- [ ] 0 off-grid rem literals in new code (lint)

**Success metric:** Token share of spacing declarations goes from about 30% to ≥85%.

**Validation:** Audit script; screenshot diffs.

## 15. Opportunities

### VIS-020: Add a stylelint token gate to CI

| Field | Value |
|---|---|
| Type | Opportunity |
| Surface | Cross-cutting |
| Persona(s) | Engineers and agents |
| Category | Design-system governance |
| Severity | Medium |
| Impact | 4 |
| Effort | S |
| Confidence | Likely |
| Priority score | 3.2 |
| Verdict | Add |
| Dependencies | Token block; precedes VIS-002, 005, 006, 007 |
| Labels | lint, ci, tokens |

**Evidence:** No stylelint in `05274cf:frontend/package.json` (ESLint and Prettier only, per platform map §1.2). The token file comments show three rounds of manual contrast patching (`01-tokens.css:47,54,121`).

**Current state:** Nothing machine-checks CSS values.

**Root cause:** Lint investment went to JS/TSX only.

**Recommendation:** Add `stylelint` + `stylelint-declaration-strict-value` + `stylelint-value-no-unknown-custom-properties`:
- `scale-unlimited/declaration-strict-value`: `["/color$/", "fill", "stroke", "font-size", "z-index", "box-shadow", "border-radius", "transition-duration"]`, with `ignoreValues: ["inherit", "transparent", "currentColor", "none", "0", "auto"]`, applied to all files except `01-tokens.css`.
- Start in warning mode with a baseline file. Flip to error for touched lines after 2 weeks.

**Rationale:** The gate stops sprawl from growing while migration proceeds. Cheapest durable fix.

**User story:** As a maintainer, I want CI to reject raw colors so that Lights Up never regresses.

**Acceptance criteria:**
- [ ] `npm run lint:css` exists and runs in CI
- [ ] New literals fail CI

**Success metric:** Literal count is monotonically non-increasing release over release.

**Validation:** Add `color: #123456` in a PR and confirm CI fails.

### VIS-021: Add a design gallery route with two-theme screenshot tests

| Field | Value |
|---|---|
| Type | Opportunity |
| Surface | Cross-cutting |
| Persona(s) | Engineers; owner-maintainer |
| Category | Design-system tooling |
| Severity | Medium |
| Impact | 3 |
| Effort | M |
| Confidence | Likely |
| Priority score | 1.6 |
| Verdict | Add |
| Dependencies | VIS-001 |
| Labels | gallery, playwright, visual-regression |

**Evidence:** 23 Playwright specs exist (platform map §1.2). `ui-testing-architecture.mdc` demands adversarial UI proofs. No component gallery exists.

**Current state:** Primitives can only be seen inside real screens with real data.

**Root cause:** No component layer to showcase (VIS-001).

**Recommendation:** Add a dev-only route `/__design` (included only when `import.meta.env.DEV` or with `?design=1` for owners). It renders every primitive in every variant and state (default, hover via `data-state`, focus, disabled, loading, error, selected) in both themes side by side. Add `e2e/design-gallery.spec.ts` with `toHaveScreenshot()` per theme at 390 and 1440.

**Rationale:** The gallery makes the system visible and testable without Storybook's dependency weight.

**User story:** As an engineer, I want to see every button state in both themes so that I can catch regressions before QA.

**Acceptance criteria:**
- [ ] Gallery covers all primitives × states × 2 themes
- [ ] Screenshot spec runs in CI on the mocked server `:8799`

**Success metric:** Visual regressions caught pre-merge (track count).

**Validation:** Intentionally change `--radius-sm` and see the spec fail.

### VIS-022: Add a compact density mode for Admin

| Field | Value |
|---|---|
| Type | Opportunity |
| Surface | Owner, Admin |
| Persona(s) | Established owner at scale; platform admin |
| Category | Layout & density |
| Severity | Low |
| Impact | 2 |
| Effort | M |
| Confidence | Likely |
| Priority score | 0.53 |
| Verdict | Add |
| Dependencies | VIS-006, VIS-007 |
| Labels | admin, density |

**Evidence:** Admin uses consumer spacing (`map_admin-overview_owner_1440.png`, `map_admin-tasks_owner_1440.png`). There are 20 admin sections (platform map §1.6). SC-19.

**Current state:** Admin tables and lists show fewer rows than a scan-oriented tool should.

**Root cause:** One spacing scale for all surfaces.

**Recommendation:** Set `html[data-density="compact"]` automatically under `/admin/*`, overriding `--space-3: 8px; --space-4: 12px; --tap-min: 36px` (desktop pointer only, via `@media (pointer: fine)`), with table rows at 36px. Same brand, tighter rhythm.

**Rationale:** Admin should be deliberately more utilitarian. It uses the same token mechanism (VIS-018).

**User story:** As an owner, I want to see more tasks per screen so that my weekly pass is faster.

**Acceptance criteria:**
- [ ] Admin Tasks shows ≥30% more rows at 1440×900
- [ ] Touch devices keep 44px targets

**Success metric:** Rows visible above the fold on `/admin/tasks`.

**Validation:** Screenshot comparison at 1440 and iPad.

---

## Required deliverable 1 — Proposed design tokens

### Token table (with contrast)

| Token | Lights Down | Lights Up | Role | Contrast (worst surface) |
|---|---|---|---|---|
| `--bg` | `#0d0d0d` | `#f9f7f2` | Page | — |
| `--surface` | `#101218` | `#fbf9f4` | Panels | — |
| `--surface-2` | `#171a22` | `#f0eee9` | Inset, fills | — |
| `--surface-raised` (`--surface-3` alias) | `#1c2029` | `#ffffff` | Cards, popovers | — |
| `--text` | `#e6e2d6` | `#1b1c19` | Primary text | 12.59 / 14.76 |
| `--muted` | `#9a958a` | `#4d4635` | Secondary text | 5.47 / 8.07 |
| `--accent` | `#ffb800` | `#b8860b` | **Fill only** | non-text 9.40 / 2.81 (fill; never text) |
| `--accent-ink` | `#ffb800` | `#735c00` | Accent text, focus | 9.40 / 5.56 |
| `--accent-text` (`--on-accent`) | `#1a1208` | `#1a1208` | Text on accent fill | 10.68 / 5.69 |
| `--accent-soft` | gold 14% | gold 12% | Selected fill | text on it ≥14 |
| `--danger` | `#e8918a` | `#ba1a1a` | Error text/icon | 6.87 / 5.57 |
| `--success` | `#7dba98` | **`#276b4a`** (was `#2e7d57`) | Success | 7.26 / 5.51 |
| `--warning` **new** | `#f0a35e` | `#9a4a00` | Warning | 7.85 / 5.40 |
| `--info` **new** | `#8db7e0` | `#2c5d8a` | Info | 7.75 / 5.96 |
| `--star` **new** | `#ffb800` | `#8a6500` | Ratings (non-text) | 9.40 / 4.59 |
| `--border-subtle` | `#22262f` | `#e5e2da` | Dividers (decorative) | 1.08 / 1.12 |
| `--border` | `#2c313c` | `#d0c5af` | Card edges (decorative) | 1.25 / 1.47 |
| `--border-field` | `#636d82` | `#857a62` | Input/control edges | 3.14 / 3.65 |
| `--ink-on-media` | `#e6e2d6` | `#e6e2d6` | Text over posters/video | 16.2 on black |

### Ready-to-paste CSS (additions and changes to `frontend/src/styles/01-tokens.css`)

```css
:root {
  /* Type scale — ratio 1.2 on the 15px root (--base-font-size). Floor 12px. */
  --text-xs: 0.8rem;      /* 12px   caption, eyebrow */
  --text-sm: 0.875rem;    /* 13.1px small, meta, chip */
  --text-md: 0.9375rem;   /* 14.1px dense UI, table */
  --text-base: 1rem;      /* 15px   body */
  --text-lg: 1.2rem;      /* 18px   h4, lead */
  --text-xl: 1.44rem;     /* 21.6px h3 */
  --text-2xl: 1.728rem;   /* 25.9px h2 */
  --text-3xl: 2.074rem;   /* 31.1px h1 */
  --text-display: clamp(2.5rem, 7vw, 5.25rem); /* title hero */
  --weight-regular: 400;
  --weight-medium: 500;
  --weight-semibold: 600;
  --weight-bold: 700;
  --leading-none: 1;
  --leading-tight: 1.25;
  --leading-snug: 1.4;
  --leading-body: 1.55;
  --tracking-tight: -0.02em;
  --tracking-normal: 0;
  --tracking-label: 0.06em;

  /* Spacing — 4px grid */
  --space-0-5: 2px;
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

  /* Elevation (dark-theme values; Lights Up overrides below) */
  --shadow-1: 0 1px 2px rgb(0 0 0 / 0.25);
  --shadow-2: 0 8px 24px rgb(0 0 0 / 0.28);
  --shadow-3: 0 12px 36px rgb(0 0 0 / 0.40);
  --shadow-4: 0 24px 60px rgb(0 0 0 / 0.45);
  --shadow-focus-ring: 0 0 0 3px color-mix(in srgb, var(--accent-ink) 30%, transparent);

  /* Layers */
  --z-base: 0;
  --z-raised: 1;
  --z-sticky: 20;
  --z-topbar: 50;
  --z-drawer: 80;
  --z-popover: 100;
  --z-modal: 120;
  --z-toast: 130;
  --z-max: 1000;

  /* Motion */
  --dur-instant: 80ms;
  --dur-fast: 150ms;
  --dur-base: 220ms;
  --dur-slow: 300ms;
  --dur-slower: 700ms;
  --ease-standard: cubic-bezier(0.2, 0, 0, 1);
  --ease-out: cubic-bezier(0, 0, 0.2, 1);
  --ease-in-out: cubic-bezier(0.4, 0, 0.2, 1);

  /* Icons */
  --icon-sm: 16px;
  --icon-md: 20px;
  --icon-lg: 24px;
}

html[data-theme="lights-down"] {
  --warning: #f0a35e;
  --warning-ink: var(--warning);
  --info: #8db7e0;
  --info-ink: var(--info);
  --star: #ffb800;
  --surface-3: var(--surface-raised);
}

html[data-theme="lights-up"] {
  --success: #276b4a;
  --warning: #9a4a00;
  --warning-ink: var(--warning);
  --info: #2c5d8a;
  --info-ink: var(--info);
  --star: #8a6500;
  --surface-3: var(--surface-raised);
  --shadow-1: 0 1px 2px color-mix(in srgb, var(--text) 10%, transparent);
  --shadow-2: 0 8px 24px color-mix(in srgb, var(--text) 12%, transparent);
  --shadow-3: 0 12px 36px color-mix(in srgb, var(--text) 16%, transparent);
  --shadow-4: 0 24px 60px color-mix(in srgb, var(--text) 20%, transparent);
}

html {
  --danger-soft: color-mix(in srgb, var(--danger) 12%, transparent);
  --success-soft: color-mix(in srgb, var(--success) 12%, transparent);
  --warning-soft: color-mix(in srgb, var(--warning) 12%, transparent);
  --info-soft: color-mix(in srgb, var(--info) 12%, transparent);
}

/* Breakpoints: CSS variables can't be used in @media, so use postcss-custom-media. */
@custom-media --bp-phone (max-width: 560px);
@custom-media --bp-tablet (max-width: 768px);
@custom-media --bp-laptop (max-width: 1024px);
@custom-media --bp-desktop (min-width: 1280px);
@custom-media --bp-wide (min-width: 1440px);

html[data-theme-switching="instant"] *,
html[data-theme-switching="instant"] *::before,
html[data-theme-switching="instant"] *::after {
  transition: none !important;
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

### Mapping existing values to tokens (codemod input)

| Dimension | Current values | Target |
|---|---|---|
| z-index | 1, 2, 3, 4, 5, 6, 8 | `--z-raised` (1), or local stacking contexts |
| | 20, 30, 35 | `--z-sticky` |
| | 40, 41, 45, 50 | `--z-topbar` |
| | 60, 70, 80, 85, 90 | `--z-drawer` |
| | 100 | `--z-popover` |
| | 120 | `--z-modal` |
| | 130 | `--z-toast` |
| | 1000, 1200 | `--z-max` (portal menus) or `--z-popover` |
| Durations | 80–120 ms | `--dur-instant` |
| | 140–180 ms | `--dur-fast` |
| | 200–280 ms | `--dur-base` |
| | 300–450 ms | `--dur-slow` |
| | 550 ms–1.6 s | `--dur-slower` |
| | 28 s drift | stays a literal (ambient) |
| Breakpoints | 390, 560 | `--bp-phone` |
| | 640, 720, 760, 768, 769 | `--bp-tablet` (verify the 640/720 cases visually) |
| | 840, 900, 901, 926, 960, 990, 1024 | `--bp-laptop` |
| | 1100, 1200, 1280 | `--bp-desktop` |
| | 1440 | `--bp-wide` |
| Shadows | 53 values | nearest of `--shadow-1…4` by blur radius (≤4px → 1; ≤24px → 2; ≤40px → 3; >40px → 4) |
| Radius | 2/4px | `--radius-xs` |
| | 6px, 0.35rem | `--radius-sm` |
| | 8/10/12px, 0.5–0.75rem, all `--radius-md` fallbacks | `--radius-md` |
| | 14/16px | `--radius-lg` |
| | 24px | `--radius-xl` |
| | 999px | `--radius-pill` (chips only) |

## Required deliverable 2 — Typography specimen

Root = `--base-font-size` (15px at "medium"; the per-user small, medium, and large settings scale all of it). Pixel values below are at medium.

| Level | Family | Size token (px) | Weight | Line height | Letter spacing | Usage |
|---|---|---|---|---|---|---|
| Display | Fraunces Variable | `--text-display` (37.5–78.75) | 600 | 0.95 | −0.03em | Title-detail hero name, Year in Review |
| H1 | Fraunces Variable | `--text-3xl` (31.1) | 600 | 1.15 | −0.02em | Page title (Overview, Live, Settings) |
| H2 | Fraunces Variable | `--text-2xl` (25.9) | 600 | 1.2 | −0.015em | Section title ("For you", "Household health") |
| H3 | Fraunces Variable | `--text-xl` (21.6) | 600 | 1.25 | −0.01em | Card group, modal title |
| H4 | DM Sans Variable | `--text-lg` (18) | 600 | 1.3 | 0 | Sub-section, list group |
| H5 | DM Sans Variable | `--text-base` (15) | 600 | 1.4 | 0 | Card title, table group |
| H6 / Eyebrow | DM Sans Variable | `--text-xs` (12) | 600 | 1.3 | `--tracking-label` 0.06em, uppercase | "SYNOPSIS", "AT A GLANCE" (max one per section) |
| Body | DM Sans Variable | `--text-base` (15) | 400 | 1.55 | 0 | Synopsis, chat replies, help. Measure 60–70ch (`max-width: 68ch`) |
| Body small | DM Sans Variable | `--text-sm` (13.1) | 400 | 1.45 | 0 | Rail explanations, meta, helper text |
| Caption | DM Sans Variable | `--text-xs` (12) | 500 | 1.35 | 0.01em | Timestamps, counts, poster subtitle |
| Label (controls) | DM Sans Variable | `--text-sm` (13.1) | 600 | 1.3 | 0 (sentence case) | Buttons, chips, tabs, field labels |
| Data / numerals | DM Sans Variable + `font-variant-numeric: tabular-nums` | `--text-md` (14.1) | 500 | 1.35 | 0 | Tables, Live guide times, stats tiles |
| Code | `--font-mono` (single stack) | `--text-sm` (13.1) | 400 | 1.5 | 0 | Logs, config snippets, keys |

Rules:
- Fraunces never below 18px.
- Uppercase only on Eyebrow.
- One monospace stack (delete the 6 literal stacks).
- Weights 400/500/600/700 only.
- Body measure ≤70ch. Title-detail synopsis today runs about 95ch at 1440 (`map_title-detail_owner_1440.png`, left column); cap it at `68ch`.

## Required deliverable 3 — Component consolidation plan

| Component | Current variants (evidence) | Target | States required |
|---|---|---|---|
| **Button** | Global `button {}` gold default (50 unclassed), `button.ghost`, `.btn-link`, `.login-primary/secondary`, `.explore-search-submit`, `.dash-purge-btn(--muted/--danger)`, `.confirm-all-button`, title-detail pill actions, about 30 families in total; `Button.tsx` unused | `Button` variant `primary \| neutral \| secondary \| ghost \| danger` × size `sm 34 \| md 44 \| lg 52`; `loading` prop | default, hover, focus-visible, active, disabled, loading (spinner + `aria-busy`) |
| **IconButton** | `app-topbar-icon`, `live-chrome-icon-btn`, `scheduled-task-icon-btn`, `poster-action-grip` (30px), `viewport-expand-btn`, `thread-delete-btn` | `IconButton` size `sm 32 \| md 40 \| lg 44`, required `label`, variants `ghost \| overlay` (on media) | + pressed (`aria-pressed`) |
| **Field / Select / Textarea** | `.login-field` (good), settings inputs, composer, library search, Explore search (`radius-lg`) | `Field` (label, hint, error) wrapping `Input`, `Select`, `Textarea`; 44px; `--border-field`; `--radius-sm` | default, hover, focus, disabled, error, read-only |
| **Chip** | 35 `*chip*` + 4 `*pill*` selectors; 3 styles on Chat home | `Chip` variant `suggestion \| filter`; `Badge` for status | default, hover, focus, selected, disabled |
| **Badge** | `badge`, `stat-chip`, `certified-badge-*`, `title-chip(-accent)`, `admin-rail-badge`, `app-nav-badge`, `primary-bottom-nav-badge`, rating badges | `Badge` tone `neutral \| accent \| success \| warning \| danger \| info`; `CountBadge` | — |
| **Card** | 36 `*-card` roots | `Card` (surface, `--radius-lg`, `--shadow-1`, padding `--space-4`) + `MediaCard` (poster 2:3, title, meta, reason) + `StatCard` | default, hover (raised), focus-within, selected, loading (skeleton) |
| **Dialog** | 11 modal/drawer/sheet roots, 21 `role="dialog"` sites | `Dialog` (centered, sizes `sm 400 \| md 560 \| lg 720`) + `Sheet` (side or bottom; drawer, footnote, title drawer); both use `useFocusTrap` | open/close motion `--dur-base`, reduced-motion instant |
| **Toast** | `UndoToast` only | `Toast` tone + action, `--z-toast`, 6 s default, pause on hover/focus | — |
| **Tabs** | Library tabs, Health tabs, Live Guide/Watch segmented control | `Tabs` (underline) + `SegmentedControl` (pill group) | selected, focus, disabled |
| **InlineAlert** | `-error`, `-success` | + `-warning`, `-info`, each with an icon | dismissible |
| **Skeleton / Spinner** | `dash-skeleton`, `live-guide-skeleton`, `poster-rail-loader-spinner`, `live-player-spinner`; many "Loading titles…" text states | `Skeleton` (rect/text/poster), `Spinner` (one; static under reduced motion) | — |
| **Tooltip** | none (relies on `title=`) | `Tooltip` for icon buttons (aria-describedby) | hover, focus |
| **Table** | `dash-table`, `investigate-review-table`, scheduled-tasks table | `DataTable` styles: 40px rows (36 compact), tabular numbers, sticky header `--z-sticky` | row hover, selected, sort |

Target: about 14 primitives in `frontend/src/components/ui/`, each with a colocated CSS file that uses only tokens.

## Required deliverable 4 — Before/after for the 5 most important screens

### Screen 1: Chat home (`/chat`) — `map_chat_owner_1440.png`, `map_chat_owner_390.png`

Before:
```
┌ ≡ Projectionist ⊕ ───────────────── 🔍 💬 🧭 🔔12 ⛨ ⚙ ☀ (QA qa-owner) ┐
│CONVERSATIONS  [+][«] │ Good to meet you — I'm Curator. Which        │
│[Search threads…    ] │ thread of your library shall we pull on?     │
│▌New conversation  ✕  │ Try a starter, or just ask — I'm here.       │
│ New conversation  ✕  │ (Resume)(Tonight under 2h)(Continue)(Like…)  │ ← pills, grey
│ New conversation  ✕  │ [Trace the lineage…] [Unwatched New Hollywd] │ ← rectangles
│ … ×9 cards           │ [Compare two films I rated highly]           │
│ plexomat · 4595 …    │ More from home                               │
│ [ Watchlist ]        │                                              │
│                      │ ┌ ⧉ General Exploration ─────────────────┐   │
│                      │ │ Compare two directors…                 │   │
│                      │ │ (● The Professor ⌄)  (Cozy)(Thrill)…(⚄)(↑)│ ← 3rd chip style
└──────────────────────┴──┴────────────────────────────────────────┴───┘
```
After:
```
┌ ≡ Projectionist ─────────────── Search Chat Explore Inbox•12 ⚙ ☀ (QA) ┐
│ Conversations   [+ New] │                                            │
│ [Search threads     ]   │  Which thread of your library              │  H1 Fraunces 31px
│ TODAY                   │  shall we pull on?                         │
│  Untitled · 75d         │  Curator · The Professor ⌄                 │  caption 12px muted
│ EARLIER                 │                                            │
│  What should I watch…   │  ( Tonight under 2h ) ( Continue watching ) │  Chip suggestion ×4
│  Recommend R-rated…     │  ( Something like… ) ( Trace a director )  │  (merged starters+ideas)
│                         │                                            │
│                         │  More from home ▸                          │
│ ─────────────────────── │ ┌──────────────────────────────────────┐   │
│ 4,595 films · 797 shows │ │ Ask for anything…                     │   │  Field 16px
│ [Watchlist]  (neutral)  │ │ [Cozy][Thrill][Laugh][Think][Escape]   (↑)│  Chip filter + Button primary
└─────────────────────────┴─┴──────────────────────────────────────┴───┘
```
Changes:
- Merge starter and idea prompts into one `Chip suggestion` row (max 4; VIS-009).
- Mood chips become `Chip filter` with `aria-pressed`.
- Thread list as rows (not cards), grouped by date, with a 13px title and 12px meta.
- The send button is the one primary.
- Persona appears as a caption under the H1, removing the "I'm Curator" vs "The Professor" double naming in one glance.
- The "General Exploration" monospace tag becomes a `Badge`.

### Screen 2: Explore hub (`/explore`) — `map_explore_owner_1440.png`, `map_explore_owner_390.png`

Before:
```
┌ top bar ───────────────────────────────────────────────────────────────┐
│ [🔍 Search your library by title or plot…              ] [ Search ]    │ ← #f9f7f2 on gold 3.04:1
│ [Movies     ][TV          ][Related titles][Tags        ]              │
│ For you                                          Chat about these      │
│ ▢▢▢▢▢▢▢▢  posters 2:3, ⋮ grip 30px                                    │
│ Title (Year) — 12px                                                    │
│ You watched X; Y — both stories turn on… (12px grey, 4 lines)          │
└────────────────────────────────────────────────────────────────────────┘
```
After:
```
┌ top bar ───────────────────────────────────────────────────────────────┐
│ [🔍 Search your library by title or plot…              ][ Search ]     │ Button primary lg, --accent-text 5.69:1
│ ( Movies ) ( TV ) ( Related titles ) ( Tags )                          │ SegmentedControl / Chip filter, 1 row
│                                                                        │
│ For you                                    Chat about these →          │ H2 Fraunces 26px; ghost link
│ ┌────┐┌────┐┌────┐┌────┐┌────┐┌────┐                                   │ MediaCard, gap --space-4
│ │2:3 ││    ││    ││    ││    ││    │  ⋮ IconButton 36px overlay        │
│ └────┘└────┘└────┘└────┘└────┘└────┘                                   │
│ Title            body-sm 13px semibold, 2-line clamp                    │
│ 2015 · Film      caption 12px muted                                     │
│ "Both turn on a spin-off" ← reason, body-sm, 2-line clamp, ⓘ Why       │
└────────────────────────────────────────────────────────────────────────┘
```
Changes:
- The Search CTA uses fill + `--accent-text` (VIS-003) and `--radius-sm` to match fields.
- Entry tiles shrink to one chip row (they duplicate the nav and the search).
- Rail reason text is clamped to 2 lines with a "Why" disclosure.
- Year moves into meta.
- 12px floor throughout (VIS-004).

### Screen 3: Title detail (`/title/movie/348`) — `map_title-detail_owner_1440.png`, `map_title-detail_owner_390.png`

Before:
```
┌ [≡] ← Back to chat                                            MOVIE ┐  no app top bar
│                    full-bleed backdrop                              │
│ [1979 MAY 25][117 MINS][IN YOUR LIBRARY ✓][TMDB ★ 8.2]              │  11.25px uppercase chips
│ Alien  [R]                                                          │  Fraunces 78px
│ (●PLAY)(TRAILER)(RATE)(WATCHED)(CHAT)(TOGETHER)(MORE)               │  7 uppercase pills
│ SYNOPSIS                                      [RELEASED][DECADE]    │
│ During its return to the earth… (~95ch line)  [COLLECTION][RATING]  │
└─────────────────────────────────────────────────────────────────────┘
```
After:
```
┌ ≡ Projectionist ──── Search Chat Explore Inbox ⚙ ☀ (QA) ┐  .app-topbar--over-media (scrim)
│ ← Back to chat                                           │
│                    full-bleed backdrop                   │
│ Alien                                                    │  --text-display
│ 1979 · 1h 57m · R · ★ 8.2 TMDB · In your library ✓       │  caption 13px, tabular-nums, one line
│ [▶ Play]  [Trailer] [Mark watched] [Watch together] [⋯]  │  1 primary lg + 3 secondary md + IconButton
│                                                          │  (Rate, Chat → ⋯ menu)
│ Synopsis                                  ┌ Details ─────┐│  H2 26px, sentence case
│ During its return to the earth,           │ Released …   ││  body 15px, max 68ch
│ commercial spaceship Nostromo…            │ Collection … ││  Card, dl grid
└───────────────────────────────────────────┴──────────────┘┘
```
Changes:
- The AppShell is back in an overlay variant (VIS-008).
- Metadata chips collapse to one caption line.
- Actions go from 7 to 4 + overflow.
- Sentence case throughout.
- The synopsis measure is capped.
- Details become one `Card` with a `dl`, instead of four mini-cards.

### Screen 4: Admin Overview (`/admin/overview`) — `map_admin-overview_owner_1440.png`, `map_admin-overview_owner_390.png`

Before:
```
│ SETUP │ Overview                                                     │
│ …     │ 5 things need attention                                      │
│       │ ┌ Radarr is marked connected but has no saved key   [Open] ┐ │ gold
│       │ ┌ Sonarr is marked connected…                       [Open] ┐ │ gold
│       │ ┌ Pin a dedicated secrets key                       [Open] ┐ │ gold
│       │ ┌ Download a household backup                       [Open] ┐ │ gold
│       │ ┌ This week's Monday pass isn't done                [Open] ┐ │ gold
│       │ AT A GLANCE  Household health ?            [Setup checklist] │ gold
│       │ [Connected][5,392][88%][0%][Warming]                          │
```
After:
```
│ SETUP │ Overview                                       Setup checklist ▸ │ ghost
│ …     │ Needs attention · 5                                              │ H2
│       │ ⚠ Radarr key missing — badge says connected   [Test connection]› │ warning icon, secondary sm
│       │ ⚠ Sonarr key missing — badge says connected   [Test connection]› │
│       │ ⓘ Pin a dedicated secrets key                 [How to pin]     › │ info icon
│       │ ⓘ Download a household backup                 [Download]       › │
│       │ ○ Monday pass · 3 of 4 left                   [Start pass]     › │
│       │ Household health                                                 │
│       │ [● Connected][5,392 indexed][88% unwatched][0% rated][◐ Warming] │ StatCard, status via Badge tone
```
Changes:
- No gold buttons in the list (VIS-013).
- Row severity is shown with `--warning`/`--info` icons and colors (VIS-015).
- Verb labels replace "Open".
- Compact density on `/admin/*` (VIS-022).
- "Warming" uses the `warning` tone instead of brand gold.

### Screen 5: Live guide (`/live`) — `map_live-guide_owner_1440.png`, `map_live-guide_owner_390.png`

Before:
```
│ Live                                         [Guide|Watch] ▦ ⧉ ▶  │
│ Projectionist LIVE │10:30 AM│11:00 AM│11:30 AM│12:00 PM│…           │
│ 100 Comedian │8│Rory Scovel Tries Stand-Up…│1│Pete Davidson…│1│Jeff…│ ← short cells stack time
│              │-│10:45–11:51 AM TV-MA       │2│              │0│     │   text vertically
│ 103 Youth Safe │ (empty, no message)                                │
```
After:
```
│ Live                                      ( Guide | Watch )  ▦ ⧉ ▶  │ SegmentedControl
│ Channel        │10:30   │11:00   │11:30   │12:00   │ … tabular-nums  │ sticky header --z-sticky
│ 100 Comedian   │▌│Rory Scovel Tries Stand-Up…  │·│Pete Davidson…     │ cells <8min: no text, ▌ sliver + Tooltip
│                │ │10:45–11:51 · TV-MA          │ │12:06–12:55       │ caption 12px
│ 103 Youth Safe │ Nothing scheduled today — Open Live Studio ›         │ empty-state row (owner) / "Off air" (member)
│ 104 Weather    │ Local forecast · all day                             │
```
Changes:
- Cells narrower than about 56px render no text: a 4px `--accent-soft` sliver with a `Tooltip` instead of letter-stacked time.
- The time header uses `tabular-nums` and a sticky position.
- Empty channels get a designed row.
- The Guide/Watch toggle uses `SegmentedControl`.
- The "Now" line uses `--accent-ink` at 2px (it is already gold, so keep it).

## Required deliverable 5 — Migration path (no big bang)

1. **Step 0 — Freeze sprawl (week 1, S).** Land stylelint in warning mode with a baseline (VIS-020). Add the token contrast unit test (VIS-016). No visual change.
2. **Step 1 — Tokens as aliases (week 1, S).** Paste the token block: new tokens, plus `--radius-md`, `--surface-3`, and status tokens. Rename the phantom variables (VIS-005). Visual change is limited to the Lights Up success tone and the previously broken `--radius-md` call sites.
3. **Step 2 — Contrast quick wins (week 1–2, XS–S).**
   - VIS-003 (Search CTA plus 11 accent-as-text rules).
   - VIS-002 literal replacements.
   - VIS-013 single primary.
   - VIS-010 instant theme switching.
   - VIS-011 global reduced motion.
   Each is its own PR, with before/after screenshots on QA `:8792` in both themes.
4. **Step 3 — Type floor (week 3, S).** Change `--text-xs`/`--text-sm` values only. Run screenshot diffs at 390 and 1440 on the five key screens. Fix overflows found. Then the literal font-size codemod per partial (VIS-004).
5. **Step 4 — Primitives by surface (weeks 3–8, L).**
   - Build `components/ui/` (Button, IconButton, Chip, Badge, Card, Dialog/Sheet, Toast, Tabs, Skeleton, Tooltip, Field).
   - Neutralize the global `button {}` rule **per surface** with a scoping class: add `.ds-surface` to the Explore layout first, where `.ds-surface button:not([class])` gets the neutral style.
   - Migrate in order: Explore → Title detail (with VIS-008) → Chat (VIS-009) → Admin Overview → Settings → Live → remaining Admin.
   - Remove the global gold default once all surfaces carry `.ds-surface`.
6. **Step 5 — Codemods (weeks 6–10, M).** z-index, shadows, durations, and breakpoints using the mapping table (VIS-006), then spacing (VIS-007), one CSS partial per PR.
7. **Step 6 — Gallery and density (weeks 8–12, M).** `/__design` with screenshot tests (VIS-021); admin compact density (VIS-022). Flip stylelint to error.
8. **Step 7 — Docs.** Update DESIGN.md at Step 1 and Step 4 (VIS-014).

Every step is independently shippable and reversible. No step requires a redesign freeze.

## 16. Remediation plan

**Now (0–2 weeks)**

| ID | Title | Effort | Owner role | Dependencies |
|---|---|---|---|---|
| VIS-003 | Stop using the gold fill as text in Lights Up | XS | Frontend engineer | — |
| VIS-013 | One primary per action group on Admin Overview | XS | Frontend engineer | — |
| VIS-011 | Global reduced motion | XS | Frontend engineer | — |
| VIS-014 | Sync DESIGN.md | XS | Design director | — |
| VIS-020 | Stylelint token gate (warning mode) | S | Frontend lead | — |
| VIS-005 | Define or remove phantom variables | S | Frontend engineer | Token block |
| VIS-015 | Complete status palette | S | Design + frontend | — |
| VIS-010 | Instant programmatic theme switch | S | Frontend engineer | — |

**Next (2–6 weeks)**

| ID | Title | Effort | Owner role | Dependencies |
|---|---|---|---|---|
| VIS-002 | Replace literals with semantic tokens | M | Frontend engineer | VIS-015, VIS-020 |
| VIS-004 | Type floor and modular scale | M | Design + frontend | Token block |
| VIS-008 | AppShell on title detail; 4-action hero | S | Frontend engineer | VIS-001 (Button) |
| VIS-001 | Component layer and Button adoption (phase 1: Explore, Title, Chat) | L | Frontend lead | Token block |
| VIS-009 | Chip primitive | M | Frontend engineer | VIS-001 |

**Later (6+ weeks)**

| ID | Title | Effort | Owner role | Dependencies |
|---|---|---|---|---|
| VIS-006 | Elevation, z, motion, and breakpoint codemods | M | Frontend engineer | VIS-020 |
| VIS-012 | One icon system | S | Frontend engineer | Subset script |
| VIS-021 | Design gallery and screenshot tests | M | Frontend + QA | VIS-001 |
| VIS-007 | Spacing convergence | L | Frontend engineer | VIS-020 |
| VIS-022 | Admin compact density | M | Design + frontend | VIS-006, VIS-007 |

**Sequencing rationale:**
- The gate and the tokens come first, so that nothing new adds debt.
- Contrast fixes are next: they are user-visible, cheap, and High severity.
- The type change comes before primitives, so primitives are built on the final scale.
- Primitives go surface by surface, so each PR is visually verifiable on QA `:8792`.
- Codemods come last, because they are invisible and benefit from the gate.

## 17. Quick wins (high impact, XS–S)

1. **VIS-003:** two lines in `10-explore-delight.css:311-312`, plus 11 `var(--accent)` → `var(--accent-ink)` swaps. Fixes the primary CTA contrast (3.04 → 5.69).
2. **VIS-013:** Admin Overview "Open" ×5 → secondary verbs. Restores hierarchy.
3. **VIS-011:** one global reduced-motion rule.
4. **VIS-010:** a `data-theme-switching` guard. Removes washed-out first paint.
5. **VIS-005:** define `--radius-md: 10px` and `--warning`. Fixes silent fallbacks in 14 + 4 places.
6. **VIS-004 (part 1):** change only `--text-xs` to `0.8rem` and `--text-sm` to `0.875rem`. Lifts 362 declarations above the 12px floor.

## 18. Open questions needing product/business input

1. **Default theme.** The code defaults to "system", while DESIGN.md says Lights Down. Which should the brand lead with on first run? This affects which theme gets primary QA.
2. **Pills.** DESIGN.md says "no pill chrome", but the product uses 71 pills. Should pills be allowed for chips and filters only (my recommendation), or banned?
3. **Admin density.** Is a compact Admin (36px rows on desktop) acceptable to the owner persona, or does the owner primarily administer from an iPad (keep 44px)?
4. **Persona naming in chrome.** "Curator" vs "The Professor" on the Chat H1. Should the H1 name the persona at all? This is a Content/Product call; it affects the Chat wireframe.
5. **Component dependency.** Are headless primitives such as Radix Dialog/Popover acceptable dependencies (license MIT, ~10–20 kB gzip), or must every primitive stay hand-rolled?
6. **Type size default.** If the 12px floor still feels small to the household, should "medium" move to a 16px root (a bigger, riskier layout change)?

---

## Phase 6 department self-check

- [x] The document opens with Part A, and every conclusion cites finding IDs.
- [x] Every Critical/High finding appears in the narrative. The four High weaknesses are VIS-001, 002, 003, and 004; the two High strengths are VIS-016 and 017. All are cited in Bottom line and Key conclusions. There are no Critical findings.
- [x] Completed the "Foundations challenged" table, the "If we built it today" view, and the "Stop doing" list.
- [x] All four surfaces are covered (Public, Consumer, Owner, Admin/Ops), each with a grade.
- [x] Strengths are documented in full finding format with "Protect this" notes (VIS-016–019).
- [x] Recommendations carry exact specs: hex values, ratios, px/rem, tokens, wireframes, and a codemod mapping.
- [x] Every finding has evidence, root cause, rationale, and acceptance criteria.
- [x] IDs are unique (VIS-001 … VIS-022).
- [x] No application code was modified. I wrote only this file and added no screenshots (I reused `map_*`).
- [ ] Status file: not updated by this department, per the coordinator's hard rule (the coordinator owns `_status.md`).

**Limits:** I did not verify Lights Down live (code ratios only). I did not walk member or youth sessions. The VIS-010 root cause is *Likely* (inferred from code plus screenshot), not reproduced frame by frame.
