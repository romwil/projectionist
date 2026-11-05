"""HTML shell stamps Live from the native lineup so the icon bar skips the session lookup."""

import importlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from projectionist.live_channels.native_schedule import save_schedule
from projectionist.web.nav_bootstrap import (
    inject_nav_bootstrap,
    live_channels_nav_ready,
    nav_bootstrap_markup,
)


def _settings(*, enabled: bool, url: str, data_dir: Path) -> SimpleNamespace:
    return SimpleNamespace(
        features=SimpleNamespace(live_channels_enabled=enabled),
        tunarr=SimpleNamespace(url=url),
        data_dir=data_dir,
    )


def _save_station(data_dir: Path) -> None:
    save_schedule(
        {
            "channels": {
                "ch-104": {
                    "id": "ch-104",
                    "name": "Late Night",
                    "number": 104,
                    "items": [],
                }
            }
        },
        data_dir=data_dir,
    )


def test_live_ready_with_stations_and_no_tunarr_url(tmp_path: Path):
    _save_station(tmp_path)
    settings = _settings(enabled=True, url="", data_dir=tmp_path)
    assert live_channels_nav_ready(settings) is True
    assert str(settings.tunarr.url).strip() == ""


def test_tunarr_url_is_not_required_and_does_not_make_live_ready(tmp_path: Path):
    empty = _settings(enabled=True, url="http://10.10.1.202:18765", data_dir=tmp_path)
    assert live_channels_nav_ready(empty) is False

    _save_station(tmp_path)
    with_url = _settings(enabled=True, url="http://10.10.1.202:18765", data_dir=tmp_path)
    without_url = _settings(enabled=True, url="  ", data_dir=tmp_path)
    assert live_channels_nav_ready(with_url) is True
    assert live_channels_nav_ready(without_url) is True


def test_live_stays_out_of_nav_when_disabled_or_empty(tmp_path: Path):
    _save_station(tmp_path)
    disabled = _settings(enabled=False, url="", data_dir=tmp_path)
    assert live_channels_nav_ready(disabled) is False

    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    enabled_empty = _settings(enabled=True, url="", data_dir=empty_dir)
    assert live_channels_nav_ready(enabled_empty) is False


class FeaturesLiveReadyTests(unittest.TestCase):
    """The shared /api/features flag is the same rule the nav stamp uses."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["PROJECTIONIST_SKIP_DOTENV"] = "1"
        os.environ["LLM_PROVIDER"] = "ollama"
        import projectionist.web.jobs as jobs

        jobs._manager = None
        import projectionist.web.app as app_mod

        importlib.reload(app_mod)
        self.client = TestClient(app_mod.app)
        root = Path(self._tmpdir.name)
        (root / "settings.json").write_text(
            json.dumps(
                {
                    "features": {"live_channels_enabled": True},
                    "tunarr": {"url": ""},
                    "llm_provider": "ollama",
                }
            ),
            encoding="utf-8",
        )
        _save_station(root)

    def tearDown(self) -> None:
        import projectionist.web.jobs as jobs

        jobs._manager = None
        os.environ.pop("DATA_DIR", None)
        os.environ.pop("PROJECTIONIST_SKIP_DOTENV", None)
        os.environ.pop("LLM_PROVIDER", None)
        self._tmpdir.cleanup()

    def test_features_ready_when_stations_exist_and_tunarr_url_is_empty(self) -> None:
        resp = self.client.get("/api/features")
        self.assertEqual(resp.status_code, 200, resp.text)
        features = resp.json()["features"]
        self.assertTrue(features["live_channels_enabled"])
        self.assertTrue(features["live_channels_ready"])
        saved = json.loads((Path(self._tmpdir.name) / "settings.json").read_text(encoding="utf-8"))
        self.assertEqual(str(saved["tunarr"]["url"]).strip(), "")

    def test_features_not_ready_from_a_tunarr_url_alone(self) -> None:
        root = Path(self._tmpdir.name)
        (root / "live_lineup.json").unlink()
        settings = json.loads((root / "settings.json").read_text(encoding="utf-8"))
        settings["tunarr"]["url"] = "http://tunarr.test:8000"
        (root / "settings.json").write_text(json.dumps(settings), encoding="utf-8")
        resp = self.client.get("/api/features")
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertTrue(resp.json()["features"]["live_channels_enabled"])
        self.assertFalse(resp.json()["features"]["live_channels_ready"])


def test_bootstrap_markup_is_a_boolean_stamp():
    assert nav_bootstrap_markup(True) == (
        '<script>window.__PROJECTIONIST_NAV__={"liveChannelsReady":true}</script>'
    )
    html = inject_nav_bootstrap("<html><head><title>x</title></head><body></body></html>", ready=False)
    assert html.index("liveChannelsReady") < html.index("</head>")
    assert "false" in html
