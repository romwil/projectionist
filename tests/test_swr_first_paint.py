"""Non-blocking stale / cold paths for the shared SWR cache and its consumers.

Product rule (Explore 1.37.24, extended in 1.37.25): once anything is cached,
recompute never sits on the request path; a true cold miss returns a warming
skeleton quickly instead of hanging first paint.
"""

from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from projectionist.swr_cache import SwrCache


def _elapsed(fn):
    t0 = time.perf_counter()
    out = fn()
    return out, time.perf_counter() - t0


class SwrCacheTests(unittest.TestCase):
    def test_cold_miss_returns_warming_without_waiting(self) -> None:
        cache = SwrCache("t_cold", soft_ttl=60, hard_ttl=600)
        calls = {"n": 0}

        def slow() -> dict:
            calls["n"] += 1
            time.sleep(0.4)
            return {"v": 1}

        result, took = _elapsed(lambda: cache.get("k", slow, warming=lambda: {"skeleton": True}))
        self.assertTrue(result.warming)
        self.assertEqual(result.payload, {"skeleton": True})
        self.assertLess(took, 0.2)
        self.assertTrue(cache.wait_idle(3))
        again = cache.get("k", slow)
        self.assertEqual(again.state, "fresh")
        self.assertEqual(again.payload, {"v": 1})
        self.assertEqual(calls["n"], 1)

    def test_cold_wait_returns_real_payload_when_build_is_fast(self) -> None:
        cache = SwrCache("t_cold_wait", soft_ttl=60, hard_ttl=600)
        result = cache.get("k", lambda: {"v": 2}, warming=lambda: {}, cold_wait=1.0)
        self.assertEqual(result.state, "fresh")
        self.assertEqual(result.payload, {"v": 2})

    def test_second_cold_request_does_not_wait_again(self) -> None:
        cache = SwrCache("t_second", soft_ttl=60, hard_ttl=600)

        def slow() -> dict:
            time.sleep(0.5)
            return {"v": 1}

        cache.get("k", slow, warming=lambda: {}, cold_wait=0.05)
        _, took = _elapsed(lambda: cache.get("k", slow, warming=lambda: {}, cold_wait=2.0))
        self.assertLess(took, 0.3)

    def test_stale_serves_immediately_and_refreshes_in_background(self) -> None:
        cache = SwrCache("t_stale", soft_ttl=60, hard_ttl=600)
        cache.put("k", {"v": "old"})
        cache.invalidate()

        def slow() -> dict:
            time.sleep(0.35)
            return {"v": "new"}

        result, took = _elapsed(lambda: cache.get("k", slow))
        self.assertTrue(result.stale)
        self.assertEqual(result.payload["v"], "old")
        self.assertLess(took, 0.2)
        self.assertTrue(cache.wait_idle(3))
        self.assertEqual(cache.get("k", slow).payload["v"], "new")

    def test_single_flight(self) -> None:
        cache = SwrCache("t_single", soft_ttl=60, hard_ttl=600)
        cache.put("k", {"v": 0})
        cache.invalidate()
        calls = {"n": 0}

        def slow() -> dict:
            calls["n"] += 1
            time.sleep(0.2)
            return {"v": 1}

        for _ in range(5):
            cache.get("k", slow)
        self.assertTrue(cache.wait_idle(3))
        self.assertEqual(calls["n"], 1)

    def test_rejected_rebuild_keeps_last_good_payload(self) -> None:
        cache = SwrCache("t_reject", soft_ttl=60, hard_ttl=600)
        cache.put("k", {"ready": True, "v": "good"})
        cache.invalidate()
        bad = lambda: {"ready": False, "reason": "tunarr_unreachable"}  # noqa: E731
        cache.get("k", bad, accept=lambda p: p.get("ready"))
        self.assertTrue(cache.wait_idle(3))
        kept = cache.get("k", bad, accept=lambda p: p.get("ready"))
        self.assertEqual(kept.payload["v"], "good")
        self.assertTrue(kept.stale)

    def test_durable_payload_survives_a_restart(self) -> None:
        from projectionist.library.db import Database

        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "t.db")
            first = SwrCache("t_durable", soft_ttl=60, hard_ttl=600, durable=True)
            first.put("k", {"v": "persisted"}, db=db)
            # New process == new cache object with empty memory.
            second = SwrCache("t_durable", soft_ttl=60, hard_ttl=600, durable=True)

            def never() -> dict:
                time.sleep(0.3)
                return {"v": "rebuilt"}

            result, took = _elapsed(lambda: second.get("k", never, db=db))
            self.assertTrue(result.stale)
            self.assertEqual(result.payload["v"], "persisted")
            self.assertLess(took, 0.2)
            self.assertTrue(second.wait_idle(3))


