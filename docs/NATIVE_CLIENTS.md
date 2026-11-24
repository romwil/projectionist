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
| **Handheld** (iPhone, iPad, Mac) | Every web sign-in path — Plex PIN, local password, OIDC, redeeming an invite, and requesting access — can end in a device credential instead of a cookie. The TV-style code stays as a secondary path | Built (NAT-002 / SES-001). `native_sign_in` is 1 |
| **Handheld via TV** | Scan a QR on a paired TV to sign a phone in as the same member, then confirm on the phone | Proposed, optional |

Every credential is sent as `Authorization: Bearer <credential>`; the server stores only a hash (`hash_secret` in `devices/pairing.py`). Members see and revoke their devices in **Settings → Apple TV** today; *proposed:* that page becomes **Settings → Devices** for every kind.

```bash
# A paired device checks who it is (device bearer)
curl -s -H "Authorization: Bearer YOUR_DEVICE_CREDENTIAL" \
  http://your-host:8788/api/auth/me | python3 -m json.tool
```

### Native sign-in

Send `client` when the caller wants a device credential instead of `curatorx_session`. `kind` is `iphone` or `ipad`. `label` is the name shown under Settings → Apple TV until that page becomes Settings → Devices (NAT-005). The credential comes back once, in the JSON body, and is stored only as a hash. A request without `client` still sets the browser cookie.

`GET /api/features` includes `sign_in` before anyone is signed in:

```json
{ "methods": ["plex", "local", "oidc"], "access_requests_open": true }
```

`methods` is the same list as `auth_methods`. `access_requests_open` is whether `POST /api/access-requests` is accepting requests. That route needs no cookie.

```bash
# Local password. Omit client for the browser cookie.
curl -s -X POST http://your-host:8788/api/auth/local/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"alex","password":"YOUR_PASSWORD","client":{"kind":"iphone","label":"Alex’s iPhone"}}'
```

Plex PIN: `POST /api/auth/plex/pin` with `client` returns `pin_nonce` and does not set the nonce cookie. Poll with header `X-Projectionist-Pin-Nonce`. The header is the nonce, not the device credential. When the PIN completes, the body carries the credential once.

OIDC: `POST /api/auth/oidc/authorize` with `client`, `code_challenge`, and `code_challenge_method` (`S256` only). The provider still redirects to this server’s configured callback. That callback answers `302` to `projectionist://auth/callback?code=…&state=…`. `POST /api/auth/oidc/exchange` with that `code`, the PKCE `code_verifier`, and the same `client` returns the credential. The code is single-use and lasts two minutes. The credential is never in a URL. A client-supplied redirect is not accepted.

Invite: `GET /api/invites/validate?token=…` stays public. The body is the inviter’s display name, the role, the expiry, whether the invite is Youth, and which methods it allows. It does not include another member’s email. `POST /api/invites/redeem/local` with `client` returns a device credential. Plex and OIDC redemption use the same `client` on those paths, plus the invite token they already accept. The Join page links to `projectionist://join?base=<server>&token=<invite>`.

