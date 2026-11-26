# Drop: container hardening + a maintained Unraid template (front-door gate)

**From:** Will (via design chat) · **Date:** 2026-11-26 · **Type:** security gate, packaging · **Gate:** blocks Cloudflare Access removal

## Why

Production mounts the **Docker socket** (seen in the 1.46.2 rollback `docker inspect`). That's effectively root on the whole Unraid host if the app is ever compromised. The code doesn't use it, and `docker-compose.unraid.yml` already says not to mount it. The production template is out of step with the repo. Before the front door is public, the container must run with least privilege, and the Unraid template must be a maintained, versioned artifact, since the community launch will use it.

## Decisions (accepted)

1. **No Docker socket, ever,** in any shipped template or compose file. Docker-smoke in CI asserts the image runs without it, and startup logs a warning if a socket is mounted.
2. **QA tooling is not part of the product.** Anything for the QA sidecar, maintainer pentest live runs, or host management lives outside the core image and its templates (the program repo or a private ops repo). Remove leftovers and references from the core image, compose files and the shipped template; update docs that point at them.
3. **The library is read-only by default:**
   - `/movies`, `/tv`, `/preroll` mounted `:ro` in the shipped template and compose files.
   - Investigate → Apply (episode renames) becomes an **opt-in maintenance capability**: available only when the owner explicitly mounts the library read-write *and* turns on "Allow file renames". Owner-only, audited, and off by default. When the mount is read-only, the UI explains why Apply is unavailable.
   - Copies made ahead go to their own writable folder (an existing setting), never inside the library.
4. **Least-privilege runtime** in the template and compose (and documented):
   - runs as `PUID`/`PGID` (default 99:100 for Unraid, or 1000; decide and document);
   - `--security-opt no-new-privileges:true`, `--cap-drop ALL` (add back only what's proven necessary);
   - a read-only root filesystem where feasible, with tmpfs for `/tmp`;
   - healthcheck on `/api/ready` (not `/api/health`), with memory and CPU limits documented as optional.
5. **Ports:** only `8788` is required. **Port 8791 (theater) is LAN-only by documentation:** never routed through the tunnel. Decide whether it's still needed; if not, remove it.
6. **The Unraid template is maintained in the repo** (`unraid/projectionist.xml`, the `curatorx.xml` alias retired or marked legacy):
   - fields: `/config` (rw), library paths (ro), the copies folder (rw, optional), the preroll folder (ro), PUID/PGID, TZ, the web port; optional `/dev/dri` (Intel Quick Sync) and NVIDIA runtime fields, matching the hardware detection; ExtraParams with the security options above;
   - Overview, Support, Project and Icon URLs; a template version that follows releases;
   - CI validates the XML and checks it matches `docker-compose.unraid.yml` (same mounts, no socket, ro library).
   - A short `docs/UNRAID.md`: install, update, the GPU passthrough options, and a "safe defaults" explanation.
7. **Production adopts the template** through the sequenced change plan (with the IP move to 10.10.1.57). The current container's settings are captured first, with rollback to the current run config.

## Done when

- The template and compose files mount no socket, the library is ro, and the security options are present.
- CI fails if a socket or rw library appears.
- Investigate Apply is refused on a ro library with a clear message.
- Production runs from the template with no socket (verified by `docker inspect`), a ro library and the healthcheck on ready.
- docs/UNRAID.md is published.
---
## Processing note (agent, 2026-11-26)
- Created: SEC-035.
- The drop calls itself a gate for Access removal. Access is staying, so the hardening still ships, and production adopts the template with the IP move inside the written change plan. It does not end in turning Access off. This lane does not adopt the template on the host.
- *Proposed:* port 8791 stays LAN-only and is never put on the tunnel, until the person says whether the theater port is still needed.
- *Proposed:* the Unraid template documents PUID/PGID 99:100 as the Community Applications default, and the maintainer host keeps uid 1000 when it adopts the template.
- Outbox: none.
- Needs the person: whether port 8791 is still needed. The lane keeps it off the tunnel either way.
