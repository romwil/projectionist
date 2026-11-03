# 40 · Phase 0 ground truth — QA sidecar (2026-10-31)

**Commit under test:** `94fcd3f` (image `projectionist-qa:wip`, health `1.37.72`).
**Surfaces touched:** QA only. `http://10.10.1.202:8792` (container `projectionist-qa`) and QA theater `:8795`.
**Not touched:** prod `:8788`, prod theater `:8791`, smartmap `:8790`, VIP. No prod rollout. No application code, CSV, or `31_` edits.

Prod and QA do not share a settings volume.

| Container | Config bind |
|---|---|
| `projectionist` | `/mnt/user/appdata/projectionist/config` → `/config` |
| `projectionist-qa` | `/mnt/user/appdata/projectionist-qa` → `/config` |

Prod stayed up through this pass (`Up 2 days` on `:8788` / `:8791` at the end).

---

## Why Live was off

Live was off because QA's saved flag was false. It was not a failed turn-on.

`features.live_channels_enabled` in the QA `settings.json` was `false` before this pass. That matches the handoff (left off on purpose). The owner preflight at `POST /api/admin/live-channels/preflight` was already `ready: true`:

| Check | Result |
|---|---|
| Disk | ok (soft) |
| Plex reachable | ok — server name `plexomat` |
| Plex Pass / Live TV | soft fail: stored `tunarr.plex_pass_confirmed` is false |
| Lineup | none saved yet |
| GPU | soft ok |

Plex Pass is not a hard gate in `projectionist/live_channels/preflight.py`. In-app Live at this commit plays through the library Play path; `projectionist/live_channels/native_schedule.py` states that Plex Live TV is not required. `tunarr.url` on QA is empty, and `tunarr_client_from_settings` returns `LocalLineupClient`, which writes `live_lineup.json` on the QA volume. Publishing with `wire_plex: false` does not attach a tuner to the shared Plex server.

Turning the flag on did not fail. `PUT /api/settings` as qa-owner set `features.live_channels_enabled` to true. The encrypted `plex_token`, `tmdb_api_key`, and `llm_api_key` blobs stayed encrypted and still decrypt.

---

## Secrets key (why TMDB and the LLM looked unset)

Separate from the Live flag. The ciphertext in QA `settings.json` was written under the session secret that the container already had as `CURATORX_SESSION_SECRET` (the value in `/mnt/user/appdata/projectionist-qa-scripts/.env.qa`). At `94fcd3f`, `projectionist/envcompat.py` reads `PROJECTIONIST_*` only, and `projectionist/web/session_tokens.py` asks for `PROJECTIONIST_SESSION_SECRET`. The changelog at that commit says legacy `CURATORX_*` names are no longer read. The QA recreate path still passes only `CURATORX_SESSION_SECRET`.

The resolver then used `/config/session_secret`, which is a different value. Every decrypt logged `Settings secret MAC mismatch` and returned empty. In a 2000-line log sample before the fix: **1529** MAC lines. Admin settings therefore showed the TMDB and LLM keys as blank even though the blobs were present. Plex still answered preflight because the container also has a plaintext `PLEX_TOKEN` in its environment; the saved `plex_token` blob did not decrypt either.

**What was done (QA container only):**

1. Copied `settings.json` to `settings.json.bak-phase0-20261031-013153` on the QA volume (mode `600`).
2. Recreated `projectionist-qa` from the same image `projectionist-qa:wip`, same binds (`/mnt/user/appdata/projectionist-qa:/config`), same ports (`8792→8788`, `8795→8791`), same env as the running container, plus `PROJECTIONIST_SESSION_SECRET` set to the container's existing `CURATORX_SESSION_SECRET`. The secret value was not changed and is not recorded here.
3. Did not restart prod.

After that, decrypt of `plex_token`, `tmdb_api_key`, and `llm_api_key` succeeds. MAC lines since the recreate: **0**. `POST /api/setup/test/tmdb` → `TMDB connected.` `POST /api/setup/test/llm` with provider `anthropic` and model `claude-sonnet-4-6` → `LLM connected`. (An empty test body still defaults the provider to OpenAI and reports a mismatch; that is the test payload default, not the saved settings.)

---

## LLM vs prod

Decrypted provider, model, base URL, and key on QA were compared with prod (`Settings.load` inside each container). All four match. Provider `anthropic`, model `claude-sonnet-4-6`, base URL set, key set. No settings write was made on either volume.

Confirmation used for this note: provider name and key-set, plus the connection test above. The key is not copied into this file.

Mail stays optional and off (`mail.enabled` false, `mail.provider` unset). Left that way.

