"""Value-based validation tests for Database query methods.

These tests seed known data into real SQLite databases and verify ACTUAL
returned values — not just structural presence. Covers aggregation,
joins, date windows, ordering, filtering, and cosine similarity ranking.
"""

import json
import math
import tempfile
import time
import unittest
import uuid
from pathlib import Path
from typing import Any, Dict, List

from curatorx.library.db import DEFAULT_CONTEXT_HASH, DEFAULT_LENS_ID, Database
from curatorx.library.embeddings import cosine_similarity, semantic_search


def _make_db() -> tuple:
    """Create a temporary directory and Database. Returns (tmpdir, db)."""
    tmp = tempfile.mkdtemp()
    db = Database(Path(tmp) / "test.db")
    return tmp, db


def _seed_library(db: Database, items: list[dict]) -> None:
    for item in items:
        db.upsert_library_item(item)


# ---------------------------------------------------------------------------
# telemetry_summary — aggregation correctness
# ---------------------------------------------------------------------------


class TestTelemetrySummary(unittest.TestCase):
    """Verify telemetry_summary groups and counts events correctly."""

    def test_counts_grouped_by_event_class(self):
        """Seed telemetry events with known classes, verify exact counts."""
        _, db = _make_db()
        db.insert_telemetry_event(
            event_id="e1", event_class="library_sync", payload_json="{}"
        )
        db.insert_telemetry_event(
            event_id="e2", event_class="library_sync", payload_json="{}"
        )
        db.insert_telemetry_event(
            event_id="e3", event_class="library_sync", payload_json="{}"
        )
        db.insert_telemetry_event(
            event_id="e4", event_class="chat_message", payload_json="{}"
        )
        db.insert_telemetry_event(
            event_id="e5", event_class="arr_queue", payload_json="{}"
        )
        db.insert_telemetry_event(
            event_id="e6", event_class="arr_queue", payload_json="{}"
        )

        result = db.telemetry_summary(hours=24)

        self.assertEqual(result["library_sync"], 3)
        self.assertEqual(result["chat_message"], 1)
        self.assertEqual(result["arr_queue"], 2)
        self.assertEqual(len(result), 3)

    def test_empty_telemetry_returns_empty_dict(self):
        """No events should produce an empty dict."""
        _, db = _make_db()
        result = db.telemetry_summary(hours=24)
        self.assertEqual(result, {})

    def test_old_events_excluded_by_window(self):
        """Manually backdated events should be excluded by a narrow window.

        We insert an event with CURRENT_TIMESTAMP (always 'now'), then manually
        update its timestamp to 48 hours ago. A 24-hour window should exclude it.
        """
        _, db = _make_db()
        db.insert_telemetry_event(
            event_id="old-evt", event_class="sync", payload_json="{}"
        )
        with db.connect() as conn:
            conn.execute(
                "UPDATE system_telemetry_stream SET timestamp = datetime('now', '-48 hours') WHERE id = ?",
                ("old-evt",),
            )

        result = db.telemetry_summary(hours=24)
        self.assertEqual(result, {})

        result_wide = db.telemetry_summary(hours=72)
        self.assertEqual(result_wide.get("sync"), 1)

    def test_duplicate_event_ids_ignored(self):
        """INSERT OR IGNORE means duplicate IDs are silently skipped."""
        _, db = _make_db()
        db.insert_telemetry_event(
            event_id="dup", event_class="sync", payload_json='{"a":1}'
        )
        db.insert_telemetry_event(
            event_id="dup", event_class="sync", payload_json='{"a":2}'
        )
        result = db.telemetry_summary(hours=24)
        self.assertEqual(result["sync"], 1)


# ---------------------------------------------------------------------------
# export_training_corpus — multi-table join, field mapping
# ---------------------------------------------------------------------------


