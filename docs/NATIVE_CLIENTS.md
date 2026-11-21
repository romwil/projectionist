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
| **Handheld** (iPhone, iPad, Mac) | Every web sign-in path — Plex PIN, local password, OIDC, redeeming an invite, and requesting access — can end in a device credential instead of a cookie. The TV-style code stays as a secondary path | Accepted (NAT-002 / SES-001) |
| **Handheld via TV** | Scan a QR on a paired TV to sign a phone in as the same member, then confirm on the phone | Proposed, optional |

Every credential is sent as `Authorization: Bearer <credential>`; the server stores only a hash (`hash_secret` in `devices/pairing.py`). Members see and revoke their devices in **Settings → Apple TV** today; *proposed:* that page becomes **Settings → Devices** for every kind.

```bash
# A paired device checks who it is (device bearer)
curl -s -H "Authorization: Bearer YOUR_DEVICE_CREDENTIAL" \
  http://your-host:8788/api/auth/me | python3 -m json.tool
```

---

## Capabilities

`GET /api/features` is public. It carries `api_contract` and a `capabilities` map on every response, including the stripped payload a client reads before anyone signs in (NAT-001). The signed-in payload still includes `features.cached_art`.

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
    "tracks": 0,             // TRK-003
    "native_sign_in": 0,     // NAT-002 ships → 1
    "push": 0,               // NAT-006
    "approvals": 0,          // NAT-006
    "cached_art": 1          // same fact as features.cached_art
  }
}
```

```bash
curl -s http://your-host:8788/api/features | python3 -m json.tool
```

- A capability number is that feature’s **contract version**: `0` absent, `1` first contract, `2` a breaking revision. Additive fields do not bump it. `api_contract` is `3`, the first published number. Clients branch on these numbers, not on the server version string.
- `capabilities.cached_art` is `1` while `features.cached_art` is true and `0` when that flag is off. The boolean stays on the signed-in payload only, where EXP-006 put it. The number is on the public payload too, so a client can know before sign-in.
- Clients turn features on by capability. A client facing an older server shows the honest line (*“This Projectionist doesn’t support handheld captions yet.”*) rather than failing.
- **Honest limit.** A `0` means this server knows the name and does not offer that contract yet. It is not a hint that the feature is about to appear.

---

## The API contract

Native clients ship through app stores on their own clocks, so the API they depend on must not drift silently.

- **OpenAPI snapshot.** `scripts/export-openapi.sh` writes `docs/api/openapi.json` for the routes tagged `client` (NAT-003). It runs with `PROJECTIONIST_EXPOSE_OPENAPI=1` in a throwaway data directory. Production leaves that variable unset, so `/docs` and `/openapi.json` stay off. CI runs `scripts/check-openapi.sh` and fails when the client-facing set changes without a regenerated snapshot.
- **Client-facing set.** The routes a native client may call are tagged `client` and listed in the snapshot: health, features, device pairing and throw-intent, profile, Explore hub, tonight’s table, search, title detail, cached art, playback, the live lineup, and the weather channel (including its audio and image URLs). Admin routes are not in the set. A web member claiming or revoking a device is not in the set either.
- **Fixtures.** Each client-facing route has a recorded example response under `docs/api/fixtures/`, which client repositories decode in their contract tests. *Proposed (NAT-004).*
- **Deprecation.** A client-facing route changes shape only with a capability bump, and the old shape stays for at least one minor release.

```bash
./scripts/export-openapi.sh
./scripts/check-openapi.sh
```

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
| NAT-001 | Capability manifest + `api_contract` on `GET /api/features` (done: contract 3, map above) | — |
| NAT-002 | Handheld device credentials for every web sign-in path (Plex PIN, local password, OIDC, invite redeem, request access). A native client sends *proposed* `client: {kind, label}` and receives a device credential once instead of `curatorx_session`. Plex PIN nonce is client-held, not a cookie. OIDC uses an allowlisted custom-scheme redirect, PKCE, and a short-lived single-use code exchanged for the credential (the credential never appears in a URL). Invite `validate` stays public and returns only the inviter display name, role, and expiry. The web Join page offers an open-in-app link carrying the base URL and invite token. `native_sign_in: 1` and a public list of enabled methods ship with it. Security-sensitive: design → plan → build | pairing (local work), NAT-001 |
| NAT-003 | OpenAPI snapshot + client-facing route tags + CI drift check (done: `docs/api/openapi.json`) | — |
| NAT-004 | Response fixtures for client-facing routes | NAT-003 |
| NAT-005 | **Settings → Devices** — store and return device **kind** (`tv` / `iphone` / `ipad`) on claim and list; rename Settings → Apple TV to Devices; page title, empty state, and claim confirmation speak the kind (not always “Apple TV”). Handhelds may use the existing code flow before NAT-002. Waiting client: APL-016 | pairing (shipped) |
| NAT-006 | Push registration (APNs token per device; revoke drops the token) through the publisher relay, because a self-hosted server does not hold the publisher key. Payloads are content-free: `approval_needed`, `something_ready`, or `security_notice`, plus an opaque id. The client fetches the detail. Approval object covers device sign-in (a phone may approve a pair code; the code path stays the fallback; *proposed:* the issuing device names the member first) and Youth join (SES-009). Approvals expire, are single-use, are audited, and re-check authorization. A new device on any NAT-002 path sends `security_notice` to the member’s other devices. Per-member notification preferences. Capabilities `push: 1` and `approvals: 1`. If the relay is down, the same approvals still work in the app and on the web. Ship PRIV-026 the same day. Deep links need ARCH-010 | NAT-002, ARCH-010 |

## See also

- [SECURITY.md](SECURITY.md) — session, rate-limit, and device-credential posture
- [PRIVACY.md](PRIVACY.md) — what leaves the box