def _live_settings(url: str = "http://tunarr.test") -> SimpleNamespace:
    return SimpleNamespace(
        features=SimpleNamespace(live_channels_enabled=True),
        tunarr=SimpleNamespace(url=url),
    )


def _guide(ts: float, *, title_now: str = "Now Show") -> dict:
    return {
        "enabled": True,
        "ready": True,
        "count": 1,
        "generated_at": ts,
        "reason": "",
        "channels": [
            {
                "id": "c1",
                "name": "One",
                "number": 1,
                "now": None,
                "next": None,
                "programs": [
                    {
                        "title": title_now,
                        "start": ts - 600,
                        "stop": ts + 600,
                        "duration_seconds": 1200,
                        "is_flex": False,
                    },
                    {
                        "title": "Later Show",
                        "start": ts + 600,
                        "stop": ts + 2400,
                        "duration_seconds": 1800,
                        "is_flex": False,
                    },
                ],
            }
        ],
    }


class LiveGuideSwrTests(unittest.TestCase):
    def setUp(self) -> None:
        from projectionist.live_channels import guide_cache

        guide_cache.GUIDE_CACHE.clear()
        guide_cache.ON_NOW_CACHE.clear()
        self.gc = guide_cache

    def test_cold_guide_returns_warming_quickly_when_tunarr_hangs(self) -> None:
        def hang(*_a, **_k):
            time.sleep(0.6)
            return _guide(time.time())

        with patch("projectionist.live_channels.guide.build_guide_snapshot", side_effect=hang):
            snap, took = _elapsed(
                lambda: self.gc.get_guide_snapshot(_live_settings(), cold_wait=0.0)
            )
        self.assertTrue(snap["warming"])
        self.assertFalse(snap["ready"])
        self.assertLess(took, 0.25)
        self.gc.GUIDE_CACHE.wait_idle(3)

    def test_default_cold_wait_does_not_block_on_hung_tunarr(self) -> None:
        """The live guide request path must not sit on a slow Tunarr build."""

        def hang(*_a, **_k):
            time.sleep(1.5)
            return _guide(time.time())

        with patch("projectionist.live_channels.guide.build_guide_snapshot", side_effect=hang):
            snap, took = _elapsed(lambda: self.gc.get_guide_snapshot(_live_settings()))
        self.assertTrue(snap["warming"])
        self.assertFalse(snap["ready"])
        self.assertLess(took, 0.25)
        self.gc.GUIDE_CACHE.wait_idle(3)

    def test_durable_guide_paints_while_refresh_hangs(self) -> None:
        from projectionist.library.db import Database

        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "guide.db")
            settings = _live_settings()
            key = self.gc._cache_key(settings, youth_max_rating=None, extra="guide|h=6.0")
            self.gc.GUIDE_CACHE.put(key, _guide(time.time()), db=db)
            self.gc.GUIDE_CACHE.clear()

            def hang(*_a, **_k):
                time.sleep(1.5)
                return _guide(time.time(), title_now="Fresh")

            with patch("projectionist.live_channels.guide.build_guide_snapshot", side_effect=hang):
                snap, took = _elapsed(
                    lambda: self.gc.get_guide_snapshot(settings, db=db)
                )
        self.assertLess(took, 0.25)
        self.assertTrue(snap["ready"])
        self.assertTrue(snap["stale"])
        self.assertEqual(snap["channels"][0]["now"]["title"], "Now Show")
        self.gc.GUIDE_CACHE.wait_idle(3)

    def test_stale_guide_never_waits_on_tunarr_and_rebases_now(self) -> None:
        ts = time.time()
        settings = _live_settings()
        key = self.gc._cache_key(settings, youth_max_rating=None, extra="guide|h=6.0")
        # Built 15 minutes ago: "Now Show" ended, "Later Show" is on now.
        past = ts - 900
        self.gc.GUIDE_CACHE.put(key, _guide(past))
        self.gc.GUIDE_CACHE.invalidate()

        def hang(*_a, **_k):
            time.sleep(0.5)
            return _guide(time.time(), title_now="Fresh")

        with patch("projectionist.live_channels.guide.build_guide_snapshot", side_effect=hang):
            snap, took = _elapsed(lambda: self.gc.get_guide_snapshot(settings))
        self.assertLess(took, 0.25)
        self.assertTrue(snap["stale"])
        row = snap["channels"][0]
        self.assertEqual(row["now"]["title"], "Later Show")
        self.assertIsNone(row["next"])
        self.assertGreaterEqual(row["now"]["percent"], 0)
        self.gc.GUIDE_CACHE.wait_idle(3)

    def test_unreachable_tunarr_does_not_replace_good_guide(self) -> None:
        ts = time.time()
        settings = _live_settings()
        key = self.gc._cache_key(settings, youth_max_rating=None, extra="guide|h=6.0")
        self.gc.GUIDE_CACHE.put(key, _guide(ts))
        self.gc.GUIDE_CACHE.invalidate()
        down = {
            "enabled": True,
            "ready": False,
            "channels": [],
            "count": 0,
            "reason": "tunarr_unreachable",
            "error": "boom",
        }
        with patch("projectionist.live_channels.guide.build_guide_snapshot", return_value=down):
            self.gc.get_guide_snapshot(settings)
            self.gc.GUIDE_CACHE.wait_idle(3)
            kept = self.gc.get_guide_snapshot(settings)
        self.assertTrue(kept["ready"])
        self.assertEqual(kept["channels"][0]["now"]["title"], "Now Show")

    def test_disabled_and_unconfigured_are_instant_and_uncached(self) -> None:
        off = SimpleNamespace(
            features=SimpleNamespace(live_channels_enabled=False),
            tunarr=SimpleNamespace(url=""),
        )
        self.assertEqual(self.gc.get_guide_snapshot(off)["reason"], "live_channels_disabled")
        nourl = _live_settings(url="")
        self.assertEqual(self.gc.get_on_now_snapshot(nourl)["reason"], "tunarr_url_missing")

    def test_rebase_matches_builder_when_not_stale(self) -> None:
        ts = time.time()
        guide = _guide(ts)
        rebased = self.gc.rebase_snapshot_to_now(guide, now=ts)
        row = rebased["channels"][0]
        self.assertEqual(row["now"]["title"], "Now Show")
        self.assertEqual(row["next"]["title"], "Later Show")
        self.assertAlmostEqual(row["now"]["percent"], 50.0, delta=1.0)


