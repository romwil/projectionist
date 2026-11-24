# Roadmap board — media engine, shared sessions, and tracks

The single list of planned platform work for the next era of Projectionist: our own playback engine, sessions that span devices, a time-coded understanding of every film and episode, and tracks that play with them — plus **experience convergence** so web and native clients share one language. How drops become items: [docs/claude.roadmap.md](../claude.roadmap.md).

**Why this era.** Projectionist is media intelligence for people who love their collections — not a recommendation widget. Owning the stream frees playback from Plex (and makes Jellyfin possible). Knowing *when* things happen inside a title lets the curator speak at the right moment. Sessions that span devices make a phone a companion, not just a remote. Every ENG/SES/TML/TRK item here works for **TV episodes and seasons** as well as films.

Status values: `proposed` · `accepted` · `in progress` · `shipped (x.y.z)` · `done` · `parked` · `declined`.

## Sequencing

Three lanes run at the same time. The engine lane is the playback tiers, then Jellyfin (ENG-010). ENG-010 follows ENG-012, ENG-013, ENG-005, and ENG-014, includes the Jellyfin side of the source-transcode tier (ENG-013), and comes before any public community launch. Native clients run in their own repository, in parallel. This board does not record their screens or plans. The server-for-sessions lane is SES-001 through SES-009, then the timeline (TML), then tracks (TRK). NAT items thread through as each capability ships. The public community launch is the last milestone and has no date. Its install template, hardware passthrough docs, first-run onboarding, privacy statement, and security review are written when that work starts.

The numbered list is the subject order inside that plan.

1. **ENG** — the playback engine. Shipped through ENG-007 and ENG-004, including text captions extracted ahead of play. The web profile comes from the browser's own codec checks. ENG-011, the library playability report, is done. ENG-012 serves an audio-only transcode: the video is copied and the audio is encoded for the device. ENG-013 asks the media source to transcode a picture the device cannot play, and records why. The member still plays on that source's existing path. ENG-014 makes compatible copies inside the owner's disk budget. Next, not started: ENG-005, then ENG-010. ENG-006 stays waiting. ENG-015 prepares the film while the preroll plays. The server session and the web hand-off are on main (pull request 298, `54649269`). They are not in production 1.45.5. The playability report now names the codecs in the video-transcode bucket for each device. Level stays blank until the listing or ffprobe confirms it. HDR comes from Plex's stored media analysis when that database is available: HDR10 and HLG stay distinct, and a missing transfer stays blank. Watch count and file size come from Plex metadata, which is enough to rank a copy ahead of time. ENG-006 is not started. Engine sessions are opt-in (`engine_opt_in`). Play through Projectionist stays off until an owner turns it on
2. **SES** — shared sessions (extends the pairing and throw work), SES-001 through SES-009, in the sessions lane. Signed-in clients learn the home and away addresses (`household_addresses`). Rooms (`rooms`) are the named screens, without what is playing. A session (`session_object`) has an owner, a screen, a position, and a level. The live channel (`shared_sessions`) authorizes commands and stamps them with server time. Joining (`session_join`) is a code on the screen or the starter's approval. A Youth member asks first (`youth_join`); approval tightens the room, and push waits. A device in the session can read a caption feed (`session_captions`). The starter can move the same session to another screen (`session_handoff`). A media file can be fingerprinted (`timeline_files`), and dialogue can be imported from the subtitle cache (`timeline_dialogue`). The web client lists rooms, starts a film with Play in…, and follows that session as a remote (SES-008, pull request 311, `b2d3b226`). That is on main and not in production 1.45.5.
3. **TML** — the timeline layer, after the session items
4. **TRK** — tracks: Moments, Booth Notes, Class / Study, after the timeline
5. **NAT** — the client contract, threaded through the lanes as each capability ships
6. **EXP** — experience convergence (parallel). Lane B’s next item is **EXP-001** (design tokens). EXP-013, EXP-004, EXP-005, EXP-006, EXP-014, EXP-015, and EXP-016 are done. EXP-017 (owner RSS for local headlines) is proposed and later. UV index and air quality on the weather boards are hooks and wait for the person. EXP-018 is the warm-up lines file, the step names, and the web screen, on main (pull request 298, `54649269`). The slowed fixture is still ahead. EXP-019, the installable web app, is done on main (pull request 309, `a0d72b62`). Push waits. Neither is in production 1.45.5.
7. **SEC** — the public front door, continued from the review series at the next free numbers (SEC-017 onward). SEC-017 through SEC-022 are the gate before the extra login on the public hostname can come off. That login stays until the person removes it. SEC-017 through SEC-024 are on main. SEC-025 (a new sign-in tells the owner) is in this change and is not a release image. Edge rules are a separate plan and are not applied here.

