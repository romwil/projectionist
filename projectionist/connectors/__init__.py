"""Connector clients for external services."""

from projectionist.connectors.fanart import FanartClient
from projectionist.connectors.http import optional_int, parse_plex_guid, request_json, request_xml
from projectionist.connectors.plex import PlexClient, PlexLibraryItem, PlexSection
from projectionist.connectors.radarr import RadarrClient
from projectionist.connectors.sonarr import SonarrClient
from projectionist.connectors.tautulli import TautulliClient
from projectionist.connectors.tmdb import TMDBClient
from projectionist.connectors.tvdb import TVDBClient

__all__ = [
    "FanartClient",
    "PlexClient",
    "PlexLibraryItem",
    "PlexSection",
    "RadarrClient",
    "SonarrClient",
    "TMDBClient",
    "TVDBClient",
    "TautulliClient",
    "optional_int",
    "parse_plex_guid",
    "request_json",
    "request_xml",
]
