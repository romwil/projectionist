"""Record example responses for client-facing routes (NAT-004).

The bodies are what a test household returns: one film, pairing frozen to
stable ids, Plex fetches replaced with a short playlist, and weather read
from the checked-in Chicago forecast fixture. Nothing here is a live
household, and the Plex token never leaves the server.
"""

from __future__ import annotations

import base64
import importlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import patch
from uuid import UUID

from fastapi.testclient import TestClient

from projectionist.theater.weather_channel.sources.almanac import moon_phase as _live_moon_phase
from projectionist.web.client_contract import CLIENT_ROUTES

FIXTURE_DIR = Path("docs/api/fixtures")
JPEG = b"\xff\xd8\xff" + b"\x00" * 16
PLAYLIST = (
    "#EXTM3U\n"
    "#EXT-X-VERSION:7\n"
    "#EXT-X-PLAYLIST-TYPE:VOD\n"
    "#EXTINF:6.000,\n"
    "segment0.ts\n"
    "#EXT-X-ENDLIST\n"
)
SESSION_ID = "00000000-0000-4000-8000-000000000001"
# Moon age moves every day. The example almanac stays the one recorded here.
FIXTURE_MOON_AT = datetime(2026, 11, 21, 3, 30, tzinfo=timezone.utc)
PLEX = "http://127.0.0.1:32400"
TOKEN = "server-token"
FORBIDDEN = (TOKEN, "LEAKED", "/Users/", "/mnt/")


def fixture_slug(method: str, path: str) -> str:
    cleaned = (
        path.strip("/")
        .replace("/", "-")
        .replace("{", "")
        .replace("}", "")
        .replace(":", "-")
    )
    return f"{method.lower()}-{cleaned}.json"


_FROZEN_TIMES = {"created_at", "last_login_at", "updated_at"}


def _freeze_times(node: Any) -> None:
    """Test rows are inserted on the wall clock. Examples use one fixed instant."""
    if isinstance(node, dict):
        for key, value in list(node.items()):
            if key in _FROZEN_TIMES and isinstance(value, (int, float)):
                node[key] = 1_700_000_000
            else:
                _freeze_times(value)
    elif isinstance(node, list):
        for item in node:
            _freeze_times(item)
def _envelope(
    method: str,
    path: str,
    response: Any,
    *,
    example_path: str | None = None,
    query: dict[str, str] | None = None,
) -> dict[str, Any]:
    content_type = response.headers.get("content-type", "").split(";")[0].strip()
    body: dict[str, Any] = {
        "method": method,
        "path": path,
        "status": response.status_code,
        "content_type": content_type,
    }
    if example_path:
        body["example_path"] = example_path
    if query:
        body["query"] = query
    if "json" in content_type or response.content[:1] in (b"{", b"["):
        payload = response.json()
        _freeze_times(payload)
        body["body"] = payload
    elif (
        content_type.startswith("text/")
        or "mpegurl" in content_type
        or content_type.endswith("+json")
    ):
        body["body_text"] = response.text
    else:
        body["body_base64"] = base64.b64encode(response.content).decode("ascii")
        body["byte_length"] = len(response.content)
    return body


def _token_urlsafe(nbytes: int = 32) -> str:
    if nbytes == 18:
        return "pending-fixture-1"
    return "credential-fixture"


_CODE_LETTERS = iter("ABCDEFGHJKLMNPQRSTUVWXYZ23456789")


def _choice(_alphabet: str) -> str:
    return next(_CODE_LETTERS)


def _uuid4() -> UUID:
    return UUID("00000000-0000-4000-8000-000000000001")


def _fake_fetch(url: str, *, headers: Any = None, timeout: int = 30, method: str = "GET"):
    _ = (headers, timeout, method)
    if str(url).endswith(".ts"):
        return b"\x00\x01segment", "video/mp2t", 200, url
    return PLAYLIST.encode("utf-8"), "application/vnd.apple.mpegurl", 200, url