**Before the next production rollout.** Two defects from QA 1.41.1 are recorded below. They are not new capability items. The database-file fix lands before production moves. The Safari stall is investigated before any further playlist change. This record does not edit `docs/RELEASE.md`; the fix lane adds the empty-database check to that file’s pre-rollout checklist.

## Board

| ID | Title | Status | Owning doc |
|----|-------|--------|------------|
| ENG-001 | Media source interface + Plex path mapping + cached ffprobe | done | [PLAYBACK_ENGINE](../PLAYBACK_ENGINE.md#roadmap-items) |
| ENG-002 | Planner with recorded reason; dry-run plan endpoint | done | [PLAYBACK_ENGINE](../PLAYBACK_ENGINE.md#roadmap-items) |
| ENG-003 | Session API with device profiles; VOD fMP4 HLS remux | done | [PLAYBACK_ENGINE](../PLAYBACK_ENGINE.md#roadmap-items) |
| ENG-004 | WebVTT caption renditions (household cache first). Text captions are extracted ahead of play. Picture captions stay on the Plex path | done | [PLAYBACK_ENGINE](../PLAYBACK_ENGINE.md#roadmap-items) |
| ENG-005 | Image-caption OCR job | proposed | [PLAYBACK_ENGINE](../PLAYBACK_ENGINE.md#roadmap-items) |
| ENG-006 | Own video transcode: software 1080p H.264 above a benchmark, plus VAAPI/NVENC. The report names the codecs that would need it and can rank a copy ahead of time. This stays waiting | accepted | [PLAYBACK_ENGINE](../PLAYBACK_ENGINE.md#roadmap-items) |
| ENG-007 | Web player on engine sessions, behind an off-by-default setting. The profile comes from the browser's codec checks | done | [PLAYBACK_ENGINE](../PLAYBACK_ENGINE.md#roadmap-items) |
| ENG-008 | Scrub thumbnails | proposed | [PLAYBACK_ENGINE](../PLAYBACK_ENGINE.md#roadmap-items) |
| ENG-009 | Live Channels on engine sessions (ARCH-007 facade; PRD-007 freeze) | proposed | [PLAYBACK_ENGINE](../PLAYBACK_ENGINE.md#roadmap-items) |
| ENG-010 | Jellyfin media source | proposed | [PLAYBACK_ENGINE](../PLAYBACK_ENGINE.md#roadmap-items) |
| ENG-011 | Library playability report for each device profile | done | [PLAYBACK_ENGINE](../PLAYBACK_ENGINE.md#library-playability-report) |
| ENG-012 | Audio-only transcode tier | done | [PLAYBACK_ENGINE](../PLAYBACK_ENGINE.md#roadmap-items) |
| ENG-013 | Source-transcode tier. A picture the device cannot play is asked of the media source, with a reason. Members see the same playback | done | [PLAYBACK_ENGINE](../PLAYBACK_ENGINE.md#roadmap-items) |
| ENG-014 | Pre-optimized versions inside a disk budget. The owner chooses a folder outside the Plex libraries. The job starts with titles above 1080p, then the most-watched, until the disk budget. One encode at a time, from 1:00 a.m. to 6:00 a.m. A ready copy plays as direct or remux | done | [PLAYBACK_ENGINE](../PLAYBACK_ENGINE.md#roadmap-items) |
| ENG-015 | Prepare the film while the preroll plays. The server starts the film session at Play, records `ready_at_handoff`, and moves to the library path if the engine stops during the bumper. The web hand-off is on main (pull request 298, `54649269`). Not in production 1.45.5 | done | [PLAYBACK_ENGINE](../PLAYBACK_ENGINE.md#prepare-the-film-during-the-preroll) |
| SES-001 | Device credentials for every handheld sign-in path (same work as NAT-002) | done | [SHARED_SESSIONS](../SHARED_SESSIONS.md#roadmap-items) |
| SES-002 | Rooms registry + visibility | done | [SHARED_SESSIONS](../SHARED_SESSIONS.md#rooms) |
| SES-003 | Session object (owner, screen, position, level) | done | [SHARED_SESSIONS](../SHARED_SESSIONS.md#roadmap-items) |
| SES-004 | Realtime channel + command authorization + clock | done | [SHARED_SESSIONS](../SHARED_SESSIONS.md#the-realtime-channel) |
| SES-005 | Join flow + guest permissions | done | [SHARED_SESSIONS](../SHARED_SESSIONS.md#roadmap-items) |
| SES-006 | Handheld captions | done | [SHARED_SESSIONS](../SHARED_SESSIONS.md#roadmap-items) |
| SES-007 | Handoff between screens | done | [SHARED_SESSIONS](../SHARED_SESSIONS.md#roadmap-items) |
| SES-008 | Web client as a second screen. Settings → Rooms, Play in…, and the live-channel remote are on main (pull request 311, `b2d3b226`). Not in production 1.45.5 | done | [SHARED_SESSIONS](../SHARED_SESSIONS.md#roadmap-items) |
| SES-009 | Youth join approval tightens the session ceiling | done | [SHARED_SESSIONS](../SHARED_SESSIONS.md#privacy-and-youth) |
| TML-001 | Timeline schema + file fingerprinting | done | [TIMELINE](../TIMELINE.md#roadmap-items) |
| TML-002 | Dialogue import from the household subtitle cache | done | [TIMELINE](../TIMELINE.md#roadmap-items) |
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
| NAT-002 | Handheld device credentials for every web sign-in path | done | [NATIVE_CLIENTS](../NATIVE_CLIENTS.md#roadmap-items) |
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
| EXP-014 | Weather boards on the web, every width. UV and air quality are hooks | done | [EXPERIENCE](../EXPERIENCE.md#roadmap-items) |
| EXP-015 | Weather headline controls, including Youth. Local headlines stay a news search | done | [EXPERIENCE](../EXPERIENCE.md#roadmap-items) |
| EXP-016 | Poster depth on the web: light, edge, generated placeholders | done | [EXPERIENCE](../EXPERIENCE.md#roadmap-items) |
| EXP-017 | Optional owner RSS for local weather headlines | proposed | [EXPERIENCE](../EXPERIENCE.md#roadmap-items) |
| EXP-018 | Warm-up lines, step names, and the web screen are on main (pull request 298, `54649269`). Humor stays On. The slowed fixture is still ahead. Not in production 1.45.5 | accepted | [EXPERIENCE](../EXPERIENCE.md#warm-up-screen) |
| EXP-019 | Installable web app. Manifest, shell worker, quiet install, media keys, shortcuts. On main (pull request 309, `a0d72b62`). Push waits. Not in production 1.45.5 | done | [EXPERIENCE](../EXPERIENCE.md#roadmap-items) |
| SEC-017 | Use the tunnel client address for rate limits | done | [SECURITY](../SECURITY.md#roadmap-items) |
| SEC-018 | Throttle sign-in failures per account | done | [SECURITY](../SECURITY.md#roadmap-items) |
| SEC-019 | Require a second factor for owner accounts | done | [SECURITY](../SECURITY.md#roadmap-items) |
| SEC-020 | Treat the tunnel as outside the house | done | [SECURITY](../SECURITY.md#roadmap-items) |
| SEC-021 | Keep private responses out of shared caches | done | [SECURITY](../SECURITY.md#roadmap-items) |
| SEC-022 | Give anonymous callers only the sign-in card | done | [SECURITY](../SECURITY.md#roadmap-items) |
| SEC-023 | Check the origin on cookie writes | done | [SECURITY](../SECURITY.md#roadmap-items) |
| SEC-024 | Keep MCP on the LAN unless the owner says otherwise | done | [SECURITY](../SECURITY.md#roadmap-items) |
| SEC-025 | Notice a new sign-in | done | [SECURITY](../SECURITY.md#roadmap-items) |
| SEC-026 | Review the public handshake | accepted | [SECURITY](../SECURITY.md#roadmap-items) |

## Known defects (not roadmap items)

Bugs stay off the item list. Both of these shipped in 1.41.2.

| Defect | Status | Owning doc |
|--------|--------|------------|
| An empty or invalid `projectionist.db` hides the real database and can stop startup. Skip that file, log the skip, and refuse to start when two real databases are present. Do not delete or overwrite anything automatically | Shipped in 1.41.2. The pre-rollout check is in `docs/RELEASE.md` | [DATA_MODEL](../DATA_MODEL.md#which-database-file-opens) |
| Safari on the Plex path stops after one burst (QA 1.41.1). `BANDWIDTH` is the measured peak plus 10 percent. `AVERAGE-BANDWIDTH` is the container average | Shipped in 1.41.2. A 15-minute Safari watch is still the proof the stall is gone | [PLAYBACK_ENGINE](../PLAYBACK_ENGINE.md#known-defect-safari-stops-after-one-burst-qa-1411) |
| QA 1.42.0: a device credential opened an engine session, then the header-free playlist returned 401 because the household gate ignored the path token. The preroll played. The film did not | Fixed on main. Not in the 1.42.0 image. Clients must send `engine_opt_in` | [PLAYBACK_ENGINE](../PLAYBACK_ENGINE.md#playlist-401-on-a-device-credential-2026-11-21) |

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
| 2026-11-20 | **Weather boards show UV index and air quality.** `air-quality-api.open-meteo.com` is already listed in PRIVACY.md; showing the numbers is not a new egress host. Local headlines stay a Google News search for the place. Owner RSS feeds are later (EXP-017, proposed), not part of EXP-015 |
| 2026-11-20 | **QA 1.41.1 defects, recorded and not fixed.** An empty `projectionist.db` must not hide the real database; that fix lands before the next production rollout, including its `docs/RELEASE.md` checklist line (the fix lane writes that line). Safari on the Plex path still stops after one burst; the cause is written down before the playlist changes again |
| 2026-11-20 | **NAT-001** publishes `api_contract` 3 and the capability map on every `GET /api/features`. Shipped keys are `device_pairing` 1, `throw` 1, and `cached_art` 1 (the same fact as `features.cached_art`). Accepted keys stay at 0: `native_sign_in`, `push`, `approvals`, plus the engine, session, timeline, and track names |
| 2026-11-20 | **NAT-003** tags the routes a native client may call and checks `docs/api/openapi.json` in CI. Admin routes, device claim, and device revoke stay out of that set |
| 2026-11-20 | **Play through Projectionist** is the household switch `features.play_through_projectionist`, off by default. The owner sets it with `PUT /api/playback/engine-setting`. The web player uses an engine session only while it is on |
| 2026-11-20 | **NAT-004** records one example response per client route under `docs/api/fixtures/` and checks it in CI |
| 2026-11-20 | **NAT-002** lets every web sign-in path end in a device credential. `native_sign_in` is 1. `sign_in` on `GET /api/features` lists the methods this household has turned on. The pair-code stays the secondary path |
| 2026-11-20 | **ENG-001** reads a title through a Plex media source: owner path mappings, cached ffprobe, and `GET /api/playback/media/{rating_key}` with no file paths in the response |
| 2026-11-21 | **ENG-004** puts household subtitle files into the engine master playlist as WebVTT. A title that can be captioned that way plays through the engine and does not record a caption fallback. Picture captions still use the Plex path until ENG-005 |
| 2026-11-21 | **Engine sessions are opt-in.** `POST /api/playback/sessions` returns a library plan unless the client sends `engine_opt_in`. `playback_engine` means the server can. The QA 1.42.0 playlist 401 was the household gate rejecting a header-free playlist URL that a device credential had opened. That URL now checks the path token. Not in the 1.42.0 image |
| 2026-11-21 | **Playback tiers, cheapest first:** direct, remux, audio-only, captions as text, source transcode, own video transcode, pre-optimized copies. ENG-011 through ENG-014 are accepted. ENG-006 is re-scoped and waits on the report. The browser profile and ahead-of-time text captions are accepted follow-ups. None of that follow-up work is started |
| 2026-11-21 | **The web profile comes from the browser.** At play time the web app asks `canPlayType`, `MediaSource.isTypeSupported`, and `MediaCapabilities.decodingInfo` for HEVC (`hvc1`, including 10-bit), AV1, AC-3, and E-AC-3, and sends that profile with the session. The planner records the answer. A browser that does not report HEVC still gets the not-playable plan. Ahead-of-time text captions, ENG-011, ENG-012, ENG-013, and ENG-014 are still not started |
| 2026-11-21 | **Text captions are extracted ahead of Play.** A library scan, a new arrival, Continue Watching, For you, or the title page queues embedded text tracks. Play serves WebVTT that is already cached and does not wait on ffmpeg. A text track that is not ready yet records that the captions are not ready, and the job keeps going. Picture captions still use the Plex path. ENG-011, ENG-012, ENG-013, ENG-014, ENG-005, and ENG-006 are not started |
| 2026-11-21 | **The library playability report is in the tree.** Settings → Playback dry-runs the planner for each named device profile, and for this browser when the owner refreshes. A title is serve the file, remux, audio-only, captions not ready yet, picture captions, ask the media source to transcode, or not playable through the engine. ENG-011 is done. ENG-012, ENG-013, ENG-005, ENG-014, and ENG-006 are not started. This is not a release |
| 2026-11-21 | **Background playback work stays quiet until the owner asks.** The playability report does not start on startup, on a timer, on a library scan, or when Settings opens. The first shares come from Plex’s stream metadata; ffprobe confirms afterwards, one file at a time, at low priority, and a restart continues. Caption extraction queues new arrivals, Continue Watching, For you, and the title page. A scan does not enqueue the library. The title being played is first in that queue. A Plex timeout is reported as a timeout. A plan the engine cannot serve (`full`, and `audio` until ENG-012) plays on the Plex path. This is not a release |
| 2026-11-21 | **The source-transcode bucket says why.** For each device, the playability report splits titles that need a video transcode into codec, level, and bit depth, and counts how many of those are above 1080p or HDR. Safari’s count and Apple TV’s count are the GPU decision. Shares still come from Plex stream metadata before ffprobe. This does not transcode, and it is not ENG-006. This is not a release |
| 2026-11-23 | **Dialogue is imported from the subtitle cache.** The import returns how many cues were stored, not the lines. Importing again replaces the previous dialogue for that file. `timeline_dialogue` is 1. This is not a release |
| 2026-11-23 | **A media file gets a fingerprint.** Size, modification time, and duration hash to one version. The same numbers return the same row. The record does not include events. `timeline_files` is 1. `timeline` stays 0. This is not a release |
| 2026-11-23 | **The starter can move a session to another screen.** The id, position, and level stay. The old screen can no longer read it. `session_handoff` is 1. This is not a release |
| 2026-11-23 | **A device in the session can read captions.** `GET /api/sessions/{id}/captions` returns the household subtitle cues. Someone outside the session gets nothing, including the line. The room's caption command is separate. `session_captions` is 1. This is not a release |
| 2026-11-23 | **A Youth member asks before joining an adult session.** The owner sees the request in Settings and can approve or say not now. Approve limits the room to that member's ceiling and pauses a title above it. Not now does not name the film. The approval is stored. A push is not sent. `youth_join` is 1. `push` and `approvals` stay 0. This is not a release |
| 2026-11-23 | **A member can join a session.** The code on the screen joins at once. Without a code, the starter approves or says not now. Until then the title stays hidden. Guests use the remote only when the starter allows it, and they cannot change the level, the room's captions, or end the session. `session_join` is 1. This is not a release |
| 2026-11-21 | **The live channel authorizes commands and carries a clock.** `/api/sessions/{id}/live` sends state and accepts commands from the starter and the screen. The same commands can be posted. A stranger is refused. Events include `server_time_ms`. While playing, a device estimates the playhead from the last position plus elapsed time. While paused, it holds. `shared_sessions` is 1 |
| 2026-11-21 | **A session has an owner, a screen, a position, and a level.** `POST /api/sessions` starts one on a room. The starter owns the level and can end it. The screen can read it and report position. Other members get 404. One session per screen; starting another ends the previous one. `session_object` is 1. It is kept in memory until restart. Joining is still later |
| 2026-11-21 | **Rooms are named screens.** `GET /api/rooms` lists them for every signed-in member. A handheld is not a room. The list has no playback and no person. `rooms` is 1. Renaming is the owner, or the member signed in on that screen |
| 2026-11-21 | **Clients learn home and away from the server.** The owner sets the public base URL. Signed-in `GET /api/features` publishes `addresses.home` and `addresses.away`. `household_addresses` is 1. Engine playlist and segment URLs stay relative. A signed-out client gets the capability and not the addresses |
| 2026-11-21 | **A picture the device cannot play asks the media source.** The plan is `source-transcode`, with a reason of codec, level, or bit depth, and the source that will do it. Plex is that source today. Projectionist does not start ffmpeg for it. Play still uses the usual path, so a member sees no change. A file this server cannot read stays a fallback, not a transcode. ENG-006 is not started: the breakdown explains the bucket and does not record a library count that would justify our own video transcode. This is not a release |
| 2026-11-21 | **Weather boards on the web** at three widths, with headline controls and poster depth. At 1024 px and wider it is the channel, 768–1023 px scales that channel, and under 768 px it is one scrolling page. Youth sessions hide headlines unless the owner allows them. Turning headlines off stops the news fetches. UV index, air quality, and owner RSS are hooks and were not added. This is not a release |
| 2026-11-21 | **Audio-only playback copies the video and converts the sound.** A title whose picture the device can play, and whose sound it cannot (E-AC-3, AC-3, DTS, TrueHD), is plan `audio` and a playable engine session. ffmpeg encodes the profile's first audio codec, usually AAC, and copies the video. That ffmpeg is idle-priority and shares the one heavy-media slot with caption extraction and the playability file check. A Play probe does not wait on that slot. A plan whose video is above the profile stays `full` and plays on the Plex path. This is not a release |
| 2026-11-21 | **Jellyfin comes before any public community launch.** ENG-010 follows ENG-012, ENG-013, ENG-005, and ENG-014, and includes the Jellyfin side of the source-transcode tier. Three lanes run at once: the engine (playback tiers, then ENG-010), native clients in their own repository, and the server for sessions (SES-001 through SES-009, then the timeline, then tracks). NAT items still thread through as each capability ships. The public community launch is the last milestone and has no date. Install template, hardware passthrough docs, first-run onboarding, the privacy statement, and a security review are written when that milestone starts. This is not a release |
| 2026-11-19 | **Lane A remux spike:** H.264+AC-3 fMP4 HLS (`-c copy`) + household WebVTT works on Safari/WebKit and tvOS AVPlayer (seek without restart; captions selectable). Desktop Chrome/hls.js rejects AC-3 — planner must audio-transcode for those profiles. Findings: [engine-spike-findings](../superpowers/specs/2026-11-19-engine-spike-findings.md). Spike code stays on `spike/engine-remux` (not merged) |
| 2026-11-22 | **The video-transcode bucket names the codec.** For each device, the playability report counts the video codecs inside that bucket. Level is left blank when a codec the device can play had no level to compare. HDR is left blank when the listing or ffprobe never said. Blank is not a count of zero. Bit depth stays zero when the profile does not limit it, which means bit depth was not the reason. The section listing supplies codec, profile, and frame size. Level, bit depth, and HDR are on the per-title stream and on ffprobe. This does not transcode, and it is not a release |
| 2026-11-22 | **The playability report can rank a copy ahead of time.** Each title keeps the watch count and file size Plex already reports. HDR10 and HLG come from the stored media analysis (`color_trc` of `smpte2084` and `arib-std-b67`), which the section listing does not carry. A missing transfer stays blank. The Safari and Apple TV video-transcode titles are ordered with anything above 1080p first, then the most-watched of the rest, and the disk total is the sum of those file sizes. The ranking does not make the copies and does not transcode. ENG-014 and ENG-006 are not started. This is not a release |
| 2026-11-22 | **An unfinished report that cannot rank is planned again from the listing.** Watch counts and file sizes are on the Plex section listing, with or without `PLEX_LIBRARY_DATABASE`. HDR still comes from the analysis rows only when that database is set, and a missing transfer stays blank rather than zero. A refresh continues ffprobe only when the saved plan already has those listing fields and a `copy_ahead` block. This does not make the copies, and it is not a release |
| 2026-11-22 | **Copies are made ahead of time, inside a disk budget.** The owner chooses a writable folder that is not inside a Plex library and not a parent of one. The default budget is 200 GiB. The queue is the Safari and Apple TV video-transcode ranking: above 1080p first, then watch count. One ffmpeg runs at a time, at idle priority, from 1:00 a.m. to 6:00 a.m. A partial file is not played, and the same title continues the next night. A finished copy is preferred over a live transcode. Settings → Playback shows the queue, the space used, and a way to remove a copy. This is not a release |
| 2026-11-22 | **Prepare the film while the preroll plays, then show an honest warm-up when it is not ready.** ENG-015 and EXP-018 are accepted and not started. They follow the playback-start fixes already underway: one title's transcode-start timeout must not open the shared circuit, a playlist waits while ffmpeg is starting, and a session can say preparing, ready, or failed. ENG-015 is the server session during the preroll. EXP-018 is the lines file and the step names first, then the web screen. Further copy work stays after that. This is not a release |
| 2026-11-24 | **The browser can install Projectionist.** The manifest, a shell worker that does not store API responses, art, or media, a quiet Install entry, media keys, and the player shortcuts are on main. Push waits on NAT-006. EXP-019 is done (pull request 309, `a0d72b62`). This is not in production 1.45.5 |
| 2026-11-24 | **The web lists rooms, Play in… starts a film on one of them, and the remote follows that session.** SES-008 is done (pull request 311, `b2d3b226`). This is not in production 1.45.5 |
| 2026-11-24 | **The film prepares during the preroll, and the web warm-up screen is on main.** ENG-015 and EXP-018 landed in pull request 298 (`54649269`). The slowed warm-up fixture is still ahead. This is not in production 1.45.5 |
| 2026-11-24 | **The public hostname will rely on household sign-in.** SEC-017 through SEC-026 are accepted, continuing the existing SEC series. SEC-017 through SEC-022 are the gate. The extra login in front of the hostname stays until the person removes it. Edge rules are not applied in this pass. SEC-017 through SEC-024 are on main. SEC-025 is in this change and is not a release |

## Superseded review rows (carry-forward)

| Review ID | Replaced by |
|-----------|-------------|
| PRD-022 | SES-002 / SES-003 (Projectionist screens). Plex-as-screen kind can return later behind the same session API |
| PRD-024 (in part) | Engine attribution (ENG-003). Native-Plex “likely” tier remains GRO-010 |

## Folders

- [`inbox/`](inbox/) — drop new material here
- [`accepted/`](accepted/) — processed drops with their notes
- [`outbox/`](outbox/) — handoffs to client repositories
