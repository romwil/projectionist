"""Whether Investigate Apply may rename files on disk.

The shipped library mount is read-only. Apply runs only when the owner turns
on file renames and the folders this process can see are writable.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Sequence

RENAMES_OFF = (
    "File renames are off. Turn on Allow file renames, and mount the library "
    "read-write, before Apply can rename files."
)
LIBRARY_MISSING = "The library folders are not mounted, so Apply cannot rename files."
LIBRARY_READONLY = (
    "The library is mounted read-only, so Apply cannot rename files. "
    "Mount it read-write only while you are renaming, then mount it read-only again."
)


def file_rename_refusal(settings: Any, *, roots: Sequence[Path] | None = None) -> str | None:
    """A sentence when Apply must refuse, or None when a rename may start."""
    features = getattr(settings, "features", None)
    if not bool(getattr(features, "allow_file_renames", False)):
        return RENAMES_OFF
    if roots is None:
        from projectionist.library.episode_investigate.path_map import configured_local_roots

        roots = [Path(item) for item in configured_local_roots(settings)]
    existing = [Path(root) for root in roots if Path(root).is_dir()]
    if not existing:
        return LIBRARY_MISSING
    if any(not os.access(root, os.W_OK) for root in existing):
        return LIBRARY_READONLY
    return None


def file_rename_status(settings: Any, *, roots: Sequence[Path] | None = None) -> dict[str, Any]:
    reason = file_rename_refusal(settings, roots=roots)
    return {"allowed": reason is None, "reason": reason or ""}
