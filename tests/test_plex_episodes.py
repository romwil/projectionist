"""Tests for Plex TV season/episode parsing."""

from __future__ import annotations

import unittest
import xml.etree.ElementTree as ET
from unittest.mock import patch

from projectionist.connectors.plex import PlexClient


class PlexEpisodeParsingTests(unittest.TestCase):
    def _client(self) -> PlexClient:
        return PlexClient("http://plex.test:32400", "token")

    def test_show_seasons_skips_all_episodes_folder_without_rating_key(self) -> None:
        xml = """
        <MediaContainer size="2">
          <Directory key="/library/metadata/1/allLeaves" title="All episodes" leafCount="10" />
          <Directory ratingKey="200" index="1" title="Season 1" leafCount="10" viewedLeafCount="0" />
        </MediaContainer>
        """
        client = self._client()
        with patch.object(client, "_request_xml", return_value=ET.fromstring(xml)):
            seasons = client.show_seasons("100")

        self.assertEqual(len(seasons), 1)
        self.assertEqual(seasons[0].rating_key, "200")
        self.assertEqual(seasons[0].season_number, 1)

    def test_show_all_episodes_parses_video_leaves(self) -> None:
        xml = """
        <MediaContainer size="2">
          <Video ratingKey="301" title="Pilot" parentIndex="1" index="1" duration="3600000" viewCount="0" />
          <Video ratingKey="302" title="Second" parentIndex="1" index="2" duration="3600000" viewCount="1" />
        </MediaContainer>
        """
        client = self._client()
        with patch.object(client, "_request_xml", return_value=ET.fromstring(xml)):
            episodes = client.show_all_episodes("100")

        self.assertEqual(len(episodes), 2)
        self.assertEqual(episodes[0].title, "Pilot")
        self.assertEqual(episodes[0].season_number, 1)
        self.assertEqual(episodes[0].episode_number, 1)
        self.assertEqual(episodes[0].runtime_minutes, 60)

    def test_parse_video_captures_added_at(self) -> None:
        xml = """
        <Video ratingKey="401" title="Inception" year="2010" addedAt="1704067200" viewCount="3" />
        """
        client = self._client()
        element = ET.fromstring(xml)
        item = client._parse_video(element, "movie")
        self.assertEqual(item.added_at, 1704067200)
        self.assertEqual(item.view_count, 3)

    def test_parse_video_reads_guid_children_for_external_ids(self) -> None:
        xml = """
        <Video ratingKey="218935" guid="plex://movie/5d7768374de0ee001fccc04a"
               title="The 'Burbs" year="1989">
          <Guid id="imdb://tt0096734" />
          <Guid id="tmdb://11974" />
          <Guid id="tvdb://5869" />
        </Video>
        """
        client = self._client()
        element = ET.fromstring(xml)
        item = client._parse_video(element, "movie")
        self.assertEqual(item.tmdb_id, "11974")
        self.assertEqual(item.imdb_id, "tt0096734")
        self.assertEqual(item.tvdb_id, "5869")


if __name__ == "__main__":
    unittest.main()
