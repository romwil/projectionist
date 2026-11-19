# Experience convergence: one design language across web, phone, tablet, and TV

Dropped 2026-11-18 after a pass over the screenshots in `docs/reviews/2026-10-28*/screenshots/` and `docs/reviews/2026-11-01/screenshots/` (builds 1.37.x–1.38.0; some items may be fixed in 1.40.x, so **verify on the current build**), the 2026-11-01 Visual and UX reviews, and the 2026-11-18 rescore.

**Goal:** a world-class, singular Projectionist experience. The web app and the native clients feel like one product because they share one language, one navigation model, one voice, and one source for design values.

**Proposed prefix:** `EXP` (experience convergence). Per `docs/claude.roadmap.md`, a new prefix needs the person’s approval.

---

## What the screenshots show

**Protect.** Title detail is the best screen in the product: full-bleed art, the Fraunces title, a single gold **Play**. It is the template the rest should grow toward. Lobby Theater shows the same instinct: one poster and nothing else.

**The gap: the web app is control-first; the vision is art-first.**

1. **Explore opens with tools, not cinema.** A search bar and four utility tiles (Movies, TV, Related titles, Tags) sit above For you. Every For you poster then carries a paragraph of *why*, all visible at once (`map_explore_owner_1440.png`).
2. **The *why* copy reads like debug output** on the most important rail: “both stories turn on a took place”, “brandon Christensen worked on both”, “qa-owner, You watched…” (`map_explore_owner_1440.png`, `ux_owner_inbox_1440.png`). PRD-001 shipped a quality gate; verify it on 1.40.1.
3. **System vocabulary leaks to members and Youth:** “No named link to something you finished — not a cosine guess… let Scheduled Tasks catch up” (Youth Explore, `ux_youth_explore_1440.png`); “Good to meet you — I'm Curator” (`map_chat_owner_390.png`, violates the glossary in `docs/DOCS_STYLE.md`); “Resume New conversation”; “Expand 1 titles in turnstyle view”; a monospace “General Exploration” label; “Agent activity”; “your CuratorX household” in Inbox (`map_chat-reply-success_owner_1440.png`, `ux_owner_inbox_1440.png`).
4. **Art often renders empty:** grey placeholders on the chat title card, the whole Search grid, For you at 390, and Youth Continue Watching (`map_search-results_owner_1440.png`, `map_explore_owner_390.png`, `ux_youth_explore_1440.png`). Whether capture timing or real, an art-first design needs art that never looks broken: dominant-color placeholders and a server-side art cache (Lobby already has `theater/poster_cache.py`).
5. **Navigation disagrees with itself.** Desktop has seven unlabeled icons plus a hamburger. At 390 the bottom bar is Search · Chat · Explore · Inbox · Settings, with Live missing and Settings taking a primary slot. Search for owners carries Delete / Export CSV / Select page beside browsing (PRD-014).
6. **The Live guide breaks on short slots.** Filler slots wrap their time one character per line (“8 – 1 0 :”). An empty “Youth Safe” row has no sentence. Half the viewport is blank (`map_live-guide_owner_1440.png`).
7. **Inbox looks like an admin queue** (checkboxes, Read / Dismiss per row) where members should feel they are receiving letters (`ux_owner_inbox_1440.png`).
8. **Chat is busy around a thin core.** The thread list fills with “New conversation · 75d ago” duplicates and raw markdown in previews (“[**What We Do…”). The composer stacks four suggestion chips, five mood chips, a persona picker, and a dice button (`map_chat-reply-success_owner_1440.png`).

---

## Proposed direction

### One language, three densities

| Density | Where | Feel |
|---------|-------|------|
| **Cinema** | TV clients, Watch, Live, Title, the top of Explore | Art fills the screen; one sentence; one gold action |
| **Companion** | Phone, tablet, web Explore / Chat / Inbox / Search | Touch-first, art-led cards; the *why* on focus / hover / tap, not as a wall of text |
| **Workbench** | Admin | Dense and utilitarian; same type and amber (1.40.0 Admin is the foothold, VIS-022) |

### Proposed items

| ID (proposed) | Item | Done when |
|---------------|------|-----------|
| EXP-001 | **Design tokens as source of truth**: `design/tokens.json` (color with semantic aliases, type scale, spacing, radius, elevation, motion, breakpoints) generates `frontend/src/styles/01-tokens.css` and a Swift token file for native clients. Absorbs VIS-005/006/007/010/011/012/015 and gates with VIS-020 stylelint | One edit to `tokens.json` changes web and native; CI fails on hard-coded colors outside tokens |
| EXP-002 | **One navigation model**: Explore · Live · Chat · Search as primary peers on every client; Inbox behind the bell; Settings, Admin, theme, Help in the profile menu. Absorbs PRD-015 | Desktop top bar shows four labeled peers + bell + avatar; 390 bottom bar is the same four + Inbox; Live always present when stations exist |
| EXP-003 | **Explore, cinema-first**: a For you **hero** (backdrop, title, one *why* sentence, Play / More), shelves below; browse tiles move under a “Browse” row lower on the page; *why* on hover/focus/tap only | First viewport at 1440 and 390 is art plus one sentence |
| EXP-004 | **Voice pass on *why* sentences** (server): templates rewritten in the curator’s voice; a quality gate that refuses fragments; never “You” about household evidence (PRIV-001 rule) | Sampled 50 For you cards: no fragment, no lowercase names, no account handles |
| EXP-005 | **Member-vocabulary sweep**: no system terms (cosine, Scheduled Tasks, turnstyle, agent activity, CuratorX) on member or Youth surfaces; one assistant name (UX-006); GRO-015 rule | A copy lint (allowlist of member strings) passes in CI |
| EXP-006 | **Art never looks broken**: dominant-color + blurhash placeholders from the server; art served from Projectionist’s own cache for every client (with SEC-013 egress policy) | No grey placeholder visible after 1 s on LAN in any screenshot of the gallery |
| EXP-007 | **Search for watching, not managing**: owner bulk tools move to Admin → Libraries (PRD-014); search results are art-led | Member and owner search look the same; Delete is not reachable from Search |
| EXP-008 | **Live guide polish** (within the PRD-007 freeze: fixes only): sub-15-minute fillers collapse into a hairline “between programs” marker; empty rows get one sentence; now/next preview strip | No wrapped time text at any width; Youth-skipped row explains itself |
| EXP-009 | **Inbox as letters**: grouped (For you · Household · Letters), art-led rows, swipe/hover actions instead of per-row buttons; one count (UX-007) | Member Inbox has no checkboxes by default; badge count matches everywhere |
| EXP-010 | **Chat, quieter**: deduplicated thread list (empty threads are not saved), rendered previews, one starter row, mood chips behind a single control, title cards with art and **Play / Play in…** | Composer area shows at most one row of suggestions |
| EXP-011 | **Design gallery** (VIS-021) as the shared visual reference for every client, screenshot-tested in both themes at 390 / 1024 / 1440 | Gallery route renders every primitive and the four anchor screens |
| EXP-012 | **Title detail keeps navigation** without breaking the hero (VIS-008 reframed): transparent shell over art | Back and primary peers reachable on title detail at every width |

**Sequencing:** EXP-001, EXP-004, EXP-005 first (they make every later screen cheaper and fix what members read). Then EXP-002, EXP-003, EXP-006 (the art-first core). Then the rest, alongside ENG / SES.

**Open for the person:** approve the `EXP` prefix; confirm Explore (not Chat) as the default home for members, which the red team’s Q2 left open and the native clients already assume.