class TestExportTrainingCorpus(unittest.TestCase):
    """Verify export_training_corpus collects all three tables correctly."""

    def test_export_includes_all_seeded_data(self):
        """Seed feedback, preferences, reviews and verify exact export content."""
        _, db = _make_db()

        session_id = "sess-1"
        db.ensure_chat_session(session_id)
        db.save_chat_message(
            session_id, "msg-1", "user", [{"type": "text", "content": "hello"}]
        )
        db.upsert_message_feedback(
            feedback_id="fb-1",
            message_id="msg-1",
            session_id=session_id,
            user_id=None,
            feedback_type="helpful",
            excerpt="great",
        )

        db.add_preference("genre_like", "I love sci-fi", weight=2.0)
        db.add_preference("director_like", "Nolan fan", weight=1.5)

        now = time.time()
        with db.connect() as conn:
            conn.execute(
                """
                INSERT INTO user_title_reviews
                    (id, rating_key, media_type, title, stars, review_text, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                ("rev-1", "rk-100", "movie", "Inception", 5, "Mind-bending", now, now),
            )

        result = db.export_training_corpus()

        self.assertIn("exported_at", result)
        self.assertIsInstance(result["exported_at"], float)

        self.assertEqual(len(result["message_feedback"]), 1)
        self.assertEqual(result["message_feedback"][0]["feedback_type"], "helpful")
        self.assertEqual(result["message_feedback"][0]["excerpt"], "great")

        self.assertEqual(len(result["preference_facts"]), 2)
        pref_texts = {p["text"] for p in result["preference_facts"]}
        self.assertEqual(pref_texts, {"I love sci-fi", "Nolan fan"})

        self.assertEqual(len(result["user_title_reviews"]), 1)
        self.assertEqual(result["user_title_reviews"][0]["title"], "Inception")
        self.assertEqual(result["user_title_reviews"][0]["stars"], 5)

    def test_export_empty_tables_returns_empty_lists(self):
        """All three tables empty should return empty lists."""
        _, db = _make_db()
        result = db.export_training_corpus()
        self.assertEqual(result["message_feedback"], [])
        self.assertEqual(result["preference_facts"], [])
        self.assertEqual(result["user_title_reviews"], [])

    def test_export_ordering_is_asc_by_created_at(self):
        """Items should be ordered by created_at ascending."""
        _, db = _make_db()
        db.add_preference("genre_like", "First pref")
        time.sleep(0.01)
        db.add_preference("genre_like", "Second pref")
        time.sleep(0.01)
        db.add_preference("genre_like", "Third pref")

        result = db.export_training_corpus()
        texts = [p["text"] for p in result["preference_facts"]]
        self.assertEqual(texts, ["First pref", "Second pref", "Third pref"])


# ---------------------------------------------------------------------------
# get_chat_thread / list_chat_threads — JSON reconstruction from rows
# ---------------------------------------------------------------------------


class TestChatThreads(unittest.TestCase):
    """Verify chat thread creation, retrieval, and listing."""

    def test_get_chat_thread_returns_correct_structure(self):
        """Created thread should have exact fields and values."""
        _, db = _make_db()
        sid = "thread-abc"
        db.create_chat_thread(sid, thread_title="Test Thread")

        thread = db.get_chat_thread(sid)

        self.assertIsNotNone(thread)
        self.assertEqual(thread["id"], sid)
        self.assertEqual(thread["thread_title"], "Test Thread")
        self.assertEqual(thread["message_count"], 0)
        self.assertEqual(thread["preview"], "")
        self.assertEqual(thread["lens_id"], DEFAULT_LENS_ID)
        self.assertEqual(thread["context_hash"], DEFAULT_CONTEXT_HASH)

    def test_get_chat_thread_message_count_and_preview(self):
        """After adding messages, message_count and preview should update."""
        _, db = _make_db()
        sid = "thread-msg"
        db.create_chat_thread(sid, thread_title="Counted Thread")
        db.save_chat_message(
            sid, "m1", "user", [{"type": "text", "content": "Hello world"}]
        )
        db.save_chat_message(
            sid, "m2", "assistant", [{"type": "text", "content": "Hi there"}]
        )
        db.save_chat_message(
            sid, "m3", "user", [{"type": "text", "content": "Last message here"}]
        )

        thread = db.get_chat_thread(sid)
        self.assertEqual(thread["message_count"], 3)
        self.assertEqual(thread["preview"], "Last message here")

    def test_get_chat_thread_nonexistent_returns_none(self):
        """Nonexistent session ID should return None."""
        _, db = _make_db()
        self.assertIsNone(db.get_chat_thread("does-not-exist"))

    def test_get_chat_thread_user_id_filtering(self):
        """Thread created by user_id='alice' should not be visible to 'bob'."""
        _, db = _make_db()
        db.create_chat_thread("t-alice", thread_title="Alice's Thread", user_id="alice")

        self.assertIsNotNone(db.get_chat_thread("t-alice", user_id="alice"))
        self.assertIsNone(db.get_chat_thread("t-alice", user_id="bob"))
        self.assertIsNotNone(db.get_chat_thread("t-alice"))

    def test_list_chat_threads_ordering(self):
        """Threads should be ordered by updated_at DESC."""
        _, db = _make_db()
        db.create_chat_thread("t-old", thread_title="Old Thread")
        time.sleep(0.02)
        db.create_chat_thread("t-mid", thread_title="Mid Thread")
        time.sleep(0.02)
        db.create_chat_thread("t-new", thread_title="New Thread")

        threads = db.list_chat_threads()

        self.assertEqual(len(threads), 3)
        self.assertEqual(threads[0]["thread_title"], "New Thread")
        self.assertEqual(threads[1]["thread_title"], "Mid Thread")
        self.assertEqual(threads[2]["thread_title"], "Old Thread")

    def test_list_chat_threads_with_messages_shows_counts(self):
        """Each listed thread should report its correct message_count."""
        _, db = _make_db()
        db.create_chat_thread("t1", thread_title="Thread One")
        db.save_chat_message("t1", "m1", "user", [{"type": "text", "content": "msg1"}])
        db.save_chat_message("t1", "m2", "assistant", [{"type": "text", "content": "reply"}])

        db.create_chat_thread("t2", thread_title="Thread Two")

        threads = db.list_chat_threads()
        thread_map = {t["id"]: t for t in threads}

        self.assertEqual(thread_map["t1"]["message_count"], 2)
        self.assertEqual(thread_map["t2"]["message_count"], 0)

    def test_list_chat_threads_limit(self):
        """Limit parameter should cap the number of returned threads."""
        _, db = _make_db()
        for i in range(10):
            db.create_chat_thread(f"t-{i}", thread_title=f"Thread {i}")
            time.sleep(0.005)

        threads = db.list_chat_threads(limit=3)
        self.assertEqual(len(threads), 3)

    def test_list_chat_threads_user_id_filter(self):
        """User ID filter should only return threads for that user."""
        _, db = _make_db()
        db.create_chat_thread("t-a", thread_title="Alice's", user_id="alice")
        db.create_chat_thread("t-b", thread_title="Bob's", user_id="bob")
        db.create_chat_thread("t-n", thread_title="No Owner")

        alice_threads = db.list_chat_threads(user_id="alice")
        self.assertEqual(len(alice_threads), 1)
        self.assertEqual(alice_threads[0]["thread_title"], "Alice's")

    def test_list_chat_threads_preview_from_last_message(self):
        """Preview should come from the last message's text block."""
        _, db = _make_db()
        db.create_chat_thread("t-prev", thread_title="Preview Test")
        db.save_chat_message(
            "t-prev", "m1", "user", [{"type": "text", "content": "First message"}]
        )
        db.save_chat_message(
            "t-prev",
            "m2",
            "assistant",
            [{"type": "text", "content": "This is the latest reply"}],
        )

        threads = db.list_chat_threads()
        self.assertEqual(threads[0]["preview"], "This is the latest reply")

    def test_default_thread_title(self):
        """Thread created without explicit title should get the default."""
        _, db = _make_db()
        db.create_chat_thread("t-default")
        thread = db.get_chat_thread("t-default")
        self.assertEqual(thread["thread_title"], "New conversation")


# ---------------------------------------------------------------------------
# preference_facts — filter and dedup logic
# ---------------------------------------------------------------------------


class TestPreferenceFacts(unittest.TestCase):
    """Verify preference_facts returns correct data with ordering and filtering."""

    def test_returns_all_seeded_facts(self):
        """All inserted facts should be returned."""
        _, db = _make_db()
        db.add_preference("genre_like", "I love horror")
        db.add_preference("genre_dislike", "Not a fan of rom-coms")
        db.add_preference("director_like", "Big Kubrick fan")

        facts = db.preference_facts(limit=50)

        self.assertEqual(len(facts), 3)
        texts = {f["text"] for f in facts}
        self.assertEqual(texts, {"I love horror", "Not a fan of rom-coms", "Big Kubrick fan"})

    def test_ordering_is_desc_by_created_at(self):
        """Facts should come back newest-first."""
        _, db = _make_db()
        db.add_preference("a", "First")
        time.sleep(0.01)
        db.add_preference("b", "Second")
        time.sleep(0.01)
        db.add_preference("c", "Third")

        facts = db.preference_facts(limit=50)
        texts = [f["text"] for f in facts]
        self.assertEqual(texts, ["Third", "Second", "First"])

    def test_limit_caps_results(self):
        """Limit should cap the number of returned facts."""
        _, db = _make_db()
        for i in range(10):
            db.add_preference("genre_like", f"fact-{i}")

        facts = db.preference_facts(limit=3)
        self.assertEqual(len(facts), 3)

    def test_user_id_filter_includes_null_user(self):
        """user_id filter should include facts with NULL user_id."""
        _, db = _make_db()
        db.add_preference("genre_like", "Global pref")
        db.add_preference("genre_like", "Alice pref", user_id="alice")
        db.add_preference("genre_like", "Bob pref", user_id="bob")

        alice_facts = db.preference_facts(limit=50, user_id="alice")
        texts = {f["text"] for f in alice_facts}
        self.assertIn("Global pref", texts)
        self.assertIn("Alice pref", texts)
        self.assertNotIn("Bob pref", texts)

    def test_no_user_id_returns_all(self):
        """Without user_id filter, all facts are returned."""
        _, db = _make_db()
        db.add_preference("a", "Global")
        db.add_preference("b", "Alice specific", user_id="alice")

        facts = db.preference_facts(limit=50)
        self.assertEqual(len(facts), 2)

    def test_empty_preferences(self):
        """Empty table should return empty list."""
        _, db = _make_db()
        facts = db.preference_facts(limit=50)
        self.assertEqual(facts, [])

    def test_weight_preserved(self):
        """Weight values should be preserved in returned rows."""
        _, db = _make_db()
        db.add_preference("genre_like", "Weighted pref", weight=3.5)

        facts = db.preference_facts(limit=50)
        self.assertEqual(len(facts), 1)
        self.assertAlmostEqual(facts[0]["weight"], 3.5, places=1)


# ---------------------------------------------------------------------------
# list_recent_arr_queue — ordering, status filtering
# ---------------------------------------------------------------------------


class TestListRecentArrQueue(unittest.TestCase):
    """Verify arr queue listing with correct ordering and field mapping."""

    def test_ordering_by_queued_at_desc(self):
        """Items should come back newest-first."""
        _, db = _make_db()
        db.record_arr_queue(media_type="movie", source="radarr", tmdb_id=100, title="Old Movie")
        time.sleep(0.01)
        db.record_arr_queue(media_type="movie", source="radarr", tmdb_id=200, title="New Movie")

        queue = db.list_recent_arr_queue()
        self.assertEqual(len(queue), 2)
        self.assertEqual(queue[0]["title"], "New Movie")
        self.assertEqual(queue[1]["title"], "Old Movie")

    def test_field_mapping_complete(self):
        """All fields should be correctly mapped from the row."""
        _, db = _make_db()
        db.record_arr_queue(
            media_type="movie",
            source="radarr",
            tmdb_id=42,
            title="Test Film",
            session_id="sess-123",
        )

        queue = db.list_recent_arr_queue()
        self.assertEqual(len(queue), 1)
        item = queue[0]
        self.assertEqual(item["media_type"], "movie")
        self.assertEqual(item["tmdb_id"], 42)
        self.assertIsNone(item["tvdb_id"])
        self.assertEqual(item["title"], "Test Film")
        self.assertEqual(item["source"], "radarr")
        self.assertEqual(item["session_id"], "sess-123")
        self.assertIsInstance(item["queued_at"], float)

    def test_limit_parameter(self):
        """Limit should cap the results."""
        _, db = _make_db()
        for i in range(10):
            db.record_arr_queue(media_type="movie", source="radarr", tmdb_id=i + 1, title=f"Film {i}")
            time.sleep(0.005)

        queue = db.list_recent_arr_queue(limit=3)
        self.assertEqual(len(queue), 3)
        self.assertEqual(queue[0]["title"], "Film 9")

    def test_limit_clamped_to_100(self):
        """Limit should be clamped to max 100."""
        _, db = _make_db()
        db.record_arr_queue(media_type="movie", source="radarr", tmdb_id=1, title="One")

        queue = db.list_recent_arr_queue(limit=999)
        self.assertEqual(len(queue), 1)

    def test_tvdb_id_show_items(self):
        """Show items with tvdb_id should map correctly."""
        _, db = _make_db()
        db.record_arr_queue(media_type="show", source="sonarr", tvdb_id=555, title="Test Show")

        queue = db.list_recent_arr_queue()
        self.assertEqual(len(queue), 1)
        self.assertEqual(queue[0]["media_type"], "show")
        self.assertEqual(queue[0]["tvdb_id"], 555)
        self.assertIsNone(queue[0]["tmdb_id"])

    def test_empty_queue(self):
        """Empty queue should return empty list."""
        _, db = _make_db()
        queue = db.list_recent_arr_queue()
        self.assertEqual(queue, [])

    def test_duplicate_tmdb_id_updates_existing(self):
        """Re-queuing same tmdb_id/media_type should update, not duplicate."""
        _, db = _make_db()
        db.record_arr_queue(media_type="movie", source="radarr", tmdb_id=100, title="Original")
        time.sleep(0.01)
        db.record_arr_queue(media_type="movie", source="seerr", tmdb_id=100, title="Updated")

        queue = db.list_recent_arr_queue()
        self.assertEqual(len(queue), 1)
        self.assertEqual(queue[0]["title"], "Updated")
        self.assertEqual(queue[0]["source"], "seerr")


# ---------------------------------------------------------------------------
# count_chat_sessions_last_days — date window calculation
# ---------------------------------------------------------------------------


class TestCountChatSessionsLastDays(unittest.TestCase):
    """Verify date window boundary logic for session counting."""

    def test_sessions_within_window_counted(self):
        """All sessions created within the window should be counted."""
        _, db = _make_db()
        db.create_chat_thread("s1")
        db.create_chat_thread("s2")
        db.create_chat_thread("s3")

        count = db.count_chat_sessions_last_days(days=30)
        self.assertEqual(count, 3)

    def test_exact_boundary_included(self):
        """A session created 1 second inside the cutoff should be included.

        The cutoff is recomputed inside count_chat_sessions_last_days using
        a fresh time.time(), so we add a small buffer to avoid race conditions.
        """
        _, db = _make_db()
        now = time.time()
        just_inside_cutoff = now - (7 * 86400) + 2

        with db.connect() as conn:
            conn.execute(
                """
                INSERT INTO chat_sessions
                    (id, created_at, updated_at, lens_id, thread_title, context_hash)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                ("at-boundary", just_inside_cutoff, just_inside_cutoff, DEFAULT_LENS_ID, "Boundary", DEFAULT_CONTEXT_HASH),
            )

        count = db.count_chat_sessions_last_days(days=7)
        self.assertEqual(count, 1)

    def test_just_outside_boundary_excluded(self):
        """A session 1 second before the cutoff should be excluded."""
        _, db = _make_db()
        now = time.time()
        just_before_cutoff = now - (7 * 86400) - 1

        with db.connect() as conn:
            conn.execute(
                """
                INSERT INTO chat_sessions
                    (id, created_at, updated_at, lens_id, thread_title, context_hash)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                ("outside", just_before_cutoff, just_before_cutoff, DEFAULT_LENS_ID, "Old", DEFAULT_CONTEXT_HASH),
            )

        count = db.count_chat_sessions_last_days(days=7)
        self.assertEqual(count, 0)

    def test_zero_days_counts_nothing_old(self):
        """With days=0, only sessions from the current instant should count."""
        _, db = _make_db()
        now = time.time()
        with db.connect() as conn:
            conn.execute(
                """
                INSERT INTO chat_sessions
                    (id, created_at, updated_at, lens_id, thread_title, context_hash)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                ("old", now - 100, now - 100, DEFAULT_LENS_ID, "Old", DEFAULT_CONTEXT_HASH),
            )

        count = db.count_chat_sessions_last_days(days=0)
        self.assertEqual(count, 0)

    def test_mixed_old_and_new_sessions(self):
        """Mix of sessions inside and outside the window."""
        _, db = _make_db()
        now = time.time()

        db.create_chat_thread("recent-1")
        db.create_chat_thread("recent-2")

        with db.connect() as conn:
            old_time = now - (60 * 86400)
            conn.execute(
                """
                INSERT INTO chat_sessions
                    (id, created_at, updated_at, lens_id, thread_title, context_hash)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                ("old-1", old_time, old_time, DEFAULT_LENS_ID, "Old Thread", DEFAULT_CONTEXT_HASH),
            )

        count = db.count_chat_sessions_last_days(days=30)
        self.assertEqual(count, 2)

    def test_empty_database_returns_zero(self):
        """No sessions should return 0."""
        _, db = _make_db()
        count = db.count_chat_sessions_last_days(days=30)
        self.assertEqual(count, 0)


# ---------------------------------------------------------------------------
# semantic_search — cosine similarity ranking, threshold filtering
# ---------------------------------------------------------------------------


class TestSemanticSearch(unittest.TestCase):
    """Verify cosine similarity ranking and filtering in semantic_search."""

    def test_ranking_by_similarity_descending(self):
        """Items should be ranked by cosine similarity, highest first."""
        _, db = _make_db()
        _seed_library(db, [
            {"rating_key": "a", "media_type": "movie", "title": "Movie A", "year": 2020},
            {"rating_key": "b", "media_type": "movie", "title": "Movie B", "year": 2021},
            {"rating_key": "c", "media_type": "movie", "title": "Movie C", "year": 2022},
        ])

        items = db.all_library_items()
        id_map = {r["title"]: int(r["id"]) for r in items}

        db.set_embedding(id_map["Movie A"], [1.0, 0.0, 0.0])
        db.set_embedding(id_map["Movie B"], [0.7, 0.7, 0.0])
        db.set_embedding(id_map["Movie C"], [0.0, 0.0, 1.0])

        query_vec = [1.0, 0.0, 0.0]
        results = semantic_search(db, query_vec, limit=10)

        result_ids = [item_id for item_id, _ in results]
        self.assertEqual(result_ids[0], id_map["Movie A"])
        self.assertEqual(result_ids[1], id_map["Movie B"])
        self.assertEqual(result_ids[2], id_map["Movie C"])

        self.assertAlmostEqual(results[0][1], 1.0, places=5)
        self.assertGreater(results[1][1], results[2][1])

    def test_media_type_filter(self):
        """media_type filter should only return matching items."""
        _, db = _make_db()
        _seed_library(db, [
            {"rating_key": "m1", "media_type": "movie", "title": "Action Movie", "year": 2020},
            {"rating_key": "s1", "media_type": "show", "title": "Drama Show", "year": 2021},
        ])

        items = db.all_library_items()
        id_map = {r["title"]: int(r["id"]) for r in items}

        db.set_embedding(id_map["Action Movie"], [1.0, 0.0])
        db.set_embedding(id_map["Drama Show"], [0.9, 0.1])

        results = semantic_search(db, [1.0, 0.0], limit=10, media_type="movie")
        result_ids = {item_id for item_id, _ in results}
        self.assertIn(id_map["Action Movie"], result_ids)
        self.assertNotIn(id_map["Drama Show"], result_ids)

    def test_candidate_ids_filter(self):
        """candidate_ids should restrict search to only those IDs."""
        _, db = _make_db()
        _seed_library(db, [
            {"rating_key": "a", "media_type": "movie", "title": "A", "year": 2020},
            {"rating_key": "b", "media_type": "movie", "title": "B", "year": 2021},
            {"rating_key": "c", "media_type": "movie", "title": "C", "year": 2022},
        ])

        items = db.all_library_items()
        id_map = {r["title"]: int(r["id"]) for r in items}

        db.set_embedding(id_map["A"], [1.0, 0.0])
        db.set_embedding(id_map["B"], [0.9, 0.1])
        db.set_embedding(id_map["C"], [0.5, 0.5])

        candidates = {id_map["B"], id_map["C"]}
        results = semantic_search(db, [1.0, 0.0], limit=10, candidate_ids=candidates)

        result_ids = {item_id for item_id, _ in results}
        self.assertNotIn(id_map["A"], result_ids)
        self.assertIn(id_map["B"], result_ids)
        self.assertIn(id_map["C"], result_ids)

    def test_limit_parameter(self):
        """Limit should cap the number of results returned."""
        _, db = _make_db()
        for i in range(5):
            _seed_library(db, [
                {"rating_key": f"item-{i}", "media_type": "movie", "title": f"Film {i}", "year": 2020},
            ])

        items = db.all_library_items()
        for row in items:
            db.set_embedding(int(row["id"]), [1.0, 0.0])

        results = semantic_search(db, [1.0, 0.0], limit=2)
        self.assertEqual(len(results), 2)

    def test_empty_embeddings_returns_empty(self):
        """No embeddings should return empty list."""
        _, db = _make_db()
        results = semantic_search(db, [1.0, 0.0], limit=10)
        self.assertEqual(results, [])

    def test_orthogonal_vectors_have_zero_similarity(self):
        """Orthogonal vectors should have cosine similarity of 0."""
        _, db = _make_db()
        _seed_library(db, [
            {"rating_key": "orth", "media_type": "movie", "title": "Orthogonal", "year": 2020},
        ])

        items = db.all_library_items()
        item_id = int(items[0]["id"])
        db.set_embedding(item_id, [0.0, 1.0])

        results = semantic_search(db, [1.0, 0.0], limit=10)
        self.assertEqual(len(results), 1)
        self.assertAlmostEqual(results[0][1], 0.0, places=5)


# ---------------------------------------------------------------------------
# cosine_similarity — unit tests for the helper function
# ---------------------------------------------------------------------------


class TestCosineSimilarity(unittest.TestCase):
    """Verify the cosine_similarity helper function."""

    def test_identical_vectors(self):
        self.assertAlmostEqual(cosine_similarity([1, 2, 3], [1, 2, 3]), 1.0, places=5)

    def test_opposite_vectors(self):
        self.assertAlmostEqual(cosine_similarity([1, 0], [-1, 0]), -1.0, places=5)

    def test_orthogonal_vectors(self):
        self.assertAlmostEqual(cosine_similarity([1, 0], [0, 1]), 0.0, places=5)

    def test_empty_vectors_return_zero(self):
        self.assertEqual(cosine_similarity([], []), 0.0)

    def test_zero_vector_returns_zero(self):
        self.assertEqual(cosine_similarity([0, 0], [1, 1]), 0.0)

    def test_mismatched_lengths_return_zero(self):
        self.assertEqual(cosine_similarity([1, 2], [1, 2, 3]), 0.0)


# ---------------------------------------------------------------------------
# get_embeddings / set_embedding — round-trip verification
# ---------------------------------------------------------------------------


class TestEmbeddingRoundTrip(unittest.TestCase):
    """Verify embedding storage and retrieval preserves exact values."""

    def test_set_and_get_embedding(self):
        """Stored vector should be exactly retrievable."""
        _, db = _make_db()
        _seed_library(db, [
            {"rating_key": "e1", "media_type": "movie", "title": "Embedded Film", "year": 2020},
        ])
        items = db.all_library_items()
        item_id = int(items[0]["id"])

        vector = [0.1, 0.2, 0.3, 0.4, 0.5]
        db.set_embedding(item_id, vector)

        embeddings = db.get_embeddings()
        self.assertEqual(len(embeddings), 1)
        self.assertEqual(embeddings[0][0], item_id)
        for stored, original in zip(embeddings[0][1], vector):
            self.assertAlmostEqual(stored, original, places=10)

    def test_set_embeddings_bulk(self):
        """Bulk insert should store all embeddings."""
        _, db = _make_db()
        _seed_library(db, [
            {"rating_key": f"e{i}", "media_type": "movie", "title": f"Film {i}", "year": 2020}
            for i in range(3)
        ])
        items = db.all_library_items()
        id_list = [int(r["id"]) for r in items]

        db.set_embeddings([
            (id_list[0], [1.0, 0.0]),
            (id_list[1], [0.0, 1.0]),
            (id_list[2], [0.5, 0.5]),
        ])

        embeddings = db.get_embeddings()
        self.assertEqual(len(embeddings), 3)

    def test_overwrite_embedding(self):
        """Re-setting an embedding should overwrite the old one."""
        _, db = _make_db()
        _seed_library(db, [
            {"rating_key": "ow", "media_type": "movie", "title": "Overwrite", "year": 2020},
        ])
        items = db.all_library_items()
        item_id = int(items[0]["id"])

        db.set_embedding(item_id, [1.0, 0.0])
        db.set_embedding(item_id, [0.0, 1.0])

        embeddings = db.get_embeddings()
        self.assertEqual(len(embeddings), 1)
        self.assertAlmostEqual(embeddings[0][1][0], 0.0, places=5)
        self.assertAlmostEqual(embeddings[0][1][1], 1.0, places=5)


# ---------------------------------------------------------------------------
# record_arr_queue / is_arr_queued — COALESCE identity logic
# ---------------------------------------------------------------------------


class TestArrQueueIdentity(unittest.TestCase):
    """Verify the COALESCE-based identity matching in arr_queue operations."""

    def test_is_arr_queued_by_tmdb_id(self):
        """Queued by tmdb_id should be queryable by tmdb_id."""
        _, db = _make_db()
        db.record_arr_queue(media_type="movie", source="radarr", tmdb_id=42)

        self.assertTrue(db.is_arr_queued(media_type="movie", tmdb_id=42))
        self.assertFalse(db.is_arr_queued(media_type="movie", tmdb_id=99))
        self.assertFalse(db.is_arr_queued(media_type="show", tmdb_id=42))

    def test_is_arr_queued_by_tvdb_id(self):
        """Queued by tvdb_id should be queryable by tvdb_id."""
        _, db = _make_db()
        db.record_arr_queue(media_type="show", source="sonarr", tvdb_id=555)

        self.assertTrue(db.is_arr_queued(media_type="show", tvdb_id=555))
        self.assertFalse(db.is_arr_queued(media_type="show", tvdb_id=999))

    def test_no_id_returns_false(self):
        """Querying without tmdb_id or tvdb_id should return False."""
        _, db = _make_db()
        self.assertFalse(db.is_arr_queued(media_type="movie"))

    def test_record_without_any_id_is_noop(self):
        """Recording without tmdb_id or tvdb_id should silently do nothing."""
        _, db = _make_db()
        db.record_arr_queue(media_type="movie", source="radarr")
        queue = db.list_recent_arr_queue()
        self.assertEqual(queue, [])

    def test_queued_tmdb_ids_set(self):
        """queued_tmdb_ids should return a set of all queued tmdb_ids."""
        _, db = _make_db()
        db.record_arr_queue(media_type="movie", source="radarr", tmdb_id=10)
        db.record_arr_queue(media_type="movie", source="radarr", tmdb_id=20)
        db.record_arr_queue(media_type="show", source="sonarr", tvdb_id=30)

        ids = db.queued_tmdb_ids("movie")
        self.assertEqual(ids, {10, 20})


# ---------------------------------------------------------------------------
# upsert_library_item — column coverage
# ---------------------------------------------------------------------------


class TestUpsertLibraryItem(unittest.TestCase):
    """Verify upsert_library_item stores and retrieves all fields correctly."""

    def test_all_fields_round_trip(self):
        """All nullable/optional fields should be stored and retrievable."""
        _, db = _make_db()
        item = {
            "rating_key": "full-item",
            "media_type": "movie",
            "title": "Full Data Movie",
            "year": 2023,
            "summary": "A test movie with all fields populated.",
            "genres": ["Action", "Drama"],
            "cast": ["Actor One", "Actor Two"],
            "directors": ["Director One"],
            "keywords": ["test", "validation"],
            "tmdb_id": 12345,
            "tvdb_id": 67890,
            "imdb_id": "tt1234567",
            "poster_url": "https://example.com/poster.jpg",
            "backdrop_url": "https://example.com/backdrop.jpg",
            "view_count": 5,
            "added_at": 1700000000,
            "last_viewed_at": 1700100000,
            "file_size": 4_000_000_000,
            "in_radarr": True,
            "in_sonarr": False,
            "runtime_minutes": 142,
            "vote_average": 8.5,
        }
        db.upsert_library_item(item)

        row = db.library_item_by_tmdb(12345, "movie")
        self.assertIsNotNone(row)
        self.assertEqual(row["title"], "Full Data Movie")
        self.assertEqual(row["year"], 2023)
        self.assertEqual(row["tmdb_id"], 12345)
        self.assertEqual(row["view_count"], 5)
        self.assertEqual(row["runtime_minutes"], 142)
        self.assertAlmostEqual(row["vote_average"], 8.5, places=1)

    def test_upsert_updates_existing(self):
        """Re-upserting with same rating_key should update the row."""
        _, db = _make_db()
        db.upsert_library_item({
            "rating_key": "up1",
            "media_type": "movie",
            "title": "Original Title",
            "year": 2020,
        })
        db.upsert_library_item({
            "rating_key": "up1",
            "media_type": "movie",
            "title": "Updated Title",
            "year": 2021,
        })

        items = db.all_library_items()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["title"], "Updated Title")
        self.assertEqual(items[0]["year"], 2021)

    def test_null_optional_fields(self):
        """Items with NULL year, runtime, etc. should store correctly."""
        _, db = _make_db()
        db.upsert_library_item({
            "rating_key": "null-item",
            "media_type": "movie",
            "title": "Null Fields",
        })

        items = db.all_library_items()
        self.assertEqual(len(items), 1)
        self.assertIsNone(items[0]["year"])
        self.assertIsNone(items[0]["runtime_minutes"])
        self.assertIsNone(items[0]["vote_average"])