class AdminLiveStatusSwrTests(unittest.TestCase):
    def setUp(self) -> None:
        from projectionist.live_channels import status_cache

        status_cache.STATUS_CACHE.clear()
        status_cache.CRAFT_CACHE.clear()
        self.sc = status_cache

    def test_stale_status_is_instant_and_job_overlay_is_live(self) -> None:
        settings = _live_settings()
        key = self.sc._key(settings)
        self.sc.STATUS_CACHE.put(key, {"live_channels_enabled": True, "job": {"busy": False}, "v": 1})
        self.sc.STATUS_CACHE.invalidate()

        def slow(_settings):
            time.sleep(0.5)
            return {"live_channels_enabled": True, "job": {"busy": False}, "v": 2}

        with (
            patch.object(self.sc, "build_live_channels_status", side_effect=slow),
            patch.object(self.sc, "_live_job_snapshot", return_value={"busy": True}),
        ):
            out, took = _elapsed(lambda: self.sc.get_live_channels_status(settings, None))
        self.assertLess(took, 0.25)
        self.assertTrue(out["stale"])
        self.assertEqual(out["v"], 1)
        self.assertEqual(out["job"], {"busy": True})
        self.sc.STATUS_CACHE.wait_idle(3)

    def test_cold_status_returns_probe_free_skeleton_fast(self) -> None:
        from projectionist.config_store import Settings

        settings = Settings()
        settings.features.live_channels_enabled = True
        settings.tunarr.url = "http://10.255.255.1:8000"
        settings.tunarr.docker_orchestration = True

        def hang(_settings):
            time.sleep(0.6)
            return {"live_channels_enabled": True}

        with patch.object(self.sc, "build_live_channels_status", side_effect=hang) as build:
            out, took = _elapsed(
                lambda: self.sc.get_live_channels_status(settings, None, cold_wait=0.0)
            )
        self.assertTrue(out["warming"])
        self.assertEqual(out["tunarr"]["url"], "http://10.255.255.1:8000")
        self.assertTrue(out["tunarr"]["reachability"].get("checking"))
        # Warming must not call the probe builder on the request path.
        self.assertLess(took, 0.25)
        self.sc.STATUS_CACHE.wait_idle(3)
        self.assertEqual(build.call_count, 1)  # background only


