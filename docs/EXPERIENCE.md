# Experience convergence

One design language across web, phone, tablet, and TV. The web app and native clients feel like one product because they share one language, one navigation model, one voice, and one source for design values.

**Status:** Proposed (EXP prefix **accepted** 2026-11-18). Item IDs (`EXP-…`) are tracked in [docs/roadmap/](roadmap/README.md).
**Audience:** Developers / contributors; members for behavior.
**Related:** [DESIGN.md](DESIGN.md) · [PRODUCT.md](PRODUCT.md) · [NATIVE_CLIENTS.md](NATIVE_CLIENTS.md) · [DOCS_STYLE.md](DOCS_STYLE.md)

Jump to: [Densities](#one-language-three-densities) · [Items](#roadmap-items) · [Open decisions](#open-decisions)

---

## One language, three densities

| Density | Where | Feel |
|---------|-------|------|
| **Cinema** | TV clients, Watch, Live, Title, the top of Explore | Art fills the screen; one sentence; one gold action |
| **Companion** | Phone, tablet, web Explore / Chat / Inbox / Search | Touch-first, art-led cards; the *why* on focus / hover / tap, not as a wall of text |
| **Workbench** | Admin | Dense and utilitarian; same type and amber (1.40.0 Admin is the foothold) |

**Protect:** Title detail (full-bleed art, Fraunces title, one gold **Play**) and Lobby Theater (one poster) are the templates the rest grow toward.

**Explore is the default home** for every member, Youth, and guest, on every client (decided 2026-11-18). Chat stays a primary peer (Explore · Live · Chat · Search).

---

## Roadmap items

| ID | Item | Why | Done when | Depends on | Status |
|----|------|-----|-----------|------------|--------|
| EXP-001 | **Design tokens as source of truth** — `design/tokens.json` generates `frontend/src/styles/01-tokens.css` and a Swift token file for native clients; absorbs VIS-005/006/007/010/011/012/015; stylelint gate (VIS-020) | One edit changes web and native | One edit to `tokens.json` changes web and native; CI fails on hard-coded colors outside tokens | — | proposed |
| EXP-002 | **One navigation model** — Explore · Live · Chat · Search as primary peers on every client; Inbox behind the bell; Settings, Admin, theme, Help in the profile menu (absorbs PRD-015) | Members stop learning a different map per device | Desktop top bar shows four labeled peers + bell + avatar; 390 bottom bar is the same four + Inbox; Live always present when stations exist | EXP-001 | proposed |
| EXP-003 | **Explore, cinema-first** — For you **hero** (backdrop, title, one *why* sentence, Play / More), shelves below; browse tiles under a lower “Browse” row; *why* on hover/focus/tap only | First paint is cinema, not tools | First viewport at 1440 and 390 is art plus one sentence | EXP-001, EXP-004 | proposed |
| EXP-004 | **Voice pass on *why* sentences** (server) — templates in the curator’s voice; quality gate refuses fragments; never “You” about household evidence (PRIV-001) | For you stops reading like debug output | Sampled 50 For you cards: no fragment, no lowercase names, no account handles | — | done |
| EXP-005 | **Member-vocabulary sweep** — no system terms (cosine, Scheduled Tasks, turnstyle, agent activity, CuratorX) on member or Youth surfaces; one assistant name (UX-006); GRO-015 | Members never see internals | A copy lint (allowlist of member strings) passes in CI | — | done |
| EXP-006 | **Art never looks broken** — one authenticated route serves cached posters and backdrops for every client. The server fetches the image under the SEC-013 egress policy and caches it. Hub, title, and search payloads set `poster_url` and `backdrop_url` to that route instead of an empty string or a tokenized Plex URL. Dominant-color and blurhash placeholders can follow on the same item | Clients cannot show art while thumbs stay on Plex and the API strips the token | A credentialed client loads a poster and a backdrop from the route; hub, title, and search cards point at it | SEC-013 (the policy ships with the route) | done |
| EXP-007 | **Search for watching, not managing** — owner bulk tools move to Admin → Libraries (PRD-014); search results are art-led | Search is a primary peer on every client | Member and owner search look the same; Delete is not reachable from Search | EXP-002 | proposed |
| EXP-008 | **Live guide polish** (within PRD-007: fixes only) — sub-15-minute fillers collapse into a hairline “between programs” marker; empty rows get one sentence; now/next preview strip | Guide stays readable on short slots | No wrapped time text at any width; Youth-skipped row explains itself | — | proposed |
| EXP-009 | **Inbox as letters** — grouped (For you · Household · Letters), art-led rows, swipe/hover actions; one count (UX-007 / PRD-009) | Inbox stops looking like an admin queue | Member Inbox has no checkboxes by default; badge count matches everywhere | EXP-002 | proposed |
| EXP-010 | **Chat, quieter** — deduplicated thread list, rendered previews, one starter row, mood chips behind a single control, title cards with art and **Play / Play in…** | Chat’s core is thin and calm | Composer area shows at most one row of suggestions | EXP-005 | proposed |
| EXP-011 | **Design gallery** (VIS-021) as the shared visual reference for every client, screenshot-tested in both themes at 390 / 1024 / 1440 | Native clients match one gallery | Gallery route renders every primitive and the four anchor screens | EXP-001 | proposed |
| EXP-012 | **Title detail keeps navigation** without breaking the hero (VIS-008 reframed): transparent shell over art | Cinema hero without trapping the member | Back and primary peers reachable on title detail at every width | EXP-002 | proposed |
| EXP-013 | **Explore is the default home** — server default of `default_page` becomes `explore` for new accounts and accounts still on `auto`; explicit `chat` still works; DESIGN / HELP / onboarding say Explore is home | Answers red-team Q2; matches native clients | A new member’s first sign-in lands on Explore at 390 and 1440; `default_page = chat` still lands on Chat; Help describes Explore as home | — | done |

**Sequencing:** EXP-013, EXP-005, EXP-004, and EXP-006 are done. **EXP-001 is next in Lane B.** Then EXP-002 → EXP-003, and the rest alongside ENG / SES. EXP-006 decided 2026-11-20 and shipped as `GET /api/library/art/{media_type}/{item_id}` (`features.cached_art`).

**Client contract:** EXP items that change chrome or tokens ship a capability bump when native clients must change (see [NATIVE_CLIENTS.md](NATIVE_CLIENTS.md#capabilities)). Web-only polish may ship without a new capability number.

---

## Open decisions

- None blocking EXP-013 / EXP-001…012 creation — prefix and Explore-as-home are **accepted** (2026-11-18).
- Verify screenshot findings from older builds on current 1.40.1 before treating each EXP item as still open.

## See also

- Carry-forward triage of 2026-11-01 review rows: [roadmap/accepted/2026-11-19-review-carryforward-triage.md](roadmap/accepted/2026-11-19-review-carryforward-triage.md)
