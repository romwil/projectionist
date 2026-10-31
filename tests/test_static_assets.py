"""Cache and compression policy for production frontend assets."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.gzip import GZipMiddleware

from projectionist.web.static_assets import IMMUTABLE_ASSET_CACHE_CONTROL, ImmutableAssetStaticFiles


class StaticAssetPolicyTests(unittest.TestCase):
    def test_hashed_asset_is_immutable_and_gzipped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            assets = Path(tmp)
            (assets / "app-abc12345.js").write_text("x" * 2048, encoding="utf-8")
            app = FastAPI()
            app.add_middleware(GZipMiddleware)
            app.mount("/assets", ImmutableAssetStaticFiles(directory=assets), name="assets")

            response = TestClient(app).get("/assets/app-abc12345.js", headers={"Accept-Encoding": "gzip"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["cache-control"], IMMUTABLE_ASSET_CACHE_CONTROL)
        self.assertEqual(response.headers["content-encoding"], "gzip")

    def test_unhashed_asset_is_not_immutable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            assets = Path(tmp)
            (assets / "runtime.js").write_text("x", encoding="utf-8")
            app = FastAPI()
            app.mount("/assets", ImmutableAssetStaticFiles(directory=assets), name="assets")

            response = TestClient(app).get("/assets/runtime.js")

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("immutable", response.headers.get("cache-control", ""))


if __name__ == "__main__":
    unittest.main()