# ---------------------------------------------------------------------------
# library_counts — aggregation sanity
# ---------------------------------------------------------------------------


class TestLibraryCounts(unittest.TestCase):
    """Verify library_counts returns exact counts per media type."""

    def test_exact_counts(self):
        _, db = _make_db()
        _seed_library(db, [
            {"rating_key": "m1", "media_type": "movie", "title": "Movie 1"},
            {"rating_key": "m2", "media_type": "movie", "title": "Movie 2"},
            {"rating_key": "m3", "media_type": "movie", "title": "Movie 3"},
            {"rating_key": "s1", "media_type": "show", "title": "Show 1"},
        ])

        counts = db.library_counts()
        self.assertEqual(counts["movies"], 3)
        self.assertEqual(counts["shows"], 1)
        self.assertEqual(counts["items"], 4)

    def test_empty_library(self):
        _, db = _make_db()
        counts = db.library_counts()
        self.assertEqual(counts["movies"], 0)
        self.assertEqual(counts["shows"], 0)
        self.assertEqual(counts["items"], 0)


# ---------------------------------------------------------------------------
# upsert_message_feedback — upsert conflict handling
# ---------------------------------------------------------------------------


class TestMessageFeedback(unittest.TestCase):
    """Verify message feedback upsert and listing."""

    def test_upsert_creates_feedback(self):
        _, db = _make_db()
        sid = "fb-sess"
        db.ensure_chat_session(sid)
        db.save_chat_message(sid, "msg-1", "assistant", [{"type": "text", "content": "hi"}])

        result = db.upsert_message_feedback(
            feedback_id="fb-1",
            message_id="msg-1",
            session_id=sid,
            user_id=None,
            feedback_type="helpful",
            excerpt="good answer",
        )

        self.assertEqual(result["feedback"], "helpful")
        self.assertEqual(result["excerpt"], "good answer")
        self.assertEqual(result["message_id"], "msg-1")

    def test_upsert_updates_on_conflict(self):
        """Re-upserting same message_id+user_id should update feedback_type."""
        _, db = _make_db()
        sid = "fb-sess2"
        db.ensure_chat_session(sid)
        db.save_chat_message(sid, "msg-2", "assistant", [{"type": "text", "content": "hi"}])

        db.upsert_message_feedback(
            feedback_id="fb-2a",
            message_id="msg-2",
            session_id=sid,
            user_id="alice",
            feedback_type="helpful",
            excerpt="nice",
        )
        db.upsert_message_feedback(
            feedback_id="fb-2b",
            message_id="msg-2",
            session_id=sid,
            user_id="alice",
            feedback_type="not_helpful",
            excerpt="changed my mind",
        )

        feedbacks = db.list_message_feedback(sid, user_id="alice")
        self.assertEqual(len(feedbacks), 1)
        self.assertEqual(feedbacks[0]["feedback"], "not_helpful")
        self.assertEqual(feedbacks[0]["excerpt"], "changed my mind")


