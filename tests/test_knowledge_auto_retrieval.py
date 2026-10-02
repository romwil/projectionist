"""Missing-but-fetchable knowledge is backlog, not an Admin exception.

Covers the Admin → Library knowledge contract:

* a missing plot is fetched by the scheduled pass, with no button;
* only retrieval that was *tried and failed* becomes an exception;
* batch caps / backoff / the breaker keep a big library from stampeding upstream.
"""

from __future__ import annotations

import asyncio
import json
import tempfile
import time
import unittest
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

from projectionist.config_store import Settings
from projectionist.library import knowledge_fetch as kf
from projectionist.library.db import Database
from projectionist.scheduler.tasks import (
    coverage_deficit_audit,
    long_synopsis_enrichment,
    metadata_enrichment,
)
from projectionist.scheduler.tasks.coverage_deficit_audit import CoverageDeficitAudit
from projectionist.web import augmentation_routes as aug_routes

SYN = "projectionist.scheduler.tasks.long_synopsis_enrichment"
META = "projectionist.scheduler.tasks.metadata_enrichment"


def _run(coro):
    return asyncio.run(coro)


class _Base(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self._tmp.name) / "lib.db")

    def tearDown(self) -> None:
        self.db.close()
        self._tmp.cleanup()

    def add_movie(self, n: int, **extra: Any) -> int:
        return self.db.upsert_library_item(
            {
                "rating_key": f"rk{n}",
                "media_type": "movie",
                "title": f"Film {n}",
                "year": 2000 + (n % 20),
                **extra,
            }
        )

    def synopsis_run(self, fetch: Any, *, batch: int | None = None) -> Dict[str, Any]:
        size = batch if batch is not None else long_synopsis_enrichment.DEFAULT_BATCH_SIZE
        with patch(f"{SYN}.fetch_extract", side_effect=fetch), patch(
            f"{SYN}.asyncio.sleep", new=AsyncMock()
        ), patch(f"{SYN}.resolve_batch_size", return_value=size):
            return _run(
                long_synopsis_enrichment.run(
                    self.db, Settings(long_synopsis_source="wikipedia"), lambda: False
                )
            )

    def audit(self) -> Dict[str, Any]:
        return _run(coverage_deficit_audit.run(self.db, Settings(), lambda: False))

    def pending(self) -> List[Dict[str, Any]]:
        return self.db.list_staged_augmentations(
            status="pending", task_name=coverage_deficit_audit.TASK_NAME
        )

    def make_retryable(self) -> None:
        """Fast-forward every backoff window (test clock)."""
        with self.db.connect() as conn:
            conn.execute("UPDATE knowledge_fetch_state SET next_retry_at = 0 WHERE exhausted = 0")


class MissingPlotAutoFetchTests(_Base):
    def test_missing_plot_is_fetched_without_the_button(self) -> None:
        ids = [self.add_movie(i, summary="Short.") for i in range(3)]
        result = self.synopsis_run(lambda title, **_: f"Plot of {title}.")
        self.assertEqual(result["enriched"], 3)
        for item_id in ids:
            self.assertTrue(self.db.library_item_by_id(item_id)["long_synopsis"])
        # Nothing was ever an exception.
        self.audit()
        self.assertEqual(self.pending(), [])
        self.assertEqual(kf.list_exhausted(self.db), [])

    def test_not_fetched_yet_is_not_an_exception(self) -> None:
        # Two telemetry sightings used to be enough to park a title as an exception.
        item_id = self.add_movie(1)
        self.db.upsert_closed_loop_event(
            event_type="coverage_deficit",
            priority_tier="P2",
            entity_type="library_item",
            entity_key=str(item_id),
            payload_json=json.dumps({"deficit_kind": "synopsis", "title": "Film 1"}),
        )
        self.db.upsert_closed_loop_event(
            event_type="coverage_deficit",
            priority_tier="P2",
            entity_type="library_item",
            entity_key=str(item_id),
            payload_json=json.dumps({"deficit_kind": "synopsis", "title": "Film 1"}),
        )
        stats = self.audit()
        self.assertEqual(stats["staged"], 0)
        self.assertEqual(self.pending(), [])

    def test_legacy_pending_backlog_rows_are_resolved(self) -> None:
        unfetched = self.add_movie(1)
        filled = self.add_movie(2)
        self.db.set_long_synopsis(filled, "Already here.", "wikipedia")
        legacy = [
            self.db.insert_staged_augmentation(
                task_name="coverage_deficit_audit",
                priority_tier="P2",
                target_entity_type="library_item",
                target_entity_id=str(item_id),
                candidate_data_json=json.dumps({"deficit_kind": kind}),
                confidence_score=0.7,
            )
            for item_id, kind in ((unfetched, "synopsis"), (filled, "synopsis"), (unfetched, "motif"))
        ]
        keyword = self.db.insert_staged_augmentation(
            task_name="coverage_deficit_audit",
            priority_tier="P1",
            target_entity_type="keyword",
            target_entity_id="obscure",
            candidate_data_json=json.dumps({"deficit_kind": "theme_keyword"}),
            confidence_score=0.7,
        )
        stats = self.audit()
        self.assertEqual(stats["resolved"], 3)
        for row_id in legacy:
            self.assertEqual(self.db.get_staged_augmentation(row_id)["status"], "resolved")
        # A theme keyword still needs a human mapping.
        self.assertEqual(self.db.get_staged_augmentation(keyword)["status"], "pending")

    def test_motif_gaps_are_never_exceptions(self) -> None:
        from projectionist.scheduler.tasks.coverage_signals import emit_motif_deficit_signals

        self.add_movie(1, summary="A plot with words but no shared motifs.")
        self.assertEqual(emit_motif_deficit_signals(self.db), 0)


