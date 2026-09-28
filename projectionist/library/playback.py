"""In-browser library Play — Plex universal HLS session (server-side only).

Household browsers never see ``X-Plex-Token`` or the PMS LAN URL. Playlists are
rewritten onto ``/api/library/playback/{session}/…`` the same way Live Channels
keeps Tunarr off the wire.
"""

from __future__ import annotations

import logging
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Mapping, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, quote, urlencode, urljoin, urlparse
from urllib.request import Request, urlopen

from projectionist.library.watch_state import resolve_plex_watch_token
from projectionist.youth.rating_gate import (
    content_rating_allowed,
    resolve_youth_max_rating,
    youth_gate_active,
)

logger = logging.getLogger(__name__)

PLEX_PRODUCT = "Projectionist"
PLEX_CLIENT_IDENTIFIER = "projectionist-library-play"
PROGRESS_THROTTLE_S = 10.0
RESUME_THRESHOLD_MS = 2 * 60 * 1000
SESSION_TTL_S = 6 * 60 * 60
MAX_RATING_KEY_LEN = 128
# Plex universal HLS masters live under this directory. Relative playlist lines
# like ``session/{id}/base/index.m3u8`` must resolve here — not at PMS root —
# or the proxy fetches ``/session/...`` and Plex returns 4xx → we surface 502.
UNIVERSAL_HLS_DIR = "video/:/transcode/universal"
UNIVERSAL_HLS_MASTER = f"{UNIVERSAL_HLS_DIR}/start.m3u8"

_SAFE_RATING_KEY = re.compile(r"^[A-Za-z0-9._:@/-]{1,128}$")
_SAFE_SESSION = re.compile(r"^[A-Za-z0-9._-]{8,80}$")
_SAFE_PATH = re.compile(r"^[A-Za-z0-9._~:@!$&'()*+,;=\-/%]+$")
_URI_LINE = re.compile(r'URI="([^"]+)"')
_TOKEN_QUERY_KEYS = frozenset(
    {
        "x-plex-token",
        "x_plex_token",
        "plex-token",
        "token",
    }
)
_YOUTH_BLOCKED = (
    "This title is above your youth rating limit, or it doesn’t have a rating "
    "we can allow."
)


class PlaybackError(Exception):
    """User-safe playback failure."""

    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = int(status_code)
        self.message = str(message)


class YouthBlockedError(PlaybackError):
    def __init__(self, message: str = _YOUTH_BLOCKED) -> None:
        super().__init__(message, status_code=403)


FetchFn = Callable[..., Tuple[bytes, str, int, str]]


@dataclass
class PlaybackSession:
    session_id: str
    user_id: str
    rating_key: str
    plex_base: str
    token: str
    token_source: Optional[str] = None
    duration_ms: int = 0
    view_offset_ms: int = 0
    title: str = ""
    show_title: str = ""
    season: Optional[int] = None
    episode: Optional[int] = None
    poster_url: str = ""
    content_rating: str = ""
    next_episode: Optional[Dict[str, Any]] = None
    plex_watch_url: str = ""
    last_progress_at: float = 0.0
    created_at: float = field(default_factory=time.time)
    last_offset_s: float = 0.0


_sessions: Dict[str, PlaybackSession] = {}
_lock = threading.Lock()


def validate_rating_key(raw: Any) -> str:
    """Reject empty, oversized, or path-traversal rating keys."""
    key = str(raw or "").strip()
    if not key:
        raise PlaybackError("A library title is required to play.")
    if len(key) > MAX_RATING_KEY_LEN:
        raise PlaybackError("That library key is not valid.")
    if ".." in key.split("/") or key.startswith(("http:", "https:", "//")):
        raise PlaybackError("That library key is not valid.")
    if not _SAFE_RATING_KEY.match(key):
        raise PlaybackError("That library key is not valid.")
    return key


def validate_session_id(raw: Any) -> str:
    sid = str(raw or "").strip()
    if not sid or not _SAFE_SESSION.match(sid):
        raise PlaybackError("Playback session is not valid.")
    return sid


