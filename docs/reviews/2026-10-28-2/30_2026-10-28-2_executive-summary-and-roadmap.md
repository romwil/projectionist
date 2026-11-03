# 30 · Executive summary and roadmap — run 2026-10-28-2

Commit reviewed: **`94fcd3f`** on every batch. No commit drift. Survey host: QA `http://10.10.1.202:8792` (Path A image of that SHA, health `1.37.72`, not Hub CA proof). Backlog: `2026-10-28-2_backlog.csv` — **237 rows**, equal to every Weakness, Opportunity, and Remove finding in departments 01–10. Strengths are not rows.

The Chief Skeptic applied five factual corrections (accessibility CI claim, poster cause, gzip claim, bundle units, admin link count). No department grade changed. See `21_2026-10-28-2_red-team.md`.

---

## Leadership briefing

**Overall grade: C+.** Projectionist is a real household product with the right job: what this house should watch tonight, from titles it already owns, with a reason you can read. Product graded that job **B−** and told the board to protect named kinship and refuse a blended household taste profile (PRD, platform map sacred cows). Security and architecture are the same shape: a strong core (allowlisted public routes, revocable sessions, SQLite write serializer, numbered migrations) with a few paths that ignore the rules the rest of the app enforces (SEC-001, SEC-002, ARCH-007, ARCH-008).

The grade is not higher because three promises the product already makes are false, and one process failure makes every other fix unsafe to ship. Deletion is not deletion (PRIV-001, Critical). Youth is a rating flag that newsletters, nudges, and Continue Watching do not consult (PRIV-007, GRO-008, UX-044, PRD-011). Connections can say Connected while the secrets key cannot decrypt (OPS-011, OPS-010). And `main` can stay red because CI and Lint do not block a merge or a rollout (ARCH-007, PERF-010). Under that, one synchronous library query freezes the whole process, including health and the lobby theater (PERF-008).

**What to do for two quarters.** Stop adding surfaces. Make the promises true, put a gate in front of `main`, and keep the living-room loop (Explore with a named reason, Play, a rating, another night). Park or explicitly renew Live, Lobby, Holidays, Whisper, and My Journey (see `31_2026-10-28-2_big-decisions.md`). Measure success inside the box. There is no phone-home, and that is a strength (PRIV-017, GRO).

**What the platform does best.** Library-grounded recommendations with a sentence that names the link (UX-002, GRO-005). Confirm-before-*arr writes (UX-003, OPS-005). A public Privacy page and opt-in-off letters (PRIV-018, PRIV-023). A single container on SQLite with a real migration history (ARCH-001, ARCH-002). A Play path that can refuse an R-rated URL to a youth account in plain language (UX-041, SEC-030).

**Read the QA box before you fund the Highs.** Every department walked one sidecar with an undecryptable TMDB key, no LLM, Live off, synthetic accounts, and pentest-seeded access requests (`21`). Blank posters (VIS-027), “configure an LLM” chat (UX-010, PRD-007), the MAC-mismatch log flood (OPS-010), and the stale Access queue (OPS-014) are real code paths, and they also got their severity from that setup. Re-prove them on a healthy install before treating them as the quarter’s theme. The authorization holes, the event-loop stall, the deletion gap, the youth-gate gaps, and the red CI do not depend on that setup.

---

## Department grades

| Department | Grade | Verdict |
|---|---|---|
| Product | B− | The job is sharp. Activation (login, chat without an LLM, ratings) does not complete it. Feature gravity is ahead of the core loop. |
| UX | C | Named kinship and Play are honest. The shell assumes a fully wired install. Sign-out, Escape-from-Play, and Continue Watching disagree with the gates. |
| Visual design | C | Tokens exist and can carry a system. Amber is both fill and ink. Posters failed on this QA box; Plex-only installs can fail the same way. |
| Accessibility | C− | Play can be reached. Focus, titles, and dialogs are not a contract. Lint runs in CI; accessibility rules do not. |
| Growth | C− | The writing is better than the measurement. Chat turns and recommendation-to-play are invisible. The curator has several names. |
| Security | C+ | The perimeter holds. The stream route and the agent tool layer do not. |
| Privacy | C− | Local-first and opt-in-off are real. The Privacy page, purge, and two owner downloads disagree with the code. |
| Architecture | C+ | Keep the monolith and SQLite. Gates, settings writes, and authorization are spread out and fail open. |
| Performance | C− | Fast on the LAN. The uncompressed bundle and the blocking Movies query will not survive a phone or a second member. |
| Operations | C+ | The Monday pass is the right ritual. Connections can lie, and Tasks is still a scheduler dump. |

