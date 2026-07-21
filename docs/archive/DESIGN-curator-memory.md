# Curator memory design

> **Archived / superseded.** The canonical, maintained version of this design now
> lives in [DESIGN.md](../DESIGN.md) ("Curator memory model" → "Design intent")
> and [ARCHITECTURE.md](../ARCHITECTURE.md) ("Curator memory subsystem"). This
> note is kept for provenance.

v1.8.30 separates durable media knowledge from private partnership memory.

- Repository memory is append-only, sanitized research about people, companies, and titles. It has entity, snapshot, relation, insight, and activity records. It never stores Plex paths, tokens, or credentialed URLs.
- User memory is scoped to one `user_id`: preferences, self-disclosures, learning goals, watch intentions, external watches, and follow-ups.
- Authorization fails closed. A user can read their own memory. An owner can review/export another account only when that account has the owner-set **Youth mode** flag. Adult member memory is never an owner view.
- Export is available to the account holder. Purge hard-deletes that user's notes and chat sessions/messages atomically; shared repository knowledge remains intact.
- Person and company research uses configured official APIs and records public, source-attributed snapshots. Filmography comparison reports only transparent overlap/counts. Idle `entity_memory_enrichment` refreshes a small batch of stale repository entities and never touches private user memory.

`preference_facts` is migrated idempotently into `user_memory_notes`; legacy rows are retained solely as a rollback compatibility source. New account-scoped preference writes use the unified store.