def validate_playback_path(relative_path: str) -> str:
    """Normalize a proxied HLS path; reject traversal and odd schemes."""
    raw = str(relative_path or "").strip()
    if not raw:
        return "index.m3u8"
    if ".." in raw.split("/") or raw.startswith(("http:", "https:", "//")):
        raise PlaybackError("Invalid stream path")
    cleaned = raw.lstrip("/")
    if not _SAFE_PATH.match(cleaned):
        raise PlaybackError("Invalid stream path characters")
    return cleaned


def playback_proxy_base(session_id: str) -> str:
    return f"/api/library/playback/{quote(str(session_id), safe='')}"


def playlist_resolution_path(playlist_path: str) -> str:
    """Path used as the urljoin base when rewriting relative HLS URIs.

    Browser-facing masters are advertised as ``index.m3u8``, but Plex emits
    relatives against ``/video/:/transcode/universal/``. Bare ``session/…``
    proxy paths (from older rewrites) get the same prefix.
    """
    path = str(playlist_path or "").strip().lstrip("/")
    if not path or path in {"index.m3u8", "master.m3u8"}:
        return UNIVERSAL_HLS_MASTER
    if path.startswith("session/") and UNIVERSAL_HLS_DIR not in path:
        return f"{UNIVERSAL_HLS_DIR}/{path}"
    return path


def plex_fetch_path(relative_path: str) -> str:
    """Map a proxied relative path onto the PMS path to GET."""
    path = validate_playback_path(relative_path)
    if path in {"index.m3u8", "master.m3u8"}:
        return UNIVERSAL_HLS_MASTER
    if path.startswith("session/") and UNIVERSAL_HLS_DIR not in path:
        return f"{UNIVERSAL_HLS_DIR}/{path}"
    return path


def should_resume_from_offset(view_offset_ms: Any) -> bool:
    try:
        offset = int(view_offset_ms or 0)
    except (TypeError, ValueError):
        return False
    return offset >= RESUME_THRESHOLD_MS


def should_send_progress(last_sent_at: Any, now: Optional[float] = None) -> bool:
    stamp = time.time() if now is None else float(now)
    if last_sent_at in (None, 0, 0.0):
        return True
    try:
        prior = float(last_sent_at)
    except (TypeError, ValueError):
        return True
    return stamp - prior >= PROGRESS_THROTTLE_S


def strip_secret_query(uri: str) -> str:
    """Drop Plex token query params so rewritten playlists never leak credentials."""
    text = str(uri or "")
    if "?" not in text:
        return text
    path, query = text.split("?", 1)
    kept = [
        (key, value)
        for key, value in parse_qsl(query, keep_blank_values=True)
        if key.lower() not in _TOKEN_QUERY_KEYS
    ]
    if not kept:
        return path
    return f"{path}?{urlencode(kept, doseq=True)}"


def _row_int(row: Any, key: str) -> Optional[int]:
    if row is None:
        return None
    try:
        value = row[key]
    except (KeyError, IndexError, TypeError):
        return None
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _row_str(row: Any, key: str) -> str:
    if row is None:
        return ""
    try:
        return str(row[key] or "").strip()
    except (KeyError, IndexError, TypeError):
        return ""


def _episode_by_rating_key(db: Any, rating_key: str) -> Optional[Any]:
    with db.connect() as conn:
        return conn.execute(
            """
            SELECT e.*, s.title AS show_title, s.rating_key AS show_rating_key,
                   s.content_rating AS show_content_rating, s.poster_url AS show_poster_url
            FROM library_episodes e
            LEFT JOIN library_items s ON s.id = e.show_item_id
            WHERE e.rating_key = ?
            """,
            (rating_key,),
        ).fetchone()


