# Native and second-screen clients

How a client that is not the bundled web app — an Apple TV, a phone, a tablet, a future Android or desktop app — talks to a Projectionist household: how it signs in, how it learns what this server can do, and how the server keeps its API stable enough for clients that ship on their own schedule.

**Status:** Partly built (Apple TV pairing + throw: `projectionist/devices/`, `web/device_routes.py`), the rest proposed. Item IDs (`NAT-…`) are tracked in [docs/roadmap/](roadmap/README.md).
**Audience:** Developers / client authors.
**Related:** [SHARED_SESSIONS.md](SHARED_SESSIONS.md) · [PLAYBACK_ENGINE.md](PLAYBACK_ENGINE.md) · [SECURITY.md](SECURITY.md) · [PRIVACY.md](PRIVACY.md) · [MCP.md](MCP.md)

Jump to: [Principles](#principles) · [Sign-in](#signing-in) · [Capabilities](#capabilities) · [Contract](#the-api-contract) · [Clients](#known-clients) · [Items](#roadmap-items)

---

## Principles

1. **The server is the source of truth.** Clients render; they do not decide library reach, Youth ceilings, or what a track contains.
2. **Clients ask, they don’t guess.** A client learns what this server supports from a capability manifest, not by comparing version strings.
3. **Credentials are per device.** A device gets its own revocable credential. Browser cookies (`curatorx_session`) never leave the browser.
4. **Same privacy rules as the web.** No client sees file paths, Plex tokens, or another member’s taste. The browse privacy schema (`library_privacy.py`) applies to every client.
5. **The AGPL boundary is the HTTP API.** A client that only talks to this API is a separate program. Clients must not copy this repository’s Python or React; if a client wants shared logic, it is reimplemented against the documented contract.

---

## Signing in

| Device kind | How it signs in | Status |
|-------------|-----------------|--------|
| **TV** (Apple TV) | Shows a code (`XXXX-XXXX`, no 0/O/1/I, 5-minute lifetime); a signed-in web member enters it; the TV polls and receives its credential once | Built (local work: `POST /api/devices/pair/issue`, `…/rotate`, `GET …/pending/{id}`, `POST …/claim`, `POST /api/devices/{id}/revoke`) |
| **Handheld** (iPhone, iPad, Mac) | Native sign-in with the methods the household already offers — Plex PIN (system web auth sheet), local password, OIDC — exchanged for a device credential instead of a cookie | Proposed (NAT-002 / SES-001) |
| **Handheld via TV** | Scan a QR on a paired TV to sign a phone in as the same member, then confirm on the phone | Proposed, optional |

Every credential is sent as `Authorization: Bearer <credential>`; the server stores only a hash (`hash_secret` in `devices/pairing.py`). Members see and revoke their devices in **Settings → Apple TV** today; *proposed:* that page becomes **Settings → Devices** for every kind.

```bash
# A paired device checks who it is (device bearer)
curl -s -H "Authorization: Bearer YOUR_DEVICE_CREDENTIAL" \
  http://your-host:8788/api/auth/me | python3 -m json.tool
```

---

## Capabilities

`GET /api/features` is already public. *Proposed (NAT-001):* it gains a `capabilities` map and an `api_contract` number:

```jsonc
{
  "api_contract": 3,
  "capabilities": {
    "device_pairing": 1,
    "throw": 1,
    "playback_engine": 0,    // ENG-003 ships → 1
    "caption_tracks": 0,     // ENG-004
    "shared_sessions": 0,    // SES-004
    "timeline": 0,           // TML-005
    "tracks": 0              // TRK-003
  }
}
```

- A capability number is that feature’s **contract version**: `0` absent, `1` first contract, `2` a breaking revision. Additive fields do not bump it.
- Clients turn features on by capability. A client facing an older server shows the honest line (*“This Projectionist doesn’t support handheld captions yet.”*) rather than failing.

---

## The API contract

Native clients ship through app stores on their own clocks, so the API they depend on must not drift silently.

- **OpenAPI snapshot.** *Proposed (NAT-003):* `scripts/export-openapi.sh` writes `docs/api/openapi.json` (generated with `EXPOSE_OPENAPI=1`, which stays off in production). CI fails when routes in the client-facing set change without the snapshot being regenerated.
- **Client-facing set.** The routes a native client may call are tagged (`tags=["client"]`) and listed in the snapshot. Admin routes are not in the set.
- **Fixtures.** Each client-facing route has a recorded example response under `docs/api/fixtures/`, which client repositories decode in their contract tests.
- **Deprecation.** A client-facing route changes shape only with a capability bump, and the old shape stays for at least one minor release.

---

## Known clients

| Client | Repository | Notes |
|--------|------------|-------|
| Web app | this repo (`frontend/`) | The reference client |
| Native clients (e.g. Apple TV, phone, tablet) | separate repositories | Talk to this API only. Coordinated through the shared roadmap item IDs below |
| MCP clients | this repo (`projectionist/mcp/`) | See [MCP.md](MCP.md) |

**Coordination.** Work that spans this server and a client carries one shared item ID (`ENG-…`, `SES-…`, `TML-…`, `TRK-…`, `NAT-…`). The server item lands first, behind a capability; the client item references it. See [docs/claude.roadmap.md](claude.roadmap.md) for how roadmap drops are processed.

---

## Roadmap items

| ID | Item | Depends on |
|----|------|------------|
| NAT-001 | Capability manifest + `api_contract` on `GET /api/features` | — |
| NAT-002 | Handheld device credentials via native sign-in (Plex PIN / local / OIDC) | pairing (local work) |
| NAT-003 | OpenAPI snapshot + client-facing route tags + CI drift check | — |
| NAT-004 | Response fixtures for client-facing routes | NAT-003 |
| NAT-005 | **Settings → Devices** — store and return device **kind** (`tv` / `iphone` / `ipad`) on claim and list; rename Settings → Apple TV to Devices; page title, empty state, and claim confirmation speak the kind (not always “Apple TV”). Handhelds may use the existing code flow before NAT-002. Waiting client: APL-016 | pairing (shipped) |
| NAT-006 | Push registration for native clients (APNs token per device). APNs needs the app publisher’s key, so a self-hosted server pushes through the publisher’s relay; *proposed:* pushes are **content-free** (“Something is ready in Projectionist”) and the app fetches the detail from the household server, so no title ever crosses the relay. Ship PRIV-026 panel the same day. Deep links need ARCH-010 SPA fallbacks | NAT-002, ARCH-010 |

## See also

- [SECURITY.md](SECURITY.md) — session, rate-limit, and device-credential posture
- [PRIVACY.md](PRIVACY.md) — what leaves the box
