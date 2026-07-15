"""Tests for HMAC-SHA256 session token creation and verification."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import tempfile
import time
import unittest
from unittest.mock import patch

from curatorx.web.session_tokens import (
    clear_session_secret_cache,
    create_session_token,
    parse_session_token,
)


class SessionTokenTestCase(unittest.TestCase):
    """Base class that provides a temporary DATA_DIR with a valid secret."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ.pop("CURATORX_SESSION_SECRET", None)
        clear_session_secret_cache()

    def tearDown(self) -> None:
        clear_session_secret_cache()
        os.environ.pop("DATA_DIR", None)
        self._tmpdir.cleanup()


class TokenCreationTests(SessionTokenTestCase):
    """Verify create_session_token produces well-formed tokens."""

    def test_token_contains_dot_separator(self) -> None:
        """Token has body.signature format."""
        token = create_session_token("user-1")
        self.assertIn(".", token)
        parts = token.split(".")
        self.assertEqual(len(parts), 2)

    def test_token_payload_contains_uid_and_exp(self) -> None:
        """Decoded payload includes the user ID and an expiry timestamp."""
        token = create_session_token("alice")
        body = token.rsplit(".", 1)[0]
        payload = json.loads(base64.urlsafe_b64decode(body.encode()))
        self.assertEqual(payload["uid"], "alice")
        self.assertIn("exp", payload)
        self.assertGreater(payload["exp"], time.time())

    def test_custom_ttl_sets_correct_expiry(self) -> None:
        """The expiry is approximately now + ttl_seconds."""
        before = time.time()
        token = create_session_token("user-2", ttl_seconds=3600)
        body = token.rsplit(".", 1)[0]
        payload = json.loads(base64.urlsafe_b64decode(body.encode()))
        self.assertAlmostEqual(payload["exp"], before + 3600, delta=5)

    def test_very_long_user_id_succeeds(self) -> None:
        """Handles arbitrarily long user IDs without error."""
        long_id = "x" * 4096
        token = create_session_token(long_id)
        self.assertIsNotNone(token)
        result = parse_session_token(token)
        self.assertEqual(result, long_id)


class TokenVerificationTests(SessionTokenTestCase):
    """Verify parse_session_token accepts/rejects tokens correctly."""

    def test_valid_token_returns_user_id(self) -> None:
        """A freshly created token round-trips through parse."""
        token = create_session_token("bob")
        self.assertEqual(parse_session_token(token), "bob")

    def test_expired_token_is_rejected(self) -> None:
        """A token with TTL=0 is immediately expired."""
        token = create_session_token("expired-user", ttl_seconds=0)
        time.sleep(0.05)
        self.assertIsNone(parse_session_token(token))

    def test_tampered_payload_is_rejected(self) -> None:
        """Modifying the body invalidates the HMAC signature."""
        token = create_session_token("user-3")
        body, sig = token.rsplit(".", 1)
        tampered_payload = {"uid": "attacker", "exp": time.time() + 9999}
        tampered_body = base64.urlsafe_b64encode(
            json.dumps(tampered_payload, separators=(",", ":")).encode()
        ).decode()
        forged = f"{tampered_body}.{sig}"
        self.assertIsNone(parse_session_token(forged))

    def test_wrong_secret_rejects_token(self) -> None:
        """A token signed with one secret cannot be verified with another."""
        token = create_session_token("user-4")
        clear_session_secret_cache()
        os.environ["CURATORX_SESSION_SECRET"] = "completely-different-secret-value"
        self.assertIsNone(parse_session_token(token))

    def test_empty_token_is_rejected(self) -> None:
        """Empty string returns None."""
        self.assertIsNone(parse_session_token(""))

    def test_no_dot_token_is_rejected(self) -> None:
        """A token without a dot separator is invalid."""
        self.assertIsNone(parse_session_token("nodothere"))

    def test_garbage_body_is_rejected(self) -> None:
        """Non-base64 body is rejected gracefully."""
        self.assertIsNone(parse_session_token("!!!invalid!!!.abcdef1234"))


class ConstantTimeComparisonTests(SessionTokenTestCase):
    """Verify the implementation uses timing-safe comparison."""

    def test_uses_hmac_compare_digest(self) -> None:
        """parse_session_token must call hmac.compare_digest for signature check."""
        token = create_session_token("timing-user")
        with patch("curatorx.web.session_tokens.hmac.compare_digest", wraps=hmac.compare_digest) as mock_cmp:
            parse_session_token(token)
            mock_cmp.assert_called_once()


if __name__ == "__main__":
    unittest.main()