def _pick_show_episode(db: Any, show_item_id: int) -> Optional[Any]:
    with db.connect() as conn:
        on_deck = conn.execute(
            """
            SELECT * FROM library_episodes
            WHERE show_item_id = ?
              AND view_offset_ms IS NOT NULL
              AND view_offset_ms > 0
            ORDER BY COALESCE(last_viewed_at, 0) DESC, season_number ASC, episode_number ASC
            LIMIT 1
            """,
            (int(show_item_id),),
        ).fetchone()
        if on_deck is not None:
            return on_deck
        unwatched = conn.execute(
            """
            SELECT * FROM library_episodes
            WHERE show_item_id = ?
              AND (view_count IS NULL OR view_count = 0)
            ORDER BY season_number ASC, episode_number ASC
            LIMIT 1
            """,
            (int(show_item_id),),
        ).fetchone()
        if unwatched is not None:
            return unwatched
        return conn.execute(
            """
            SELECT * FROM library_episodes
            WHERE show_item_id = ?
            ORDER BY season_number ASC, episode_number ASC
            LIMIT 1
            """,
            (int(show_item_id),),
        ).fetchone()


def _next_episode(db: Any, show_item_id: int, season: Optional[int], episode: Optional[int]) -> Optional[Dict[str, Any]]:
    if show_item_id <= 0 or season is None or episode is None:
        return None
    with db.connect() as conn:
        row = conn.execute(
            """
            SELECT rating_key, title, season_number, episode_number
            FROM library_episodes
            WHERE show_item_id = ?
              AND (
                    season_number > ?
                    OR (season_number = ? AND episode_number > ?)
                  )
            ORDER BY season_number ASC, episode_number ASC
            LIMIT 1
            """,
            (int(show_item_id), int(season), int(season), int(episode)),
        ).fetchone()
    if row is None:
        return None
    return {
        "rating_key": str(row["rating_key"] or ""),
        "title": str(row["title"] or ""),
        "season": _row_int(row, "season_number"),
        "episode": _row_int(row, "episode_number"),
    }


def _playable_from_episode(row: Any, *, show_title: str = "", show_rating: str = "", poster_url: str = "") -> Dict[str, Any]:
    duration = _row_int(row, "duration_ms") or 0
    if duration <= 0:
        runtime = _row_int(row, "runtime_minutes") or 0
        duration = runtime * 60 * 1000
    return {
        "rating_key": _row_str(row, "rating_key"),
        "media_type": "episode",
        "title": _row_str(row, "title") or "Episode",
        "show_title": show_title or _row_str(row, "show_title"),
        "season": _row_int(row, "season_number"),
        "episode": _row_int(row, "episode_number"),
        "duration_ms": duration,
        "view_offset_ms": _row_int(row, "view_offset_ms") or 0,
        "content_rating": _row_str(row, "content_rating") or show_rating or _row_str(row, "show_content_rating"),
        "poster_url": poster_url or _row_str(row, "show_poster_url"),
        "show_item_id": _row_int(row, "show_item_id") or 0,
    }


def resolve_playable_item(db: Any, rating_key: str) -> Dict[str, Any]:
    """Resolve a movie / episode / show key to a playable movie or episode."""
    key = validate_rating_key(rating_key)
    item = db.library_item_by_rating_key(key)
    if item is not None:
        media_type = _row_str(item, "media_type").lower()
        if media_type == "movie":
            duration = _row_int(item, "duration_ms") or 0
            if duration <= 0:
                runtime = _row_int(item, "runtime_minutes") or 0
                duration = runtime * 60 * 1000
            return {
                "rating_key": key,
                "media_type": "movie",
                "title": _row_str(item, "title") or "Movie",
                "show_title": "",
                "season": None,
                "episode": None,
                "duration_ms": duration,
                "view_offset_ms": _row_int(item, "view_offset_ms") or 0,
                "content_rating": _row_str(item, "content_rating"),
                "poster_url": _row_str(item, "poster_url"),
                "show_item_id": 0,
            }
        if media_type == "episode":
            return _playable_from_episode(item)
        if media_type == "show":
            episode = _pick_show_episode(db, int(item["id"]))
            if episode is None:
                raise PlaybackError("This show doesn’t have a playable episode yet.")
            playable = _playable_from_episode(
                episode,
                show_title=_row_str(item, "title"),
                show_rating=_row_str(item, "content_rating"),
                poster_url=_row_str(item, "poster_url"),
            )
            playable["show_item_id"] = int(item["id"])
            return playable
        raise PlaybackError("Only movies and TV episodes can play in Projectionist.")

    episode = _episode_by_rating_key(db, key)
    if episode is not None:
        return _playable_from_episode(episode)
    raise PlaybackError("Library item not found", status_code=404)


