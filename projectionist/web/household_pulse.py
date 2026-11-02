"""Household pulse (GRO-018): a weekly, household-total view of on-box events.

Reads only what this server already wrote locally: ``chat_turn`` and
``play_start`` rows in ``system_telemetry_stream``, ``llm_usage``, inbox
delivery and seen times in ``user_notifications``, and the in-memory runtime
reservoir. Nothing is fetched or sent. Every number is a household total; no
row is broken down by member, and no member id leaves this module.
"""

from __future__ import annotations

import json
import sqlite3
import time
from typing import Any, Dict, List, Optional

from projectionist.web import runtime_metrics

WEEK_S = 7 * 86400
WEEKS = 4

# Guardrails from the 2026-11-01 growth tracking plan. A turn counts as failed
# only on ``outcome == "error"``; a member pressing Stop is not a failure.
CHAT_FAILURE_MAX = 0.05
CHAT_P95_MAX_MS = 12_000
LLM_SPEND_JUMP = 0.5


def _p95(values: List[float]) -> Optional[float]:
    if not values:
        return None
    ordered = sorted(values)
    return float(ordered[min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1))))])


def _week_index(ts: float, now: float) -> Optional[int]:
    age = now - ts
    if age < 0 or age >= WEEKS * WEEK_S:
        return None
    return int(age // WEEK_S)


def _empty_week(i: int, now: float) -> Dict[str, Any]:
    return {
        "start": now - (i + 1) * WEEK_S,
        "end": now - i * WEEK_S,
        "plays_from_picks": 0,
        "plays": 0,
        "chat_turns": 0,
        "chat_errors": 0,
        "_durations": [],
        "_members": set(),
        "llm_tokens": 0,
        "llm_usd": 0.0,
        "notifications_delivered": 0,
        "notifications_seen": 0,
    }


def build_household_pulse(db: Any, *, now: Optional[float] = None) -> Dict[str, Any]:
    now = time.time() if now is None else float(now)
    weeks = [_empty_week(i, now) for i in range(WEEKS)]
    since = now - WEEKS * WEEK_S
    with db.connect() as conn:
        rows = conn.execute(
            """
            SELECT event_class, payload_json, CAST(strftime('%s', timestamp) AS REAL) AS ts
            FROM system_telemetry_stream
            WHERE event_class IN ('chat_turn', 'play_start')
              AND timestamp >= datetime(?, 'unixepoch')
            """,
            (since,),
        ).fetchall()
        for row in rows:
            idx = _week_index(float(row["ts"] or 0), now)
            if idx is None:
                continue
            week = weeks[idx]
            try:
                payload = json.loads(row["payload_json"] or "{}")
            except (TypeError, ValueError):
                payload = {}
            if not isinstance(payload, dict):
                payload = {}
            if payload.get("user_id"):
                week["_members"].add(str(payload["user_id"]))
            if row["event_class"] == "chat_turn":
                week["chat_turns"] += 1
                if payload.get("outcome") == "error":
                    week["chat_errors"] += 1
                if isinstance(payload.get("duration_ms"), (int, float)):
                    week["_durations"].append(float(payload["duration_ms"]))
            else:
                week["plays"] += 1
                if payload.get("rec_id"):
                    week["plays_from_picks"] += 1
        for row in conn.execute(
            "SELECT created_at, COALESCE(total_tokens, 0) AS t, COALESCE(estimated_usd, 0) AS usd "
            "FROM llm_usage WHERE created_at >= ?",
            (since,),
        ):
            idx = _week_index(float(row["created_at"]), now)
            if idx is not None:
                weeks[idx]["llm_tokens"] += int(row["t"])
                weeks[idx]["llm_usd"] += float(row["usd"])
        try:
            notes = conn.execute(
                "SELECT CAST(created_at AS REAL) AS c, seen_at FROM user_notifications "
                "WHERE CAST(created_at AS REAL) >= ?",
                (since,),
            ).fetchall()
        except sqlite3.Error:
            notes = []
        for row in notes:
            idx = _week_index(float(row["c"] or 0), now)
            if idx is not None:
                weeks[idx]["notifications_delivered"] += 1
                if row["seen_at"]:
                    weeks[idx]["notifications_seen"] += 1

    out_weeks = []
    for week in weeks:
        turns = week["chat_turns"]
        out_weeks.append(
            {
                "start": week["start"],
                "end": week["end"],
                "plays_from_picks": week["plays_from_picks"],
                "plays": week["plays"],
                "chat_turns": turns,
                "chat_failure_rate": round(week["chat_errors"] / turns, 3) if turns else None,
                "chat_p95_ms": _p95(week["_durations"]),
                "active_members": len(week["_members"]),
                "llm_tokens": week["llm_tokens"],
                "llm_usd": round(week["llm_usd"], 4),
                "notifications_delivered": week["notifications_delivered"],
                "notifications_seen": week["notifications_seen"],
            }
        )
    this_week, last_week = out_weeks[0], out_weeks[1]
    with db.connect() as conn:
        try:
            member_ids = {
                str(r["id"]) for r in conn.execute("SELECT id FROM users WHERE COALESCE(disabled, 0) = 0")
            }
        except sqlite3.Error:
            member_ids = set()
    members = len(member_ids)
    active_28d = set().union(*(w["_members"] for w in weeks))
    runtime = runtime_metrics.runtime_snapshot(db)
    return {
        "generated_at": now,
        "source": "on_box",
        "telemetry_enabled": _telemetry_enabled(db),
        "north_star": {
            "label": "Plays started from a pick",
            "this_week": this_week["plays_from_picks"],
            "last_week": last_week["plays_from_picks"],
            "weekly": [w["plays_from_picks"] for w in reversed(out_weeks)],
        },
        "guardrails": [
            _guardrail(
                "chat_failure_rate",
                "Chat replies that failed",
                this_week["chat_failure_rate"],
                CHAT_FAILURE_MAX,
            ),
            _guardrail("chat_p95_ms", "Slowest chat replies (p95)", this_week["chat_p95_ms"], CHAT_P95_MAX_MS),
            _spend_guardrail(this_week, last_week),
            {
                "id": "dormant_members",
                "label": "Members with no chats or plays in 4 weeks",
                "value": len(member_ids - active_28d) if members else None,
                "limit": None,
                "status": "info" if members else "no_data",
            },
        ],
        "box": {
            "write_queue_depth": runtime["write_queue"].get("queue_depth"),
            "write_max_wait_s": runtime["write_queue"].get("max_wait_s"),
            "api_p95_ms": runtime["latency"].get("api", {}).get("p95_ms"),
            "uptime_s": runtime["uptime_s"],
        },
        "weeks": out_weeks,
    }


def _telemetry_enabled(db: Any) -> bool:
    try:
        value = db.get_config("telemetry_enabled")
    except Exception:  # noqa: BLE001
        return True
    if value is None:
        return True
    return str(value).strip().lower() not in ("0", "false", "no", "off")


def _spend_guardrail(this_week: Dict[str, Any], last_week: Dict[str, Any]) -> Dict[str, Any]:
    now_usd, prev_usd = this_week["llm_usd"], last_week["llm_usd"]
    base = {"id": "llm_spend", "label": "AI spend this week (USD)", "value": now_usd, "limit": None}
    if not now_usd and not prev_usd:
        return {**base, "status": "no_data"}
    spend_jump = prev_usd > 0 and now_usd > prev_usd * (1 + LLM_SPEND_JUMP)
    usage_jump = this_week["chat_turns"] > last_week["chat_turns"] * (1 + LLM_SPEND_JUMP)
    return {**base, "status": "watch" if spend_jump and not usage_jump else "ok"}


def _guardrail(key: str, label: str, value: Any, limit: Optional[float]) -> Dict[str, Any]:
    if value is None:
        status = "no_data"
    elif limit is None:
        status = "info"
    else:
        status = "ok" if float(value) <= limit else "watch"
    return {"id": key, "label": label, "value": value, "limit": limit, "status": status}
