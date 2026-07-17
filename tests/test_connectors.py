"""Tests for HTTP helpers and TVDB client."""

import unittest

from curatorx.connectors.http import merge_plex_provider_ids, parse_plex_guid
from curatorx.connectors.tvdb import TVDBClient


class HttpHelperTests(unittest.TestCase):
    def test_parse_plex_guid(self) -> None:
        ids = parse_plex_guid("com.plexapp.agents.themoviedb://12345?lang=en")
        self.assertEqual(ids["tmdb_id"], "12345")

    def test_parse_plex_guid_modern_tmdb_format(self) -> None:
        ids = parse_plex_guid("tmdb://11974")
        self.assertEqual(ids["tmdb_id"], "11974")

    def test_parse_plex_guid_typed_paths(self) -> None:
        self.assertEqual(parse_plex_guid("tmdb://movie/550")["tmdb_id"], "550")
        self.assertEqual(parse_plex_guid("tmdb://tv/1396")["tmdb_id"], "1396")
        self.assertEqual(parse_plex_guid("tvdb://series/81189")["tvdb_id"], "81189")

    def test_merge_plex_provider_ids_from_guid_children(self) -> None:
        from curatorx.connectors.http import merge_plex_provider_ids

        ids = merge_plex_provider_ids(
            "plex://movie/5d7768374de0ee001fccc04a",
            "imdb://tt0096734",
            "tmdb://movie/11974",
            "tvdb://5869",
        )
        self.assertEqual(ids["tmdb_id"], "11974")
        self.assertEqual(ids["imdb_id"], "tt0096734")
        self.assertEqual(ids["tvdb_id"], "5869")


class TVDBClientTests(unittest.TestCase):
    def test_base_url(self) -> None:
        client = TVDBClient("test-key")
        self.assertEqual(client.base_url, "https://api4.thetvdb.com/v4")


if __name__ == "__main__":
    unittest.main()
