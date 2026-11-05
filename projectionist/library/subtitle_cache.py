"""One household-language subtitle file per movie and episode.

Files live at ``DATA_DIR/subtitles/{rating_key}/{language}.srt`` and are served
as WebVTT by the authenticated ``/api/library/items/{key}/subtitles/{id}/file``
route under the stream id ``cached-{language}``. Play and Live list that file
first, so turning captions on never waits on a download.

How a file is obtained, in order (:func:`ensure_household_subtitle`):

1. The cache already holds a usable file. Stop.
2. Plex has a drawable household-language text track. Copy it. No
   OpenSubtitles call.
3. OpenSubtitles, only when ``PROJECTIONIST_OPENSUBTITLES_API_KEY`` is set:
   moviehash of the readable media file, then the IMDB id (and year) for a
   movie, or the parent show's IMDB id plus season and episode for an episode.

Bitmap tracks are skipped. An empty or malformed body is never cached.
"""

from __future__ import annotations

import logging
import re
import threading
import urllib.parse
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from projectionist.library import subtitle_state
from projectionist.library.episode_investigate.capabilities import opensubtitles_api_key

logger = logging.getLogger(__name__)

SUBTITLES_DIRNAME = "subtitles"
CACHED_STREAM_PREFIX = "cached-"
OPENSUBTITLES_API = "https://api.opensubtitles.com/api/v1"
OPENSUBTITLES_USER_AGENT = "Projectionist v1"
#: Each OpenSubtitles HTTP call.
OPENSUBTITLES_TIMEOUT_SECONDS = 15
#: Whole OpenSubtitles step for one title; a hang past this fails that title only.
TITLE_LOOKUP_TIMEOUT_SECONDS = 45
MAX_SUBTITLE_BYTES = 2 * 1024 * 1024

NO_KEY_NOTE = (
    "OpenSubtitles isn’t set up, so Projectionist can only save subtitles Plex already has."
)
NONE_FOUND_NOTE = "No text subtitles were found for this title in your language."
FETCH_FAILED_NOTE = "Couldn’t fetch subtitles for this title right now. Projectionist will try again later."
QUOTA_NOTE = "OpenSubtitles download limit reached. Projectionist will try again after it resets."

_TEXT_SUFFIXES = (".srt", ".vtt", ".webvtt", ".ass", ".ssa", ".txt", "")
_TIMING_RE = re.compile(r"\d{1,2}:\d{2}(?::\d{2})?[.,]\d{1,3}\s*-->\s*\d{1,2}:\d{2}")
_SAFE_KEY_RE = re.compile(r"[^A-Za-z0-9_.-]")

# OpenSubtitles wants ISO 639-1; Plex and settings sometimes carry 639-2.
_ISO2 = {
    "eng": "en", "spa": "es", "fra": "fr", "fre": "fr", "deu": "de", "ger": "de",
    "ita": "it", "por": "pt", "jpn": "ja", "kor": "ko", "zho": "zh", "chi": "zh",
    "rus": "ru", "nld": "nl", "dut": "nl", "swe": "sv", "nor": "no", "dan": "da",
    "fin": "fi", "pol": "pl", "tur": "tr", "ara": "ar", "heb": "he", "hin": "hi",
    "ell": "el", "gre": "el", "ces": "cs", "cze": "cs", "hun": "hu", "tha": "th",
}


class OpenSubtitlesQuota(RuntimeError):
    """The account hit its download allowance; ``reset_at`` is epoch seconds when known."""

    def __init__(self, message: str, *, reset_at: Optional[float] = None) -> None:
        super().__init__(message)
        self.reset_at = reset_at


def iso2(code: Any) -> str:
    text = str(code or "").strip().lower().replace("_", "-").split("-", 1)[0]
    return _ISO2.get(text, text)


def household_languages(settings: Any) -> List[str]:
    from projectionist.library.subtitles import preferred_subtitle_languages

    out: List[str] = []
    for code in preferred_subtitle_languages(settings):
        short = iso2(code)
        if short and short not in out:
            out.append(short)
    return out or ["en"]


def household_language(settings: Any) -> str:
    return household_languages(settings)[0]


def title_language_is_household(original_language: Any, settings: Any) -> Optional[bool]:
    """``None`` when the title language is unknown."""
    lang = iso2(original_language)
    if not lang:
        return None
    return lang == household_language(settings)


