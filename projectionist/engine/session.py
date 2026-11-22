"""Engine playback sessions.

Opening a session records the plan. A remux, direct, or audio-only plan
starts fMP4 HLS only when the client sets ``engine_opt_in``. Audio-only
copies the video and encodes the audio. A source-transcode plan names the
media source and the reason, and stays on that source's playback path.
Playlist and segment URLs carry the session token; they do not require an
Authorization header. The household gate allows those URLs through and the
route checks the token.
"""

from __future__ import annotations

import secrets
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Sequence

from projectionist.engine.captions import CaptionRendition
from projectionist.engine.planner import plan_playback
from projectionist.engine.profiles import DeviceProfile
from projectionist.engine.remux import start_remux
from projectionist.engine.source import MediaAsset
from projectionist.library.playback import PlaybackError, YouthBlockedError

_LOCK = threading.Lock()
_SESSIONS: dict[str, "EngineSession"] = {}

# A client that did not ask for an engine session stays on the library path.
# The capability means this server can open one. It does not mean the client must.
OPT_IN_REASON = (
    "This client did not opt in to an engine session, so playback stays on the library path."
)


def declined_engine_session(rating_key: str) -> dict[str, Any]:
    """Library-path answer. No remux, no playlist URL, no session to resume."""
    return {
        "session_id": "",
        "rating_key": rating_key,
        "plan": "library",
        "reason": OPT_IN_REASON,
        "playable": False,
        "master_url": "",
        "title": "",
        "duration_ms": 0,
        "view_offset_ms": 0,
        "profile": "",
        "source_reason": "",
        "provider": "",
    }


@dataclass
class EngineSession:
    session_id: str
    token: str
    rating_key: str
    user_id: str
    plan: str
    reason: str
    playable: bool
    title: str
    duration_ms: int
    view_offset_ms: int
    profile_id: str
    source_reason: str = ""
    provider: str = ""
    directory: Optional[Path] = None
    process: Any = None
    cancelled: bool = False
    created_at: float = field(default_factory=time.time)

    def master_url(self) -> str:
        if not self.playable:
            return ""
        return f"/api/playback/sessions/{self.session_id}/{self.token}/master.m3u8"

    def public(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "rating_key": self.rating_key,
            "plan": self.plan,
            "reason": self.reason,
            "playable": self.playable,
            "master_url": self.master_url(),
            "title": self.title,
            "duration_ms": self.duration_ms,
            "view_offset_ms": self.view_offset_ms,
            "profile": self.profile_id,
            "source_reason": self.source_reason,
            "provider": self.provider,
        }


def reset_engine_sessions() -> None:
    with _LOCK:
        for session in _SESSIONS.values():
            _stop_process(session)
        _SESSIONS.clear()


def get_engine_session(session_id: str, *, user_id: str = "") -> EngineSession:
    with _LOCK:
        session = _SESSIONS.get(str(session_id or "").strip())
    if session is None:
        raise PlaybackError("Playback session is not valid.", status_code=404)
    if user_id and session.user_id and session.user_id != user_id:
        raise PlaybackError("Playback session is not valid.", status_code=404)
    return session


def session_for_token(session_id: str, token: str) -> EngineSession:
    session = get_engine_session(session_id)
    if not secrets.compare_digest(session.token, str(token or "")):
        raise PlaybackError("Playback session is not valid.", status_code=404)
    return session


def resolve_session_file(session: EngineSession, relative: str) -> Path:
    if session.directory is None:
        raise PlaybackError("This session has no stream.", status_code=404)
    raw = str(relative or "").strip().lstrip("/")
    if not raw or ".." in raw.split("/") or raw.startswith(("http:", "https:", "//")):
        raise PlaybackError("Invalid stream path", status_code=400)
    root = session.directory.resolve()
    candidate = (root / raw).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as error:
        raise PlaybackError("Invalid stream path", status_code=400) from error
    if not candidate.is_file():
        raise PlaybackError("Stream segment is not ready.", status_code=404)
    return candidate


def _stop_process(session: EngineSession) -> None:
    session.cancelled = True
    process = session.process
    if process is None:
        return
    try:
        if process.poll() is None:
            process.terminate()
    except OSError:
        return
    session.process = None


