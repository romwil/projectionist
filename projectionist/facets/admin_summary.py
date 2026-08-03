"""Read-only facet registry summary for Admin Knowledge Ops."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from projectionist.facets.overlay import overlay_taxonomy_path
from projectionist.facets.registry import get_registry


def registry_admin_summary(*, data_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Return concept/alias/pack counts plus overlay presence for the dashboard."""
    reg = get_registry()
    overlay_path = overlay_taxonomy_path(data_dir) if data_dir else None
    overlay_exists = bool(overlay_path and overlay_path.is_file())
    overlay_alias_count = 0
    if overlay_exists and overlay_path is not None:
        try:
            payload = json.loads(overlay_path.read_text(encoding="utf-8"))
            aliases = payload.get("aliases") if isinstance(payload, dict) else {}
            if isinstance(aliases, dict):
                overlay_alias_count = len(aliases)
        except (OSError, json.JSONDecodeError, UnicodeError):
            overlay_alias_count = 0

    unresolved = 0
    try:
        from projectionist.facets.closed_loop import resolve_closed_loop_database

        db = resolve_closed_loop_database()
        if db is not None:
            rows = db.list_closed_loop_events(
                event_type="unmapped_token",
                entity_type="facet",
                min_hit_count=1,
                limit=1000,
            )
            unresolved = len(rows)
    except Exception:  # noqa: BLE001 — summary must not fail closed-loop bind issues
        unresolved = 0

    source_paths: List[str] = list(getattr(reg, "source_paths", ()) or ())

    return {
        "concept_count": len(reg.concepts),
        "alias_count": len(reg.aliases),
        "pack_count": len(reg.facet_packs),
        "motif_alias_count": len(reg.motif_search_aliases),
        "overlay_path": str(overlay_path) if overlay_path else None,
        "overlay_exists": overlay_exists,
        "overlay_alias_count": overlay_alias_count,
        "unresolved_facet_signals": unresolved,
        "source_paths": source_paths,
    }
