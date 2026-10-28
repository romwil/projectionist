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

    def test_media_file_paths_merges_episode_leaves_when_show_has_a_part(self) -> None:
        show = ET.fromstring(
            """
            <MediaContainer>
              <Directory ratingKey="1">
                <Media><Part file="/trailers/extra.mkv" size="1" /></Media>
              </Directory>
            </MediaContainer>
            """
        )
        leaves = ET.fromstring(
            """
            <MediaContainer>
              <Video ratingKey="2">
                <Media><Part file="/tv/Show/S01E01.mkv" size="9" /></Media>
              </Video>
            </MediaContainer>
            """
        )
        client = self._client()
        with patch.object(client, "_request_xml", side_effect=[show, leaves]) as requested:
            paths = client.media_file_paths("1", include_leaves=True)
        self.assertEqual(paths, ["/trailers/extra.mkv", "/tv/Show/S01E01.mkv"])
        self.assertIn("/allLeaves", requested.call_args_list[1].args[0])

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

    def test_media_file_parts_includes_size_and_media_id(self) -> None:
        xml = ET.fromstring(
            """
            <MediaContainer>
              <Video ratingKey="5">
                <Media id="88">
                  <Part file="/movies/The Furious.mkv" size="6400" />
                </Media>
              </Video>
            </MediaContainer>
            """
        )
        client = self._client()
        with patch.object(client, "_request_xml", return_value=xml):
            parts = client.media_file_parts("5")
        self.assertEqual(
            parts,
            [{"file": "/movies/The Furious.mkv", "size": 6400, "media_id": "88"}],
        )
        with patch.object(client, "_request_xml", return_value=xml):
            self.assertEqual(client.media_file_paths("5"), ["/movies/The Furious.mkv"])

    def test_delete_media_asks_plex_to_remove_files(self) -> None:
        client = self._client()
        with (
            patch.object(
                client,
                "media_file_parts",
                return_value=[{"file": "/movies/a.mkv", "size": 9, "media_id": "44"}],
            ),
            patch.object(client, "_request_empty") as empty,
        ):
            client.delete_media("123", delete_files=True)
        paths = [call.args[0] for call in empty.call_args_list]
        self.assertTrue(any("/library/metadata/123/media/44" in path for path in paths))
        self.assertTrue(any("saveFile=0" in path for path in paths))
        self.assertTrue(all(call.kwargs.get("method") == "DELETE" for call in empty.call_args_list))

    def test_delete_metadata_does_not_ask_to_save_or_delete_files(self) -> None:
        client = self._client()
        with patch.object(client, "_request_empty") as empty:
            client.delete_metadata("123")
        empty.assert_called_once()
        self.assertEqual(empty.call_args.args[0], "/library/metadata/123")
        self.assertNotIn("saveFile", empty.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
