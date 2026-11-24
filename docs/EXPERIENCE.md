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
| EXP-014 | **Weather boards on every web width.** Six boards from the payload the server already builds (right now, next 12 hours, five-day, almanac, headlines, radar), with a chyron that adds information. At 1024 px and wider it is the channel. At 768–1023 px the same channel scales (instrument tiles 2×2, three headline columns, a compact footer). Below 768 px it is one scrolling page, not a timed channel. UV index and air quality are a hook and are not drawn. A missing reading stays blank | The forecast should read clearly on a wide screen, a tablet, and a phone | At 390, 834, and 1440 the layout matches, with no horizontal scroll at 390. Reduced motion shows the latest radar frame. The chyron never repeats the board | — | done |
| EXP-015 | **Headline controls.** Owner setting Live → Weather → Headlines, on by default. Youth sessions hide headlines unless the owner allows them. The payload says `enabled` and per-scope `available`. Titles stay as published. Off also stops the fetches. Local headlines stay a news search for the place. Owner RSS is a hook (`local_source` stays `search`) and is not fetched | Members can turn news off, and Youth does not see it by default. The local column stays the search the server already runs | With the setting off, no client shows headlines and no news feed is fetched. With it on, local headlines are still that place search | EXP-014 | done |
| EXP-016 | **Poster depth on the web.** One Poster component: rounded art, a rim light, a two-layer shadow, a bottom scrim when the title sits on the art, and a lift on hover and keyboard focus that reduced motion turns off. Missing art is a deterministic placeholder seeded by the item id, and cached art fades in over it. The top nav is a glass capsule with a solid fallback when blur or transparency is unavailable | Shelves should have light and an edge, and a missing poster should not be a flat fill | Explore, Title, and the seasonal live shelf use Poster. Keyboard focus shows the lift and a visible ring | EXP-006 | done |
| EXP-017 | **Optional owner RSS for local weather headlines.** An owner may later add their own local feeds. With none set, local headlines stay the Google News search from EXP-015. Not part of EXP-015. A new feed host is listed in PRIVACY.md before any fetch | Owners who want a paper or station feed can add it, without changing the default | *Proposed.* When picked up: an owner can save feed URLs, those feeds fill the local column, and an empty list keeps today’s search. Not started | EXP-015 | proposed |
| EXP-018 | **Warm-up lines, step names, then the web screen.** One versioned lines file, a pool per playback step, and an owner humor setting. The web screen uses that file. See [Warm-up screen](#warm-up-screen) | The wait before the first frame should tell the truth and still be worth watching | The lines route, `step`, and the web screen are on main (pull request 298, `54649269`). The slowed fixture is still ahead. Not in production 1.45.5 | ENG-015 | accepted |
| EXP-019 | **Installable web app.** A manifest, a shell worker that stores the app shell and never stores API responses, art, or media, a quiet Install Projectionist entry, media keys on the library player, and the player shortcuts. Web Push waits on NAT-006 | Households whose client is the browser get their own window and media keys | On main (pull request 309, `a0d72b62`). The installed window opens on Explore. The worker serves no API or media response from cache. Push is not part of this. Not in production 1.45.5 | — | done |
| EXP-020 | **Holiday shelves with a theme.** Scored candidates, a theme, roles, grounded notes, an owner preview, and one Holidays & seasons page. Capability `holiday_shelves`. Youth responses omit After bedtime | A seasonal shelf should be a mix with a reason, and the owner should approve it | In this change. Not in the 1.46.1 image. Held until tag `v1.46.1` exists | — | accepted |

**Sequencing:** EXP-013, EXP-005, EXP-004, EXP-006, EXP-014, EXP-015, EXP-016, and EXP-019 are done. **EXP-001 is next in Lane B.** EXP-017 is proposed and later. Then EXP-002 → EXP-003, and the rest alongside ENG / SES. EXP-006 decided 2026-11-20 and shipped as `GET /api/library/art/{media_type}/{item_id}` (`features.cached_art`). The weather boards ship at three widths. UV index, air quality, and owner RSS stay hooks until the person asks. Local headlines stay a news search for the place. EXP-018's lines file, step names, and web screen are on main (pull request 298, `54649269`). The slowed fixture is still ahead. EXP-019 is on main (pull request 309, `a0d72b62`) and is not in production 1.45.5. Push waits.

**Client contract:** EXP items that change chrome or tokens ship a capability bump when native clients must change (see [NATIVE_CLIENTS.md](NATIVE_CLIENTS.md#capabilities)). Web-only polish may ship without a new capability number. No new weather route and no new capability number. Headline `enabled` and per-scope `available` are the EXP-015 flags. `local_source` stays `search` until an owner feed list exists. UV and air quality are not part of this web pass.

## Warm-up screen

The lines file, the session step names, and the web screen are on main (pull request 298, `54649269`). The slowed fixture is still ahead. Other clients use [the outbox handoff](roadmap/outbox/2026-11-22-EXP-018-apple.md). Their screens are not specified here. This follows ENG-015. It is not in production 1.45.5.

Live's scope freeze (PRD-007) still holds. The static on a tune stays a short channel flip. This item adds no channel type.

**Why.** The wait before the first frame is real work: waking disks, remuxing, encoding the sound, preparing captions, sometimes falling back to the library path. A screen that uses the title's art, tells the truth about the step, and offers one dry line makes that wait part of the show.

**Done when.**

- *Proposed:* `GET /api/playback/warmup-lines` returns a versioned document with a general pool and a pool per step. Clients cache it. New lines ship in that file, without a client release. The starter lines are the accepted drop [2026-11-22-EXP-018-warmup-screen.md](roadmap/accepted/2026-11-22-EXP-018-warmup-screen.md).
- *Proposed:* the session `step` is one of `waking_disk`, `probing`, `remuxing`, `encoding_audio`, `preparing_captions`, `falling_back`, `waiting_on_plex`, `buffering`.
- The owner can set Warm-up humor to On (default), Dry (the status line only, art kept), or Off (a minimal indicator on the art). The lines stay appropriate for every member, including Youth. An error is never a joke. No line repeats during a session.
- On the web, a start that is not playing within about 0.8 seconds shows the title's art, one line from that step's pool and then the general pool, and an honest status line with a counter. A fallback to the library path stays on the screen and moves to the `falling_back` pool, with no error shown for a fallback that works. After about 45 seconds with no first frame, the jokes stop and the page offers Keep waiting, Try again, and Back, with the reason.
- Reduced motion does not drift or flicker. The status line is the live region. Joke lines are hidden from assistive tech.
- A slowed fixture shows the warm-up and shows it gone after the first frame.
- On Live, static still comes first. If the tune takes longer than about 1.5 seconds, the static gives way to this screen and uses the program's or the channel's art.

**Depends on.** The session `state` values from the work already running. Art URLs from EXP-006. It sits behind ENG-015 in the playback queue.

**Client contract.** `warmup_screen` is `1` when the lines document and `step` are served. A missing name means the client shows art and an honest status, with no joke line. `GET /api/playback/warmup-lines` returns version `1` and a pool per step. The session read includes `step`. The web screen in this repository is the next client.

**Honest limits.** The screen does not make a slow disk faster, and it does not start a transcode on its own. Humor Off and Dry are the owner's choice for the household.

**Privacy.** The lines file is static copy. The step is part of the household session record. No new host is contacted.

**Status.** The lines file, `step`, and the web screen are in. The owner humor control is still On. A slowed live play was not run in a browser in this pass.

---

## Open decisions

- None blocking EXP-013 / EXP-001…012 creation — prefix and Explore-as-home are **accepted** (2026-11-18).
- Verify screenshot findings from older builds on current 1.40.1 before treating each EXP item as still open.
- Weather boards on the web are **done** at three widths (2026-11-21). UV index, air quality, and owner RSS are hooks and wait for the person. Local headlines stay a news search. Owner RSS remains proposed as EXP-017.

## See also

- Carry-forward triage of 2026-11-01 review rows: [roadmap/accepted/2026-11-19-review-carryforward-triage.md](roadmap/accepted/2026-11-19-review-carryforward-triage.md)
