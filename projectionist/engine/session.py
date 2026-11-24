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
from projectionist.engine.quality import title_is_replaced
from projectionist.engine.remux import start_remux
from projectionist.engine.tries import failed_try_keys
from projectionist.engine.source import MediaAsset
from projectionist.library.playback import PlaybackError, YouthBlockedError

_LOCK = threading.Lock()
_SESSIONS: dict[str, "EngineSession"] = {}
# A live session publishes the media playlist after ffmpeg starts, which can
# be after the request. Unraid disks may still be spinning up, and an audio
# transcode may still be waiting for the shared slot, so the process is not
# attached yet. Wait for the file. 404 is an unknown or expired session.
_PLAYLIST_WAIT_S = 30.0
_FFMPEG_FAILED = "ffmpeg exited before the media playlist was published."
_PLAYLIST_NOT_READY = "The media playlist was not ready in time."

# The path token dies with the session, and also after this long without the
# playhead or the media playlist actually moving. A fetch renews the same token.
MEDIA_TOKEN_TTL_SECONDS = 6 * 60 * 60

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
    poster_url: str = ""
    backdrop_url: str = ""
    source_reason: str = ""
    provider: str = ""
    directory: Optional[Path] = None
    data_dir: Optional[Path] = None
    process: Any = None
    cancelled: bool = False
    master_seen: bool = False
    media_playlist_seen: bool = False
    created_at: float = field(default_factory=time.time)
    token_ttl_s: float = MEDIA_TOKEN_TTL_SECONDS
    token_expires_at: float = 0.0
    token_progress_ms: int = -1
    # Play asked for a preroll. Preparation runs during that bumper.
    warm: bool = False
    step: str = ""
    ready_at: Optional[float] = None
    handoff_at: Optional[float] = None
    ready_at_handoff: Optional[bool] = None
    library_fallback: bool = False
    library_session_id: str = ""
    prepare_frozen_ms: Optional[int] = None
    clock: Any = field(default=time.time, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self.token_expires_at <= 0:
            self.token_expires_at = float(self.created_at) + float(self.token_ttl_s)
        if self.token_progress_ms < 0:
            self.token_progress_ms = int(self.view_offset_ms or 0)

    def master_url(self) -> str:
        if not self.playable:
            return ""
        return f"/api/playback/sessions/{self.session_id}/{self.token}/master.m3u8"

    def public(self) -> dict[str, Any]:
        refresh_warm_start(self)
        body = {
            "session_id": self.session_id,
            "rating_key": self.rating_key,
            "plan": self.plan,
            "reason": self.reason,
            "playable": self.playable,
            "state": session_playback_state(self),
            "prepare_ms": prepare_milliseconds(self),
            "ready_at_handoff": self.ready_at_handoff,
            "step": self.step,
            "master_url": self.master_url(),
            "title": self.title,
            "poster_url": self.poster_url,
            "backdrop_url": self.backdrop_url,
            "duration_ms": self.duration_ms,
            "view_offset_ms": self.view_offset_ms,
            "profile": self.profile_id,
            "source_reason": self.source_reason,
            "provider": self.provider,
        }
        if self.library_session_id:
            body["library_session_id"] = self.library_session_id
        return body


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


def media_token_expired(session: EngineSession) -> bool:
    """True once the session has ended, or the play has been still for the TTL."""
    if session.cancelled:
        return True
    return float(session.clock()) >= float(session.token_expires_at)


def renew_media_token(session: EngineSession) -> None:
    """Keep the same path token alive while this play is still moving."""
    if session.cancelled:
        return
    session.token_expires_at = float(session.clock()) + float(session.token_ttl_s)


def session_for_token(session_id: str, token: str) -> EngineSession:
    session = get_engine_session(session_id)
    if not secrets.compare_digest(session.token, str(token or "")):
        raise PlaybackError("Playback session is not valid.", status_code=404)
    if media_token_expired(session):
        raise PlaybackError("Playback session is not valid.", status_code=404)
    return session


def _playlist_ready(session: EngineSession) -> bool:
    if session.directory is None:
        return False
    playlist = session.directory / "av" / "stream.m3u8"
    try:
        return playlist.is_file()
    except OSError:
        return False


def prepare_milliseconds(session: EngineSession) -> int:
    """How long preparation has taken, frozen once the film is ready or has moved on."""
    if session.prepare_frozen_ms is not None:
        return session.prepare_frozen_ms
    end = session.ready_at if session.ready_at is not None else float(session.clock())
    return max(0, int(round((end - session.created_at) * 1000)))


def refresh_warm_start(session: EngineSession) -> None:
    """Stamp readiness. A preroll whose engine died moves to the library plan.

    The member is still watching the bumper, so this is not a failed play.
    A session that was not opened for a preroll keeps today's failed state.
    """
    if session.ready_at is None and _playlist_ready(session):
        session.ready_at = float(session.clock())
    if (
        not session.warm
        or session.cancelled
        or session.handoff_at is not None
        or session.library_fallback
    ):
        return
    if session.ready_at is not None or not session.playable:
        return
    if not _process_exited(session.process):
        return
    session.library_fallback = True
    session.plan = "library"
    from projectionist.engine.warmup import set_step

    set_step(session, "falling_back")
    session.playable = False
    session.reason = (
        "The film was not ready during the preroll, so playback continues on the library path."
    )
    session.source_reason = ""
    session.provider = ""
    session.prepare_frozen_ms = max(
        0, int(round((float(session.clock()) - session.created_at) * 1000))
    )


def note_handoff(session: EngineSession) -> None:
    """Record whether the film was ready when the preroll handed off. The first call wins."""
    refresh_warm_start(session)
    if session.handoff_at is not None:
        return
    session.handoff_at = float(session.clock())
    session.ready_at_handoff = session_playback_state(session) == "ready"


def session_playback_state(session: EngineSession) -> str:
    """``preparing`` until the media playlist exists, then ``ready`` or ``failed``.

    A session that is not an engine playlist has no state. ffmpeg exiting
    before the file exists is failed, so the client can leave immediately.
    A process that has not started yet is still preparing.
    """
    if not session.playable or session.directory is None:
        return ""
    playlist = session.directory / "av" / "stream.m3u8"
    try:
        ready = playlist.is_file()
    except OSError:
        ready = False
    if ready:
        return "ready"
    if session.cancelled or _process_exited(session.process):
        return "failed"
    return "preparing"


def _media_playlist(relative: str) -> bool:
    return relative.rsplit("/", 1)[-1] == "stream.m3u8"


def _process_exited(process: Any) -> bool:
    """True once ffmpeg has a return code. A process that has not started is still live."""
    if process is None:
        return False
    try:
        return process.poll() is not None
    except OSError:
        return False


def _playlist_failure(session: EngineSession) -> Optional[PlaybackError]:
    """Why a live session still has no media playlist. None means keep waiting.

    An unknown or stopped session is a 404 from the lookup, before this runs.
    ffmpeg leaving without the file is its own error. A segment that is not
    the media playlist stays a 404 so the player can retry that one file.
    """
    if session.cancelled:
        return PlaybackError("Playback session is not valid.", status_code=404)
    if _process_exited(session.process):
        return PlaybackError(_FFMPEG_FAILED, status_code=502)
    return None


def resolve_session_file(
    session: EngineSession,
    relative: str,
    *,
    wait_s: Optional[float] = None,
    sleep: Any = time.sleep,
    clock: Any = time.monotonic,
) -> Path:
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
    if candidate.is_file():
        return candidate
    if not _media_playlist(raw):
        raise PlaybackError("Stream segment is not ready.", status_code=404)
    failure = _playlist_failure(session)
    if failure is not None:
        raise failure
    limit = float(_PLAYLIST_WAIT_S if wait_s is None else wait_s)
    if limit > 0:
        deadline = clock() + limit
        while clock() < deadline:
            if candidate.is_file():
                return candidate
            failure = _playlist_failure(session)
            if failure is not None:
                raise failure
            remaining = deadline - clock()
            if remaining <= 0:
                break
            sleep(min(0.2, remaining))
        if candidate.is_file():
            return candidate
        failure = _playlist_failure(session)
        if failure is not None:
            raise failure
    raise PlaybackError(_PLAYLIST_NOT_READY, status_code=503)


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
    poster_url: str = "",
    backdrop_url: str = "",
    duration_ms: int,
    view_offset_ms: int,
    data_dir: Path,
    runner: Any = None,
    ffmpeg: Optional[str] = None,
    force_reason: str = "",
    captions: Optional[Sequence[CaptionRendition]] = None,
    source: Any = None,
    ready_copy: Any = None,
    warm: bool = False,
) -> EngineSession:
    planned = plan_playback(
        asset,
        profile,
        source=source,
        failed_tries=failed_try_keys(data_dir),
        ready_copy=ready_copy,
        replaced=title_is_replaced(data_dir, str(asset.rating_key or "")),
    )
    play_asset = ready_copy if planned.get("from_copy") and ready_copy is not None else asset
    plan = str(planned["plan"])
    reason = str(planned["reason"])
    source_reason = str(planned.get("source_reason") or "")
    provider = str(planned.get("provider") or "")
    audio_codec = ""
    needs_audio = plan == "audio" or (plan == "try" and bool(planned.get("audio_transcode")))
    if needs_audio:
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
        and plan in {"remux", "direct", "audio", "try"}
        and bool(play_asset.local_path)
        and play_asset.probe is not None
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
        poster_url=str(poster_url or ""),
        backdrop_url=str(backdrop_url or ""),
        duration_ms=max(0, int(duration_ms or 0)),
        view_offset_ms=max(0, int(view_offset_ms or 0)),
        profile_id=profile.id,
        source_reason=source_reason if plan == "source-transcode" else "",
        provider=provider if plan == "source-transcode" else "",
        data_dir=Path(data_dir),
        warm=bool(warm),
    )
    if playable:
        directory = Path(data_dir) / "engine" / "sessions" / session.session_id
        media_duration_ms = session.duration_ms
        if (
            media_duration_ms <= 0
            and play_asset.probe is not None
            and play_asset.probe.duration_s > 0
        ):
            media_duration_ms = int(round(play_asset.probe.duration_s * 1000))
        try:
            if needs_audio:
                from projectionist.engine.audio import start_audio_transcode

                def _still_wanted() -> bool:
                    return not session.cancelled

                def _attach(process: Any) -> bool:
                    with _LOCK:
                        if session.cancelled:
                            return False
                        session.process = process
                        return True

                from projectionist.engine.warmup import set_step

                set_step(session, "encoding_audio")
                start_audio_transcode(
                    Path(str(play_asset.local_path)),
                    directory,
                    probe=play_asset.probe,
                    file_size=int(play_asset.probe.size if play_asset.probe else 0),
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
                from projectionist.engine.warmup import set_step

                set_step(session, "remuxing")
                session.process = start_remux(
                    Path(str(play_asset.local_path)),
                    directory,
                    probe=play_asset.probe,
                    file_size=int(play_asset.probe.size if play_asset.probe else 0),
                    duration_ms=media_duration_ms,
                    runner=runner,
                    ffmpeg=ffmpeg,
                    captions=list(captions or []),
                )
        except FileNotFoundError:
            from projectionist.engine.warmup import set_step

            session.plan = "plex-fallback"
            session.reason = "ffmpeg is not available, so this title stays on the Plex path"
            session.playable = False
            set_step(session, "falling_back")
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


def _media_request_is_playback(name: str) -> bool:
    """A media playlist or a segment means the player is still playing.

    The master playlist is the index. Fetching it alone does not move the film.
    """
    if name == "stream.m3u8":
        return True
    return name.endswith((".m4s", ".mp4", ".vtt"))


def note_session_media(session: EngineSession, relative: str) -> None:
    """Remember which playlist this client actually asked for."""
    name = str(relative or "").strip().lstrip("/").rsplit("/", 1)[-1]
    if name == "master.m3u8":
        session.master_seen = True
    elif name == "stream.m3u8":
        session.media_playlist_seen = True
    if _media_request_is_playback(name):
        renew_media_token(session)


def note_playback_progress(session: EngineSession, time_ms: int) -> bool:
    """Renew the path token when the playhead has moved. The same position does not."""
    current = max(0, int(time_ms or 0))
    if current == int(session.token_progress_ms):
        return False
    session.token_progress_ms = current
    session.view_offset_ms = current
    renew_media_token(session)
    return True


def _remember_fast_failed_try(session: EngineSession) -> None:
    """A try whose master was fetched and whose media playlist was not.

    Safari can reject the master and never ask for ``av/stream.m3u8``. That
    is a failed try, so the next play does not open another one. A play that
    did ask for the media playlist is left to the first-frame report.
    """
    if session.plan != "try" or session.data_dir is None:
        return
    if not session.master_seen or session.media_playlist_seen:
        return
    from projectionist.engine.tries import record_first_frame

    record_first_frame(
        session.data_dir,
        rating_key=session.rating_key,
        profile_id=session.profile_id,
        arrived=False,
    )


def stop_engine_session(session: EngineSession) -> dict[str, Any]:
    _remember_fast_failed_try(session)
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
