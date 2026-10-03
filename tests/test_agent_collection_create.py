"""Regression: agent collection create must not fail on its last step or fall back silently."""

from __future__ import annotations

import json
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch

from projectionist.agent.curator import _execute_tool_safely, _parse_tool_arguments
from projectionist.agent.tools import ToolRegistry, execute_confirmed_action
from projectionist.config_store import FeatureFlags, Settings
from projectionist.connectors.plex import PlexClient
from projectionist.connectors.plex_collections import PlexCollection, create_collection
from projectionist.library.db import DEFAULT_LENS_ID, Database


def _settings(**extra) -> Settings:
    return Settings(
        plex_url="http://plex.test",
        plex_token="token",
        plex_movie_section="1",
        features=FeatureFlags(plex_collections_enabled=True, **extra),
    )


class PlexCreateCollectionParsingTests(unittest.TestCase):
    def _client(self) -> PlexClient:
        return PlexClient("http://plex.test", "token")

    def test_childless_directory_response_yields_rating_key(self) -> None:
        # Real PMS returns a childless <Directory/>; ElementTree treats that as falsy.
        root = ET.fromstring('<MediaContainer size="1"><Directory ratingKey="777" title="x"/></MediaContainer>')
        with patch("projectionist.connectors.plex_collections.request_xml", return_value=root):
            made = create_collection(
                self._client(), section_id="1", title="Noir", media_type="movie"
            )
        self.assertEqual(made.rating_key, "777")

    def test_empty_body_recovers_by_title_instead_of_failing(self) -> None:
        existing = PlexCollection("888", "Noir", "1", "movie")
        with patch(
            "projectionist.connectors.plex_collections.request_xml",
            side_effect=ET.ParseError("no element found"),
        ), patch(
            "projectionist.connectors.plex_collections.list_collections",
            return_value=[existing],
        ):
            made = create_collection(
                self._client(), section_id="1", title="Noir", media_type="movie"
            )
        self.assertEqual(made.rating_key, "888")

    def test_unrecoverable_response_raises_clear_error(self) -> None:
        root = ET.fromstring('<MediaContainer size="0"/>')
        with patch("projectionist.connectors.plex_collections.request_xml", return_value=root), patch(
            "projectionist.connectors.plex_collections.list_collections", return_value=[]
        ):
            with self.assertRaises(RuntimeError) as ctx:
                create_collection(self._client(), section_id="1", title="Noir", media_type="movie")
        self.assertIn("Noir", str(ctx.exception))


class ConfirmedPlexCollectionTests(unittest.IsolatedAsyncioTestCase):
    def _propose(self, db: Database, settings: Settings):
        registry = ToolRegistry(db, settings, DEFAULT_LENS_ID, user_id="owner-1")
        return registry

    async def test_plex_failure_keeps_token_redeemable_and_names_the_cause(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "t.db")
            settings = _settings()
            registry = self._propose(db, settings)
            proposal = json.loads(
                await registry.execute(
                    "create_plex_collection", {"title": "Noir", "media_type": "movie"}
                )
            )
            self.assertEqual(proposal["scope"], "plex_only")
            self.assertIn("NOT create a Projectionist collection", proposal["message"])
            token = proposal["confirmation_token"]
            with patch(
                "projectionist.connectors.plex_collections.create_collection",
                side_effect=RuntimeError("HTTP 500 from plex"),
            ):
                failed = json.loads(
                    await registry.execute("confirm_pending_action", {"confirmation_token": token})
                )
            self.assertFalse(failed["ok"])
            self.assertIn("HTTP 500", failed["error"])
            self.assertIn("still pending", failed["error"])
            fake = PlexCollection("c1", "[CuratorX] Noir", "1", "movie")
            with patch(
                "projectionist.connectors.plex_collections.create_collection", return_value=fake
            ):
                retried = json.loads(
                    await registry.execute("confirm_pending_action", {"confirmation_token": token})
                )
            self.assertTrue(retried["ok"])
            self.assertEqual(retried["result"]["scope"], "plex_only")
            self.assertFalse(retried["result"]["projectionist_collection"])

    async def test_registry_write_failure_after_plex_create_is_not_reported_as_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "t.db")
            settings = _settings()
            registry = self._propose(db, settings)
            token = json.loads(
                await registry.execute(
                    "create_plex_collection", {"title": "Noir", "media_type": "movie"}
                )
            )["confirmation_token"]
            fake = PlexCollection("c2", "[CuratorX] Noir", "1", "movie")
            with patch(
                "projectionist.connectors.plex_collections.create_collection", return_value=fake
            ), patch.object(
                db, "record_ephemeral_plex_collection", side_effect=RuntimeError("db locked")
            ):
                out = await execute_confirmed_action(db, settings, token, user_id="owner-1")
            self.assertEqual(out["result"]["rating_key"], "c2")
            self.assertIn("warning", out["result"])
            # Token consumed because Plex really was written.
            with self.assertRaises(RuntimeError):
                await execute_confirmed_action(db, settings, token, user_id="owner-1")