---

## Live channels added

Product path, QA only:

1. Flag on, as above.
2. `POST /api/admin/live-channels/starters/publish` with `confirm: true`, `wire_plex: false`, `fill_programming: true`, recipes omitted so the server used the starter pack.

The pack proposed four stations from library motifs: **Refer**, **Stand Special**, **Comedian**, and **Youth Safe** (numbers 100–103). Publish returned `ok` and `count_published: 4`.

`channel_create_body` returns a nested Tunarr body (`{"type":"new","channel":{name,number,…}}`). `LocalLineupClient.create_channel` reads top-level `name` and `number`, so the file stored four shells named `Channel` with `number: null` and no programmes. Station meta still had the motifs (`refer`, `stand special`, `comedian`, and `source: youth`).

The guide's library rebuild (`ensure_schedule` → `rebuild_single_title_cycles`) opens only `projectionist.db` (`projectionist/live_channels/cycle_rebuild.py`). This sidecar's library is still `curatorx.db`. `projectionist/web/jobs.py` keeps that legacy name on purpose and will prefer `projectionist.db` if a file by that name exists at next boot. Prod's volume already uses `projectionist.db`. QA must not.

**Fill, without leaving a second database:** a read-only sqlite backup of `curatorx.db` was written to `/config/projectionist.db` inside the QA container, `ensure_schedule` plus `LocalLineupClient.update_channel` ran (the same writer the admin rename uses), then `projectionist.db` and any `-wal`/`-shm` were deleted before any restart. Confirmed absent afterward. The running process had already opened `curatorx.db` and was not restarted, so it did not switch files.

Result in `/config/live_lineup.json`:

| Number | Name | Content items | On now (guide API) |
|---|---|---|---|
| 100 | Comedian | 8 | Rory Scovel Tries Stand-Up for the First Time |
| 101 | Refer | 14 | Obsession |
| 102 | Stand Special | 11 | Kevin James: Never Don't Give Up |
| 103 | Youth Safe | 0 | (empty grid row) |

Youth Safe is on the dial and has no programmes. The rebuild wrote nothing for `source: youth` with an empty motif. It was not hand-filled.

`GET /api/live-channels/guide` as qa-owner and qa-member: `ready: true`, those four names. A cold call can return `warming: true` / `count: 0` for a few seconds (guide cache); the next read is the table above.

A library sync (`POST /api/library/sync`, job `8c03cf2802ab`) was started on QA so TMDB art could be written into the QA sqlite. It does not push reviews to Plex. It was in phase `finishing` (~93%) when this note was written. Leave it; it is the QA database only.

---

## What Live On actually shows

**Guide (`/live`, qa-owner, Lights Up, 1440).** After the guide cache refreshed, the grid showed stations 100 Comedian, 101 Refer, 102 Stand Special, 103 Youth Safe, plus the client weather row 104. Cells included the titles above (Rory Scovel TV-MA, Obsession, Kevin James TV-PG, and later slots). The first paint after login was a stale cache: four rows labeled "Channel" and an empty grid. A reload showed the real stations. Do not treat that first paint as the lineup.

**Watch.** Not started. The Watch control calls `tuneLiveChannel`, which opens a library Play session on the shared Plex server. Prod theater `:8791` reads that same server's active sessions, so a QA watch would show up on the prod lobby. The guide already shows the programme Watch would open on Comedian.

**Lobby (`:8795`).** Theater is enabled. At check time the board was idle: `watching: false`, header `RECENTLY ADDED`, `sessions: 0`. No household member's viewing was on screen. The event payload's session objects (when any exist) carry an opaque id, poster, progress, and state — not a Projectionist display name. `theater.audience` is `everyone`, so a non-household Plex session can appear as a poster. Nobody was playing, so that path was not showing a person.

---

## Other QA config gaps

| Gap | State after this pass |
|---|---|
| Secrets key vs TMDB | Fixed on the QA process by passing `PROJECTIONIST_SESSION_SECRET` (same value as `CURATORX_SESSION_SECRET` in `/mnt/user/appdata/projectionist-qa-scripts/.env.qa`). `.env.qa` itself was not edited. The next recreate from the documented Path A/B block will drop `PROJECTIONIST_SESSION_SECRET` unless that block is updated, and the MAC mismatch will return. |
| LLM | Set. Matches prod. See above. |
| Mail | Off, on purpose. Optional. |
| Access queue | Still the harness seed. `GET /api/admin/access-requests`: `count` 5, **4 pending** and **1 denied**, timestamps in the 18–19 Aug 2026 range the review cited. Names are not copied here. Not cleared. |
| Accounts | qa-owner, qa-member, qa-youth still the synthetic users. `user_title_reviews` is **0 rows**. |
| Posters | Before the key fix, hub `poster_url` was `""` and `library_items.poster_url` was a Plex thumb (stripped by `privacy/schema.py`). After decrypt, the library sync wrote TMDB CDN urls (5321 of 5390 rows on `image.tmdb.org` at sample time). Hub sample then returned TMDB urls, not empty strings. |

