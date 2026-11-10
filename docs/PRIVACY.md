# Privacy & data use

This page explains what Projectionist stores, who can see it, and what leaves the server. It's written for the people who use the app, not only for the owner reading the [security assessment](SECURITY.md). Where the app falls short of what you might expect, this page says so.

Projectionist is **self-hosted**. The household owner chooses where it runs, which AI provider answers chat, and whether people sign in. **There is no Projectionist cloud account, and Projectionist does not phone home.**

The short version:

- **What is stored.** The library catalog, your chats and preferences, your notifications, and the owner's connection settings. All of it lives in one database and one settings file on the owner's server, plus the daily backups described below.
- **What leaves the server.** Your chat goes to the AI provider the owner picked. Search text may go to the owner's embeddings provider. Notifications go to the email or push service the owner set up. Poster images load from public artwork sites. Your Plex token and the owner's settings file do not leave.
- **What you control.** **Settings → My data** lets you download everything Projectionist keeps about you, delete memory notes one at a time, or delete your data while keeping your account. To remove the account itself, ask the owner. **[Getting a copy or leaving](#getting-a-copy-or-leaving)** lists what each choice deletes and what stays.

Jump to: [Household members](#household-members) · [Server owners](#server-owners) · [MCP](#mcp) · [Exposure matrices](#exposure-matrices) · [We do not](#we-do-not)

---

## Who this is for

| Role | How you arrive | What you control |
|------|----------------|------------------|
| **Owner** | Runs the server. With sign-in on, the first owner is made by the owner password in the container settings, by the setup wizard, or by signing in from the browser that turned sign-in on. | Connections, libraries, AI provider, household accounts, mail, backups, MCP keys |
| **Member** | Joins by invite link or by asking to join on the sign-in page | Your own profile, chats, watchlist, lists, ratings, and notification choices |
| **Youth** | A member account the owner marked **Youth mode** | Same as a member, with content limits |

The default install has **no sign-in**. Anyone who can reach the app on the network acts as the owner. With sign-in on, each person's chats and preferences are kept apart. It is still one household on one server, not a public service.

---

## From the household member's perspective

### How you sign in

The owner decides which sign-in methods the household uses. Each stores a little about you:

- **Sign in with Plex.** Your Plex display name, Plex account number, and, when Plex shares them, your email and avatar link. Projectionist also keeps an encrypted copy of your Plex account token so it can sync your Plex watchlist. That token is never shown in the app or handed to other tools.
- **Single sign-on (SSO).** Your account number at the SSO provider, plus the name and email the provider shares.
- **Username and password.** Your username and a one-way scrambled form of your password. Projectionist can't read your password back.

Every account also stores a role (owner, member, or guest), whether **Youth mode** is on, your **preferred name** (what the curator calls you), and an optional uploaded profile picture.

### Asking to join

If you ask to join from the sign-in page, Projectionist keeps the name, email, and message you typed so the owner can approve or decline. The request stays on the server after the owner decides.

If the owner invites you by email, Projectionist sends the invite through the household's mail service and keeps your email address on the invite.

### What is yours alone

With sign-in on, these belong to your account. Other members can't open them:

- Chat threads and messages
- Private memory notes: goals, things you plan to watch, follow-ups
- Taste and preference notes the curator keeps for you
- Your watchlist, lists, ratings, and reviews
- Your inbox: newsletters, nudges, whispers, Year in Review, and titles someone recommended to you
- Plex viewing that Plex recorded under your own Plex account
- Actions you started that still need confirming

A list stays private until you **publish** it to the household.

### What the owner can see

Your chats are private from other members. They are **not** private from the server itself:

- **Anyone with the server's files can read everything**, including your chats and memory. That includes the owner's backups.
- **Youth accounts.** Curator memory is **off by default** for Youth accounts: the curator neither reads nor saves it unless the owner turns Youth memory on. When it is on, the owner can read notes saved since that account entered Youth mode in **Admin → Youth review**. Turning **Youth mode** on for an existing account needs the owner to confirm, sends that person an inbox notice, and is written to the security log. It never opens what the curator remembered before. Your profile shows a **Youth** badge while it is on.
- **The household list** the owner sees includes your notification email, your saved weather place, your Plex account number, and when you last signed in.
- **Activity.** **Admin → Overview** shows household totals. The owner's tools can also list individual chat turns and plays with the account that made them. Those rows never include what you typed.
- **Likely picks.** Overview also shows a separate **likely** count: Plex plays of a title Projectionist suggested to that same person in the 7 days before. It never counts as a confirmed play from a pick. Each row is kept 90 days, is in **Download my data**, and is removed by **Delete my data**.
- **What the owner did.** **Settings → My data** lists the changes the owner made to your account (role, account on or off, Youth mode, auto-confirm, password reset) and each time they opened the Youth memory review. It shows no note text.

### Inbox, newsletters, and alerts

Projectionist can write to you: a weekly newsletter, the occasional "you have to see this" nudge, a whisper about something new, and a Year in Review. Each lands in your **Inbox**.

Each email has a one-click unsubscribe link. It turns off only that kind of email for you, and it stops working after **Delete my data**.

**How it works.** A newsletter, nudge, or whisper names a title and one reason it connects to something **you** finished. Only your own viewing counts. If you haven't watched enough yet, you get a quieter note or none. Someone else's viewing never stands in.

Choose what reaches you in **Settings → Notifications**:

- **Email.** Sent through the mail service the owner set up. Depending on their choice, that is their own mail server or Resend, an email delivery company.
- **Apprise** (push to apps like Discord or Telegram). Only the owner adds destinations. If you turn it on, your notes go to the household destinations the owner chose, and other people may read those.

### What the curator remembers

The curator keeps two kinds of memory:

- **Your private memory.** Preferences, stated goals, watch intentions, and follow-ups for your account only.
- **Shared knowledge** about titles, people, and companies it looked up. This isn't tied to any account, so everyone's curator can reuse it. It is saved as the AI wrote it. If you mention something personal while it researches a title, that detail could end up in shared knowledge.

### Getting a copy or leaving

Open **Settings → My data**. Everything there acts on your account only. No one else can download or delete your data from that page, and you can't reach anyone else's.

- **What the curator remembers.** Each private memory note, with a **Delete** button. A deleted note is gone, not hidden.
- **Download my data.** One file with everything Projectionist keeps about you: profile, chats with every message, memory, watchlist, lists, ratings and reviews, inbox, Plex viewing, badges, Year in Review, and the rest. Passwords and sign-in tokens are left out. A readable version includes your chat messages too.
- **Delete my data.** Removes all of that except your account, so you can keep signing in and start fresh. You type a short phrase to confirm.
- **To leave the household**, ask the owner to remove your account in **Admin → Members**. That deletes your profile and picture too.

**What stays after removal:**

- Problems you reported about a title, your request to join, and the invite you joined with. Your name, email, and account link are removed; the rest stays as the household's record.
- Curator voices you shared with the household, without your name.
- Security log entries about your account, such as sign-ins and the removal itself. They hold an account number, not your chats.
- Shared knowledge the curator saved about titles and people.
- **Backups.** The daily backups made before you left still hold your data until they roll off after seven days. If the owner restores one of them, Projectionist removes your data again before the app starts, so you don't come back. Backups the owner downloaded and keeps somewhere else are out of Projectionist's reach.
- Copies the AI provider kept under its own terms.

### What the AI provider receives

Chat uses the AI provider the owner connected: OpenAI, Anthropic, OpenRouter, or a model on the owner's own machine such as Ollama. It receives:

- Your messages and the conversation so far
- Your private memory and preference notes, so the curator knows you
- What the curator looks up to answer: titles, library matches, and your watch signals

**Youth accounts are different.** Youth chats never use the household model. The owner picks one of two options: **none** (the default), where no model is called and the chat explains why, or **a model on the home network**, such as Ollama or LM Studio. If that local model isn't set up, or its address isn't on the home network, Youth chat sends nothing and says so.

**Search.** When you search by meaning ("lonely space movies"), your search words may go to the owner's embeddings provider, which can be a different company from the chat provider.

It does not receive the Plex server token, the owner's settings file, or other members' chats. If the owner runs a local model, chat stays on the home network.

### Voice mode

If you turn on voice input:

- Your **browser or device** handles the microphone. Some browsers send speech to a cloud service to turn it into text.
- Projectionist never receives or stores raw audio. It gets the text, which then follows the normal chat path.
- **Speak replies** uses your browser's built-in voice.

### Weather Channel (Live)

When someone opens the **Weather Channel** from Live:

| Signal | What leaves the server | When |
|--------|------------------------|------|
| **Place search** | The text you type (ZIP, city and state, or city and country) to Open-Meteo (`geocoding-api.open-meteo.com`) | You search for a place |
| **Forecast, hourly, regional cities** | The coordinates of the place, and of nearby cities from a list built into Projectionist, to Open-Meteo (`api.open-meteo.com`) | Every 30 minutes while someone watches |
| **Records, frost, first snow** | The coordinates to the Open-Meteo archive (`archive-api.open-meteo.com`) | Once a day while someone watches |
| **UV, air quality, pollen** | The coordinates to Open-Meteo air quality (`air-quality-api.open-meteo.com`) | Every 30 minutes while someone watches |
| **Alerts (US only)** | The coordinates to the National Weather Service (`api.weather.gov`) | Every 5 minutes while someone watches a US place |
| **Radar and satellite** | A map box around the coordinates to Iowa Environmental Mesonet (`mesonet.agron.iastate.edu`) and NOAA (`cdn.star.nesdis.noaa.gov`) for US places, or to RainViewer (`api.rainviewer.com`, `tilecache.rainviewer.com`) elsewhere | Every 10 minutes while someone watches |
| **Webcams** | The coordinates to Windy (`api.windy.com`, images from `imgproxy.windy.com`) | Only when the owner adds a Windy key |
| **Headlines** | The city name (local search) or the country (front page) to Google News (`news.google.com`). The world feed from BBC (`feeds.bbci.co.uk`) gets nothing about the place. | Every 30 minutes while someone watches |
| **Voiceover scripts** | The weather data and the place name to the household model (the LLM in Configuration) | When the data changes, if a model is set |
| **Headline recap** | Only the fetched headline titles and their sources to the household model | When headlines change, if a model is set |
| **Voice** | Nothing. Speech is rendered on the server by a local voice model. | Weather narration is on |
| **Voice model** | A one-time download of the voice files from GitHub (`github.com`, Kokoro) or Hugging Face (`huggingface.co`, Piper). Both redirect to their file CDNs. | The owner turns on Weather narration |
| **Music** | Nothing. It plays from the owner's music folder. | A music folder is set |

Weather services get coordinates and place names, never who is watching. Your browser loads maps, webcam stills, and voice audio from Projectionist, not from those services. One cache serves everyone watching the same place. Nothing is fetched for a place nobody is watching, and nothing at all while the channel is off. If narration is off or the voice fails, the channel shows captions instead; it does not use your browser's voice.

A place you save is stored on your profile and reused, so it isn't looked up again.

### Subtitles

Subtitle enrichment, the owner's **Backfill subtitles**, Play, or Live may download a caption file from OpenSubtitles and keep it on the server; the lookup sends a file hash or an IMDB id, and there is no OpenSubtitles call when the key is empty.

### Watchlist and your Plex account

Watchlist pins are yours. When watchlist sync with Plex is on, Projectionist uses the encrypted Plex account token from your sign-in to read and update your Plex watchlist. If that token is missing, it asks you to sign in again. It never uses the household's server token in its place.

### Lists

Lists you make are stored on the server under your account. A list is **private** until you **publish** it to the household. Publishing to Plex uses your own Plex account. If Plex doesn't accept it, Projectionist says so instead of pretending.

### People on the Plex server who never joined

Plex tells Projectionist about plays from every account on the Plex server, including friends and family who never joined Projectionist. Projectionist keeps those plays apart, under that Plex account's name. With sign-in on, they never become anyone's "You watched" line or newsletter reason. They are not deleted automatically yet.

### What other members cannot see

- Your chats, memory, and message feedback
- Actions you started that still need confirming
- Your watchlist, ratings, and reviews as your personal record
- Your Plex viewing
- Owner-only Admin: connection settings, keys, household accounts

### MCP and members

Members don't control MCP keys. MCP lets the owner connect other AI apps to Projectionist. The owner's choices about that are described under [MCP](#mcp).

---

## From the server owner's perspective

### Fleet credentials

Stored under the data directory (typically `/config`, in `settings.json` and the SQLite database):

- Plex server URL and **server** token
- Radarr, Sonarr, Seerr, TMDB, TVDB, Fanart, Tautulli, OpenSubtitles, and ACRCloud keys as configured
- LLM and embeddings provider URLs, models, and API keys
- Mail settings (SMTP or Resend) and household Apprise destinations
- Webhook secret, session secret, feature flags

Only the owner sees these, in **Admin → Configuration**. UI-saved keys in `settings.json` are encrypted at rest when `PROJECTIONIST_SECRETS_KEY` (or the generated key file) is present. Back that key up with `/config`, or the encrypted values can't be read after a restore.

### Backups

**How it works.** The **Household backup** scheduled task writes `DATA_DIR/backups/projectionist-auto-<timestamp>.zip` once a day. Each file holds `settings.json` and a consistent copy of the database, and only the newest seven are kept. Nothing is uploaded. **Admin → Overview → Full household backup** downloads the same kind of file on demand, and each download is written to the security log.

A backup holds **everyone's** chats, memory, and viewing, plus your encrypted keys. Store it like a password vault.

```bash
# List on-box snapshots (Docker)
docker exec projectionist python -m projectionist.backups list

# Restore: stop the app first, then run the restore in a one-off container
docker stop projectionist
docker run --rm -v /mnt/user/appdata/projectionist/config:/config \
  romwil/projectionist:latest python -m projectionist.backups restore \
  --from /config/backups/projectionist-auto-YYYYMMDDTHHMMSSZ.zip --yes
docker start projectionist
```

Restore checks the snapshot before touching anything. **It never brings back an account you removed, or data a member deleted.** Every removal and **Delete my data** is recorded in `DATA_DIR/privacy-erasures.json` (the account id and a time, nothing else). Restore re-applies that list to the snapshot copy, then compacts it, before the copy goes live. If that file can't be read, restore refuses. Restore from the same data folder; a snapshot restored into an empty folder has no list to apply. It moves the current database and `settings.json` to `backups/pre-restore-<timestamp>/` rather than deleting them. Those set-aside folders are not pruned, so remove them yourself once the restore looks right. **Admin → Overview → Needs attention** warns when the backup task is off or the newest snapshot is more than three days old.

**Honest limit:** the snapshot lives on the same disk as the data. Copy `DATA_DIR/backups` somewhere else if you need protection from a failed disk.

### Export and removal, exactly

Members do this from **Settings → My data**. The same routes work with a session cookie. Every route acts on the signed-in account only; there is no parameter that names another account, and an owner can't export or purge someone else from the app.

```bash
# Export the signed-in account (JSON; add ?format=markdown for a readable copy with messages)
curl -s -b 'curatorx_session=YOUR_SESSION' \
  http://localhost:8788/api/me/memory > my-projectionist-export.json

# Delete my data: everything below marked "Delete my data", keeping the account
curl -s -b 'curatorx_session=YOUR_SESSION' -X POST \
  -H 'Content-Type: application/json' -d '{"confirm": "delete my data"}' \
  http://localhost:8788/api/me/data/erase

# Older, narrower purge: memory, chats, saved pages, preferences, Plex viewing, activity counts
curl -s -b 'curatorx_session=YOUR_SESSION' -X DELETE \
  http://localhost:8788/api/me/memory
```

**How it works.** One list in `projectionist/privacy/registry.py` names every table that holds data about an account, and says whether it is exported, removed by **Delete my data**, and deleted, stripped of the name, or kept when the account is removed. Export, both purges, account removal, restore, and the table below all read that list. A test fails when a new column that looks like an account link (`user_id`, `email`, and similar) is not on it, and another fails if this table drifts from it.

Account removal runs as one database transaction, so a failure part-way leaves the account whole rather than half-deleted. Deletes use SQLite's `secure_delete`, and the write-ahead log is truncated afterwards, so deleted chat text isn't left readable in the database files. The uploaded profile picture is deleted from disk.

<!-- privacy-registry:begin (generated by python -m projectionist.privacy.registry) -->
| Data | In your download | Delete my data | Removing the account | Table |
|------|:----------------:|:--------------:|:--------------------:|-------|
| Your request to join (name, email, message) | Yes | No | Name removed | `access_requests` |
| Join requests you approved or declined (who decided) | No | No | Name removed | `access_requests` |
| The invite you joined with (email, expected Plex or SSO account) | Yes | No | Name removed | `invites` |
| Invites you sent (who sent them) | No | No | Name removed | `invites` |
| Problems you reported about a title (your name is removed, the note stays) | Yes | No | Name removed | `media_issues` |
| Notes other members got from you (your name is removed) | No | No | Name removed | `user_notifications` |
| Curator voices you shared with the household (your name is removed) | Yes | No | Name removed | `persona_templates` |
| Library clean-up actions you ran (who ran them) | No | No | Name removed | `grooming_action_log` |
| Temporary Plex collections you made (who made them) | No | No | Name removed | `ephemeral_plex_collections` |
| Owner checklist ticks (who ticked them) | No | No | Name removed | `owner_checklist_marks` |
| Security log entries about your account | No | No | **Kept** | `security_audit_log` |
| Plex viewing: finished titles | Yes | Yes | Deleted | `watch_completions` |
| Plex viewing: session links | No | Yes | Deleted | `watch_session_events` |
| Plex viewing: sessions | Yes | Yes | Deleted | `watch_sessions` |
| Plex viewing: play, pause, and stop events | Yes | Yes | Deleted | `watch_events` |
| Picks you probably watched in Plex within 7 days (likely, not confirmed) | Yes | Yes | Deleted | `pick_watched_likely` |
| Your linked Plex account on the Plex server | Yes | Yes | Deleted | `watch_source_identities` |
| Thumbs up or down on curator replies | Yes | Yes | Deleted | `message_feedback` |
| Chat messages | Yes | Yes | Deleted | `chat_messages` |
| Chat threads | Yes | Yes | Deleted | `chat_sessions` |
| Saved library pages | Yes | Yes | Deleted | `saved_library_pages` |
| Private memory notes | Yes | Yes | Deleted | `user_memory_notes` |
| Preference notes | Yes | Yes | Deleted | `preference_facts` |
| Activity counts (chat turns and plays, never your words) | Yes | Yes | Deleted | `system_telemetry_stream` |
| Memory audit trail (when notes were added, exported, or purged) | Yes | Yes | Deleted | `user_memory_events` |
| Watchlist | Yes | Yes | Deleted | `watchlist_pins` |
| Titles on your lists | Yes | Yes | Deleted | `curated_list_items` |
| Lists you made, private or published | Yes | Yes | Deleted | `curated_lists` |
| Course progress | Yes | Yes | Deleted | `user_course_progress` |
| Course sessions | Yes | Yes | Deleted | `user_syllabus_sessions` |
| Ratings and written reviews | Yes | Yes | Deleted | `user_title_reviews` |
| Pending rating prompts | Yes | Yes | Deleted | `rating_prompt_queue` |
| Actions you started that were never confirmed | Yes | Yes | Deleted | `pending_actions` |
| Inbox: newsletters, nudges, whispers, and alerts | Yes | Yes | Deleted | `user_notifications` |
| Titles someone recommended to you, and ones you recommended | Yes | Yes | Deleted | `user_recommendations` |
| Taste profile | Yes | Yes | Deleted | `user_taste_profile` |
| Weekly picks rail | Yes | Yes | Deleted | `user_weekly_rails` |
| Badges | Yes | Yes | Deleted | `user_badges` |
| Streaks | Yes | Yes | Deleted | `user_streaks` |
| Challenge progress | Yes | Yes | Deleted | `user_challenge_progress` |
| Year in Review | Yes | Yes | Deleted | `year_in_review_snapshots` |
| AI usage records (token counts, no words) | Yes | Yes | Deleted | `llm_usage` |
| Private curator voices you made | Yes | Yes | Deleted | `persona_templates` |
| The key that makes your email unsubscribe links work | No | Yes | Deleted | `mail_unsubscribe_nonces` |
| Your profile: name, email, sign-in links, and settings | Yes | No | Deleted | `users` |
| Uploaded profile picture | No | No | Deleted | `DATA_DIR/avatars/<account>.*` |
<!-- privacy-registry:end -->

**Youth review.** `GET /api/users/{id}/memory` returns memory only for accounts flagged Youth, and only notes saved since that account's Youth mode started. **Admin → Youth review** shows the same.

### Plex watch evidence health

Every 15 minutes, the **Plex Watch History** scheduled task asks Plex for a bounded page of played history. Projectionist keeps normalized movie and episode identifiers, the stable Plex account id, event time, optional progress and duration, and a fingerprint. It does **not** keep the raw response, Plex token, client IP, or transcode details.

Webhooks add pause, stop, and played signals as they happen. Active playback is sampled once a minute while sessions exist and every five minutes while idle. For those samples Projectionist keeps a one-way client hash, not the device name, address, or raw payload. Marking a title watched or unwatched records a manual correction only for an exactly linked Plex account.

**Exact account mapping.** An event belongs to a household member only when Plex's stable account id matches that member's linked Plex id. Display names are never used to guess. Events from accounts that never joined stay **unmapped**, stored with the Plex account's display name in `watch_source_identities`. Unmapped events never feed a member's newsletter, nudge, whisper, or "You watched" line. They are not pruned yet.

A completion is `certain` when progress crosses 90%, `likely` when strong terminal evidence reconstructs that, or `plex_event_only` when Plex reported played without progress detail. These are evidence labels, not proof of who was watching.

```bash
# Run an ingest now (otherwise every 15 minutes while idle)
curl -s -X POST \
  'http://localhost:8788/api/admin/scheduled-tasks/watch_history_ingest/run?wait=true' \
  | python3 -m json.tool

# Source health: capability, cursor age, mapped/unmapped counts, last error category
curl -s http://localhost:8788/api/admin/watch-tracker/status | python3 -m json.tool
```

The status response returns no titles, rating keys, account ids, or event rows. With sign-in on, use the owner session; members get `403 Forbidden`.

### Notifications and mail

Newsletters, nudges, whispers, and Year in Review are built per member from that member's own mapped evidence. A member who wants email or Apprise also needs it on in **Settings → Notifications**.

- **Email** goes through SMTP or Resend as set in **Admin → Mail**. Invites with an email address are mailed the same way.
- **Apprise** goes to the household destinations set in **Admin → Mail**. Only the owner can add per-account destinations; members can't, so a member can't make the server call an address they chose.
- **Full MCP** includes a newsletter preview tool that can show any member's letter. See [MCP](#mcp).

### Investigate episodes

When the owner runs **Admin → Libraries → Investigate episodes**, Projectionist may send the following **only for that job**:

| Signal | What leaves the LAN | When |
|--------|---------------------|------|
| **Vision stills** | Up to five JPEG frames from the episode file to the chat LLM | Vision is on and the model accepts images |
| **Identify (ACRCloud)** | A short (~12 s) audio clip to `identify-*.acrcloud.com` | Identify keys are configured |
| **OpenSubtitles hash** | A file hash, not the video, to look up a subtitle match | `PROJECTIONIST_OPENSUBTITLES_API_KEY` (or the UI key) is set |

Stills and clips are cached under the data directory for the current job so you can review them. Older job folders are removed when a new job starts.

### Activity counts and the security log

These records stay on this server so you can run it well. None is sent anywhere.

- **Activity counts** (`system_telemetry_stream`). A chat turn records its outcome, card and tool counts, and timing, never the words. A play started in Projectionist records the title and, only when the member pressed Play on a curator card or a household recommendation, which pick it came from. Opening the Household pulse records that an owner looked, with the account id and nothing else. Rows are kept 90 days. **Admin → Overview → Household pulse** shows weekly household totals: plays from a pick, failed and slow chat replies, AI spend, and how many members have been quiet for four weeks. It never shows who did what. `GET /api/admin/telemetry/events` returns the raw rows, including the account id.
- **Server timings** (in memory only). How long recent requests took and how many database writes are waiting. They are never written to the database or sent anywhere, and they reset when the server restarts. Owners read them at `GET /api/admin/runtime`; the server also logs one line a minute with the same numbers.
- **Security log** (`security_audit_log`). Sign-ins, failed sign-ins, password changes and resets, invites, role and Youth changes, settings saves, secret reveals, MCP key changes, and backup downloads. Settings saves list setting **names**, never values. Only owners can read it (**Admin → Health → Security log**). It keeps the newest 20,000 rows and is not removed with an account.

### Images

Member-facing library JSON and privacy MCP prefer TMDB poster and backdrop URLs (`image.tmdb.org`), which carry no Plex token or LAN hostname. Plex thumbnail URLs that embed `X-Plex-Token` stay inside the owner's in-app views.

### Browser-side third parties

Fonts and icons are self-hosted. A signed-in browser contacts only the origins you turned on by configuring a provider:

| Origin | When | Why |
|---|---|---|
| `image.tmdb.org`, `artworks.thetvdb.com`, `assets.fanart.tv` | A poster or backdrop loads | Artwork CDNs; no Plex token or LAN hostname in the URL |
| `www.themoviedb.org` | Rematch studio / Repair the miss links a title's TMDB page | Public TMDB title page; no API key leaves the browser |
| `www.youtube.com` / `www.youtube-nocookie.com` | Someone opens a trailer that only has a YouTube source | Trailer playback |

### Webhooks, logs, and network

- Plex webhooks require the configured webhook secret.
- Application logs can include titles, job phases, and user ids, but not API keys. Treat log access as sensitive.
- Don't expose port `8788` to the internet. Keep Projectionist on a trusted network or behind an authenticated reverse proxy. See [SECURITY.md](SECURITY.md).

---

## MCP (Model Context Protocol)

MCP lets external AI apps query your library. The key a client presents decides what it gets, not a mode the client claims.

### Privacy mode (default for sharing)

- **Tools:** catalog search and browse, facets, counts, TV progress filters, and TMDB discovery.
- **Schema:** titles, years, genres, cast, short overviews, `tmdb_id` / `tvdb_id`, coarse watch state, and TMDB image URLs.
- **Never includes:** Plex or LAN media URLs, `rating_key`, machine identifiers, household identities, email or avatars, file sizes, raw view times, `in_radarr` / `in_sonarr`, paths, secrets, or write tools.

### Full mode (trusted LAN automation)

- **Tools:** the privacy tools with internal fields, taste and watch-based helpers (`analyze_watch_patterns`, `recommend_hidden_gems`, purge candidates, watchlist pins), confirm-gated Radarr/Sonarr/Seerr proposals, and a **weekly newsletter preview for any member**. That preview includes the member's name and watch-based reasons, and it reaches whatever AI provider the client uses.
- **Never includes:** live `X-Plex-Token` URLs, webhook, session, LLM, or *arr keys, or `settings.json`.

| Key | Env | Purpose |
|-----|-----|---------|
| Privacy MCP key | `PROJECTIONIST_MCP_API_KEY` | Public-content catalog |
| Full MCP key | `PROJECTIONIST_MCP_FULL_API_KEY` | Internal fields, household taste, confirm-gated proposals |

Rotate keys in **Admin → Advanced**; the full value shows once after you regenerate. Don't reuse one string for both. Stdio full mode requires the full key in the environment. Operator guide: [MCP.md](MCP.md).

---

## Exposure matrices

Legend: **Y** = may see or receive · **—** = not exposed · **\*** = the provider the owner chose

| Data | Stored where | Member | Owner | Privacy MCP | Full MCP | AI provider |
|------|--------------|--------|-------|-------------|----------|-------------|
| Title metadata, facets, short overviews | Library index | Y | Y | Y | Y | Y\* |
| TMDB poster / backdrop URLs | Library index | Y | Y | Y | Y | Y\* |
| Plex tokenized poster URLs | Library index | — | In-app only | — | — | — |
| `tmdb_id` / `tvdb_id` | Library index | Y | Y | Y | Y | Y\* |
| Plex `rating_key`, file size, `in_radarr` / `in_sonarr` | Library index | — | Y | — | Y | Y\* (tools) |
| Chats and messages | Database | Own | Server files and backups | — | — | Own chat\* |
| Private memory and preference facts | Database | Own | Youth accounts since Youth mode started; server files and backups | — | — | Own chat\* (Youth: local model or none) |
| Mapped watch evidence | Database | Own | Server files; aggregate health | — | Household taste tools | Own chat\* |
| Unmapped Plex viewing | Database | — | Server files; aggregate counts | — | — | — |
| Newsletter, nudge, whisper text | Database | Own | Server files | — | Newsletter preview | — |
| Activity counts | Database | — | Totals, plus raw rows by API | — | — | — |
| Security log | Database | — | Y | — | — | — |
| Watchlist pins | Database | Own | Own | — | Pins tool | Own chat\* |
| Ratings and reviews | Database | Own | Server files | — | — | Own chat\* |
| Published lists | Database | Household | Household | — | — | Own chat\* |
| Profile (name, email, weather place, last sign-in) | Database | Own | Household list | — | — | Name only |
| Encrypted Plex account token | Database | — | — | — | — | — |
| Access requests and invite emails | Database | — | Y | — | — | — |
| Plex server token, *arr / LLM / mail keys | `settings.json` | — | Admin | — | — | — |
| MCP keys | Env / settings | — | Admin | Auth only | Auth only | — |
| Search-by-meaning text | Sent, not stored | Own | — | — | — | Embeddings provider\* |
| Backups | `DATA_DIR/backups` and downloads | — | Everything above | — | — | — |

---

## We do not

- Sell household data, or train a Projectionist-hosted model on your chats
- Require a Projectionist cloud account, or send analytics anywhere
- Expose live `X-Plex-Token` media URLs through privacy MCP or member library views
- Let a privacy MCP key, or a mode flag, unlock full MCP
- Hand MCP clients the Plex server token, AI provider key, or `settings.json`
- Store raw microphone audio
- Let members add Apprise destinations, or confirm Radarr/Sonarr adds unless the owner turned on **Without my confirm** for that adult member (each such add is in the security log with the member and title, never their chat or memory)
- Use someone else's viewing to write your "You watched" lines
- Pretend a Plex list publish worked when Plex refused it
- Bring back a removed account, or data a member deleted, when the owner restores a backup

---

## Your choices

- **Members:** turn email, Apprise, nudges, and newsletters on or off in **Settings → Notifications**. Delete a chat thread from **Chat**. Download or delete your data in **Settings → My data**. Ask the owner to remove your account.
- **Owners:** keep sign-in off for a single trusted operator, or turn it on so each person's data is kept apart.
- Pick an AI provider you trust. A local model such as Ollama keeps chat on your network.
- Leave `PROJECTIONIST_MCP_FULL_API_KEY` unset if you only want the privacy MCP schema. Rotate MCP keys if one leaks.
- Copy `DATA_DIR/backups` off the server if you need protection from a failed disk, and store those copies like secrets.

---

## Related docs

- [SECURITY.md](SECURITY.md) — operator threat model and findings
- [MCP.md](MCP.md) — MCP tools, keys, and transport
- [wiki/Multi-User.md](wiki/Multi-User.md) — household sign-in
- [HELP.md](HELP.md) — in-app Help (`/help`)
- In-app copy of this page: **`/privacy`** (no sign-in required)
