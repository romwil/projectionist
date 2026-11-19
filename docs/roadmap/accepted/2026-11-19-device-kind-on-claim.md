# Name the device kind on claim and in the device list

Dropped 2026-11-18 by the Apple client. Platform need only. Touches **NAT-005**.

Pairing already works (`POST /api/devices/pair/issue`, rotate, pending poll, claim, revoke). The default label is “Apple TV”, and **Settings → Apple TV** speaks as if every paired device were a television.

Clients that pair with those routes need a kind on the device record — `tv`, `iphone`, or `ipad` — and the claim page and the device list need to show that kind. A free-text label is not enough: the page title, empty state, and claim confirmation still say “Apple TV”.

This should not wait on NAT-002. Handhelds can pair with the existing code flow before native sign-in exists. NAT-005 (Settings → Devices) is the natural home; the kind has to be stored and returned by the pairing routes that already exist.

**Waiting client item:** APL-016. The routes do not need to block on this; the missing piece is the kind.

No client screens, copy, or product plans in this request.

---
## Processing note (agent, 2026-11-19)
- Updated: NAT-005 (device kind on claim/list; Settings → Devices; depends on pairing shipped, not NAT-002)
- Outbox: 2026-11-19-NAT-005-apple.md (client APL-016)
- Needs the person: nothing to create the item; say when to implement NAT-005
