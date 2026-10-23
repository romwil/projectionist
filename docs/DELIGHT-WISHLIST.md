# Delight wishlist — BA opportunity briefs

This is a **pre-backlog brief**. It is what a BA would hand engineering *before* tickets. It is not shipping status and not a sprint plan. Delivery sequencing (1.37.61–66) lives in [2026-10-23-delight-wishlist-delivery.md](superpowers/plans/2026-10-23-delight-wishlist-delivery.md); this file stays the brief.

Shipping status lives in [CHANGELOG.md](../CHANGELOG.md) and [PRODUCT.md](PRODUCT.md). Knowledge mechanics live in [MEDIA_INTELLIGENCE.md](MEDIA_INTELLIGENCE.md). MCP contract lives in [MCP.md](MCP.md).

**Baseline:** Automat prod is **1.37.60** shipped (For you junk-copy refuse + iPad 2× selection). Do not list those as future work. Do not reopen parked Phase 6 leftovers or Tunarr-era doors — they sit in the [Archive](#archive).

SQLite WAL. Optional Plex / Radarr / Sonarr / TMDB / LLM. MCP: `python -m projectionist.mcp.server` (tools only; no resources). Dual keys: privacy = read-only public schema; full = internal fields + confirm-gated *arr. Private user memory never leaves either plane.

Jump to: [How to read a brief](#how-to-read-a-brief) · [Index](#index-of-briefs) · [Personas](#personas-context-of-use) · [Cross-cutting](#cross-cutting) · [Household viewer](#household-viewer) · [Youth](#youth-member) · [Curator / admin](#curator--admin--maintainer) · [Live TV grazer](#live-tv-grazer) · [Lobby](#theater--lobby-kiosk) · [MCP](#mcp-personas) · [Repo agent](#cursor--repo-agent) · [Research spikes](#research-spikes) · [Archive](#archive)

---

## How to read a brief

The unit of this document is an **opportunity brief**, not a paragraph of intent. Every brief is specific enough that a later ticket writer does not invent the product.

| Field | What it must contain |
|-------|----------------------|
| **ID** | Stable (`XC-01`, `TN-01`). Do not renumber when adding. |
| **Persona** | One primary. Secondary only when they consume the same object. |
| **Job / situation** | When and where (Explore hub, MCP `what_to_watch_tonight`, iPad Safari Play, Lobby `:8791`, Admin Monday, Claude Desktop, n8n). |
| **Current behavior** | Named surfaces, APIs, tools, example copy, what is wrong or missing *today*. |
| **Desired behavior** | What the human or agent sees/hears/gets: example sentences, JSON fields, UI placement. |
| **Honesty gate** | Exact refuse rules. Empty is better than junk. |
| **Data** | Already in SQLite vs would need to collect. |
| **Success** | Observable pass/fail a reviewer can run. |
| **Out of scope** | So the brief cannot sprawl. |
| **Depends on / unblocks** | Other brief IDs, not slogans. |

Shipped substrate is **current behavior**, not a new opportunity. If the remaining work is “do not regress,” the brief says so.

**Hard non-goals** (same locks as [PRODUCT.md](PRODUCT.md)): no Projectionist-managed Plex HDHomeRun / tuner rebuild; no Tunarr; no IdleScheduler rewrite; no Postgres/Redis; no “on Netflix”; no gift queue / trust diary / Admin House seasonal veto; no 2× on Live TV; no Lobby kiosk campaign unless the house actually relies on `:8791`.

---

## Index of briefs

| ID | Title | Primary persona |
|----|-------|-----------------|
| [XC-01](#xc-01-shared-reason-builder) | Shared reason builder | Cross-cutting |
| [XC-02](#xc-02-episode-overlay-is-plot-not-a-watched-title) | Episode overlay is plot, not a watched title | Cross-cutting |
| [XC-03](#xc-03-citations-and-availability) | Citations and availability | Cross-cutting |
| [HV-01](#hv-01-for-you-copy-on-the-first-rail) | For you copy on the first rail | Household viewer |
| [HV-02](#hv-02-chat-cites-the-same-explanation-object) | Chat cites the same explanation object | Household viewer |
| [HV-03](#hv-03-poster-why-line-when-a-bridge-exists) | Poster why line when a bridge exists | Household viewer |
| [HV-04](#hv-04-play-living-room-contract) | Play living-room contract | Household viewer |
| [HV-05](#hv-05-continue-watching-shrink-resume) | Continue Watching → shrink → resume | Household viewer |
| [YT-01](#yt-01-youth-for-you-and-live-fail-closed) | Youth For you and Live fail closed | Youth |
| [YT-02](#yt-02-pick-for-me-with-a-youth-safe-why) | Pick for me with a youth-safe why | Youth |
| [YT-03](#yt-03-youth-year-in-review-from-their-finishes) | Youth Year in Review from their finishes | Youth |
| [CA-01](#ca-01-named-kinship-on-titles-people-opened) | Named kinship on titles people opened | Curator |
| [CA-02](#ca-02-kinship_miss-as-a-human-list) | `kinship_miss` as a human list | Curator |
| [CA-03](#ca-03-weekly-newsletter-as-a-household-artifact) | Weekly newsletter as a household artifact | Curator |
| [CA-04](#ca-04-year-in-review-from-the-watch-tracker) | Year in Review from the watch tracker | Curator |
| [LV-01](#lv-01-cycle-pool-honesty) | Cycle pool honesty | Live grazer |
| [LV-02](#lv-02-flex-and-preroll-as-scheduled-identity) | Flex and preroll as scheduled identity | Live grazer |
| [LV-03](#lv-03-guide-after-a-pause) | Guide after a pause | Live grazer |
| [LV-04](#lv-04-weather-as-the-last-channel) | Weather as the last channel | Live grazer |
| [LB-01](#lb-01-idle-feed-from-the-index) | Idle feed from the index | Lobby |
| [LIB-01](#lib-01-owned-inventory-vs-gaps) | Owned inventory vs gaps | MCP librarian |
| [LIB-02](#lib-02-named-kinship-over-privacy-mcp) | Named kinship over privacy MCP | MCP librarian |
| [TN-01](#tn-01-what_to_watch_tonight-is-for-you) | `what_to_watch_tonight` is For you | Tonight concierge |
| [TN-02](#tn-02-in-progress-tv-is-finish-this) | In-progress TV is finish this | Tonight concierge |
| [FL-01](#fl-01-confirm-gated-arr-writes) | Confirm-gated *arr writes | Homelab fleet |
| [FL-02](#fl-02-propose-only-real-gaps) | Propose only real gaps | Homelab fleet |
| [NW-01](#nw-01-mcp-drafts-the-same-facts-as-admin-newsletters) | MCP drafts the same facts as Admin newsletters | Newsletter writer |
| [OP-01](#op-01-named-kinship-and-miss-demand-over-mcp) | Named kinship and miss demand over MCP | Ops agent |
| [LP-01](#lp-01-channel-recipe-from-owned-titles) | Channel recipe from owned titles | Live programming |
| [LP-02](#lp-02-read-the-published-native-lineup) | Read the published native lineup | Live programming |
| [RA-01](#ra-01-surfaces-match-productmd) | Surfaces match PRODUCT.md | Repo agent |
| [RA-02](#ra-02-for-you-copy-tests-are-the-contract) | For you copy tests are the contract | Repo agent |

---

## Personas — context of use

Household accounts today are **owner** or **member** (Youth is a flag on a member). Legacy guest rows map to member. There is no public tour. In-app curator voices (The Professor, Spark, The Steward, The Host) are how the household curator *speaks* — they are not a separate backlog.

### Human

**Household viewer.** iPad Safari, phone, or laptop on the Automat LAN (or a tunneled household session). Signed-in member. Night path is Explore → For you / Continue Watching → `/watch`. They can Play in-library titles that have a Plex `rating_key`, pin a watchlist, open Chat, open Inbox. They cannot mutate *arr. Youth-gated members are a separate persona below.

**Youth member.** Same house, distinct big-poster shell (1.23.0). Fail-closed rating gate: unrated hidden; ratings above the owner max hidden. Pick for me and youth-safe Live already exist. Empty For you is success when the only bridges are adult titles.

**Curator / admin / maintainer.** Owner on Automat LAN `http://10.10.1.202:8788`. Admin → Health / Ops / Newsletters / Live Channels / Library knowledge / Scheduled Tasks. VIP CDN and SSH tunnels are not version truth. Monday ritual is ~20 minutes.

**Theater / Lobby kiosk.** LAN-only `:8791` lightbox. Now-playing from Plex sessions; idle recently-added / released / trending. PRODUCT parks kiosk polish unless the house relies on it.

**Live TV grazer.** `/live` Guide / Watch / Weather. Native lineup `DATA_DIR/live_lineup.json`. Playback is library Play (Plex HLS), not a broadcast container. Antenna / Plex Live TV is the owner’s Plex gear — Projectionist does not run that tuner.

**Cursor / repo agent.** This git repo + Automat LAN reads. [AGENTS.md](../AGENTS.md), codegraph, [PRODUCT.md](PRODUCT.md). Interactive UI QA on `:8792` only — never prod `:8788`, never smartmap `:8790`.

### MCP

MCP has **tools only**. HTTP: `X-Projectionist-MCP-Key`. Stdio: `python -m projectionist.mcp.server` / `projectionist-mcp`. Mode comes from the key, never from a client query param. Privacy and full keys must differ.

**Household librarian (privacy key).** Claude Desktop / ChatGPT. Read-only public schema: titles, metadata, TMDB CDN posters. No `rating_key` lookup, no file sizes, no raw watch timestamps, no `in_radarr` / `in_sonarr`, no tokenized Plex thumbs. Tools they actually call: `library_query`, `library_aggregate`, `library_facet_catalog_tool`, `library_tv_episodes`, `library_tv_progress`, `library_overview_tool`, `library_title_detail` (tmdb_id / tvdb_id only), `sample_owned_library`, `discover_missing_titles`, `search_tmdb_proxy`, `upcoming_premieres`.

**Tonight concierge (full key).** Watch-adjacent tools. Today: `what_to_watch_tonight`, `recommend_hidden_gems`, `list_watchlist_pins`, `analyze_watch_patterns`. Full mode required for those four. Privacy-mode clients must not get a fake tonight from public metadata.

**Homelab fleet agent (full key, often n8n).** `propose_add_radarr` / `propose_add_sonarr` / `propose_remove_arr` + `confirm_pending_action`. Confirm/execute requires active-curation scope (`mcp_full_confirm_enabled` / `PROJECTIONIST_MCP_FULL_CONFIRM`). Without it: `requires_human_confirmation` and the token survives for `POST /api/actions/confirm`.

**Newsletter / YIR writer (full key).** Owner’s Claude Desktop or a scheduled agent. Today: `analyze_watch_patterns`, `library_overview_tool`, `upcoming_premieres`, `list_watchlist_pins`. In-app generate/send stays canonical (`POST /api/admin/weekly-newsletter/generate`, Admin → Ops → Newsletters). MCP drafts; it does not send mail.

**Library-health / ops agent (full key).** `library_overview_tool`, `suggest_purge_candidates_tool`, `library_aggregate`. Suggestions, not deletes.

**Live programming assistant.** No Live MCP tools today. They pick station pools with `library_query` filters that match Live Channels fine-tune (genre, decade, rating, unwatched). Near-term: read `live_lineup.json` the way Admin already does ([LP-02](#lp-02-read-the-published-native-lineup)).

Chat-agent graph tools (`find_similar_titles`, `list_relations`, `walk_relations`, `titles_by_person`) are **in-process** (`projectionist.agent.tools.ToolRegistry`), not MCP yet. Wrapping them is [LIB-02](#lib-02-named-kinship-over-privacy-mcp). Inventing a parallel graph is not.

---

## Cross-cutting

If several personas share one product rule, the rule lives here. Persona sections link to it. Do not restate the rule as a slogan in five places.

### XC-01 Shared reason builder

- **Persona.** Primary: household viewer. Secondary: youth, newsletter writer, tonight concierge, in-app chat, repo agent.
- **Job / situation.** Any surface that answers “why this title, tonight, for this house”: Explore For you (`GET /api/library/feeds/for-you`, hub rail `for_you`), Inbox nudges / whispers, weekly member newsletter (`build_member_newsletter`), chat “more like last night” / `find_similar_titles`, MCP `what_to_watch_tonight`.
- **Current behavior.**
  - Explore For you (`feed_for_you` → `list_linked_unwatched` → `bridge_between`) already emits `kind=watched_bridge` with `{kind, sentence, terms, seed_ids, peer_id, evidence}`. Empty shelf copy: *“No named link to something you finished — not a cosine guess. Finish a title, or let Scheduled Tasks catch up Named kinship.”* Mode is `"watched_bridge"`. Weekly persona rails (`feed_for_you_weekly` / `member_weekly_rail`) are a **separate** taste cache and are not a cosine fallback for this shelf.
  - Inbox / whispers / `build_member_newsletter` already call `specific_bridge` / `watched_library_rows`. Newsletter omit rule today: a newly added title with no named link is dropped; the letter says *“Nothing new this week shares a subject, a creator, or a franchise with what you have watched.”*
  - Neighbor / More Like This / Related titles use `_why_payload` + `specific_plot_link` / `honest_plot_link`. Cosine-only rows stay out (`explainable_only=True`, `item_neighbors.explainable`, `plot_link_json`).
  - In-app chat `find_similar_titles` reads `item_neighbors` (`mode=similar|surprising`) and refuses cosine-only peers. Chat cards still accept `set_recommendation_reasons` / `recommendation_reason` strings; pipeline labels (`"tmdb title match"`, `"double feature — first half"`) are stripped by `sanitize_recommendation_reason`. That is **not** the same object as `watched_bridge`.
  - **MCP `what_to_watch_tonight` is not For you.** Full-mode only. Implementation:

    ```text
    query_library(media_type, query="watch tonight", unwatched_only=False,
                  in_progress_only=False, sort="title", limit=N)
    ```

    Payload is a library dump: `{total_matched, returned, offset, has_more, items[]}` with browse rows. No `explanation`, no `mode`, no empty-note. The FTS query `"watch tonight"` does not mean “worth watching now.” A client that narrates those hits as “because you watched” is lying.
  - In-app agent `ToolRegistry._tool_what_to_watch_tonight` is a **third** path: scores `all_library_items()` by `effective_view_count`, stamps `reason="Good pick for tonight"`. That string is not a named link.
- **Desired behavior.** One builder, one object, every mouth. Callers: `list_linked_unwatched` (For you / inbox / newsletter), chat similar-title cards, MCP `what_to_watch_tonight` ([TN-01](#tn-01-what_to_watch_tonight-is-for-you)).

  Example explanation (plot link):

  ```json
  {
    "kind": "watched_bridge",
    "sentence": "You finished House (2004); Contagion (2011) — both stories turn on a diagnostic puzzle.",
    "terms": ["diagnostic puzzle"],
    "seed_ids": [1408],
    "peer_id": 99,
    "evidence": {
      "seed_source": "completion",
      "link_kind": "plot_link",
      "seed_title": "House",
      "episode_rating_key": "ep-not-cancer",
      "episode_title": "Not Cancer"
    }
  }
  ```

  Crew / collection variants keep `kind=watched_bridge` with `evidence.link_kind` of `shared_crew` | `directed_by` | `written_by` | `collection`. Sentence examples:
  - *“You finished Heat (1995); Collateral (2004) — shared director/writer: Michael Mann.”*
  - *“You pinned The Bourne Identity (2002); The Bourne Supremacy (2004) — same collection: Bourne Collection.”*

  UI placement: For you card meta (`cardMeta` already reads `item.why || item.recommendation_reason`). Chat card `recommendation_reason` **is** `explanation.sentence` or omitted. Newsletter body is those sentences, one per pick. MCP tonight returns the same `explanation` object per item ([TN-01](#tn-01-what_to_watch_tonight-is-for-you)).
- **Honesty / empty-better-than-junk gate.**
  - No named link → omit the title. Do not fill with cosine, `with_neighbors_pct`, `"Good pick for tonight"`, `"tmdb title match"`, or Wikipedia/TMDB glue.
  - `specific_plot_link` / `honest_plot_link` refuse generic overlap. Banned example sentences: *“Both stories turn on an ordinary people.”* *“Both stories turn on a drama television and a which premiered.”* Refused terms include `ordinary people`, `drama television`, `which premiered`, `tropical climates`, `creative arts`.
  - No seed from `watch_completions` / `watch_sessions` / terminal `watch_events` / `watchlist_pins` → no “because you watched.” Library `view_count` / `last_viewed_at` is last-resort seed only when the ledger is empty, and still needs a named inner link.
  - Runtime caps (“under two hours”) **filter** the bridge list. They do not invent substitutes.
  - Privacy MCP does not get tonight from public TMDB metadata.
- **Data it already has.** `library_items` plot layers (`summary`, `tmdb_overview`, `tagline`, `long_synopsis`, `llm_logline`); `people` / `credits`; `title_relations`; `item_neighbors.explainable` + `plot_link_json`; `watch_completions` / `watch_sessions` / `watch_events`; `watchlist_pins`; `library_episodes.summary` for overlay.
- **Data it would need.** None for the shared object. MCP tonight needs to **call** `list_linked_unwatched` instead of `query_library`. Chat needs to prefer `explanation.sentence` over `set_recommendation_reasons` when a bridge exists.
- **Success.** A reviewer finishes *House* S8E2, then: For you card, inbox nudge, weekly newsletter pick, chat “more like last night,” and MCP `what_to_watch_tonight` either (a) cite the same `kind=watched_bridge` sentence naming *House (2004)* plus a noun-phrase plot subject / crew / collection, or (b) omit the peer. None of those five surfaces include *“an ordinary people”* or *“Good pick for tonight.”*
- **Out of scope.** New ranking engine. Weekly persona rail as For you fallback. Episode knowledge graph ([RS-02](#rs-02-episode-knowledge-graph)). Mood chips over MCP ([RS-03](#rs-03-mood-chips-over-mcp)).
- **Depends on / unblocks.** Unblocks [HV-01](#hv-01-for-you-copy-on-the-first-rail), [HV-02](#hv-02-chat-cites-the-same-explanation-object), [HV-03](#hv-03-poster-why-line-when-a-bridge-exists), [TN-01](#tn-01-what_to_watch_tonight-is-for-you), [CA-03](#ca-03-weekly-newsletter-as-a-household-artifact), [NW-01](#nw-01-mcp-drafts-the-same-facts-as-admin-newsletters). Uses [XC-02](#xc-02-episode-overlay-is-plot-not-a-watched-title) for seed labels.

---

### XC-02 Episode overlay is plot, not a watched title

- **Persona.** Household viewer (For you / inbox). Secondary: newsletter, MCP tonight.
- **Job / situation.** Member finished a TV **episode**. Explore For you, inbox, newsletter, and MCP tonight explain a peer.
- **Current behavior.** Completing an episode resolves to the **show** `library_items` row, then `_overlay_episode` prepends `library_episodes.summary` (or the episode title if summary is empty) onto `summary` so `plot_blob` / `_plot_phrase_candidate_ids` match the episode’s story. That overlay is correct for **matching**. Display is not: `_title_label` appends `episode_title`, so `bridge_between` emits *“You finished House (2004) — Not Cancer; The Beauty (2026) — …”*. *Not Cancer* reads as a movie the house finished. Empty episode plots fall back to the episode title as plot text, which can also leak into phrase search.
- **Desired behavior.** Overlay stays on the seed’s plot blob and in `evidence.episode_rating_key` / `evidence.episode_title`. Display `sentence` names the **show** (and year), not the episode title as a watched work. Optional clause, only when the episode has a real Plex plot: *“You finished an episode of House (2004); Contagion (2011) — both stories turn on a diagnostic puzzle.”* If the episode has no plot, match against the show plot or omit the peer — do not treat the string `Not Cancer` as plot text.
- **Honesty gate.** A For you / inbox / newsletter / MCP tonight sentence never presents an episode title as the watched title. Cosine show-neighbors stay refused. No per-episode `item_neighbors`.
- **Data it already has.** `watch_completions.rating_key` + `parent_rating_key`; `library_episodes.title` / `summary` / `season_number` / `episode_number`.
- **Data it would need.** None.
- **Success.** After completing House S8E2 *Not Cancer*, a House-seeded For you card never includes the substring `Not Cancer` as the watched title. The reason is a noun phrase naming a plot subject, a crew name, or a collection — or the card is omitted. `explanation.evidence.episode_title` may still be `"Not Cancer"` for debugging.
- **Out of scope.** Per-episode embeddings ([RS-02](#rs-02-episode-knowledge-graph)). Changing Continue Watching episode labels (those cards *should* name the episode).
- **Depends on / unblocks.** Required by [XC-01](#xc-01-shared-reason-builder) display copy. Unblocks honest TV For you.

---

### XC-03 Citations and availability

- **Persona.** MCP librarian / tonight concierge / newsletter writer. Secondary: in-app chat.
- **Job / situation.** An agent answers “do we have it?”, “why this?”, or “add this.”
- **Current behavior.** Privacy MCP sanitizes via `_emit` → `sanitize(audience=audience_for_mode())`. `library_title_detail(rating_key=…)` errors in privacy mode. `discover_missing_titles` returns `{title, year, media_type, tmdb_id, poster_url, in_library: false}`. `sample_owned_library` is an owned sample (the old `find_collection_gaps` alias) — **not** gap discovery. `upcoming_premieres` is `query_library(recently_added_days=30, sort="added_at")` — recently added, not theatrical premiere. In-app availability line is In your library / Requestable / Not here yet (no Netflix). Chat `research_title` (in-process) returns provenance; there is no MCP wrap yet.
- **Desired behavior.** Every agent-facing title row that claims playability has `in_library: true` **and** a `rating_key` (full mode) or an explicit `playable: true` derived from one (privacy mode may omit the key but must not claim playable without it). Gap titles stay `in_library: false` and are never scheduled, Play-linked, or narrated as on disk / on Plex. “Recently added” copy uses that phrase, never “premiered.” Provenance for research (when wrapped) names TMDB / Wikipedia / OMDb / TVDB — never a Plex path.
- **Honesty gate.** Do not hallucinate on-disk or Plex availability. Do not say “on Netflix.” Do not treat `upcoming_premieres` as upcoming theatrical dates. Do not look up `rating_key` on the privacy key.
- **Data it already has.** `library_items.rating_key`, `in_radarr` / `in_sonarr` (full only), TMDB ids, Seerr requestability in-app.
- **Data it would need.** None for the rule. MCP `research_title` wrap is later ([LIB-02](#lib-02-named-kinship-over-privacy-mcp) adjacent; see MCP.md).
- **Success.** A privacy-mode `library_query` hit never includes `rating_key` or a Plex thumb URL. A `discover_missing_titles` item is never passed to Live lineup builders or Play. A newsletter pick without a library `rating_key` is omitted or labeled requestable — never “play this.”
- **Out of scope.** External streaming availability. Public pages.
- **Depends on / unblocks.** Constrains [TN-01](#tn-01-what_to_watch_tonight-is-for-you), [LP-01](#lp-01-channel-recipe-from-owned-titles), [NW-01](#nw-01-mcp-drafts-the-same-facts-as-admin-newsletters), [FL-02](#fl-02-propose-only-real-gaps).

---

## Household viewer

Couch, iPad Safari, “what should we watch.” Night path: Explore → For you / Continue Watching → `/watch`.

### HV-01 For you copy on the first rail

- **Persona.** Household viewer.
- **Job / situation.** Opens `/explore`. For you is the first rail (1.37.59). Cards use `cardMeta` → `item.why || item.recommendation_reason`.
- **Current behavior.** `GET /api/library/feeds/for-you` returns `{feed: "for-you", mode: "watched_bridge", items, empty, note}`. Junk-copy refuse is on `main` (PR #149): `honest_plot_link` rebuilds stored `plot_link_json` from honest terms or returns none. Empty note is the honest one quoted in [XC-01](#xc-01-shared-reason-builder). Remaining defect is [XC-02](#xc-02-episode-overlay-is-plot-not-a-watched-title) (episode titles in “you finished …”).
- **Desired behavior.** First-scroll cards show `explanation.sentence` under the poster, or the rail is empty with the existing note. No second “weekly For you” rail.
- **Honesty gate.** [XC-01](#xc-01-shared-reason-builder) + [XC-02](#xc-02-episode-overlay-is-plot-not-a-watched-title). Never cosine filler. Empty is success.
- **Data it already has.** Same as XC-01.
- **Data it would need.** None beyond XC-02 display fix.
- **Success.** House For you card never includes episode title *Not Cancer* as the watched title; reason is a noun phrase naming a plot subject, crew, or collection, or the card is omitted. Empty rail shows the “no named link / not a cosine guess” note.
- **Out of scope.** Redesigning the Explore hub. Restoring Tonight’s table (superseded 1.37.38).
- **Depends on / unblocks.** XC-01, XC-02.

---

### HV-02 Chat cites the same explanation object

- **Persona.** Household viewer (adult).
- **Job / situation.** Chat: “more like last night” / “why is For you empty?” In-app agent tools, not MCP.
- **Current behavior.** `find_similar_titles` / `list_relations` / `walk_relations` / `titles_by_person` already refuse cosine-only peers. Empty neighbors mean the idle scheduler has not materialized the cache. Chat can still stamp a free-text `recommendation_reason` via `set_recommendation_reasons`. Rail → chat seed (`railChatSeed.js`) already forwards `why`.
- **Desired behavior.** If More Like This / For you has an `explanation`, chat reuses `explanation.sentence` as the card why. If the graph is catching up, the assistant says the cache is not ready — not that nothing is related, and not a cosine dump. Question “why is For you empty?” answers with the For you `note` / refusal, not a browse dump.
- **Honesty gate.** Do not invent a plot link. Do not use `"Good pick for tonight"`. Pipeline reasons stay sanitized to empty.
- **Data it already has.** In-process graph tools; `item_neighbors.explainable`; For you payload.
- **Data it would need.** None. Optional: pass `explanation` through `TitleCard` instead of a parallel string.
- **Success.** After an empty For you, chat does not list cosine peers as “because you watched.” After a House bridge exists, chat’s similar-title card why matches For you’s `explanation.sentence`.
- **Out of scope.** New in-app curator voices. MCP graph wrap ([LIB-02](#lib-02-named-kinship-over-privacy-mcp)).
- **Depends on / unblocks.** XC-01.

---

### HV-03 Poster why line when a bridge exists

- **Persona.** Household viewer.
- **Job / situation.** Title poster on Explore sections other than For you, title detail, More Like This carousel.
- **Current behavior.** For you is the only Explore rail that systematically shows `watched_bridge` copy. More Like This uses neighbor `_why_payload` labels (`plot_link` sentence, or crew/collection). Other cards rely on `recommendation_reason` when a curator set one.
- **Desired behavior.** Any card that arrived via a bridge (For you, inbox “open this,” More Like This from a watched seed) shows the one-line `explanation.sentence` under the title — same object as XC-01. Cards that did not arrive via a bridge show no why line (not a similarity score).
- **Honesty gate.** No line when `kind` is missing. Do not fall back to cosine label (*“Strong plot kinship”*) as the why. `_why_payload` already blanks neighbor labels when `specific_plot_link` refuses; keep that.
- **Data it already has.** Shared explanation shape on neighbors / relations / inbox.
- **Data it would need.** A way to know the card’s *arrival* kind (bridge vs browse). Browse walls stay why-less unless a bridge is attached.
- **Success.** A browse-sorted Movies wall does not sprout “because you watched” on every poster. A More Like This peer with `plot_link_json` shows the plot-subject sentence; a cosine-only neighbor is not in the carousel.
- **Out of scope.** Redesigning `PosterActionMenu`. Watch-together session polling.
- **Depends on / unblocks.** XC-01.

---

### HV-04 Play living-room contract

- **Persona.** Household viewer (iPad Safari living room; phone shrink-onto-page). Secondary: youth (same player).
- **Job / situation.** `/watch/{ratingKey}` library Play. Not Live.
- **Current behavior (shipped — do not reopen as features).**
  - Buffering OSD: `BufferingIndicator` via `libraryBufferingHealth` / `stepLibraryBufferingUi` (same delay as Live so brief underruns do not flash). Copy is **Buffering**, not a faint “Loading…”. Seek-fail copy owns the stage (*“Couldn’t jump in this title.”*).
  - Hold-to-2×: press-and-hold the picture outside controls (`applyHoldPlaybackRate`). Release returns to 1× and does not pause (`holdToRateShouldCancelTap`). **Live TV must not call this.** iPad Safari often ignores `playbackRate` on Plex HLS without `#EXT-X-ENDLIST`; `shouldShowHoldRateChip` is true only when the element reports rate 2 — never a fake chip.
  - Captions: one overlay (`SubtitleOverlay` + `silenceNativeTextTracks`). CC menu nudges sync by 0.5s. Native text tracks stay silenced so cues do not double.
  - Preroll: random video from `/preroll` on **movie** start; episodes skip; HTTP 204 if missing; not skippable; no title on screen.
- **Desired behavior.** Keep that contract. Do not add chrome (always-on transport, extra badges, second caption renderer, 2× on Live). If Safari leaves `playbackRate` at 1, the picture stays 1× and there is no 2× chip.
- **Honesty gate.** No fake 2×. Live clock stays 1×. One caption layer. Missing preroll folder → start the picture, no bumper, no error toast that implies a missing movie.
- **Data it already has.** Plex HLS session; preroll bind `PROJECTIONIST_PREROLL_MEDIA`; subtitle VTT from Plex.
- **Data it would need.** None.
- **Success.** Regression: iPad Safari library Play hold does not select page text (PR #148). Buffering chip appears after the Live hold delay when waiting for frames, hides when a current frame is present. Live Watch has no 2× chip and `playbackRate` stays 1. Enabling CC shows one cue layer, not native + overlay.
- **Out of scope.** 2× on Live. Tuner work. Redesigning the OSD. Pause-when-backgrounded remains Settings → Profile, this-browser only.
- **Depends on / unblocks.** Protects living-room Play. Unblocks nothing new.

---

### HV-05 Continue Watching → shrink → resume

- **Persona.** Household viewer.
- **Job / situation.** Night path: Explore Continue Watching → Play → lock iPad / switch apps → come back.
- **Current behavior.** Continue Watching is Plex on-deck, not live sessions (`feeds.py`). Shrink-onto-page survives reload (1.37.42+). `pagehide` resume (1.37.58). Close on the bar leaves the player and does not resurrect after reload.
- **Desired behavior.** Lock the iPad, come back: same title, same spot, shrink panel if they had shrunk. **Close** means close.
- **Honesty gate.** Do not resurrect a player the member dismissed. Do not claim someone is watching in another room (that is Lobby Plex sessions, not this path).
- **Data it already has.** Resume offset; shrink state; Continue Watching cache (`rememberContinueWatchingProgress`).
- **Data it would need.** None.
- **Success.** After lock/reload mid-title, Play resumes within a few seconds of the prior offset. After Close, reload does not reopen the player.
- **Out of scope.** Live session polling as a member feature. Watch-together ([RS-05](#rs-05-watch-together-without-a-session-poll)).
- **Depends on / unblocks.** None.

---

## Youth member

Same house, narrower door. Distinct layout already shipped. Invite-only join is the household door — do not build a guest tour.

### YT-01 Youth For you and Live fail closed

- **Persona.** Youth member.
- **Job / situation.** Explore For you; Live Guide/Watch; chat cards.
- **Current behavior.** `filter_items_for_youth` / `filter_payload_for_youth` hide unrated and over-ceiling titles on feeds, chat cards, and Live. For you is another feed. In-app `what_to_watch_tonight` youth tests exist; MCP tonight is full-mode and must still honor the same gate when the acting user is youth (today MCP is not per-user — see honesty).
- **Desired behavior.** Nothing unrated or over the owner max appears, including “because you watched.” Empty For you for a youth account is success when the only bridges are adult titles.
- **Honesty gate.** Skip the pick rather than cite a title they cannot open. MCP full-key tonight is an **owner** tool; do not expose it to a youth ChatGPT session. If a household MCP is ever user-scoped, apply the same gate.
- **Data it already has.** `content_rating`; owner max; youth flag.
- **Data it would need.** None for in-app. User-scoped MCP is out of scope here.
- **Success.** A PG-13 youth account never sees an R For you card even when the adult finished that title last night. Empty rail, no cosine filler.
- **Out of scope.** Guest tour. Public pages.
- **Depends on / unblocks.** XC-01 (youth sees a filtered view of the same builder).

---

### YT-02 Pick for me with a youth-safe why

- **Persona.** Youth member.
- **Job / situation.** Youth shell Pick for me / Surprise Me one-shot.
- **Current behavior.** Quick-pick exists; `test_quick_pick_api.py` expects `why: "Unwatched pick for you"` — a pipeline label, not a named link. Mood chips are Companion one-shot and must not overwrite taste.
- **Desired behavior.** One youth-safe sentence from XC-01 if a bridge exists and the peer passes the rating gate: *“You finished Paddington (2014); Paddington 2 (2017) — same collection: Paddington.”* If not, pick an unwatched in-rating title **with no why line** (do not stamp “Unwatched pick for you” as if it were a plot link). Skip rather than cite an adult title.
- **Honesty gate.** No adult seed in the sentence. No cosine. Empty/skip > junk why.
- **Data it already has.** Quick-pick pool; rating gate; XC-01 builder.
- **Data it would need.** None.
- **Success.** Reviewer: youth Pick for me never includes an R title and never shows *“Unwatched pick for you”* as the visible why. Either a named youth-safe bridge sentence or no why.
- **Out of scope.** Mood over MCP ([RS-03](#rs-03-mood-chips-over-mcp)). Overwriting taste.
- **Depends on / unblocks.** XC-01.

---

### YT-03 Youth Year in Review from their finishes

- **Persona.** Youth member.
- **Job / situation.** Opt-in YIR (`year_in_review_opt_in`), `/year-in-review/{year}`.
- **Current behavior.** YIR is already per-member watch-tracker (`year_in_review_snapshots`, `honesty_footnote`: *“Finishes attributed to you — not the whole household.”* Confidence buckets: certain / likely / plex_event_only). Empty coverage should not produce a reel of household Plex totals.
- **Desired behavior.** A youth reel uses only that youth’s tracked finishes, rating-gated. No owner-visible adult memory mixed in. No reel from empty coverage.
- **Honesty gate.** Do not substitute Plex `view_count`. Do not mix adult completions into a youth reel.
- **Data it already has.** Watch tracker; opt-in flag; rating gate.
- **Data it would need.** Confirm youth rows are excluded from adult household rollups (if not, that is the ticket).
- **Success.** Youth account with zero tracked finishes: no reel, honest empty. Youth account that only finished G/PG titles: those titles only.
- **Out of scope.** Social sharing. Public pages.
- **Depends on / unblocks.** CA-04 (same tracker honesty).

---

## Curator / admin / maintainer

Automat LAN is truth (`http://10.10.1.202:8788`). Monday ritual, Ops newsletters, Investigate / rematch, Native Live craft.

### CA-01 Named kinship on titles people opened

- **Persona.** Curator / owner with ~20 minutes on Monday.
- **Job / situation.** Admin Dashboard Monday pass (`OwnerHealthHero`): Named kinship → open issues → purge pressure → Scheduled Tasks. Coverage: `GET /api/library/knowledge-coverage`.
- **Current behavior.** `with_explainable_neighbors_pct` is the Named kinship KPI (share of **all** library titles with ≥1 explainable neighbor). `with_neighbors_pct` is Similar cache (cosine). Hash embeddings labeled via `embedding_model` / `embedding_is_hash_fallback`. Automat 1.37.58 snapshot ~72.9% — PRODUCT says the target is higher on *opened* titles, not a fake 100%. The payload does **not** split opened vs cold titles. `kinship_miss` (`telemetry_events.event_type=kinship_miss`) already prefers idle batches (1.37.57) when More Like This / Related / bridge has zero peers.
- **Desired behavior.** Monday pass still leads with Named kinship. Add a second observable: **Named kinship on opened titles** — percent of titles that recorded a `kinship_miss` or a title-detail / More Like This view in the last 7 days that now have `item_neighbors.explainable=1`. Display next to the global %. Copy: Similar cache % is not “useful relatedness.” Catch-up is the lever.
- **Honesty gate.** Do not report 100% kinship as a goal. Hash-fallback stays labeled. Hit counts are demand, not a grade.
- **Data it already has.** `with_explainable_neighbors_pct`; `kinship_miss` rows (`hit_count`, `entity_id`); knowledge-coverage payload.
- **Data it would need.** A definition of “opened”: reuse `kinship_miss` keys (already demand) **or** a small counter on title-detail / More Like This. Prefer miss keys so we do not invent a new analytics plane. Field name e.g. `with_explainable_neighbors_opened_pct` on `GET /api/library/knowledge-coverage`.
- **Success.** After Sunday empty More Like This on *Heat*, Monday coverage JSON includes an opened-title kinship % that moves when idle `plot_neighbors` annotates *Heat*. Global Similar cache % can stay high while opened Named kinship is the number the hero quotes.
- **Out of scope.** IdleScheduler rewrite. Postgres. Auto-promoting misses into staged augmentations ([RS-01](#rs-01-closed-loop-miss--staged-augmentation)).
- **Depends on / unblocks.** CA-02, OP-01.

---

### CA-02 `kinship_miss` as a human list

- **Persona.** Curator.
- **Job / situation.** Admin Library health / knowledge, after the Monday pass tiles.
- **Current behavior.** Misses write `telemetry_events` (`event_type=kinship_miss`, soft queue cap, `hit_count` bumps). Idle `metadata_enrichment` / `long_synopsis_enrichment` / `summary_motifs` / `plot_neighbors` prefer that backlog. There is no owner-facing list of “titles someone opened to an empty shelf.”
- **Desired behavior.** A human list: title, poster, why it queued (`more_like_this_empty` | `related_empty` | `bridge_zero_peers`), `hit_count`, last miss time. Links to the title. Not a grade. Not auto-repair.
- **Honesty gate.** Demand ≠ quality. Do not auto-promote into staged augmentations. Hash-fallback still labeled on those titles.
- **Data it already has.** `telemetry_events` kinship_miss; `library_items`.
- **Data it would need.** A read API, e.g. `GET /api/library/kinship-miss?limit=50`, owner-only.
- **Success.** Owner can name three titles that had empty More Like This this week without querying SQLite by hand.
- **Out of scope.** Closed-loop promote ([RS-01](#rs-01-closed-loop-miss--staged-augmentation)). Scheduler rewrite.
- **Depends on / unblocks.** CA-01. Unblocks OP-01 (same list over MCP).

---

### CA-03 Weekly newsletter as a household artifact

- **Persona.** Curator (generate/send). Secondary: household viewer (receives), newsletter MCP writer.
- **Job / situation.** Admin → Ops → Newsletters (`/admin/newsletters`). `POST /api/admin/weekly-newsletter/generate`. Transport: SMTP / Resend / Apprise only.
- **Current behavior.** `build_member_newsletter` already runs new-this-week titles through `specific_bridge` / `watched_library_rows`. No why → title omitted. Empty reason block is the honest sentence in XC-01. House letter (`weekly_letter.py`, kind `digest`) is a different artifact (unwatched hours, dead weight, disk) — not For you.
- **Desired behavior.** Keep the bridge gate. Each recommended title’s body line **is** `explanation.sentence` after XC-02 (show name, not episode title as watched work). Availability: in-library Play only when a `rating_key` exists; otherwise omit or mark requestable. Recently added ≠ premiered.
- **Honesty gate.** No seed → no recommendation paragraph. No Netflix. No Wikipedia glue. iPad Safari sticky-bar / footer footgun stays documented in the Automat runbook — do not “fix” mail by adding a second send path.
- **Data it already has.** Digest new-this-week; watch ledger; XC-01 builder.
- **Data it would need.** None beyond XC-01/XC-02.
- **Success.** Generated letter for a member who finished *House* contains either a bridge sentence naming *House (2004)* and a plot/crew/collection link, or the empty honest block — never *“an ordinary people”* and never *Not Cancer* as a watched title.
- **Out of scope.** MCP sending mail ([NW-01](#nw-01-mcp-drafts-the-same-facts-as-admin-newsletters) drafts only). Gift queue.
- **Depends on / unblocks.** XC-01, XC-02, XC-03.

---

### CA-04 Year in Review from the watch tracker

- **Persona.** Curator (generate) + member (view).
- **Job / situation.** Admin → Ops → Newsletters YIR generate; `/year-in-review/{year}`. Opt-in `year_in_review_opt_in`.
- **Current behavior.** Snapshots from the watch tracker, not Plex `view_count`. `honesty_footnote` already distinguishes live progress / reconstructed / plex_event_only. Default year handling is in the Ops runbook.
- **Desired behavior.** Keep tracker-backed finishes. Graph use is allowed for a “because you finished X” chapter **only** via XC-01. No chapter from empty coverage. Youth: [YT-03](#yt-03-youth-year-in-review-from-their-finishes).
- **Honesty gate.** Do not substitute Plex `view_count`. Do not claim household totals as “your year” on a member reel.
- **Data it already has.** `year_in_review_snapshots`; watch tracker confidence; XC-01.
- **Data it would need.** None unless a graph chapter is added — then reuse XC-01, do not fork.
- **Success.** Member with opt-in and zero tracker finishes: no fake reel. Member with finishes: titles match tracker rows, footnote present.
- **Out of scope.** Social signals as a required chapter. Public share pages.
- **Depends on / unblocks.** XC-01 if a “because you finished” chapter is added.

Investigate / rematch / Good News (1.36) stay the honesty layer for wrong files. Runtime-only Likely stays unchecked; Identify does not pick season/episode. That is shipped stewardship, not a new brief.

Seasonal shelves already write the same store Explore reads (Live Channels). If the professor cannot answer, the button says so. Not a new brief.

---

## Live TV grazer

Cable-box from the native lineup. Projectionist does not run the owner’s HDHomeRun.

### LV-01 Cycle pool honesty

- **Persona.** Live TV grazer. Secondary: Live programming assistant.
- **Job / situation.** `/live` Guide + Watch. Station recipe: show / collection / theme. Cycle rebuild 1.37.53.
- **Current behavior.** A station whose saved cycle is a single title is rewritten from its show, collection, or theme the next time the guide is read. If the library truly has one playable item, that title still repeats (`test_live_native_schedule.py`: one-title loop emits the same key in back-to-back slots). Guide length ~one week of named titles (not **Unknown Airing** after tonight).
- **Desired behavior.** When the resolved playable pool is 1, the Guide/Watch chrome says so in plain words (*“This station has one playable title in the library — it will repeat.”*). When the pool is >1, consecutive prime-time slots on that station are not the same `rating_key` unless the owner chose a single-show “nonstop” recipe. Rebuild remains Admin → channel Settings → Rebuild lineup.
- **Honesty gate.** Do not pretend variety. Do not invent Unknown Airing as a real title. Missing lineup → `lineup_missing`, not a fake programme.
- **Data it already has.** `live_lineup.json` cycles; station recipe; playable `rating_key`s.
- **Data it would need.** Pool size already computable at rebuild; surface it on the channel health token / guide header.
- **Success.** A collection station with 12 movies does not air *Heat* in two adjacent slots after a rebuild. A station with one playable file shows the one-title notice and may repeat.
- **Out of scope.** Tunarr. HDHomeRun. Shuffle algorithm rewrite beyond rebuild-from-recipe.
- **Depends on / unblocks.** LP-01 (recipe from owned titles).

---

### LV-02 Flex and preroll as scheduled identity

- **Persona.** Live TV grazer.
- **Job / situation.** Between programmes; movie start bumper.
- **Current behavior.** Flex pad reports `is_flex` and plays a filler clip when the station has a playable filler rating key; else a progressive preroll bumper so the video element is not a black frame (`play_source_for_channel` in `native_schedule.py`). Lower-third names what’s up next (`guide_flex_title` / “Up next”). Guide labels flex as **Between programs**, not the next episode’s title (`guide.py` keeps guideFlexTitle pads labeled flex). Movie preroll on Live only when the guide says a movie is starting now or about to air; shows and movies already underway skip it. Each browser picks its own bumper (no shared bumper clock). Missing `/preroll` → HTTP 204.
- **Desired behavior.** Pad is still *this* channel: continuity asset bound to the station (Admin → Live Channels → Setup → Between-show breaks), not a black frame, not labeled as a programme title. Preroll at movie boundaries stays a bumper (no title, not skippable), not a hidden first act of the film. If neither filler nor preroll exists, show a named station card / slate (*“Between programs — up next: …”) rather than black.
- **Honesty gate.** Pad is pad. Do not label filler as a programme title. Do not steal the next episode’s name for a flex slot.
- **Data it already has.** Continuity filler binds; `PROJECTIONIST_PREROLL_MEDIA`; `guide_flex_title`; `is_flex`.
- **Data it would need.** A fallback slate when both filler and preroll are missing (could be CSS/OSD, not a new media type).
- **Success.** During a 12-minute flex, Watch shows a picture or a named slate plus “up next: {real title}.” Guide row says Between programs, not the next movie’s title. Black-frame-only is a fail.
- **Out of scope.** 2× on Live. Newspaper EPG. Tunarr filler collections as the engine (`live_channels/filler.py` Tunarr helpers are leftover — native path is `live_lineup.json`).
- **Depends on / unblocks.** None.

---

### LV-03 Guide after a pause

- **Persona.** Live TV grazer.
- **Job / situation.** Pauses a Live Watch file, comes back.
- **Current behavior.** Rejoin live vs Finish this prompt exists. Finishing a paused file stretches the clock on purpose.
- **Desired behavior.** The choice stays explicit. Copy keeps saying that finishing a paused file stretches the linear clock. Rejoin live jumps to the guide’s now.
- **Honesty gate.** Do not imply the house-wide linear clock waited. Do not 2× to catch up.
- **Data it already has.** Guide now/next; Play offset.
- **Data it would need.** None.
- **Success.** After a 20-minute pause, the prompt names both actions; choosing Finish this does not silently rewrite other stations’ clocks.
- **Out of scope.** 2× on Live. DVR.
- **Depends on / unblocks.** None.

---

### LV-04 Weather as the last channel

- **Persona.** Live TV grazer.
- **Job / situation.** `/live` Weather Channel.
- **Current behavior.** Weather Channel shipped. Place from env / profile / in-channel search (Open-Meteo). Music folder is its own Admin card; unset/empty → forecast without a fake soundtrack.
- **Desired behavior.** Keep Weather as the last channel, not a broken movie grid. No pretend listings.
- **Honesty gate.** Missing music folder → forecast, no fake soundtrack. Geocode failure → say so, do not invent a city.
- **Data it already has.** Open-Meteo; profile lat/lon; muzak root.
- **Data it would need.** None.
- **Success.** Unset music: forecast plays, UI says no soundtrack. Weather is not mixed into movie-station grids.
- **Out of scope.** Turning Weather into a programmed movie station.
- **Depends on / unblocks.** None.

---

## Theater / Lobby kiosk

LAN-only `:8791`. PRODUCT parks polish unless the house relies on it. Do not start a campaign.

### LB-01 Idle feed from the index

- **Persona.** Lobby kiosk. Secondary: household (walks past the wall).
- **Job / situation.** Idle carousel when nothing is playing; now-playing from Plex sessions when something is.
- **Current behavior.** `theater/snapshot.py` idle feeds: `feed_recently_added`, `feed_recent_releases`, `feed_trending`. Now-playing from Plex sessions, privacy-minimized (`_opaque_session_id`). Art from `library_items`.
- **Desired behavior.** Idle posters are titles in the index. Now-playing posters resolve to library art. Never a TMDB-only discovery card. If the house later wants For you-honest idle, **fall back** to the named idle feed when For you is empty — never cosine filler on a ten-foot UI. That For you-idle variant is **only if** [RS-04](#rs-04-does-this-house-use-lobby-8791) says the wall is in use.
- **Honesty gate.** Never show a title that is not in the index. Never expose `:8791` off LAN. Never claim a member is watching unless a Plex session is on the Lobby snapshot.
- **Data it already has.** Library feeds; Plex sessions; household `plex_user_id` keys.
- **Data it would need.** For you-idle only after RS-04.
- **Success.** Idle carousel items all have a `library_items` row. A TMDB gap title never appears.
- **Out of scope.** Lobby chrome, newspaper EPG, kiosk-only motion. Member now-watching polling.
- **Depends on / unblocks.** RS-04 for any For you-idle work.

---

## MCP personas

### MCP tool inventory (today)

Read (both keys unless noted):

| Tool | Args (principal) | Returns today |
|------|------------------|---------------|
| `library_query` | media/year/genre/crew/keyword/rating/language, `query`/`fts_query`/`semantic_query`, watch filters, runtime, *arr flags (full), `sort`, `offset`, `limit` | `{total_matched, returned, offset, has_more, items[]}` browse rows |
| `library_aggregate` | `group_by` (decade, year, genre, …) + subset of filters | Bucket counts |
| `library_facet_catalog_tool` | `facet_type`, `limit` | Top facet values |
| `library_tv_episodes` | `show` / `show_id`, `season`, `unwatched_only`, paging | Episode rows |
| `library_tv_progress` | `group_by=show\|season`, `in_progress_only`, `limit` | Progress summary |
| `library_overview_tool` | none | Totals, decades, genres, directors, TV progress |
| `library_title_detail` | `media_type` + `tmdb_id` \| `tvdb_id` \| `rating_key` (full only) | Title detail dump |
| `sample_owned_library` | media/year/genre, `limit` | `{overview, sample_owned}` — **not** gaps |
| `discover_missing_titles` | TMDB gap filters, `limit` | `{items: [{title, year, media_type, tmdb_id, poster_url, in_library: false}]}` |
| `search_tmdb_proxy` | `query`, `media_type`, `limit` | Trimmed TMDB + CDN posters |
| `upcoming_premieres` | `limit` | `query_library(recently_added_days=30, sort=added_at)` |
| `what_to_watch_tonight` | `media_type`, `query`, `limit` — **full** | Library dump with `query="watch tonight"` — **not For you** |
| `recommend_hidden_gems` | `media_type`, `limit` — **full** | `query_library(max_view_count=1, sort=vote)` |
| `analyze_watch_patterns` | `limit` — **full** | `{overview, in_progress_tv}` |
| `list_watchlist_pins` | `limit` — **full** | `{items, count}` |
| `suggest_purge_candidates_tool` | `limit` — **full** | `{count, items}` suggestions |

Writes (full only): `propose_add_radarr(tmdb_id, title)`, `propose_add_sonarr(tvdb_id, title)`, `propose_remove_arr(...)`, `confirm_pending_action(token, confirmed)`.

Not on MCP: `find_similar_titles`, `list_relations`, `walk_relations`, `titles_by_person`, Live lineup, knowledge-coverage, `kinship_miss`, newsletters, YIR.

---

### LIB-01 Owned inventory vs gaps

- **Persona.** Household librarian (privacy MCP).
- **Job / situation.** Claude Desktop: “do we have it?” / “what are we missing in 1970s crime?”
- **Current behavior.** `library_query` / `library_title_detail` hit SQLite. `discover_missing_titles` is real TMDB gaps (`in_library=false`). `sample_owned_library` is an owned sample. Privacy mode never invents watch history.
- **Desired behavior.** “We have it” only from `library_query` / detail with `in_library` true. Gaps only from `discover_missing_titles`. Agents must not use `sample_owned_library` as gap discovery (tool docstring already says so; client instructions should too).
- **Honesty gate.** XC-03. No `rating_key` in privacy. No tokenized Plex thumbs. `upcoming_premieres` ≠ premiered.
- **Data it already has.** Index + TMDB key.
- **Data it would need.** None.
- **Success.** Privacy `library_title_detail(rating_key=…)` returns the existing error. `discover_missing_titles` items all have `in_library: false`. A sample_owned item is a library row.
- **Out of scope.** Full-mode internals on the privacy key.
- **Depends on / unblocks.** XC-03.

---

### LIB-02 Named kinship over privacy MCP

- **Persona.** Household librarian. Secondary: tonight concierge.
- **Job / situation.** “More like Heat” / “same director as …” / “franchise siblings” from Claude Desktop on the **privacy** key.
- **Current behavior.** Those questions only work in-app (`list_relations`, `walk_relations`, `titles_by_person`, `find_similar_titles`). MCP cannot walk `title_relations` or `people`/`credits` except via `library_query` director/cast filters (browse, not a named why).
- **Desired behavior.** Wrap the **same** in-process functions as MCP tools (privacy-sanitized): `list_relations`, `walk_relations` (depth ≤ 2), `titles_by_person`, `find_similar_titles` with `explainable_only=True`. Each peer carries XC-01 `explanation` or is omitted. Empty neighbors: `{items: [], note: "Named kinship cache not ready — not that nothing is related."}`.
- **Honesty gate.** Cosine-only rows stay out. Empty = cache not ready. No `rating_key` on privacy. Do not add MCP tools that bypass `explainable_only`.
- **Data it already has.** `title_relations`, `item_neighbors.explainable`, `people` / `credits`.
- **Data it would need.** MCP wrappers; no new graph.
- **Success.** Privacy `list_relations(seed=Heat)` returns collection/crew/plot_link peers with sentences, or an honest empty note — never a cosine-only row, never a Plex key.
- **Out of scope.** A second similarity index. `research_title` MCP (sanitized wrap is listed in MCP.md as later; provenance required; no Plex paths).
- **Depends on / unblocks.** XC-01. Helps TN-01 if tonight wants graph peers.

---

### TN-01 `what_to_watch_tonight` is For you

- **Persona.** Tonight concierge (full MCP).
- **Job / situation.** Claude Desktop / ChatGPT: “what should we watch tonight?”
- **Current behavior.** Full-mode `query_library(..., query="watch tonight", sort="title")` dump. See XC-01. In-app agent tool is a third, also not For you (`reason="Good pick for tonight"`).
- **Desired behavior.** MCP `what_to_watch_tonight` calls `list_linked_unwatched` (same path as `feed_for_you`). Optional filters (`runtime_max`, `media_type`) **filter** that list.

  Example payload:

  ```json
  {
    "mode": "watched_bridge",
    "empty": false,
    "note": null,
    "items": [
      {
        "title": "Contagion",
        "year": 2011,
        "media_type": "movie",
        "in_library": true,
        "playable": true,
        "explanation": {
          "kind": "watched_bridge",
          "sentence": "You finished House (2004); Contagion (2011) — both stories turn on a diagnostic puzzle.",
          "terms": ["diagnostic puzzle"]
        }
      }
    ]
  }
  ```

  Honest empty:

  ```json
  {
    "mode": "watched_bridge",
    "empty": true,
    "items": [],
    "note": "No named link to something you finished — not a cosine guess."
  }
  ```

  Cap default 3–8 finishable titles. Privacy mode: existing full-mode error (do not synthesize from TMDB).
- **Honesty gate.** XC-01, XC-02, XC-03. Runtime caps do not invent substitutes. Do not narrate browse hits as “because you watched.”
- **Data it already has.** `list_linked_unwatched`.
- **Data it would need.** None. Change the tool body; keep the name.
- **Success.** After a House completion with an honest peer, MCP tonight’s first item `explanation.kind` is `watched_bridge` and `in_library` is true. After junk-only overlap (ordinary people), payload is empty with the note. `query="watch tonight"` is not used as FTS.
- **Out of scope.** Privacy-mode tonight. Mood chips ([RS-03](#rs-03-mood-chips-over-mcp)). Renaming the tool.
- **Depends on / unblocks.** XC-01, XC-02, XC-03. Align in-app `_tool_what_to_watch_tonight` to the same builder or stop telling the model they are the same tool.

---

### TN-02 In-progress TV is finish this

- **Persona.** Tonight concierge.
- **Job / situation.** “What should we watch?” when a show is on deck.
- **Current behavior.** `library_tv_progress(in_progress_only=true)` and `analyze_watch_patterns` already return in-progress TV. Tonight dump does not prefer them.
- **Desired behavior.** Tonight payload may include a `continue: []` block from TV progress / Continue Watching: *“Finish The Bear S2E4 (paused 12 minutes in).”* Separate from `items[]` new-bridge picks. Progress is not a completion.
- **Honesty gate.** Do not mark in-progress as watched. Do not invent an on-deck episode that Plex on-deck / `library_tv_progress` did not return.
- **Data it already has.** `library_tv_progress`; Continue Watching / on-deck; `analyze_watch_patterns.in_progress_tv`.
- **Data it would need.** Wire those into TN-01 payload as `continue`, not as `watched_bridge`.
- **Success.** A show with an in-progress episode appears under `continue` with season/episode, not as a “because you finished” peer of itself.
- **Out of scope.** Live now-watching polling.
- **Depends on / unblocks.** TN-01.

---

### FL-01 Confirm-gated *arr writes

- **Persona.** Homelab fleet agent (n8n / trusted LAN, full key).
- **Job / situation.** Propose add/remove; human or scoped confirm.
- **Current behavior.** `propose_add_*` short-circuit on exists / acquisition exclusion. `confirm_pending_action` without active-curation scope returns `requires_human_confirmation` and leaves the token. Privacy callers get an error. No silent `require_confirmation=false`.
- **Desired behavior.** Keep that. Without scope, do not retry-confirm in a loop. Cancel always allowed.
- **Honesty gate.** Never double-add. Never re-add an exclusion. Never confirm on the privacy key. Never delete files from a chatty model (`propose_remove_arr` still needs confirm; `delete_files` defaults false).
- **Data it already has.** Pending-action table; *arr clients; exclusion flags.
- **Data it would need.** None.
- **Success.** Full key without confirm scope: propose succeeds, confirm returns `requires_human_confirmation`, token still redeemable in the web status dock. Privacy key: propose tools error.
- **Out of scope.** Seerr replacement for member media requests. Self-confirming keys stay rare (trusted in-stack only).
- **Depends on / unblocks.** FL-02.

---

### FL-02 Propose only real gaps

- **Persona.** Homelab fleet agent.
- **Job / situation.** Building an add queue from “we don’t have this.”
- **Current behavior.** Agent can call `discover_missing_titles` then `propose_add_radarr`. Nothing stops proposing a cosine “similar to what you own” TMDB hit from `search_tmdb_proxy`.
- **Desired behavior.** Propose only titles that `discover_missing_titles` (or an explicit TMDB id the owner named) says are missing. Optional why: “missing from 1970s crime slice you asked for” — not a fake watched_bridge.
- **Honesty gate.** Do not propose from cosine similar-to-owned. Do not confirm on the privacy key. Do not schedule gap titles on Live.
- **Data it already has.** `discover_missing_titles`; propose tools.
- **Data it would need.** None (policy + maybe a `source: "discover_missing_titles"` field on the pending payload).
- **Success.** A pending add’s tmdb_id is absent from `library_items`. A title already in Radarr returns the existing short-circuit object, not a new token.
- **Out of scope.** Auto-download. Seerr.
- **Depends on / unblocks.** FL-01, XC-03.

---

### NW-01 MCP drafts the same facts as Admin newsletters

- **Persona.** Newsletter / YIR writer (full MCP).
- **Job / situation.** Owner’s desktop agent drafting the weekly note or a YIR beat.
- **Current behavior.** Writer can call `analyze_watch_patterns`, `upcoming_premieres`, `library_overview_tool`, `list_watchlist_pins`. None of those return `watched_bridge` sentences. In-app generate/send stays canonical.
- **Desired behavior.** Either (a) MCP tonight-style `list_linked_unwatched` (TN-01) plus overview/progress, or (b) a read-only `weekly_newsletter_preview` that returns the same `build_member_newsletter` body/picks the Admin button would send — without sending. Agent drafts; Admin → Newsletters sends.
- **Honesty gate.** Recently added ≠ premiered. Overview counts are not “you watched.” YIR: tracker finishes, not `view_count`. XC-01/XC-02/XC-03.
- **Data it already has.** Newsletter builder; watch ledger; overview.
- **Data it would need.** A preview tool **or** TN-01 + instructions. Prefer wrapping `build_member_newsletter` so copy cannot drift.
- **Success.** MCP preview body matches Admin generate for the same member/week, including the empty honest block when there are no bridges.
- **Out of scope.** MCP sending SMTP/Resend/Apprise. Mail transport settings.
- **Depends on / unblocks.** XC-01, CA-03, TN-01.

---

### OP-01 Named kinship and miss demand over MCP

- **Persona.** Library-health / ops agent (full MCP).
- **Job / situation.** Monday pass without opening Admin.
- **Current behavior.** `library_overview_tool`, `suggest_purge_candidates_tool`, `library_aggregate`. No coverage split, no miss list. Purge candidates are suggestions; `propose_remove_arr` still needs confirm.
- **Desired behavior.** Read tools: knowledge-coverage payload (`with_explainable_neighbors_pct`, opened % from CA-01, `embedding_is_hash_fallback`) and CA-02 miss list. Still no deletes from the model.
- **Honesty gate.** Hash-fallback labeled. Do not report 100% kinship as a goal. Purge is a review list.
- **Data it already has.** Coverage endpoint; kinship_miss; purge helper.
- **Data it would need.** MCP wraps of existing owner GETs.
- **Success.** Agent can say “Named kinship on opened titles is 41%; these three titles had empty More Like This” from tool JSON, without inventing percentages.
- **Out of scope.** Fleet mutation from the ops agent unless a separate full key with confirm scope. Snapshot / backup stay in Admin.
- **Depends on / unblocks.** CA-01, CA-02.

---

### LP-01 Channel recipe from owned titles

- **Persona.** Live programming assistant.
- **Job / situation.** Owner in Claude Desktop: “Chaos Night is these movies.”
- **Current behavior.** `library_query` filters (genre, decade, rating, unwatched) match Live Channels fine-tune. No publish-from-MCP. `discover_missing_titles` is a shopping list.
- **Desired behavior.** Build a candidate list from **owned** `library_query` hits (`in_library` / playable). Owner still publishes in Admin (Go on air / Rebuild). Do not schedule a TMDB gap title.
- **Honesty gate.** XC-03. Gap titles are not a lineup.
- **Data it already has.** `library_query`; Live fine-tune fields.
- **Data it would need.** None for the recipe list. Publish remains Admin.
- **Success.** A proposed Chaos Night list is a subset of `library_query` items with playable keys. A `discover_missing_titles` hit is refused as a programme.
- **Out of scope.** MCP that publishes a channel without confirm. Tunarr OpenAPI dayparts.
- **Depends on / unblocks.** XC-03, LV-01.

---

### LP-02 Read the published native lineup

- **Persona.** Live programming assistant (privacy or full).
- **Job / situation.** “What’s on 101 at 8?” without opening `/live`.
- **Current behavior.** No Live MCP tools. Admin / Guide read `DATA_DIR/live_lineup.json`.
- **Desired behavior.** Read-only MCP: channel number/name, now/next, flex vs programme, pool size notice from LV-01. Missing file: `{error: "lineup_missing"}`. Sanitize: no Plex tokens, no host paths.
- **Honesty gate.** Do not invent Unknown Airing as a real title. Do not attach or rebuild a Plex tuner. Flex stays flex.
- **Data it already has.** `live_lineup.json`; Guide now/next helpers.
- **Data it would need.** A thin MCP wrap of the native guide read.
- **Success.** Tool on a running Automat lineup names the real now title for channel 101. With the file removed, `lineup_missing` — no synthetic programmes.
- **Out of scope.** MCP publish/shuffle. HDHomeRun. 2×.
- **Depends on / unblocks.** LV-01 (pool notice), LV-02 (flex flag).

---

## Cursor / repo agent

Operators of the product who also change it. Delight them as operators, not as a second docs dump.

### RA-01 Surfaces match PRODUCT.md

- **Persona.** Cursor / repo agent.
- **Job / situation.** Implementing from this file or PRODUCT.
- **Current behavior.** PRODUCT / HELP / MEDIA_INTELLIGENCE tell the 1.37.59 story. This file no longer presents Phases 3–6 as current work.
- **Desired behavior.** Agents do not resurrect Tunarr, guest tour, Phase 6 gift queue, IdleScheduler rewrite, or Postgres. LAN `:8788` is version truth; `projectionist.automat.vip` is not. QA UI on `:8792` only.
- **Honesty gate.** Do not treat CDN/tunnels as version. Do not stop smartmap `:8790` or prod `:8788` for QA.
- **Data it already has.** PRODUCT, AUTOMAT, AGENTS.md.
- **Data it would need.** None.
- **Success.** A PR spawned from this wishlist does not add Tunarr orchestration, HDHomeRun attach, or a gift-queue table.
- **Out of scope.** New in-app chat voices as a “delight program.”
- **Depends on / unblocks.** Everything else in this file.

---

### RA-02 For you copy tests are the contract

- **Persona.** Repo agent.
- **Job / situation.** UI-string / kinship / feed changes.
- **Current behavior.** PR #149 + `tests/test_household_bridges.py` / `tests/test_surprising_plot_kinship.py` refuse `ordinary people`, `drama television`, `which premiered`, empty-without-bridges. `honest_plot_link` rebuilds or refuses stored junk `plot_link_json`.
- **Desired behavior.** Any change to For you / `_sentence` / overlay display adds a pass/fail test at the XC-01/XC-02 success lines. Empty-shelf tests stay load-bearing.
- **Honesty gate.** Empty shelf tests are as load-bearing as happy-path rails.
- **Data it already has.** Unit coverage on refuse paths.
- **Data it would need.** XC-02 display tests (episode title not in watched-title copy). TN-01 MCP tests once that tool changes.
- **Success.** A UI-string change cannot ship *“an ordinary people.”* House overlay test: *Not Cancer* is not the watched title.
- **Out of scope.** Visual snapshot theater for every rail.
- **Depends on / unblocks.** XC-01, XC-02, TN-01.

---

## Research spikes

A note that cannot be specified against real code/data stays here: question, evidence to gather, decision it unlocks. Not fake features.

### RS-01 Closed-loop miss → staged augmentation

- **Question.** Should `kinship_miss` ever auto-promote into staged augmentations (MEDIA_INTELLIGENCE “next horizon”), or is idle prefer (1.37.57) enough?
- **Evidence.** After CA-02 exists: miss hit_counts vs how often idle annotation actually fills More Like This within 24h on Automat. Owner time spent on empty shelves Mondays.
- **Decision unlocked.** Whether to schedule closed-loop work. Default until then: **no**. Not an IdleScheduler rewrite.

### RS-02 Episode knowledge graph

- **Question.** After XC-02, is show+episode overlay still too coarse for TV For you (peers matching the wrong episode story)?
- **Evidence.** Sample 20 Automat episode completions: overlay peers vs owner judgment. Count false peers caused by show-level plot remaining in `plot_blob`.
- **Decision unlocked.** Per-episode embeddings / `item_neighbors` (MEDIA_INTELLIGENCE parked). Default: **do not build** until XC-02 ships and still fails.

### RS-03 Mood chips over MCP

- **Question.** Should Companion’s one-shot `mood=` quick-pick exist on MCP tonight?
- **Evidence.** Whether anyone calls MCP tonight for mood vs For you. Risk of overwriting taste (in-app mood is one-shot and must not persist).
- **Decision unlocked.** A `mood` arg on TN-01 that filters the bridge list, or no. Never a parallel ranker.

### RS-04 Does this house use Lobby `:8791`?

- **Question.** Is the kiosk on in daily use?
- **Evidence.** Owner confirmation; whether `:8791` is up on Automat; whether anyone looks at it.
- **Decision unlocked.** If no, LB-01 stays “don’t lie” only — no For you-idle. PRODUCT already parks a polish campaign.

### RS-05 Watch together without a session poll

- **Question.** Is an Inbox note that names a title + why (existing Watch together / inbox) enough, or are we being asked for live “they’re in the other room”?
- **Evidence.** Current Watch together + inbox usage. Lobby already shows Plex now-playing for the wall.
- **Decision unlocked.** If the ask is live presence, **refuse** (member now-watching polling is parked). If the ask is an Inbox note with XC-01 why, that can be a later brief — not specified here because the notes were a feeling.

---

## Archive

Historical delight program. **Do not schedule from this section.** Living briefs are above. Shipping truth is CHANGELOG / PRODUCT.

Status: **Shipped** = in product; **Superseded** = shipped then replaced; **Parked** = not on the 1.37 roadmap.

### Phases 1–6 (compact)

| Phase | Focus | Status |
| ----- | ----- | ------ |
| **1** | Curator memory — cited knowledge, follow-ups, fail-closed per-user memory | **Shipped** 1.10.0 |
| **2** | Owner tools — health hero, grooming undo, collections/courses, Youth review, weekly digest | **Shipped** 1.16.0 |
| **3** | Adult everyday — where-to-watch, watchlist, continue-watching, inbox + mail, taste/weekly rail | **Shipped** P3a 1.20.0; P3b 1.21.0; P3c 1.22.0. Weekly Explore rail **superseded** by For you (1.37.58+) |
| **4** | Distinct youth + guest doors | **Shipped** 1.23.0; guest tour **superseded** (invite-only join; guest → member) |
| **5** | Curator depth — Enthusiast nudge, Scholar syllabus, Concierge acquire, Companion mood | **Shipped** 1.24.0 (live now-watching dropped). GIF/clip in chat remains parked Like |
| **6** | Honesty, evening, owner story, scholar, craft | **Triaged 1.37.58** — core **shipped** in 1.36; leftovers **parked** |

Historical spec: [2026-09-24-delight-phase-6.md](superpowers/specs/2026-09-24-delight-phase-6.md). Tunarr dual-watch leftovers: [live-channels-deferred](superpowers/plans/2026-07-29-live-channels-deferred.md).

**Still locked from Phases 3–6:** external “on Netflix/Max”; live Plex session polling as a member feature; replacing Seerr for post-member *media* requests (Projectionist owns *account* access requests only); public pages; Postgres/Redis; yanking `CURATORX_*` without a CA note.

### Locked decisions (Phases 3–5)

| Topic | Decision |
| ----- | -------- |
| Where-to-watch v1 | In-library + Seerr only. No external streaming-service availability. |
| Notifications | `/inbox` + optional owner-configured mail. Weekly newsletter opt-in. Per-user email + channel prefs. |
| Mail v1 | SMTP **and** Resend; secrets `0600`. Apprise in the same transport family. |
| Youth unrated titles | **Fail-closed** — hide empty `content_rating` and ratings above owner max. |
| Household roles | owner / member. Youth is a flag. Guest tour superseded. |
| Now-watching / Plex sessions | Out of the delight program. Lobby may show Plex now-playing; that is not member now-watching. |
| Guest request-access | Invite/request queue → owner inbox. Seerr remains for *media* requests after membership. |

### Phase 6 / 1.36 triage (1.37.58)

| MUST | Disposition |
|------|-------------|
| Episode investigation (stills, OSHash, runtime, vision fusion) | **Shipped** 1.36.0 (+ 1.36.1–2) |
| ACRCloud Identification API (not Broadcast Monitoring / Custom File Scan) | **Shipped** 1.36.0 / 1.36.1 |
| Rematch studio + repair-the-miss + Good News | **Shipped** 1.36.0 |
| Afterglow, unfinished, whisper inbox | **Shipped** 1.36.0 |
| Tonight’s table | **Shipped** 1.36.0, **superseded** 1.37.38 — For you is the honest shelf |
| Phone Play + pinned composer | `plex://` 1.36.5, **superseded** by `/watch` 1.37.0 |
| Owner letter | **Shipped**; surviving surface Admin → Newsletters |
| Scholar footnotes, walks, syllabus | **Shipped** 1.36.0 |
| Seasonal preview/veto on Admin → House | **Parked** — seasonal editing on **Live Channels** |
| Gift queue | **Parked** — removed 1.37.24 |
| Trust diary | **Parked** — rematch / Investigate / job cards remain the audit trail |

### Parked inventory (do not resurrect as the plan)

| Item | Origin | Notes |
|------|--------|-------|
| Gift queue | Phase 6 / Admin → House | Removed 1.37.24 |
| Trust diary | Phase 6 / Admin → House | Removed 1.37.24 |
| Admin House seasonal preview/veto as a page | Phase 6 | Seasonal shelves: Admin → Live Channels |
| Enthusiast GIF/clip in chat | Phase 5 Like | Still deferred |
| Projectionist-managed Plex HDHomeRun / XMLTV attach / tuner rebuild | Tunarr dual-watch | Native Live 1.37.51+; never Repair Plex |
| Tunarr Docker orchestration / admin auth / image pin | Tunarr dual-watch | Engine removed from the running path |
| Daypart / Chaos schedule-slots via Tunarr OpenAPI | Tunarr dual-watch | |
| Newspaper EPG / re-run starter pack against Tunarr | Tunarr dual-watch | |
| IdleScheduler rewrite / global priority across all trickle tasks | Craft / MEDIA_INTELLIGENCE | Miss queue prefer in 1.37.57 is enough |
| Postgres / Redis | Craft lock | SQLite WAL stays |
| External “on Netflix” where-to-watch | Phases 3–6 lock | In-library + Seerr only |
| Lobby kiosk polish campaign | PRODUCT parked | Unless RS-04 says the house relies on `:8791` |
| 2× on Live TV | Play 1.37.59 excluded | Linear clock stays 1× |
| Public pages | Phase 6 lock | |
| Live Plex session polling as a member feature | Enthusiast re-rank | Lobby now-playing is a kiosk feed |
| Yank `CURATORX_*` without a CA note | 1.34.0 | Compose-layer map only |

Older Cursor plans `persona_delight_top_10_a8ebd6a0` and `unified_gaps_and_delight_b1cef49d` are historical.

---

## See also

- [PRODUCT.md](PRODUCT.md) — positioning, surface map, SWOT, parked Tunarr-era non-goals
- [MEDIA_INTELLIGENCE.md](MEDIA_INTELLIGENCE.md) — explainable kinship, `watched_bridge`, `kinship_miss`
- [MCP.md](MCP.md) — dual keys, tool list, H3 confirm scope
- [HELP.md](HELP.md) — household + owner how-to
- [DESIGN.md](DESIGN.md) — product principles
- [docs/ops/AUTOMAT.md](ops/AUTOMAT.md) — prod `:8788`, smartmap `:8790`, QA `:8792`
