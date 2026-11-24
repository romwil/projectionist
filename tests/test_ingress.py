"""Ingress handshake: Docker NAT is not LAN; snapshots never store secrets."""

from __future__ import annotations

import ipaddress
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from projectionist.library.db import Database
from projectionist.web.ingress import (
    build_detection_snapshot,
    sanitize_detection_snapshot,
    setup_posture,
    snapshot_contains_secrets,
    wan_interlock_blocks,
)
from projectionist.web.setup_mode import load_detection_snapshot, persist_detection_snapshot


class SetupPostureTests(unittest.TestCase):
    def test_docker_bridge_all_interfaces_is_public_failsafe(self) -> None:
        peer = ipaddress.ip_address("172.17.0.1")
        self.assertTrue(peer.is_private)
        self.assertEqual(
            setup_posture(bind_host="0.0.0.0", peer=peer, trusted_proxy=False),
            "public_failsafe",
        )

    def test_docker_user_bridge_is_public_failsafe(self) -> None:
        peer = ipaddress.ip_address("172.18.0.4")
        self.assertTrue(peer.is_private)
        self.assertEqual(
            setup_posture(bind_host="0.0.0.0", peer=peer, trusted_proxy=False),
            "public_failsafe",
        )

    def test_true_lan_stays_lan(self) -> None:
        self.assertEqual(
            setup_posture(
                bind_host="0.0.0.0",
                peer=ipaddress.ip_address("192.168.1.20"),
                trusted_proxy=False,
            ),
            "lan",
        )
        self.assertEqual(
            setup_posture(
                bind_host="0.0.0.0",
                peer=ipaddress.ip_address("10.10.1.50"),
                trusted_proxy=False,
            ),
            "lan",
        )

    def test_public_peer_halts(self) -> None:
        self.assertEqual(
            setup_posture(
                bind_host="0.0.0.0",
                peer=ipaddress.ip_address("8.8.8.8"),
                trusted_proxy=False,
            ),
            "halt_wan",
        )

    def test_tailscale_cgnat_peer_is_lan_not_halt(self) -> None:
        """RFC 6598 100.64.0.0/10 (Tailscale) is not WAN even when is_private is False."""
        peer = ipaddress.ip_address("100.64.1.1")
        self.assertEqual(
            setup_posture(bind_host="0.0.0.0", peer=peer, trusted_proxy=False),
            "lan",
        )

    def test_trusted_proxy_wins(self) -> None:
        self.assertEqual(
            setup_posture(
                bind_host="0.0.0.0",
                peer=ipaddress.ip_address("172.17.0.1"),
                trusted_proxy=True,
            ),
            "proxy",
        )


class SnapshotSanitizeTests(unittest.TestCase):
    def test_drops_secret_keys_and_header_values(self) -> None:
        dirty = {
            "family": "AF_INET",
            "bind_host": "0.0.0.0",
            "bind_port": 8788,
            "peer_host": "172.17.0.1",
            "peer_port": 43210,
            "classification": "public_failsafe",
            "forwarded_proto_present": True,
            "forwarded_for_present": True,
            "trusted_proxy_mode": False,
            "authorization": "Bearer super-secret",
            "cookie": "session=abc",
            "x-plex-token": "plex-token-value",
            "x-forwarded-for": "8.8.8.8",
        }
        clean = sanitize_detection_snapshot(dirty)
        blob = json.dumps(clean).lower()
        self.assertNotIn("authorization", blob)
        self.assertNotIn("bearer", blob)
        self.assertNotIn("cookie", blob)
        self.assertNotIn("x-plex-token", blob)
        self.assertNotIn("plex-token-value", blob)
        self.assertNotIn("8.8.8.8", blob)
        self.assertEqual(clean["bind_host"], "0.0.0.0")
        self.assertEqual(clean["peer_host"], "172.17.0.1")

    def test_persist_rejects_secret_shaped_values(self) -> None:
        snap = build_detection_snapshot(
            bind_host="0.0.0.0",
            bind_port=8788,
            peer_host="172.17.0.1",
            peer_port=9,
            classification="public_failsafe",
            forwarded_proto_present=True,
            forwarded_for_present=False,
            trusted_proxy_mode=False,
        )
        dirty = dict(snap)
        dirty["authorization"] = "Bearer abc"
        dirty["x-plex-token"] = "tok"
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "t.db")
            stored = persist_detection_snapshot(db, dirty)
            loaded = load_detection_snapshot(db)
        blob = json.dumps({"stored": stored, "loaded": loaded}).lower()
        self.assertNotIn("authorization", blob)
        self.assertNotIn("x-plex-token", blob)
        self.assertNotIn("bearer", blob)
        self.assertFalse(snapshot_contains_secrets(stored))


