"""Ingress handshake: Docker NAT is not LAN; snapshots never store secrets."""

from __future__ import annotations

import ipaddress
import json
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
        request.headers.get.side_effect = lambda name, default="": header_map.get(name.lower(), default)
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

    def test_trusted_forwarded_public_client_still_blocks(self) -> None:
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
            self.assertTrue(
                wan_interlock_blocks(request, multi_user_enabled=False, bind_host="0.0.0.0")
            )

    def test_trusted_forwarded_private_client_does_not_block_public_peer(self) -> None:
        request = self._request(
            "8.8.8.8",
            headers=[(b"x-forwarded-for", b"10.10.1.50")],
        )
        with unittest.mock.patch(
            "projectionist.web.ingress.trust_proxy_headers",
            return_value=True,
        ):
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
        self.assertFalse(
            wan_interlock_blocks(lan, multi_user_enabled=False, bind_host="0.0.0.0")
        )
        self.assertFalse(
            wan_interlock_blocks(docker, multi_user_enabled=False, bind_host="0.0.0.0")
        )
        self.assertTrue(
            wan_interlock_blocks(public, multi_user_enabled=False, bind_host="0.0.0.0")
        )


if __name__ == "__main__":
    unittest.main()
