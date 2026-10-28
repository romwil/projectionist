"""Thin ToolRegistry: execute dispatch + youth/card state."""

from __future__ import annotations

from projectionist.agent.tools._helpers import *  # noqa: F401, F403
from projectionist.agent.tools.library import LibraryToolsMixin
from projectionist.agent.tools.research import ResearchToolsMixin
from projectionist.agent.tools.memory import MemoryToolsMixin
from projectionist.agent.tools.acquire import AcquireToolsMixin
from projectionist.agent.tools.plex import PlexToolsMixin
from projectionist.agent.tools.reviews import ReviewsToolsMixin
from projectionist.agent.tools.watchlist import WatchlistToolsMixin
from projectionist.agent.tools.lists import ListsToolsMixin
from projectionist.agent.tools.tonight import TonightToolsMixin

class ToolRegistry(
    LibraryToolsMixin,
    ResearchToolsMixin,
    MemoryToolsMixin,
    AcquireToolsMixin,
    PlexToolsMixin,
    ReviewsToolsMixin,
    WatchlistToolsMixin,
    ListsToolsMixin,
    TonightToolsMixin,
):
    def __init__(
        self,
        db: Database,
        settings: Settings,
        lens_id: str,
        *,
        user_id: Optional[str] = None,
        seerr_user_id: Optional[int] = None,
        user_role: Optional[str] = None,
        is_youth: bool = False,
        persona_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> None:
        self.db = db
        self.settings = settings
        self.lens_id = lens_id
        self.user_id = user_id
        self.seerr_user_id = seerr_user_id
        self.user_role = user_role
        self.is_youth = bool(is_youth)
        self.persona_id = persona_id
        self.session_id = session_id
        self._cards: List[TitleCard] = []
        self._discussed_cards: List[TitleCard] = []
        self._pending_token_entries: List[Dict[str, str]] = []
        self._recommendation_context = False
        self._cleared_discussed_for_targeted_search = False
        self._suggested_replies: List[str] = []
        self._review_conflicts: List[Dict[str, Any]] = []
        self._review_prompts: List[Dict[str, Any]] = []
        # Titles stripped from Youth tool JSON this turn — for post-generation scrub.
        self._youth_blocked_titles: set[str] = set()
        # Year-slice audit label set by query/summarize tools this turn (sticky clear).
        self._turn_audit_label: Optional[str] = None
        # Curator village: at most one sibling consult per user turn.
        self._consult_used = False
        self._persona_consults: List[Dict[str, Any]] = []

    def _deny_personal_mutation_if_gated(self) -> Optional[str]:
        """H5: under multi-user, block personal writes unless the household opts in.

        Single-owner (multi-user off) keeps immediate writes. *arr / Seerr /
        collections stay on the confirm-token path regardless.
        """
        if not self.settings.features.multi_user_enabled:
            return None
        if self.settings.features.agent_may_mutate_personal_data:
            return None
        return json.dumps(
            {
                "error": (
                    "Personal data writes via chat are disabled while multi-user is on. "
                    "An owner can enable “Agent may mutate personal data” in Settings → "
                    "Household, or make the change in the UI."
                ),
                "code": "agent_personal_mutation_gated",
            }
        )

    def _apply_youth_filters(self, filters: LibraryFilters) -> LibraryFilters:
        if not self.is_youth:
            return filters
        from projectionist.youth.apply import apply_youth_gate_to_filters

        class _YouthUser:
            is_youth = True

        return apply_youth_gate_to_filters(filters, user=_YouthUser(), settings=self.settings)

    def _note_youth_blocked_title(self, title: Any) -> None:
        if not self.is_youth:
            return
        text = str(title or "").strip()
        if text:
            self._youth_blocked_titles.add(text)

    def _card_allowed(self, card: TitleCard) -> bool:
        if not self.is_youth:
            return True
        from projectionist.youth.rating_gate import content_rating_allowed, resolve_youth_max_rating

        return content_rating_allowed(
            getattr(card, "content_rating", "") or "",
            max_rating=resolve_youth_max_rating(self.settings),
        )

    def _allowed_cards(self, cards: Sequence[TitleCard]) -> List[TitleCard]:
        """Youth-safe subset of ``cards`` — also used to build tool JSON items.

        Tool payloads must be filtered too, not just the rendered cards: an
        over-ceiling title left in the JSON is a title the model can name in prose.
        """
        if not self.is_youth:
            return list(cards)
        allowed: List[TitleCard] = []
        for card in cards:
            if self._card_allowed(card):
                allowed.append(card)
            else:
                self._note_youth_blocked_title(getattr(card, "title", ""))
        return allowed

    def _youth_filter_tool_items(
        self,
        items: Sequence[Mapping[str, Any]],
        *,
        cards: Optional[Sequence[TitleCard]] = None,
    ) -> List[Dict[str, Any]]:
        """Fail-closed Youth filter for external discovery tool JSON items.

        Prefers ``content_rating`` on the item when present; otherwise matches
        ``tmdb_id`` against allowed cards. Unrated / unmatched titles are omitted
        and recorded for the post-generation scrub.
        """
        if not self.is_youth:
            return [dict(item) for item in items if isinstance(item, Mapping)]

        from projectionist.youth.rating_gate import content_rating_allowed, resolve_youth_max_rating

        max_rating = resolve_youth_max_rating(self.settings)
        allowed_ids: set[int] = set()
        if cards is not None:
            for card in self._allowed_cards(cards):
                if card.tmdb_id:
                    allowed_ids.add(int(card.tmdb_id))

        kept: List[Dict[str, Any]] = []
        for item in items:
            if not isinstance(item, Mapping):
                continue
            rating = item.get("content_rating")
            if rating is not None and str(rating).strip() != "":
                if content_rating_allowed(rating, max_rating=max_rating):
                    kept.append(dict(item))
                else:
                    self._note_youth_blocked_title(item.get("title"))
                continue
            tmdb_id = int(item.get("tmdb_id") or 0)
            if tmdb_id and tmdb_id in allowed_ids:
                kept.append(dict(item))
            else:
                # Unrated / no matching allowed card → fail closed.
                self._note_youth_blocked_title(item.get("title"))
        return kept

    def _offer_card(self, card: TitleCard) -> None:
        if self._card_allowed(card):
            self._cards.append(card)
        else:
            self._note_youth_blocked_title(getattr(card, "title", ""))

    def _register_pending_token(self, token: str, action: str) -> None:
        self._pending_token_entries.append({"token": token, "action": action})

    @property
    def cards(self) -> List[TitleCard]:
        return self._cards

    @property
    def youth_blocked_titles(self) -> List[str]:
        return sorted(self._youth_blocked_titles)

    @property
    def recommendation_context(self) -> bool:
        return self._recommendation_context

    @property
    def discussed_cards(self) -> List[TitleCard]:
        return self._discussed_cards

    @property
    def suggested_replies(self) -> List[str]:
        return self._suggested_replies

    @property
    def pending_tokens(self) -> List[Dict[str, str]]:
        return self._pending_token_entries

    @property
    def review_conflicts(self) -> List[Dict[str, Any]]:
        return self._review_conflicts

    @property
    def review_prompts(self) -> List[Dict[str, Any]]:
        return self._review_prompts

    @property
    def turn_audit_label(self) -> Optional[str]:
        return self._turn_audit_label

    @property
    def persona_consults(self) -> List[Dict[str, Any]]:
        return self._persona_consults

    def note_turn_audit_label(self, label: Optional[str]) -> None:
        cleaned = str(label or "").strip()
        if cleaned:
            self._turn_audit_label = cleaned

    async def execute(self, name: str, arguments: Mapping[str, Any]) -> str:
        handler: Optional[Callable] = getattr(self, f"_tool_{name}", None)
        if handler is None:
            logger.warning("Unknown agent tool requested: %s", name)
            return json.dumps({"error": f"Unknown tool {name}"})
        logger.debug("Executing tool %s", name)
        try:
            result = await handler(arguments)
            if not self.user_id:
                return result
            try:
                parsed = json.loads(result)
            except (TypeError, json.JSONDecodeError):
                return result
            from projectionist.watch_tracker.store import attach_user_watch_summaries

            adopted = attach_user_watch_summaries(
                self.db,
                parsed,
                user_id=self.user_id,
            )
            return json.dumps(adopted)
        except Exception:
            logger.exception("Tool %s failed", name)
            raise

