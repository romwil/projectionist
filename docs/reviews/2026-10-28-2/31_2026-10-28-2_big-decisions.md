# 31 · Big decisions — run 2026-10-28-2

These are leadership calls. They are not tickets. Each one blocks a slice of `2026-10-28-2_backlog.csv` (`DecisionRequired`). Commit reviewed: `94fcd3f`. The red team’s three questions are BD-1, BD-2, and BD-3. The cross-examination added BD-4 and BD-5.

Decision owner for all five: the maintainer. Deadline: before the next Hub release after this review, and in any case within 14 days of accepting the roadmap. Waiting is option “do nothing” on each ADR.

## DecisionRequired remap

The backlog cited BD-06, BD-07, BD-08, and BD-09. Those decisions were never written. All eleven rows are remapped to `no`. None of them depends on BD-1 through BD-5. Phase placement is the `LaunchPhase` column on `2026-10-28-2_backlog.csv`.

**BD-06** (how deep the youth contract goes) → `no`

- PRD-011. Re-prove before build (P0). The R-rated thread list was text the harness typed.
- SEC-018 and ARCH-015. One viewer policy, in this release (P2).
- PRIV-008. Youth data-profile platform, post-launch.

**BD-07** (whether to build an agent capability kernel) → `no`

- SEC-002. Role, Youth, and confirm inside tools (P2).
- SEC-034. CI corpus that locks that policy (P2).
- ARCH-022. Capability service-layer refactor, post-launch with ARCH-016 through ARCH-024.

**BD-08** (single-owner step-up, and settings that fail open) → `no`

- SEC-007. Owner credential on crown-jewel routes (P2).
- ARCH-008. Atomic settings writes that fail closed (P2).

**BD-09** (whether full-mode MCP is on by default) → `no`

- PRIV-014. Disclose that exposure and default affinity tools to the owner (P2).
- SEC-032. Per-key rate limits, last-used, and scopes, post-launch.

---

## BD-1 · Who is the roadmap for, and how will we know it worked?

**Context.** Projectionist is a self-hosted household app with no phone-home (PRIV-017). Public acquisition is GitHub, Docker Hub, and Unraid CA. The review surveyed one Automat QA sidecar. The red team asked who the next two quarters serve: that household, or the unknown CA installers, given that nothing leaves the box and the project’s public star count is not a funnel.

**Options.**

1. **Do nothing.** Keep shipping what the maintainer’s house needs. Success stays anecdotal.
2. **Automat-only.** Sequence the roadmap by this household’s Monday pass, Live, and youth accounts. Treat CA users as later.
3. **Installer-first, measured on box.** Every epic needs a success metric a household can see locally (GRO tracking plan). Publish those checks in release notes. Do not add a telemetry vendor.

**Recommendation.** Option 3. The core job (tonight’s title from what you own, with a named reason) is the installer job. Automat’s scale (thousands of titles, multi-user, youth) is the stress test, not a separate product. Metrics stay local: recommendation-to-play (GRO-014), youth-gate fixture counts, health latency under load (PERF-008), deletion residue (PRIV-001).

**Trade-offs.** Option 2 ships faster for one house and drifts from CA users who never see Automat’s bugs. Option 3 refuses vanity dashboards, so “did it work?” is a release checklist, not a chart.

**Cost.** Small. A local event spine (EP-10) and a release-note checklist. No new service.

**Reversibility.** High. Adding a phone-home later would be a new decision and would contradict PRIV-017.

**Deadline.** 14 days. Blocks GRO-007, GRO-014, and any epic that currently has no on-box metric.



WR: 3, although i see the next major milestone is 'readiness to invite household users' release plan, so we'll have more feedback and metrics coming. 

**Decided.** Option 3. The next milestone is readiness to invite household users, with metrics from that cohort, and still no phone-home.

---

## BD-2 · Keep, park, or remove Live, Lobby, Holidays, Whisper, and My Journey

**Context.** Product’s grade rests on the core loop and names feature gravity as the thing earning less than that loop (PRD-013 and the product bottom line). The Monday pass, named kinship, Play, and youth gates are unfinished. Live was off for the entire review. Lobby discloses now-playing to the room. Holidays, Whisper, and My Journey add scheduler and copy surface. The red team says one maintainer cannot do the trust-and-delivery quarter and also grow these.

**Options.**

1. **Do nothing.** Leave all five in the primary nav and the scheduler.
2. **Park.** Hide from primary nav and idle scheduler unless the owner turns them on. Code stays. No new work this quarter.
3. **Remove.** Delete one or more. Lobby and Live have LAN households that already use them on Automat.

**Recommendation.** Option 2 for this quarter. Park Holidays, Whisper, and My Journey behind the existing admin switches, off on idle. Keep Live and Lobby installed, and add no features to them until EP-05, EP-08, EP-01, EP-02, and EP-03 are in. Revisit remove-or-keep at the end of the quarter with on-box use counts (BD-1), not with this review’s Live-off screenshots.

**Trade-offs.** Parking disappoints anyone mid-ritual on My Journey. Removing Live now would strand a working LAN path the review did not exercise. Doing nothing spends the quarter on surfaces the board already said are ahead of the job.

**Cost.** Park is S (nav and scheduler flags). Remove is L per surface.

**Reversibility.** Park is reversible. Remove is not, without a restore from git.

**Deadline.** 14 days. Blocks PRD-013 and new work filed against those surfaces.

