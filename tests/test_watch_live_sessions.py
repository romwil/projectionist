"""Phase 2 active Plex session observation tests."""

from __future__ import annotations

import tempfile
import threading
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch

from projectionist.config_store import Settings
from projectionist.connectors.plex import PlexClient
from projectionist.library.db import Database
from projectionist.watch_tracker.live_sessions import (
    IDLE_POLL_SECONDS,
    LIVE_POLL_SECONDS,
    LiveSessionPoller,
    normalize_active_session,
    poll_active_sessions,
    poll_interval_seconds,
)


ACTIVE_SESSIONS_XML = """
<MediaContainer size="3">
  <Video ratingKey="movie-1" type="movie" viewOffset="120000" duration="600000">
    <User id="42" title="Member" />
    <Player address="192.0.2.10" machineIdentifier="client-a"
            title="Living Room" state="playing" />
    <Session id="session-a" bandwidth="12000" location="lan" />
  </Video>
  <Video ratingKey="episode-1" type="episode" grandparentRatingKey="show-1"
         viewOffset="300000" duration="3600000">
    <User id="42" title="Member" />
    <Player publicAddress="203.0.113.8" machineIdentifier="client-b"
            title="Phone" state="paused" />
    <Session id="session-b" />
  </Video>
  <Track ratingKey="track-1" type="track">
    <User id="42" />
    <Player machineIdentifier="client-c" />
    <Session id="session-c" />
  </Track>
</MediaContainer>
"""


class PlexActiveSessionParserTests(unittest.TestCase):
    def test_active_sessions_parses_playable_rows_without_network_fields(self) -> None:
        client = PlexClient("http://plex.test:32400", "secret-token")
        with patch.object(
            client,
            "_request_xml",
            return_value=ET.fromstring(ACTIVE_SESSIONS_XML),
        ):
            sessions = client.active_sessions()

        self.assertEqual(len(sessions), 2)
        movie, episode = sessions
        self.assertEqual(movie.source_user_key, "42")
        self.assertEqual(movie.rating_key, "movie-1")
        self.assertEqual(movie.client_identifier, "client-a")
        self.assertEqual(movie.session_key, "session-a")
        self.assertEqual(movie.state, "playing")
        self.assertEqual(episode.media_type, "episode")
        self.assertEqual(episode.parent_rating_key, "show-1")
        self.assertEqual(episode.state, "paused")
        self.assertNotIn("192.0.2.10", repr(sessions))
        self.assertNotIn("203.0.113.8", repr(sessions))
        self.assertNotIn("Living Room", repr(sessions))
        self.assertNotIn("secret-token", repr(sessions))

    def test_active_sessions_skips_rows_without_stable_account_identity(self) -> None:
        xml = """
        <MediaContainer>
          <Video ratingKey="movie-1" type="movie" viewOffset="1" duration="2">
            <User title="Display name is not identity" />
            <Player machineIdentifier="client-a" />
            <Session id="session-a" />
          </Video>
        </MediaContainer>
        """
        client = PlexClient("http://plex.test:32400", "token")
        with patch.object(client, "_request_xml", return_value=ET.fromstring(xml)):
            self.assertEqual(client.active_sessions(), [])


class LiveSessionObservationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db = Database(Path(self._tmpdir.name) / "sessions.db")
        self.user = self.db.upsert_plex_user(
            user_id="plex-user-42",
            display_name="Member",
            email=None,
            plex_user_id="42",
            role="member",
        )

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_poll_persists_progress_and_hashes_stable_client_identifier(self) -> None:
        client = PlexClient("http://plex.test:32400", "secret-token")
        with patch.object(
            client,
            "_request_xml",
            return_value=ET.fromstring(ACTIVE_SESSIONS_XML),
        ):
            result = poll_active_sessions(
                self.db,
                client,
                server_machine_id="server-1",
                occurred_at_ms=1_700_000_000_000,
            )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["active_sessions"], 2)
        self.assertEqual(result["inserted"], 2)
        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT source_event_kind, user_id, client_key, session_key,
                       progress_ms, duration_ms, terminal
                FROM watch_events ORDER BY rating_key
                """
            ).fetchall()
        self.assertEqual({row["source_event_kind"] for row in rows}, {"session_progress"})
        self.assertEqual({row["user_id"] for row in rows}, {self.user["id"]})
        self.assertEqual({row["terminal"] for row in rows}, {0})
        self.assertTrue(all(len(row["client_key"]) == 64 for row in rows))
        stored = " ".join(str(value) for row in rows for value in row)
        self.assertNotIn("client-a", stored)
        self.assertNotIn("client-b", stored)

    def test_reconnect_and_client_switch_remain_distinct_observations(self) -> None:
        client = PlexClient("http://plex.test:32400", "token")
        root = ET.fromstring(ACTIVE_SESSIONS_XML)
        with patch.object(client, "_request_xml", return_value=root):
            first = client.active_sessions()[0]
        first_event = normalize_active_session(
            first,
            server_machine_id="server-1",
            occurred_at_ms=1_700_000_000_000,
        )

        root.find("Video/Player").set("machineIdentifier", "client-new")
        root.find("Video/Session").set("id", "session-new")
        with patch.object(client, "_request_xml", return_value=root):
            reconnected = client.active_sessions()[0]
        second_event = normalize_active_session(
            reconnected,
            server_machine_id="server-1",
            occurred_at_ms=1_700_000_060_000,
        )

        self.assertNotEqual(first_event.client_key, second_event.client_key)
        self.assertNotEqual(first_event.session_key, second_event.session_key)
        self.assertFalse(first_event.terminal)
        self.assertFalse(second_event.terminal)

    def test_outage_fails_soft_and_uses_idle_interval(self) -> None:
        settings = Settings(
            plex_url="http://plex.test:32400",
            plex_token="secret-token",
        )
        with patch.object(PlexClient, "machine_identifier", return_value="server-1"), patch.object(
            PlexClient,
            "active_sessions",
            side_effect=RuntimeError("Plex unavailable at 203.0.113.9"),
        ):
            result = LiveSessionPoller.poll_once(self.db, settings)

        self.assertEqual(result["status"], "degraded")
        self.assertEqual(result["active_sessions"], 0)
        self.assertNotIn("203.0.113.9", str(result))
        self.assertEqual(poll_interval_seconds(result), IDLE_POLL_SECONDS)

    def test_adaptive_intervals_and_clean_stop_restart(self) -> None:
        self.assertEqual(
            poll_interval_seconds({"status": "ok", "active_sessions": 1}),
            LIVE_POLL_SECONDS,
        )
        self.assertEqual(
            poll_interval_seconds({"status": "ok", "active_sessions": 0}),
            IDLE_POLL_SECONDS,
        )

        called = threading.Event()

        def poll_once(_db, _settings):
            called.set()
            return {"status": "ok", "active_sessions": 0}

        poller = LiveSessionPoller(
            db_factory=lambda: self.db,
            settings_factory=Settings,
            poll_fn=poll_once,
            initial_delay_seconds=0,
        )
        poller.start()
        self.assertTrue(called.wait(timeout=1))
        poller.stop()
        self.assertFalse(poller.is_running)

        called.clear()
        poller.start()
        self.assertTrue(called.wait(timeout=1))
        poller.stop()
        self.assertFalse(poller.is_running)


if __name__ == "__main__":
    unittest.main()