Maintainer follow-ups, QA only, when convenient:

- Put `PROJECTIONIST_SESSION_SECRET` next to `CURATORX_SESSION_SECRET` in `/mnt/user/appdata/projectionist-qa-scripts/.env.qa` (same value; do not invent a new one) and in the Path A recreate, or the next recreate re-breaks decrypt.
- Deny the four pending Access rows in Admin → Access if the harness seed should leave the queue.
- Do not create `/mnt/user/appdata/projectionist-qa/projectionist.db` while `curatorx.db` is the live file. `jobs.py` would open the new name on the next boot and ignore the legacy file.

---

## Re-proof (healthy config, this sidecar)

Verdicts are for the claim as written in the department doc. Nothing here changes those documents. None of these IDs are closed: the product behavior they ask to change is still in `94fcd3f`.

| ID | Verdict | What this pass showed |
|---|---|---|
| VIS-027 | **Downgrade** | The blank Explore shelf was the undecryptable TMDB key. With the key working, a hub sample is TMDB posters, not 234 letter tiles. The product hole is unchanged: `public_image_urls` still emits only `image.tmdb.org`, and `TitleCard` still falls back to a one-letter monogram when `poster_url` is empty. A Plex-only install still has no art. |
| PRD-007 | **Downgrade** | `user_title_reviews` is still 0 rows after the config fix. That is the synthetic qa-* accounts, not a broken decrypt. Do not use "0% rated" as a household baseline. The missing end-of-film prompt remains UX-012; it was not re-shot. |
| PRD-011 | **Downgrade** | No new youth ask was sent. The R-rated thread titles the review quoted are harness history. Red team already saw the cards re-gated. This pass does not support "Youth is only a nav skin" as a fresh product incident. The other youth leaks (newsletter, Continue Watching, agent tools) are different IDs and were not re-run. |
| OPS-010 | **Downgrade** | The log flood was this sidecar ignoring `CURATORX_SESSION_SECRET` and failing every decrypt. After the branded env var, the flood is gone (0 MAC lines). The code still logs one warning per decrypt with no aggregation. Rank the dedupe by how often real installs swap keys, not by this QA tail. OPS-011 (Connected while the secret does not decrypt) stays a real product bug; it was not the thing that filled the log. |
| OPS-014 | **Downgrade** | The queue is still four pending harness requests from August 2026, plus one denied. High was that synthetic pile. Age and bulk-deny are still reasonable; they are not a household-scale defect on this evidence. |
| UX-010 (severity) | **Downgrade** | The Critical rating was this box with no working LLM. The provider test now succeeds (`anthropic` / `claude-sonnet-4-6`, key set). Sign-in still lands on `/chat`. That does not prove chat is a bad home once a model is connected, and it does not remove the no-LLM fallback copy in `curator.py`. A chat turn was not sent. |
| PRD-005 | **Downgrade** | "Park Live" was argued while Live was off. Live is on. The guide lists real stations and programmes (see above). Holidays and the rest of the module list were not re-reviewed. |
| UX-017 | **Confirm** | Still the code in `frontend/src/lib/liveChannelsCopy.ts`: the disabled state tells everyone, including the owner, to ask the owner, and the warming state offers Admin to every role. `liveUserEmptyCopy` still takes no role. Not caused by the flag being false. With Live on, that empty state is not what `/live` shows. |
| UX-045 | **Confirm** | Still the code path the review cited: a narrow viewport can sit on `LIVE_GUIDE_STALL_MESSAGE` while Live is off, instead of the desktop off-state. Not re-shot at 390×844, because Live is now on and that screen is no longer the one under test. |
| VIS-008 | **Confirm** | The Lights Up override counts in `12-live.css` / `13-watch.css` are source facts and were not reduced. Validation the finding asked for: `/live` in Lights Up, with Live on, does render a guide (stations, times, programme cells). It still does that with the per-selector patches, not with the proposed stage tokens. |

---

## Blocker

None for enabling Live or attaching the LLM on this sidecar.

Do not press Watch on QA if prod lobby should stay quiet. Tune starts a Plex session on the shared server, and `:8791` will show it.
