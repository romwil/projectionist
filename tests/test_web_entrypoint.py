"""Entry-point bind/exposure helpers (review finding C2)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from projectionist.web.__main__ import (
    UVICORN_H11_MAX_INCOMPLETE_EVENT_SIZE,
    UVICORN_TIMEOUT_KEEP_ALIVE,
    bind_exposed_without_auth,
    main,
    resolve_host,
    warn_if_exposed_without_auth,
)


class ResolveHostTests(unittest.TestCase):
    def test_defaults_to_all_interfaces_for_docker(self) -> None:
        with patch.dict("os.environ", {}, clear=False) as env:
            for key in ("HOST", "PROJECTIONIST_HOST"):
                env.pop(key, None)
            self.assertEqual(resolve_host(), "0.0.0.0")

    def test_host_env_override(self) -> None:
        with patch.dict("os.environ", {"HOST": "127.0.0.1"}, clear=False):
            self.assertEqual(resolve_host(), "127.0.0.1")

    def test_projectionist_host_override(self) -> None:
        with patch.dict("os.environ", {"PROJECTIONIST_HOST": "10.0.0.5"}, clear=False) as patched:
            patched.pop("HOST", None)
            self.assertEqual(resolve_host(), "10.0.0.5")

    def test_ignores_legacy_curatorx_host(self) -> None:
        with patch.dict("os.environ", {"CURATORX_HOST": "10.0.0.6"}, clear=False) as patched:
            patched.pop("HOST", None)
            patched.pop("PROJECTIONIST_HOST", None)
            self.assertEqual(resolve_host(), "0.0.0.0")


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
        with patch("projectionist.web.__main__._multi_user_enabled", return_value=False):
            with self.assertLogs("projectionist.web.__main__", level="WARNING") as cm:
                warn_if_exposed_without_auth("0.0.0.0", 8788)
        self.assertTrue(any("full admin access" in line for line in cm.output))

    def test_silent_when_loopback(self) -> None:
        with patch("projectionist.web.__main__._multi_user_enabled", return_value=False):
            with patch("projectionist.web.__main__.logger") as mock_logger:
                warn_if_exposed_without_auth("127.0.0.1", 8788)
                mock_logger.warning.assert_not_called()

    def test_silent_when_multi_user_enabled(self) -> None:
        with patch("projectionist.web.__main__._multi_user_enabled", return_value=True):
            with patch("projectionist.web.__main__.logger") as mock_logger:
                warn_if_exposed_without_auth("0.0.0.0", 8788)
                mock_logger.warning.assert_not_called()


class UvicornTimeoutTests(unittest.TestCase):
    def test_main_sets_keep_alive_and_incomplete_event_limits(self) -> None:
        with patch.dict("os.environ", {"PROJECTIONIST_THEATER_DISABLE": "1"}, clear=False):
            with patch("uvicorn.run") as run:
                main()
        kwargs = run.call_args.kwargs
        self.assertEqual(kwargs["timeout_keep_alive"], UVICORN_TIMEOUT_KEEP_ALIVE)
        self.assertEqual(
            kwargs["h11_max_incomplete_event_size"],
            UVICORN_H11_MAX_INCOMPLETE_EVENT_SIZE,
        )
        self.assertEqual(UVICORN_TIMEOUT_KEEP_ALIVE, 5)
        self.assertEqual(UVICORN_H11_MAX_INCOMPLETE_EVENT_SIZE, 16 * 1024)

    def test_resolve_theater_port_default(self) -> None:
        from projectionist.web.__main__ import resolve_theater_port

        with patch.dict("os.environ", {}, clear=False) as env:
            env.pop("PROJECTIONIST_THEATER_PORT", None)
            self.assertEqual(resolve_theater_port(), 8791)


class LobbyOptInTests(unittest.TestCase):
    """PRD-013: the unauthenticated theater port opens only after the owner opts in."""

    def _main_with_settings(self, payload: str | None, env: dict[str, str] | None = None):
        with tempfile.TemporaryDirectory() as tmp:
            if payload is not None:
                (Path(tmp) / "settings.json").write_text(payload, encoding="utf-8")
            environ = {"DATA_DIR": tmp, "PROJECTIONIST_SKIP_DOTENV": "1", **(env or {})}
            with patch.dict("os.environ", environ, clear=False) as live:
                if not env or "PROJECTIONIST_THEATER_DISABLE" not in env:
                    live.pop("PROJECTIONIST_THEATER_DISABLE", None)
                live.pop("PORT", None)
                live.pop("PROJECTIONIST_THEATER_PORT", None)
                with (
                    patch("uvicorn.run") as run,
                    patch(
                        "projectionist.web.__main__._serve_dual", new=MagicMock(return_value=None)
                    ) as dual,
                    patch("asyncio.run") as arun,
                ):
                    main()
            return run, dual, arun

    def test_fresh_install_serves_only_the_main_port(self) -> None:
        run, dual, arun = self._main_with_settings(None)
        run.assert_called_once()
        self.assertEqual(run.call_args.kwargs["port"], 8788)
        dual.assert_not_called()
        arun.assert_not_called()

    def test_saved_lobby_settings_left_off_stay_off(self) -> None:
        run, _dual, arun = self._main_with_settings(
            '{"theater": {"enabled": false, "orientation": "portrait"}}'
        )
        run.assert_called_once()
        arun.assert_not_called()

    def test_owner_who_turned_lobby_on_keeps_the_theater(self) -> None:
        run, dual, arun = self._main_with_settings('{"theater": {"enabled": true}}')
        run.assert_not_called()
        arun.assert_called_once()
        self.assertEqual(dual.call_args.kwargs["theater_port"], 8791)

    def test_disable_env_wins_over_the_setting(self) -> None:
        run, _dual, arun = self._main_with_settings(
            '{"theater": {"enabled": true}}', env={"PROJECTIONIST_THEATER_DISABLE": "1"}
        )
        run.assert_called_once()
        arun.assert_not_called()


if __name__ == "__main__":
    unittest.main()