class HardFailureStaysAnExceptionTests(_Base):
    def test_synopsis_misses_back_off_then_exhaust_then_surface(self) -> None:
        item_id = self.add_movie(1)

        first = self.synopsis_run(lambda *a, **k: "")
        self.assertEqual(first["misses"], 1)
        # Backing off, not yet an exception.
        self.assertFalse(kf.get_state(self.db, item_id, kf.KIND_SYNOPSIS)["exhausted"])
        self.assertEqual(self.synopsis_run(lambda *a, **k: "")["enriched"], 0)  # parked: not retried
        self.audit()
        self.assertEqual(self.pending(), [])

        for _ in range(kf.MAX_MISS_ATTEMPTS - 1):
            self.make_retryable()
            self.synopsis_run(lambda *a, **k: "")
        state = kf.get_state(self.db, item_id, kf.KIND_SYNOPSIS)
        self.assertTrue(state["exhausted"])
        self.assertEqual(state["attempts"], kf.MAX_MISS_ATTEMPTS)

        stats = self.audit()
        self.assertEqual(stats["staged"], 1)
        rows = self.pending()
        self.assertEqual(len(rows), 1)
        candidate = json.loads(rows[0]["candidate_data_json"])
        self.assertEqual(candidate["deficit_kind"], "synopsis")
        self.assertTrue(candidate["retrieval_exhausted"])
        self.assertEqual(candidate["failure"], "miss")
        # Re-auditing does not duplicate it.
        self.assertEqual(self.audit()["staged"], 0)

    def test_tmdb_unknown_id_is_a_hard_failure_exception(self) -> None:
        item_id = self.add_movie(1, tmdb_id=999999)
        fake = MagicMock()
        fake.movie_details.side_effect = RuntimeError(
            "HTTP 404 from https://api.themoviedb.org/3/movie/999999: not found"
        )
        with patch(f"{META}.TMDBClient", return_value=fake), patch(
            f"{META}.asyncio.sleep", new=AsyncMock()
        ):
            result = _run(
                metadata_enrichment.run(self.db, Settings(tmdb_api_key="k"), lambda: False)
            )
        self.assertEqual(result["exhausted"], 1)
        state = kf.get_state(self.db, item_id, kf.KIND_METADATA)
        self.assertTrue(state["exhausted"])
        self.assertEqual(state["last_outcome"], kf.OUTCOME_HARD)

        self.assertEqual(self.audit()["staged"], 1)
        candidate = json.loads(self.pending()[0]["candidate_data_json"])
        self.assertEqual(candidate["deficit_kind"], "metadata")
        self.assertIn("404", candidate["failure_detail"])

    def test_gap_that_closes_drops_off_the_exception_list(self) -> None:
        item_id = self.add_movie(1)
        for _ in range(kf.MAX_MISS_ATTEMPTS):
            self.make_retryable()
            self.synopsis_run(lambda *a, **k: "")
        self.audit()
        self.assertEqual(len(self.pending()), 1)
        self.db.set_long_synopsis(item_id, "Found elsewhere.", "wikipedia")
        stats = self.audit()
        self.assertEqual(stats["resolved"], 1)
        self.assertEqual(self.pending(), [])

    def test_dismissed_exception_stays_dismissed_until_it_fails_again(self) -> None:
        item_id = self.add_movie(1)
        for _ in range(kf.MAX_MISS_ATTEMPTS):
            self.make_retryable()
            self.synopsis_run(lambda *a, **k: "")
        self.audit()
        row = self.pending()[0]
        time.sleep(0.01)
        self.db.update_staged_augmentation_status(int(row["id"]), status="rejected")
        self.assertEqual(self.audit()["staged"], 0)
        self.assertEqual(self.pending(), [])
        self.assertIsNotNone(kf.get_state(self.db, item_id, kf.KIND_SYNOPSIS))


