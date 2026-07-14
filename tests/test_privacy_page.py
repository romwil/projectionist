"""SPA fallback for the public privacy disclosure page."""

from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from curatorx.web.app import app


class PrivacyPageTests(unittest.TestCase):
    def test_privacy_route_serves_html_without_auth(self) -> None:
        client = TestClient(app)
        response = client.get("/privacy")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers.get("content-type", ""))


if __name__ == "__main__":
    unittest.main()
