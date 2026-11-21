# Roadmap board — media engine, shared sessions, and tracks

The single list of planned platform work for the next era of Projectionist: our own playback engine, sessions that span devices, a time-coded understanding of every film and episode, and tracks that play with them — plus **experience convergence** so web and native clients share one language. How drops become items: [docs/claude.roadmap.md](../claude.roadmap.md).

**Why this era.** Projectionist is media intelligence for people who love their collections — not a recommendation widget. Owning the stream frees playback from Plex (and makes Jellyfin possible). Knowing *when* things happen inside a title lets the curator speak at the right moment. Sessions that span devices make a phone a companion, not just a remote. Every ENG/SES/TML/TRK item here works for **TV episodes and seasons** as well as films.

Status values: `proposed` · `accepted` · `in progress` · `shipped (x.y.z)` · `done` · `parked` · `declined`.

## Sequencing

1. **ENG** — the playback engine. Lane order: ENG-001 → ENG-002 → ENG-003 → **ENG-007** → ENG-004 → the rest. ENG-007 is off until the household turns on *Play through Projectionist*
2. **SES** — shared sessions (extends the Apple TV pairing + throw work)
3. **TML** — the timeline layer
4. **TRK** — tracks: Moments, Booth Notes, Class / Study
5. **NAT** — the client contract, threaded through 1–4 as each capability ships
6. **EXP** — experience convergence (parallel). Lane B’s next item is **EXP-001** (design tokens). EXP-013, EXP-004, EXP-005, and EXP-006 are done. EXP-014, EXP-015, and EXP-016 are accepted

## Board

