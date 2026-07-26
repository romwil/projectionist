"""Entry-point bind/exposure helpers (review finding C2)."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from curatorx.web.__main__ import (
    bind_exposed_without_auth,
    resolve_host,
    warn_if_exposed_without_auth,
)


class ResolveHostTests(unittest.TestCase):
    def test_defaults_to_all_interfaces_for_docker(self) -> None:
        with patch.dict("os.environ", {}, clear=False) as _env:
            for key in ("HOST", "CURATORX_HOST"):
                _env.pop(key, None)
            self.assertEqual(resolve_host(), "0.0.0.0")

    def test_host_env_override(self) -> None:
        with patch.dict("os.environ", {"HOST": "127.0.0.1"}, clear=False):
            self.assertEqual(resolve_host(), "127.0.0.1")

    def test_curatorx_host_override(self) -> None:
        env = {"CURATORX_HOST": "10.0.0.5"}
        with patch.dict("os.environ", env, clear=False) as _env:
            _env.pop("HOST", None)
            self.assertEqual(resolve_host(), "10.0.0.5")


class BindExposureTests(unittest.TestCase):
    def test_all_interfaces_without_auth_is_exposed(self) -> None:
        self.assertTrue(bind_exposed_without_auth("0.0.0.0", multi_user_enabled=False))

    def test_all_interfaces_with_multi_user_is_not_flagged(self) -> None:
        self.assertFalse(bind_exposed_without_auth("0.0.0.0", multi_user_enabled=True))

    def test_loopback_ipv4_not_exposed(self) -> None:
        self.assertFalse(bind_exposed_without_auth("127.0.0.1", multi_user_enabled=False))

    def test_loopback_ipv6_not_exposed(self) -> None:
        self.assertFalse(bind_exposed_without_auth("::1", multi_user_enabled=False))

    def test_localhost_hostname_not_exposed(self) -> None:
        self.assertFalse(bind_exposed_without_auth("localhost", multi_user_enabled=False))

    def test_lan_address_without_auth_is_exposed(self) -> None:
        self.assertTrue(bind_exposed_without_auth("192.168.1.50", multi_user_enabled=False))


class WarnEmissionTests(unittest.TestCase):
    def test_warns_when_exposed(self) -> None:
        with patch("curatorx.web.__main__._multi_user_enabled", return_value=False):
            with self.assertLogs("curatorx.web.__main__", level="WARNING") as cm:
                warn_if_exposed_without_auth("0.0.0.0", 8788)
        self.assertTrue(any("full admin access" in line for line in cm.output))

    def test_silent_when_loopback(self) -> None:
        with patch("curatorx.web.__main__._multi_user_enabled", return_value=False):
            with patch("curatorx.web.__main__.logger") as mock_logger:
                warn_if_exposed_without_auth("127.0.0.1", 8788)
                mock_logger.warning.assert_not_called()

    def test_silent_when_multi_user_enabled(self) -> None:
        with patch("curatorx.web.__main__._multi_user_enabled", return_value=True):
            with patch("curatorx.web.__main__.logger") as mock_logger:
                warn_if_exposed_without_auth("0.0.0.0", 8788)
                mock_logger.warning.assert_not_called()


if __name__ == "__main__":
    unittest.main()
