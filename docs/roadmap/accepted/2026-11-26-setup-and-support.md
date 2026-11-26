# Drop: easy to run, easy to help — setup, Doctor, owner console, guided remote access

**From:** Will (via design chat) · **Date:** 2026-11-26 · **Type:** product (owner experience), community launch readiness · **Related:** two doors, the exposure card, container hardening, the Unraid template

## Why

Getting Projectionist running and getting a household member's iPhone or Apple TV connected must be easy, or people give up. Security has to be the default path, not extra homework. The product itself should diagnose problems and explain fixes in plain language.

## Decisions (accepted)

### 1. First-run setup wizard (web)

1. Welcome + the owner account (a passkey, or password + TOTP).
2. **Connect Plex** (owner PIN flow); detect the libraries.
3. **Library paths, auto-mapped:** compare Plex's file paths with the container's mounts, propose the path map, verify with one probe per library. Explain read-only.
4. Optional: the AI curator (provider + key, with a spending cap), the persona.
5. **Remote access, chosen not assumed:**
   - "Home only for now"
   - "I use Tailscale or a VPN" (recommended)
   - "Cloudflare Tunnel"
   - "My own reverse proxy"

   Each opens its guided walkthrough (§4). Recorded so the Doctor and the exposure card know what to expect.
6. Invite the first member (with media-user picking) and **add a device** (QR).

### 2. Doctor (diagnostics engine, server)

One check registry, run on demand, after updates, and daily. Each check: status, plain explanation, fix steps, docs link. Starting checks:
- settings and DB readable and writable by the app user (the 1.46.2 lesson);
- DB integrity; disk space for /config and copies;
- Plex reachable + token valid; the path map resolves (sampled); ffmpeg present + versions; hardware encoders (from detection);
- clock skew; time zone set;
- front door: HTTPS off-LAN; the public origin configured; cookie flags effective;
- app door: listening and separate; tagged-route test passes;
- exposure: everything in the exposure card (socket, ro library, MCP LAN-only, owner second factor, etc.);
- update available (from GitHub releases; no telemetry);
- email/notifications configured.

### 3. Owner console

**Web:** Admin → Household health. Doctor results, the exposure card, recent sign-in notices, devices, members missing a second factor, update status, "Run all checks".

**Bad things surface:**
- a **banner** for owners at sign-in when any check is red;
- an **owner notification** (inbox now; push later) when a check turns red;
- the **weekly letter's owner section** lists what still needs fixing.

### 4. Guided remote access (docs + in-app walkthroughs)

- `docs/REMOTE-ACCESS.md` plus in-app step-by-step walkthroughs (with screenshots), one per path: **Tailscale/VPN** (recommended), **Cloudflare Tunnel + Access** (front door behind Access with email one-time codes; app door hostname with edge rules), **reverse proxy** (Nginx Proxy Manager, SWAG, Traefik, Caddy, plus forward-auth examples that exempt the app door), and **port forwarding** (discouraged; what's required).
- **Optional Cloudflare assistant:** the owner pastes a **scoped Cloudflare API token** (permissions listed). Projectionist shows a plan (tunnel hostnames for both doors, the Access app for the front door with email OTP, edge rules for the app door) and applies it only after the owner confirms. The token is used for that session and **not stored** unless the owner opts in. Every change is logged with an undo list. Default: off, guide-only.
- **"Test from outside" with a household device:** the app (on cellular, Wi-Fi off) checks reachability of the away and app_away addresses, TLS, and the gate, then reports back to the server. The Doctor shows "Your phone reached the app door over HTTPS ✓" / "TLS error: certificate name mismatch". No third-party probing service.

### 5. Member self-help (with the owner's privacy respected)

- In every client: **"Something's not working"** → runs device-side checks (which door answered, TLS, credential valid, last error codes), shows plain fixes, and can **send a diagnostic report to the owner's inbox** (no viewing data; device model, app version, error codes, check results). The owner sees "Mom's iPad: app door TLS certificate mismatch" with the fix link.
- **The curator can answer setup questions** using a `doctor_status` tool (owner: full; members: only their own device and access). "Why can't the TV find the server?" → grounded answer from the checks.

### 6. Install paths

- The Unraid Community Applications template (the hardening drop), a compose file for everything else, and both documented in `docs/INSTALL.md` with a 5-minute path.
- In-app "What's new" after updates, linking release notes.

## Done when

- A fresh install on the lab goes from container start to a member's iPhone streaming using only the wizard, QR and the Tailscale or Cloudflare walkthrough.
- The Doctor catches a root-owned settings file, a broken path map, an HTTP-only away address, and a missing owner second factor, with correct fix text.
- The banner and owner notification fire on a red check.
- A member's diagnostic report reaches the owner's inbox.
- The Cloudflare assistant shows a plan and applies nothing without confirmation (tested against a mock API).
---
## Processing note (agent, 2026-11-26)
- Created: PRD-026, PRD-027, PRD-028. Community-launch track, after SEC-035 and SEC-036. Not this run.
- Outbox: `docs/roadmap/outbox/2026-11-26-PRD-027-support.md`.
- Needs the person: nothing. Do not build it in this run.
