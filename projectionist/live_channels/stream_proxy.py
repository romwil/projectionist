"""Auth’d HLS proxy from Projectionist → Tunarr (no Tunarr LAN leak to browsers).

Household clients load playlists and segments from Projectionist only. Playlist
URIs are rewritten to stay on the proxy path so master → media → TS never
exposes the Tunarr base URL.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, Iterable, Mapping, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import quote, unquote, urljoin, urlparse
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

_URI_LINE = re.compile(r'URI="([^"]+)"')
_SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9._~:@!$&'()*+,;=\-/%]+$")


def stream_proxy_base(channel_id: str) -> str:
    cid = quote(str(channel_id or "").strip(), safe="")
    return f"/api/live-channels/stream/{cid}"


def tunarr_master_url(tunarr_base: str, channel_id: str) -> str:
    base = str(tunarr_base or "").strip().rstrip("/")
    cid = str(channel_id or "").strip()
    return f"{base}/stream/channels/{cid}.m3u8?mode=hls"


def tunarr_stream_url(tunarr_base: str, channel_id: str, relative_path: str = "") -> str:
    """Build a Tunarr stream URL for a channel-relative path."""
    base = str(tunarr_base or "").strip().rstrip("/")
    cid = str(channel_id or "").strip()
    rel = str(relative_path or "").lstrip("/")
    if not rel:
        return tunarr_master_url(base, cid)
    # Master shorthand: index.m3u8 / master.m3u8 → Tunarr master playlist.
    if rel in {"index.m3u8", "master.m3u8", f"{cid}.m3u8"}:
        return tunarr_master_url(base, cid)
    return f"{base}/stream/channels/{cid}/{rel}"


def validate_stream_path(relative_path: str) -> str:
    """Normalize and reject path traversal / odd schemes."""
    raw = unquote(str(relative_path or "").strip())
    if not raw:
        return "index.m3u8"
    if ".." in raw.split("/") or raw.startswith(("http:", "https:", "//")):
        raise ValueError("Invalid stream path")
    cleaned = raw.lstrip("/")
    if not _SAFE_SEGMENT.match(cleaned):
        raise ValueError("Invalid stream path characters")
    return cleaned


def _proxy_uri_for_tunarr(
    uri: str,
    *,
    channel_id: str,
    tunarr_base: str,
    playlist_path: str,
) -> str:
    """Map a playlist URI (absolute Tunarr or relative) onto our proxy."""
    text = str(uri or "").strip()
    if not text:
        return text
    proxy_root = stream_proxy_base(channel_id)
    tunarr_root = str(tunarr_base or "").strip().rstrip("/")
    channel_prefix = f"/stream/channels/{str(channel_id).strip()}/"

    if text.startswith(("http://", "https://")):
        parsed = urlparse(text)
        path = parsed.path or ""
        if channel_prefix in path:
            rel = path.split(channel_prefix, 1)[1]
            query = f"?{parsed.query}" if parsed.query else ""
            return f"{proxy_root}/{rel}{query}"
        # Master playlist often points at …/channels/{id}.m3u8 — map to index.
        if path.rstrip("/").endswith(f"/stream/channels/{str(channel_id).strip()}.m3u8"):
            query = f"?{parsed.query}" if parsed.query else ""
            return f"{proxy_root}/index.m3u8{query}"
        # Unknown absolute host — keep opaque (should not happen for Tunarr HLS).
        return text

    # Relative to the playlist's directory on Tunarr.
    playlist_dir = str(playlist_path or "").rsplit("/", 1)[0] if "/" in playlist_path else ""
    joined = urljoin(f"{playlist_dir}/" if playlist_dir else "", text)
    joined = joined.lstrip("/")
    if joined.startswith("http"):
        return _proxy_uri_for_tunarr(
            joined,
            channel_id=channel_id,
            tunarr_base=tunarr_root,
            playlist_path=playlist_path,
        )
    return f"{proxy_root}/{joined}"


def rewrite_hls_playlist(
    body: str,
    *,
    channel_id: str,
    tunarr_base: str,
    playlist_path: str,
) -> str:
    """Rewrite #EXTINF / URI= / bare URL lines to Projectionist proxy paths."""
    out_lines = []
    for line in str(body or "").splitlines():
        stripped = line.strip()
        if not stripped:
            out_lines.append(line)
            continue
        if stripped.startswith("#"):
            if "URI=" in stripped:

                def _repl(match: re.Match[str]) -> str:
                    original = match.group(1)
                    proxied = _proxy_uri_for_tunarr(
                        original,
                        channel_id=channel_id,
                        tunarr_base=tunarr_base,
                        playlist_path=playlist_path,
                    )
                    return f'URI="{proxied}"'

                out_lines.append(_URI_LINE.sub(_repl, line))
            else:
                out_lines.append(line)
            continue
        proxied = _proxy_uri_for_tunarr(
            stripped,
            channel_id=channel_id,
            tunarr_base=tunarr_base,
            playlist_path=playlist_path,
        )
        out_lines.append(proxied)
    # Preserve trailing newline if present.
    ending = "\n" if body.endswith("\n") else ""
    return "\n".join(out_lines) + ending