| ID | Title | Status | Owning doc |
|----|-------|--------|------------|
| ENG-001 | Media source interface + Plex path mapping + cached ffprobe | proposed | [PLAYBACK_ENGINE](../PLAYBACK_ENGINE.md#roadmap-items) |
| ENG-002 | Planner with recorded reason; dry-run plan endpoint | proposed | [PLAYBACK_ENGINE](../PLAYBACK_ENGINE.md#roadmap-items) |
| ENG-003 | Session API with device profiles; VOD fMP4 HLS remux | proposed | [PLAYBACK_ENGINE](../PLAYBACK_ENGINE.md#roadmap-items) |
| ENG-004 | WebVTT caption renditions (household cache first) | proposed | [PLAYBACK_ENGINE](../PLAYBACK_ENGINE.md#roadmap-items) |
| ENG-005 | Image-caption OCR job | proposed | [PLAYBACK_ENGINE](../PLAYBACK_ENGINE.md#roadmap-items) |
| ENG-006 | Audio + full transcode plans; hardware encode; concurrency | proposed | [PLAYBACK_ENGINE](../PLAYBACK_ENGINE.md#roadmap-items) |
| ENG-007 | Web player on engine sessions, right after ENG-003, behind an off-by-default setting | accepted | [PLAYBACK_ENGINE](../PLAYBACK_ENGINE.md#roadmap-items) |
| ENG-008 | Scrub thumbnails | proposed | [PLAYBACK_ENGINE](../PLAYBACK_ENGINE.md#roadmap-items) |
| ENG-009 | Live Channels on engine sessions (ARCH-007 facade; PRD-007 freeze) | proposed | [PLAYBACK_ENGINE](../PLAYBACK_ENGINE.md#roadmap-items) |
| ENG-010 | Jellyfin media source | proposed | [PLAYBACK_ENGINE](../PLAYBACK_ENGINE.md#roadmap-items) |
| SES-001 | Device credentials for every handheld sign-in path (same work as NAT-002) | accepted | [SHARED_SESSIONS](../SHARED_SESSIONS.md#roadmap-items) |
| SES-002 | Rooms registry + visibility | proposed | [SHARED_SESSIONS](../SHARED_SESSIONS.md#roadmap-items) |
| SES-003 | Session object (owner, screen, position, level) | proposed | [SHARED_SESSIONS](../SHARED_SESSIONS.md#roadmap-items) |
| SES-004 | Realtime channel + command authorization + clock | proposed | [SHARED_SESSIONS](../SHARED_SESSIONS.md#roadmap-items) |
| SES-005 | Join flow + guest permissions | proposed | [SHARED_SESSIONS](../SHARED_SESSIONS.md#roadmap-items) |
| SES-006 | Handheld captions | proposed | [SHARED_SESSIONS](../SHARED_SESSIONS.md#roadmap-items) |
| SES-007 | Handoff between screens | proposed | [SHARED_SESSIONS](../SHARED_SESSIONS.md#roadmap-items) |
| SES-008 | Web client as a second screen | proposed | [SHARED_SESSIONS](../SHARED_SESSIONS.md#roadmap-items) |
| SES-009 | Youth join approval tightens the session ceiling | accepted | [SHARED_SESSIONS](../SHARED_SESSIONS.md#privacy-and-youth) |
| TML-001 | Timeline schema + file fingerprinting | proposed | [TIMELINE](../TIMELINE.md#roadmap-items) |
| TML-002 | Dialogue import from the household subtitle cache | proposed | [TIMELINE](../TIMELINE.md#roadmap-items) |
| TML-003 | Scene / shot detection job | proposed | [TIMELINE](../TIMELINE.md#roadmap-items) |
| TML-004 | Speaker hints | proposed | [TIMELINE](../TIMELINE.md#roadmap-items) |
| TML-005 | `timeline_context` agent tool + spoiler guard | proposed | [TIMELINE](../TIMELINE.md#roadmap-items) |
| TML-006 | Chat turns carry session context | proposed | [TIMELINE](../TIMELINE.md#roadmap-items) |
| TML-007 | Series index across episodes | proposed | [TIMELINE](../TIMELINE.md#roadmap-items) |
| TML-008 | Owner timeline coverage view | proposed | [TIMELINE](../TIMELINE.md#roadmap-items) |
| TRK-001 | Track + cue schema, storage, validation | proposed | [TRACKS](../TRACKS.md#roadmap-items) |
| TRK-002 | Moments track generation | proposed | [TRACKS](../TRACKS.md#roadmap-items) |
| TRK-003 | Track delivery on sessions | proposed | [TRACKS](../TRACKS.md#roadmap-items) |
| TRK-004 | Booth Notes editions (Mix × Heat) | proposed | [TRACKS](../TRACKS.md#roadmap-items) |
| TRK-005 | Trusted public sources (owner opt-in) | proposed | [TRACKS](../TRACKS.md#roadmap-items) |
| TRK-006 | Class / Study lessons on the timeline | proposed | [TRACKS](../TRACKS.md#roadmap-items) |
| TRK-007 | Detours | proposed | [TRACKS](../TRACKS.md#roadmap-items) |
| TRK-008 | “Your edition is ready” notifications | proposed | [TRACKS](../TRACKS.md#roadmap-items) |
| TRK-009 | Series studies | proposed | [TRACKS](../TRACKS.md#roadmap-items) |
| TRK-010 | Web overlay renderer | proposed | [TRACKS](../TRACKS.md#roadmap-items) |
| NAT-001 | Capability manifest + `api_contract` | done | [NATIVE_CLIENTS](../NATIVE_CLIENTS.md#roadmap-items) |
| NAT-002 | Handheld device credentials for every web sign-in path | accepted | [NATIVE_CLIENTS](../NATIVE_CLIENTS.md#roadmap-items) |
| NAT-003 | OpenAPI snapshot + client route tags + CI drift check | done | [NATIVE_CLIENTS](../NATIVE_CLIENTS.md#roadmap-items) |
| NAT-004 | Response fixtures | done | [NATIVE_CLIENTS](../NATIVE_CLIENTS.md#roadmap-items) |
| NAT-005 | Settings → Devices + device kind on claim/list | proposed | [NATIVE_CLIENTS](../NATIVE_CLIENTS.md#roadmap-items) |
| NAT-006 | Content-free push, including security approvals | accepted | [NATIVE_CLIENTS](../NATIVE_CLIENTS.md#roadmap-items) |
| EXP-001 | Design tokens as source of truth | proposed | [EXPERIENCE](../EXPERIENCE.md#roadmap-items) |
| EXP-002 | One navigation model | proposed | [EXPERIENCE](../EXPERIENCE.md#roadmap-items) |
| EXP-003 | Explore, cinema-first | proposed | [EXPERIENCE](../EXPERIENCE.md#roadmap-items) |
| EXP-004 | Voice pass on *why* sentences | done | [EXPERIENCE](../EXPERIENCE.md#roadmap-items) |
| EXP-005 | Member-vocabulary sweep | done | [EXPERIENCE](../EXPERIENCE.md#roadmap-items) |
| EXP-006 | Art never looks broken | done | [EXPERIENCE](../EXPERIENCE.md#roadmap-items) |
| EXP-007 | Search for watching, not managing | proposed | [EXPERIENCE](../EXPERIENCE.md#roadmap-items) |
| EXP-008 | Live guide polish (PRD-007 fixes only) | proposed | [EXPERIENCE](../EXPERIENCE.md#roadmap-items) |
| EXP-009 | Inbox as letters | proposed | [EXPERIENCE](../EXPERIENCE.md#roadmap-items) |
| EXP-010 | Chat, quieter | proposed | [EXPERIENCE](../EXPERIENCE.md#roadmap-items) |
| EXP-011 | Design gallery | proposed | [EXPERIENCE](../EXPERIENCE.md#roadmap-items) |
| EXP-012 | Title detail keeps navigation | proposed | [EXPERIENCE](../EXPERIENCE.md#roadmap-items) |
| EXP-013 | Explore is the default home | done | [EXPERIENCE](../EXPERIENCE.md#roadmap-items) |
| EXP-014 | Weather boards on the web, every width | accepted | [EXPERIENCE](../EXPERIENCE.md#roadmap-items) |
| EXP-015 | Weather headline controls, including Youth | accepted | [EXPERIENCE](../EXPERIENCE.md#roadmap-items) |
| EXP-016 | Poster depth on the web: light, edge, generated placeholders | accepted | [EXPERIENCE](../EXPERIENCE.md#roadmap-items) |

SES-001 and NAT-002 describe the same work from two sides; build them as one change.

## Decisions

| Date | Decision |
|------|----------|
| 2026-11-18 | `EXP` (experience convergence) is an approved prefix |
| 2026-11-18 | **Explore is the default home for every member and every client.** Chat stays a primary peer; it is no longer the front door. Server default for `default_page` becomes `explore` (EXP-013) |
| 2026-11-18 | **A Youth member joining an adult’s session triggers an owner notification; Approve tightens the session to the Youth ceiling** (SES-009). Answers PRD-025 vs initiator-owns-intent |
| 2026-11-19 | Inbox processed: EXP-001…013 created; era *Depends on* updated from carry-forward triage; NAT-005 gains device kind (client APL-016 outbox) |
| 2026-11-19 | **360 reviews are local-only** (gitignore review run artifacts; untrack; strip links from tracked docs). History purge authorized the same day |
| 2026-11-19 | **Both build lanes start in parallel**: Lane A (engine remux spike) and Lane B (EXP-013 → EXP-005 → EXP-004 → EXP-001) |
| 2026-11-19 | **Agents merge their own PRs** when every required `main` CI check is green (`gh pr merge --merge`); never bypass checks; merge ≠ release |
| 2026-11-20 | **Apple clients adopt ENG-003 engine sessions before the web.** The web player stays on the Plex universal path until ENG-007. Spike code stays off `main` |
| 2026-11-20 | **EXP-006 moves to the front of Lane B.** EXP-013, EXP-005, and EXP-004 are done, so cached art is the next experience item, ahead of EXP-001 |
| 2026-11-20 | **EXP-006 ships** `GET /api/library/art/{media_type}/{item_id}`. Hub, title, and search `poster_url` / `backdrop_url` point at it. The server fetches under the SEC-013 allowlist. `features.cached_art` is the client gate |
| 2026-11-20 | **Native handhelds get every web sign-in path** (Plex, local password, OIDC, invite redeem, request access), ending in a device credential. The pair-code stays the secondary path. NAT-002 and SES-001 are accepted |
| 2026-11-20 | **Push is a priority and includes security.** Payloads stay content-free. NAT-006 is accepted: device sign-in approval, Youth join on the same object, and a new-device notice |
| 2026-11-20 | **The web takes engine sessions as ENG-007, immediately after ENG-003**, behind *Play through Projectionist* (off by default). Apple clients still adopt ENG-003 first. Captions fall back to the Plex path until ENG-004 |
| 2026-11-20 | **NAT-001** publishes `api_contract` 3 and the capability map on every `GET /api/features`. Shipped keys are `device_pairing` 1, `throw` 1, and `cached_art` 1 (the same fact as `features.cached_art`). Accepted keys stay at 0: `native_sign_in`, `push`, `approvals`, plus the engine, session, timeline, and track names |
| 2026-11-20 | **NAT-003** tags the routes a native client may call and checks `docs/api/openapi.json` in CI. Admin routes, device claim, and device revoke stay out of that set |
| 2026-11-20 | **NAT-004** records one example response per client route under `docs/api/fixtures/` and checks it in CI |
| 2026-11-19 | **Lane A remux spike:** H.264+AC-3 fMP4 HLS (`-c copy`) + household WebVTT works on Safari/WebKit and tvOS AVPlayer (seek without restart; captions selectable). Desktop Chrome/hls.js rejects AC-3 — planner must audio-transcode for those profiles. Findings: [engine-spike-findings](../superpowers/specs/2026-11-19-engine-spike-findings.md). Spike code stays on `spike/engine-remux` (not merged) |

## Superseded review rows (carry-forward)

| Review ID | Replaced by |
|-----------|-------------|
| PRD-022 | SES-002 / SES-003 (Projectionist screens). Plex-as-screen kind can return later behind the same session API |
| PRD-024 (in part) | Engine attribution (ENG-003). Native-Plex “likely” tier remains GRO-010 |

## Folders

- [`inbox/`](inbox/) — drop new material here
- [`accepted/`](accepted/) — processed drops with their notes
- [`outbox/`](outbox/) — handoffs to client repositories
