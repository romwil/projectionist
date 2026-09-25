"""ACRCloud Identification API (Music / Audio Recognition). Not Broadcast Monitoring."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import re
import struct
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional, Sequence
from urllib.parse import urlparse

from projectionist.library.episode_investigate.capabilities import acrcloud_config
from projectionist.library.episode_investigate.ffmpeg import (
    IDENTIFY_CLIP_FRACTION,
    IDENTIFY_CLIP_SECONDS,
    IDENTIFY_MAX_BYTES,
    extract_identify_clip,
)

logger = logging.getLogger(__name__)

DEFAULT_HOST = "identify-us-west-2.acrcloud.com"
IDENTIFY_PATH = "/v1/identify"
SIGNATURE_VERSION = "1"
DATA_TYPE = "audio"
MIN_IDENTIFY_INTERVAL = 1.5
THEME_SUFFIXES = (
    "original television soundtrack",
    "main title theme",
    "opening credits",
    "ending theme",
    "opening theme",
    "title theme",
    "theme song",
    "end credits",
    "main title",
    "soundtrack",
    "theme",
    "score",
)

_last_identify_at = 0.0
_rate_lock = threading.Lock()
_identified_keys: set[str] = set()
_identified_lock = threading.Lock()

IdentifyFetch = Callable[[str, bytes, str, Mapping[str, str]], Mapping[str, Any]]
TmdbSearch = Callable[[str], Sequence[Mapping[str, Any]]]


def normalize_identify_host(raw: str) -> str:
    """Accept a region host or full Identify URL. Reject non-Identify hosts."""
    text = str(raw or "").strip()
    if not text:
        return DEFAULT_HOST
    if "://" not in text:
        text = f"https://{text}"
    parsed = urlparse(text)
    host = (parsed.hostname or "").strip().lower()
    if not host:
        return DEFAULT_HOST
    if not host.endswith(".acrcloud.com") or not host.startswith("identify"):
        raise ValueError("ACRCloud host must be an Identification region (identify-*.acrcloud.com).")
    return host


def identify_url(host: str) -> str:
    return f"https://{normalize_identify_host(host)}{IDENTIFY_PATH}"


def series_title_from_acr(title: str) -> str:
    """Strip theme / score suffixes so we can search TMDB for the show."""
    cleaned = str(title or "").strip()
    if not cleaned:
        return ""
    cleaned = re.sub(r"\s*[\(\[].*?[\)\]]\s*", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -–—:")
    lowered = cleaned.lower()
    for suffix in THEME_SUFFIXES:
        if lowered == suffix:
            return ""
        if lowered.endswith(f" {suffix}") or lowered.endswith(f": {suffix}") or lowered.endswith(f"- {suffix}"):
            cleaned = cleaned[: -len(suffix)].rstrip(" -–—:")
            lowered = cleaned.lower()
            break
    return cleaned.strip()


def sign_identify(*, access_key: str, access_secret: str, timestamp: str) -> str:
    string_to_sign = "\n".join(
        ["POST", IDENTIFY_PATH, access_key, DATA_TYPE, SIGNATURE_VERSION, str(timestamp)]
    )
    digest = hmac.new(
        access_secret.encode("utf-8"),
        string_to_sign.encode("utf-8"),
        hashlib.sha1,
    ).digest()
    return base64.b64encode(digest).decode("ascii")


def silent_wav_bytes(*, seconds: float = IDENTIFY_CLIP_SECONDS, rate: int = 16000) -> bytes:
    frames = max(1, int(float(seconds) * int(rate)))
    data = b"\x00\x00" * frames
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + len(data),
        b"WAVE",
        b"fmt ",
        16,
        1,
        1,
        int(rate),
        int(rate) * 2,
        2,
        16,
        b"data",
        len(data),
    )
    return header + data


def parse_identify_payload(payload: Mapping[str, Any]) -> Dict[str, Any]:
    status = payload.get("status") if isinstance(payload.get("status"), Mapping) else {}
    try:
        code = int(status.get("code") or 0)
    except (TypeError, ValueError):
        code = 0
    message = str(status.get("msg") or "").strip()
    if code not in {0, 1001}:
        return {
            "found": False,
            "ok": False,
            "code": code,
            "message": message or "Identify failed",
            "title": "",
            "series_title": "",
            "score": None,
        }
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), Mapping) else {}
    music = metadata.get("music") if isinstance(metadata.get("music"), list) else []
    row = next((item for item in music if isinstance(item, Mapping)), None)
    if row is None:
        return {
            "found": False,
            "ok": True,
            "code": code or 1001,
            "message": message or "No result",
            "title": "",
            "series_title": "",
            "score": None,
        }
    title = str(row.get("title") or "").strip()
    try:
        score = float(row.get("score")) if row.get("score") is not None else None
    except (TypeError, ValueError):
        score = None
    return {
        "found": True,
        "ok": True,
        "code": code,
        "message": message or "Success",
        "title": title,
        "series_title": series_title_from_acr(title),
        "artists": [
            str(item.get("name") or "").strip()
            for item in (row.get("artists") or [])
            if isinstance(item, Mapping) and str(item.get("name") or "").strip()
        ],
        "score": score,
    }


def map_acr_title_to_tmdb(
    title: str,
    *,
    search: Optional[TmdbSearch] = None,
    tmdb_client: Any = None,
    this_show: Optional[Mapping[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    query = series_title_from_acr(title) or str(title or "").strip()
    if not query:
        return None
    rows: Sequence[Mapping[str, Any]] = ()
    if search is not None:
        rows = search(query)
    elif tmdb_client is not None and hasattr(tmdb_client, "search_tv"):
        try:
            rows = tmdb_client.search_tv(query)
        except Exception as error:  # noqa: BLE001
            logger.info("ACRCloud TMDB map failed query=%s error=%s", query, error)
            return None
    if not rows:
        return None
    this = this_show if isinstance(this_show, Mapping) else {}
    this_tmdb = this.get("tmdb_id")
    this_title = str(this.get("title") or "").strip().lower()
    exact = []
    this_hit = None
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        name = str(row.get("name") or row.get("original_name") or "").strip()
        try:
            tmdb_id = int(row.get("id")) if row.get("id") is not None else None
        except (TypeError, ValueError):
            tmdb_id = None
        if this_tmdb and tmdb_id is not None:
            try:
                if int(this_tmdb) == int(tmdb_id):
                    this_hit = {"series_title": name or query, "tmdb_id": tmdb_id}
            except (TypeError, ValueError):
                pass
        if name.lower() == query.lower() or (this_title and name.lower() == this_title):
            exact.append({"series_title": name or query, "tmdb_id": tmdb_id})
    if this_hit:
        return this_hit
    if exact:
        return exact[0]
    first = next((row for row in rows if isinstance(row, Mapping)), None)
    if first is None:
        return None
    try:
        tmdb_id = int(first.get("id")) if first.get("id") is not None else None
    except (TypeError, ValueError):
        tmdb_id = None
    return {
        "series_title": str(first.get("name") or first.get("original_name") or query).strip(),
        "tmdb_id": tmdb_id,
    }


def identify_bytes(
    sample: bytes,
    *,
    settings: Any = None,
    host: str = "",
    access_key: str = "",
    access_secret: str = "",
    filename: str = "clip.wav",
    fetch: Optional[IdentifyFetch] = None,
    wait_rate_limit: bool = True,
) -> Dict[str, Any]:
    creds = acrcloud_config(settings)
    key = str(access_key or creds.get("access_key") or "").strip()
    secret = str(access_secret or creds.get("access_secret") or "").strip()
    region = str(host or creds.get("host") or DEFAULT_HOST).strip()
    if not key or not secret:
        return {"found": False, "ok": False, "message": "ACRCloud is not configured.", "title": ""}
    if not sample:
        return {"found": False, "ok": False, "message": "Identify clip is empty.", "title": ""}
    if len(sample) > IDENTIFY_MAX_BYTES:
        return {"found": False, "ok": False, "message": "Identify clip is over the size cap.", "title": ""}
    try:
        url = identify_url(region)
    except ValueError as error:
        return {"found": False, "ok": False, "message": str(error), "title": ""}
    timestamp = str(int(time.time()))
    signature = sign_identify(access_key=key, access_secret=secret, timestamp=timestamp)
    fields = {
        "access_key": key,
        "sample_bytes": str(len(sample)),
        "timestamp": timestamp,
        "signature": signature,
        "data_type": DATA_TYPE,
        "signature_version": SIGNATURE_VERSION,
    }
    if wait_rate_limit:
        _throttle()
    if fetch is not None:
        try:
            payload = fetch(url, sample, filename, fields)
        except Exception as error:  # noqa: BLE001 — a miss must not fail the job
            logger.info("ACRCloud identify failed: %s", error)
            return {"found": False, "ok": False, "message": str(error)[:400], "title": ""}
        return parse_identify_payload(payload) if isinstance(payload, Mapping) else {
            "found": False,
            "ok": False,
            "message": "Identify returned an empty body.",
            "title": "",
        }
    try:
        body, content_type = _multipart(fields, {"sample": (filename, sample, "audio/wav")})
        request = urllib.request.Request(
            url,
            data=body,
            method="POST",
            headers={"Content-Type": content_type},
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read()
        payload = json.loads(raw.decode("utf-8") or "{}")
    except Exception as error:  # noqa: BLE001 — a miss must not fail the job
        logger.info("ACRCloud identify failed: %s", error)
        return {"found": False, "ok": False, "message": str(error)[:400], "title": ""}
    if isinstance(payload, Mapping):
        return parse_identify_payload(payload)
    return {"found": False, "ok": False, "message": "Identify returned an empty body.", "title": ""}


def identify_file(
    path: str,
    dest_dir: Path,
    *,
    settings: Any = None,
    runtime_seconds: Optional[float] = None,
    tmdb_client: Any = None,
    this_show: Optional[Mapping[str, Any]] = None,
    file_key: str = "",
    fetch: Optional[IdentifyFetch] = None,
    extract: Optional[Callable[..., Optional[Path]]] = None,
) -> Optional[Dict[str, Any]]:
    """One Identify per episode file. A miss returns Uncertain evidence, not an error."""
    creds = acrcloud_config(settings)
    if not creds.get("available"):
        return None
    key = str(file_key or path or "").strip()
    if key and not _claim_file(key):
        return None
    clip_fn = extract or extract_identify_clip
    clip = clip_fn(
        path,
        Path(dest_dir) / "identify.wav",
        runtime_seconds=runtime_seconds,
        seconds=IDENTIFY_CLIP_SECONDS,
        fraction=IDENTIFY_CLIP_FRACTION,
        max_bytes=IDENTIFY_MAX_BYTES,
    )
    if clip is None or not Path(clip).is_file():
        return {"found": False, "ok": True, "message": "Could not cut an Identify clip.", "title": ""}
    try:
        sample = Path(clip).read_bytes()
    except OSError as error:
        logger.info("identify clip read failed: %s", error)
        return {"found": False, "ok": True, "message": "Could not read the Identify clip.", "title": ""}
    parsed = identify_bytes(sample, settings=settings, filename="identify.wav", fetch=fetch)
    if parsed.get("found") and (tmdb_client is not None or this_show is not None):
        mapped = map_acr_title_to_tmdb(
            str(parsed.get("title") or ""),
            tmdb_client=tmdb_client,
            this_show=this_show,
        )
        if mapped:
            parsed["mapped"] = True
            parsed["series_title"] = mapped.get("series_title") or parsed.get("series_title")
            parsed["tmdb_id"] = mapped.get("tmdb_id")
        else:
            parsed["mapped"] = False
    return parsed


def test_identify_clip(
    *,
    settings: Any = None,
    path: str = "",
    runtime_seconds: Optional[float] = None,
    dest_dir: Optional[Path] = None,
    fetch: Optional[IdentifyFetch] = None,
) -> Dict[str, Any]:
    """HMAC POST a clip to Identify. Never renames library files."""
    creds = acrcloud_config(settings)
    if not creds.get("available"):
        return {
            "ok": False,
            "renamed": False,
            "message": "ACRCloud access key and secret are required.",
        }
    sample: bytes
    source = "silent"
    if path:
        dest = Path(dest_dir) if dest_dir is not None else Path(os.environ.get("TMPDIR") or "/tmp")
        clip = extract_identify_clip(
            path,
            dest / "identify-test.wav",
            runtime_seconds=runtime_seconds,
        )
        if clip is None:
            return {
                "ok": False,
                "renamed": False,
                "message": "Could not cut a test clip (ffmpeg missing or file unreadable).",
            }
        sample = clip.read_bytes()
        source = "file"
    else:
        sample = silent_wav_bytes()
    parsed = identify_bytes(sample, settings=settings, fetch=fetch, wait_rate_limit=False)
    return {
        "ok": bool(parsed.get("ok")),
        "found": bool(parsed.get("found")),
        "renamed": False,
        "source": source,
        "host": creds.get("host") or DEFAULT_HOST,
        "title": parsed.get("title") or "",
        "series_title": parsed.get("series_title") or "",
        "message": parsed.get("message") or "",
        "code": parsed.get("code"),
    }


def reset_identify_throttle_for_tests() -> None:
    global _last_identify_at
    with _rate_lock:
        _last_identify_at = 0.0
    with _identified_lock:
        _identified_keys.clear()


def _claim_file(key: str) -> bool:
    with _identified_lock:
        if key in _identified_keys:
            return False
        _identified_keys.add(key)
        return True


def _throttle() -> None:
    global _last_identify_at
    with _rate_lock:
        now = time.monotonic()
        wait = MIN_IDENTIFY_INTERVAL - (now - _last_identify_at)
        if wait > 0:
            time.sleep(wait)
        _last_identify_at = time.monotonic()


def _multipart(
    fields: Mapping[str, str],
    files: Mapping[str, tuple[str, bytes, str]],
) -> tuple[bytes, str]:
    boundary = f"----ProjectionistIdentify{int(time.time() * 1000)}"
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.append(f"--{boundary}\r\n".encode("utf-8"))
        chunks.append(
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode("utf-8")
        )
    for name, (filename, content, ctype) in files.items():
        chunks.append(f"--{boundary}\r\n".encode("utf-8"))
        chunks.append(
            (
                f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'
                f"Content-Type: {ctype}\r\n\r\n"
            ).encode("utf-8")
        )
        chunks.append(content)
        chunks.append(b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode("utf-8"))
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"
