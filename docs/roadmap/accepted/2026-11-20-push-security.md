# Push notifications for native clients, including security approvals

Dropped 2026-11-20. **Decided by the person:** push to native clients is a priority, and it carries security as well as convenience. This expands **NAT-006** (content-free push via the publisher's relay). Update `docs/NATIVE_CLIENTS.md` and the board, and mark NAT-006 `accepted`.

## What the platform needs

1. **Push registration per device** (NAT-006 as written): a device stores its APNs token against its device record; revoking the device drops the token.
2. **Content-free payloads only.** Every push says only that something needs attention (`approval_needed`, `something_ready`, `security_notice`) plus an opaque id. The client fetches the details from the household server with its device credential. No title, member name, device name, or library data goes to the relay.
3. **Approval requests** (new): a server-side object a member can approve or deny from any of their signed-in devices:
   - **Device sign-in approval.** When a new device issues a pair code (`POST /api/devices/pair/issue`), the server may offer it to the member's devices for approval, so a phone can approve a TV without typing the code. The code path stays as the fallback. *Proposed:* the issuing device has to pick or name the member first, so approvals go only to that member's devices.
   - **Youth join approval** (SES-009) uses the same object.
   - Approvals expire, are single-use, are audited, and re-check authorization when acted on.
4. **New-device notices.** When a member's account gains a device (any sign-in path, NAT-002), the member's other devices get a `security_notice`.
5. **Notification preferences** per member (which kinds they receive), alongside the existing in-app and email preferences.
6. **Capability:** `push: 1` and `approvals: 1` in `GET /api/features`.

## Honest limits

- APNs needs the publisher's key, so a self-hosted server sends through the publisher relay (NAT-006). If the relay is down, approvals still work in-app and on the web.
- Approval by push is a convenience on top of the existing checks, not a replacement: the server re-validates every approval.

## Sequencing

After NAT-002 (native sign-in) in the contract lane, or as its own lane. Security-sensitive: design → plan → build, with the security review check green before merge.

---
## Processing note (agent, 2026-11-20)
- Updated: NAT-006 marked accepted. Content-free push, approvals, and new-device notices.
- Outbox: 2026-11-20-NAT-006-native.md
- Needs the person: nothing. After NAT-002. Not started.