async def _fake_art(*_args: Any, **_kwargs: Any):
    return JPEG, "image/jpeg", 'W/"heat-poster"'


def _recorded_moon() -> dict[str, Any]:
    return _live_moon_phase(FIXTURE_MOON_AT)


def _weather_service(data_dir: Path):
    from projectionist.theater.weather_channel.http import FetchResult
    from projectionist.theater.weather_channel.service import WeatherService

    forecast = Path("tests/fixtures/weather/forecast_chicago.json")

    def fake_fetch(url: str, **_kwargs: Any) -> FetchResult:
        _ = url
        return FetchResult(forecast.read_bytes())

    return WeatherService(data_dir, fetch=fake_fetch, autostart=False)


def collect_client_fixtures() -> dict[str, dict[str, Any]]:
    """Return ``METHOD path`` -> fixture envelope for every client route."""
    global _CODE_LETTERS
    _CODE_LETTERS = iter("ABCDEFGHJKLMNPQRSTUVWXYZ23456789")
    tmp = tempfile.TemporaryDirectory()
    data_dir = Path(tmp.name)
    saved_env = dict(os.environ)
    keep = {
        "PATH",
        "HOME",
        "USER",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "TMPDIR",
        "PYTHONPATH",
        "VIRTUAL_ENV",
        "PYTHONDONTWRITEBYTECODE",
    }
    os.environ.clear()
    os.environ.update({key: value for key, value in saved_env.items() if key in keep})
    os.environ["DATA_DIR"] = str(data_dir)
    os.environ["PROJECTIONIST_SKIP_DOTENV"] = "1"
    os.environ["LLM_PROVIDER"] = "ollama"
    os.environ["PROJECTIONIST_SESSION_SECRET"] = "client-fixture-session-secret"
    os.environ["PROJECTIONIST_SETUP_STATE"] = "active"
    try:
        (data_dir / "settings.json").write_text(
            json.dumps(
                {
                    "plex_url": PLEX,
                    "plex_token": TOKEN,
                    "llm_provider": "ollama",
                    "onboarding_complete": True,
                }
            ),
            encoding="utf-8",
        )
        from projectionist.circuit_breaker import reset_host_circuits
        from projectionist.library.playback import reset_playback_sessions
        from projectionist.web.auth import clear_pin_bindings
        from projectionist.web.rate_limit import clear_rate_limits
        from projectionist.web.session_tokens import clear_session_secret_cache

        from projectionist.web.addresses import reset_observed_home

        reset_host_circuits()
        clear_session_secret_cache()
        clear_rate_limits()
        clear_pin_bindings()
        reset_playback_sessions()
        reset_observed_home()
        import projectionist.web.jobs as jobs

        jobs._manager = None
        import projectionist.web.app as app_mod

        importlib.reload(app_mod)
        app_mod.DATA_DIR = data_dir
        client = TestClient(app_mod.app)
        from tests.owner_claim_helpers import grant_owner_claim

        grant_owner_claim(client)
        db = jobs.get_job_manager().db
        db.upsert_library_item(
            {
                "rating_key": "movie-1",
                "media_type": "movie",
                "title": "Heat",
                "year": 1995,
                "content_rating": "R",
                "duration_ms": 10_200_000,
                "view_offset_ms": 0,
                "tmdb_id": 949,
                "poster_url": "https://image.tmdb.org/t/p/w500/heat.jpg",
                "backdrop_url": "https://image.tmdb.org/t/p/w780/heat-bg.jpg",
            }
        )
        weather = _weather_service(data_dir)
        recorded: dict[str, dict[str, Any]] = {}

        def keep(method: str, path: str, response: Any, **extra: Any) -> None:
            recorded[f"{method} {path}"] = _envelope(method, path, response, **extra)

        with (
            patch("projectionist.devices.pairing.time.time", return_value=1_700_000_000),
            patch("projectionist.devices.pairing.secrets.choice", side_effect=_choice),
            patch("projectionist.devices.pairing.secrets.token_urlsafe", side_effect=_token_urlsafe),
            patch("uuid.uuid4", side_effect=_uuid4),
            patch(
                "projectionist.connectors.plex.cached_machine_identifier",
                return_value="machine-1",
            ),
            patch("projectionist.library.playback.fetch_plex_bytes", side_effect=_fake_fetch),
            patch("projectionist.library.cached_art.load_cached_art", side_effect=_fake_art),
            patch(
                "projectionist.web.theater_delight_routes.get_weather_service",
                return_value=weather,
            ),
            patch(
                "projectionist.theater.weather_channel.sources.almanac.moon_phase",
                side_effect=lambda when=None: _recorded_moon(),
            ),
        ):
            keep("GET", "/api/health", client.get("/api/health"))
            keep("GET", "/api/features", client.get("/api/features"))
            # Sign-in routes in this household are not turned on. The example is
            # that answer, so the file never holds a device credential or a PIN nonce.
            keep(
                "POST",
                "/api/auth/plex/pin",
                client.post("/api/auth/plex/pin", json={}),
            )
            keep(
                "GET",
                "/api/auth/plex/pin/{pin_id}",
                client.get("/api/auth/plex/pin/1"),
                example_path="/api/auth/plex/pin/1",
            )
            keep(
                "POST",
                "/api/auth/plex",
                client.post("/api/auth/plex", json={"auth_token": "not-a-token"}),
            )
            keep(
                "POST",
                "/api/auth/local/login",
                client.post(
                    "/api/auth/local/login",
                    json={"username": "member", "password": "password123"},
                ),
            )
            keep(
                "POST",
                "/api/auth/local/register",
                client.post(
                    "/api/auth/local/register",
                    json={"username": "member", "password": "password123"},
                ),
            )
            keep("GET", "/api/auth/oidc/authorize", client.get("/api/auth/oidc/authorize"))
            keep(
                "POST",
                "/api/auth/oidc/authorize",
                client.post(
                    "/api/auth/oidc/authorize",
                    json={
                        "client": {"kind": "iphone", "label": "Phone"},
                        "code_challenge": "a" * 43,
                        "code_challenge_method": "S256",
                    },
                ),
            )
            keep(
                "GET",
                "/api/auth/oidc/callback",
                client.get("/api/auth/oidc/callback", params={"code": "none", "state": "none"}),
                query={"code": "none", "state": "none"},
            )
            keep(
                "POST",
                "/api/auth/oidc/exchange",
                client.post(
                    "/api/auth/oidc/exchange",
                    json={
                        "code": "a" * 32,
                        "code_verifier": "b" * 43,
                        "client": {"kind": "iphone", "label": "Phone"},
                    },
                ),
            )
            keep(
                "GET",
                "/api/invites/validate",
                client.get("/api/invites/validate", params={"token": "not-an-invite"}),
                query={"token": "not-an-invite"},
            )
            keep(
                "POST",
                "/api/invites/redeem/local",
                client.post(
                    "/api/invites/redeem/local",
                    json={
                        "token": "not-an-invite",
                        "username": "member",
                        "password": "password123",
                    },
                ),
            )
            keep(
                "POST",
                "/api/access-requests",
                client.post(
                    "/api/access-requests",
                    json={"display_name": "Neighbor", "message": "Could I join?"},
                ),
            )
            keep("GET", "/api/auth/me", client.get("/api/auth/me"))
            keep(
                "PATCH",
                "/api/auth/me",
                client.patch("/api/auth/me", json={"preferred_name": "Member"}),
            )
            issued = client.post("/api/devices/pair/issue", json={})
            keep("POST", "/api/devices/pair/issue", issued)
            pending_id = issued.json()["pending_id"]
            rotated = client.post(
                "/api/devices/pair/rotate", json={"pending_id": pending_id}
            )
            keep("POST", "/api/devices/pair/rotate", rotated)
            keep("POST", "/api/devices/pair/rotate", rotated)
            code = rotated.json()["code"]
            claimed = client.post("/api/devices/pair/claim", json={"code": code})
            keep(
                "GET",
                "/api/devices/pair/pending/{pending_id}",
                client.get(f"/api/devices/pair/pending/{pending_id}"),
                example_path=f"/api/devices/pair/pending/{pending_id}",
            )
            device_id = claimed.json()["device_id"]
            credential = str(
                recorded["GET /api/devices/pair/pending/{pending_id}"]["body"]["credential"]
            )
            bearer = {"Authorization": f"Bearer {credential}"}
            client.post(
                f"/api/devices/{device_id}/throw",
                json={
                    "kind": "title",
                    "media_type": "movie",
                    "item_id": "movie-1",
                    "id_type": "rating_key",
                },
            )
            keep(
                "GET",
                "/api/devices/me/intent",
                client.get("/api/devices/me/intent", headers=bearer),
            )
            keep("GET", "/api/library/feeds/hub", client.get("/api/library/feeds/hub"))
            keep(
                "GET",
                "/api/library/feeds/tonight-table",
                client.get("/api/library/feeds/tonight-table"),
            )
            keep(
                "GET",
                "/api/library/query",
                client.get("/api/library/query", params={"query": "Heat"}),
                query={"query": "Heat"},
            )
            keep(
                "GET",
                "/api/title/{media_type}/{item_id}",
                client.get(
                    "/api/title/movie/949",
                    params={"id_type": "tmdb", "enrich": "false"},
                ),
                example_path="/api/title/movie/949",
                query={"id_type": "tmdb", "enrich": "false"},
            )
            keep(
                "GET",
                "/api/library/art/{media_type}/{item_id}",
                client.get(
                    "/api/library/art/movie/949",
                    params={"id_type": "tmdb", "kind": "poster"},
                ),
                example_path="/api/library/art/movie/949",
                query={"id_type": "tmdb", "kind": "poster"},
            )
            started = client.post(
                "/api/library/playback/start",
                json={"rating_key": "movie-1"},
            )
            keep("POST", "/api/library/playback/start", started)
            session_id = started.json().get("session_id", SESSION_ID)
            keep(
                "POST",
                "/api/library/playback/{session_id}/seek",
                client.post(
                    f"/api/library/playback/{session_id}/seek",
                    json={"offset_ms": 1000},
                ),
                example_path=f"/api/library/playback/{session_id}/seek",
            )
            keep(
                "POST",
                "/api/library/playback/{session_id}/progress",
                client.post(
                    f"/api/library/playback/{session_id}/progress",
                    json={"state": "playing", "time_ms": 1000, "duration_ms": 10_200_000},
                ),
                example_path=f"/api/library/playback/{session_id}/progress",
            )
            keep(
                "POST",
                "/api/library/playback/{session_id}/subtitles",
                client.post(
                    f"/api/library/playback/{session_id}/subtitles",
                    json={"subtitle_stream_id": "", "offset_ms": 1000},
                ),
                example_path=f"/api/library/playback/{session_id}/subtitles",
            )
            keep(
                "GET",
                "/api/library/playback/{session_id}/index.m3u8",
                client.get(f"/api/library/playback/{session_id}/index.m3u8"),
                example_path=f"/api/library/playback/{session_id}/index.m3u8",
            )
            keep(
                "GET",
                "/api/library/playback/{session_id}/master.m3u8",
                client.get(f"/api/library/playback/{session_id}/master.m3u8"),
                example_path=f"/api/library/playback/{session_id}/master.m3u8",
            )
            keep(
                "GET",
                "/api/library/playback/{session_id}/{path:path}",
                client.get(f"/api/library/playback/{session_id}/segment0.ts"),
                example_path=f"/api/library/playback/{session_id}/segment0.ts",
            )
            keep(
                "POST",
                "/api/library/playback/{session_id}/stop",
                client.post(
                    f"/api/library/playback/{session_id}/stop",
                    json={"time_ms": 1000, "duration_ms": 10_200_000},
                ),
                example_path=f"/api/library/playback/{session_id}/stop",
            )
            keep("GET", "/api/live-channels/on-now", client.get("/api/live-channels/on-now"))
            keep(
                "GET",
                "/api/live-channels/guide",
                client.get("/api/live-channels/guide", params={"hours": "12"}),
                query={"hours": "12"},
            )
            keep(
                "POST",
                "/api/live-channels/tune",
                client.post("/api/live-channels/tune", json={"channel_id": "station-a"}),
            )
            weather_response = client.get("/api/live/weather")
            keep("GET", "/api/live/weather", weather_response)
            audio_name = "a" * 32 + ".opus"
            image_id = "b" * 32
            if weather_response.status_code == 200:
                payload = weather_response.json()
                scripts = (payload.get("scripts") or {}).get("current") or []
                if scripts and scripts[0].get("audio_url"):
                    audio_name = str(scripts[0]["audio_url"]).rsplit("/", 1)[-1]
                frames = ((payload.get("maps") or {}).get("radar") or {}).get("frames") or []
                if frames and frames[0].get("url"):
                    image_id = str(frames[0]["url"]).rsplit("/", 1)[-1]
            keep(
                "GET",
                "/api/live/weather/audio/{name}",
                client.get(f"/api/live/weather/audio/{audio_name}"),
                example_path=f"/api/live/weather/audio/{audio_name}",
            )
            keep(
                "GET",
                "/api/live/weather/image/{image_id}",
                client.get(f"/api/live/weather/image/{image_id}"),
                example_path=f"/api/live/weather/image/{image_id}",
            )
        missing = {f"{method} {path}" for method, path in CLIENT_ROUTES} - set(recorded)
        if missing:
            listed = ", ".join(sorted(missing))
            raise RuntimeError(f"Client fixtures were not recorded: {listed}")
        return recorded
    finally:
        tmp.cleanup()
        os.environ.clear()
        os.environ.update(saved_env)


