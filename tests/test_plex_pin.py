"""Unit tests for Plex PIN OAuth helpers (mocked plex.tv)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from curatorx.connectors.plex_account import (
    build_plex_auth_url,
    create_plex_pin,
    fetch_plex_pin,
    get_or_create_client_id,
)


class PlexPinHelperTests(unittest.TestCase):
    def test_get_or_create_client_id_persists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = get_or_create_client_id(root)
            second = get_or_create_client_id(root)
            self.assertEqual(first, second)
            self.assertTrue((root / "plex_oauth_client_id").exists())

    def test_build_plex_auth_url(self) -> None:
        url = build_plex_auth_url("cid-1", "CODE12")
        self.assertTrue(url.startswith("https://app.plex.tv/auth/#!?"))
        self.assertIn("clientID=cid-1", url)
        self.assertIn("code=CODE12", url)
        self.assertIn("CuratorX", url)

    def test_create_plex_pin_parses_response(self) -> None:
        payload = {
            "id": 99,
            "code": "ZZZZ",
            "expiresIn": 1800,
            "expiresAt": "2099-01-01T00:00:00Z",
            "authToken": None,
        }
        with patch("curatorx.connectors.plex_account.request_json", return_value=payload) as mocked:
            pin = create_plex_pin("client-abc")
        self.assertEqual(pin["id"], 99)
        self.assertEqual(pin["code"], "ZZZZ")
        self.assertEqual(pin["client_id"], "client-abc")
        self.assertIn("code=ZZZZ", pin["auth_url"])
        mocked.assert_called_once()
        args, kwargs = mocked.call_args
        self.assertEqual(args[0], "https://plex.tv/api/v2/pins?strong=true")
        self.assertEqual(kwargs["method"], "POST")
        self.assertEqual(kwargs["headers"]["X-Plex-Client-Identifier"], "client-abc")
        self.assertEqual(kwargs["headers"]["X-Plex-Product"], "CuratorX")

    def test_fetch_plex_pin(self) -> None:
        payload = {"id": 99, "code": "ZZZZ", "authToken": "tok-1"}
        with patch("curatorx.connectors.plex_account.request_json", return_value=payload) as mocked:
            pin = fetch_plex_pin(99, "client-abc")
        self.assertEqual(pin["authToken"], "tok-1")
        mocked.assert_called_once()
        args, kwargs = mocked.call_args
        self.assertEqual(args[0], "https://plex.tv/api/v2/pins/99")
        self.assertEqual(kwargs["headers"]["X-Plex-Client-Identifier"], "client-abc")


if __name__ == "__main__":
    unittest.main()
