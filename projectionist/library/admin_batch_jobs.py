"""Other silent admin fan-outs — same execution snapshot as Register in Radarr."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Mapping, Optional, Sequence

from projectionist.library.admin_execution import (
    finished_message,
    flatten_result,
    request_cancel,
    start_worker,
    store_for,
)

logger = logging.getLogger(__name__)

NEWSLETTER_KIND = "weekly_newsletter"
YIR_KIND = "year_in_review"
DIGEST_KIND = "weekly_digest"
RAIL_KIND = "weekly_rail"


def _label(user: Mapping[str, Any]) -> str:
    return str(user.get("preferred_name") or user.get("display_name") or user.get("email") or user.get("id") or "Member")


def _user_item(user: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "id": str(user.get("id")),
        "title": _label(user),
        "status": "queued",
        "outcome": "",
        "error": "",
    }


def build_status(kind: str, *, idle_message: str = "Ready when you are") -> Dict[str, Any]:
    return flatten_result(store_for(kind, idle_message=idle_message).snapshot())


def cancel_job(kind: str) -> Dict[str, Any]:
    return request_cancel(kind)


def _begin_or_busy(kind: str, *, message: str, items: Sequence[Mapping[str, Any]], idle_message: str) -> Optional[str]:
    store = store_for(kind, idle_message=idle_message)
    return store.begin(phase="queued", message=message, items=items)


def start_newsletter_job(
    db: Any,
    settings: Any,
    *,
    scope: str,
    user_ids: Optional[Sequence[str]],
    owner_id: str,
) -> Dict[str, Any]:
    from projectionist.notifications.newsletters import deliver_weekly_newsletters

    if user_ids is None:
        candidates = [u for u in db.list_users(limit=500) if not u.get("disabled")]
    else:
        candidates = []
        for uid in user_ids:
            row = db.get_user(uid)
            if row is None:
                continue
            user = db._row_to_user(row)
            if user.get("disabled"):
                continue
            candidates.append(user)
    items = [_user_item(user) for user in candidates]
    store = store_for(NEWSLETTER_KIND, idle_message="Ready to send")
    job_id = _begin_or_busy(
        NEWSLETTER_KIND,
        message="Queued weekly newsletter…",
        items=items,
        idle_message="Ready to send",
    )
    if not job_id:
        snap = store.snapshot()
        snap["accepted"] = False
        snap["message"] = snap.get("message") or "A newsletter send is already running."
        return snap

    def _run(job_store, cancel) -> Mapping[str, Any]:
        delivered = emailed = skipped_opt_out = skipped_disabled = 0
        job_store.update("sending", "Sending weekly newsletter…")
        for user in candidates:
            uid = str(user.get("id"))
            if cancel.is_set():
                job_store.set_item(uid, "cancelled", outcome="cancelled")
                continue
            job_store.set_item(uid, "running", message=f"Sending to {_label(user)}…")
            try:
                result = deliver_weekly_newsletters(db, settings, user_ids=[uid])
                delivered += int(result.get("delivered") or 0)
                emailed += int(result.get("emailed") or 0)
                skipped_opt_out += int(result.get("skipped_opt_out") or 0)
                skipped_disabled += int(result.get("skipped_disabled") or 0)
                if result.get("delivered"):
                    job_store.set_item(uid, "completed", outcome="delivered")
                elif result.get("skipped_opt_out"):
                    job_store.set_item(uid, "completed", outcome="skipped")
                else:
                    job_store.set_item(uid, "completed", outcome="skipped")
            except Exception as error:  # noqa: BLE001
                logger.warning("Newsletter send failed user=%s: %s", uid, error)
                job_store.set_item(uid, "failed", error=str(error)[:400], outcome="failed")
        payload = {
            "scope": scope,
            "delivered": delivered,
            "emailed": emailed,
            "targeted": len(candidates),
            "skipped_opt_out": skipped_opt_out,
            "skipped_disabled": skipped_disabled,
            "skipped_missing": 0,
        }
        snap = job_store.snapshot()
        phase = "cancelled" if cancel.is_set() else "done"
        job_store.set_done(
            finished_message(snap.get("execution") or {}, noun="member", action="Sent"),
            result=payload,
            phase=phase,
        )
        return payload

    if not start_worker(NEWSLETTER_KIND, _run, name="weekly-newsletter"):
        snap = flatten_result(store.snapshot())
        snap["accepted"] = False
        return snap
    snap = flatten_result(store.snapshot())
    snap["accepted"] = True
    snap["job_id"] = job_id
    snap["scope"] = scope
    return snap


def start_year_in_review_job(
    db: Any,
    settings: Any,
    *,
    user_id: str,
    year: int,
    notify: bool,
    status_hint: str,
) -> Dict[str, Any]:
    from projectionist.year_in_review.delivery import deliver_year_in_review
    from projectionist.year_in_review.snapshot import build_reel_for_user

    user = db.get_user(user_id)
    label = "You"
    if user is not None:
        mapped = db._row_to_user(user)
        label = _label(mapped)
    items = [{"id": str(user_id), "title": f"{label} · {year}", "status": "queued", "outcome": "", "error": ""}]
    store = store_for(YIR_KIND, idle_message="Ready to generate")
    job_id = _begin_or_busy(
        YIR_KIND,
        message="Queued Year in Review…",
        items=items,
        idle_message="Ready to generate",
    )
    if not job_id:
        snap = store.snapshot()
        snap["accepted"] = False
        snap["message"] = snap.get("message") or "A Year in Review generate is already running."
        return snap

    def _run(job_store, cancel) -> Mapping[str, Any]:
        job_store.update("generating", f"Generating Year in Review for {year}…")
        job_store.set_item(str(user_id), "running", message=f"Building {year} reel…")
        if cancel.is_set():
            job_store.set_item(str(user_id), "cancelled", outcome="cancelled")
            payload = {"scope": "self", "year": year, "status": "cancelled", "cancelled": True}
            job_store.set_done("Cancelled Year in Review.", result=payload, phase="cancelled")
            return payload
        try:
            if notify:
                result = deliver_year_in_review(
                    db,
                    settings,
                    year=year,
                    user_ids=[str(user_id)],
                    status_hint=status_hint,
                    force=True,
                )
                payload = {"scope": "self", **result}
            else:
                snap = build_reel_for_user(db, user_id=str(user_id), year=year, status_hint=status_hint)
                status = snap.get("status")
                path = f"/year-in-review/{year}" if status in ("ready", "tease") else None
                payload = {
                    "scope": "self",
                    "year": year,
                    "generated": 1,
                    "delivered": 0,
                    "status": status,
                    "path": path,
                }
            outcome = "empty" if payload.get("status") == "empty" else "ready"
            job_store.set_item(str(user_id), "completed", outcome=outcome)
            job_store.set_done(
                f"Year in Review {payload.get('status') or 'ready'} for {year}.",
                result=payload,
                phase="done",
            )
            return payload
        except Exception as error:  # noqa: BLE001
            job_store.set_item(str(user_id), "failed", error=str(error)[:400], outcome="failed")
            raise

    if not start_worker(YIR_KIND, _run, name="year-in-review"):
        snap = flatten_result(store.snapshot())
        snap["accepted"] = False
        return snap
    snap = flatten_result(store.snapshot())
    snap["accepted"] = True
    snap["job_id"] = job_id
    snap["scope"] = "self"
    snap["year"] = year
    return snap


def start_digest_job(db: Any, settings: Any) -> Dict[str, Any]:
    from projectionist.digest import snapshot_weekly_digest

    items = [{"id": "digest", "title": "This week in your library", "status": "queued", "outcome": "", "error": ""}]
    store = store_for(DIGEST_KIND, idle_message="Ready to generate")
    job_id = _begin_or_busy(
        DIGEST_KIND,
        message="Queued weekly digest…",
        items=items,
        idle_message="Ready to generate",
    )
    if not job_id:
        snap = store.snapshot()
        snap["accepted"] = False
        snap["message"] = snap.get("message") or "A digest generate is already running."
        return snap

    def _run(job_store, cancel) -> Mapping[str, Any]:
        job_store.update("generating", "Assembling this week’s digest…")
        job_store.set_item("digest", "running", message="Assembling digest…")
        if cancel.is_set():
            job_store.set_item("digest", "cancelled", outcome="cancelled")
            payload = {"latest": None, "cancelled": True}
            job_store.set_done("Cancelled digest.", result=payload, phase="cancelled")
            return payload
        digest = snapshot_weekly_digest(db, settings)
        payload = {"latest": digest}
        job_store.set_item("digest", "completed", outcome="ready")
        job_store.set_done("Weekly digest ready.", result=payload, phase="done")
        return payload

    if not start_worker(DIGEST_KIND, _run, name="weekly-digest"):
        snap = flatten_result(store.snapshot())
        snap["accepted"] = False
        return snap
    snap = flatten_result(store.snapshot())
    snap["accepted"] = True
    snap["job_id"] = job_id
    return snap


def start_weekly_rail_job(db: Any, settings: Any) -> Dict[str, Any]:
    from projectionist.taste import build_weekly_rail_for_user, MAX_LLM_WHY_CALLS

    users = [
        u
        for u in db.list_users(limit=500)
        if not u.get("disabled") and str(u.get("role") or "member") != "guest"
    ]
    items = [_user_item(user) for user in users]
    store = store_for(RAIL_KIND, idle_message="Ready to rebuild")
    job_id = _begin_or_busy(
        RAIL_KIND,
        message="Queued weekly For-you rails…",
        items=items,
        idle_message="Ready to rebuild",
    )
    if not job_id:
        snap = store.snapshot()
        snap["accepted"] = False
        snap["message"] = snap.get("message") or "A weekly rail rebuild is already running."
        return snap

    def _run(job_store, cancel) -> Mapping[str, Any]:
        llm_budget = {"remaining": MAX_LLM_WHY_CALLS, "used": 0}
        built = empty = 0
        job_store.update("generating", "Rebuilding member For-you rails…")
        for user in users:
            uid = str(user.get("id"))
            if cancel.is_set():
                job_store.set_item(uid, "cancelled", outcome="cancelled")
                continue
            job_store.set_item(uid, "running", message=f"Building rail for {_label(user)}…")
            try:
                rail = build_weekly_rail_for_user(
                    db, settings, user=user, llm_budget=llm_budget
                )
                if rail.get("items"):
                    built += 1
                    job_store.set_item(uid, "completed", outcome="built")
                else:
                    empty += 1
                    job_store.set_item(uid, "completed", outcome="empty")
            except Exception as error:  # noqa: BLE001
                logger.warning("Weekly rail failed user=%s: %s", uid, error)
                job_store.set_item(uid, "failed", error=str(error)[:400], outcome="failed")
        payload = {
            "built": built,
            "empty": empty,
            "llm_calls_used": llm_budget["used"],
            "llm_cap": MAX_LLM_WHY_CALLS,
        }
        snap = job_store.snapshot()
        phase = "cancelled" if cancel.is_set() else "done"
        job_store.set_done(
            finished_message(snap.get("execution") or {}, noun="rail", action="Rebuilt"),
            result=payload,
            phase=phase,
        )
        return payload

    if not start_worker(RAIL_KIND, _run, name="weekly-rail"):
        snap = flatten_result(store.snapshot())
        snap["accepted"] = False
        return snap
    snap = flatten_result(store.snapshot())
    snap["accepted"] = True
    snap["job_id"] = job_id
    return snap
