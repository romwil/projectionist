"""Tests for Plex token encryption/decryption (curatorx/watchlist/crypto.py)."""

from __future__ import annotations

import base64
import hmac
import importlib.util
import os
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from curatorx.web.session_tokens import clear_session_secret_cache

# Load crypto module directly to avoid triggering watchlist/__init__.py
# which pulls in numpy via the library.embeddings import chain.
_spec = importlib.util.spec_from_file_location(
    "curatorx.watchlist.crypto",
    Path(__file__).resolve().parent.parent / "curatorx" / "watchlist" / "crypto.py",
)
_crypto_mod = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("curatorx.watchlist.crypto", _crypto_mod)
_spec.loader.exec_module(_crypto_mod)

decrypt_plex_token = _crypto_mod.decrypt_plex_token
encrypt_plex_token = _crypto_mod.encrypt_plex_token


class CryptoTestCase(unittest.TestCase):
    """Base class that provides a stable session secret for crypto ops."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["CURATORX_SESSION_SECRET"] = "test-crypto-secret-strong-enough"
        clear_session_secret_cache()

    def tearDown(self) -> None:
        clear_session_secret_cache()
        os.environ.pop("DATA_DIR", None)
        os.environ.pop("CURATORX_SESSION_SECRET", None)
        self._tmpdir.cleanup()


class EncryptDecryptRoundTripTests(CryptoTestCase):
    """Verify encrypt/decrypt round-trips preserve the plaintext."""

    def test_basic_round_trip(self) -> None:
        """Encrypting then decrypting returns the original token."""
        original = "abc123PlexToken"
        encrypted = encrypt_plex_token(original)
        self.assertNotEqual(encrypted, original)
        self.assertEqual(decrypt_plex_token(encrypted), original)

    def test_unicode_token_round_trip(self) -> None:
        """UTF-8 characters survive the encrypt/decrypt cycle."""
        original = "plex-tökén-日本語"
        encrypted = encrypt_plex_token(original)
        self.assertEqual(decrypt_plex_token(encrypted), original)

    def test_long_token_round_trip(self) -> None:
        """Long tokens are handled correctly."""
        original = "A" * 2048
        encrypted = encrypt_plex_token(original)
        self.assertEqual(decrypt_plex_token(encrypted), original)

    def test_each_encryption_produces_different_ciphertext(self) -> None:
        """Random nonce ensures non-deterministic output."""
        token = "same-token"
        enc1 = encrypt_plex_token(token)
        enc2 = encrypt_plex_token(token)
        self.assertNotEqual(enc1, enc2)


class DecryptionFailureTests(CryptoTestCase):
    """Verify decryption rejects invalid inputs."""

    def test_wrong_key_rejects_ciphertext(self) -> None:
        """A token encrypted with one key cannot be decrypted with another."""
        encrypted = encrypt_plex_token("my-secret-token")
        clear_session_secret_cache()
        os.environ["CURATORX_SESSION_SECRET"] = "a-completely-different-secret-key"
        self.assertIsNone(decrypt_plex_token(encrypted))

    def test_tampered_ciphertext_is_rejected(self) -> None:
        """Flipping bits in the ciphertext causes MAC verification to fail."""
        encrypted = encrypt_plex_token("token-to-tamper")
        raw = bytearray(base64.urlsafe_b64decode(encrypted.encode("ascii")))
        raw[-1] ^= 0xFF
        tampered = base64.urlsafe_b64encode(bytes(raw)).decode("ascii")
        self.assertIsNone(decrypt_plex_token(tampered))

    def test_tampered_mac_is_rejected(self) -> None:
        """Corrupting the MAC bytes causes verification failure."""
        encrypted = encrypt_plex_token("token-mac-tamper")
        raw = bytearray(base64.urlsafe_b64decode(encrypted.encode("ascii")))
        mac_offset = len(b"v1") + 16
        raw[mac_offset] ^= 0xFF
        tampered = base64.urlsafe_b64encode(bytes(raw)).decode("ascii")
        self.assertIsNone(decrypt_plex_token(tampered))

    def test_empty_input_returns_none(self) -> None:
        """Empty string returns None without raising."""
        self.assertIsNone(decrypt_plex_token(""))

    def test_none_input_returns_none(self) -> None:
        """None input returns None without raising."""
        self.assertIsNone(decrypt_plex_token(None))

    def test_garbage_base64_returns_none(self) -> None:
        """Invalid base64 returns None."""
        self.assertIsNone(decrypt_plex_token("!!!not-base64!!!"))

    def test_truncated_blob_returns_none(self) -> None:
        """A blob shorter than version+nonce+mac is rejected."""
        short = base64.urlsafe_b64encode(b"v1" + b"\x00" * 10).decode()
        self.assertIsNone(decrypt_plex_token(short))


class MACVerificationTests(CryptoTestCase):
    """Verify that MAC comparison uses timing-safe functions."""

    def test_uses_hmac_compare_digest(self) -> None:
        """decrypt_plex_token calls hmac.compare_digest for MAC check."""
        encrypted = encrypt_plex_token("timing-safe-token")
        with patch.object(_crypto_mod.hmac, "compare_digest", wraps=hmac.compare_digest) as mock_cmp:
            decrypt_plex_token(encrypted)
            mock_cmp.assert_called_once()


class EmptyPlaintextTests(CryptoTestCase):
    """Verify handling of empty/whitespace-only plaintext."""

    def test_empty_plaintext_raises_value_error(self) -> None:
        """encrypt_plex_token rejects empty string."""
        with self.assertRaises(ValueError):
            encrypt_plex_token("")

    def test_whitespace_only_raises_value_error(self) -> None:
        """encrypt_plex_token rejects whitespace-only input."""
        with self.assertRaises(ValueError):
            encrypt_plex_token("   ")

    def test_none_plaintext_raises_value_error(self) -> None:
        """encrypt_plex_token rejects None input."""
        with self.assertRaises(ValueError):
            encrypt_plex_token(None)


if __name__ == "__main__":
    unittest.main()
