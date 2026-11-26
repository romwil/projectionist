# Projectionist on Unraid

Projectionist is one container. Community Applications installs it from `unraid/projectionist.xml` (the same file as `templates/projectionist.xml`). The image runs as uid **1000**, not Unraid's usual 99:100. `/api/ready` checks that this user can read and write `/config`. A different user would fail that check.

The container does not mount a Docker socket. A socket is root on the whole host. Live Channels uses a Tunarr address you already run.

## Safe defaults

| What | How it ships | Why |
|------|----------------|-----|
| Config | `/mnt/user/appdata/projectionist/config` → `/config`, read-write | Settings and the database live here |
| TV, movies, prerolls | Host folders → `/tv`, `/movies`, `/preroll`, **read-only** | A bug or a bad request cannot rename the library |
| Copies | Optional `/copies`, read-write, empty until you set it | Copies made ahead never go inside the library |
| Web | Host port → `8788` | The app |
| Lobby | Host port → `8791`, **LAN only** | The lobby lightbox. Do not put this port on a tunnel, a public proxy, or a WAN forward |
| Privileges | `no-new-privileges`, drop every capability, add back only `CHOWN`, `SETUID`, `SETGID`, and `DAC_OVERRIDE` | The entrypoint repairs `/config` ownership, then the app runs as uid 1000 with no extra capabilities |
| Root filesystem | Read-only, with a writable `/tmp` | The process cannot change the image |
| Health | `/api/ready` | A container that cannot write its settings is not healthy |
| User | uid 1000, gid 1000 | Matches the ready check |

Memory and CPU limits are optional. A library sync uses more than a quiet hour. If you set a limit, start at 2 GB and raise it when a sync is killed. Do not set a limit you have not watched.

GPU passthrough is optional. Intel Quick Sync is `/dev/dri` (read-write device). NVIDIA is the NVIDIA runtime the Unraid Nvidia driver plugin documents. Leave both off until a playback path asks for them. The shipped template does not require a GPU.

## Install

1. In **Apps**, search for Projectionist, or add `unraid/projectionist.xml`.
2. Leave the library paths read-only. Set **Config** to `/mnt/user/appdata/projectionist/config`.
3. Set **TZ** to your household clock, for example `America/New_York`.
4. Apply. Open `http://<tower>:8788` and finish setup.

`curatorx.xml` is a legacy alias for installs that still have that name. New installs use `projectionist.xml`. Do not add a socket or a read-write library to the legacy file.

## When Apply needs to rename a file

Investigate → Apply is off until both of these are true:

1. **Allow file renames** is on (Household). It is off by default.
2. The library folder is mounted read-write.

Do the rename, then mount the library read-only again and turn the switch off. If the folder is read-only, Apply says so and does not change a file.

## Update

Pin `romwil/projectionist:latest`, or a release tag when you want one exact build. If Force Update pulls 0 B, the host kept a stale tag. On the Unraid host:

```bash
docker pull romwil/projectionist:latest
```

Then apply the container again. Do not delete `/config`.

Copying a new `rollout.sh` or template onto a machine that is already running does not by itself recreate that container. Recreate only after you have saved the current `docker inspect` and you mean to adopt this template. That adoption is a separate change, with its own rollback. This document does not change a running host.

## What is not in the image

QA, pentest campaigns, and host migration scripts are not part of the image and not part of this template. They stay in the maintainer's checkout.
