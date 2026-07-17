"""Verify that security headers are present on all HTTP responses."""

from __future__ import annotations

import importlib
import os
import tempfile
import unittest

from fastapi.testclient import TestClient


class SecurityHeadersTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["CURATORX_SKIP_DOTENV"] = "1"
        os.environ["LLM_PROVIDER"] = "ollama"
        import curatorx.web.jobs as jobs

        jobs._manager = None
        import curatorx.web.app as app_mod

        importlib.reload(app_mod)
        self.client = TestClient(app_mod.app)

    def tearDown(self) -> None:
        import curatorx.web.jobs as jobs

        jobs._manager = None
        for key in ("CURATORX_SKIP_DOTENV", "LLM_PROVIDER", "DATA_DIR"):
            os.environ.pop(key, None)
        self._tmpdir.cleanup()

    def _get_health_headers(self) -> dict[str, str]:
        resp = self.client.get("/api/health")
        self.assertEqual(resp.status_code, 200)
        return dict(resp.headers)

    def test_x_frame_options_deny(self) -> None:
        headers = self._get_health_headers()
        self.assertEqual(headers.get("x-frame-options"), "DENY")

    def test_x_content_type_options_nosniff(self) -> None:
        headers = self._get_health_headers()
        self.assertEqual(headers.get("x-content-type-options"), "nosniff")

    def test_x_xss_protection_disabled(self) -> None:
        headers = self._get_health_headers()
        self.assertEqual(headers.get("x-xss-protection"), "0")

    def test_content_security_policy_present(self) -> None:
        headers = self._get_health_headers()
        csp = headers.get("content-security-policy", "")
        self.assertIn("default-src 'self'", csp)
        self.assertIn("frame-ancestors 'none'", csp)
        self.assertIn("img-src", csp)
        self.assertIn("image.tmdb.org", csp)

    def test_content_security_policy_allows_youtube_trailer_frames(self) -> None:
        headers = self._get_health_headers()
        csp = headers.get("content-security-policy", "")
        self.assertIn(
            "frame-src https://www.youtube.com https://www.youtube-nocookie.com",
            csp,
        )

    def test_referrer_policy(self) -> None:
        headers = self._get_health_headers()
        self.assertEqual(
            headers.get("referrer-policy"),
            "strict-origin-when-cross-origin",
        )

    def test_permissions_policy(self) -> None:
        headers = self._get_health_headers()
        policy = headers.get("permissions-policy", "")
        self.assertIn("camera=()", policy)
        self.assertIn("microphone=(self)", policy)
        self.assertIn("geolocation=()", policy)

    def test_headers_on_api_endpoint(self) -> None:
        resp = self.client.get("/api/features")
        self.assertEqual(resp.status_code, 200)
        headers = dict(resp.headers)
        self.assertEqual(headers.get("x-frame-options"), "DENY")
        self.assertEqual(headers.get("x-content-type-options"), "nosniff")
        self.assertIn("content-security-policy", headers)

    def test_headers_on_error_response(self) -> None:
        resp = self.client.get("/api/jobs/nonexistent-id")
        self.assertEqual(resp.status_code, 404)
        headers = dict(resp.headers)
        self.assertEqual(headers.get("x-frame-options"), "DENY")
        self.assertEqual(headers.get("x-content-type-options"), "nosniff")

    def test_all_required_headers_present(self) -> None:
        expected = {
            "x-frame-options",
            "x-content-type-options",
            "x-xss-protection",
            "content-security-policy",
            "referrer-policy",
            "permissions-policy",
        }
        headers = self._get_health_headers()
        missing = expected - set(headers.keys())
        self.assertFalse(missing, f"Missing security headers: {missing}")


if __name__ == "__main__":
    unittest.main()