# ---------------------------------------------------------------------------
# _preview_from_blocks — helper function validation
# ---------------------------------------------------------------------------


class TestPreviewFromBlocks(unittest.TestCase):
    """Verify the _preview_from_blocks helper correctly extracts text."""

    def _call_preview(self, db: Database, blocks_json):
        return db._preview_from_blocks(blocks_json)

    def test_extracts_first_text_block(self):
        _, db = _make_db()
        blocks = json.dumps([
            {"type": "text", "content": "Hello, this is a preview"},
            {"type": "text", "content": "Second text"},
        ])
        self.assertEqual(self._call_preview(db, blocks), "Hello, this is a preview")

    def test_truncates_at_120_chars(self):
        _, db = _make_db()
        long_text = "x" * 200
        blocks = json.dumps([{"type": "text", "content": long_text}])
        result = self._call_preview(db, blocks)
        self.assertEqual(len(result), 120)

    def test_none_returns_empty(self):
        _, db = _make_db()
        self.assertEqual(self._call_preview(db, None), "")

    def test_empty_string_returns_empty(self):
        _, db = _make_db()
        self.assertEqual(self._call_preview(db, ""), "")

    def test_invalid_json_returns_empty(self):
        _, db = _make_db()
        self.assertEqual(self._call_preview(db, "not-json"), "")

    def test_no_text_blocks_returns_empty(self):
        _, db = _make_db()
        blocks = json.dumps([{"type": "tool_use", "name": "search"}])
        self.assertEqual(self._call_preview(db, blocks), "")

    def test_skips_empty_text_blocks(self):
        _, db = _make_db()
        blocks = json.dumps([
            {"type": "text", "content": ""},
            {"type": "text", "content": "   "},
            {"type": "text", "content": "Actual content"},
        ])
        self.assertEqual(self._call_preview(db, blocks), "Actual content")


