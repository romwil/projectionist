# Processing roadmap drops (instructions for Cursor and Claude agents)

You are an agent working in the **Projectionist** server repository. A person drops roadmap material into `docs/roadmap/inbox/` — a pasted idea, a design conversation, a bug list, a handoff from a client repository. This file tells you how to turn each drop into tracked, well-specified work **without building anything** unless the person asks.

Read this whole file before touching the inbox.

---

## 1. Know the shape of the roadmap

| Path | What lives there |
|------|------------------|
| `docs/roadmap/README.md` | **The board.** Every item ID, title, status, and owning doc. The single list of what is planned |
| `docs/roadmap/inbox/` | Raw drops, as the person wrote them. Never edit a drop’s content; you only move it |
| `docs/roadmap/accepted/` | Drops you processed, renamed `YYYY-MM-DD-<ID or topic>.md`, with a processing note appended |
| `docs/roadmap/outbox/` | Handoffs **to** client repositories (see §6). Client agents read from here |
| Owning docs | Where an item’s design lives: [PLAYBACK_ENGINE.md](PLAYBACK_ENGINE.md) (ENG), [SHARED_SESSIONS.md](SHARED_SESSIONS.md) (SES), [TIMELINE.md](TIMELINE.md) (TML), [TRACKS.md](TRACKS.md) (TRK), [NATIVE_CLIENTS.md](NATIVE_CLIENTS.md) (NAT), [PRODUCT.md](PRODUCT.md) for everything else |
| `docs/superpowers/specs/` | Full design specs for items too big for a table row (existing convention) |

ID prefixes are fixed: `ENG` playback engine · `SES` shared sessions · `TML` timeline layer · `TRK` tracks · `NAT` native-client contract · `EXP` experience convergence (approved 2026-11-18) · `PRD` product (existing series in `docs/reviews/`) · `OPS`, `PRIV`, `PERF`, `GRO`, `UX` (existing review series). A new prefix needs the person’s approval.

## 2. Read before you write

For every drop, read first:

1. The drop itself, fully.
2. `docs/PRODUCT.md` — positioning, the **Live scope freeze (PRD-007)**, and *Parked / sunset* non-goals.
3. The owning doc(s) the drop touches, and the board.
4. `docs/PRIVACY.md` and `docs/SECURITY.md` if the drop touches data, accounts, devices, or anything that leaves the box.
5. `docs/DOCS_STYLE.md` — every doc you change is held to it.

Never ask the person something these documents already answer.

## 3. Classify each drop

| The drop is… | Do this |
|--------------|---------|
| A **new capability** | Create item(s) with the next free number in the right prefix |
| A **change to an existing item** | Update that item in its owning doc; note the change on the board |
| A **bug or regression** | Do not create a roadmap item. Write it into the accepted note as “belongs in issues” and tell the person |
| A **question or idea without a decision** | Record it under the owning doc’s *Open decisions*; no item yet |
| **Cross-repo** (needs a client to change too) | Create the server item here **and** an outbox handoff (§6) |
| In conflict with a **freeze, non-goal, or privacy principle** | Do not create the item. Explain the conflict in the accepted note and ask the person |

One drop can produce several items. Split by what ships independently.

## 4. Write each item to the standard

Each item gets a row on the board and a section (or table row plus detail) in its owning doc with:

- **ID and title** — imperative, specific (“WebVTT caption renditions in the master playlist”).
- **Why** — the household outcome, in one or two sentences.
- **Done when** — observable, testable acceptance lines. Prefer “a member can…” and “`curl …` returns…”.
- **Depends on** — item IDs only.
- **Client contract** — for anything a client calls: routes, payload sketch, the capability name and number it ships behind ([NATIVE_CLIENTS.md](NATIVE_CLIENTS.md#capabilities)).
- **Honest limits** and **privacy notes** where they apply.
- **Status** — `proposed` → `accepted` (person approved) → `in progress` → `shipped (x.y.z)` → `done`; or `parked` / `declined` with a reason.

Mark anything you inferred as *Proposed:* — never present your own call as the person’s decision.

## 5. Finish the drop

1. Move the drop from `inbox/` to `accepted/` with the new name, and append:

   ```markdown
   ---
   ## Processing note (agent, YYYY-MM-DD)
   - Created: ENG-0NN, ENG-0NN (next free numbers)
   - Updated: SES-004 (added `rate` command)
   - Outbox: YYYY-MM-DD-ENG-0NN-<client>.md
   - Needs the person: <question, or “nothing”>
   ```

2. Update the board.
3. Summarize to the person in a few lines: what you created, what conflicts or questions remain.

Do **not** commit unless the person asks. Do not start implementation; picking an item up for building is a separate request that follows the repo’s normal design → plan → build flow (`docs/superpowers/`).

## 6. Coordinating with client repositories

Clients (the web app here, and separate native clients such as the Apple apps) depend on this server. The rules that keep both sides shipping cleanly:

1. **The server lands first, behind a capability.** A client feature never depends on an unreleased server shape. The server item ships with its capability number in `GET /api/features` (NAT-001).
2. **The contract is a file.** When a client-facing route changes, regenerate `docs/api/openapi.json` and the matching fixture in `docs/api/fixtures/` (NAT-003, NAT-004) in the same change.
3. **Handoffs go to the outbox.** For a cross-repo item, write `docs/roadmap/outbox/YYYY-MM-DD-<ID>-<client>.md` with: the item ID, the capability and version, the routes and payloads (link the fixtures), what the client must render or call, and the *Done when* lines that need the client. Client agents read this folder; this repository never writes into a client repository.
4. **Requests from clients arrive in the inbox.** A client agent may drop a request here (“we need `rate` in the session commands”). Process it like any drop. Client drops must describe **platform needs only** — this repository is public, so proprietary client designs do not belong in it.
5. **Shared IDs, one owner.** The server owns `ENG / SES / TML / TRK / NAT`. A client references them; it does not renumber them.

## 7. Never

- Never edit a drop’s original text; never delete a drop.
- Never reopen parked or frozen work (Tunarr orchestration, HDHomeRun attach, Live new channel types) — say why instead.
- Never invent endpoints as if they ship; mark them *Proposed*.
- Never run release rituals (Hub publish, tags, rollout) as part of roadmap processing.
- Never paste proprietary client material into this repository.
