"""NAT-004: committed client fixtures match a fresh recording."""

from __future__ import annotations

import unittest

from projectionist.web.client_contract import CLIENT_ROUTES
from projectionist.web.client_fixtures import fixture_slug, read_fixture_files


class ClientFixtureTests(unittest.TestCase):
    def test_every_client_route_has_a_fixture_file(self) -> None:
        files = read_fixture_files()
        for method, path in CLIENT_ROUTES:
            name = fixture_slug(method, path)
            self.assertIn(name, files, name)
            self.assertIn(f'"path": "{path}"', files[name])

    def test_recorded_fixtures_match_and_hide_the_server_token(self) -> None:
        from projectionist.web.client_fixtures import main

        self.assertEqual(main(["--check"]), 0)