class ProjectionistCollectionToolTests(unittest.IsolatedAsyncioTestCase):
    async def test_create_list_builds_published_course_with_items(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "t.db")
            registry = ToolRegistry(db, _settings(), DEFAULT_LENS_ID)
            out = json.loads(
                await registry.execute(
                    "create_list",
                    {
                        "name": "Noir 101",
                        "list_kind": "course",
                        "publish": True,
                        "items": [
                            {"title": "Double Indemnity", "media_type": "movie", "tmdb_id": 996},
                            {"title": "No ids", "media_type": "movie"},
                        ],
                    },
                )
            )
            self.assertEqual(out["scope"], "projectionist")
            self.assertTrue(out["published"])
            self.assertEqual(out["list_kind"], "course")
            self.assertEqual(out["items_added"], 1)
            self.assertEqual(len(out["items_failed"]), 1)
            self.assertIn("warning", out)
            published = db.get_published_list(out["list"]["id"], include_items=True)
            self.assertIsNotNone(published)
            self.assertEqual(published["list_kind"], "course")

    async def test_create_list_rejects_bad_kind_and_non_owner_publish(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "t.db")
            registry = ToolRegistry(db, _settings(), DEFAULT_LENS_ID)
            bad = json.loads(
                await registry.execute("create_list", {"name": "X", "list_kind": "shelf"})
            )
            self.assertIn("list_kind", bad["error"])
            multi = Settings(
                features=FeatureFlags(
                    multi_user_enabled=True, agent_may_mutate_personal_data=True
                )
            )
            member = ToolRegistry(db, multi, DEFAULT_LENS_ID, user_id="m1", user_role="member")
            denied = json.loads(
                await member.execute("create_list", {"name": "Y", "publish": True})
            )
            self.assertIn("owner", denied["error"])
            self.assertEqual(db.list_published_lists(), [])


class AgentToolSafetyTests(unittest.IsolatedAsyncioTestCase):
    def test_malformed_arguments_become_an_error_not_an_exception(self) -> None:
        args, err = _parse_tool_arguments('{"rating_keys": ["1", "2"')
        self.assertEqual(args, {})
        self.assertIn("not valid JSON", err)
        self.assertEqual(_parse_tool_arguments(None), ({}, None))

    async def test_tool_exception_is_returned_as_error_result(self) -> None:
        class Boom:
            async def execute(self, name, args):
                raise ValueError("bad id")

        out = json.loads(await _execute_tool_safely(Boom(), "add_to_list", {}))
        self.assertFalse(out["ok"])
        self.assertIn("add_to_list failed", out["error"])
        self.assertIn("bad id", out["error"])

    async def test_args_error_short_circuits_execution(self) -> None:
        class Never:
            async def execute(self, name, args):  # pragma: no cover
                raise AssertionError("must not run")

        out = json.loads(await _execute_tool_safely(Never(), "x", {}, "broken json"))
        self.assertEqual(out["error"], "broken json")


if __name__ == "__main__":
    unittest.main()
