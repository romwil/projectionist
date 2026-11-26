# Drop: Pocket ID as the recommended sign-in companion (amends the identity drop)

**From:** Will (via design chat) · **Date:** 2026-11-26 · **Amends:** `2026-11-25-identity-and-linked-accounts.md`

## Decision (accepted)

**Passkeys come from Pocket ID**, a passkey-only OIDC provider (BSD-2-Clause), run as a **companion container**, not inside the Projectionist image. Projectionist keeps who belongs to the household, roles, Youth, invites and linked accounts. Pocket ID proves who someone is.

### Why a companion, not bundled inside

- Isolation: the sign-in service is separate from the app that parses media and calls LLMs.
- Upstream patches arrive on Pocket ID's own release cadence.
- Passkeys are bound to Pocket ID's own origin (e.g. `id.automat.vip`), and one passkey can serve the household's other self-hosted apps too.

### Integration (Projectionist side)

1. **Setup wizard, "Use Pocket ID (recommended)":** the owner enters the Pocket ID URL and an admin API key. Projectionist then:
   - registers itself as an OIDC client (redirect URIs for web and native, PKCE);
   - creates a "Projectionist household" group and **grants that group access to the client** (new clients are restricted by default);
   - stores the client secret encrypted and turns on single sign-on with Pocket ID.
2. **Invites** with Pocket ID enabled:
   - creating an invite (with the owner's media-user pick) creates or links the person in Pocket ID (`POST /api/users`) and adds them to the group;
   - redeeming the invite hands the member a **one-time access link** (`POST /api/users/{id}/one-time-access-token`) to register their passkey, then returns to the three-step onboarding.
3. **Recovery:**
   - the owner can issue a member a new one-time access link from Admin → Members (through the API);
   - break-glass: a **LAN-only owner password + TOTP** (off the public hostname, rate-limited, audited) for when Pocket ID is down or the owner has lost every passkey.
4. **Households without Pocket ID** keep: password + TOTP (enforced for owner and admin), other OIDC providers, and optional Plex sign-in (off by default).
5. **Front-door gate 3** (owner second factor) is satisfied by a Pocket ID passkey or by password + TOTP. A plain password alone never is.
6. **Built-in passkeys** (WebAuthn inside Projectionist) move to "later/maybe". Not part of this front door.
7. **Templates:**
   - ship a recommended Pocket ID Unraid template next to ours (official image, PUID/PGID, data volume, TRUST_PROXY, app URL), plus `docs/POCKET-ID.md` (hostname, Cloudflare edge rules for `id.` too, backups of its data volume, the encryption key);
   - a compose example running both side by side.
8. **Scope of the front door and the pentest:** `id.automat.vip` becomes a public surface too. Add it to the Cloudflare change plan (its own edge rules) and to the pentest v2 staging scope (`qa-id.` or a staging Pocket ID).

## Order inside the identity lane (replaces the earlier order)

1. Remove the Plex-token sign-in.
2. The linked-accounts model + migration.
3. Invite media-user picking + three-step onboarding.
4. **Pocket ID: the setup wizard, the auto client/group registration, invite provisioning + one-time links, member recovery.**
5. TOTP + recovery codes for local passwords, with owner/admin enforcement; the LAN-only break-glass.
6. Plex sign-in as an owner option, default off; migration prompts.
7. The login page and anonymous `/api/features` list only the enabled methods.

## Done when

- On QA with a Pocket ID companion: the wizard connects and registers the client and group.
- An invite creates the member in Pocket ID, the member registers a passkey from the one-time link and lands in onboarding, and signs in later on web and in the iOS app (system sheet, PKCE) with that passkey.
- Owner recovery and break-glass work (LAN only).
- Tests mock the Pocket ID API. Security review green.
---
## Processing note (agent, 2026-11-26)
- Created: nothing for a companion. This copy is superseded.
- Updated: passkeys are built in with `py_webauthn`, and TOTP with `pyotp`, in an isolated identity module (SEC-031). No companion container. Generic OIDC stays. The order of identity items 1–3 in this file is kept. Item 4 of this file is not built.
- Outbox: none.
- Needs the person: nothing. The superseding decision is on the board.
