"""Tests for recommendation response cards."""

import unittest

from curatorx.agent.curator import _cards_for_response
from curatorx.models.schemas import TitleCard


class RecommendationCardTests(unittest.TestCase):
    def test_response_cards_deduplicate_stable_identity(self) -> None:
        class Registry:
            recommendation_context = False
            cards = [
                TitleCard(title="Stalker", year=1979, media_type="movie", tmdb_id=1398),
                TitleCard(
                    title="Stalker",
                    year=1979,
                    media_type="movie",
                    tmdb_id=1398,
                    recommendation_reason="A contemplative sci-fi landmark.",
                ),
                TitleCard(title="Akira", year=1988, media_type="movie", tmdb_id=149),
            ]

        cards = _cards_for_response(Registry())
        self.assertEqual([card.title for card in cards], ["Stalker", "Akira"])
        self.assertEqual(cards[0].recommendation_reason, "A contemplative sci-fi landmark.")

