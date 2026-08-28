"""Tests for /api/journey/exploration (My Journey refocus)."""

from __future__ import annotations

import unittest

from tests.test_api_contract import ApiContractTests


class JourneyExplorationApiTests(ApiContractTests):
    def test_journey_exploration_shape(self) -> None:
        resp = self.client.get("/api/journey/exploration")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("people", body)
        self.assertIn("directors", body["people"])
        self.assertIn("cinematographers", body["people"])
        self.assertIn("composers", body["people"])
        self.assertIsInstance(body["people"]["directors"], list)
        self.assertIn("insights", body)
        self.assertIsInstance(body["insights"], list)
        self.assertIn("courses", body)
        self.assertIn("explainers", body)
        self.assertNotIn("streak", body)
        self.assertNotIn("badges", body)
        self.assertNotIn("challenges", body)

    def test_journey_exploration_insight_cards(self) -> None:
        resp = self.client.get("/api/journey/exploration")
        self.assertEqual(resp.status_code, 200)
        for card in resp.json().get("insights") or []:
            self.assertIn(card.get("kind"), {"genre", "era"})
            self.assertTrue(str(card.get("label") or "").strip())
            self.assertGreater(int(card.get("count") or 0), 0)
            self.assertTrue(str(card.get("note") or "").strip())


if __name__ == "__main__":
    unittest.main()
