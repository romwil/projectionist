"""Tests for library sync progress labels and weighted percents."""

from __future__ import annotations

import unittest

from curatorx.web.job_progress import (
    format_count_message,
    format_job_progress,
    friendly_job_error,
    friendly_progress_message,
    phase_label,
    weighted_sync_percent,
)
from curatorx.web.jobs import JobProgress


class JobProgressFormattingTests(unittest.TestCase):
    def test_friendly_progress_message_maps_snake_case(self) -> None:
        self.assertEqual(friendly_progress_message("scanning_plex"), "Scanning Plex library…")
        self.assertEqual(friendly_progress_message("", "enriching"), "Enriching metadata…")
        self.assertEqual(friendly_progress_message("movies"), "Scanning Plex movies…")

    def test_friendly_progress_keeps_count_copy(self) -> None:
        message = "Scanning movies… 120 of ~500"
        self.assertEqual(friendly_progress_message(message, "movies"), message)

    def test_phase_labels_are_novice_friendly(self) -> None:
        self.assertEqual(phase_label("preparing"), "Preparing")
        self.assertEqual(phase_label("movies"), "Scanning movies")
        self.assertEqual(phase_label("tv"), "Scanning TV")
        self.assertEqual(phase_label("enriching"), "Enriching metadata")
        self.assertEqual(phase_label("finishing"), "Finishing")

    def test_weighted_percent_finishing_advances_with_counts(self) -> None:
        start = weighted_sync_percent("finishing", 0, 100)
        mid = weighted_sync_percent("finishing", 50, 100)
        end = weighted_sync_percent("finishing", 100, 100)
        self.assertEqual(start, 90)
        self.assertGreater(mid, start)
        self.assertLess(end, 100)
        self.assertGreater(end, mid)

    def test_weighted_percent_increases_across_phases(self) -> None:
        movies_end = weighted_sync_percent("movies", 1, 1)
        tv_start = weighted_sync_percent("tv", 0, 1)
        tv_end = weighted_sync_percent("tv", 1, 1)
        enrich_mid = weighted_sync_percent("enriching", 50, 100)
        self.assertLessEqual(movies_end, tv_start + 1)
        self.assertLess(tv_start, tv_end)
        self.assertGreater(enrich_mid, tv_end)

    def test_format_count_message(self) -> None:
        self.assertEqual(
            format_count_message("Scanning movies", 120, 500, unit="movies"),
            "Scanning movies… 120 of ~500",
        )
        self.assertEqual(
            format_count_message("Scanning movies", 500, 500, unit="movies", done=True),
            "Found 500 movies",
        )
        self.assertEqual(
            format_count_message("Enriching metadata", 40, None, unit="titles"),
            "Found 40 titles so far",
        )

    def test_format_job_progress_tuple(self) -> None:
        percent, message, label = format_job_progress("tv", 100, 100, "scanning_plex")
        self.assertLess(percent, 100)
        self.assertEqual(message, "Scanning Plex library…")
        self.assertEqual(label, "Scanning TV")

    def test_job_progress_to_dict_is_friendly(self) -> None:
        payload = JobProgress(phase="tv", current=200, total=200, message="scanning_plex").to_dict()
        self.assertLess(payload["percent"], 100)
        self.assertEqual(payload["message"], "Scanning Plex library…")
        self.assertEqual(payload["label"], "Scanning TV")
        self.assertNotIn("_", payload["message"])

    def test_friendly_job_error_strips_traceback(self) -> None:
        err = friendly_job_error("Plex is not configured\nTraceback (most recent call last):\n  File")
        self.assertEqual(err, "Plex is not configured")
        self.assertNotIn("Traceback", friendly_job_error("Traceback (most recent call last):\n boom"))


if __name__ == "__main__":
    unittest.main()
