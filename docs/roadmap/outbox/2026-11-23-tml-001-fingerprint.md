# Handoff: timeline file fingerprint

**Date:** 2026-11-23 · **Server item:** TML-001 · **Capability:** `timeline_files` 1

`timeline` stays 0. That name is the asking tool (TML-005).

## What changed

`timeline_files` stores one row per media-file version. The fingerprint is the SHA-256 of size, modification time in nanoseconds, and duration in milliseconds. `POST /api/library/timeline/files` records those numbers for a title in the library. The same numbers return the same row. A different modification time is a new row.

The response is the id, the fingerprint, and the duration. Events are not on it.

## What the client does

- Nothing yet. The asking tool is later. Read `timeline_files` only to know the record exists.

## Done when (client)

- No client change.