---

## Where the experts agree and disagree

Agreements, resolved in the cross-examination (`20`):

- **One youth and per-viewer policy**, consulted by list, Play, newsletter, nudge, and tools (PRD-011, UX-044, SEC-018, PRIV-007, GRO-008). Continue Watching today follows the Plex server account (SEC-010, PRIV-006).
- **One personal-data registry** so export, purge, account delete, and the Privacy page cannot drift (PRIV-001, PRIV-004, PRIV-010, ARCH-009).
- **Delivery before features.** Green `main`, required CI, compression, a split bundle (ARCH-007, PERF-007, PERF-010, PERF-011).
- **Owner truth on one Overview list**, fed by secrets, tasks, access, and health, instead of five new admin panels (OPS-011, OPS-030, UX-016, PRD-005).
- **Self-host the fonts.** Visual, accessibility, and privacy filed the same leak (VIS-014, PRIV-009).
- **Accent ink and accent fill are different tokens.** Use `#735c00` for Lights Up text. Visual’s `#735c00` wins over accessibility’s `#866200`, which only reaches about 4.82:1 (VIS-001, A11Y-002).

Disagreements, with a resolution:

| Conflict | Resolution |
|---|---|
| Nightly backups (PERF-009) keep a deleted member for weeks (PRIV-001, PRIV-005) | Keep the backup schedule. Say so on `/privacy`. Re-apply deletions after any restore, with a test. |
| Performance wants to cache the household Plex on-deck call (PERF-019). Security and privacy want members to stop using it (SEC-010, PRIV-006) | Per-viewer local history first. Cache only the owner’s server on-deck. |
| Taste seeding and play attribution want “the member’s Plex history” (UX-038, GRO-014). On this QA box that history is the server account (PRIV-006) | Attribute only in-app Play and the member’s own watch sessions until a Plex link exists. Leadership decision BD-4. |
| Five teams each want a new Admin panel. Product wants fewer admin pages (PRD-005) | One “Needs attention” list on Overview. Detail stays under Health. |
| Move chat off the home page vs chat is the product | Do not move it on evidence from an LLM-unset sidecar. Make the unset state honest (UX-010). Leadership decision BD-5. |
| Settings parse failure falls open to “everyone is owner” (ARCH-008). Security did not score it | Treat as joint High. Fail closed. |

The red team’s bolder option is a keep-or-cut on Live, Lobby, Holidays, Whisper, and My Journey, plus a weekly release from a green `main` instead of a release per pull request. That is BD-2 and BD-3. The risk of cutting is a household that already uses Live; the risk of keeping everything is a quarter that ships none of the promises above.

---

## Top 15 cross-department priorities

