"""Dialogue import (TML-002).

Cues come from the household subtitle cache and replace the previous dialogue
rows for that file. The response is a count, not the script.
"""

from __future__ import annotations

import json
from typing import Any

from projectionist.timeline.files import TimelineError


def import_dialogue(db: Any, *, file_id: int, cues: list[dict[str, Any]]) -> int:
    if isinstance(file_id, bool) or not isinstance(file_id, int) or file_id < 1:
        raise TimelineError("That file is not available.", status_code=404)

    def _write() -> int:
        with db.connect() as conn:
            from projectionist.library.db._shared import begin_immediate

            begin_immediate(conn)
            found = conn.execute(
                "SELECT id FROM timeline_files WHERE id = ?",
                (file_id,),
            ).fetchone()
            if found is None:
                raise TimelineError("That file is not available.", status_code=404)
            conn.execute(
                """
                DELETE FROM timeline_events
                WHERE file_id = ? AND kind = 'dialogue' AND source = 'subtitle_cache'
                """,
                (file_id,),
            )
            stored = 0
            for cue in cues:
                text = " ".join(str(cue.get("text") or "").split())[:400]
                if not text:
                    continue
                conn.execute(
                    """
                    INSERT INTO timeline_events (
                        file_id, kind, start_ms, end_ms, payload, source, confidence
                    ) VALUES (?, 'dialogue', ?, ?, ?, 'subtitle_cache', 1)
                    """,
                    (
                        file_id,
                        int(cue.get("start_ms") or 0),
                        int(cue.get("end_ms") or 0),
                        json.dumps({"text": text}, ensure_ascii=False),
                    ),
                )
                stored += 1
            return stored

    return int(db.run_write(_write, label="timeline_dialogue"))