class BatchAndRampTests(_Base):
    def test_batch_cap_bounds_upstream_calls_for_a_huge_gap(self) -> None:
        for i in range(200):
            self.add_movie(i)
        calls: List[str] = []

        def fetch(title: str, **_: Any) -> str:
            calls.append(title)
            return f"Plot {title}"

        result = self.synopsis_run(fetch, batch=7)
        self.assertEqual(len(calls), 7)
        self.assertEqual(result["enriched"], 7)
        self.assertTrue(result["has_more"])
        # The next run continues where the last stopped; nothing is fetched twice.
        self.synopsis_run(fetch, batch=7)
        self.assertEqual(len(calls), 14)
        self.assertEqual(len(set(calls)), 14)

    def test_default_batch_is_small_when_unconfigured(self) -> None:
        for i in range(60):
            self.add_movie(i)
        calls: List[str] = []
        self.synopsis_run(lambda title, **_: calls.append(title) or "x")
        self.assertLessEqual(len(calls), long_synopsis_enrichment.DEFAULT_BATCH_SIZE)

    def test_stubborn_titles_cannot_starve_the_queue(self) -> None:
        # Oldest 10 have no Wikipedia page; the rest must still get their turn.
        for i in range(25):
            self.add_movie(i)
        seen: List[str] = []

        def fetch(title: str, **_: Any) -> str:
            seen.append(title)
            return "" if int(title.split()[-1]) < 10 else f"Plot {title}"

        self.synopsis_run(fetch, batch=10)
        seen.clear()
        second = self.synopsis_run(fetch, batch=10)
        self.assertEqual(second["enriched"], 10)
        self.assertTrue(all(int(t.split()[-1]) >= 10 for t in seen))

    def test_tiny_library_fills_in_one_pass(self) -> None:
        for i in range(2):
            self.add_movie(i)
        self.assertEqual(self.synopsis_run(lambda t, **_: "plot")["enriched"], 2)
        self.assertEqual(self.db.count_items_needing_long_synopsis(), 0)

    def test_outage_trips_breaker_and_blames_no_title(self) -> None:
        for i in range(40):
            self.add_movie(i)
        calls: List[str] = []

        def down(title: str, **_: Any) -> str:
            calls.append(title)
            raise RuntimeError("Timeout requesting https://en.wikipedia.org/w/api.php")

        result = self.synopsis_run(down, batch=30)
        self.assertTrue(result["breaker_tripped"])
        self.assertEqual(len(calls), kf.BREAKER_THRESHOLD)  # stopped, not 30 calls
        self.assertEqual(kf.list_exhausted(self.db), [])
        # Held briefly, but no strike counted.
        for item_id in kf.parked_ids(self.db, kf.KIND_SYNOPSIS):
            self.assertEqual(kf.get_state(self.db, item_id, kf.KIND_SYNOPSIS)["attempts"], 0)
        self.audit()
        self.assertEqual(self.pending(), [])

    def test_rejected_credentials_stop_immediately_without_blaming_titles(self) -> None:
        for i in range(10):
            self.add_movie(i)
        calls: List[str] = []

        def rejected(title: str, **_: Any) -> str:
            calls.append(title)
            raise RuntimeError("HTTP 401 from https://www.omdbapi.com: Invalid API key")

        result = self.synopsis_run(rejected, batch=10)
        self.assertEqual(len(calls), 1)
        self.assertTrue(result["breaker_tripped"])
        self.assertEqual(kf.list_exhausted(self.db), [])