def assert_youth_allowed(user: Any, settings: Any, item: Mapping[str, Any]) -> None:
    if not youth_gate_active(user):
        return
    ceiling = resolve_youth_max_rating(settings)
    if not content_rating_allowed(item.get("content_rating"), max_rating=ceiling):
        raise YouthBlockedError()


def plex_identity_headers(token: str) -> Dict[str, str]:
    return {
        "X-Plex-Token": str(token or "").strip(),
        "X-Plex-Client-Identifier": PLEX_CLIENT_IDENTIFIER,
        "X-Plex-Product": PLEX_PRODUCT,
        "X-Plex-Platform": "Chrome",
        "X-Plex-Device": "Web",
        "X-Plex-Device-Name": "Projectionist",
        "Accept": "*/*",
    }


def universal_start_url(
    plex_base: str,
    rating_key: str,
    *,
    session_id: str,
    offset_seconds: float = 0,
) -> str:
    base = str(plex_base or "").strip().rstrip("/")
    params = {
        "path": f"/library/metadata/{rating_key}",
        "protocol": "hls",
        "fastSeek": "1",
        "directPlay": "0",
        "directStream": "1",
        "directStreamAudio": "1",
        "subtitleSize": "100",
        "audioBoost": "100",
        "location": "lan",
        "session": session_id,
        "offset": str(max(0, int(offset_seconds))),
        "copyts": "1",
        "hasMDE": "1",
        "mediaBufferSize": "102400",
        "X-Plex-Platform": "Chrome",
        "X-Plex-Product": PLEX_PRODUCT,
        "X-Plex-Client-Identifier": PLEX_CLIENT_IDENTIFIER,
        "X-Plex-Device": "Web",
        "X-Plex-Device-Name": "Projectionist",
    }
    return f"{base}/video/:/transcode/universal/start.m3u8?{urlencode(params)}"


def fetch_plex_bytes(
    url: str,
    *,
    headers: Optional[Mapping[str, str]] = None,
    timeout: int = 30,
    method: str = "GET",
) -> Tuple[bytes, str, int, str]:
    """GET/HEAD upstream Plex bytes. Returns (body, content_type, status, final_url)."""
    request = Request(url, method=method)
    for key, value in (headers or {}).items():
        if value:
            request.add_header(key, value)
    try:
        with urlopen(request, timeout=max(5, int(timeout or 30))) as response:
            content_type = str(response.headers.get("Content-Type") or "")
            status = int(getattr(response, "status", 200) or 200)
            final_url = str(getattr(response, "url", url) or url)
            body = response.read() if method != "HEAD" else b""
            return body, content_type, status, final_url
    except HTTPError as error:
        if hasattr(error, "read"):
            error.read()
        raise PlaybackError(
            f"Plex HTTP {error.code}",
            status_code=502,
        ) from error
    except URLError as error:
        raise PlaybackError("Plex is unreachable.", status_code=502) from error


