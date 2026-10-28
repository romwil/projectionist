"""Plex collection agent tools."""

from __future__ import annotations

from projectionist.agent.tools._helpers import *  # noqa: F401, F403

class PlexToolsMixin:
    def _plex_section_for_media_type(self, media_type: str) -> Optional[str]:
        normalized = str(media_type or "").strip().lower()
        if normalized == "movie":
            section = str(self.settings.plex_movie_section or "").strip()
        elif normalized == "show":
            section = str(self.settings.plex_tv_section or "").strip()
        else:
            return None
        return section or None

    def _plex_configuration_error(self) -> Optional[str]:
        if not self.settings.plex_url or not self.settings.plex_token:
            return "Plex is not configured. Add Plex URL and token in Configuration."
        return None

    async def _tool_list_plex_collections(self, args: Mapping[str, Any]) -> str:
        from projectionist.connectors.plex import PlexClient
        from projectionist.connectors.plex_collections import list_collections

        config_error = plex_collections_configuration_error(self.settings)
        if config_error:
            return json.dumps({"error": config_error})
        media_type = str(args.get("media_type") or "movie")
        section_id = self._plex_section_for_media_type(media_type)
        if not section_id:
            return json.dumps(
                {
                    "error": (
                        f"Plex {media_type} library section is not configured. "
                        "Open Configuration → Plex library mapping."
                    )
                }
            )
        client = PlexClient(self.settings.plex_url, self.settings.plex_token)
        items = list_collections(client, section_id)
        return json.dumps(
            {
                "items": [
                    {
                        "rating_key": item.rating_key,
                        "title": item.title,
                        "section_id": item.section_id,
                        "media_type": item.media_type,
                    }
                    for item in items
                ],
                "count": len(items),
            }
        )

    async def _tool_create_plex_collection(self, args: Mapping[str, Any]) -> str:
        config_error = plex_collections_configuration_error(self.settings)
        if config_error:
            return json.dumps({"error": config_error})
        media_type = str(args.get("media_type") or "movie")
        section_id = self._plex_section_for_media_type(media_type)
        if not section_id:
            return json.dumps(
                {
                    "error": (
                        f"Plex {media_type} library section is not configured. "
                        "Open Configuration → Plex library mapping."
                    )
                }
            )
        title = str(args.get("title") or "").strip()
        if not title:
            return json.dumps({"error": "title is required"})
        rating_keys = [str(key).strip() for key in (args.get("rating_keys") or []) if str(key).strip()]
        token = uuid.uuid4().hex
        payload = {
            "action": "create_plex_collection",
            "title": title,
            "media_type": media_type,
            "section_id": section_id,
            "rating_keys": rating_keys,
        }
        self.db.save_pending_action(token, "create_plex_collection", payload, user_id=self.user_id)
        self._register_pending_token(token, "create_plex_collection")
        return json.dumps(
            {
                "confirmation_token": token,
                "scope": "plex_only",
                "message": (
                    f"Awaiting user confirmation to create Plex collection '{title}' "
                    "(Plex only — this will NOT create a Projectionist collection or course; "
                    "use create_list for that). "
                    f"{_PENDING_CONFIRM_HINT}"
                ),
            }
        )

    async def _tool_add_to_plex_collection(self, args: Mapping[str, Any]) -> str:
        config_error = plex_collections_configuration_error(self.settings)
        if config_error:
            return json.dumps({"error": config_error})
        media_type = str(args.get("media_type") or "movie")
        section_id = self._plex_section_for_media_type(media_type)
        if not section_id:
            return json.dumps(
                {
                    "error": (
                        f"Plex {media_type} library section is not configured. "
                        "Open Configuration → Plex library mapping."
                    )
                }
            )
        rating_keys = [str(key).strip() for key in (args.get("rating_keys") or []) if str(key).strip()]
        if not rating_keys:
            return json.dumps({"error": "rating_keys is required"})
        collection_rating_key = str(args.get("collection_rating_key") or "").strip()
        collection_title = str(args.get("collection_title") or "").strip()
        if not collection_rating_key and not collection_title:
            return json.dumps({"error": "collection_rating_key or collection_title is required"})
        token = uuid.uuid4().hex
        payload = {
            "action": "add_to_plex_collection",
            "media_type": media_type,
            "section_id": section_id,
            "rating_keys": rating_keys,
            "collection_rating_key": collection_rating_key,
            "collection_title": collection_title,
        }
        self.db.save_pending_action(token, "add_to_plex_collection", payload, user_id=self.user_id)
        self._register_pending_token(token, "add_to_plex_collection")
        label = collection_title or collection_rating_key
        return json.dumps(
            {
                "confirmation_token": token,
                "message": (
                    f"Awaiting user confirmation to add items to Plex collection '{label}'. "
                    f"{_PENDING_CONFIRM_HINT}"
                ),
            }
        )

