# Unraid GraphQL API — Automat reference

What you can actually automate on the Automat Unraid host from the LAN: **read telemetry** (array, disks, CPU/RAM, Docker containers, shares, VMs, notifications) and **start/stop individual containers**. This is a maintainer ops note for future Automat scripts — **not** a new Projectionist service, and **not** a Hand of Franklin clone.

Audience: developers and Cursor agents with LAN reach to Automat. Member-facing docs stay in [wiki/Unraid.md](../wiki/Unraid.md).

Jump to: [What it can do](#what-it-can-do) · [What it cannot](#what-it-cannot-do) · [Connect](#connect-endpoint--auth) · [Queries that worked](#queries-that-worked) · [Mutations that worked](#mutations-that-worked) · [Logs](#container-logs) · [Automat notes](#automat-specific-notes) · [See also](#see-also)

---

## What it can do

From a LAN client with an API key, you can:

- **Poll host health** every ~15s: hostname, Unraid version, uptime, CPU %, RAM used/total, array state and capacity, per-disk temp/status/spin, parity-check status.
- **List Docker containers** (id, names, state, status, image, ports, autoStart, labels) and **start / stop** a container by GraphQL `PrefixedID`.
- **Restart a container** as stop → wait ~2s → start (no `restart` mutation on the Automat-era schema).
- **Read shares, VMs, plugins, flash USB identity, unread notifications.**
- **Tail container logs** via GraphQL `docker.logs` when present, else host `logFiles` / `logFile` (`*-json.log`), else Docker Engine on `/var/run/docker.sock`.

That is enough to build a dashboard, an alert, or a “restart `projectionist-qa`” script. It is **not** enough to recover a host whose Docker service is off.

---

## What it cannot do

The Unraid GraphQL API is **container-level Docker**, not host Docker settings and not a file bus.

| You might want | Why GraphQL will not do it |
|----------------|----------------------------|
| **Enable Docker** (Settings → Docker → Enable Docker = Yes) | No mutation. That switch lives in Unraid’s Docker service config, not `DockerMutations`. |
| **Edit `docker.cfg`** (`/boot/config/docker.cfg` on the USB flash) | Flash/config files are not a GraphQL resource. Use the Unraid GUI or SSH to the host. |
| **rsync / copy trees** (QA Path A, appdata sync, media) | Not an Unraid API. Use host SSH/`rsync` as in [AUTOMAT.md](AUTOMAT.md). |
| **Re-enable Docker after it was disabled** | When Docker is **disabled**, the engine is down. Every container dies — including anything you were using to call the API. GraphQL Docker resolvers fail because there is no daemon. Recovery is the GUI on **`:8081`** (or SSH), not another GraphQL call. |
| **Start/stop the array, add/remove disks, run parity** | `Mutation.array` / `parityCheck` exist in the official schema. They were **not** used in production here (high impact). Do not invent them for Projectionist QA. |
| **VM power, image pull, CA update, flash backup** | Present or arriving in newer Unraid API versions. **Not** proven on Automat. Introspect live schema before relying on them. |

**Honest limit:** if someone turns Docker off on Automat, GraphQL cannot turn it back on. You need the Unraid web GUI or a host shell.

---

## Connect: endpoint + auth

### Automat URLs

| What | URL | Notes |
|------|-----|--------|
| **Unraid web GUI** | `http://10.10.1.202:8081` | Automat moved the GUI off `:80`. Not Projectionist. |
| **GraphQL** | `http://10.10.1.202:8081/graphql` | Same host/port as the GUI, path `/graphql`. |
| Official sandbox (stock Unraid) | `http://YOUR_SERVER_IP/graphql` | Stock GUI is `:80`. Automat is **`:8081`**, so do not drop the port. |

If a POST returns HTML instead of JSON, the URL is wrong (missing `/graphql`, wrong port) or you hit the GUI.

Create a key in the GUI: **Settings → Management Access → API Keys** (Unraid 7.2+: **Settings → Management Access → API**). CLI: `unraid-api apikey --create`. Grant at least **READ_ANY** on ARRAY, INFO, DOCKER, LOGS (and shares/VMs/notifications if you query them) plus **UPDATE_ANY** on DOCKER for start/stop.

### Env vars (names only — never commit values)

These names were used by the homelab dashboard that proved this path. Reuse them in a script; they are not Projectionist settings.

| Variable | Required | Meaning |
|----------|----------|---------|
| `UNRAID_IP` | Yes | Unraid host IP. Automat: `10.10.1.202`. |
| `UNRAID_KEY` | Yes | GraphQL API key. Sent as header `x-api-key`. |
| `UNRAID_GRAPHQL` | No | Full GraphQL URL. Default `http://$UNRAID_IP:8081/graphql`. |
| `UNRAID_GRAPHQL_PORT` | No | Port used only when `UNRAID_GRAPHQL` is unset. Default `8081`. |
| `UNRAID_WEBUI` | No | Base URL for “open Unraid” links (no trailing slash). Automat: `http://10.10.1.202:8081`. |

Auth header (every request):

```http
x-api-key: YOUR_UNRAID_API_KEY
Content-Type: application/json
```

### Worked example

```bash
# Automat LAN — list containers (read). Replace the key; do not commit it.
curl -s http://10.10.1.202:8081/graphql \
  -H "Content-Type: application/json" \
  -H "x-api-key: YOUR_UNRAID_API_KEY" \
  -d '{"query":"{ docker { containers { id names state status } } }"}'
```

A healthy reply is JSON with `"data": { "docker": { "containers": [ ... ] } }`. GraphQL can still return HTTP 200 with an `"errors"` array — treat that as failure for that field, not as “the host is down.”

---

## How polling should work

**Split queries.** One brittle resolver (UPS, flash, notifications) can null the entire `data` object via GraphQL non-null propagation. The pattern that survived: a **core** query (server, info, metrics, vars, array) plus **separate** queries for docker, notifications, plugins, shares, VMs, flash. If docker fails, you still have array/CPU.

**Interval:** ~15 seconds was enough for a wall dashboard. Cache to a local JSON file if the UI polls faster (the dashboard’s browser polled ~5s against cache, not against Unraid).

**Timeouts:** 10s for reads, 30s for mutations. On connection errors, surface a short `CONN ERR` rather than serving a stale “ONLINE” panel.

**Units (easy to get wrong):**

- `array.capacity.kilobytes.{free,used,total}` — strings; sometimes compact (`"12.3 TB"`), sometimes numeric KB.
- Share `free` / `used` / `size` — KB (×1024 → bytes).
- `ArrayDisk.size` — documented as KB; values ≥ `1e11` were treated as already-bytes (multi-TB disks).
- `metrics.memory.total` / `used` — bytes.

---

## Queries that worked

Proven field sets (not the full Unraid schema). Live docs: [Unraid API](https://docs.unraid.net/API/) and [Using the Unraid API](https://docs.unraid.net/API/how-to-use-the-api/). Enable the GraphQL sandbox on the GUI to introspect **this** host.

**Core (must succeed or the poll is a connection error):**

```graphql
query VaultTelemetryCore {
  server { name status }
  info { os { uptime } }
  metrics { cpu { percentTotal } memory { total used percentTotal } }
  vars { version name timeZone }
  array {
    state
    capacity { kilobytes { free used total } }
    parityCheckStatus { status progress correcting paused errors }
    disks { name temp status size device type rotational isSpinning idx fsType }
    parities { name temp status size device type rotational isSpinning idx fsType }
    caches { name temp status size device type rotational isSpinning idx fsType }
  }
}
```

`server` can be null on the local node; treat missing status as OK, `OFFLINE` as degraded.

**Docker** (`READ_ANY` / `DOCKER`):

```graphql
query VaultTelemetryDocker {
  docker {
    containers {
      id names state status image
      ports { ip privatePort publicPort type }
      autoStart
      labels
    }
  }
}
```

There is **no** `lanIpPorts` / `webUiUrl` on the Automat-era `DockerContainer` type. Build LAN port strings from `ports`. Map Web UI URLs yourself (container name → `http://host:port`). Labels may arrive as a JSON object or a JSON string.

**Also polled successfully (own queries):**

| Query | Fields used |
|-------|-------------|
| Notifications | `notifications.overview.unread { alert warning info total }`, `list(filter: { type: UNREAD, offset: 0, limit: 8 }) { title subject importance }` |
| Plugins | `plugins { name version }` |
| Shares | `shares { name free used size }` |
| VMs | `vms { domains { name state } }` |
| Flash | `flash { vendor product }` |

**UPS** (`upsDevices`) was dropped from the live poll — the resolver was brittle and wiped the payload. Do not put it on the core query. Official schema still has it if you want a dedicated, failure-isolated call.

---

## Mutations that worked

`DockerMutations` on the Automat-era schema: **`start(id)`** and **`stop(id)`** only (`UPDATE_ANY` on `DOCKER`). `id` is a `PrefixedID` (often `docker:<hex>`). Return `{ id }` is enough.

```graphql
mutation {
  docker {
    stop(id: "docker:YOUR_CONTAINER_ID") { id }
  }
}
```

Safer with a variable:

```bash
curl -s http://10.10.1.202:8081/graphql \
  -H "Content-Type: application/json" \
  -H "x-api-key: YOUR_UNRAID_API_KEY" \
  -d '{"query":"mutation ($id: PrefixedID!) { docker { start(id: $id) { id } } }","variables":{"id":"docker:YOUR_CONTAINER_ID"}}'
```

**Restart:** `stop` → sleep 2s → `start`. A failed stop must not proceed to start.

**Pause / unpause:** the dashboard *attempted* `docker { pause(id) }` / `unpause`. The schema snapshot on disk only documented `start`/`stop`. Newer Unraid API source adds `restart`, `pause`, `unpause`, and container update mutations — introspect before using them. Prefer proven `start`/`stop` for Automat.

**Never** GraphQL-stop production **`projectionist`** (`:8788`) or **`smartmap`** (`:8790`). QA sidecar `projectionist-qa` on `:8792` is the only Projectionist container that may be stopped when idle. See [AUTOMAT.md](AUTOMAT.md).

---

## Container logs

Three fallbacks, in order. Need **READ_ANY** on **DOCKER** and **LOGS**.

1. **`docker.logs`** (absent on many Unraid 7.x / plugin schemas — expect `cannot query field "logs"`):

```graphql
query VaultLogs($id: PrefixedID!) {
  docker { logs(id: $id, tail: 80) { lines { message } } }
}
```

2. **Host json-file logs** via `logFiles` + `logFile` (this is what actually worked when `docker.logs` was missing):
   - `query { logFiles { path name } }` (cache ~45s).
   - Match `/var/lib/docker/containers/<64-hex>/<64-hex>-json.log` against the container id (strip a `docker:` prefix; prefix-match short ids).
   - `logFile(path:, lines: 1)` → `totalLines`, then `logFile(path:, startLine:, lines:)` for the tail.
   - Each line is Docker json-file JSON; use the `log` field.

3. **Docker Engine socket** (optional, read-only mount of host `/var/run/docker.sock`):

```http
GET /v1.41/containers/{id}/logs?stdout=1&stderr=1&tail=80&timestamps=0
```

Unix socket HTTP. Response is the multiplexed stdout/stderr stream (8-byte frames); strip a `docker:` prefix from the id. If GraphQL has no `logs`, no matching `*-json.log`, and no socket, you cannot tail from the API.

---

## Automat-specific notes

- **GUI + GraphQL share `:8081`.** PeaNUT is `:8080` on the same host; do not confuse them.
- **Port contract (do not invert):** `:8788` = prod Projectionist. `:8790` = smartmap. `:8792` = maintainer QA when it exists. GraphQL start/stop of **`projectionist`** or **`smartmap`** is a production incident, not a convenience.
- **QA Path A rsync** (`/mnt/user/appdata/projectionist-qa-build/`) is host `rsync` + `docker build`. It is unrelated to this API. CA proof remains Hub pull (Path B) — [AUTOMAT.md](AUTOMAT.md).
- **Sandboxed schema vs live:** Unraid 7.2+ ships the API in the OS ([docs](https://docs.unraid.net/API/)). Field names move. Introspect `http://10.10.1.202:8081/graphql` (sandbox on) rather than copying a dumped `schema.graphql`.
- **Keys are host secrets.** Keep them in a gitignored env file or a password manager — never in this repo, never in the Hand of Franklin tree if it is still mounted.

---

## How this works

Unraid exposes an Apollo GraphQL server next to the web GUI. API keys map to resource/action pairs (`READ_ANY` / `UPDATE_ANY` × `DOCKER`, `ARRAY`, `LOGS`, …). Queries talk to emhttp and, for Docker, to the Docker engine. That is why **disabling Docker kills Docker GraphQL**: the resolver has nowhere to go, and every container process is already gone.

Official coverage and sandbox: [Unraid API](https://docs.unraid.net/API/) · [How to use the API](https://docs.unraid.net/API/how-to-use-the-api/) · live schema in [unraid/api](https://github.com/unraid/api/blob/main/api/generated-schema.graphql).

---

## See also

- [AUTOMAT.md](AUTOMAT.md) — LAN hosts, rollout, **never stop `:8788` / `:8790`**
- [DOCKER.md](../DOCKER.md) · [wiki/Unraid.md](../wiki/Unraid.md) — generic Unraid install / Force Update
- `.cursor/rules/automat-environments.mdc` — always-on agent summary of Automat hosts