def render_fixture_files(recorded: dict[str, dict[str, Any]]) -> dict[str, str]:
    files: dict[str, str] = {}
    index: list[dict[str, str]] = []
    for key in sorted(recorded):
        method, path = key.split(" ", 1)
        name = fixture_slug(method, path)
        files[name] = json.dumps(recorded[key], indent=2, sort_keys=True) + "\n"
        index.append({"method": method, "path": path, "file": name})
    files["index.json"] = json.dumps(index, indent=2) + "\n"
    return files


def read_fixture_files() -> dict[str, str]:
    files: dict[str, str] = {}
    if not FIXTURE_DIR.is_dir():
        return files
    for path in sorted(FIXTURE_DIR.glob("*.json")):
        files[path.name] = path.read_text(encoding="utf-8")
    return files


def main(argv: list[str] | None = None) -> int:
    import sys

    args = list(sys.argv[1:] if argv is None else argv)
    check = "--check" in args
    rendered = render_fixture_files(collect_client_fixtures())
    blob = "".join(rendered.values())
    for secret in FORBIDDEN:
        if secret in blob:
            sys.stderr.write(f"Client fixture contains {secret!r}\n")
            return 1
    if check:
        current = read_fixture_files()
        if current != rendered:
            changed = sorted(
                name for name in set(current) & set(rendered) if current[name] != rendered[name]
            )
            sys.stderr.write(
                "docs/api/fixtures does not match the client routes.\n"
                "Regenerate with scripts/export-fixtures.sh\n"
            )
            if changed:
                sys.stderr.write("Changed: " + ", ".join(changed) + "\n")
            return 1
        return 0
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    for name, text in rendered.items():
        (FIXTURE_DIR / name).write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