class JourneySwrTests(unittest.TestCase):
    def setUp(self) -> None:
        from projectionist.journey import exploration

        exploration.JOURNEY_CACHE.clear()
        self.ex = exploration

    def test_journey_request_path_is_read_only(self) -> None:
        from projectionist.library.db import Database

        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "j.db")
            with patch("projectionist.engagement.sync_review_challenges") as sync:
                body = self.ex.journey_exploration(db, user_id="u1")
                self.ex.get_journey_exploration(db, user_id="u1", cold_wait=1.0)
            sync.assert_not_called()
            self.assertIn("courses", body)
            self.assertIn("explainers", body)

    def test_stale_journey_serves_instantly_while_rails_rebuild(self) -> None:
        from projectionist.library.db import Database

        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "j.db")
            self.ex.prewarm_journey(db)
            self.ex.invalidate_journey_cache()

            def slow(_db, **_k):
                time.sleep(0.4)
                return self.ex._warming_rails()

            with patch.object(self.ex, "journey_library_rails", side_effect=slow):
                body, took = _elapsed(
                    lambda: self.ex.get_journey_exploration(db, user_id="u1")
                )
            self.assertLess(took, 0.25)
            self.assertTrue(body["stale"])
            self.assertFalse(body["warming"])
            self.ex.JOURNEY_CACHE.wait_idle(3)

    def test_cold_journey_warms_instead_of_hanging(self) -> None:
        from projectionist.library.db import Database

        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "j.db")

            def slow(_db, **_k):
                time.sleep(0.5)
                return self.ex._warming_rails()

            with patch.object(self.ex, "journey_library_rails", side_effect=slow):
                body, took = _elapsed(
                    lambda: self.ex.get_journey_exploration(db, user_id="u1", cold_wait=0.0)
                )
            self.assertTrue(body["warming"])
            self.assertLess(took, 0.25)
            self.ex.JOURNEY_CACHE.wait_idle(3)

    def test_journey_rails_survive_restart_via_sync_state(self) -> None:
        from projectionist.journey.exploration import SwrCache
        from projectionist.library.db import Database

        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "j.db")
            self.ex.prewarm_journey(db)
            # Simulate a fresh process: drop memory, keep sync_state.
            self.ex.JOURNEY_CACHE.clear()
            self.assertIsInstance(self.ex.JOURNEY_CACHE, SwrCache)

            def slow(_db, **_k):
                time.sleep(0.4)
                return self.ex._warming_rails()

            with patch.object(self.ex, "journey_library_rails", side_effect=slow):
                body, took = _elapsed(
                    lambda: self.ex.get_journey_exploration(db, user_id="u1")
                )
            self.assertTrue(body["stale"])
            self.assertLess(took, 0.25)
            self.ex.JOURNEY_CACHE.wait_idle(3)