class WanInterlockTests(unittest.TestCase):
    def _request(self, host: str, headers: list[tuple[bytes, bytes]] | None = None):
        request = MagicMock()
        request.client.host = host
        request.client.port = 1234
        header_map = {k.decode().lower(): v.decode() for k, v in (headers or [])}
        request.headers.get.side_effect = lambda name, default="": header_map.get(
            name.lower(), default
        )
        return request

    def test_docker_nat_does_not_block_single_owner(self) -> None:
        """Unraid/Docker: 0.0.0.0 bind + bridge peer is not a runtime WAN lock."""
        request = self._request("172.17.0.1")
        self.assertFalse(
            wan_interlock_blocks(request, multi_user_enabled=False, bind_host="0.0.0.0")
        )

    def test_lan_does_not_block(self) -> None:
        request = self._request("192.168.1.20")
        self.assertFalse(
            wan_interlock_blocks(request, multi_user_enabled=False, bind_host="0.0.0.0")
        )

    def test_public_peer_blocks_single_owner(self) -> None:
        request = self._request("8.8.8.8")
        self.assertTrue(
            wan_interlock_blocks(request, multi_user_enabled=False, bind_host="0.0.0.0")
        )

    def test_tailscale_cgnat_does_not_block_single_owner(self) -> None:
        request = self._request("100.64.1.1")
        self.assertFalse(
            wan_interlock_blocks(request, multi_user_enabled=False, bind_host="0.0.0.0")
        )

    def test_trusted_https_proto_does_not_block_docker_or_lan(self) -> None:
        """Cloudflare Tunnel / reverse proxy: trusted HTTPS is not itself WAN."""
        docker = self._request(
            "172.17.0.1",
            headers=[(b"x-forwarded-proto", b"https")],
        )
        lan = self._request(
            "192.168.1.20",
            headers=[(b"x-forwarded-proto", b"https")],
        )
        with unittest.mock.patch(
            "projectionist.web.ingress.trust_proxy_headers",
            return_value=True,
        ):
            self.assertFalse(
                wan_interlock_blocks(docker, multi_user_enabled=False, bind_host="0.0.0.0")
            )
            self.assertFalse(
                wan_interlock_blocks(lan, multi_user_enabled=False, bind_host="0.0.0.0")
            )

    def test_forwarded_for_does_not_make_a_private_peer_external(self) -> None:
        """The first X-Forwarded-For hop is not the tunnel signal."""
        request = self._request(
            "172.17.0.1",
            headers=[
                (b"x-forwarded-proto", b"https"),
                (b"x-forwarded-for", b"8.8.8.8"),
            ],
        )
        with unittest.mock.patch(
            "projectionist.web.ingress.trust_proxy_headers",
            return_value=True,
        ):
            self.assertFalse(
                wan_interlock_blocks(request, multi_user_enabled=False, bind_host="0.0.0.0")
            )

    def test_forwarded_for_does_not_hide_a_public_peer(self) -> None:
        request = self._request(
            "8.8.8.8",
            headers=[(b"x-forwarded-for", b"10.10.1.50")],
        )
        with unittest.mock.patch(
            "projectionist.web.ingress.trust_proxy_headers",
            return_value=True,
        ):
            self.assertTrue(
                wan_interlock_blocks(request, multi_user_enabled=False, bind_host="0.0.0.0")
            )

    def test_cloudflare_headers_from_a_trusted_connector_are_external(self) -> None:
        request = self._request(
            "172.17.0.1",
            headers=[(b"cf-ray", b"9abc-EWR"), (b"cf-connecting-ip", b"203.0.113.8")],
        )
        with unittest.mock.patch.dict(os.environ, {"PROJECTIONIST_TRUSTED_PROXIES": "172.17.0.1"}):
            self.assertTrue(
                wan_interlock_blocks(request, multi_user_enabled=False, bind_host="0.0.0.0")
            )

    def test_cloudflare_headers_from_another_peer_do_not_count(self) -> None:
        request = self._request(
            "192.168.1.20",
            headers=[(b"cf-ray", b"9abc-EWR"), (b"cf-connecting-ip", b"8.8.8.8")],
        )
        with unittest.mock.patch.dict(os.environ, {"PROJECTIONIST_TRUSTED_PROXIES": "172.17.0.1"}):
            self.assertFalse(
                wan_interlock_blocks(request, multi_user_enabled=False, bind_host="0.0.0.0")
            )

    def test_a_connector_without_cloudflare_headers_is_not_external(self) -> None:
        request = self._request(
            "172.17.0.1",
            headers=[(b"x-forwarded-for", b"8.8.8.8")],
        )
        with unittest.mock.patch.dict(os.environ, {"PROJECTIONIST_TRUSTED_PROXIES": "172.17.0.1"}):
            self.assertFalse(
                wan_interlock_blocks(request, multi_user_enabled=False, bind_host="0.0.0.0")
            )

    def test_untrusted_forwarded_https_does_not_unlock_or_block_lan(self) -> None:
        lan = self._request(
            "192.168.1.20",
            headers=[(b"x-forwarded-proto", b"https")],
        )
        docker = self._request(
            "172.17.0.1",
            headers=[
                (b"x-forwarded-proto", b"https"),
                (b"x-forwarded-for", b"8.8.8.8"),
            ],
        )
        public = self._request(
            "8.8.8.8",
            headers=[
                (b"x-forwarded-proto", b"https"),
                (b"x-forwarded-for", b"192.168.1.20"),
            ],
        )
        self.assertFalse(wan_interlock_blocks(lan, multi_user_enabled=False, bind_host="0.0.0.0"))
        self.assertFalse(
            wan_interlock_blocks(docker, multi_user_enabled=False, bind_host="0.0.0.0")
        )
        self.assertTrue(wan_interlock_blocks(public, multi_user_enabled=False, bind_host="0.0.0.0"))