# ---------------------------------------------------------------------------
# Prune operations — data retention
# ---------------------------------------------------------------------------


class TestPruneOperations(unittest.TestCase):
    """Verify prune methods delete the correct rows."""

    def test_prune_telemetry_deletes_old_events(self):
        _, db = _make_db()
        db.insert_telemetry_event(event_id="fresh", event_class="sync", payload_json="{}")

        deleted = db.prune_telemetry(retention_days=30)
        self.assertEqual(deleted, 0)

        remaining = db.telemetry_summary(hours=24)
        self.assertEqual(remaining.get("sync"), 1)

    def test_prune_telemetry_zero_days_deletes_nothing_recent(self):
        """With retention_days=0, only events older than 'now' are deleted.
        Fresh events have timestamp=CURRENT_TIMESTAMP which is 'now',
        so they won't be pruned with retention_days=0."""
        _, db = _make_db()
        db.insert_telemetry_event(event_id="e1", event_class="test", payload_json="{}")

        deleted = db.prune_telemetry(retention_days=0)
        self.assertEqual(deleted, 0)


# ---------------------------------------------------------------------------
# chat_history — message ordering and lens filtering
# ---------------------------------------------------------------------------


class TestChatHistory(unittest.TestCase):
    """Verify chat_history returns messages in correct order."""

    def test_messages_returned_chronologically(self):
        """Messages should be returned oldest-first (ASC) after internal reversal."""
        _, db = _make_db()
        sid = "hist-sess"
        db.ensure_chat_session(sid)
        db.save_chat_message(sid, "m1", "user", [{"type": "text", "content": "First"}])
        time.sleep(0.01)
        db.save_chat_message(sid, "m2", "assistant", [{"type": "text", "content": "Second"}])
        time.sleep(0.01)
        db.save_chat_message(sid, "m3", "user", [{"type": "text", "content": "Third"}])

        history = db.chat_history(sid, limit=50)
        self.assertEqual(len(history), 3)
        self.assertEqual(history[0]["role"], "user")
        self.assertEqual(history[2]["role"], "user")

        blocks_first = history[0]["blocks"]
        self.assertEqual(blocks_first[0]["content"], "First")

    def test_empty_session_returns_empty(self):
        _, db = _make_db()
        sid = "empty-hist"
        db.ensure_chat_session(sid)
        history = db.chat_history(sid, limit=50)
        self.assertEqual(history, [])