def _proxy_uri_for_plex(
    uri: str,
    *,
    session_id: str,
    plex_base: str,
    playlist_path: str,
) -> str:
    text = str(uri or "").strip()
    if not text:
        return text
    proxy_root = playback_proxy_base(session_id)
    plex_root = str(plex_base or "").strip().rstrip("/")
    plex_host = urlparse(plex_root).netloc.lower()

    def _from_plex_path(path: str, query: str) -> str:
        rel = path.lstrip("/")
        suffix = ""
        if query:
            cleaned = strip_secret_query(f"placeholder{query}")
            if "?" in cleaned:
                suffix = "?" + cleaned.split("?", 1)[1]
        if not rel:
            return f"{proxy_root}/index.m3u8{suffix}"
        return f"{proxy_root}/{rel}{suffix}"

    if text.startswith(("http://", "https://")):
        parsed = urlparse(text)
        host = (parsed.hostname or "").lower()
        if plex_host and host and host != plex_host.split(":")[0] and parsed.netloc.lower() != plex_host:
            # Unknown host — drop it rather than leak a third-party absolute URL.
            return f"{proxy_root}/index.m3u8"
        query = f"?{parsed.query}" if parsed.query else ""
        return _from_plex_path(parsed.path or "", query)

    if text.startswith("/"):
        path = text
        query = ""
        if "?" in text:
            path, q = text.split("?", 1)
            query = f"?{q}"
        return _from_plex_path(path, query)

    resolved_playlist = playlist_resolution_path(playlist_path)
    playlist_dir = resolved_playlist.rsplit("/", 1)[0] if "/" in resolved_playlist else ""
    joined = urljoin(f"{playlist_dir}/" if playlist_dir else "", text)
    if joined.startswith(("http://", "https://", "/")):
        return _proxy_uri_for_plex(
            joined,
            session_id=session_id,
            plex_base=plex_root,
            playlist_path=resolved_playlist,
        )
    return f"{proxy_root}/{joined.lstrip('/')}"


def rewrite_plex_hls_playlist(
    body: str,
    *,
    session_id: str,
    plex_base: str,
    playlist_path: str,
) -> str:
    """Rewrite playlist URIs onto the Projectionist proxy; strip PMS host + token."""
    source = str(body or "")
    out_lines = []
    for line in source.splitlines():
        stripped = line.strip()
        if not stripped:
            out_lines.append(line)
            continue
        if stripped.startswith("#"):
            if "URI=" in stripped:

                def _repl(match: re.Match[str]) -> str:
                    original = match.group(1)
                    proxied = _proxy_uri_for_plex(
                        original,
                        session_id=session_id,
                        plex_base=plex_base,
                        playlist_path=playlist_path,
                    )
                    return f'URI="{proxied}"'

                out_lines.append(_URI_LINE.sub(_repl, line))
            else:
                out_lines.append(line)
            continue
        proxied = _proxy_uri_for_plex(
            stripped,
            session_id=session_id,
            plex_base=plex_base,
            playlist_path=playlist_path,
        )
        out_lines.append(proxied)
    ending = "\n" if source.endswith("\n") else ""
    rewritten = "\n".join(out_lines) + ending
    if plex_base:
        host = urlparse(plex_base).netloc
        if host and host.lower() in rewritten.lower():
            rewritten = re.sub(re.escape(host), "", rewritten, flags=re.IGNORECASE)
    if re.search(r"x-plex-token=", rewritten, re.IGNORECASE):
        rewritten = re.sub(r"([?&])X-Plex-Token=[^&\s]+", r"\1", rewritten, flags=re.IGNORECASE)
        rewritten = re.sub(r"[?&]+$", "", rewritten)
    return rewritten


def content_type_for_path(path: str, upstream: str = "") -> str:
    if upstream and "mpegurl" in upstream.lower():
        return upstream.split(";")[0].strip() or "application/vnd.apple.mpegurl"
    lower = path.lower()
    if lower.endswith(".m3u8") or lower.endswith(".m3u"):
        return "application/vnd.apple.mpegurl"
    if lower.endswith(".ts"):
        return "video/mp2t"
    if lower.endswith(".m4s") or lower.endswith(".mp4"):
        return "video/mp4"
    if lower.endswith(".vtt"):
        return "text/vtt"
    return upstream.split(";")[0].strip() if upstream else "application/octet-stream"


def is_playlist_path(path: str) -> bool:
    lower = str(path or "").lower()
    return lower.endswith(".m3u8") or lower.endswith(".m3u")


def _purge_expired_locked(now: Optional[float] = None) -> None:
    stamp = time.time() if now is None else float(now)
    expired = [
        sid
        for sid, session in _sessions.items()
        if stamp - session.created_at > SESSION_TTL_S
    ]
    for sid in expired:
        _sessions.pop(sid, None)