class SetupReopenTests(unittest.TestCase):
    def _request(self, host: str, headers: dict[str, str] | None = None):
        request = MagicMock()
        request.client.host = host
        request.client.port = 1234
        header_map = {key.lower(): value for key, value in (headers or {}).items()}
        request.headers.get.side_effect = lambda name, default="": header_map.get(
            name.lower(), default
        )
        return request

    def test_an_external_request_does_not_reopen_setup(self) -> None:
        from projectionist.web.setup_mode import SETUP_STATE_KEY, resolve_setup_state

        previous = {
            key: os.environ.get(key)
            for key in (
                "DATA_DIR",
                "PROJECTIONIST_SKIP_DOTENV",
                "PROJECTIONIST_TRUSTED_PROXIES",
                "PROJECTIONIST_SETUP_STATE",
                "PROJECTIONIST_OWNER_PASSWORD",
            )
        }
        try:
            with tempfile.TemporaryDirectory() as tmp:
                os.environ["DATA_DIR"] = tmp
                os.environ["PROJECTIONIST_SKIP_DOTENV"] = "1"
                os.environ["PROJECTIONIST_TRUSTED_PROXIES"] = "172.17.0.1"
                os.environ.pop("PROJECTIONIST_SETUP_STATE", None)
                os.environ.pop("PROJECTIONIST_OWNER_PASSWORD", None)
                (Path(tmp) / "settings.json").write_text(
                    json.dumps({"network": {"public_base_url": "https://films.example.com"}}),
                    encoding="utf-8",
                )
                external_db = Database(Path(tmp) / "external.db")
                external_db.set_config(SETUP_STATE_KEY, "active")
                state = resolve_setup_state(
                    external_db,
                    self._request("172.17.0.1", {"cf-ray": "9abc-EWR"}),
                )
                self.assertEqual(state, "active")
                self.assertEqual(external_db.get_config(SETUP_STATE_KEY), "active")

                home_db = Database(Path(tmp) / "home.db")
                home_db.set_config(SETUP_STATE_KEY, "active")
                self.assertEqual(
                    resolve_setup_state(home_db, self._request("192.168.1.20")),
                    "setup",
                )
                self.assertEqual(home_db.get_config(SETUP_STATE_KEY), "setup")
        finally:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value


if __name__ == "__main__":
    unittest.main()
