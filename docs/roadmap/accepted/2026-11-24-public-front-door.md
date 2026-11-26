# Drop: a public front door — app login only, no Cloudflare Access

**From:** Will (via design chat) · **Date:** 2026-11-24 · **Type:** security (SEC series; next free numbers) · **Owning doc:** `docs/SECURITY.md`

## Context

Some household members can't use the Zero Trust client. The plan is to remove the Cloudflare Access login on `projectionist.automat.vip` and rely on Projectionist's own sign-in over HTTPS, through the existing tunnel. Production moves to its own LAN IP (separate change). The perimeter is already default-deny with an explicit public list. These items close what's left. **Access stays on until every item marked (gate) is merged, released and verified.**

## Server items

1. **(gate) Client IP behind Cloudflare.** `rate_limit.client_ip` trusts the first `X-Forwarded-For` hop, which clients can spoof. Instead:
   - Use `CF-Connecting-IP` **only** when the direct peer is the tunnel connector (a configured trusted-proxy list or address). Otherwise use the peer address.
   - Never use the first XFF hop from an untrusted peer.
   - Tests: spoofed XFF/CF headers from a non-trusted peer don't change the key; two real clients through the trusted proxy get separate buckets.
2. **(gate) Per-account throttling:**
   - failed sign-ins per username and per invite token, with exponential backoff and a temporary lock (for example 10 failures → 15 min, growing);
   - a generic error that doesn't reveal whether an account exists;
   - the owner sees lock events in Admin → Health and Logs.
3. **(gate) Owner accounts need a second factor:**
   - the owner and any admin role sign in only through Plex or OIDC (which carry the provider's 2FA), **or** through local password plus TOTP (new: enroll with recovery codes, required for owner/admin when local login is enabled);
   - members may keep local passwords, with a minimum-strength check against a breached-password list (offline, k-anonymity, or a bundled list);
   - an owner setting can require TOTP for everyone.
4. **(gate) Public-exposure interlock that understands the tunnel:**
   - a request carrying Cloudflare headers (`cf-ray`, `cf-connecting-ip`) from the trusted connector is **external**, whatever the peer address;
   - if a public base URL or away address is configured, household login (multi-user) **cannot** be turned off, and setup mode can't be re-entered from an external request.
5. **(gate) Cache headers for private content:**
   - `Cache-Control: private, no-store` (or `private, max-age=…` where needed) on art, engine playlists and segments, library-path playlists and segments, subtitles, avatars, and every `/api/` response;
   - static assets keep long public caching;
   - test the headers per route group.
6. **(gate) Anonymous `/api/features`** returns only what sign-in needs: capability flags and sign-in methods. **No** home or away addresses, server names, library facts or version detail beyond what clients need. Test it as anonymous.
7. **Origin check for cookie-authenticated writes:** reject unsafe methods whose `Origin`/`Referer` isn't the configured public origin or the LAN origin (bearer-token clients are exempt). Test it.
8. **`/mcp` is LAN-only by default:**
   - refuse external requests (per item 4's rule) unless the owner enables "remote MCP";
   - log MCP auth failures.
9. **New sign-in notices:** a new device or browser signing in to any account notifies the owner (inbox now, push with NAT-006) and the account holder (email if set). The owner can revoke from Settings → Devices.
10. **Public surface review:** walk every entry in `PUBLIC_HANDSHAKE_EXACT` and the path-token patterns (engine media, PIN poll, pair pending). Confirm the token entropy (≥128 bits), TTLs and rate limits, and that no response reveals whether an account exists. Record the findings in `docs/SECURITY.md`.

## Infrastructure (Cloudflare, via API; plan first, apply after the owner approves)

- WAF: the Cloudflare managed ruleset on (the free plan has one), Bot Fight Mode on.
- Rate-limiting rule (edge) on `/api/auth/*`, `/api/invites/*`, `/api/access-requests`, `/api/devices/pair/*`.
- Custom rule: block `/mcp*`, `/docs*`, `/redoc*` and `/openapi.json` on the public hostname.
- Optional: a country allow-list, if the owner wants it.
- SSL/TLS: Full; Always Use HTTPS; HSTS (after confirming everything works over HTTPS); minimum TLS 1.2.
- Cache rule: bypass the cache for `/api/*`.
- Pin `cloudflared` to a version (no `latest`) and note the update procedure.
- The `curatorx.automat.vip` alias: keep it or remove it (one public name is less surface). Ask the owner.
- **Video through the proxy:** read Cloudflare's current terms on serving video through the regular proxy and tunnel on this plan, and summarize them for the owner. Don't decide for them.

## Verification before removing Access

1. Every (gate) item is released and on production.
2. With Access still on, an outside scan from a network outside the LAN (OWASP ZAP baseline against the public hostname, authenticated and unauthenticated), plus a manual pass over the public routes and the token URLs. Findings are fixed or accepted by the owner in writing.
3. Then remove the Access app for this hostname (owner approves), re-run the unauthenticated scan, and confirm the edge rules fire (rate limit and `/mcp` block).
4. Record the final setup in `projectionist-program/docs/network.md`.

---
## Processing note (agent, 2026-11-24)
- Created: SEC-017, SEC-018, SEC-019, SEC-020, SEC-021, SEC-022, SEC-023, SEC-024, SEC-025, SEC-026. The series already used SEC-001 through SEC-016, so these are the next free numbers. SEC-017 through SEC-022 are the gate (drop items 1–6). SEC-023 through SEC-026 are drop items 7–10.
- Updated: SECURITY.md roadmap section, S14, and the operator note for the trusted-proxy list. The board lists the ten items. SEC-017 is implemented here and is not a release.
- Outbox: none. SEC-025 uses the existing inbox. Push stays NAT-006. No client screen is specified in this repository.
- Needs the person: Cloudflare edge changes, whether to keep the extra public hostname, what the current video-proxy terms allow, and removing the extra login on the public hostname. Another lane is writing that plan. This lane does not apply it. The extra login stays on.

---
## Processing note (agent, 2026-11-26)
- Updated: all ten gates are on `origin/main`, checked this pass. Trusted `CF-Connecting-IP` is done.
  1. SEC-017, pull request 319, `fa442d2f`. `CF-Connecting-IP` is the rate-limit key only when the direct peer is on the trusted-proxy list.
  2. SEC-018, pull request 321, `b000de54`.
  3. SEC-019, pull request 322, `7376b1a8`.
  4. SEC-020, pull request 323, `666ee5cd`.
  5. SEC-021, pull request 325, `2e4a593e`.
  6. SEC-022, pull request 327, `e4c77c25`.
  7. SEC-023, pull request 329, `a7060336`.
  8. SEC-024, pull request 330, `aeba79d0`.
  9. SEC-025, pull request 331, `755e82ac`.
  10. SEC-026, pull request 332, `c5f622b3`.
- Updated: SEC-027, the engine media-token lifetime, pull request 333, `4c6a21ed`.
- Access stays on `projectionist.automat.vip` permanently. These gates stay as the community baseline and as defense in depth. There is no Access-removal item. The drop's "Verification before removing Access" section is not the plan.
- Needs the person: approval of the written network and edge plan before any apply. This filing applies nothing.
