# Curator memory design

v1.8.29 separates durable media knowledge from private partnership memory.

- Repository memory is append-only, sanitized research about people, companies, and titles. It has entity, snapshot, relation, insight, and activity records. It never stores Plex paths, tokens, or credentialed URLs.
- User memory is scoped to one `user_id`: preferences, self-disclosures, learning goals, watch intentions, external watches, and follow-ups.
- Authorization fails closed. A user can read their own memory. An owner can review/export another account only when that account has the owner-set **Youth mode** flag. Adult member memory is never an owner view.
- Export is available to the account holder. Purge hard-deletes that user's notes and chat sessions/messages atomically; shared repository knowledge remains intact.

`preference_facts` is migrated idempotently into `user_memory_notes`; legacy rows are retained solely as a rollback compatibility source. New account-scoped preference writes use the unified store.
