"""One curator name in member-facing copy (GRO-014)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from projectionist.library.db import Database
from projectionist.notifications.good_news import format_good_news
from projectionist.notifications.newsletters import _persona_voice_line
from projectionist.persona.display import GENERIC_CURATOR_NAME, curator_display_name

PROFESSOR = {"id": "academic-critic", "name": "Academic Critic", "nickname": "The Professor", "is_default": True}


class CuratorDisplayNameTests(unittest.TestCase):
    def test_rule(self) -> None:
        self.assertEqual(curator_display_name("Roger", PROFESSOR), "Roger")
        self.assertEqual(curator_display_name("Curator", PROFESSOR), "The Professor")
        self.assertEqual(curator_display_name("Curator", {"name": "Custom"}), "Custom")
        self.assertEqual(curator_display_name("Curator"), GENERIC_CURATOR_NAME)
        self.assertEqual(curator_display_name(None), GENERIC_CURATOR_NAME)

    def test_good_news_never_says_bare_curator(self) -> None:
        for preset in (None, "classic-curator", "academic-critic", "hype-scout", "steward"):
            for source in ("gap", "watchlist"):
                headline, _ = format_good_news(title="Heat", year=1995, source=source, preset_id=preset)
                self.assertNotIn("Curator", headline, (preset, source, headline))
                self.assertIn("curator", headline.lower())
                self.assertNotIn(" Your curator", headline)

    def test_good_news_keeps_owner_name(self) -> None:
        headline, _ = format_good_news(title="Heat", source="watchlist", curator_name="Ada")
        self.assertIn("Ada", headline)


class NewsletterVoiceTests(unittest.TestCase):
    def test_voice_line_uses_picker_label_not_template_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            voices = db.list_persona_templates()
            default = next((v for v in voices if v.get("is_default")), voices[0])
            line = _persona_voice_line(db)
        expected = default.get("nickname") or default["name"]
        self.assertTrue(line.startswith(expected), line)


if __name__ == "__main__":
    unittest.main()