| # | IDs | What | Horizon |
|---|---|---|---|
| 1 | ARCH-007, PERF-010 | Required CI and Lint. `main` green before any rollout | Now |
| 2 | PERF-008 | Movies query must not block the event loop | Now |
| 3 | SEC-001, SEC-002 | Thread ownership on chat stream. Role, Youth, and confirm inside agent tools | Now |
| 4 | PRIV-001, ARCH-009, PRIV-005 | Registry-backed purge and account delete, including reviews and avatars. Tombstones so Year in Review cannot resurrect history | Now (PRIV-001 was tagged Next; Critical privacy moves up) |
| 5 | UX-044, PRIV-007, GRO-008, PRD-011 | One youth policy on Continue Watching, newsletter, and nudges | Now |
| 6 | OPS-011, OPS-010, ARCH-008 | Connected means the secret decrypts and the last probe worked. One health fault, not a log flood. Settings writes fail closed | Now |
| 7 | PRIV-002, PRIV-003, PRIV-010 | Snapshot and taste export say whose data they contain. Privacy page matches the code | Now |
| 8 | PERF-007, PERF-011, VIS-014, PRIV-009 | Compress and cache hashed assets. Split the bundle. Self-host fonts | Now |
| 9 | UX-039, SEC-015 | One sign-out that clears the shell and the stored thread id | Now |
| 10 | UX-010, PRD-004 | Chat without an LLM tells the truth and still helps pick a title. Login states the product | Now |
| 11 | SEC-010, PRIV-006 | Per-viewer Continue Watching. “You watched” only from that person’s evidence | Next |
| 12 | OPS-012, OPS-030 | Monday pass as a checklist. Tasks shortlist, full console under Advanced | Next |
| 13 | GRO-007, GRO-014 | Local chat-turn and recommendation-to-play events. No third-party analytics | Next |
| 14 | VIS-001, A11Y-002, A11Y-003 | Ink vs fill tokens. Visible focus | Now |
| 15 | PERF-009 | Nightly verified backups, restore-tested, deletions re-applied after restore | Now, paired with 4 |

---

## Cut list

| ID | Cut |
|---|---|
| PRD-013 | Feature-gravity consolidation: Live, Lobby, Holidays, Journey, Whisper, and Year in Review do not outrank the core loop. Leadership chooses keep, park, or remove in BD-2. |
| A11Y-015 | Stop putting the full changelog in the About DOM. |
| PRIV-009 | Stop loading fonts from Google. Self-host them. |
| Guest tour stub | Security’s foundations table: delete the closed guest-tour route and flag so a settings edit cannot reopen it (SEC, sacred cow). |
| `training-corpus` name | Rename and scope the owner taste export (PRIV-003). |
| Prompt-text as policy | Delete “(owner only)” from tool descriptions as if it were a control (SEC foundations). |

---

## Strengths to protect

| ID | Protect |
|---|---|
| ARCH-001, ARCH-002, PERF-001 | Single-container SQLite WAL, write serializer, numbered migrations |
| SEC-019, SEC-020, SEC-021 | Public handshake, revocable sessions, strict CSP, no raw HTML |
| SEC-024, SEC-025, SEC-030 | MCP mode chosen by key. HLS proxy hides the Plex token. Youth Play fails closed |
| UX-002, GRO-005 | Named kinship on For you. Never fill with anonymous cosine |
| UX-003, OPS-005 | Confirm before *arr writes |
| PRIV-017, PRIV-018 | No phone-home. Every outbound letter opt-in and off |
| OPS-001 | Monday pass as the owner ritual |
| UX-001 | Role gating from one nav source |

---

## Epics

The backlog already groups rows into these epics. Horizons below are the leadership sequence, which overrides a few department tags as noted in the top 15.

| Epic | Goal | Horizon | Success |
|---|---|---|---|
| EP-05 Delivery gates | `main` green, CI required, release only from that | Now | Zero rollouts from a red `main` |
| EP-01 Agent and stream authorization | Stream route and tools use the same policy as REST | Now | Member cannot append to another thread. Member cannot mark a file bad |
| EP-08 Serving reliability | Event loop stays responsive. Backups restore-tested | Now | Health stays under 50 ms while Movies runs. One tested restore |
| EP-03 Personal-data registry | Export, erase, and the Privacy page share one list | Now | Deleted user leaves 0 rows and 0 avatar files |
| EP-02 Youth and per-viewer parity | One policy for list, play, letter, and “you watched” | Now | Youth fixtures: 0 over-ceiling titles on those surfaces |
| EP-04 Settings and integration truth | Connected matches decrypt plus last probe | Now | 0 Connected badges when the key is unset |
| EP-07 Payload and bundle diet | Compression, cache, route splits, self-hosted fonts | Now | 0 third-party font requests. Hashed assets immutable |
| EP-12 Design-system foundation | Ink vs fill, poster fallback, login fields | Now / Next | Contrast pairs documented. Missing art is a designed state |
| EP-13 Accessible interaction | Focus, titles, dialogs, player OSD | Now | Escape leaves Play. Dialogs trap and restore focus |
| EP-06 LLM-optional activation | Honest chat and a first Play without a provider | Now | Unset LLM still ends in a title, and says a model is absent |
| EP-14 Accounts and the people desk | Sign-out, password recovery, Access hygiene, Members safety | Now / Next | Sign-out leaves no prior thread id. Access age visible |
| EP-11 Glossary and copy truth | One curator name. Help matches the rail | Now | 0 storage names in member-facing copy |
| EP-10 Local event spine | Chat turn and play attribution, owner audit, no SaaS analytics | Next | A recommendation-to-play count exists for the household |
| EP-09 Rating moment | End card asks for a rating on a movie | Next | A finished movie can be rated from the end card |
| EP-15 Surface consolidation | Overview “Needs attention”. Monday checklist. Parked satellites | Next | Owner starts Monday from Overview. No fifth new admin app |