def fetch_tunarr_bytes(
    url: str,
    *,
    timeout: int = 30,
    headers: Optional[Mapping[str, str]] = None,
) -> Tuple[bytes, str, int]:
    """GET upstream Tunarr bytes. Returns (body, content_type, status)."""
    request = Request(url, method="GET")
    for key, value in (headers or {}).items():
        if value:
            request.add_header(key, value)
    try:
        with urlopen(request, timeout=max(5, int(timeout or 30))) as response:
            content_type = str(response.headers.get("Content-Type") or "")
            status = int(getattr(response, "status", 200) or 200)
            return response.read(), content_type, status
    except HTTPError as error:
        detail = error.read() if hasattr(error, "read") else b""
        raise RuntimeError(f"Tunarr HTTP {error.code}: {detail[:160]!r}") from error
    except URLError as error:
        raise RuntimeError(f"Tunarr unreachable: {error.reason}") from error


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
    if lower.endswith(".key"):
        return "application/octet-stream"
    return upstream.split(";")[0].strip() if upstream else "application/octet-stream"


def is_playlist_path(path: str) -> bool:
    lower = str(path or "").lower()
    return lower.endswith(".m3u8") or lower.endswith(".m3u")


def proxy_channel_stream(
    settings: Any,
    channel_id: str,
    relative_path: str = "index.m3u8",
    *,
    timeout: int = 30,
) -> Dict[str, Any]:
    """Fetch one stream asset from Tunarr; rewrite playlists to the proxy."""
    from projectionist.live_channels.publish import tunarr_client_from_settings

    cid = str(channel_id or "").strip()
    if not cid:
        raise ValueError("channel_id is required")
    path = validate_stream_path(relative_path)
    client = tunarr_client_from_settings(settings)
    url = tunarr_stream_url(client.base_url, cid, path)
    body, upstream_ct, status = fetch_tunarr_bytes(url, timeout=timeout)
    media_type = content_type_for_path(path, upstream_ct)
    if is_playlist_path(path):
        text = body.decode("utf-8", errors="replace")
        rewritten = rewrite_hls_playlist(
            text,
            channel_id=cid,
            tunarr_base=client.base_url,
            playlist_path=path,
        )
        return {
            "body": rewritten.encode("utf-8"),
            "media_type": "application/vnd.apple.mpegurl",
            "status": status,
            "path": path,
            "upstream_url_host": urlparse(url).netloc,
        }
    return {
        "body": body,
        "media_type": media_type,
        "status": status,
        "path": path,
        "upstream_url_host": urlparse(url).netloc,
    }


def iter_chunked(data: bytes, size: int = 64 * 1024) -> Iterable[bytes]:
    view = memoryview(data)
    for start in range(0, len(view), size):
        yield bytes(view[start : start + size])
