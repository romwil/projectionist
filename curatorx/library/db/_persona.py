"""Lenses, derived contexts, persona, and persona templates.

Behavior-preserving split of the original ``curatorx.library.db`` module: this
mixin carries a verbatim cluster of ``Database`` methods. Composed back into the
single ``Database`` class in ``curatorx/library/db/__init__.py``.
"""

from __future__ import annotations

import sqlite3
from typing import (
    Any,
    Dict,
    List,
    Optional,
)

from ._shared import (
    ACTIVE_CONTEXT_CONFIG_KEY,
    ACTIVE_LENS_CONFIG_KEY,
    CURATOR_NAME_CONFIG_KEY,
    DEFAULT_CONTEXT_HASH,
    DEFAULT_LENS_ID,
    DEFAULT_PERSONA_ID,
)


class PersonaLensesMixin:
    def get_active_lens_id(self) -> str:
        return self.get_config(ACTIVE_LENS_CONFIG_KEY, DEFAULT_LENS_ID) or DEFAULT_LENS_ID

    def set_active_lens_id(self, lens_id: str) -> None:
        if not self.get_lens(lens_id):
            raise ValueError(f"Unknown lens_id: {lens_id}")
        self.set_config(ACTIVE_LENS_CONFIG_KEY, lens_id)

    # --- Derived contexts ---

    def get_derived_context(self, context_hash: str) -> Optional[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(
                "SELECT * FROM derived_contexts WHERE context_hash = ?",
                (context_hash,),
            ).fetchone()

    def get_active_derived_context(self) -> sqlite3.Row:
        active_hash = self.get_config(ACTIVE_CONTEXT_CONFIG_KEY, DEFAULT_CONTEXT_HASH) or DEFAULT_CONTEXT_HASH
        row = self.get_derived_context(active_hash)
        if row:
            return row
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO derived_contexts (
                    context_hash, inferred_label, thematic_centroid_json, interaction_density
                ) VALUES (?, 'General Exploration', NULL, 1)
                """,
                (DEFAULT_CONTEXT_HASH,),
            )
        row = self.get_derived_context(DEFAULT_CONTEXT_HASH)
        assert row is not None
        return row

    def update_derived_context_label(self, context_hash: str, label: str) -> None:
        cleaned = str(label or "").strip()
        if not cleaned:
            return
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE derived_contexts
                SET inferred_label = ?, last_active_at = CURRENT_TIMESTAMP
                WHERE context_hash = ?
                """,
                (cleaned, context_hash),
            )

    # --- Persona ---

    def get_persona(self, metric_id: str = DEFAULT_PERSONA_ID) -> Optional[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(
                "SELECT * FROM curator_persona_metrics WHERE metric_id = ?",
                (metric_id,),
            ).fetchone()

    def upsert_persona(
        self,
        *,
        metric_id: str = DEFAULT_PERSONA_ID,
        curator_name: Optional[str] = None,
        persona_identity: Optional[str] = None,
        val_bro_prof: Optional[float] = None,
        val_dipl_snark: Optional[float] = None,
        val_pass_auto: Optional[float] = None,
        persona_preset_id: Optional[str] = ...,  # type: ignore[assignment]
        persona_prompt_override: Optional[str] = ...,  # type: ignore[assignment]
        clear_persona_override: bool = False,
    ) -> sqlite3.Row:
        current = self.get_persona(metric_id)
        name = curator_name if curator_name is not None else (current["curator_name"] if current else "Curator")
        identity = (
            persona_identity
            if persona_identity is not None
            else (str(current["persona_identity"] or "") if current and "persona_identity" in current.keys() else "")
        )
        bro = val_bro_prof if val_bro_prof is not None else (float(current["val_bro_prof"]) if current else 0.5)
        snark = val_dipl_snark if val_dipl_snark is not None else (float(current["val_dipl_snark"]) if current else 0.5)
        auto = val_pass_auto if val_pass_auto is not None else (float(current["val_pass_auto"]) if current else 0.5)

        if persona_preset_id is ...:
            preset_id = str(current["persona_preset_id"] or "") if current and "persona_preset_id" in current.keys() else None
            preset_id = preset_id or None
        else:
            preset_id = persona_preset_id

        if clear_persona_override:
            override = None
        elif persona_prompt_override is ...:
            override = (
                str(current["persona_prompt_override"])
                if current and current["persona_prompt_override"] is not None
                else None
            )
        else:
            override = persona_prompt_override

        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO curator_persona_metrics (
                    metric_id, curator_name, persona_identity, val_bro_prof, val_dipl_snark,
                    val_pass_auto, persona_preset_id, persona_prompt_override, last_modified
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(metric_id) DO UPDATE SET
                    curator_name=excluded.curator_name,
                    persona_identity=excluded.persona_identity,
                    val_bro_prof=excluded.val_bro_prof,
                    val_dipl_snark=excluded.val_dipl_snark,
                    val_pass_auto=excluded.val_pass_auto,
                    persona_preset_id=excluded.persona_preset_id,
                    persona_prompt_override=excluded.persona_prompt_override,
                    last_modified=CURRENT_TIMESTAMP
                """,
                (metric_id, name, identity, bro, snark, auto, preset_id, override),
            )
        if curator_name is not None:
            self.set_config(CURATOR_NAME_CONFIG_KEY, name)
        persona = self.get_persona(metric_id)
        assert persona is not None
        return persona

    # --- Persona Templates ---

    _PERSONA_TEMPLATE_COLS = (
        "id, name, visibility, owner_user_id, "
        "val_bro_prof, val_dipl_snark, val_pass_auto, "
        "val_depth, val_obscurity, val_verbosity, val_formality, "
        "system_prompt_override, accent_color, is_default, created_at"
    )

    def _row_to_persona_template(self, row: sqlite3.Row) -> Dict[str, Any]:
        return {
            "id": str(row["id"]),
            "name": str(row["name"]),
            "visibility": str(row["visibility"]),
            "owner_user_id": row["owner_user_id"],
            "val_bro_prof": float(row["val_bro_prof"]),
            "val_dipl_snark": float(row["val_dipl_snark"]),
            "val_pass_auto": float(row["val_pass_auto"]),
            "val_depth": float(row["val_depth"]),
            "val_obscurity": float(row["val_obscurity"]),
            "val_verbosity": float(row["val_verbosity"]),
            "val_formality": float(row["val_formality"]),
            "system_prompt_override": row["system_prompt_override"],
            "accent_color": row["accent_color"],
            "is_default": bool(row["is_default"]),
            "created_at": str(row["created_at"]) if row["created_at"] else None,
        }

    def list_persona_templates(
        self,
        *,
        user_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Return persona templates visible to a given user.

        Visibility rules:
        - ``builtin`` templates are always visible.
        - ``shared`` templates are always visible.
        - ``private`` templates are only visible to their owner.
        """
        with self.connect() as conn:
            if user_id is None:
                rows = conn.execute(
                    f"SELECT {self._PERSONA_TEMPLATE_COLS} FROM persona_templates "
                    "WHERE visibility IN ('builtin', 'shared') "
                    "ORDER BY visibility ASC, name ASC"
                ).fetchall()
            else:
                rows = conn.execute(
                    f"SELECT {self._PERSONA_TEMPLATE_COLS} FROM persona_templates "
                    "WHERE visibility IN ('builtin', 'shared') "
                    "   OR (visibility = 'private' AND owner_user_id = ?) "
                    "ORDER BY visibility ASC, name ASC",
                    (user_id,),
                ).fetchall()
        return [self._row_to_persona_template(row) for row in rows]

    def get_persona_template(self, template_id: str) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            row = conn.execute(
                f"SELECT {self._PERSONA_TEMPLATE_COLS} FROM persona_templates WHERE id = ?",
                (template_id,),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_persona_template(row)

    def create_persona_template(
        self,
        *,
        template_id: str,
        name: str,
        visibility: str = "shared",
        owner_user_id: Optional[str] = None,
        val_bro_prof: float = 0.5,
        val_dipl_snark: float = 0.5,
        val_pass_auto: float = 0.5,
        val_depth: float = 0.5,
        val_obscurity: float = 0.5,
        val_verbosity: float = 0.5,
        val_formality: float = 0.5,
        system_prompt_override: Optional[str] = None,
        accent_color: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a new persona template.

        Owner-created templates are ``shared`` (visible to all users);
        member-created templates are ``private`` (visible only to the creator).
        """
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO persona_templates (
                    id, name, visibility, owner_user_id,
                    val_bro_prof, val_dipl_snark, val_pass_auto,
                    val_depth, val_obscurity, val_verbosity, val_formality,
                    system_prompt_override, accent_color
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    template_id, name, visibility, owner_user_id,
                    val_bro_prof, val_dipl_snark, val_pass_auto,
                    val_depth, val_obscurity, val_verbosity, val_formality,
                    system_prompt_override, accent_color,
                ),
            )
        template = self.get_persona_template(template_id)
        assert template is not None
        return template

    def update_persona_template(
        self,
        template_id: str,
        *,
        name: Optional[str] = None,
        val_bro_prof: Optional[float] = None,
        val_dipl_snark: Optional[float] = None,
        val_pass_auto: Optional[float] = None,
        val_depth: Optional[float] = None,
        val_obscurity: Optional[float] = None,
        val_verbosity: Optional[float] = None,
        val_formality: Optional[float] = None,
        system_prompt_override: Optional[str] = ...,  # type: ignore[assignment]
        accent_color: Optional[str] = ...,  # type: ignore[assignment]
    ) -> Dict[str, Any]:
        """Update a custom persona template. Built-in templates are immutable."""
        current = self.get_persona_template(template_id)
        if current is None:
            raise ValueError(f"Unknown persona template: {template_id}")
        if current["visibility"] == "builtin":
            raise ValueError("Built-in persona templates are immutable")

        resolved = {
            "name": name if name is not None else current["name"],
            "val_bro_prof": val_bro_prof if val_bro_prof is not None else current["val_bro_prof"],
            "val_dipl_snark": val_dipl_snark if val_dipl_snark is not None else current["val_dipl_snark"],
            "val_pass_auto": val_pass_auto if val_pass_auto is not None else current["val_pass_auto"],
            "val_depth": val_depth if val_depth is not None else current["val_depth"],
            "val_obscurity": val_obscurity if val_obscurity is not None else current["val_obscurity"],
            "val_verbosity": val_verbosity if val_verbosity is not None else current["val_verbosity"],
            "val_formality": val_formality if val_formality is not None else current["val_formality"],
            "system_prompt_override": (
                system_prompt_override if system_prompt_override is not ... else current["system_prompt_override"]
            ),
            "accent_color": accent_color if accent_color is not ... else current["accent_color"],
        }
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE persona_templates SET
                    name = ?, val_bro_prof = ?, val_dipl_snark = ?, val_pass_auto = ?,
                    val_depth = ?, val_obscurity = ?, val_verbosity = ?, val_formality = ?,
                    system_prompt_override = ?, accent_color = ?
                WHERE id = ?
                """,
                (
                    resolved["name"],
                    resolved["val_bro_prof"], resolved["val_dipl_snark"], resolved["val_pass_auto"],
                    resolved["val_depth"], resolved["val_obscurity"],
                    resolved["val_verbosity"], resolved["val_formality"],
                    resolved["system_prompt_override"], resolved["accent_color"],
                    template_id,
                ),
            )
        updated = self.get_persona_template(template_id)
        assert updated is not None
        return updated

    def delete_persona_template(self, template_id: str) -> bool:
        """Delete a custom persona template. Built-in templates cannot be deleted."""
        current = self.get_persona_template(template_id)
        if current is None:
            return False
        if current["visibility"] == "builtin":
            raise ValueError("Built-in persona templates cannot be deleted")
        with self.connect() as conn:
            conn.execute("DELETE FROM persona_templates WHERE id = ?", (template_id,))
        return True

    def set_user_default_persona(self, user_id: str, persona_id: str) -> None:
        """Set a user's default persona template for new conversations."""
        with self.connect() as conn:
            conn.execute(
                "UPDATE users SET default_persona_id = ? WHERE id = ?",
                (persona_id, user_id),
            )

    def get_user_default_persona_id(self, user_id: str) -> Optional[str]:
        """Return the user's default persona template ID, or None."""
        with self.connect() as conn:
            row = conn.execute(
                "SELECT default_persona_id FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
        if row is None:
            return None
        return row["default_persona_id"]

    def set_thread_persona(self, session_id: str, persona_id: Optional[str]) -> None:
        """Attach or update a persona template on a chat thread."""
        with self.connect() as conn:
            conn.execute(
                "UPDATE chat_sessions SET persona_id = ? WHERE id = ?",
                (persona_id, session_id),
            )

    def get_thread_persona_id(self, session_id: str) -> Optional[str]:
        """Return the persona_id attached to a thread, or None."""
        with self.connect() as conn:
            row = conn.execute(
                "SELECT persona_id FROM chat_sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
        if row is None:
            return None
        return row["persona_id"]

    # --- Lenses ---

    def list_lenses(self) -> List[sqlite3.Row]:
        with self.connect() as conn:
            return list(
                conn.execute(
                    "SELECT * FROM curation_lenses ORDER BY created_at ASC, lens_name ASC"
                ).fetchall()
            )

    def get_lens(self, lens_id: str) -> Optional[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(
                "SELECT * FROM curation_lenses WHERE lens_id = ?",
                (lens_id,),
            ).fetchone()

    def create_lens(self, lens_id: str, lens_name: str, description: str = "") -> sqlite3.Row:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO curation_lenses (lens_id, lens_name, description)
                VALUES (?, ?, ?)
                """,
                (lens_id, lens_name, description),
            )
        lens = self.get_lens(lens_id)
        assert lens is not None
        return lens

    def update_lens(
        self,
        lens_id: str,
        *,
        lens_name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> sqlite3.Row:
        current = self.get_lens(lens_id)
        if not current:
            raise ValueError(f"Unknown lens_id: {lens_id}")
        name = lens_name if lens_name is not None else current["lens_name"]
        desc = description if description is not None else (current["description"] or "")
        with self.connect() as conn:
            conn.execute(
                "UPDATE curation_lenses SET lens_name = ?, description = ? WHERE lens_id = ?",
                (name, desc, lens_id),
            )
        lens = self.get_lens(lens_id)
        assert lens is not None
        return lens

    # --- Lens taste profile ---

    def get_lens_taste_profile(self, lens_id: str) -> List[sqlite3.Row]:
        with self.connect() as conn:
            return list(
                conn.execute(
                    """
                    SELECT * FROM lens_taste_profile
                    WHERE lens_id = ?
                    ORDER BY weight DESC, cluster_tag ASC
                    """,
                    (lens_id,),
                ).fetchall()
            )

    def set_lens_taste_weight(
        self,
        lens_id: str,
        cluster_tag: str,
        weight: float,
        *,
        explicit_lock: Optional[bool] = None,
        respect_lock: bool = True,
    ) -> None:
        if not self.get_lens(lens_id):
            raise ValueError(f"Unknown lens_id: {lens_id}")
        with self.connect() as conn:
            existing = conn.execute(
                "SELECT * FROM lens_taste_profile WHERE lens_id = ? AND cluster_tag = ?",
                (lens_id, cluster_tag),
            ).fetchone()
            if existing and respect_lock and int(existing["explicit_lock"]) == 1 and explicit_lock is None:
                return
            lock_value = (
                int(bool(explicit_lock))
                if explicit_lock is not None
                else (int(existing["explicit_lock"]) if existing else 0)
            )
            conn.execute(
                """
                INSERT INTO lens_taste_profile (lens_id, cluster_tag, weight, explicit_lock, last_updated)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(lens_id, cluster_tag) DO UPDATE SET
                    weight=excluded.weight,
                    explicit_lock=excluded.explicit_lock,
                    last_updated=CURRENT_TIMESTAMP
                """,
                (lens_id, cluster_tag, weight, lock_value),
            )

    # --- Chat (lens-scoped) ---

    DEFAULT_THREAD_TITLE = "New conversation"