def get_session(session_id: str, *, user_id: str) -> PlaybackSession:
    sid = validate_session_id(session_id)
    with _lock:
        _purge_expired_locked()
        session = _sessions.get(sid)
        if session is None:
            raise PlaybackError("That playback session has ended.", status_code=404)
        if session.user_id and user_id and session.user_id != user_id:
            raise PlaybackError("That playback session belongs to someone else.", status_code=403)
        return session


def forget_session(session_id: str) -> None:
    with _lock:
        _sessions.pop(str(session_id or "").strip(), None)


def reset_playback_sessions() -> None:
    """Test helper — drop in-memory sessions."""
    with _lock:
        _sessions.clear()


def _put_session(session: PlaybackSession) -> None:
    with _lock:
        _purge_expired_locked()
        _sessions[session.session_id] = session


def update_local_view_offset(db: Any, rating_key: str, offset_ms: int, duration_ms: int = 0) -> None:
    key = str(rating_key or "").strip()
    if not key:
        return
    now = time.time()
    offset = max(0, int(offset_ms or 0))
    with db.connect() as conn:
        conn.execute(
            """
            UPDATE library_items
            SET view_offset_ms = ?, updated_at = ?
            WHERE rating_key = ?
            """,
            (offset, now, key),
        )
        conn.execute(
            """
            UPDATE library_episodes
            SET view_offset_ms = ?
            WHERE rating_key = ?
            """,
            (offset, key),
        )
        if duration_ms >= 30_000 and offset >= int(duration_ms) * 0.9:
            conn.execute(
                """
                UPDATE library_items
                SET view_count = CASE WHEN COALESCE(view_count, 0) < 1 THEN 1 ELSE view_count END,
                    last_viewed_at = ?,
                    view_offset_ms = 0,
                    updated_at = ?
                WHERE rating_key = ?
                """,
                (int(now), now, key),
            )
            conn.execute(
                """
                UPDATE library_episodes
                SET view_count = CASE WHEN COALESCE(view_count, 0) < 1 THEN 1 ELSE view_count END,
                    last_viewed_at = ?,
                    view_offset_ms = 0
                WHERE rating_key = ?
                """,
                (int(now), key),
            )


def plex_timeline_url(
    plex_base: str,
    rating_key: str,
    *,
    state: str,
    time_ms: int,
    duration_ms: int,
) -> str:
    base = str(plex_base or "").strip().rstrip("/")
    params = {
        "ratingKey": rating_key,
        "key": f"/library/metadata/{rating_key}",
        "state": state,
        "time": str(max(0, int(time_ms))),
        "duration": str(max(0, int(duration_ms))),
        "X-Plex-Client-Identifier": PLEX_CLIENT_IDENTIFIER,
        "X-Plex-Product": PLEX_PRODUCT,
    }
    return f"{base}/:/timeline?{urlencode(params)}"


def _timeline_state(raw: str) -> str:
    state = str(raw or "playing").strip().lower()
    if state in {"playing", "paused", "stopped", "buffering"}:
        return state
    return "playing"


def send_plex_timeline(
    session: PlaybackSession,
    *,
    state: str,
    time_ms: int,
    duration_ms: int,
    fetch: Optional[FetchFn] = None,
) -> None:
    fetch = fetch or fetch_plex_bytes
    url = plex_timeline_url(
        session.plex_base,
        session.rating_key,
        state=_timeline_state(state),
        time_ms=time_ms,
        duration_ms=duration_ms,
    )
    try:
        fetch(url, headers=plex_identity_headers(session.token), timeout=10)
    except PlaybackError:
        logger.debug("Plex timeline failed for %s", session.rating_key, exc_info=True)


def stop_plex_session(
    session: PlaybackSession,
    *,
    fetch: Optional[FetchFn] = None,
) -> None:
    fetch = fetch or fetch_plex_bytes
    base = session.plex_base.rstrip("/")
    url = f"{base}/video/:/transcode/universal/stop?session={quote(session.session_id)}"
    try:
        fetch(url, headers=plex_identity_headers(session.token), timeout=10)
    except PlaybackError:
        logger.debug("Plex universal/stop failed for %s", session.session_id, exc_info=True)


