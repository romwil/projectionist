# Handoff: youth join approval

**Date:** 2026-11-23 · **Server item:** SES-009 · **Capability:** `youth_join` 1

Depends on `session_join` 1. Push delivery is NAT-006 and is not part of this item. `push` and `approvals` stay 0.

## What changed

A Youth member joining a session that is looser than their ceiling does not join, even with the screen code. The server stores an approval. The owner reads it at `GET /api/session-approvals` and on the web at Settings → Room approvals.

Approve adds them as a guest and sets the session ceiling. If the playing title is above that ceiling, or unrated, the session pauses and `held_for_ceiling` is true. Play stays refused until the next title. Not now declines. The Youth member's responses do not include the title.

The row expires, is single-use, and the server checks that the member is still in Youth mode and that the caller still owns the session.

When the Youth member leaves, the ceiling stays until the starter changes the title.

## What the client does

- When `youth_join` is at least 1, a pending join is an approval, not a seat.
- Show the title only to the owner.
- Stop the picture when `held_for_ceiling` is true.

## Done when (client)

- The owner can approve or say not now without a push.
- A declined member still cannot see the title.
