"""Durable media issue queue database coverage."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from curatorx.library.db import Database


class MediaIssueDbTests(unittest.TestCase):
    def test_create_filter_and_log_repair_attempt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            issue = db.create_media_issue(
                issue_id="issue-1",
                reporter_user_id=None,
                rating_key="plex-1",
                tmdb_id=1,
                tvdb_id=None,
                media_type="movie",
                title="Example",
                code="bad_video",
                note="Stops halfway through",
            )
            self.assertEqual(issue["status"], "open")
            updated = db.update_media_issue(
                "issue-1",
                status="approved",
                repair_action="skipped",
                repair_log_entry={"outcome": "skipped", "reason": "Not managed by Radarr."},
            )
            assert updated is not None
            self.assertEqual(updated["repair_log"][0]["outcome"], "skipped")
            self.assertEqual(db.list_media_issues(status="approved")[0]["id"], "issue-1")


if __name__ == "__main__":
    unittest.main()