def open_engine_session(
    asset: MediaAsset,
    profile: DeviceProfile,
    *,
    user_id: str,
    title: str,
    duration_ms: int,
    view_offset_ms: int,
    data_dir: Path,
    runner: Any = None,
    ffmpeg: Optional[str] = None,
    force_reason: str = "",
    captions: Optional[Sequence[CaptionRendition]] = None,
    source: Any = None,
) -> EngineSession:
    planned = plan_playback(asset, profile, source=source)
    plan = str(planned["plan"])
    reason = str(planned["reason"])
    source_reason = str(planned.get("source_reason") or "")
    provider = str(planned.get("provider") or "")
    audio_codec = ""
    if plan == "audio":
        from projectionist.engine.audio import audio_encode_codec

        audio_codec = audio_encode_codec(profile)
        if not audio_codec:
            plan = "plex-fallback"
            reason = (
                f"{profile.id} has no audio codec this server can encode, "
                "so this title stays on the Plex path"
            )
            source_reason = ""
            provider = ""
    if force_reason:
        plan = "plex-fallback"
        reason = force_reason
        source_reason = ""
        provider = ""
    playable = (
        not force_reason
        and plan in {"remux", "direct", "audio"}
        and bool(asset.local_path)
        and asset.probe is not None
    )
    session = EngineSession(
        session_id=str(uuid.uuid4()),
        token=secrets.token_urlsafe(24),
        rating_key=asset.rating_key,
        user_id=str(user_id or ""),
        plan=plan,
        reason=reason,
        playable=False,
        title=title,
        duration_ms=max(0, int(duration_ms or 0)),
        view_offset_ms=max(0, int(view_offset_ms or 0)),
        profile_id=profile.id,
        source_reason=source_reason if plan == "source-transcode" else "",
        provider=provider if plan == "source-transcode" else "",
    )
    if playable:
        directory = Path(data_dir) / "engine" / "sessions" / session.session_id
        media_duration_ms = session.duration_ms
        if media_duration_ms <= 0 and asset.probe is not None and asset.probe.duration_s > 0:
            media_duration_ms = int(round(asset.probe.duration_s * 1000))
        try:
            if plan == "audio":
                from projectionist.engine.audio import start_audio_transcode

                def _still_wanted() -> bool:
                    return not session.cancelled

                def _attach(process: Any) -> bool:
                    with _LOCK:
                        if session.cancelled:
                            return False
                        session.process = process
                        return True

                start_audio_transcode(
                    Path(str(asset.local_path)),
                    directory,
                    probe=asset.probe,
                    file_size=int(asset.probe.size if asset.probe else 0),
                    duration_ms=media_duration_ms,
                    audio_codec=audio_codec,
                    runner=runner,
                    ffmpeg=ffmpeg,
                    captions=list(captions or []),
                    still_wanted=_still_wanted,
                    attach=_attach,
                    max_channels=int(getattr(profile, "max_channels", 0) or 0),
                )
            else:
                session.process = start_remux(
                    Path(str(asset.local_path)),
                    directory,
                    probe=asset.probe,
                    file_size=int(asset.probe.size if asset.probe else 0),
                    duration_ms=media_duration_ms,
                    runner=runner,
                    ffmpeg=ffmpeg,
                    captions=list(captions or []),
                )
        except FileNotFoundError:
            session.plan = "plex-fallback"
            session.reason = "ffmpeg is not available, so this title stays on the Plex path"
            session.playable = False
            session.source_reason = ""
            session.provider = ""
        else:
            session.directory = directory
            session.playable = True
            session.plan = plan
            session.reason = reason
    with _LOCK:
        _SESSIONS[session.session_id] = session
    return session


def stop_engine_session(session: EngineSession) -> dict[str, Any]:
    _stop_process(session)
    with _LOCK:
        _SESSIONS.pop(session.session_id, None)
    return {
        "ok": True,
        "session_id": session.session_id,
        "plan": session.plan,
        "reason": session.reason,
    }


def assert_session_allowed(user: Any, settings: Any, item: dict[str, Any]) -> None:
    """Youth ceiling matches library playback. Re-raised for the route."""
    from projectionist.library.playback import assert_youth_allowed as _allow

    try:
        _allow(user, settings, item)
    except YouthBlockedError:
        raise