# ---------------------------------------------------------------------------
# maybe_auto_title_thread — auto-titling logic
# ---------------------------------------------------------------------------


class TestAutoTitleThread(unittest.TestCase):
    """Verify auto-title sets title from first message content."""

    def test_sets_title_from_first_message(self):
        _, db = _make_db()
        sid = "auto-title"
        db.create_chat_thread(sid)
        db.maybe_auto_title_thread(sid, "What are the best sci-fi movies?")

        thread = db.get_chat_thread(sid)
        self.assertEqual(thread["thread_title"], "What are the best sci-fi movies?")

    def test_truncates_long_messages(self):
        _, db = _make_db()
        sid = "auto-long"
        db.create_chat_thread(sid)
        long_msg = "A" * 100
        db.maybe_auto_title_thread(sid, long_msg)

        thread = db.get_chat_thread(sid)
        self.assertEqual(len(thread["thread_title"]), 61)  # 60 chars + ellipsis

    def test_does_not_overwrite_existing_title(self):
        _, db = _make_db()
        sid = "auto-existing"
        db.create_chat_thread(sid, thread_title="Custom Title")
        db.maybe_auto_title_thread(sid, "Should not overwrite")

        thread = db.get_chat_thread(sid)
        self.assertEqual(thread["thread_title"], "Custom Title")

    def test_empty_message_does_nothing(self):
        _, db = _make_db()
        sid = "auto-empty"
        db.create_chat_thread(sid)
        db.maybe_auto_title_thread(sid, "   ")

        thread = db.get_chat_thread(sid)
        self.assertEqual(thread["thread_title"], "New conversation")


# ---------------------------------------------------------------------------
# delete_chat_thread — cascade and user_id logic
# ---------------------------------------------------------------------------


class TestDeleteChatThread(unittest.TestCase):

    def test_delete_existing_thread(self):
        _, db = _make_db()
        db.create_chat_thread("del-1")
        self.assertTrue(db.delete_chat_thread("del-1"))
        self.assertIsNone(db.get_chat_thread("del-1"))

    def test_delete_nonexistent_returns_false(self):
        _, db = _make_db()
        self.assertFalse(db.delete_chat_thread("nope"))

    def test_delete_with_wrong_user_id_fails(self):
        _, db = _make_db()
        db.create_chat_thread("del-user", user_id="alice")
        self.assertFalse(db.delete_chat_thread("del-user", user_id="bob"))
        self.assertIsNotNone(db.get_chat_thread("del-user"))


if __name__ == "__main__":
    unittest.main()
