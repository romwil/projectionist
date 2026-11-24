"""EXP-018: versioned warm-up lines and the session step that picks them."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from projectionist.engine.profiles import APPLE_TV_4K, CHROME
from projectionist.engine.routes import describe_title
from projectionist.engine.session import open_engine_session, reset_engine_sessions
from projectionist.engine.warmup import STEPS, load_warmup_lines, set_step
from tests.test_engine_session import _asset


class WarmupLineTests(unittest.TestCase):
    def test_lines_are_versioned_and_cover_every_step(self) -> None:
        document = load_warmup_lines()
        self.assertGreaterEqual(document["version"], 1)
        self.assertGreaterEqual(len(document["general"]), 8)
        self.assertEqual(set(document["steps"]), set(STEPS))
        for name in STEPS:
            self.assertGreaterEqual(len(document["steps"][name]), 2)
            for line in document["steps"][name]:
                self.assertNotIn("fuck", line.lower())

    def test_an_unknown_step_is_rejected(self) -> None:
        class _Session:
            step = ""

        with self.assertRaises(ValueError):
            set_step(_Session(), "joke")

    def test_locate_names_the_disk_and_the_probe(self) -> None:
        class _Source:
            def locate(self, rating_key, **kwargs):
                del rating_key, kwargs
                return "asset"

        seen: list[str] = []
        asset = describe_title(
            None,
            None,
            Path("."),
            "1",
            source=_Source(),
            on_step=seen.append,
        )
        self.assertEqual(asset, "asset")
        self.assertEqual(seen, ["waking_disk", "probing"])

    def test_a_preparing_remux_and_an_audio_encode_name_their_steps(self) -> None:
        reset_engine_sessions()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                media = Path(tmp) / "film.mkv"
                media.write_bytes(b"mkv")

                def runner(cmd, cwd):
                    del cmd
                    Path(cwd).mkdir(parents=True, exist_ok=True)

                remux = _asset()
                remux.local_path = str(media)
                session = open_engine_session(
                    remux,
                    APPLE_TV_4K,
                    user_id="owner",
                    title="3 Ninjas",
                    duration_ms=600_000,
                    view_offset_ms=0,
                    data_dir=Path(tmp),
                    runner=runner,
                    ffmpeg="ffmpeg",
                )
                self.assertEqual(session.public()["state"], "preparing")
                self.assertEqual(session.public()["step"], "remuxing")

                audio = _asset("ac3")
                audio.local_path = str(media)
                encoded = open_engine_session(
                    audio,
                    CHROME,
                    user_id="owner",
                    title="3 Ninjas",
                    duration_ms=600_000,
                    view_offset_ms=0,
                    data_dir=Path(tmp),
                    runner=runner,
                    ffmpeg="ffmpeg",
                )
                self.assertEqual(encoded.plan, "audio")
                self.assertEqual(encoded.public()["step"], "encoding_audio")
        finally:
            reset_engine_sessions()
