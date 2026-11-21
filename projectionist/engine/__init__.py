"""Projectionist's playback engine.

Plex is a media source. This package owns path mapping, probing, planning,
and engine sessions. The web app includes the router; playback policy stays
here.
"""

from projectionist.engine.pathmap import map_plex_path, normalize_mappings
from projectionist.engine.probe import probe_file
from projectionist.engine.source import PlexMediaSource, public_media

__all__ = [
    "PlexMediaSource",
    "map_plex_path",
    "normalize_mappings",
    "probe_file",
    "public_media",
]
