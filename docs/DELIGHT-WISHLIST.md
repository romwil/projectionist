# Delight wishlist

Living backlog for experiences that make CuratorX feel more generous. Tags are target persona and priority; promotion into a delivery plan remains an owner decision.

## Human personas

### Owner / Curator
- **Must:** at-a-glance library health and an issue-queue badge in navigation; one-click grooming/enrichment rerun; safe undo for the last bulk action.
- **Love:** curated collections/courses (for example, a Kurosawa deep-dive) published to members; a weekly digest of library and member-request changes; Youth-account moderation dashboard.
- **Like:** scheduled seasonal rails; export/import of lenses and curated lists.

### Adult household member
- **Must:** a fast answer to “where can I watch this / is it here?”; instant-feeling synced watchlist and lists; resume/continue-watching surfaced.
- **Love:** a personalized weekly rail with a persona-voiced why; chat-from-here on every rail; a visible, tunable taste profile; arrival notifications for gap titles.
- **Like:** shareable saved pages; mood-tuned surprise picks; watch-party/recommend-to-household flourishes.

### Youth member
- **Must:** age-appropriate results and moderated memory; a clear, friendly persona voice; simple big-poster browsing.
- **Love:** gentle movie-learning explainers; genre exploration badges/streaks; ask-the-curator guardrails.
- **Like:** themed kid rails and a pick-for-me spinner.

### Guest / visitor
- **Must:** browse without owner-only data; an obvious sign-in route; no destructive actions.
- **Love:** a public-friendly “what’s great here” tour and request-access flow.
- **Like:** a taste quiz that can seed a profile after joining.

## AI curator archetype votes

These votes are derived from the current persona-template spectrum: energetic Enthusiast, analytical Scholar, attentive Concierge, and warm Companion. Each is framed as a constraint in today’s toolset, not a promise to users.

### The Enthusiast
- **Must:** “I could delight users more if I could react to what they are watching right now.”
- **Love:** “I could delight users more if I could send a timely, opt-in ‘you have to see this’ nudge.”
- **Like:** “I could delight users more if I could share a relevant GIF or clip in chat.”

### The Scholar
- **Must (✅ shipped 1.10.0):** “I could delight users more if I could rely on durable cited knowledge for claims about style and technique.” — repository memory now persists source-cited research snapshots and insights (`research_*`, `recall_repo_memory`, `save_repo_insight`).
- **Love:** “I could delight users more if I could build a multi-session film-course syllabus.”
- **Like:** “I could delight users more if I could render footnote-style source citations inline.”

### The Concierge
- **Must (✅ shipped 1.10.0):** “I could delight users more if I could remember intentions and safely follow up on promises.” — per-user `follow_up` / `watch_intention` notes drive a "resume where we left off" line in the per-turn prompt.
- **Love:** “I could delight users more if I could coordinate an opt-in cross-service path from availability to acquisition.”
- **Like:** “I could delight users more if I could suggest around a member’s calendar, weekends, and holidays.”

### The Companion
- **Must (✅ shipped 1.10.0):** “I could delight users more if I could retain safe long-term memory of who a member is while respecting Youth/adult privacy.” — fail-closed per-user memory (`user_memory_notes` via `UserMemoryService`; owner review limited to Youth-flagged accounts).
- **Love:** “I could delight users more if I could tune a pick from a quick mood check-in.”
- **Like:** “I could delight users more if I could remember consented in-jokes and callbacks.”
