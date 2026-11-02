# Privacy & data use

This page explains what Projectionist stores, who can see it, and what leaves the server. It's written for the people who use the app, not only for the owner reading the [security assessment](SECURITY.md). Where the app falls short of what you might expect, this page says so.

Projectionist is **self-hosted**. The household owner chooses where it runs, which AI provider answers chat, and whether people sign in. **There is no Projectionist cloud account, and Projectionist does not phone home.**

The short version:

- **What is stored.** The library catalog, your chats and preferences, your notifications, and the owner's connection settings. All of it lives in one database and one settings file on the owner's server, plus the daily backups described below.
- **What leaves the server.** Your chat goes to the AI provider the owner picked. Search text may go to the owner's embeddings provider. Notifications go to the email or push service the owner set up. Poster images load from public artwork sites. Your Plex token and the owner's settings file do not leave.
- **What you can't do yet.** There is no **Download my data** or **Delete my data** button. To leave, ask the owner to remove your account. **[Getting a copy or leaving](#getting-a-copy-or-leaving)** lists what removal deletes and what it leaves behind.

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
- **Youth accounts.** The owner can read a Youth account's memory in **Admin → Youth review**. The owner can turn **Youth mode** on for any account, which also opens that account's memory to them. Each change is written to the security log. Your profile shows a **Youth** badge while it is on.
- **The household list** the owner sees includes your notification email, your saved weather place, your Plex account number, and when you last signed in.
- **Activity.** **Admin → Overview** shows household totals. The owner's tools can also list individual chat turns and plays with the account that made them. Those rows never include what you typed.

### Inbox, newsletters, and alerts

Projectionist can write to you: a weekly newsletter, the occasional "you have to see this" nudge, a whisper about something new, and a Year in Review. Each lands in your **Inbox**.

**How it works.** A newsletter, nudge, or whisper names a title and one reason it connects to something **you** finished. Only your own viewing counts. If you haven't watched enough yet, you get a quieter note or none. Someone else's viewing never stands in.

Choose what reaches you in **Settings → Notifications**:

- **Email.** Sent through the mail service the owner set up. Depending on their choice, that is their own mail server or Resend, an email delivery company.
- **Apprise** (push to apps like Discord or Telegram). Only the owner adds destinations. If you turn it on, your notes go to the household destinations the owner chose, and other people may read those.

### What the curator remembers

The curator keeps two kinds of memory:

- **Your private memory.** Preferences, stated goals, watch intentions, and follow-ups for your account only.
- **Shared knowledge** about titles, people, and companies it looked up. This isn't tied to any account, so everyone's curator can reuse it. It is saved as the AI wrote it. If you mention something personal while it researches a title, that detail could end up in shared knowledge.

### Getting a copy or leaving

**There is no Download my data or Delete my data button yet.** Projectionist can delete a single chat thread from **Chat**. For anything more:

- **To leave**, ask the owner to remove your account in **Admin → Members**.
- **To get a copy**, ask the owner. They can't export another person's data from the app, but they hold the full backup.

**What removal deletes:** your profile, private memory, chats and messages, saved library pages, preference notes, your Plex viewing record, activity counts, watchlist, lists, inbox, taste profile, badges, streaks, courses, and Year in Review.

**What removal leaves behind:**

- Your ratings and written reviews, and any pending rating prompts
- Actions you started that were never confirmed
- AI usage records (deleted after 90 days)
- Problems you reported about a title (your name is removed, the text stays)
- Your request to join, and the email on any invite you received
- Your uploaded profile picture
- Shared knowledge the curator saved
- Security log entries about your account
- Copies in backups made before removal. The daily backups roll off after seven days. Backups the owner downloaded last as long as they keep them.

### What the AI provider receives

Chat uses the AI provider the owner connected: OpenAI, Anthropic, OpenRouter, or a model on the owner's own machine such as Ollama. It receives:

- Your messages and the conversation so far
- Your private memory and preference notes, so the curator knows you
- What the curator looks up to answer: titles, library matches, and your watch signals

**Youth accounts use the same provider.** A Youth account's chats go wherever adult chats go. There is no separate local-only setting for Youth yet.

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
| **Place search** | The text you type (ZIP, city and state, or city and country) to Open-Meteo, a free weather service | You search for a place |
| **Forecast** | The latitude and longitude of your saved place, or the household default, to Open-Meteo | The channel opens |
| **Voiceover** | Nothing. Your browser speaks it. | The channel opens |
| **Music** | Nothing. It plays from the owner's music folder. | A music folder is set |

A place you save is stored on your profile and reused, so it isn't looked up again.

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

