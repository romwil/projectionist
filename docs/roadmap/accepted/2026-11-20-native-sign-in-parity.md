# Native clients get the same sign-in as the web, including invites

Dropped 2026-11-20. **Decided by the person:** native handheld clients support every way a person can get into a household on the web: Plex, local username and password, single sign-on (OIDC), **redeeming an invite**, and requesting access. The TV-style code (a signed-in device approves a new one) stays as a secondary path.

This expands **NAT-002** (and SES-001, the same work from the sessions side). Update the item in `docs/NATIVE_CLIENTS.md` and the board; mark it `accepted`.

## What the platform needs

**Every sign-in path can end in a device credential instead of a cookie.** Today Plex PIN, local login/register, OIDC, and invite redemption all end in `curatorx_session`. A native client asks for a device credential instead (proposed: a `client: {"kind": "iphone" | "ipad", "label": "…"}` object on the request) and receives it **once** in the response. The device is created like a paired TV (hashed credential, listed and revocable under Settings → Devices, NAT-005).

| Path | Today | Native need |
|------|-------|-------------|
| Plex | `POST /api/auth/plex/pin`, poll `GET /api/auth/plex/pin/{id}`, `POST /api/auth/plex` (accepts `invite_token`) | Same flow; the final step returns a device credential when the request is a native client's. The PIN nonce cookie must not be required for native callers (bind the PIN to a client-held nonce in the body instead) |
| Local | `POST /api/auth/local/login`, `POST /api/auth/local/register` | Same, returning a device credential |
| Single sign-on | `GET /api/auth/oidc/authorize` → `GET /api/auth/oidc/callback` (accepts `invite_token`) | Authorize with a **native redirect URI** (an allowlisted custom scheme, e.g. `projectionist://auth/callback`) and **PKCE**. The callback redirects to the app with a short-lived, single-use **code** (never the credential in a URL); the app exchanges the code for the credential |
| Invite | `GET /api/invites/validate` (public), `POST /api/invites/redeem/local`; Plex and OIDC take `invite_token` | All three redemption paths return a device credential for native callers. `validate` stays public and returns only what the invite screen needs (inviter display name, role, expiry), never other members' data |
| Request access | `POST /api/access-requests` | Usable from a native client unchanged; confirm it needs no cookie |

**Opening an invite on a phone.** Universal links can't cover every self-hosted household's domain (the app's associated domains are fixed when it's built). So the web **Join** page gets an **Open in the app** link using the app's custom URL scheme, carrying the server's base URL and the invite token. The app can also accept a pasted invite link. The token stays single-use and expiring, exactly as today.

**Capability:** advertise `native_sign_in: 1` in `GET /api/features` (NAT-001) when all of the above ships, so clients show only the paths this server supports. Also expose **which methods this household has enabled** (Plex, local, OIDC, and whether access requests are open) on a public endpoint, so the sign-in screen shows only real options.

## Done when

- A new member can redeem an invite on an iPhone with each enabled method and lands signed in, with the device listed under Settings → Devices.
- An existing member can sign in on an iPhone with Plex, local password, or single sign-on.
- No credential or session token ever appears in a URL; OIDC uses PKCE and a single-use code.
- Rate limits and audit entries match the web paths (same buckets or stricter).
- The capability and the public method list are in the OpenAPI snapshot and fixtures (NAT-003 / NAT-004).

## Sequencing

NAT-002 joins the **contract** lane after NAT-001, or becomes its own lane if the contract lane is busy. It is a security-sensitive change: design → plan → build per `docs/superpowers/`, with a test for every path and the security review check green before merge.

---
## Processing note (agent, 2026-11-20)
- Updated: NAT-002 and SES-001 marked accepted. Every web sign-in path can end in a device credential. The pair-code stays secondary.
- Outbox: 2026-11-20-NAT-002-native.md
- Needs the person: nothing. Security-sensitive; design → plan → build, not started.