class AdminLifecycleSwrTests(unittest.TestCase):
    def setUp(self) -> None:
        from projectionist.live_channels import lifecycle_progress as lp

        lp.reset_progress_for_tests()
        self.lp = lp

    def test_cold_lifecycle_status_is_instant_while_probes_hang(self) -> None:
        settings = SimpleNamespace(
            tunarr=SimpleNamespace(
                url="http://tunarr.test:8000",
                docker_orchestration=True,
            )
        )

        def hang(_settings):
            time.sleep(0.6)
            return {
                "phase": "ready",
                "percent": 100,
                "message": "Tunarr is ready",
                "ready": True,
                "busy": False,
                "ok": True,
                "error": "",
                "container_id": "abc",
                "container_name": "tunarr",
                "http_ready": True,
                "logs_ready": True,
                "container_running": True,
                "still_starting": False,
                "tunarr_url": "http://tunarr.test:8000",
                "determinate": True,
                "updated_at": time.time(),
            }

        with patch.object(self.lp, "build_lifecycle_status", side_effect=hang):
            out, took = _elapsed(
                lambda: self.lp.get_lifecycle_status(settings, cold_wait=0.0)
            )
        self.assertTrue(out["warming"])
        self.assertLess(took, 0.25)
        self.assertFalse(out["http_ready"])
        self.lp.LIFECYCLE_CACHE.wait_idle(3)

    def test_stale_lifecycle_serves_while_refresh_hangs(self) -> None:
        settings = SimpleNamespace(
            tunarr=SimpleNamespace(
                url="http://tunarr.test:8000",
                docker_orchestration=True,
            )
        )
        key = self.lp._lifecycle_cache_key(settings)
        self.lp.LIFECYCLE_CACHE.put(
            key,
            {
                "phase": "ready",
                "percent": 100,
                "message": "Tunarr is ready",
                "ready": True,
                "busy": False,
                "ok": True,
                "error": "",
                "container_id": "old",
                "container_name": "tunarr",
                "http_ready": True,
                "logs_ready": True,
                "container_running": True,
                "still_starting": False,
                "tunarr_url": "http://tunarr.test:8000",
                "determinate": True,
                "updated_at": time.time(),
            },
        )
        self.lp.LIFECYCLE_CACHE.invalidate()

        def hang(_settings):
            time.sleep(0.5)
            return {
                "phase": "ready",
                "percent": 100,
                "message": "Tunarr is ready",
                "ready": True,
                "busy": False,
                "ok": True,
                "error": "",
                "container_id": "new",
                "container_name": "tunarr",
                "http_ready": True,
                "logs_ready": True,
                "container_running": True,
                "still_starting": False,
                "tunarr_url": "http://tunarr.test:8000",
                "determinate": True,
                "updated_at": time.time(),
            }

        with patch.object(self.lp, "build_lifecycle_status", side_effect=hang):
            out, took = _elapsed(lambda: self.lp.get_lifecycle_status(settings))
        self.assertLess(took, 0.25)
        self.assertTrue(out["stale"])
        self.assertEqual(out["container_id"], "old")
        self.lp.LIFECYCLE_CACHE.wait_idle(3)
        refreshed = self.lp.get_lifecycle_status(settings)
        self.assertEqual(refreshed["container_id"], "new")

    def test_busy_progress_store_overlays_stale_probe_payload(self) -> None:
        settings = SimpleNamespace(
            tunarr=SimpleNamespace(
                url="http://tunarr.test:8000",
                docker_orchestration=True,
            )
        )
        key = self.lp._lifecycle_cache_key(settings)
        self.lp.LIFECYCLE_CACHE.put(
            key,
            {
                "phase": "idle",
                "percent": 0,
                "message": "Ready when you are",
                "ready": False,
                "busy": False,
                "ok": True,
                "error": "",
                "container_id": "",
                "container_name": "tunarr",
                "http_ready": False,
                "logs_ready": False,
                "container_running": False,
                "still_starting": False,
                "tunarr_url": "http://tunarr.test:8000",
                "determinate": True,
                "updated_at": time.time(),
            },
        )
        self.lp.progress_store().begin(container_name="tunarr-proj")
        self.lp.progress_store().set_phase("waiting_ready", "Waiting for Tunarr HTTP", percent=80)

        def hang(_settings):
            time.sleep(0.4)
            return {
                "phase": "waiting_ready",
                "percent": 85,
                "message": "Waiting",
                "ready": False,
                "busy": True,
                "ok": True,
                "error": "",
                "container_id": "abc",
                "container_name": "tunarr-proj",
                "http_ready": False,
                "logs_ready": False,
                "container_running": True,
                "still_starting": True,
                "tunarr_url": "http://tunarr.test:8000",
                "determinate": True,
                "updated_at": time.time(),
            }

        with patch.object(self.lp, "build_lifecycle_status", side_effect=hang):
            out, took = _elapsed(lambda: self.lp.get_lifecycle_status(settings))
        self.assertLess(took, 0.25)
        self.assertTrue(out["busy"])
        self.assertEqual(out["phase"], "waiting_ready")
        self.assertEqual(out["percent"], 80)
        self.lp.LIFECYCLE_CACHE.wait_idle(3)


