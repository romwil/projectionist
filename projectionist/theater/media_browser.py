"""Container-visible media folder browser for owner Live settings.

Roots are known media paths plus Docker bind mounts the process can see
(``/proc/self/mountinfo``). The rest of the container filesystem is not offered
as media.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

_PSEUDO_FS = frozenset(
    {
        "proc",
        "sysfs",
        "cgroup",
        "cgroup2",
        "tmpfs",
        "devtmpfs",
        "devpts",
        "mqueue",
        "securityfs",
        "pstore",
        "bpf",
        "tracefs",
        "debugfs",
        "nsfs",
        "autofs",
        "binfmt_misc",
        "configfs",
        "fusectl",
        "rpc_pipefs",
        "overlay",
    }
)
_SYSTEM_PREFIXES = (
    "/proc",
    "/sys",
    "/dev",
    "/usr",
    "/bin",
    "/lib",
    "/opt",
    "/app",
    "/etc",
    "/run",
    "/tmp",
    "/var",
    "/root",
    "/home",
)
_KNOWN_MEDIA = ("/preroll", "/tv", "/movies", "/music", "/media")
_KNOWN_MOUNT_NAMES = frozenset({"preroll", "tv", "movies", "music", "media"})


def _unescape_mount(value: str) -> str:
    return (
        value.replace("\\040", " ")
        .replace("\\011", "\t")
        .replace("\\012", "\n")
        .replace("\\134", "\\")
    )


def parse_mountinfo(text: str) -> List[Dict[str, str]]:
    """Parse ``/proc/self/mountinfo`` lines into root / mountpoint / fstype."""
    mounts: List[Dict[str, str]] = []
    for raw in str(text or "").splitlines():
        line = raw.strip()
        if " - " not in line:
            continue
        left, right = line.split(" - ", 1)
        left_parts = left.split()
        right_parts = right.split()
        if len(left_parts) < 5 or len(right_parts) < 1:
            continue
        mounts.append(
            {
                "root": _unescape_mount(left_parts[3]),
                "mountpoint": _unescape_mount(left_parts[4]),
                "fstype": right_parts[0],
            }
        )
    return mounts


def is_shared_in_mount(mount: Dict[str, str]) -> bool:
    """True for a Docker bind (or known media mount) shared into the container."""
    mountpoint = str(mount.get("mountpoint") or "")
    if mountpoint in {"", "/"} or not mountpoint.startswith("/"):
        return False
    if _is_system_path(mountpoint):
        return False
    if str(mount.get("fstype") or "") in _PSEUDO_FS:
        return False
    root = str(mount.get("root") or "/")
    if root not in {"", "/"}:
        return True
    name = mountpoint.rstrip("/").rsplit("/", 1)[-1].lower()
    return name in _KNOWN_MOUNT_NAMES


def _is_system_path(path: str) -> bool:
    cleaned = str(path or "")
    if cleaned in {"", "/"}:
        return True
    return any(cleaned == prefix or cleaned.startswith(prefix + "/") for prefix in _SYSTEM_PREFIXES)


def read_mountinfo() -> str:
    try:
        return Path("/proc/self/mountinfo").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _bindish(mount: Dict[str, str]) -> bool:
    mountpoint = str(mount.get("mountpoint") or "")
    if mountpoint in {"", "/"}:
        return False
    if str(mount.get("fstype") or "") in _PSEUDO_FS:
        return False
    root = str(mount.get("root") or "/")
    if root not in {"", "/"}:
        return True
    name = mountpoint.rstrip("/").rsplit("/", 1)[-1].lower()
    return name in _KNOWN_MOUNT_NAMES


def bind_mount_points(
    mountinfo_text: Optional[str] = None,
    *,
    include_points: Optional[Sequence[str]] = None,
) -> List[str]:
    """Shared-in mountpoints, plus configured media paths that are themselves binds."""
    text = read_mountinfo() if mountinfo_text is None else mountinfo_text
    configured = set()
    for raw in include_points or []:
        try:
            resolved = str(Path(raw).resolve())
        except OSError:
            continue
        configured.add(resolved.rstrip("/") or resolved)
    points: List[str] = []
    seen = set()
    for mount in parse_mountinfo(text):
        point = mount["mountpoint"].rstrip("/") or mount["mountpoint"]
        highlight = is_shared_in_mount(mount) or (point in configured and _bindish(mount))
        if not highlight or point in seen:
            continue
        seen.add(point)
        points.append(point)
    return points


def _existing_dir(raw: str, *, allow_any: bool = False) -> Optional[Path]:
    text = str(raw or "").strip()
    if not text or text == "/":
        return None
    if not allow_any and _is_system_path(text):
        return None
    path = Path(text)
    try:
        if not path.is_dir():
            return None
        resolved = path.resolve()
    except OSError:
        return None
    if str(resolved) == "/":
        return None
    if not allow_any and _is_system_path(str(resolved)):
        return None
    return resolved


def allowed_media_roots(
    *,
    settings: Any = None,
    environ: Optional[Any] = None,
    mountinfo_text: Optional[str] = None,
) -> List[Path]:
    """Directories the owner may browse or save as the muzak folder."""
    from projectionist.theater.preroll import resolve_preroll_root

    discovered: List[tuple[str, bool]] = [(raw, False) for raw in _KNOWN_MEDIA]
    if settings is not None:
        for attr in ("movies_root", "tv_root"):
            discovered.append((str(getattr(settings, attr, "") or ""), True))
    preroll = resolve_preroll_root(environ)
    if preroll is not None:
        discovered.append((str(preroll), True))
    configured_points: List[str] = []
    if settings is not None:
        for attr in ("movies_root", "tv_root"):
            configured_points.append(str(getattr(settings, attr, "") or ""))
    if preroll is not None:
        configured_points.append(str(preroll))
    for point in bind_mount_points(mountinfo_text, include_points=configured_points):
        discovered.append((point, True))
    roots: List[Path] = []
    seen = set()
    for raw, allow_any in discovered:
        resolved = _existing_dir(raw, allow_any=allow_any)
        if resolved is None:
            continue
        key = str(resolved)
        if key in seen:
            continue
        seen.add(key)
        roots.append(resolved)
    return roots


def resolve_within_roots(raw: str, roots: Sequence[Path]) -> Optional[Path]:
    """Resolve ``raw`` and accept it only when it stays inside an allowed root.

    Symlinks and ``..`` are followed, then rejected if they leave the roots.
    """
    text = str(raw or "").strip()
    if not text or "\x00" in text or text == "/":
        return None
    candidate = Path(text)
    if not candidate.is_absolute():
        return None
    try:
        resolved = candidate.resolve()
    except OSError:
        return None
    if str(resolved) == "/":
        return None
    for root in roots:
        try:
            root_resolved = root.resolve()
        except OSError:
            continue
        if resolved == root_resolved or root_resolved in resolved.parents:
            return resolved
    return None


def _entry(path: Path, *, bind_points: Iterable[str]) -> Dict[str, Any]:
    key = str(path)
    mounts = {point.rstrip("/") for point in bind_points}
    return {
        "name": path.name or key,
        "path": key,
        "is_dir": True,
        "bind_mount": key in mounts,
    }


def browse_media(
    path: str = "",
    *,
    settings: Any = None,
    environ: Optional[Any] = None,
    mountinfo_text: Optional[str] = None,
) -> Dict[str, Any]:
    """List allowed roots, or one directory level under them."""
    roots = allowed_media_roots(settings=settings, environ=environ, mountinfo_text=mountinfo_text)
    mounts = bind_mount_points(mountinfo_text, include_points=[str(root) for root in roots])
    if not str(path or "").strip():
        return {
            "path": "",
            "parent": None,
            "entries": [_entry(root, bind_points=mounts) for root in roots],
            "note": (
                "Shared in marks folders mounted from the host. "
                "Other container files stay hidden."
            ),
        }
    resolved = resolve_within_roots(path, roots)
    if resolved is None or not resolved.is_dir():
        raise ValueError("That folder isn’t in a media location this container can see.")
    entries: List[Dict[str, Any]] = []
    try:
        children = sorted(resolved.iterdir(), key=lambda item: item.name.lower())
    except OSError as exc:
        raise ValueError("That folder isn’t readable.") from exc
    for child in children:
        if child.name.startswith(".") or child.is_symlink():
            continue
        try:
            if not child.is_dir():
                continue
            child_resolved = child.resolve()
        except OSError:
            continue
        if resolve_within_roots(str(child_resolved), roots) is None:
            continue
        entries.append(_entry(child_resolved, bind_points=mounts))
    parent: Optional[str] = ""
    if any(resolved == root.resolve() for root in roots):
        parent = ""
    else:
        parent_path = resolved.parent
        if resolve_within_roots(str(parent_path), roots) is None:
            parent = ""
        else:
            parent = str(parent_path)
    return {
        "path": str(resolved),
        "parent": parent,
        "entries": entries,
        "bind_mount": str(resolved) in {point.rstrip("/") for point in mounts},
        "note": "Shared in marks folders mounted from the host.",
    }


def confine_muzak_folder(
    raw: str,
    *,
    settings: Any = None,
    environ: Optional[Any] = None,
    mountinfo_text: Optional[str] = None,
) -> Optional[Path]:
    """Return a directory under allowed roots, or None when empty/invalid."""
    text = str(raw or "").strip()
    if not text:
        return None
    roots = allowed_media_roots(settings=settings, environ=environ, mountinfo_text=mountinfo_text)
    resolved = resolve_within_roots(text, roots)
    if resolved is None or not resolved.is_dir():
        return None
    return resolved
