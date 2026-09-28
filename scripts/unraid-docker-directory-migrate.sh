#!/usr/bin/env bash
# Unraid docker.img (vDisk) → directory data-root migration.
#
# Hand-run on Automat (root) during a maintenance window. This script does
# NOT stop Docker, does NOT flip Settings → Docker → Enable Docker, does NOT
# docker stop/start projectionist or smartmap, does NOT start QA, does NOT
# bind :8790, does NOT delete docker.img, does NOT docker system prune, and
# does NOT start parity.
#
# Canonical copy: scripts/unraid-docker-directory-migrate.sh in the git repo.
# Copy onto Automat (do not put this in prod appdata/config). Pointer:
#   docs/ops/AUTOMAT.md — "Docker vDisk → directory"
#
# Why: Unraid's loop-mounted docker.img vDisk is a single point of failure and
# a FUSE footgun if the path is /mnt/user/.... Directory data-root on the
# cache pool (/mnt/cache/..., never /mnt/user) is the durable layout.
#
# Agreed procedure (Will does GUI; script waits / copies / prints):
#   1. Settings → Docker → stop timeout 10→60, Enable Docker: No, Apply
#      Script prompts and polls until docker info fails AND the img loop is gone.
#   2. mkdir /mnt/cache/system/docker/docker/
#   3. loop-mount the img READ-ONLY (cache path, not FUSE /mnt/user)
#   4. rsync -aHAX --numeric-ids → directory
#   5. umount; print GUI: data-root directory, path …/docker/, KEEP vDisk, Enable Yes
#   6. Optional --verify :8788 /api/health and :8790 HTTP (never starts anything)
#
# Usage (on Automat, as root):
#   ./scripts/unraid-docker-directory-migrate.sh --dry-run
#   ./scripts/unraid-docker-directory-migrate.sh
#   ./scripts/unraid-docker-directory-migrate.sh --verify
#
# Env overrides (still subject to FUSE / array refusals):
#   DOCKER_IMG   default /mnt/cache/system/docker/docker.img
#   DOCKER_DIR   default /mnt/cache/system/docker/docker
#   DOCKER_CFG   default /boot/config/docker.cfg
#   LOG_FILE     default /tmp/unraid-docker-directory-migrate.log
#   WAIT_SECS    poll budget for Docker-down and --verify (default 900 / 300)
#
# Style sibling: scripts/unraid-rollout.sh (log/die, set -euo pipefail).

set -euo pipefail

usage() {
  cat <<'EOF'
Unraid docker.img → directory data-root migration (hand-run, maintenance window).

Usage:
  unraid-docker-directory-migrate.sh [--dry-run] [--verify] [--i-confirm-nonempty-dest]
  unraid-docker-directory-migrate.sh --verify
  unraid-docker-directory-migrate.sh --help

Flags:
  --dry-run                   Preflight + print planned commands. No mkdir/mount/rsync
                              unless Docker is already down (then RO mount + rsync -n).
  --verify                    After Enable Docker Yes: poll :8788 health and :8790 HTTP.
                              Never docker start. Never bind :8790. Never start QA.
  --i-confirm-nonempty-dest   Dest exists and is not empty; proceed anyway (TTY YES also works).
  -h, --help                  This text.

This script will NEVER:
  - Set Enable Docker itself (GUI-only on Unraid)
  - docker stop / docker start any container (projectionist, smartmap, QA, …)
  - rm docker.img
  - docker system prune
  - start parity / mdcmd
  - bind or occupy :8790
  - docker start projectionist-qa

GUI checkpoints are printed at each phase. See docs/ops/AUTOMAT.md.
EOF
}

DRY_RUN=0
VERIFY=0
CONFIRM_NONEMPTY=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=1; shift ;;
    --verify) VERIFY=1; shift ;;
    --i-confirm-nonempty-dest) CONFIRM_NONEMPTY=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *)
      printf 'Unknown arg: %s\n' "$1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

# Defaults — cache pool paths, never FUSE /mnt/user.
DOCKER_IMG="${DOCKER_IMG:-/mnt/cache/system/docker/docker.img}"
DOCKER_DIR="${DOCKER_DIR:-/mnt/cache/system/docker/docker}"
DOCKER_CFG="${DOCKER_CFG:-/boot/config/docker.cfg}"
LOG_FILE="${LOG_FILE:-/tmp/unraid-docker-directory-migrate.log}"
WAIT_DOWN_SECS="${WAIT_SECS:-${WAIT_DOWN_SECS:-900}}"
WAIT_VERIFY_SECS="${WAIT_VERIFY_SECS:-300}"
PROD_HEALTH_URL="${PROD_HEALTH_URL:-http://127.0.0.1:8788/api/health}"
SMARTMAP_URL="${SMARTMAP_URL:-http://127.0.0.1:8790/}"
MIN_TIMEOUT=60
HEADROOM_PCT=15
HEADROOM_FLOOR_BYTES=$((2 * 1024 * 1024 * 1024))