class LibraryDerivedCachesTests(unittest.TestCase):
    def test_coverage_and_health_do_not_recompute_on_request_path(self) -> None:
        from projectionist.library import derived_caches as dc
        from projectionist.library.db import Database

        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "d.db")
            dc.COVERAGE_CACHE.clear()
            dc.HEALTH_CACHE.clear()
            dc.rebuild_after_library_change(db)
            dc.COVERAGE_CACHE.invalidate()
            dc.HEALTH_CACHE.invalidate()

            def slow(_db):
                time.sleep(0.4)
                return {"slow": True}

            with (
                patch("projectionist.library.query.compute_knowledge_coverage", side_effect=slow),
                patch("projectionist.library.health.compute_library_health", side_effect=slow),
            ):
                cov, t1 = _elapsed(lambda: dc.get_knowledge_coverage(db))
                health, t2 = _elapsed(lambda: dc.get_library_health(db))
            self.assertLess(t1, 0.25)
            self.assertLess(t2, 0.25)
            self.assertTrue(cov["stale"])
            self.assertTrue(health["stale"])
            self.assertNotIn("slow", cov)
            dc.COVERAGE_CACHE.wait_idle(3)
            dc.HEALTH_CACHE.wait_idle(3)


class PlexIdentityNegativeCacheTests(unittest.TestCase):
    def test_failed_identity_lookup_is_not_retried_on_every_request(self) -> None:
        from projectionist.connectors import plex

        plex._cached_plex_identity = None
        plex._plex_identity_failed = None
        calls = {"n": 0}

        def boom(self_):
            calls["n"] += 1
            raise OSError("plex down")

        try:
            with patch.object(plex.PlexClient, "server_identity", boom):
                for _ in range(4):
                    self.assertEqual(plex.cached_plex_identity("http://plex.test", "tok"), ("", ""))
            self.assertEqual(calls["n"], 1)
        finally:
            plex._cached_plex_identity = None
            plex._plex_identity_failed = None


if __name__ == "__main__":
    unittest.main()
