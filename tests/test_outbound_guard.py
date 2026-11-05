"""SEC-007: outbound notification destinations must be public, at every hop."""

from __future__ import annotations

import http.server
import ipaddress
import socket
import threading
import unittest
from unittest.mock import patch

from projectionist.connectors import outbound_guard
from projectionist.connectors.outbound_guard import (
    OutboundBlocked,
    check_public_destination,
    public_only_outbound,
)
from projectionist.notifications.apprise_transport import (
    AppriseSendError,
    apprise_available,
    send_apprise,
)

SSRF_CORPUS = (
    "json://127.0.0.1/hook",
    "json://localhost/hook",
    "json://10.0.0.5/hook",
    "jsons://192.168.1.20:8443/hook",
    "json://172.16.4.4/hook",
    "json://169.254.169.254/latest/meta-data",
    "json://[fe80::1]/hook",
    "json://[::1]/hook",
    "json://[::ffff:169.254.169.254]/hook",
    "json://[fd00:ec2::254]/hook",
    "json://100.100.100.200/hook",
    "json://metadata.google.internal/computeMetadata/v1",
    "http://0.0.0.0/",
    "ntfy://10.1.2.3/topic",
    "mailto://user:pw@192.168.0.2",
)


class PreflightTests(unittest.TestCase):
    def test_corpus_is_refused_before_connect(self) -> None:
        for url in SSRF_CORPUS:
            with self.subTest(url=url):
                with self.assertRaises(OutboundBlocked):
                    check_public_destination(url)

    def test_public_and_token_style_destinations_pass(self) -> None:
        with patch.object(
            outbound_guard,
            "_resolve",
            return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))],
        ):
            check_public_destination("jsons://hooks.example.com/notify")
        # Vendor schemes whose "host" is a token never resolve; the connect guard covers them.
        check_public_destination("discord://123456/abcdef-token")

    def test_dns_name_pointing_at_metadata_is_refused(self) -> None:
        with patch.object(
            outbound_guard,
            "_resolve",
            return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", 80))],
        ):
            with self.assertRaises(OutboundBlocked):
                check_public_destination("json://innocent.example/hook")


class _Redirector(http.server.BaseHTTPRequestHandler):
    hits: list[str] = []
    target = ""

    def do_POST(self):  # noqa: N802
        self.hits.append(self.path)
        self.send_response(307)
        self.send_header("Location", self.target)
        self.send_header("Content-Length", "0")
        self.end_headers()

    do_GET = do_POST

    def log_message(self, *_args):
        return


class ConnectTimeGuardTests(unittest.TestCase):
    def test_guard_is_scoped_to_the_calling_thread_and_block(self) -> None:
        with public_only_outbound():
            with self.assertRaises(OutboundBlocked):
                socket.getaddrinfo("127.0.0.1", 80)
            seen: list[object] = []
            worker = threading.Thread(target=lambda: seen.append(socket.getaddrinfo("127.0.0.1", 80)))
            worker.start()
            worker.join()
            self.assertTrue(seen, "other threads (Plex, *arr) keep LAN access")
        self.assertTrue(socket.getaddrinfo("127.0.0.1", 80))

    def test_redirect_to_private_host_is_refused_before_its_connect(self) -> None:
        import requests

        server = http.server.HTTPServer(("127.0.0.1", 0), _Redirector)
        port = server.server_address[1]
        _Redirector.hits = []
        _Redirector.target = f"http://internal.example:{port}/admin"
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        real = outbound_guard._real_getaddrinfo
        real_reason = outbound_guard.blocked_ip_reason

        def fake_dns(host, port_, *args, **kwargs):
            name = host.decode() if isinstance(host, bytes) else host
            if name == "public.example":
                return real("127.0.0.1", port_, *args, **kwargs)
            if name == "internal.example":
                return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.8", port_))]
            return real(host, port_, *args, **kwargs)

        def treat_test_server_as_public(ip, **kwargs):
            if ip == ipaddress.ip_address("127.0.0.1"):
                return None
            return real_reason(ip, **kwargs)

        connects: list[object] = []
        real_connect = socket.socket.connect

        def spy_connect(sock, address):
            connects.append(address)
            return real_connect(sock, address)

        try:
            with patch.object(outbound_guard, "_real_getaddrinfo", fake_dns), patch.object(
                outbound_guard, "blocked_ip_reason", treat_test_server_as_public
            ), patch.object(socket.socket, "connect", spy_connect):
                with public_only_outbound():
                    with self.assertRaises(requests.exceptions.ConnectionError):
                        requests.post(f"http://public.example:{port}/hook", timeout=5)
                    self.assertIn("private", outbound_guard.last_block_reason() or "")
        finally:
            server.shutdown()
            server.server_close()

        self.assertEqual(_Redirector.hits, ["/hook"])
        self.assertTrue(all(addr[0] != "10.0.0.8" for addr in connects), connects)


@unittest.skipUnless(apprise_available(), "apprise not installed")
class AppriseSendTests(unittest.TestCase):
    def test_owner_supplied_private_url_is_refused_without_a_connect(self) -> None:
        with patch.object(socket.socket, "connect", side_effect=AssertionError("connected")):
            for url in ("json://169.254.169.254/latest", "json://10.0.0.5/hook", "json://localhost/x"):
                with self.subTest(url=url):
                    with self.assertRaises(AppriseSendError) as ctx:
                        send_apprise(None, title="t", body="b", urls=[url])
                    self.assertIn("refused", str(ctx.exception))

    def test_install_config_destinations_hit_the_connect_guard(self) -> None:
        config = "urls:\n  - json://192.168.50.9/hook\n"
        with patch.object(socket.socket, "connect", side_effect=AssertionError("connected")):
            with self.assertRaises(AppriseSendError) as ctx:
                send_apprise(None, title="t", body="b", urls=[], config_body=config)
        self.assertIn("refused", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