LOOP_DEV=""
LOOP_MP=""
CLEANED=0

log() {
  local msg
  msg="$(date '+%Y-%m-%d %H:%M:%S') $*"
  printf '%s\n' "$msg"
  mkdir -p "$(dirname "$LOG_FILE")" 2>/dev/null || true
  printf '%s\n' "$msg" >>"$LOG_FILE" 2>/dev/null || true
}

die() {
  log "ERROR: $*"
  exit 1
}

hr_bytes() {
  local n="${1:-0}"
  if command -v numfmt >/dev/null 2>&1; then
    numfmt --to=iec --suffix=B "$n" 2>/dev/null || printf '%s bytes' "$n"
  else
    printf '%s bytes' "$n"
  fi
}

cleanup() {
  local rc=$?
  [[ "$CLEANED" -eq 1 ]] && return 0
  CLEANED=1
  if [[ -n "$LOOP_MP" ]]; then
    if findmnt -n "$LOOP_MP" >/dev/null 2>&1 || mountpoint -q "$LOOP_MP" 2>/dev/null; then
      log "TRAP: umount $LOOP_MP"
      umount "$LOOP_MP" 2>/dev/null || umount -l "$LOOP_MP" 2>/dev/null || true
    fi
    rmdir "$LOOP_MP" 2>/dev/null || true
  fi
  if [[ -n "$LOOP_DEV" ]]; then
    if losetup "$LOOP_DEV" >/dev/null 2>&1; then
      log "TRAP: losetup -d $LOOP_DEV"
      losetup -d "$LOOP_DEV" 2>/dev/null || true
    fi
  fi
  return "$rc"
}

trap cleanup EXIT
trap 'log "INTERRUPTED"; exit 130' INT
trap 'log "TERMINATED"; exit 143' TERM

cfg_get() {
  local key="$1"
  local line=""
  [[ -f "$DOCKER_CFG" ]] || return 0
  line="$(grep -E "^${key}=" "$DOCKER_CFG" 2>/dev/null | tail -1 || true)"
  [[ -n "$line" ]] || return 0
  line="${line#*=}"
  line="${line%\"}"
  line="${line#\"}"
  printf '%s' "$line"
}

