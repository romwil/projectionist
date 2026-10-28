"""Watch-activity fields prefer tracker evidence without flattening Plex counts."""

from __future__ import annotations

import inspect
import unittest

from projectionist.library.play_counts import watch_activity_fields


class WatchActivityFieldsTests(unittest.TestCase):
    def test_docstring_does_not_claim_history_is_uningested(self) -> None:
        doc = inspect.getdoc(watch_activity_fields) or ""
        self.assertNotIn("does not currently ingest", doc)
        self.assertIn("plex_played_event_count", doc)
        self.assertIn("sittings_observed", doc)

    def test_no_coverage_keeps_plex_count_and_unknown_sessions(self) -> None:
        fields = watch_activity_fields(
            {"media_type": "movie", "title": "Blade Runner", "view_count": 7}
        )
        self.assertEqual(fields["plex_played_event_count"], 7)
        self.assertEqual(fields["completed_watches"], 7)
        self.assertEqual(fields["rewatch_count"], 6)
        self.assertIsNone(fields["play_sessions"])
        self.assertNotIn("tracked_completions", fields)
        self.assertTrue(all("watched twice" not in str(value).lower() for value in fields.values()))

    def test_tracker_coverage_prefers_sittings_without_flattening(self) -> None:
        fields = watch_activity_fields(
            {
                "media_type": "movie",
                "title": "Heat",
                "view_count": 4,
                "tracker_coverage": "partial",
                "tracked_completions": 2,
                "sittings_observed": 5,
                "completion_confidence": {"certain": 1, "likely": 1, "plex_event_only": 0},
            }
        )
        self.assertEqual(fields["plex_played_event_count"], 4)
        self.assertEqual(fields["completed_watches"], 4)
        self.assertEqual(fields["tracked_completions"], 2)
        self.assertEqual(fields["sittings_observed"], 5)
        self.assertEqual(fields["play_sessions"], 5)
        self.assertNotEqual(fields["play_sessions"], fields["tracked_completions"])
        self.assertTrue(all("watched twice" not in str(value).lower() for value in fields.values()))


if __name__ == "__main__":
    unittest.main()