def resolve_subtitles_root(data_dir: Optional[Path] = None) -> Path:
    if data_dir is not None:
        return Path(data_dir) / SUBTITLES_DIRNAME
    from projectionist.logging_config import resolve_data_dir

    return resolve_data_dir() / SUBTITLES_DIRNAME


def _safe_key(rating_key: Any) -> str:
    key = _SAFE_KEY_RE.sub("_", str(rating_key or "").strip())
    return key.strip(".") or ""


def cache_path(rating_key: Any, language: str, *, data_dir: Optional[Path] = None) -> Optional[Path]:
    key = _safe_key(rating_key)
    lang = _safe_key(iso2(language))
    if not key or not lang:
        return None
    return resolve_subtitles_root(data_dir) / key / f"{lang}.srt"


def is_usable_subtitle_text(text: Any) -> bool:
    """A body we would draw: has timed cues and visible text, not an HTML error page."""
    body = str(text or "").strip()
    if len(body) < 10 or not _TIMING_RE.search(body):
        return False
    head = body[:200].lower()
    if head.startswith("<!doctype") or head.startswith("<html"):
        return False
    cue_text = [
        line
        for line in body.splitlines()
        if line.strip() and "-->" not in line and not line.strip().isdigit()
        and not line.strip().upper().startswith("WEBVTT")
    ]
    return bool(cue_text)


def _decode(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def read_cached(
    rating_key: Any, languages: Sequence[str], *, data_dir: Optional[Path] = None
) -> Optional[Tuple[str, Path]]:
    for code in languages:
        path = cache_path(rating_key, code, data_dir=data_dir)
        if path is None or not path.is_file():
            continue
        try:
            if is_usable_subtitle_text(path.read_text(encoding="utf-8", errors="replace")):
                return iso2(code), path
        except OSError:
            continue
    return None


def write_cached(
    rating_key: Any, language: str, text: str, *, data_dir: Optional[Path] = None
) -> Optional[Path]:
    if not is_usable_subtitle_text(text):
        return None
    path = cache_path(rating_key, language, data_dir=data_dir)
    if path is None:
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".srt.tmp")
    tmp.write_text(text.replace("\r\n", "\n").replace("\r", "\n"), encoding="utf-8")
    tmp.replace(path)
    return path


def cached_stream_id(language: str) -> str:
    return f"{CACHED_STREAM_PREFIX}{iso2(language)}"


def language_from_cached_stream_id(stream_id: Any) -> str:
    text = str(stream_id or "").strip()
    if not text.startswith(CACHED_STREAM_PREFIX):
        return ""
    return _safe_key(text[len(CACHED_STREAM_PREFIX):])


_LANGUAGE_NAMES = {
    "en": "English", "es": "Spanish", "fr": "French", "de": "German", "it": "Italian",
    "pt": "Portuguese", "ja": "Japanese", "ko": "Korean", "zh": "Chinese", "ru": "Russian",
    "nl": "Dutch", "sv": "Swedish", "no": "Norwegian", "da": "Danish", "fi": "Finnish",
    "pl": "Polish", "tr": "Turkish", "ar": "Arabic", "he": "Hebrew", "hi": "Hindi",
    "el": "Greek", "cs": "Czech", "hu": "Hungarian", "th": "Thai",
}


def _language_label(code: str) -> str:
    return _LANGUAGE_NAMES.get(code, code.upper())


def cached_track_row(rating_key: Any, language: str) -> Dict[str, Any]:
    code = iso2(language)
    sid = cached_stream_id(code)
    name = _language_label(code)
    return {
        "id": sid,
        "language": name,
        "language_code": code,
        "title": "",
        "display_title": name,
        "label": name,
        "format": "srt",
        "key": "",
        "forced": False,
        "hearing_impaired": False,
        "selected": False,
        "default": False,
        "external": True,
        "searchable": False,
        "cached": True,
        "renderable": True,
        "image": False,
        "proxy_url": (
            f"/api/library/items/{urllib.parse.quote(str(rating_key), safe='')}"
            f"/subtitles/{urllib.parse.quote(sid, safe='')}/file"
        ),
        "unavailable_reason": "",
    }


def cached_track_rows(
    rating_key: Any, settings: Any, *, data_dir: Optional[Path] = None
) -> List[Dict[str, Any]]:
    hit = read_cached(rating_key, household_languages(settings), data_dir=data_dir)
    if hit is None:
        return []
    return [cached_track_row(rating_key, hit[0])]