**How this works.** The device row is the same paired-device record a TV gets after a code claim. Revoking it in the household signs that device out. **Honest limit.** The first owner still claims the household in a browser. Native sign-in is for an account that can already be created. `kind` on a code-paired TV stays `tv`. Renaming Settings → Apple TV is NAT-005. A restart drops an in-progress Plex PIN or single sign-on code; start that sign-in again. The household’s identity provider has to accept PKCE. The server does not take a client-supplied redirect.

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
    "shared_sessions": 1,    // SES-004 live channel, commands, clock
    "timeline": 0,           // TML-005
    "tracks": 0,             // TRK-003
    "native_sign_in": 1,     // NAT-002
    "push": 0,               // NAT-006
    "approvals": 0,          // NAT-006
    "cached_art": 1,         // same fact as features.cached_art
    "household_addresses": 1, // home and away on the signed-in payload
    "rooms": 1,              // SES-002 named screens, no playback
    "session_object": 1,     // SES-003 owner, screen, position, level
    "session_join": 1        // SES-005 code or starter approval, guest remote
  }
}
```

```bash
curl -s http://your-host:8788/api/features | python3 -m json.tool
```

- A capability number is that feature’s **contract version**: `0` absent, `1` first contract, `2` a breaking revision. Additive fields do not bump it. `api_contract` is `3`, the first published number. Clients branch on these numbers, not on the server version string.
- `capabilities.cached_art` is `1` while `features.cached_art` is true and `0` when that flag is off. The boolean stays on the signed-in payload only, where EXP-006 put it. The number is on the public payload too, so a client can know before sign-in.
- Clients turn features on by capability. A client facing an older server shows the honest line (*“This Projectionist doesn’t support handheld captions yet.”*) rather than failing.
- `shared_sessions` is `1` when `/api/sessions/{id}/live` accepts commands from the starter and the screen, and events carry `server_time_ms`. A paused playhead does not advance. `session_object` is the record those commands update.
- `session_object` is `1` when `POST /api/sessions` records an owner, a screen, a position, and a level. Other members cannot read it until they join.
- `session_join` is `1` when a member can join a room with the screen's code, or ask the starter. A pending request does not include the title. Guests may send transport commands only after the starter allows the remote. They cannot change the level, the room's captions, or end the session. The join code is not on the session object.
- `rooms` is `1` when `GET /api/rooms` lists named screens. The list does not include what is playing. See [shared sessions](SHARED_SESSIONS.md#rooms).
- `household_addresses` is `1` when this server publishes `addresses.home` and `addresses.away` to a signed-in client. The strings are absent before sign-in. Home is the last origin seen from the home network; away is the owner’s public base URL, or empty. Engine playlist and segment URLs stay relative either way. See [shared sessions](SHARED_SESSIONS.md#home-and-away).
- **Honest limit.** A `0` means this server knows the name and does not offer that contract yet. It is not a hint that the feature is about to appear.
- *Proposed, not on this manifest:* `preroll_warm_start` (ENG-015) and `warmup_screen` (EXP-018). A client treats a missing name the way it treats `0`. Neither name is served until those items ship. ENG-015 adds no route. EXP-018's lines document is *proposed* as `GET /api/playback/warmup-lines`.

---

## The API contract

Native clients ship through app stores on their own clocks, so the API they depend on must not drift silently.

- **OpenAPI snapshot.** `scripts/export-openapi.sh` writes `docs/api/openapi.json` for the routes tagged `client` (NAT-003). It runs with `PROJECTIONIST_EXPOSE_OPENAPI=1` in a throwaway data directory. Production leaves that variable unset, so `/docs` and `/openapi.json` stay off. CI runs `scripts/check-openapi.sh` and fails when the client-facing set changes without a regenerated snapshot.
- **Client-facing set.** The routes a native client may call are tagged `client` and listed in the snapshot: health, features, device pairing and throw-intent, profile, Explore hub, tonight’s table, search, title detail, cached art, playback, the live lineup, and the weather channel (including its audio and image URLs). Admin routes are not in the set. A web member claiming or revoking a device is not in the set either.
- **Fixtures.** `docs/api/fixtures/` holds one recorded example per client route (NAT-004). `scripts/export-fixtures.sh` rewrites them from a test household, and CI runs `scripts/check-fixtures.sh`. A client decodes those files. The Plex token is not in them. Live tune's example is the not-enabled response. Weather audio and map frames' examples are the not-rendered responses; the weather document is the success payload.
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
| NAT-002 | Handheld device credentials for every web sign-in path (done: `client: {kind, label}`, device credential once, client-held Plex nonce, OIDC PKCE plus a single-use code, public invite validate, Join open-in-app link, `native_sign_in: 1`, public `sign_in` list) | pairing (shipped), NAT-001 |
| NAT-003 | OpenAPI snapshot + client-facing route tags + CI drift check (done: `docs/api/openapi.json`) | — |
| NAT-004 | Response fixtures for client-facing routes (done: `docs/api/fixtures/`) | NAT-003 |
| NAT-005 | **Settings → Devices** — store and return device **kind** (`tv` / `iphone` / `ipad`) on claim and list; rename Settings → Apple TV to Devices; page title, empty state, and claim confirmation speak the kind (not always “Apple TV”). Handhelds may use the existing code flow before NAT-002. Waiting client: APL-016 | pairing (shipped) |
| NAT-006 | Push registration (APNs token per device; revoke drops the token) through the publisher relay, because a self-hosted server does not hold the publisher key. Payloads are content-free: `approval_needed`, `something_ready`, or `security_notice`, plus an opaque id. The client fetches the detail. Approval object covers device sign-in (a phone may approve a pair code; the code path stays the fallback; *proposed:* the issuing device names the member first) and Youth join (SES-009). Approvals expire, are single-use, are audited, and re-check authorization. A new device on any NAT-002 path sends `security_notice` to the member’s other devices. Per-member notification preferences. Capabilities `push: 1` and `approvals: 1`. If the relay is down, the same approvals still work in the app and on the web. Ship PRIV-026 the same day. Deep links need ARCH-010 | NAT-002, ARCH-010 |

## See also

- [SECURITY.md](SECURITY.md) — session, rate-limit, and device-credential posture
- [PRIVACY.md](PRIVACY.md) — what leaves the box