WR: Unsure why the QA passes didn't see Live, it coudl have been a QA based bug. I use it extensively.  I believe as we are opening up new users to exercise the platform we'll see real use. My journey is a much less used road for sure. I would like us to move that to just badges and achievements on the user's profile page instead of a top level navigation page of its own. 

**Decided.** Keep Live and Lobby. My Journey moves to badges and achievements on the user profile and leaves top-level nav. Holidays and Whisper stay, with no new features. Do not park Live.

---

## BD-3 · Release only from a green `main`, on a weekly train

**Context.** CI and Lint run and do not block merges. `main` has been red. Hub publish and Automat prod rollout can proceed anyway (ARCH-007, PERF-010). The current habit is a release per pull request. The red team asked what the maintainer will stop doing to make room.

**Options.**

1. **Do nothing.** Merge and roll out when the maintainer is ready. CI is advisory.
2. **Required checks, release per PR.** Green `main` is mandatory. Cadence stays “when the PR is ready.”
3. **Required checks and a weekly train.** One Hub tag a week from green `main`, or skip the week. Path B QA proof before any prod `rollout.sh`.

**Recommendation.** Option 3. Option 2 still burns a release cycle per PR and keeps Path A images in the maintainer’s head as if they were proof. The weekly train is the cut that makes BD-2 and the Now list honest.

**Trade-offs.** Urgent security fixes (SEC-001, SEC-002) need a stated exception: a same-day tag is allowed when the only commits are those fixes and CI is green. A weekly train delays delight work, which is the point.

**Cost.** M once (branch protection, checklist). Then it saves time.

**Reversibility.** High. Branch protection can be relaxed. The cost of relaxing it is how `main` went red.

**Deadline.** 7 days. Blocks every other Now item’s claim to be shippable. Exception path documented in the same week.

WR: We'll do #2.

**Decided.** Option 2. Required green CI, still one release per PR, Path B before prod. Not the weekly train.

---

## BD-4 · Must a local-password member link Plex before taste uses server history?

**Context.** Continue Watching and several “you watched” lines use the Plex server token’s on-deck and household watch evidence (SEC-010, PRIV-006). QA accounts are local passwords, which is also a supported product mode. Cross-examination: UX-038 and GRO-014 want attribution from “the member’s Plex history,” and on this install that history is someone else’s. Product wants named, per-person taste, not one blended house profile.

**Options.**

1. **Do nothing.** Server on-deck remains the member rail. Copy keeps saying “you.”
2. **Local evidence only until a link exists.** In-app Play and that user’s watch sessions. Empty state when there is none. Server on-deck is owner-only.
3. **Require a Plex link** for any member who wants Continue Watching or seeded taste. Local password remains the login.

**Recommendation.** Option 2 now. Option 3 is a product offer, not a gate, and can follow if empty states annoy real households. Do not block login on a Plex link.

**Trade-offs.** Option 2 makes Continue Watching empty for members who only watch in the Plex app. That is more honest than showing a parent’s titles to a child. Option 3 is better later if most members already have Plex accounts.

**Cost.** M (EP-02). Depends on SEC-010.

**Reversibility.** High. A later “also include my Plex account” toggle can add option 3 without undoing the boundary.

**Deadline.** 14 days, because EP-02 Now work should not build the wrong rail. Blocks SEC-010, PRIV-006, UX-038, GRO-014.

WR: we can shelf this immediate decision. 2 is basically what we have now. let's consider this as a larger product discussion. I'd like to consider the ability to link multiple watch sources to an individual's account and have projectionist not soley plex centric but also jellyfin also as a back end  'library' source. this means some architecture discussions on how we consider watch history paired to the individual etc etc. 

**Decided.** Shelved. Not in this release. Jellyfin and multi-source watch history are post-launch. Do not build new taste that assumes Plex server history is the member's.

---

## BD-5 · Does chat stay the front door?

**Context.** Sacred cow: chat is the primary product. On this QA sidecar the LLM was unset, so `/` → `/chat` behaved like a keyword router and “recommend…” produced missing-title cards (UX-010). The red team says the proposal to move chat off the home page is under-evidenced until someone sees chat with a model attached. Product still says login and chat do not complete the job when the provider is missing (PRD bottom line).

**Options.**

1. **Do nothing.** Chat remains the authenticated home. Unset LLM keeps today’s copy.
2. **Chat stays home, unset state is a picker.** Home remains chat. With no provider, the page says so in one sentence and offers Explore For you, Continue Watching, and a title, without pretending to be a model (UX-010, PRD-004).
3. **Explore becomes home.** Chat moves behind a tab until an LLM is configured.

**Recommendation.** Option 2. Do not adopt option 3 from this run. Revisit option 3 only after a household with a working LLM is walked and still bounces off chat.

**Trade-offs.** Option 2 spends a small UX change and leaves the sacred cow standing. Option 3 is a large information-architecture change justified by a sidecar that could not speak.

**Cost.** S for option 2 (EP-06). L for option 3.

**Reversibility.** Option 2 is high. Option 3 is medium: nav habits stick.

**Deadline.** 14 days. Blocks UX-010 and PRD-004. Does not block SEC-001, which is the stream route, not the front door.

WR: We can make the default page configuratble by the user if they prefer.  Chat stays the home page as the core function is a LLM driven knowledge aggregator, not much functions w/o it. Explore can be the default tab if no LLM is configured yet and the message describing the missing state on that tab would explain the situation. 

**Decided.** Chat stays home. The default page is user-configurable. If no LLM is configured, default to Explore, with copy that explains the missing provider. 
