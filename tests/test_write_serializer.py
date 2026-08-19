"""Write serializer concurrency smoke + stats."""

from __future__ import annotations

import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from projectionist.library.db import Database


class WriteSerializerTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db = Database(Path(self._tmpdir.name) / "projectionist.db")

    def tearDown(self) -> None:
        self.db.close()
        self._tmpdir.cleanup()

    def test_concurrent_writers_do_not_raise_database_locked(self) -> None:
        errors: list[BaseException] = []

        def _insert(i: int) -> None:
            try:

                def _write() -> None:
                    with self.db.connect() as conn:
                        conn.execute(
                            """
                            INSERT INTO system_telemetry_stream
                                (id, event_class, payload_json)
                            VALUES (?, 'smoke', ?)
                            """,
                            (f"evt-{i}", "{}"),
                        )

                self.db.run_write(_write, label=f"smoke-{i}")
            except BaseException as exc:  # noqa: BLE001
                errors.append(exc)

        with ThreadPoolExecutor(max_workers=12) as pool:
            futures = [pool.submit(_insert, i) for i in range(40)]
            for fut in as_completed(futures):
                fut.result()

        self.assertEqual(errors, [])
        with self.db.connect() as conn:
            count = conn.execute(
                "SELECT COUNT(*) AS c FROM system_telemetry_stream WHERE event_class = 'smoke'"
            ).fetchone()["c"]
        self.assertEqual(int(count), 40)

    def test_write_queue_stats_expose_depth_and_wait(self) -> None:
        before = self.db.write_queue_stats()
        self.assertIn("queue_depth", before)
        self.assertIn("last_wait_s", before)
        self.assertIn("max_wait_s", before)
        self.assertIn("jobs_done", before)

        def _write() -> None:
            with self.db.connect() as conn:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO system_telemetry_stream
                        (id, event_class, payload_json)
                    VALUES ('stats-1', 'smoke', '{}')
                    """
                )

        self.db.run_write(_write, label="stats")
        after = self.db.write_queue_stats()
        self.assertGreaterEqual(int(after["jobs_done"]), int(before["jobs_done"]) + 1)

    def test_run_write_propagates_errors(self) -> None:
        def _boom() -> None:
            raise ValueError("write failed")

        with self.assertRaises(ValueError):
            self.db.run_write(_boom, label="boom")

    def test_try_run_drops_when_queue_is_full(self) -> None:
        import threading
        import time

        from projectionist.library.db._write_serializer import WriteSerializer

        ser = WriteSerializer(maxsize=1)
        release = threading.Event()
        started = threading.Event()

        def hold() -> None:
            started.set()
            release.wait(timeout=3)

        holder = threading.Thread(target=lambda: ser.run(hold, label="hold"), daemon=True)
        holder.start()
        self.assertTrue(started.wait(timeout=2))

        queued = threading.Event()

        def park() -> None:
            queued.set()
            ser.run(lambda: None, label="park")

        parker = threading.Thread(target=park, daemon=True)
        parker.start()
        self.assertTrue(queued.wait(timeout=2))
        time.sleep(0.05)
        dropped = ser.try_run(lambda: None, label="drop-me")
        self.assertFalse(dropped)
        release.set()
        holder.join(timeout=2)
        parker.join(timeout=2)
        ser.shutdown(timeout=2)
