"""Static-file policy for cacheable frontend build assets."""

from __future__ import annotations

import re

from starlette.staticfiles import StaticFiles


# Vite names production artifacts like ``AppRoutes-DG4trD0a.js``.  Only those
# content-addressed files are safe to cache forever; HTML and API responses
# deliberately use their existing response policies.
_HASHED_ASSET_NAME = re.compile(r".+-[A-Za-z0-9_-]{8,}\.[A-Za-z0-9]+$")
IMMUTABLE_ASSET_CACHE_CONTROL = "public, max-age=31536000, immutable"


class ImmutableAssetStaticFiles(StaticFiles):
    """Serve Vite assets with an immutable cache lifetime when content-addressed."""

    async def get_response(self, path: str, scope: object):
        response = await super().get_response(path, scope)
        if response.status_code == 200 and _HASHED_ASSET_NAME.fullmatch(path):
            response.headers["Cache-Control"] = IMMUTABLE_ASSET_CACHE_CONTROL
        return response
