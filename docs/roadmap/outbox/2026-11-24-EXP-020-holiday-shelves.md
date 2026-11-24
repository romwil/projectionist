# Outbox handoff — EXP-020 holiday shelves

**Server item:** EXP-020
**Capability:** `holiday_shelves` is `1` on `GET /api/features`.

This handoff is the platform contract. Client screens and layouts stay in the client repository.

The seasonal rail (`seasonal_spotlight` on the explore hub, and `GET /api/library/feeds/seasonal-spotlight`) may include:

- `theme`: one line stored with the shelf. The header is the holiday name, then this line. An empty theme means the header is the name only.
- `shelf_role` on a pick: `Classic`, `Family`, `New this year`, `Deep cut`, or `After bedtime`.
- `curator_note` (also copied to `why` when `why` is empty).
- `matched_because`: the signal the curator named. Owner preview uses it. Members see the note.

A pick with an empty note is not on the member rail. A Youth response omits every pick whose `shelf_role` is `After bedtime`, even when the content rating would otherwise pass.

A missing `holiday_shelves` name means the client shows the holiday name and any note already on the card.

**Depends on:** a server that has shipped this capability. It is not in the 1.46.1 image.
