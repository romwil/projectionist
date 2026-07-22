"""Tests for Plex on-deck / continue-watching reads."""

from __future__ import annotations

import unittest
import xml.etree.ElementTree as ET
from unittest.mock import patch

from curatorx.connectors.plex import PlexClient


class PlexOnDeckTests(unittest.TestCase):
    def _client(self) -> PlexClient:
        return PlexClient("http://plex.test:32400", "token")

    def test_on_deck_parses_movies_and_episodes(self) -> None:
        xml = """
        <MediaContainer size="2">
          <Video ratingKey="101" type="movie" title="Heat" year="1995"
                 viewOffset="1200000" duration="10200000" viewCount="0" />
          <Video ratingKey="501" type="episode" title="Pilot"
                 grandparentRatingKey="200" grandparentTitle="The Wire"
                 parentIndex="1" index="1"
                 viewOffset="600000" duration="3600000" viewCount="0">
            <Guid id="tmdb://123" />
          </Video>
        </MediaContainer>
        """
        client = self._client()
        with patch.object(client, "_request_xml", return_value=ET.fromstring(xml)):
            items = client.on_deck(limit=10)

        self.assertEqual(len(items), 2)
        self.assertEqual(items[0].media_type, "movie")
        self.assertEqual(items[0].rating_key, "101")
        self.assertEqual(items[0].view_offset_ms, 1200000)
        self.assertEqual(items[1].media_type, "episode")
        self.assertEqual(items[1].show_rating_key, "200")
        self.assertEqual(items[1].show_title, "The Wire")
        self.assertEqual(items[1].season_number, 1)
        self.assertEqual(items[1].episode_number, 1)
        self.assertEqual(items[1].tmdb_id, "123")

    def test_continue_watching_aliases_on_deck(self) -> None:
        client = self._client()
        with patch.object(client, "on_deck", return_value=[]) as mocked:
            result = client.continue_watching(limit=5)
        mocked.assert_called_once_with(limit=5)
        self.assertEqual(result, [])

    def test_on_deck_skips_entries_without_rating_key(self) -> None:
        xml = """
        <MediaContainer>
          <Video type="movie" title="No Key" viewOffset="100" />
          <Video ratingKey="9" type="movie" title="Ok" viewOffset="100" />
        </MediaContainer>
        """
        client = self._client()
        with patch.object(client, "_request_xml", return_value=ET.fromstring(xml)):
            items = client.on_deck()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].title, "Ok")


if __name__ == "__main__":
    unittest.main()