---

## Merged roadmap

### Now (0–2 weeks)

Ship in this order. Later items in the week depend on the gate.

1. **EP-05.** ARCH-007, PERF-010. Required checks. Fix the red `main`.
2. **EP-08 and EP-01.** PERF-008. SEC-001, SEC-002. These are correctness, not polish.
3. **EP-04.** OPS-011, OPS-010, ARCH-008. Stop lying about connections. Fail closed on a bad `settings.json`.
4. **EP-03 start.** PRIV-002, PRIV-003, PRIV-010 this week. PRIV-001 and ARCH-009 in the same epic even though purge was tagged Next: it is the only Critical privacy finding.
5. **EP-02 start.** UX-044, PRIV-007, GRO-008, PRD-011. Newsletter, nudges, Continue Watching.
6. **EP-07 start.** PERF-007. VIS-014, PRIV-009. Compression and self-hosted fonts are small.
7. **EP-14 and EP-13 start.** UX-039, SEC-015. A11Y-003, UX-042. Sign-out and Escape.
8. **EP-06 and EP-11.** UX-010, PRD-004, GRO-009. Honest door and one curator name.
9. **EP-12 token fix.** VIS-001, A11Y-002. One ink color, `#735c00`.

Re-prove VIS-027, UX-010’s severity, and OPS-014 on a healthy install before building a poster platform or an Access rewrite around this sidecar’s data.

### Next (2–6 weeks)

- EP-02 finish: per-viewer Continue Watching and copy (SEC-010, PRIV-006).
- EP-03 finish: tombstones (PRIV-005), Settings “Download my data” / “Delete my data” (PRIV-004).
- EP-15: Monday checklist and Tasks shortlist (OPS-012, OPS-030). Access age and bulk deny (OPS-014). Members confirmations (OPS-015).
- EP-10: local chat and play events (GRO-007, GRO-014). Owner security audit (SEC-012).
- EP-09: movie end card with a rating (UX-012, UX-043).
- PERF-009 restore drill, with deletions re-applied.
- Password change and owner reset (SEC-011, OPS-016).
- Bundle route split (PERF-011, ARCH-012) after compression is in.

### Later (6+ weeks)

- Youth data-protection defaults beyond the rating ceiling (PRIV-008).
- “What Projectionist knows about me” over existing tables, not a new diary store (PRIV-024).
- Optional owner TOTP on public-household installs (SEC-031).
- OIDC PKCE and nonce (SEC-005). Vetted AEAD for secrets at rest (SEC-006).
- Trusted-proxy hop count (SEC-003) before any wider publish.
- BD-2 outcomes: implement the keep, park, or remove choices for Live, Lobby, Holidays, Whisper, and My Journey.

**90-day picture.** `main` is green and required. Health stays fast while someone browses Movies. A deleted member is gone from the database and from the next Year in Review. A youth account does not get an over-ceiling title in Continue Watching or the newsletter. Connections is either usable or visibly broken. The household can count recommendations that became plays, on box, without a new vendor.

---

## Self-check

- Cross-examination and red team exist. Five corrections are logged in the affected department changelogs (02, 03, 04, 08, 09).
- CSV row count **237** equals Weakness + Opportunity + Remove across 01–10. IDs match. No Strength rows.
- All ten departments are present. No `force` gaps.
- Every batch reviewed `94fcd3f`.
- No application code was modified in Batch 6.