Restore checks the snapshot before touching anything. It moves the current database and `settings.json` to `backups/pre-restore-<timestamp>/` rather than deleting them. Those set-aside folders are not pruned, so remove them yourself once the restore looks right. **Admin → Overview → Needs attention** warns when the backup task is off or the newest snapshot is more than three days old.

**Honest limit:** the snapshot lives on the same disk as the data. Copy `DATA_DIR/backups` somewhere else if you need protection from a failed disk.

### Export and removal, exactly

Each signed-in account can export or purge its own data with the API. There is no member button for this yet, and an owner can't run it for someone else.

```bash
# Export the signed-in account (JSON) — use that account's session cookie
curl -s -b 'curatorx_session=YOUR_SESSION' \
  http://localhost:8788/api/me/memory > my-projectionist-export.json

# Purge the same set for the signed-in account (permanent)
curl -s -b 'curatorx_session=YOUR_SESSION' -X DELETE \
  http://localhost:8788/api/me/memory
```

Export and purge cover the same tables. The export leaves out the profile, watchlist, lists, reviews, inbox, and taste profile, so it is not a full copy. The Markdown export lists chat thread titles and message counts, not the messages.

| Data | Exported | Purged | Removed with the account | Table |
|------|:--------:|:------:|:------------------------:|-------|
| Private memory notes | Yes | Yes | Yes | `user_memory_notes` |
| Chat threads and messages | Yes | Yes | Yes | `chat_sessions`, `chat_messages` |
| Saved library pages | Yes | Yes | Yes | `saved_library_pages` |
| Preference facts | Yes | Yes | Yes | `preference_facts` |
| Mapped watch evidence | Yes | Yes | Yes | `watch_events`, `watch_sessions`, `watch_completions` |
| Activity counts | Yes | Yes | Yes | `system_telemetry_stream` |
| Watchlist, lists, inbox, taste profile, badges, streaks, courses, Year in Review | No | No | Yes | foreign keys to `users` |
| Ratings and reviews, rating prompts | No | No | **No** | `user_title_reviews`, `rating_prompt_queue` |
| Pending confirmations | No | No | **No** | `pending_actions` |
| LLM usage | No | No | After 90 days | `llm_usage` |
| Memory audit events | No | No | **No** | `user_memory_events` |
| Reported issues (reporter cleared) | No | No | Text stays | `media_issues` |
| Access requests, invite emails | No | No | **No** | `access_requests`, `invites` |
| Uploaded avatar file | No | No | **No** | `DATA_DIR` avatars |
| Shared repository insights | No | No | **No** | `memory_insights` |
| Security log | No | No | **No** | `security_audit_log` |

**Youth review.** `GET /api/users/{id}/memory` returns memory only for accounts flagged Youth, and **Admin → Youth review** shows the same.

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

Two records stay on this server so you can run it well. Neither is sent anywhere.

- **Activity counts** (`system_telemetry_stream`). A chat turn records its outcome, card and tool counts, and timing, never the words. A play started in Projectionist records the title and, only when the member pressed Play on a curator card or a household recommendation, which pick it came from. Rows are kept 90 days. **Admin → Overview** shows totals. `GET /api/admin/telemetry/events` returns the raw rows, including the account id.
- **Security log** (`security_audit_log`). Sign-ins, failed sign-ins, password changes and resets, invites, role and Youth changes, settings saves, secret reveals, MCP key changes, and backup downloads. Settings saves list setting **names**, never values. Only owners can read it (**Admin → Health → Security log**). It keeps the newest 20,000 rows and is not removed with an account.

### Images

Member-facing library JSON and privacy MCP prefer TMDB poster and backdrop URLs (`image.tmdb.org`), which carry no Plex token or LAN hostname. Plex thumbnail URLs that embed `X-Plex-Token` stay inside the owner's in-app views.

### Browser-side third parties

Fonts and icons are self-hosted. A signed-in browser contacts only the origins you turned on by configuring a provider:

| Origin | When | Why |
|---|---|---|
| `image.tmdb.org`, `artworks.thetvdb.com`, `assets.fanart.tv` | A poster or backdrop loads | Artwork CDNs; no Plex token or LAN hostname in the URL |
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
| Private memory and preference facts | Database | Own | Youth accounts; server files and backups | — | — | Own chat\* |
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
- Let members add Apprise destinations, or confirm Radarr/Sonarr adds
- Use someone else's viewing to write your "You watched" lines
- Pretend a Plex list publish worked when Plex refused it

---

## Your choices

- **Members:** turn email, Apprise, nudges, and newsletters on or off in **Settings → Notifications**. Delete a chat thread from **Chat**. Ask the owner to remove your account.
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
