"""Curated-list agent tools."""

from __future__ import annotations

from projectionist.agent.tools._helpers import *  # noqa: F401, F403

class ListsToolsMixin:
    def _resolve_curated_list_id(self, args: Mapping[str, Any]) -> tuple[Optional[str], Optional[str]]:
        user_id = self.user_id if self.settings.features.multi_user_enabled else None
        list_id = str(args.get("list_id") or "").strip() or None
        list_name = str(args.get("list_name") or "").strip() or None
        if list_id:
            found = self.db.get_curated_list(list_id, user_id=user_id)
            if found is None:
                return None, "List not found"
            return str(found["id"]), None
        if list_name:
            for candidate in self.db.list_curated_lists(user_id=user_id):
                if str(candidate["name"]).strip().lower() == list_name.lower():
                    return str(candidate["id"]), None
            return None, "List not found"
        return None, "list_id or list_name is required"

    async def _tool_list_lists(self, args: Mapping[str, Any]) -> str:
        del args
        user_id = self.user_id if self.settings.features.multi_user_enabled else None
        items = self.db.list_curated_lists(user_id=user_id)
        return json.dumps({"items": items, "count": len(items)})

    async def _tool_create_list(self, args: Mapping[str, Any]) -> str:
        denied = self._deny_personal_mutation_if_gated()
        if denied:
            return denied
        name = str(args.get("name") or "").strip()
        if not name:
            return json.dumps({"error": "name is required"})
        list_kind = str(args.get("list_kind") or "list").strip().lower() or "list"
        if list_kind not in {"list", "playlist", "course"}:
            return json.dumps({"error": "list_kind must be list, playlist, or course"})
        publish = bool(args.get("publish"))
        if (
            publish
            and self.settings.features.multi_user_enabled
            and (self.user_role or "") != "owner"
        ):
            return json.dumps(
                {"error": "Only the household owner can publish a collection or course."}
            )
        raw_items = args.get("items") or []
        if not isinstance(raw_items, list):
            return json.dumps({"error": "items must be an array"})
        user_id = self.user_id if self.settings.features.multi_user_enabled else None
        try:
            created = self.db.create_curated_list(
                list_id=str(uuid.uuid4()),
                user_id=user_id,
                name=name,
                description=str(args.get("description") or ""),
                list_kind=list_kind,
            )
        except ValueError as error:
            return json.dumps({"error": str(error)})
        list_id = str(created["id"])

        # Every step reports its own outcome: a partially built list must say so
        # instead of looking like a success (or a blank failure).
        added: List[Dict[str, Any]] = []
        failed: List[Dict[str, Any]] = []
        for raw in raw_items:
            entry = raw if isinstance(raw, Mapping) else {}
            title = str(entry.get("title") or "").strip()
            tmdb_id = entry.get("tmdb_id")
            tvdb_id = entry.get("tvdb_id")
            if not title or (tmdb_id is None and tvdb_id is None):
                failed.append({"title": title, "error": "title and tmdb_id or tvdb_id are required"})
                continue
            try:
                added.append(
                    self.db.add_curated_list_item(
                        item_id=str(uuid.uuid4()),
                        list_id=list_id,
                        user_id=user_id,
                        tmdb_id=int(tmdb_id) if tmdb_id is not None else None,
                        tvdb_id=int(tvdb_id) if tvdb_id is not None else None,
                        media_type=str(entry.get("media_type") or "movie"),
                        title=title,
                    )
                )
            except (ValueError, TypeError) as error:
                failed.append({"title": title, "error": str(error)})

        published = False
        publish_error: Optional[str] = None
        if publish:
            try:
                updated = self.db.set_curated_list_visibility(
                    list_id, user_id=user_id, visibility="published"
                )
                published = updated is not None
                if updated is not None:
                    created = updated
                else:
                    publish_error = "List not found when publishing"
            except ValueError as error:
                publish_error = str(error)

        payload: Dict[str, Any] = {
            "list": created,
            "list_kind": list_kind,
            "scope": "projectionist",
            "published": published,
            "items_added": len(added),
        }
        if failed:
            payload["items_failed"] = failed
        if publish and not published:
            payload["error"] = (
                f"List '{name}' was created but could not be published: "
                f"{publish_error or 'unknown error'}. It is still private."
            )
        elif failed:
            payload["warning"] = (
                f"{len(failed)} of {len(raw_items)} item(s) could not be added; "
                "tell the user which ones."
            )
        return json.dumps(payload)

    async def _tool_add_to_list(self, args: Mapping[str, Any]) -> str:
        denied = self._deny_personal_mutation_if_gated()
        if denied:
            return denied
        list_id, error = self._resolve_curated_list_id(args)
        if error:
            return json.dumps({"error": error})
        title = str(args.get("title") or "").strip()
        media_type = str(args.get("media_type") or "movie")
        tmdb_id = args.get("tmdb_id")
        tvdb_id = args.get("tvdb_id")
        if not title:
            return json.dumps({"error": "title is required"})
        if tmdb_id is None and tvdb_id is None:
            return json.dumps({"error": "tmdb_id or tvdb_id is required"})
        user_id = self.user_id if self.settings.features.multi_user_enabled else None
        try:
            item = self.db.add_curated_list_item(
                item_id=str(uuid.uuid4()),
                list_id=str(list_id),
                user_id=user_id,
                tmdb_id=int(tmdb_id) if tmdb_id is not None else None,
                tvdb_id=int(tvdb_id) if tvdb_id is not None else None,
                media_type=media_type,
                title=title,
            )
        except ValueError as err:
            return json.dumps({"error": str(err)})
        return json.dumps({"item": item})

    async def _tool_remove_from_list(self, args: Mapping[str, Any]) -> str:
        denied = self._deny_personal_mutation_if_gated()
        if denied:
            return denied
        list_id, error = self._resolve_curated_list_id(args)
        if error:
            return json.dumps({"error": error})
        user_id = self.user_id if self.settings.features.multi_user_enabled else None
        item_id = str(args.get("item_id") or "").strip() or None
        item = self.db.find_curated_list_item(
            str(list_id),
            user_id=user_id,
            item_id=item_id,
            tmdb_id=int(args["tmdb_id"]) if args.get("tmdb_id") is not None else None,
            tvdb_id=int(args["tvdb_id"]) if args.get("tvdb_id") is not None else None,
            media_type=str(args.get("media_type") or "") or None,
            title=str(args.get("title") or "").strip() or None,
        )
        if item is None:
            return json.dumps({"error": "List item not found"})
        removed = self.db.delete_curated_list_item(str(list_id), str(item["id"]), user_id=user_id)
        return json.dumps({"removed": removed, "item": item})

