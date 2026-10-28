"""Memory-domain agent tools (repo memory, user notes, preferences)."""

from __future__ import annotations

from projectionist.agent.tools._helpers import *  # noqa: F401, F403

class MemoryToolsMixin:
    async def _tool_recall_repo_memory(self, args: Mapping[str, Any]) -> str:
        """Return the latest cited snapshot, insights, and freshness for a known entity."""
        name = str(args.get("name") or "").strip()
        if not name:
            return json.dumps({"error": "Provide an entity name", "known": False})
        entity_type = str(args.get("entity_type") or "").strip() or None
        try:
            record = self.db.get_repository_entity(name, entity_type)
        except Exception:
            logger.exception("recall_repo_memory failed for %r", name)
            return json.dumps({"error": "Repository memory could not be read", "known": False})
        if not record:
            # P2 demand: discussed but missing from repository memory.
            kind = (entity_type or "title").strip().lower()
            if kind in {"title", "person", "company"}:
                try:
                    from projectionist.telemetry.demand import schedule_metadata_demand

                    schedule_metadata_demand(
                        entity_type=kind,
                        name=name,
                        reason="missing_snapshot",
                        context_source="recall",
                    )
                except Exception:
                    logger.debug("Could not schedule metadata demand for miss", exc_info=True)
            return json.dumps({"known": False, "name": name, "entity_type": entity_type})
        try:
            self.db.record_entity_discussion(record["entity_id"])
            record["discussion_count"] = int(record.get("discussion_count") or 0) + 1
        except Exception:
            logger.debug("Could not record recall activity", exc_info=True)
        record["frequently_discussed"] = int(record.get("discussion_count") or 0) >= 3
        record["freshness"] = _memory_freshness(record.get("known_since"), record.get("fetched_at"))
        record["known"] = True
        # P2 demand: stale or empty research snapshot while actively recalled.
        try:
            freshness = record.get("freshness") if isinstance(record.get("freshness"), dict) else {}
            snapshot = record.get("snapshot") if isinstance(record.get("snapshot"), dict) else {}
            sparse = not snapshot or bool(freshness.get("stale"))
            kind = str(record.get("entity_type") or "").strip().lower()
            if sparse and kind in {"title", "person", "company"}:
                from projectionist.telemetry.demand import schedule_metadata_demand

                reason = "stale_snapshot" if freshness.get("stale") else "sparse_snapshot"
                schedule_metadata_demand(
                    entity_type=kind,
                    name=str(record.get("name") or name),
                    reason=reason,
                    entity_id=str(record.get("entity_id") or "") or None,
                    context_source="recall",
                    extra={"age_days": freshness.get("age_days")},
                )
        except Exception:
            logger.debug("Could not schedule metadata demand for stale recall", exc_info=True)
        return json.dumps(record)

    async def _tool_search_memory(self, args: Mapping[str, Any]) -> str:
        """Fuzzy-list known repository entities for 'what do I already know about X'."""
        query = str(args.get("query") or "").strip()
        if not query:
            return json.dumps({"error": "Provide a search query", "matches": []})
        try:
            limit = min(max(1, int(args.get("limit") or 10)), 50)
        except (TypeError, ValueError):
            limit = 10
        try:
            matches = self.db.search_repository_memory(query, limit=limit)
        except Exception:
            logger.exception("search_memory failed for %r", query)
            return json.dumps({"error": "Repository memory could not be searched", "matches": []})
        for match in matches:
            match["freshness"] = _memory_freshness(match.get("known_since"), match.get("fetched_at"))
        return json.dumps({"query": query, "count": len(matches), "matches": matches})

    async def _tool_save_repo_insight(self, args: Mapping[str, Any]) -> str:
        """Persist a durable, source-cited insight against a known repository entity."""
        insight = str(args.get("insight") or "").strip()
        if not insight:
            return json.dumps({"error": "Provide insight text"})
        entity_id = str(args.get("entity_id") or "").strip()
        name = str(args.get("name") or "").strip()
        entity_type = str(args.get("entity_type") or "").strip() or None
        try:
            if not entity_id and name:
                entity_id = self.db.resolve_memory_entity_id(name, entity_type) or ""
            if not entity_id:
                return json.dumps(
                    {"error": "Unknown entity; research it first so it exists in repository memory", "saved": False}
                )
            saved = self.db.save_repository_insight(entity_id, insight, args.get("citations"))
        except ValueError as error:
            return json.dumps({"error": str(error), "saved": False})
        except Exception:
            logger.exception("save_repo_insight failed for entity %r", entity_id or name)
            return json.dumps({"error": "Insight could not be saved", "saved": False})
        return json.dumps({"saved": True, "id": saved["id"], "entity_id": saved["entity_id"]})

    async def _tool_remember_preference(self, args: Mapping[str, Any]) -> str:
        denied = self._deny_personal_mutation_if_gated()
        if denied:
            return denied
        from projectionist.models.schemas import PreferenceSignal

        remember_preference(
            self.db,
            PreferenceSignal(
                signal_type="explicit",
                text=str(args.get("text") or ""),
                lens_id=self.lens_id,
            ),
            user_id=self.user_id,
        )
        return json.dumps({"saved": True})

    async def _tool_remember_about_user(self, args: Mapping[str, Any]) -> str:
        denied = self._deny_personal_mutation_if_gated()
        if denied:
            return denied
        if not self.user_id:
            return json.dumps({"error": "Private memory requires an authenticated household account"})
        from projectionist.memory import UserMemoryService

        metadata = _callback_title_metadata(args)
        try:
            note = UserMemoryService(self.db).remember(
                caller_id=self.user_id,
                kind=str(args.get("kind") or "self_disclosure"),
                text=str(args.get("text") or ""),
                metadata=metadata or None,
            )
        except ValueError as error:
            return json.dumps({"error": str(error)})
        if not note:
            logger.error("User memory note was not available after creation for user %s", self.user_id)
            return json.dumps({"error": "Could not save private memory note; please try again"})
        enriched = _enrich_memory_note_deep_link(note)
        return json.dumps(
            {
                "saved": True,
                "id": enriched["id"],
                "kind": enriched["kind"],
                "deep_link": enriched.get("deep_link"),
                "title_card": enriched.get("title_card"),
            }
        )

    async def _tool_recall_user_memory(self, args: Mapping[str, Any]) -> str:
        if not self.user_id:
            return json.dumps({"error": "Private memory requires an authenticated household account"})
        from projectionist.memory import UserMemoryService

        notes = UserMemoryService(self.db).recall(
            caller_id=self.user_id,
            caller_role=self.user_role,
            limit=min(max(1, int(args.get("limit") or 20)), 100),
        )
        enriched = [_enrich_memory_note_deep_link(note) for note in notes]
        return json.dumps({"notes": enriched})

