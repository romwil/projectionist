"""Tests for logging configuration."""

import io
import logging
import os
import unittest
from unittest.mock import patch

from curatorx.logging_config import (
    _RedactionFilter,
    configure_logging,
    resolve_log_format,
    resolve_log_level,
    sanitize_log_message,
)


class LoggingConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        configure_logging(force=True)

    def test_configure_logging_initializes_root_handler(self) -> None:
        configure_logging(force=True)
        root = logging.getLogger()
        self.assertTrue(root.handlers)
        self.assertEqual(root.level, logging.INFO)

    def test_resolve_log_level_prefers_curatorx_env(self) -> None:
        with patch.dict(os.environ, {"CURATORX_LOG_LEVEL": "DEBUG", "LOG_LEVEL": "ERROR"}, clear=False):
            self.assertEqual(resolve_log_level(), logging.DEBUG)

    def test_resolve_log_level_falls_back_to_log_level(self) -> None:
        env = os.environ.copy()
        env.pop("CURATORX_LOG_LEVEL", None)
        with patch.dict(os.environ, {**env, "LOG_LEVEL": "WARNING"}, clear=True):
            self.assertEqual(resolve_log_level(), logging.WARNING)

    def test_resolve_log_level_defaults_to_info(self) -> None:
        env = os.environ.copy()
        env.pop("CURATORX_LOG_LEVEL", None)
        env.pop("LOG_LEVEL", None)
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(resolve_log_level(), logging.INFO)

    def test_invalid_level_defaults_to_info(self) -> None:
        self.assertEqual(resolve_log_level("NOT_A_LEVEL"), logging.INFO)

    def test_sanitize_log_message_redacts_secrets(self) -> None:
        raw = "GET https://api.test/movie?api_key=secret123 token=abc Bearer sk-ant-abc123"
        cleaned = sanitize_log_message(raw)
        self.assertNotIn("secret123", cleaned)
        self.assertNotIn("sk-ant-abc123", cleaned)
        self.assertIn("api_key=***", cleaned)

    def test_text_format_emits_to_stdout(self) -> None:
        configure_logging(force=True)
        buffer = io.StringIO()
        handler = logging.StreamHandler(buffer)
        handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
        test_logger = logging.getLogger("curatorx.tests.logging")
        test_logger.handlers.clear()
        test_logger.addHandler(handler)
        test_logger.setLevel(logging.INFO)
        test_logger.propagate = False
        test_logger.info("hello logging")
        self.assertIn("hello logging", buffer.getvalue())

    def test_json_format_option(self) -> None:
        with patch.dict(os.environ, {"LOG_FORMAT": "json"}, clear=False):
            self.assertEqual(resolve_log_format(), "json")

    def test_redaction_filter_redacts_under_text_formatter(self) -> None:
        """The text formatter path must redact secrets, not just JSON."""
        buffer = io.StringIO()
        handler = logging.StreamHandler(buffer)
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        )
        handler.addFilter(_RedactionFilter())
        test_logger = logging.getLogger("curatorx.tests.redaction.text")
        test_logger.handlers.clear()
        test_logger.addHandler(handler)
        test_logger.setLevel(logging.INFO)
        test_logger.propagate = False

        test_logger.info("calling https://api.test/movie?api_key=secret123 key=sk-ant-abc123xyz")

        output = buffer.getvalue()
        self.assertNotIn("secret123", output)
        self.assertNotIn("sk-ant-abc123xyz", output)
        self.assertIn("api_key=***", output)
        self.assertIn("sk-***", output)

    def test_redaction_filter_preserves_percent_args(self) -> None:
        """The filter interpolates %-args once and must not re-apply them."""
        buffer = io.StringIO()
        handler = logging.StreamHandler(buffer)
        handler.setFormatter(logging.Formatter("%(message)s"))
        handler.addFilter(_RedactionFilter())
        test_logger = logging.getLogger("curatorx.tests.redaction.args")
        test_logger.handlers.clear()
        test_logger.addHandler(handler)
        test_logger.setLevel(logging.INFO)
        test_logger.propagate = False

        test_logger.info("fetch %s with token=%s", "https://api.test", "topsecret")

        output = buffer.getvalue()
        self.assertIn("https://api.test", output)
        self.assertIn("token=***", output)
        self.assertNotIn("topsecret", output)


if __name__ == "__main__":
    unittest.main()
