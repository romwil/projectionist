# Agents merge their own PRs (standing rule), then continue

Dropped 2026-11-19. **Decided by the person:** agents merge their own PRs; the person does not need to merge them. Process this drop now.

## The rule

An agent merges a PR it opened **when every required `main` CI check is green**, the per-PR gate in `docs/RELEASE.md`:

```bash
gh pr checks --watch
gh pr merge --merge --delete-branch     # merge commit, matching the repo's history
git checkout main && git pull --ff-only
```

- **Never bypass:** no `--admin`, no direct push to `main`, no disabling or skipping checks.
- **A required check fails:** fix it on the same branch and watch again. Stop and report after two failed fix attempts, or when the failure is unrelated to the change (flaky or infrastructure).
- **A merge is not a release:** no version bump, tag, Hub publish, CA proof, or rollout unless the person asks (`docs/RELEASE.md` unchanged).
- **Still the person’s call:** history rewrites and force-pushes (“yes, rewrite history”), and anything `docs/RELEASE.md` reserves for the person (prod rollout).

## Do now

1. On the open branch `docs/roadmap-inbox-2026-11-19`:
   - `docs/claude.roadmap.md` §5: replace “Do **not** commit unless the person asks” with: commit roadmap work on a branch, open a PR, and merge it under the rule above. Implementation still starts only when an item is picked up.
   - `docs/claude.roadmap.md` §7 *Never*: add “merge by bypassing required checks.”
   - `.cursor/rules/roadmap.mdc`: replace “No implementation, no commits, no release rituals unless the person asks” with “Commit and merge roadmap work via PR when required CI is green (never bypass); no implementation or release rituals unless the person asks.”
   - Add the decision to the board’s *Decisions* table.
   - Move this drop to `accepted/` with a processing note.
2. Push, then **merge that PR** under the rule.
3. Continue `accepted/2026-11-19-01-next-steps.md` from step 2, merging each PR under the rule. The only stop left there is the final “yes, rewrite history” before the force-push in step 3. Start Lanes A and B (steps 4–5) as soon as step 1’s PR is merged.

---
## Processing note (agent, 2026-11-19)
- Created: (none — standing merge rule, not a board item)
- Updated: `docs/claude.roadmap.md` §5 (commit + merge via PR when required CI is green) and §7 (never merge by bypassing required checks); `.cursor/rules/roadmap.mdc` matching line; board Decisions row for agents-merge-own-PRs
- Also recorded: history purge completed under `accepted/2026-11-19-01-next-steps.md` (step 3)
- Outbox: none
- Needs the person: nothing for this rule; optional GitHub Support request to GC `refs/pull/*` / cached views (draft in agent report, not sent)