path_is_user_fuse() {
  local p="$1"
  local resolved fstype
  [[ -n "$p" ]] || return 1
  case "$p" in
    /mnt/user|/mnt/user/*|/mnt/user0|/mnt/user0/*) return 0 ;;
  esac
  resolved="$(realpath -m "$p" 2>/dev/null || printf '%s' "$p")"
  case "$resolved" in
    /mnt/user|/mnt/user/*|/mnt/user0|/mnt/user0/*) return 0 ;;
  esac
  local probe="$p"
  [[ -e "$probe" ]] || probe="$(dirname "$p")"
  fstype="$(findmnt -n -o FSTYPE --target "$probe" 2>/dev/null || true)"
  case "$fstype" in
    fuse.shfs|fuse.mergerfs|shfs|fuse)
      case "$probe" in
        /mnt/user|/mnt/user/*|/mnt/user0|/mnt/user0/*) return 0 ;;
      esac
      if [[ "$probe" == /mnt/user* ]]; then
        return 0
      fi
      ;;
  esac
  return 1
}

path_is_array_disk() {
  local p="$1"
  local resolved
  resolved="$(realpath -m "$p" 2>/dev/null || printf '%s' "$p")"
  case "$resolved" in
    /mnt/disk[0-9]|/mnt/disk[0-9]/*|/mnt/disk[0-9][0-9]|/mnt/disk[0-9][0-9]/*) return 0 ;;
  esac
  return 1
}

refuse_bad_dest() {
  local dest="$1"
  path_is_user_fuse "$dest" && die "dest is FUSE /mnt/user (or resolves there): $dest — use /mnt/<pool>/... (Automat: /mnt/cache/system/docker/docker/)"
  path_is_array_disk "$dest" && die "dest is an array disk path (parity writes): $dest — use the cache pool"
  case "$dest" in
    /mnt/user|/mnt/user/*)
      die "dest refused: $dest"
      ;;
  esac
}

refuse_bad_img() {
  local img="$1"
  path_is_user_fuse "$img" && die "img is FUSE /mnt/user: $img — loop-mount the cache/pool file (e.g. /mnt/cache/system/docker/docker.img)"
  [[ -f "$img" ]] || die "docker.img not found: $img"
  [[ -s "$img" ]] || die "docker.img is empty: $img"
}

docker_info_ok() {
  docker info >/dev/null 2>&1
}

dockerd_running() {
  if command -v pgrep >/dev/null 2>&1; then
    pgrep -x dockerd >/dev/null 2>&1 && return 0
  fi
  [[ -S /var/run/docker.sock ]] && docker_info_ok && return 0
  return 1
}

loop_for_img() {
  local img="$1"
  losetup -j "$img" 2>/dev/null || true
}

img_loop_present() {
  local out
  out="$(loop_for_img "$DOCKER_IMG")"
  [[ -n "${out// /}" ]]
}

var_lib_docker_mounted() {
  findmnt -n /var/lib/docker >/dev/null 2>&1
}

docker_enabled_yes() {
  local v
  v="$(cfg_get DOCKER_ENABLED | tr '[:upper:]' '[:lower:]')"
  [[ "$v" == yes || "$v" == true || "$v" == "1" ]]
}

docker_timeout_value() {
  local v
  v="$(cfg_get DOCKER_TIMEOUT)"
  if [[ -z "$v" ]]; then
    v="$(cfg_get DOCKER_STOP_TIMEOUT)"
  fi
  printf '%s' "${v:-}"
}

dest_is_empty() {
  local p="$1"
  [[ -e "$p" ]] || return 0
  [[ -d "$p" ]] || return 1
  [[ -z "$(ls -A "$p" 2>/dev/null || true)" ]]
}

free_bytes_for() {
  local p="$1"
  local avail=""
  avail="$(df -B1 --output=avail "$p" 2>/dev/null | tail -1 | tr -d ' ' || true)"
  if [[ -z "$avail" || ! "$avail" =~ ^[0-9]+$ ]]; then
    avail="$(df -k "$p" | awk 'NR==2 {print $4; exit}')"
    [[ -n "$avail" ]] && avail=$((avail * 1024))
  fi
  printf '%s' "${avail:-0}"
}

require_unraid() {
  if [[ ! -f /etc/unraid-version && ! -f /boot/config/docker.cfg ]]; then
    die "This does not look like Unraid (missing /etc/unraid-version and $DOCKER_CFG). Refusing."
  fi
}

require_root() {
  if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
    die "Must run as root on the Unraid host (needed for losetup/mount/rsync of docker data-root)."
  fi
}

require_cmds() {
  local c
  for c in rsync mount umount losetup df stat mkdir findmnt blkid; do
    command -v "$c" >/dev/null 2>&1 || die "required command not in PATH: $c"
  done
}

discover_img_if_needed() {
  if [[ -f "$DOCKER_IMG" ]]; then
    return 0
  fi
  log "Default img not at $DOCKER_IMG — searching pool mounts (not /mnt/user, not /mnt/diskN)…"
  local pool base candidate
  local -a found=()
  for pool in /mnt/cache /mnt/cache_* /mnt/*; do
    [[ -d "$pool" ]] || continue
    base="$(basename "$pool")"
    case "$base" in
      user|user0|disks|remotes|addons|rootshare|scratch) continue ;;
      disk[0-9]|disk[0-9][0-9]) continue ;;
    esac
    candidate="$pool/system/docker/docker.img"
    if [[ -f "$candidate" ]]; then
      log "  found: $candidate"
      found+=("$candidate")
    fi
  done
  if [[ ${#found[@]} -eq 1 ]]; then
    DOCKER_IMG="${found[0]}"
    DOCKER_DIR="$(dirname "$DOCKER_IMG")/docker"
    log "Using discovered img: $DOCKER_IMG"
    log "Using sibling dest:   $DOCKER_DIR"
    return 0
  fi
  if [[ ${#found[@]} -gt 1 ]]; then
    die "Multiple docker.img files found. Re-run with DOCKER_IMG=/mnt/<pool>/system/docker/docker.img"
  fi
  if [[ -f /mnt/user/system/docker/docker.img ]]; then
    die "Only FUSE path exists: /mnt/user/system/docker/docker.img — locate the cache/pool file (ls /mnt/cache/system/docker/docker.img) and re-run with DOCKER_IMG=..."
  fi
  die "docker.img not found at $DOCKER_IMG (and no pool copy discovered)"
}

print_banner() {
  log "============================================================"
  log " Unraid docker.img → directory migration"
  log " log: $LOG_FILE"
  log " dry-run=$DRY_RUN  verify=$VERIFY"
  log "============================================================"
  log "THIS SCRIPT DOES NOT: stop Docker, stop projectionist, stop"
  log "smartmap, start QA, bind :8790, rm docker.img, prune, or start parity."
  log "Will drives Enable Docker in the Unraid GUI. Script waits/copies/prints."
}

print_gui_disable() {
  cat <<EOF

------------------------------------------------------------
 GUI CHECKPOINT — disable Docker (you do this; script waits)
------------------------------------------------------------
  1. Unraid UI → Settings → Docker
  2. Docker stop timeout: set to 60 seconds (not 10)
  3. Enable Docker: No
  4. Apply
  5. Wait for the GUI to finish stopping Docker

 Do NOT: docker stop projectionist / smartmap from SSH
 Do NOT: stop smartmap to "free" :8790
 Do NOT: docker start projectionist-qa

 Script will poll until ALL of these are true:
   - docker info fails
   - dockerd is not running
   - no loop device for docker.img
   - /var/lib/docker is not a mount
   - $DOCKER_CFG has DOCKER_ENABLED other than yes
------------------------------------------------------------

EOF
}

print_gui_enable() {
  cat <<EOF

------------------------------------------------------------
 GUI CHECKPOINT — switch data-root, then enable Docker
------------------------------------------------------------
  1. Unraid UI → Settings → Docker  (Docker is still disabled)
  2. Docker data-root: directory
     (not "btrfs vDisk" / "xfs vDisk")
  3. Docker directory:
       $DOCKER_DIR
     MUST be the cache/pool path. NEVER /mnt/user/system/docker/docker
  4. KEEP the vDisk file. Do not delete docker.img.
       $DOCKER_IMG
     stays on disk as rollback.
  5. Enable Docker: Yes
  6. Apply
  7. Confirm Docker containers come back (projectionist :8788, smartmap :8790).
     Do not start projectionist-qa. Do not bind anything to :8790 except smartmap.

 Then optionally:
   $0 --verify
------------------------------------------------------------

EOF
}

print_rollback() {
  cat <<EOF

------------------------------------------------------------
 ROLLBACK (if directory data-root misbehaves)
------------------------------------------------------------
  docker.img was NOT deleted. To go back to vDisk:
  1. Settings → Docker → Enable Docker: No → Apply
  2. Docker data-root: back to vDisk (btrfs or xfs — whatever it was)
  3. Docker vDisk location:
       $DOCKER_IMG
  4. Enable Docker: Yes → Apply
  5. Leave the directory copy in place until vDisk mode is healthy:
       $DOCKER_DIR
     Only then may you remove the DIRECTORY (never rm docker.img until
     you are sure you will not roll back).
------------------------------------------------------------

EOF
}

preflight_timeout() {
  local t
  t="$(docker_timeout_value)"
  log "Preflight: $DOCKER_CFG DOCKER_ENABLED=$(cfg_get DOCKER_ENABLED | tr -d '\n')"
  log "Preflight: DOCKER_TIMEOUT=${t:-<unset>} (want >= $MIN_TIMEOUT before disable)"
  log "Preflight: DOCKER_IMAGE_FILE=$(cfg_get DOCKER_IMAGE_FILE)"
  log "Preflight: DOCKER_IMAGE_TYPE=$(cfg_get DOCKER_IMAGE_TYPE)"
  if [[ -n "$t" && "$t" =~ ^[0-9]+$ && "$t" -lt $MIN_TIMEOUT ]]; then
    if docker_info_ok || docker_enabled_yes; then
      log "WARN: stop timeout is ${t}s. Set it to ${MIN_TIMEOUT} in Settings → Docker BEFORE Enable Docker: No."
      log "      Disabling with timeout 10 can SIGKILL containers mid-flush."
      if [[ "$DRY_RUN" -eq 0 && "$VERIFY" -eq 0 ]]; then
        log "Live copy will not treat Docker-down as safe until timeout is >= $MIN_TIMEOUT OR Docker is already fully down."
      fi
    else
      log "WARN: timeout is ${t}s and Docker is already down — too late to fix this stop; copy may still proceed."
    fi
  elif [[ -n "$t" && "$t" =~ ^[0-9]+$ && "$t" -ge $MIN_TIMEOUT ]]; then
    log "Preflight: timeout $t >= $MIN_TIMEOUT (ok)"
  else
    log "WARN: could not parse DOCKER_TIMEOUT from $DOCKER_CFG"
  fi
}

preflight_space() {
  local parent avail img_alloc img_apparent
  parent="$(dirname "$DOCKER_DIR")"
  [[ -d "$parent" ]] || die "parent of dest missing: $parent"
  avail="$(free_bytes_for "$parent")"
  img_alloc="$(du -B1 "$DOCKER_IMG" 2>/dev/null | awk '{print $1; exit}')"
  img_apparent="$(stat -c %s "$DOCKER_IMG" 2>/dev/null || printf '0')"
  img_alloc="${img_alloc:-0}"
  log "Preflight: cache/pool free at $parent = $(hr_bytes "$avail") ($avail bytes)"
  log "Preflight: img allocated (du)   = $(hr_bytes "$img_alloc") ($img_alloc bytes)"
  log "Preflight: img apparent (stat)  = $(hr_bytes "$img_apparent") ($img_apparent bytes)"
  df -h "$parent" "$DOCKER_IMG" 2>/dev/null | while IFS= read -r line; do
    log "df: $line"
  done
  local need=$((img_alloc + HEADROOM_FLOOR_BYTES))
  local pct=$((img_alloc * HEADROOM_PCT / 100))
  if [[ "$pct" -gt "$HEADROOM_FLOOR_BYTES" ]]; then
    need=$((img_alloc + pct))
  fi
  log "Preflight: require free >= $(hr_bytes "$need") (allocated + ${HEADROOM_PCT}% or 2GiB floor)"
  if [[ "$avail" -lt "$need" ]]; then
    die "not enough free space on $(dirname "$DOCKER_DIR") for a directory copy while keeping docker.img (free=$avail need=$need)"
  fi
  if [[ "$img_apparent" -gt 0 && "$avail" -lt "$img_apparent" ]]; then
    log "WARN: free < virtual vDisk size. Usually OK if the img is sparse / not full; post-mount du will re-check."
  fi
}

preflight_dest() {
  refuse_bad_dest "$DOCKER_DIR"
  if [[ -e "$DOCKER_DIR" && ! -d "$DOCKER_DIR" ]]; then
    die "dest exists and is not a directory: $DOCKER_DIR"
  fi
  if [[ -f "$DOCKER_DIR" ]]; then
    die "dest must not be the img file"
  fi
  local img_real dest_real
  img_real="$(realpath -m "$DOCKER_IMG")"
  dest_real="$(realpath -m "$DOCKER_DIR")"
  [[ "$img_real" == "$dest_real" ]] && die "dest resolved equal to img: $dest_real"
  if dest_is_empty "$DOCKER_DIR"; then
    log "Preflight: dest empty or absent (ok): $DOCKER_DIR"
    return 0
  fi
  log "Preflight: dest NOT empty: $DOCKER_DIR"
  ls -la "$DOCKER_DIR" 2>/dev/null | head -20 | while IFS= read -r line; do
    log "  $line"
  done
  if [[ "$CONFIRM_NONEMPTY" -eq 1 ]]; then
    log "Preflight: --i-confirm-nonempty-dest set; continuing"
    return 0
  fi
  if [[ "$DRY_RUN" -eq 1 ]]; then
    log "WARN: dest not empty (dry-run continues; live run will ask YES or need --i-confirm-nonempty-dest)"
    return 0
  fi
  if [[ -t 0 ]]; then
    printf '\nDest %s is not empty. Type YES to rsync into it anyway: ' "$DOCKER_DIR"
    local reply=""
    read -r reply
    [[ "$reply" == YES ]] || die "dest not empty; abort (re-run with --i-confirm-nonempty-dest after reviewing)"
    log "Operator typed YES for nonempty dest"
    return 0
  fi
  die "dest not empty and no TTY; re-run with --i-confirm-nonempty-dest"
}

preflight_docker_up_means_no_copy() {
  if docker_info_ok; then
    log "Preflight: docker info SUCCEEDED — Docker is still running"
    if [[ "$DRY_RUN" -eq 1 ]]; then
      log "Dry-run: expected while Docker is up. Live run will refuse copy until GUI disable completes."
      return 0
    fi
    if [[ "$VERIFY" -eq 1 && "$DRY_RUN" -eq 0 ]]; then
      return 0
    fi
    log "Live copy will not start until Docker is fully down (prompt + poll)."
    return 0
  fi
  log "Preflight: docker info failed (Docker looks down)"
}

print_cfg_snapshot() {
  if [[ ! -f "$DOCKER_CFG" ]]; then
    log "WARN: $DOCKER_CFG missing"
    return 0
  fi
  log "Preflight: docker.cfg snapshot (non-secret keys):"
  grep -E '^(DOCKER_ENABLED|DOCKER_IMAGE_FILE|DOCKER_IMAGE_SIZE|DOCKER_IMAGE_TYPE|DOCKER_TIMEOUT|DOCKER_STOP_TIMEOUT|DOCKER_APP_CONFIG_PATH)=' "$DOCKER_CFG" 2>/dev/null | while IFS= read -r line; do
    log "  $line"
  done || true
}

timeout_ok_for_disable() {
  local t
  t="$(docker_timeout_value)"
  [[ -n "$t" && "$t" =~ ^[0-9]+$ && "$t" -ge $MIN_TIMEOUT ]]
}

docker_fully_down() {
  docker_info_ok && return 1
  dockerd_running && return 1
  img_loop_present && return 1
  var_lib_docker_mounted && return 1
  docker_enabled_yes && return 1
  return 0
}

explain_not_down() {
  if docker_info_ok; then log "  still up: docker info ok"; fi
  if dockerd_running; then log "  still up: dockerd process"; fi
  if img_loop_present; then
    log "  still up: loop device for img:"
    loop_for_img "$DOCKER_IMG" | while IFS= read -r line; do log "    $line"; done
  fi
  if var_lib_docker_mounted; then
    log "  still up: /var/lib/docker mounted:"
    findmnt /var/lib/docker 2>/dev/null | while IFS= read -r line; do log "    $line"; done
  fi
  if docker_enabled_yes; then
    log "  still up: DOCKER_ENABLED=$(cfg_get DOCKER_ENABLED) in $DOCKER_CFG"
  fi
}

wait_until_docker_down() {
  local deadline=$((SECONDS + WAIT_DOWN_SECS))
  local last_nudge=0
  log "Waiting up to ${WAIT_DOWN_SECS}s for Docker to be fully down (GUI disable)…"
  print_gui_disable
  while ((SECONDS < deadline)); do
    if docker_fully_down; then
      if ! timeout_ok_for_disable; then
        log "WARN: Docker is down but timeout was $(docker_timeout_value)s (< $MIN_TIMEOUT). Proceeding with copy; this stop may have been abrupt."
      fi
      log "Docker is down: docker info fails, no dockerd, no img loop, /var/lib/docker unmounted, Enable Docker is not yes."
      return 0
    fi
    if ((SECONDS - last_nudge >= 20)); then
      last_nudge=$SECONDS
      log "…not safe to copy yet ($(date '+%H:%M:%S'))"
      explain_not_down
      if docker_info_ok || docker_enabled_yes; then
        if ! timeout_ok_for_disable; then
          log "ACTION: Settings → Docker → set stop timeout to $MIN_TIMEOUT, THEN Enable Docker: No → Apply"
        else
          log "ACTION: Settings → Docker → Enable Docker: No → Apply (timeout already >= $MIN_TIMEOUT)"
        fi
      fi
    fi
    sleep 2
  done
  log "Timed out after ${WAIT_DOWN_SECS}s waiting for Docker down. Last state:"
  explain_not_down
  die "refuse copy: Docker is not fully down (Enable Docker still yes and/or docker still running and/or loop still present)"
}

space_ok_for_tree() {
  local src="$1"
  local dest_parent="$2"
  local used avail need pct
  log "Measuring source tree (du -x -s) — may take a minute…"
  used="$(du -x -s -B1 "$src" 2>/dev/null | awk '{print $1; exit}')"
  used="${used:-0}"
  avail="$(free_bytes_for "$dest_parent")"
  pct=$((used * HEADROOM_PCT / 100))
  need=$((used + pct))
  if [[ "$HEADROOM_FLOOR_BYTES" -gt "$pct" ]]; then
    need=$((used + HEADROOM_FLOOR_BYTES))
  fi
  log "Source used: $(hr_bytes "$used") ($used bytes)"
  log "Dest free:   $(hr_bytes "$avail") ($avail bytes)"
  log "Need:        $(hr_bytes "$need") ($need bytes)"
  if [[ "$avail" -lt "$need" ]]; then
    die "not enough free space for rsync (used=$used free=$avail need=$need)"
  fi
}

loop_mount_ro() {
  local fstype opts
  LOOP_MP="$(mktemp -d /tmp/docker-img-ro-migrate.XXXXXX)"
  log "Creating read-only loop for $DOCKER_IMG"
  LOOP_DEV="$(losetup -f --show -r "$DOCKER_IMG")"
  [[ -n "$LOOP_DEV" ]] || die "losetup -f --show -r failed for $DOCKER_IMG"
  log "Loop device: $LOOP_DEV (read-only)"
  fstype="$(blkid -o value -s TYPE "$LOOP_DEV" 2>/dev/null || blkid -o value -s TYPE "$DOCKER_IMG" 2>/dev/null || true)"
  log "Filesystem type: ${fstype:-<unknown>}"
  opts="ro"
  case "$fstype" in
    xfs) opts="ro,norecovery,nouuid" ;;
    btrfs) opts="ro" ;;
    ext4|ext3|ext2) opts="ro,noload" ;;
  esac
  log "mount -o $opts $LOOP_DEV $LOOP_MP"
  if ! mount -o "$opts" "$LOOP_DEV" "$LOOP_MP"; then
    log "mount with $opts failed; trying plain ro"
    mount -o ro "$LOOP_DEV" "$LOOP_MP" || die "failed to mount $LOOP_DEV on $LOOP_MP"
  fi
  findmnt "$LOOP_MP" | while IFS= read -r line; do log "mount: $line"; done
  log "Source listing (top):"
  ls -la "$LOOP_MP" | while IFS= read -r line; do log "  $line"; done
}

umount_loop() {
  if [[ -n "$LOOP_MP" ]] && findmnt -n "$LOOP_MP" >/dev/null 2>&1; then
    log "umount $LOOP_MP"
    umount "$LOOP_MP" || die "umount failed: $LOOP_MP"
  fi
  if [[ -n "$LOOP_DEV" ]] && losetup "$LOOP_DEV" >/dev/null 2>&1; then
    log "losetup -d $LOOP_DEV"
    losetup -d "$LOOP_DEV" || die "losetup -d failed: $LOOP_DEV"
  fi
  LOOP_DEV=""
  if [[ -n "$LOOP_MP" ]]; then
    rmdir "$LOOP_MP" 2>/dev/null || true
  fi
  LOOP_MP=""
  log "Loop unmounted. docker.img left in place: $DOCKER_IMG"
}

run_rsync() {
  local src="$1"
  local rc=0
  if [[ "$DRY_RUN" -eq 1 ]]; then
    log "rsync DRY-RUN (no writes to dest)"
    log "rsync -aHAX --numeric-ids --human-readable --info=stats2,progress2 --dry-run $src/ $DOCKER_DIR/"
    rsync -aHAX --numeric-ids --human-readable --info=stats2,progress2 \
      --dry-run \
      "$src/" "$DOCKER_DIR/" || rc=$?
  else
    log "rsync -aHAX --numeric-ids --human-readable --info=stats2,progress2 $src/ $DOCKER_DIR/"
    rsync -aHAX --numeric-ids --human-readable --info=stats2,progress2 \
      "$src/" "$DOCKER_DIR/" || rc=$?
  fi
  log "rsync finished (exit $rc)"
  [[ "$rc" -eq 0 ]] || die "rsync failed with exit $rc — dest may be incomplete; docker.img was not modified"
}

http_code() {
  local url="$1"
  if ! command -v curl >/dev/null 2>&1; then
    printf ''
    return 1
  fi
  curl -sS -o /dev/null -w '%{http_code}' --max-time 5 "$url" 2>/dev/null || printf ''
}

verify_services() {
  local deadline=$((SECONDS + WAIT_VERIFY_SECS))
  local body="" code=""
  log "============================================================"
  log " VERIFY — observational only (no docker start, no QA, no :8790 bind)"
  log "============================================================"
  log "Waiting up to ${WAIT_VERIFY_SECS}s for Docker engine + prod :8788 health…"
  log "If Docker is still disabled, Enable it in the GUI now (see printed checkpoints)."

  while ((SECONDS < deadline)); do
    if docker_info_ok; then
      log "docker info: ok"
      break
    fi
    log "…waiting for docker info (Enable Docker: Yes → Apply if you have not)"
    sleep 3
  done
  if ! docker_info_ok; then
    die "verify: docker info still failing after ${WAIT_VERIFY_SECS}s — this script will not start Docker or containers"
  fi

  if command -v docker >/dev/null 2>&1; then
    log "docker ps (names/ports) — observation only:"
    docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' 2>/dev/null | while IFS= read -r line; do
      log "  $line"
    done || true
    if docker inspect projectionist-qa >/dev/null 2>&1; then
      local qs
      qs="$(docker inspect -f '{{.State.Status}}' projectionist-qa 2>/dev/null || true)"
      log "NOTE: projectionist-qa exists (status=${qs:-?}). This script will not start, stop, or bind it."
    fi
  fi

  log "Polling $PROD_HEALTH_URL"
  body=""
  while ((SECONDS < deadline)); do
    if command -v curl >/dev/null 2>&1; then
      body="$(curl -fsS --max-time 5 "$PROD_HEALTH_URL" 2>/dev/null || true)"
    fi
    if [[ -n "$body" ]]; then
      log "Prod :8788 health body: $body"
      if printf '%s' "$body" | grep -q '"status"[[:space:]]*:[[:space:]]*"ok"'; then
        log "VERIFY OK: :8788 status=ok"
        break
      fi
      log "WARN: :8788 responded but JSON missing status=ok"
    else
      log "…:8788 not healthy yet"
    fi
    sleep 3
  done
  if [[ -z "$body" ]] || ! printf '%s' "$body" | grep -q '"status"[[:space:]]*:[[:space:]]*"ok"'; then
    die "verify: :8788 health failed — inspect Docker UI / projectionist logs. This script will not docker start projectionist."
  fi

  log "Checking $SMARTMAP_URL (HTTP any response; will NOT start smartmap if down)"
  code="$(http_code "$SMARTMAP_URL")"
  if [[ -n "$code" && "$code" != "000" ]]; then
    log "VERIFY OK: :8790 HTTP $code (smartmap reachable). Never rebinding this port."
  else
    log "WARN: :8790 did not respond. This script will NOT docker start smartmap or bind :8790."
    log "      Check the household smartmap container in the Docker UI if that is unexpected."
  fi

  if command -v curl >/dev/null 2>&1; then
    code="$(http_code http://127.0.0.1:8792/)"
    if [[ -n "$code" && "$code" != "000" ]]; then
      log "NOTE: :8792 is listening (HTTP $code) — QA sidecar? Leaving it alone."
    else
      log "NOTE: :8792 not listening (QA idle). Good — this script never starts projectionist-qa."
    fi
  fi
  log "=== verify done ==="
}

copy_phase() {
  log "Step: refuse copy while Docker is up / Enable Docker yes / loop present"
  if docker_info_ok; then
    log "Docker is running — will not copy. Prompting for GUI disable."
  fi
  wait_until_docker_down

  if [[ "$DRY_RUN" -eq 0 ]]; then
    log "Step: mkdir -p $DOCKER_DIR"
    mkdir -p "$DOCKER_DIR"
    refuse_bad_dest "$DOCKER_DIR"
  else
    log "Dry-run: would mkdir -p $DOCKER_DIR"
  fi

  loop_mount_ro
  space_ok_for_tree "$LOOP_MP" "$(dirname "$DOCKER_DIR")"

  if [[ "$DRY_RUN" -eq 0 ]]; then
    log "Step: rsync whole docker root → $DOCKER_DIR"
    run_rsync "$LOOP_MP"
    log "Dest listing (top):"
    ls -la "$DOCKER_DIR" | while IFS= read -r line; do log "  $line"; done
    log "Dest du (may take a minute):"
    du -x -sh "$DOCKER_DIR" 2>/dev/null | while IFS= read -r line; do log "  $line"; done || true
  else
    log "Step: rsync -n (dry-run) whole docker root → $DOCKER_DIR"
    run_rsync "$LOOP_MP"
  fi

  umount_loop
  log "KEPT docker.img (never deleted): $DOCKER_IMG"
  ls -lh "$DOCKER_IMG" | while IFS= read -r line; do log "  $line"; done
}

# --- main ---

print_banner
require_unraid
require_root

if [[ "$VERIFY" -eq 1 && "$DRY_RUN" -eq 0 ]]; then
  # --verify is post-cutover only: never copy, never Enable Docker, never docker start.
  # Skip dest-empty / free-space preflights — after a live copy the directory is full
  # and cache free space is supposed to have dropped.
  log "--verify only (no rsync, no docker start). Prod :8788 + smartmap :8790."
  log "Host: $(hostname 2>/dev/null || echo '?')  Unraid: $(cat /etc/unraid-version 2>/dev/null || echo '?')"
  print_cfg_snapshot
  if docker_fully_down; then
    log "Docker is fully down. Enable it in the GUI; this script will poll and will not start it."
    print_gui_enable
  fi
  verify_services
  print_rollback
  exit 0
fi

require_cmds
discover_img_if_needed
refuse_bad_img "$DOCKER_IMG"
refuse_bad_dest "$DOCKER_DIR"

log "Host: $(hostname 2>/dev/null || echo '?')  Unraid: $(cat /etc/unraid-version 2>/dev/null || echo '?')"
log "Img:  $DOCKER_IMG"
log "Dest: $DOCKER_DIR"
log "Cfg:  $DOCKER_CFG"
print_cfg_snapshot
preflight_timeout
preflight_space
preflight_dest
preflight_docker_up_means_no_copy

if [[ "$DRY_RUN" -eq 1 ]]; then
  log "=== DRY-RUN mode ==="
  if docker_fully_down; then
    log "Docker is already down; dry-run will RO-mount and rsync -n"
    copy_phase
  else
    log "Docker is not fully down (normal for a rehearsal)."
    log "Would wait for GUI disable, then:"
    log "  mkdir -p $DOCKER_DIR"
    log "  losetup -f --show -r $DOCKER_IMG"
    log "  mount -o ro <loop> <tmp-mp>"
    log "  rsync -aHAX --numeric-ids --human-readable --info=stats2,progress2 <mp>/ $DOCKER_DIR/"
    log "  umount; losetup -d"
    log "  NEVER rm $DOCKER_IMG"
    print_gui_disable
    explain_not_down
  fi
  print_gui_enable
  print_rollback
  log "=== DRY-RUN complete (no Enable Docker change, img kept) ==="
  if [[ "$VERIFY" -eq 1 ]]; then
    log "Skipping --verify during dry-run while copy was not a live cutover."
  fi
  exit 0
fi

log "=== LIVE copy ==="
copy_phase
print_gui_enable
print_rollback
log "=== LIVE copy complete. docker.img kept. Enable Docker in the GUI. ==="
log "Next: GUI steps above, then: $0 --verify"
