# Drop: one Projectionist sign-in; Plex and Jellyfin become linked accounts

**From:** Will (via design chat) · **Date:** 2026-11-25 · **Type:** identity rework, part of the public front door · **Reference:** design canvas boards `WebInviteOnboarding`, `PhoneSignInPasskey`, and the "Identity" sticky

## Why

Today a member's identity *is* their Plex account. Their security depends on their Plex password, the login page asks for media-server credentials, and Jellyfin would need a second identity scheme. Separate **who you are** (a Projectionist account with strong sign-in methods) from **what you've linked** (Plex, later Jellyfin and Seerr). One secure sign-in works everywhere, and media links are made by the owner behind the scenes.

## Decisions (accepted)

1. **Sign-in methods**, each enabled per household by the owner:
   - **Passkeys (WebAuthn): recommended, first on every screen.** The relying party is the configured public origin, with the LAN origin as a separate RP where needed; the docs explain the limits. A member can register several passkeys and see and remove them in Settings → Sign-in.
   - **Password + TOTP:** TOTP is required for owner and admin roles. Recovery codes; the breached-password check from the front-door work.
   - **Single sign-on (existing OIDC):** Google or the household's own provider (Authentik, Authelia, Pocket ID…). Native apps keep using PKCE with a single-use code.
   - **Plex sign-in: optional, OFF by default.** The owner can enable it (useful for households that start Plex-only). When off, nothing about Plex appears on any login screen.
   - **The Plex-token sign-in is removed entirely** (UI and the `auth_plex_token` route).
   - **Owner gate (front-door gate 3)** is satisfied by: passkey, password + TOTP, or OIDC. A plain password alone is never enough for owner or admin.
2. **Linked accounts** live on the person, never used to sign in:
   - **Plex:** server user id (and plex.tv account id when known).
   - **Jellyfin** (future, ENG-010): server user id.
   - **Seerr:** user id. The Seerr link moves out of the Plex sign-in path, into linked accounts or owner mapping.
3. **The invite flow (owner side):**
   - Creating an invite lets the owner **pick the invitee's media-server user** from the server's own list: Plex Home and shared users via the owner's token; later, Jellyfin users via the admin API. It also sets the role and the Youth profile.
   - That link is stored on the invite and applied when the account is created. The invitee never signs in to Plex.
4. **The invite flow (member side, three steps):**
   1. Sign in: create a passkey, or a password (+ TOTP if required), or SSO.
   2. Your accounts: shows links the owner made, plus an **optional "Connect your own Plex account"** (the plex.tv PIN window once).
   3. Done: points to the apps, and offers "Where you watch" (the streaming-services drop).
5. **What needs the member's own Plex token** (verified in code, `users.plex_token_enc`): **their Plex watchlist sync** (`watchlist/plex_sync.py`) and **personal watch state read and written on Plex** (`library/watch_state.py`).
   - Without a connected token, those features say so plainly and offer "Connect Plex".
   - Everything Projectionist does itself works from the owner-side link: history, Explore, Chat, Continue Watching from Projectionist's own records.
   - Revoking the link deletes the stored token.
6. **Migrating existing members:**
   - Current Plex-signed-in users keep working.
   - At their next sign-in they're asked to add a passkey or a password, with a skippable reminder and an owner-set deadline.
   - Their Plex identity becomes a linked account, keeping the token if they had one.
   - When everyone has another method, the owner can turn Plex sign-in off. The owner's own account must have a passkey or password + TOTP first.
7. **Native apps:**
   - Every method finishes in the system web-auth sheet and returns a device credential (unchanged contract, NAT-002).
   - Passkeys work through the web sheet without associated domains.
   - The pair-code fallback stays.
8. **The login page and `/api/features` (anonymous)** list only the methods the household enabled, with no Plex wording when Plex sign-in is off.

## Items (create on the board)

- Passkeys (register, sign in, manage; RP config; tests)
- TOTP + recovery codes; the owner/admin enforcement
- The linked-accounts model + migration from `users.plex_*` columns
- Invite: pick a media-server user (Plex now, Jellyfin later behind the media-source interface)
- Onboarding: the three steps; "Connect your own Plex account"
- Plex sign-in as an owner option, default off; remove Plex-token sign-in
- The Seerr link moved to linked accounts
- Migration prompts for existing members
- `docs/SECURITY.md` and the authz test updated

## Done when

- A new invitee joins with a passkey, never sees Plex, and their Plex user is linked by the owner.
- They connect Plex later and their watchlist syncs.
- An existing Plex member migrates to a passkey.
- With Plex sign-in off, no login surface mentions Plex.
- The owner can't sign in with a password alone.
- Security review green on each PR.
---
## Processing note (agent, 2026-11-26)
- Created: SEC-028, SEC-029, SEC-030, SEC-031, SEC-032, SEC-033, SEC-034.
- Order: SEC-028, then SEC-029, then SEC-030, then the app door (SEC-036) after container hardening (SEC-035), then SEC-031 onward.
- SEC-031 is built-in passkeys (`py_webauthn`) and TOTP (`pyotp`) in an isolated identity module. The companion-container copy in `2026-11-26-pocket-id-companion.md` is superseded. No Pocket ID container. No `id.automat.vip`. Generic OIDC stays.
- Each identity pull request waits for an explicit approval comment before it merges.
- Outbox: `docs/roadmap/outbox/2026-11-26-SEC-031-identity.md` (platform needs only).
- Needs the person: an approval comment on each identity pull request before merge.