def cached_subtitle_vtt(
    rating_key: Any, stream_id: Any, *, data_dir: Optional[Path] = None
) -> Optional[str]:
    from projectionist.library.subtitles import srt_to_vtt

    lang = language_from_cached_stream_id(stream_id)
    if not lang:
        return None
    hit = read_cached(rating_key, [lang], data_dir=data_dir)
    if hit is None:
        return None
    return srt_to_vtt(hit[1].read_text(encoding="utf-8", errors="replace"))


# -- Title context ---------------------------------------------------------


def _imdb_numeric(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text.startswith("tt"):
        text = text[2:]
    return text.lstrip("0") if text.isdigit() else ""


def title_subtitle_context(db: Any, rating_key: Any) -> Dict[str, Any]:
    """Media type, title language, and lookup ids for one movie or episode."""
    key = str(rating_key or "").strip()
    ctx: Dict[str, Any] = {
        "rating_key": key,
        "media_type": "",
        "original_language": "",
        "imdb_id": "",
        "parent_imdb_id": "",
        "season": None,
        "episode": None,
        "year": None,
        "title": "",
    }
    if db is None or not key:
        return ctx
    try:
        with db.connect() as conn:
            row = conn.execute(
                "SELECT media_type, original_language, imdb_id, year, title "
                "FROM library_items WHERE rating_key = ?",
                (key,),
            ).fetchone()
            if row is not None:
                ctx.update(
                    media_type=str(row["media_type"] or ""),
                    original_language=str(row["original_language"] or ""),
                    imdb_id=str(row["imdb_id"] or ""),
                    year=row["year"],
                    title=str(row["title"] or ""),
                )
                return ctx
            ep = conn.execute(
                """
                SELECT e.season_number, e.episode_number, e.title AS episode_title,
                       s.imdb_id AS show_imdb, s.original_language AS show_language,
                       s.title AS show_title
                FROM library_episodes e
                JOIN library_items s ON s.id = e.show_item_id
                WHERE e.rating_key = ?
                """,
                (key,),
            ).fetchone()
    except Exception as error:  # noqa: BLE001
        logger.debug("subtitle context lookup failed for %s: %s", key, error)
        return ctx
    if ep is not None:
        ctx.update(
            media_type="episode",
            original_language=str(ep["show_language"] or ""),
            parent_imdb_id=str(ep["show_imdb"] or ""),
            season=ep["season_number"],
            episode=ep["episode_number"],
            title=str(ep["episode_title"] or ep["show_title"] or ""),
        )
    return ctx


# -- Plex copy ---------------------------------------------------------------


def _plex_text_candidates(
    streams: Sequence[Any], languages: Sequence[str], *, prefer_sdh: bool
) -> List[Tuple[str, Dict[str, Any]]]:
    from projectionist.library.subtitles import language_matches, subtitle_is_renderable

    out: List[Tuple[str, Dict[str, Any]]] = []
    rows = [s.to_dict() if hasattr(s, "to_dict") else dict(s) for s in streams]
    for code in languages:
        matches = [
            row
            for row in rows
            if subtitle_is_renderable(row) and language_matches(row, code)
        ]
        matches.sort(
            key=lambda row: (
                0 if row.get("forced") else 1,
                1 if (prefer_sdh and row.get("hearing_impaired")) else 0,
                0 if row.get("hearing_impaired") else 1,
            ),
            reverse=True,
        )
        out.extend((iso2(code), row) for row in matches)
    return out


def _fetch_plex_text(client: Any, stream: Mapping[str, Any]) -> str:
    from projectionist.library.subtitles import subtitle_fetch_paths

    for path in subtitle_fetch_paths(stream):
        try:
            raw = client.fetch_subtitle_bytes(path)
        except Exception as error:  # noqa: BLE001
            logger.debug("Plex subtitle fetch failed path=%s: %s", path, error)
            continue
        text = _decode(raw)
        if is_usable_subtitle_text(text):
            return text
    return ""


# -- OpenSubtitles -----------------------------------------------------------


class OpenSubtitlesClient:
    """Minimal REST client: search, then download one file. Short timeouts."""

    def __init__(
        self,
        api_key: str,
        *,
        timeout: int = OPENSUBTITLES_TIMEOUT_SECONDS,
        request_json: Optional[Callable[..., Any]] = None,
        request_bytes: Optional[Callable[..., bytes]] = None,
    ) -> None:
        from projectionist.connectors import http

        self.api_key = api_key
        self.timeout = timeout
        self._json = request_json or http.request_json
        self._bytes = request_bytes or http.request_bytes

    def _headers(self) -> Dict[str, str]:
        return {
            "Api-Key": self.api_key,
            "Accept": "application/json",
            "User-Agent": OPENSUBTITLES_USER_AGENT,
        }

    def search(self, params: Mapping[str, Any]) -> List[Dict[str, Any]]:
        query = urllib.parse.urlencode({k: v for k, v in sorted(params.items()) if v not in (None, "")})
        try:
            payload = self._json(
                f"{OPENSUBTITLES_API}/subtitles?{query}",
                headers=self._headers(),
                timeout=self.timeout,
            )
        except RuntimeError as error:
            _raise_if_quota(error)
            raise
        rows = payload.get("data") if isinstance(payload, Mapping) else None
        return [row for row in rows or [] if isinstance(row, Mapping)]

    def download(self, file_id: Any) -> Tuple[bytes, Optional[int], Optional[float]]:
        try:
            payload = self._json(
                f"{OPENSUBTITLES_API}/download",
                method="POST",
                headers=self._headers(),
                body={"file_id": int(file_id), "sub_format": "srt"},
                timeout=self.timeout,
            )
        except RuntimeError as error:
            _raise_if_quota(error)
            raise
        if not isinstance(payload, Mapping) or not payload.get("link"):
            raise RuntimeError("OpenSubtitles returned no download link")
        remaining = payload.get("remaining")
        try:
            remaining_i: Optional[int] = int(remaining) if remaining is not None else None
        except (TypeError, ValueError):
            remaining_i = None
        reset_at = _parse_reset(payload.get("reset_time_utc"))
        body = self._bytes(
            str(payload["link"]),
            headers={"User-Agent": OPENSUBTITLES_USER_AGENT},
            timeout=self.timeout,
            max_bytes=MAX_SUBTITLE_BYTES,
        )
        return body, remaining_i, reset_at


def _parse_reset(value: Any) -> Optional[float]:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        from datetime import datetime

        return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _raise_if_quota(error: BaseException) -> None:
    text = str(error)
    if "HTTP 406" in text or "HTTP 429" in text:
        raise OpenSubtitlesQuota(QUOTA_NOTE) from error


def opensubtitles_queries(ctx: Mapping[str, Any], moviehash: str = "") -> List[Dict[str, Any]]:
    """Lookups in order: file hash, then IMDB (movie) or parent IMDB + S/E (episode)."""
    queries: List[Dict[str, Any]] = []
    if moviehash:
        queries.append({"moviehash": moviehash})
    if ctx.get("media_type") == "episode":
        parent = _imdb_numeric(ctx.get("parent_imdb_id"))
        season, episode = ctx.get("season"), ctx.get("episode")
        if parent and season is not None and episode is not None:
            queries.append(
                {
                    "parent_imdb_id": parent,
                    "season_number": int(season),
                    "episode_number": int(episode),
                }
            )
    else:
        imdb = _imdb_numeric(ctx.get("imdb_id"))
        if imdb:
            query: Dict[str, Any] = {"imdb_id": imdb}
            if ctx.get("year"):
                query["year"] = int(ctx["year"])
            queries.append(query)
    return queries


def pick_opensubtitles_file(
    rows: Sequence[Mapping[str, Any]], languages: Sequence[str], *, prefer_sdh: bool = False
) -> Optional[Tuple[str, Any]]:
    """``(language, file_id)`` for the best text hit, household language order."""
    for code in languages:
        wanted = iso2(code)
        ranked: List[Tuple[tuple, Any]] = []
        for row in rows:
            attrs = row.get("attributes") if isinstance(row.get("attributes"), Mapping) else {}
            if iso2(attrs.get("language")) != wanted:
                continue
            if attrs.get("foreign_parts_only"):
                continue
            for item in attrs.get("files") or []:
                if not isinstance(item, Mapping) or item.get("file_id") is None:
                    continue
                name = str(item.get("file_name") or "").lower()
                suffix = Path(name).suffix
                if suffix not in _TEXT_SUFFIXES:
                    continue
                sdh = bool(attrs.get("hearing_impaired"))
                score = (
                    1 if attrs.get("moviehash_match") else 0,
                    1 if (prefer_sdh and sdh) else 0,
                    0 if sdh else 1,
                    int(attrs.get("download_count") or 0),
                )
                ranked.append((score, item["file_id"]))
        if ranked:
            ranked.sort(key=lambda pair: pair[0], reverse=True)
            return wanted, ranked[0][1]
    return None


def _media_moviehash(settings: Any, client: Any, rating_key: str) -> str:
    if client is None:
        return ""
    try:
        paths = client.media_file_paths(rating_key)
    except Exception as error:  # noqa: BLE001
        logger.debug("Plex media path lookup failed for %s: %s", rating_key, error)
        return ""
    from projectionist.library.episode_investigate.oshash import file_oshash
    from projectionist.library.episode_investigate.path_map import resolve_visible_media_path

    for raw in paths[:1]:
        try:
            visible = resolve_visible_media_path(raw, settings) or raw
        except Exception:  # noqa: BLE001
            visible = raw
        if visible and Path(visible).is_file():
            return file_oshash(visible) or ""
    return ""


def _opensubtitles_lookup(
    client: OpenSubtitlesClient,
    ctx: Mapping[str, Any],
    moviehash: str,
    languages: Sequence[str],
    *,
    prefer_sdh: bool,
) -> Dict[str, Any]:
    """Run the ordered lookups. Returns ``{text, language, remaining, reset_at, error}``."""
    lang_param = ",".join(sorted(dict.fromkeys(iso2(code) for code in languages)))
    last_error = ""
    for query in opensubtitles_queries(ctx, moviehash):
        try:
            rows = client.search({**query, "languages": lang_param})
        except OpenSubtitlesQuota:
            raise
        except Exception as error:  # noqa: BLE001
            last_error = str(error)[:200]
            continue
        pick = pick_opensubtitles_file(rows, languages, prefer_sdh=prefer_sdh)
        if pick is None:
            continue
        language, file_id = pick
        try:
            body, remaining, reset_at = client.download(file_id)
        except OpenSubtitlesQuota:
            raise
        except Exception as error:  # noqa: BLE001
            last_error = str(error)[:200]
            continue
        text = _decode(body)
        if not is_usable_subtitle_text(text):
            last_error = "OpenSubtitles returned an empty or unreadable file"
            continue
        return {
            "text": text,
            "language": language,
            "remaining": remaining,
            "reset_at": reset_at,
            "error": "",
        }
    return {"text": "", "language": "", "remaining": None, "reset_at": None, "error": last_error}


def _run_with_timeout(fn: Callable[[], Dict[str, Any]], timeout: float) -> Dict[str, Any]:
    """Bound one title's lookup. A stuck socket fails this title, not the run."""
    holder: Dict[str, Any] = {}

    def _target() -> None:
        try:
            holder["result"] = fn()
        except BaseException as error:  # noqa: BLE001
            holder["error"] = error

    worker = threading.Thread(target=_target, name="opensubtitles-lookup", daemon=True)
    worker.start()
    worker.join(timeout)
    if worker.is_alive():
        raise TimeoutError(f"OpenSubtitles lookup took longer than {int(timeout)}s")
    if "error" in holder:
        raise holder["error"]
    return holder.get("result") or {}


# -- Public helper -----------------------------------------------------------


def _result(
    *,
    ok: bool,
    rating_key: str,
    reason: str,
    message: str = "",
    language: str = "",
    source: str = "",
    configured: bool,
    called: bool = False,
    track: Optional[Dict[str, Any]] = None,
    quota_reset_at: Optional[float] = None,
) -> Dict[str, Any]:
    return {
        "ok": ok,
        "cached": track is not None,
        "rating_key": rating_key,
        "reason": reason,
        "message": message,
        "language": language,
        "source": source,
        "track": track,
        "opensubtitles_configured": configured,
        "opensubtitles_called": called,
        "quota": reason == "quota",
        "quota_reset_at": quota_reset_at,
    }


def ensure_household_subtitle(
    settings: Any,
    rating_key: Any,
    *,
    db: Any = None,
    data_dir: Optional[Path] = None,
    language: str = "",
    prefer_sdh: bool = False,
    plex_client: Any = None,
    opensubtitles: Optional[OpenSubtitlesClient] = None,
    allow_opensubtitles: bool = True,
    lookup_timeout: Optional[float] = None,
    now: Optional[float] = None,
) -> Dict[str, Any]:
    """Make sure one household-language text file is cached for this title.

    Records the outcome in ``subtitle_state`` when ``db`` is given. A quota
    hit is not recorded against the title; the caller pauses instead.
    """
    from projectionist.library.subtitles import plex_client_from_settings

    key = str(rating_key or "").strip()
    languages = household_languages(settings)
    if language:
        first = iso2(language)
        languages = [first] + [code for code in languages if code != first]
    state_lang = languages[0]
    api_key = opensubtitles_api_key(settings)
    configured = bool(api_key)
    if not key:
        return _result(
            ok=False,
            rating_key="",
            reason="missing_rating_key",
            message="A Plex rating key is required.",
            configured=configured,
        )

    hit = read_cached(key, languages, data_dir=data_dir)
    if hit is not None:
        if db is not None:
            prior = subtitle_state.get_state(db, key, state_lang) or {}
            if prior.get("status") != subtitle_state.STATUS_CACHED:
                subtitle_state.record_cached(db, key, state_lang, source="cache", now=now)
        return _result(
            ok=True,
            rating_key=key,
            reason="already_cached",
            language=hit[0],
            source="cache",
            configured=configured,
            track=cached_track_row(key, hit[0]),
        )

    client = plex_client if plex_client is not None else plex_client_from_settings(settings)
    plex_error = ""
    if client is not None:
        try:
            streams = client.list_subtitle_streams(key)
        except Exception as error:  # noqa: BLE001
            streams = []
            plex_error = str(error)[:200]
        for code, row in _plex_text_candidates(streams, languages, prefer_sdh=prefer_sdh):
            text = _fetch_plex_text(client, row)
            if text and write_cached(key, code, text, data_dir=data_dir):
                if db is not None:
                    subtitle_state.record_cached(db, key, state_lang, source="plex", now=now)
                return _result(
                    ok=True,
                    rating_key=key,
                    reason="copied_from_plex",
                    language=code,
                    source="plex",
                    configured=configured,
                    track=cached_track_row(key, code),
                )

    if not configured:
        if db is not None:
            if plex_error:
                subtitle_state.record_failure(db, key, state_lang, plex_error, now=now)
            else:
                subtitle_state.record_none_found(db, key, state_lang, no_key=True, now=now)
        return _result(
            ok=False,
            rating_key=key,
            reason="no_opensubtitles_key",
            message=NO_KEY_NOTE,
            configured=False,
        )
    if not allow_opensubtitles:
        return _result(
            ok=False,
            rating_key=key,
            reason="opensubtitles_paused",
            message=QUOTA_NOTE,
            configured=True,
        )

    ctx = title_subtitle_context(db, key)
    os_client = opensubtitles or OpenSubtitlesClient(api_key)

    def _lookup() -> Dict[str, Any]:
        moviehash = _media_moviehash(settings, client, key)
        return _opensubtitles_lookup(os_client, ctx, moviehash, languages, prefer_sdh=prefer_sdh)

    try:
        found = _run_with_timeout(
            _lookup, TITLE_LOOKUP_TIMEOUT_SECONDS if lookup_timeout is None else lookup_timeout
        )
    except OpenSubtitlesQuota as quota:
        return _result(
            ok=False,
            rating_key=key,
            reason="quota",
            message=QUOTA_NOTE,
            configured=True,
            called=True,
            quota_reset_at=quota.reset_at,
        )
    except Exception as error:  # noqa: BLE001 — includes the per-title timeout
        logger.info("OpenSubtitles lookup failed for %s: %s", key, error)
        if db is not None:
            subtitle_state.record_failure(db, key, state_lang, str(error)[:200], now=now)
        return _result(
            ok=False,
            rating_key=key,
            reason="timeout" if isinstance(error, TimeoutError) else "error",
            message=FETCH_FAILED_NOTE,
            configured=True,
            called=True,
        )

    text = str(found.get("text") or "")
    if text:
        code = str(found.get("language") or state_lang)
        if write_cached(key, code, text, data_dir=data_dir):
            if db is not None:
                subtitle_state.record_cached(db, key, state_lang, source="opensubtitles", now=now)
            result = _result(
                ok=True,
                rating_key=key,
                reason="downloaded",
                language=code,
                source="opensubtitles",
                configured=True,
                called=True,
                track=cached_track_row(key, code),
            )
            remaining = found.get("remaining")
            if remaining is not None and int(remaining) <= 0:
                result["quota"] = True
                result["quota_reset_at"] = found.get("reset_at")
            return result

    error = str(found.get("error") or "")
    if db is not None:
        if error:
            subtitle_state.record_failure(db, key, state_lang, error, now=now)
        else:
            subtitle_state.record_none_found(db, key, state_lang, now=now)
    return _result(
        ok=False,
        rating_key=key,
        reason="error" if error else "none_found",
        message=FETCH_FAILED_NOTE if error else NONE_FOUND_NOTE,
        configured=True,
        called=True,
    )
