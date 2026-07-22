# Documentation style — the CuratorX standard

CuratorX treats documentation as a **first-class deliverable**, on the same footing as the code and the "explain the why" education commitment that already runs through the product. A feature is not done when it works; it is done when a real person can understand it, use it, and trust it without reading the source.

This page is the durable standard every user-facing doc is held to. It is also written to its own rubric, so it doubles as a worked example: read it once as a guide, and again as a template.

**Who must follow it:** anyone changing a document under `docs/`, the `README`, in-app copy rendered from markdown (`/help`, `/privacy`), release notes, or member-facing UI strings.

Jump to: [The bar](#the-bar) · [Audience & voice](#audience--voice-matrix) · [Worked examples](#worked-examples-and-runnable-snippets) · [E-E-A-T checklist](#e-e-a-t-trust-checklist) · [Release notes](#release-notes-highlights-convention) · [Definition of done](#definition-of-done-for-docs)

---

## The bar

World-class technical communication: **warm and engaging, but demonstrably authoritative.** The reader should finish a section feeling that the author deeply understands a complex thing — and then made it feel simple. Warmth is the voice; it is never a substitute for substance.

Concretely, every doc in scope meets the following.

### Quality rubric

- **Task-first structure.** Each section answers "what am I trying to do?", then shows the shortest path, then the deeper explanation. Lead with the outcome, not the mechanism. A reader skimming only the first sentence of each section should still learn what the feature is for.
- **Show, don't assert.** Replace bare claims with a worked example. For members that means a real chat prompt and the kind of answer it yields; for owners/developers it means a runnable command or config block. No capability is described without at least one example.
- **Copy-pasteable where the audience is technical.** Owner/operator/developer guidance uses fenced code blocks — `bash`/`curl`, `docker run` / Compose YAML, `settings.json` / env excerpts — that are correct and self-contained. A reader should be able to paste and run without editing anything except obvious placeholders (`YOUR_KEY`, `your-host`).
- **Right audience, right depth.** Members get plain-language actions and example prompts, never raw HTTP verbs. Owners get the API/config depth, with examples. The same capability can appear twice at two depths (a guided UI action for members, a `curl` snippet for owners).
- **Trust signals.** Each non-trivial feature carries a compact "How this works" note plus honest limits and caveats. Say why knowledge-coverage bars start sparse; say what a repair will *not* do. Authoritative beats salesy.
- **Scannability & consistency.** Consistent heading hierarchy (headings are deep-link anchors — don't reword them casually), short intros, bullet steps, callouts for gotchas, and a "See also" cross-link between related sections. Terminology matches the **actual in-app labels** exactly (e.g. "Scheduled Tasks", "Plot Lab", "Lights Down", "Report issue").
- **Accessible & theme-safe rendering.** In-app docs (`/help`, `/privacy`) must render cleanly in both **Lights Up** and **Lights Down** themes. Use fenced code blocks with a language hint so syntax colors and contrast come from the shared markdown styles. Never rely on color alone to convey meaning; keep tables narrow enough to wrap.

---

## Audience & voice matrix

CuratorX documentation serves three audiences. Pick the audience per document (or per section), and match the voice and the evidence type.

| Audience | Where they read | Voice | Evidence they need | Never show them |
|----------|-----------------|-------|--------------------|-----------------|
| **Member** (household user) | In-app `/help` (member half), `/privacy` | Warm, plain-language, encouraging. Second person ("you"). | **Example chat prompts** and the kind of reply they yield; step-by-step "how to get X" using in-app labels and menus. | Raw HTTP verbs, `settings.json` keys, table names, env vars. |
| **Owner** (server operator) | In-app `/help` (`## For owners`), `docs/ONBOARDING.md`, `docs/FAQ.md`, `docs/CONFIGURATION.md` | Warm but precise; assumes comfort with Docker and a terminal. | **Runnable snippets** — `curl`, Compose YAML, `settings.json`/env excerpts — plus "how it works / why it matters" and honest limits. | Marketing fluff; hand-waving about what a command does. |
| **Developer / contributor** | GitHub-only: `README.md`, `docs/WEB_UI.md`, `docs/ARCHITECTURE.md`, `docs/DATA_MODEL.md` | Direct, technical, terse. | Accurate routes, schemas, quickstart commands that actually run. | Warmth for its own sake; member-style repetition. |

**The render split is real and load-bearing.** `frontend/src/pages/HelpPage.jsx` (`markdownForRole`, ~127–140) drops everything from the first `## For owners` heading down to `## Related documentation` for members and guests. So:

- Owner-only depth (API endpoints, `curl`, config keys) belongs **below** `## For owners` in `docs/HELP.md`, where members never see it.
- A member-facing endpoint reference (e.g. "export your memory") must be **restated as a guided UI action** in the member half — "Export or delete your private memory from **Settings → Privacy**" — not a `GET /api/me/memory` line.
- Do not rename the `## For owners` heading or the anchor headings the app links to (`#start-here`, `#chat`, `#plot-lab`, `#coverage-over-time`, etc.) without updating `HelpPage.jsx` and `PrivacyPage.jsx`.

---

## Worked examples and runnable snippets

Every non-trivial capability gets at least one example. Choose the form by audience.

### Member example (prompt → outcome)

Show the prompt a member would actually type, then describe the shape of the answer — not a fabricated transcript, but an honest "here's what you get back".

> **You ask:** "What should we watch tonight, something under two hours I haven't seen?"
>
> **Your curator replies** with a short shortlist drawn from *your* library — each pick has a one-line "why this fits" and a **Play** button when the title has a Plex match. Follow-up chips like *"only comedies"* or *"something older"* let you refine without retyping.

### Owner example (runnable, self-contained)

A snippet an owner can paste. Include the host/port and an obvious placeholder for secrets. Prefer showing the *outcome* (a trimmed response) too.

```bash
# Check how complete the curator's plot knowledge is (owner host)
curl -s http://localhost:8788/api/library/knowledge-coverage | python3 -m json.tool
# → {"overview_pct": 98, "embeddings_pct": 91, "motifs_pct": 63, "neighbors_pct": 44, ...}
```

### Config / env example

```jsonc
// {DATA_DIR}/settings.json — turn off the Wikipedia long-synopsis trickle
{
  "long_synopsis_source": "off"   // "wikipedia" (default) | "omdb" | "auto" | "off"
}
```

**Rules for snippets**

- They must be **correct** against the shipped code. Verify endpoints, flags, and keys before writing them.
- Self-contained: no invisible prior step. If a step is required first, show it.
- Placeholders are obvious (`YOUR_TMDB_KEY`, `your-unraid-ip`), never real secrets.
- Fenced, with a language hint (` ```bash `, ` ```yaml `, ` ```jsonc `) so they render legibly in both themes.

---

## E-E-A-T trust checklist

E-E-A-T — Experience, Expertise, Authoritativeness, Trustworthiness — is how a reader decides whether to believe a doc. Before publishing, confirm each:

- [ ] **Experience** — the guidance reads as if written by someone who has actually run this path (real defaults, real gotchas, the thing that trips people up).
- [ ] **Expertise** — a short "how it works" explains the mechanism so the advice is understood, not just followed.
- [ ] **Authoritativeness** — claims are specific and verifiable (exact table names in `docs/`, exact endpoints for owners, exact in-app labels for members). No vague "handles your data securely".
- [ ] **Trustworthiness** — honest limits are stated plainly. What the feature will **not** do, when it can fail, and what the fallback is. Privacy/security claims match the shipped behavior exactly — if unsure, read the code first.
- [ ] **No hand-waving on data & safety.** Export/purge maps, MCP exposure, and "what leaves the box" are specific and current.

---

## Release notes: Highlights convention

Release notes reach real people. `CHANGELOG.md` feeds `frontend/public/release-notes.json` via [scripts/generate-release-notes.sh](../scripts/generate-release-notes.sh), which surfaces on the About page and the **What's New** modal.

Every release gets a **two-part** CHANGELOG entry:

1. A short **`### Highlights`** block — benefit-led, "what this means for you", written for a member/owner reading the modal. Two to four bullets, no jargon.
2. The existing technical sections (`### Added` / `### Changed` / `### Fixed` / `### Verification`) — the engineering record.

The generator promotes a `### Highlights` section into a top-level `highlights` array; the What's New modal leads with that human copy while the changelog keeps the engineering detail. If a release omits `### Highlights`, the generator falls back to the old behavior (no breakage).

```markdown
## [1.13.0] — 2026-07-20

A short one-line summary of the release.

### Highlights
- **Help that teaches.** The in-app guide now walks you through real tasks with example prompts and copy-paste commands.
- **A clear privacy map.** Exactly what "export" and "purge" cover — no guesswork.

### Added
- ...technical bullets...
```

**Forward-only.** Adopt this per release going forward. Do not retroactively rewrite old entries.

---

## Definition of done for docs

A user-facing change is not done until:

- [ ] The relevant guide (`HELP.md`, `PRIVACY.md`, `ONBOARDING.md`, `FAQ.md`, `README`, `WEB_UI.md`, …) is updated **in the same PR** as the code.
- [ ] Every new/changed capability has at least one worked example (prompt for members, runnable snippet for owners/devs).
- [ ] Member prose contains no raw HTTP verbs, config keys, or table names; those live in the owner/developer sections only.
- [ ] Terminology matches the in-app labels exactly.
- [ ] Honest limits and a "how it works" note accompany each non-trivial feature.
- [ ] `/help` and `/privacy` render cleanly in **Lights Up** and **Lights Down**, code blocks legible in both, and the owner render split still hides owner-only depth from members.
- [ ] Deep-link anchors the app relies on still resolve (see [WEB_UI.md](WEB_UI.md) → Help & knowledge).
- [ ] The CHANGELOG entry includes a benefit-led **`### Highlights`** block.

If you can't check a box, the doc isn't finished — the same way a failing test blocks a merge.

---

## See also

- [HELP.md](HELP.md) — in-app Help (`/help`); the member/owner render-split exemplar
- [PRIVACY.md](PRIVACY.md) — the authoritative data map exemplar
- [WEB_UI.md](WEB_UI.md) — routes, Help anchors, and how docs render in-app
- [TESTING.md](../TESTING.md) · [docs/TESTING.md](TESTING.md) — the docs gate in the release checklist
- [RELEASE.md](RELEASE.md) — version bump, CHANGELOG, GitHub release, Docker Hub ship steps
- `.cursor/rules/docs-style.mdc` — the enforcement rule that points every future change back here
- `.cursor/rules/release.mdc` — points agents at `RELEASE.md` for ship work