def start_plex_hls(
    session: PlaybackSession,
    *,
    offset_seconds: float,
    fetch: Optional[FetchFn] = None,
) -> None:
    fetch = fetch or fetch_plex_bytes
    url = universal_start_url(
        session.plex_base,
        session.rating_key,
        session_id=session.session_id,
        offset_seconds=offset_seconds,
    )
    fetch(url, headers=plex_identity_headers(session.token), timeout=30)
    session.last_offset_s = max(0.0, float(offset_seconds))


def session_public_payload(session: PlaybackSession, *, can_resume: Optional[bool] = None) -> Dict[str, Any]:
    offset = int(session.view_offset_ms or 0)
    resume = should_resume_from_offset(offset) if can_resume is None else bool(can_resume)
    return {
        "session_id": session.session_id,
        "stream_url": f"{playback_proxy_base(session.session_id)}/index.m3u8",
        "duration_ms": int(session.duration_ms or 0),
        "view_offset_ms": offset,
        "title": session.title,
        "show_title": session.show_title,
        "season": session.season,
        "episode": session.episode,
        "can_resume": resume,
        "next_episode": session.next_episode,
        "poster_url": session.poster_url,
        "rating_key": session.rating_key,
        "plex_watch_url": session.plex_watch_url,
    }


def start_playback(
    db: Any,
    settings: Any,
    *,
    rating_key: str,
    user: Any,
    start_over: bool = False,
    fetch: Optional[FetchFn] = None,
) -> Dict[str, Any]:
    fetch = fetch or fetch_plex_bytes
    playable = resolve_playable_item(db, rating_key)
    assert_youth_allowed(user, settings, playable)
    plex_url = str(getattr(settings, "plex_url", "") or "").strip()
    if not plex_url:
        raise PlaybackError("Plex isn’t connected.", status_code=503)
    resolved = resolve_plex_watch_token(
        db,
        settings,
        user_id=str(getattr(user, "id", "") or ""),
    )
    token = str(resolved.get("token") or "").strip()
    if not token:
        raise PlaybackError("Plex isn’t connected.", status_code=503)

    offset_ms = 0 if start_over else int(playable.get("view_offset_ms") or 0)
    session_id = str(uuid.uuid4())
    next_ep = None
    show_item_id = int(playable.get("show_item_id") or 0)
    if playable.get("media_type") == "episode" and show_item_id:
        next_ep = _next_episode(db, show_item_id, playable.get("season"), playable.get("episode"))

    from projectionist.connectors.plex import plex_watch_url as plex_web_watch_url
    from projectionist.connectors.plex import cached_machine_identifier

    machine_id = ""
    try:
        machine_id = cached_machine_identifier(plex_url, token, timeout=5)
    except Exception:  # noqa: BLE001
        machine_id = ""

    session = PlaybackSession(
        session_id=session_id,
        user_id=str(getattr(user, "id", "") or ""),
        rating_key=str(playable["rating_key"]),
        plex_base=plex_url.rstrip("/"),
        token=token,
        token_source=str(resolved.get("source") or "") or None,
        duration_ms=int(playable.get("duration_ms") or 0),
        view_offset_ms=offset_ms,
        title=str(playable.get("title") or ""),
        show_title=str(playable.get("show_title") or ""),
        season=playable.get("season"),
        episode=playable.get("episode"),
        poster_url=str(playable.get("poster_url") or ""),
        content_rating=str(playable.get("content_rating") or ""),
        next_episode=next_ep,
        plex_watch_url=plex_web_watch_url(machine_id, str(playable["rating_key"])),
        last_offset_s=offset_ms / 1000.0,
    )
    start_plex_hls(session, offset_seconds=session.last_offset_s, fetch=fetch)
    _put_session(session)
    return session_public_payload(session, can_resume=should_resume_from_offset(offset_ms) and not start_over)


def seek_playback(
    session: PlaybackSession,
    offset_ms: int,
    *,
    fetch: Optional[FetchFn] = None,
) -> Dict[str, Any]:
    fetch = fetch or fetch_plex_bytes
    offset = max(0, int(offset_ms or 0))
    stop_plex_session(session, fetch=fetch)
    session.view_offset_ms = offset
    start_plex_hls(session, offset_seconds=offset / 1000.0, fetch=fetch)
    _put_session(session)
    return session_public_payload(session, can_resume=False)