class LedgerPolicyTests(unittest.TestCase):
    def test_backoff_is_monotonic_and_exhausts(self) -> None:
        for outcome, limit in (
            (kf.OUTCOME_MISS, kf.MAX_MISS_ATTEMPTS),
            (kf.OUTCOME_ERROR, kf.MAX_ERROR_ATTEMPTS),
        ):
            last = 0
            for attempt in range(1, limit + 1):
                delay, exhausted = kf.backoff_for(outcome, attempt)
                self.assertGreaterEqual(delay, last)
                last = delay
                self.assertEqual(exhausted, attempt == limit)
        self.assertTrue(kf.backoff_for(kf.OUTCOME_HARD, 1)[1])

    def test_exhausted_titles_get_one_automatic_recheck_later(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "lib.db")
            item_id = db.upsert_library_item(
                {"rating_key": "a", "media_type": "movie", "title": "Rare"}
            )
            kf.record_failure(db, item_id, kf.KIND_SYNOPSIS, kf.OUTCOME_HARD, "x", now=1000.0)
            self.assertEqual(db.items_needing_long_synopsis(limit=5, now=1001.0), [])
            later = 1000.0 + kf.EXHAUSTED_RECHECK_SECONDS + 5
            self.assertEqual(len(db.items_needing_long_synopsis(limit=5, now=later)), 1)
            db.close()


class OwnerRetryTests(_Base):
    def setUp(self) -> None:
        super().setUp()
        aug_routes._db_factory = lambda: self.db
        aug_routes._data_dir = Path(self._tmp.name)
        aug_routes._settings_factory = lambda: Settings(long_synopsis_source="wikipedia")
        aug_routes._scheduler_trigger = lambda name: {"status": "started", "task": name}

    def tearDown(self) -> None:
        aug_routes._db_factory = None
        aug_routes._data_dir = None
        aug_routes._settings_factory = None
        aug_routes._scheduler_trigger = None
        super().tearDown()

    def _exhaust_and_stage(self) -> tuple[int, int]:
        item_id = self.add_movie(1)
        for _ in range(kf.MAX_MISS_ATTEMPTS):
            self.make_retryable()
            self.synopsis_run(lambda *a, **k: "")
        self.audit()
        return item_id, int(self.pending()[0]["id"])

    def test_try_again_now_success_clears_the_exception(self) -> None:
        item_id, row_id = self._exhaust_and_stage()
        with patch("projectionist.web.staged_augmentation_promote._fetch_for_row",
                   return_value=("Finally found.", "wikipedia")):
            result = _run(aug_routes.approve_staged_augmentation(row_id, user={"role": "owner"}))
        self.assertEqual(result["acted"]["action"], "synopsis_written")
        self.assertIsNone(kf.get_state(self.db, item_id, kf.KIND_SYNOPSIS))
        self.assertEqual(self.audit()["staged"], 0)

    def test_try_again_now_failure_stays_visible_but_does_not_reappear_instantly(self) -> None:
        item_id, row_id = self._exhaust_and_stage()
        time.sleep(0.01)
        with patch("projectionist.web.staged_augmentation_promote._fetch_for_row",
                   return_value=("", "")):
            result = _run(aug_routes.approve_staged_augmentation(row_id, user={"role": "owner"}))
        self.assertEqual(result["acted"]["action"], "synopsis_miss")
        self.assertTrue(kf.get_state(self.db, item_id, kf.KIND_SYNOPSIS)["exhausted"])
        # Owner just retried; the same failure is not re-listed on the next audit.
        self.assertEqual(self.audit()["staged"], 0)
        self.assertEqual(self.pending(), [])

    def test_audit_signal_for_unexhausted_gap_is_skipped(self) -> None:
        item_id = self.add_movie(1)
        task = CoverageDeficitAudit(self.db, min_hit_count=1)
        out = _run(
            task.process_signal(
                {
                    "entity_type": "library_item",
                    "entity_key": str(item_id),
                    "hit_count": 50,
                    "payload_json": json.dumps({"deficit_kind": "synopsis"}),
                }
            )
        )
        self.assertIsNone(out)


if __name__ == "__main__":
    unittest.main()