def report_progress(
    db: Any,
    session: PlaybackSession,
    *,
    state: str,
    time_ms: int,
    duration_ms: int,
    now: Optional[float] = None,
    force: bool = False,
    fetch: Optional[FetchFn] = None,
) -> Dict[str, Any]:
    fetch = fetch or fetch_plex_bytes
    stamp = time.time() if now is None else float(now)
    mapped = _timeline_state(state)
    if mapped == "stopped":
        force = True
    if not force and not should_send_progress(session.last_progress_at, stamp):
        return {"ok": True, "throttled": True}
    session.last_progress_at = stamp
    session.view_offset_ms = max(0, int(time_ms or 0))
    if duration_ms:
        session.duration_ms = int(duration_ms)
    send_plex_timeline(
        session,
        state=mapped,
        time_ms=session.view_offset_ms,
        duration_ms=int(session.duration_ms or duration_ms or 0),
        fetch=fetch,
    )
    update_local_view_offset(
        db,
        session.rating_key,
        session.view_offset_ms,
        int(session.duration_ms or 0),
    )
    _put_session(session)
    return {"ok": True, "throttled": False}


def stop_playback(
    db: Any,
    session: PlaybackSession,
    *,
    time_ms: Optional[int] = None,
    duration_ms: Optional[int] = None,
    fetch: Optional[FetchFn] = None,
) -> Dict[str, Any]:
    fetch = fetch or fetch_plex_bytes
    if time_ms is not None:
        session.view_offset_ms = max(0, int(time_ms))
    if duration_ms:
        session.duration_ms = int(duration_ms)
    send_plex_timeline(
        session,
        state="stopped",
        time_ms=int(session.view_offset_ms or 0),
        duration_ms=int(session.duration_ms or 0),
        fetch=fetch,
    )
    stop_plex_session(session, fetch=fetch)
    update_local_view_offset(
        db,
        session.rating_key,
        int(session.view_offset_ms or 0),
        int(session.duration_ms or 0),
    )
    forget_session(session.session_id)
    return {"ok": True}


def proxy_session_asset(
    session: PlaybackSession,
    relative_path: str,
    *,
    fetch: Optional[FetchFn] = None,
) -> Dict[str, Any]:
    fetch = fetch or fetch_plex_bytes
    path = validate_playback_path(relative_path)
    if path in {"index.m3u8", "master.m3u8"}:
        url = universal_start_url(
            session.plex_base,
            session.rating_key,
            session_id=session.session_id,
            offset_seconds=session.last_offset_s,
        )
        rewrite_base = UNIVERSAL_HLS_MASTER
    else:
        base = session.plex_base.rstrip("/")
        upstream = plex_fetch_path(path)
        url = f"{base}/{upstream.lstrip('/')}"
        rewrite_base = upstream
    body, upstream_ct, status, final_url = fetch(
        url,
        headers=plex_identity_headers(session.token),
        timeout=30,
    )
    media_type = content_type_for_path(path, upstream_ct)
    if is_playlist_path(path):
        final_path = urlparse(str(final_url or "")).path.lstrip("/")
        if final_path and UNIVERSAL_HLS_DIR in final_path:
            rewrite_base = final_path
        text = body.decode("utf-8", errors="replace")
        rewritten = rewrite_plex_hls_playlist(
            text,
            session_id=session.session_id,
            plex_base=session.plex_base,
            playlist_path=rewrite_base,
        )
        return {
            "body": rewritten.encode("utf-8"),
            "media_type": "application/vnd.apple.mpegurl",
            "status": status,
            "path": path,
        }
    return {
        "body": body,
        "media_type": media_type,
        "status": status,
        "path": path,
    }


def iter_chunked(data: bytes, size: int = 64 * 1024):
    view = memoryview(data)
    for start in range(0, len(view), size):
        yield bytes(view[start : start + size])
