"""Plain-language Plex Live TV attach helpers (HDHR + XMLTV URLs).

Tunarr is added as an *additional* network tuner alongside any existing OTA /
HDHomeRun / DVR setup. Projectionist never instructs owners to remove or replace
existing Live TV hardware.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Mapping, Optional
from urllib.parse import urlparse

# Starter channels publish from 100+ (see starter_pack._BASE_CHANNEL_NUMBER).
_VIRTUAL_CHANNEL_FLOOR = 100
# Fallback when a Tunarr URL has no explicit port (managed default is 18765).
_DEFAULT_TUNARR_PORT = 18765
# Hostnames Plex (and household clients) cannot resolve / should not paste.
_DOCKER_ONLY_HOSTS = frozenset(
    {
        "host.docker.internal",
        "localhost",
        "127.0.0.1",
        "::1",
        "0.0.0.0",
    }
)


def normalize_tunarr_base(url: str) -> str:
    cleaned = str(url or "").strip().rstrip("/")
    return cleaned


def is_docker_only_host(hostname: Optional[str]) -> bool:
    """True when the host is only meaningful inside Docker / loopback."""
    host = str(hostname or "").strip().lower().rstrip(".")
    if not host:
        return True
    if host in _DOCKER_ONLY_HOSTS:
        return True
    return host.endswith(".localhost")


def tunarr_port_from_url(url: str, *, default: int = _DEFAULT_TUNARR_PORT) -> int:
    cleaned = normalize_tunarr_base(url)
    if not cleaned:
        return default
    parsed = urlparse(cleaned if "://" in cleaned else f"http://{cleaned}")
    if parsed.port:
        return int(parsed.port)
    if (parsed.scheme or "http").lower() == "https":
        return 443
    return default


def _hostname_from_url_or_host(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if "://" not in raw and "/" not in raw and ":" in raw and raw.count(":") == 1:
        # host:port without scheme
        return raw.split(":", 1)[0].strip()
    parsed = urlparse(raw if "://" in raw else f"http://{raw}")
    return str(parsed.hostname or "").strip()


def resolve_plex_facing_tunarr_base(
    settings: Any = None,
    *,
    tunarr_url: Optional[str] = None,
    request_host: Optional[str] = None,
    environ: Optional[Mapping[str, str]] = None,
) -> Dict[str, Any]:
    """Pick a LAN-reachable Tunarr base for Plex attach paste URLs.

    Projectionist→Tunarr may keep ``host.docker.internal`` in ``tunarr.url``.
    Plex and household clients cannot resolve that — never return it here.

    Preference order:
    1. ``tunarr.public_url`` settings override (must be LAN-reachable)
    2. ``PROJECTIONIST_TUNARR_PUBLIC_URL`` env
    3. ``tunarr.url`` when its host is already LAN-reachable
    4. Request ``Host`` / ``X-Forwarded-Host`` hostname + Tunarr port
    5. ``PROJECTIONIST_PUBLIC_URL`` hostname + Tunarr port
    6. ``PROJECTIONIST_HOST_IP`` / ``HOST_IP`` + Tunarr port

    Never returns ``host.docker.internal`` / localhost as ``base_url`` — those are
    Projectionist↔Tunarr sibling DNS only. When no LAN base is known, ``base_url``
    is empty and ``docker_only`` is true so the UI can refuse to offer a paste URL.
    """
    from projectionist.envcompat import branded_env, resolve_env

    env = environ if environ is not None else os.environ
    tunarr = getattr(settings, "tunarr", None) if settings is not None else None
    api_url = str(
        tunarr_url or (getattr(tunarr, "url", "") if tunarr else "") or ""
    ).strip()
    port = tunarr_port_from_url(api_url, default=_DEFAULT_TUNARR_PORT)
    # Prefer port from public_url when set (may differ only by host).
    public_setting = str(getattr(tunarr, "public_url", "") if tunarr else "").strip()
    if public_setting:
        port = tunarr_port_from_url(public_setting, default=port)

    def _lan_ok(base: str, *, source: str) -> Optional[Dict[str, Any]]:
        normalized = normalize_tunarr_base(base)
        host = _hostname_from_url_or_host(normalized)
        if not normalized or is_docker_only_host(host):
            return None
        return {
            "base_url": normalized,
            "source": source,
            "docker_only": False,
            "port": tunarr_port_from_url(normalized, default=port),
        }

    def _empty(*, source: str) -> Dict[str, Any]:
        return {
            "base_url": "",
            "source": source,
            "docker_only": True,
            "port": port,
        }

    if public_setting:
        hit = _lan_ok(public_setting, source="settings.public_url")
        if hit:
            return hit
        # Misconfigured public_url (docker-only) — keep searching.

    env_public = branded_env("TUNARR_PUBLIC_URL") if environ is None else (
        env.get("PROJECTIONIST_TUNARR_PUBLIC_URL")
        or env.get("CURATORX_TUNARR_PUBLIC_URL")
        or ""
    )
    if str(env_public or "").strip():
        hit = _lan_ok(str(env_public).strip(), source="env.TUNARR_PUBLIC_URL")
        if hit:
            return hit

    if api_url:
        hit = _lan_ok(api_url, source="tunarr.url")
        if hit:
            return hit

    host_candidates: List[str] = []
    if request_host:
        # May be "host:port" or bare host; ignore forwarded port (Projectionist).
        host_candidates.append(_hostname_from_url_or_host(str(request_host)))
    public_app = (
        branded_env("PUBLIC_URL")
        if environ is None
        else (env.get("PROJECTIONIST_PUBLIC_URL") or env.get("CURATORX_PUBLIC_URL") or "")
    )
    if str(public_app or "").strip():
        host_candidates.append(_hostname_from_url_or_host(str(public_app).strip()))
    host_ip = ""
    if environ is None:
        host_ip = branded_env("HOST_IP") or resolve_env("HOST_IP") or ""
    else:
        host_ip = (
            env.get("PROJECTIONIST_HOST_IP")
            or env.get("CURATORX_HOST_IP")
            or env.get("HOST_IP")
            or ""
        )
    if str(host_ip or "").strip():
        host_candidates.append(str(host_ip).strip())

    for host in host_candidates:
        if not host or is_docker_only_host(host):
            continue
        hit = _lan_ok(f"http://{host}:{port}", source="derived_lan_host")
        if hit:
            return hit

    return _empty(source="lan_unknown")


def derive_managed_public_url(
    *,
    host_port: int = _DEFAULT_TUNARR_PORT,
    published_host_ip: Optional[str] = None,
    environ: Optional[Mapping[str, str]] = None,
) -> str:
    """LAN-facing Tunarr base for managed Docker starts (Plex paste / public_url).

    Never returns host.docker.internal. Empty when no LAN IP can be derived.
    """
    from projectionist.envcompat import branded_env, resolve_env

    env = environ if environ is not None else os.environ
    port = int(host_port or _DEFAULT_TUNARR_PORT)

    candidates: List[str] = []
    if environ is None:
        for raw in (
            branded_env("TUNARR_PUBLIC_URL"),
            branded_env("HOST_IP"),
            resolve_env("HOST_IP"),
        ):
            if raw:
                candidates.append(str(raw).strip())
    else:
        for key in (
            "PROJECTIONIST_TUNARR_PUBLIC_URL",
            "CURATORX_TUNARR_PUBLIC_URL",
            "PROJECTIONIST_HOST_IP",
            "CURATORX_HOST_IP",
            "HOST_IP",
        ):
            if env.get(key):
                candidates.append(str(env[key]).strip())
    if published_host_ip:
        candidates.append(str(published_host_ip).strip())

    for raw in candidates:
        if not raw:
            continue
        if "://" in raw or raw.startswith("http"):
            host = _hostname_from_url_or_host(raw)
            if is_docker_only_host(host):
                continue
            # Full URL override (TUNARR_PUBLIC_URL)
            if "://" in raw:
                return normalize_tunarr_base(raw)
            return f"http://{host}:{port}"
        host = _hostname_from_url_or_host(raw)
        if is_docker_only_host(host):
            continue
        return f"http://{host}:{port}"
    return ""


def hdhr_url(tunarr_base: str) -> str:
    """Tuner discovery URL Plex accepts for Tunarr's HDHomeRun emulator."""
    base = normalize_tunarr_base(tunarr_base)
    if not base:
        return ""
    # Tunarr serves HDHR device XML at root; Plex "HDHomeRun" tuner uses the base host.
    return f"{base}/"


def xmltv_url(tunarr_base: str) -> str:
    base = normalize_tunarr_base(tunarr_base)
    if not base:
        return ""
    return f"{base}/api/xmltv.xml"


def probe_existing_plex_livetv(settings: Any = None, *, timeout: int = 5) -> Dict[str, Any]:
    """Soft probe for existing Plex Live TV / DVR devices.

    Returns ``status`` of ``detected`` | ``none`` | ``unknown``. Detection uses
    best-effort Plex endpoints that vary by PMS version — never treat failure as
    "no Live TV" and never block attach on this signal.
    """
    if settings is None:
        return {
            "status": "unknown",
            "ok": None,
            "device_count": None,
            "message": (
                "Plex Live TV detection was not run. If you already have an OTA "
                "tuner, keep it — add Tunarr as another network tuner."
            ),
        }
    plex_url = str(getattr(settings, "plex_url", "") or "").strip()
    plex_token = str(getattr(settings, "plex_token", "") or "").strip()
    if not plex_url or not plex_token:
        return {
            "status": "unknown",
            "ok": None,
            "device_count": None,
            "message": (
                "Plex is not configured here, so existing tuners cannot be listed. "
                "If you already use OTA Live TV, leave that setup alone and add "
                "Tunarr as an additional network tuner."
            ),
        }
    try:
        from projectionist.connectors.plex import PlexClient

        client = PlexClient(plex_url, plex_token, timeout=timeout)
    except Exception as error:  # noqa: BLE001
        return {
            "status": "unknown",
            "ok": None,
            "device_count": None,
            "message": (
                "Could not open a Plex client for Live TV detection "
                f"({str(error)[:120]}). Add Tunarr as another tuner; do not remove OTA."
            ),
        }

    # Prefer /livetv/dvrs (DVR setups). Fall back to /livetv/tuners when present.
    # Either path failing → unknown (honest), not "none".
    counts: List[int] = []
    last_error = ""
    for path, tags in (
        ("/livetv/dvrs", ("Dvr", "DVR")),
        ("/livetv/tuners", ("Device", "Tuner", "MediaGrabber")),
    ):
        try:
            root = client._request_xml(path)
        except Exception as error:  # noqa: BLE001
            last_error = str(error)[:160]
            continue
        if root is None:
            continue
        n = 0
        for tag in tags:
            n += len(list(root.iter(tag)))
        # Also count direct children that look like devices when tags differ.
        if n == 0:
            n = sum(
                1
                for child in list(root)
                if str(getattr(child, "tag", "") or "")
                not in ("", "MediaContainer", "Size")
            )
        counts.append(n)

    if not counts and last_error:
        return {
            "status": "unknown",
            "ok": None,
            "device_count": None,
            "message": (
                "Could not reliably read Plex Live TV devices "
                f"({last_error}). If you already have OTA, keep it — Tunarr is "
                "added as another tuner, not a replacement."
            ),
        }
    if not counts:
        return {
            "status": "unknown",
            "ok": None,
            "device_count": None,
            "message": (
                "Plex Live TV device listing is unavailable on this server build. "
                "Add Tunarr as an additional network tuner; leave any OTA DVR alone."
            ),
        }

    device_count = max(counts)
    if device_count > 0:
        return {
            "status": "detected",
            "ok": True,
            "device_count": device_count,
            "message": (
                "Existing Live TV setup detected — Tunarr will be added as another "
                "tuner. Keep your OTA / current DVR; do not remove or replace it."
            ),
        }
    return {
        "status": "none",
        "ok": True,
        "device_count": 0,
        "message": (
            "No existing Plex Live TV / DVR devices were listed. You can add Tunarr "
            "as your first network tuner — or as another tuner later if you add OTA."
        ),
    }


def build_plex_attach(
    settings: Any = None,
    *,
    tunarr_url: Optional[str] = None,
    request_host: Optional[str] = None,
    discovery_ok: Optional[bool] = None,
    existing_livetv: Optional[Dict[str, Any]] = None,
    discovery_base_url: Optional[str] = None,
) -> Dict[str, Any]:
    """Checklist + copy URLs for adding Tunarr *alongside* existing Plex Live TV.

    Paste URLs use a host-facing Tunarr base (LAN IP / public_url). Discovery probes
    may still use the Docker-side ``tunarr.url`` (e.g. host.docker.internal).
    """
    tunarr = getattr(settings, "tunarr", None) if settings is not None else None
    api_url = str(
        tunarr_url or (getattr(tunarr, "url", "") if tunarr else "") or ""
    ).strip()
    facing = resolve_plex_facing_tunarr_base(
        settings,
        tunarr_url=api_url,
        request_host=request_host,
    )
    url = str(facing.get("base_url") or "").strip()
    hdhr = hdhr_url(url)
    xmltv = xmltv_url(url)
    host = _hostname_from_url_or_host(url)

    livetv = existing_livetv if isinstance(existing_livetv, dict) else None
    if livetv is None:
        livetv = probe_existing_plex_livetv(settings)

    coexist_note = (
        "Plex supports multiple tuners and guide sources. Tunarr is an "
        "*additional* network tuner — leave any OTA HDHomeRun / antenna DVR in "
        "place. Projectionist never asks you to wipe or replace existing Live TV."
    )

    steps: List[Dict[str, str]] = [
        {
            "title": "Open Plex Live TV & DVR (keep what you have)",
            "body": (
                "In Plex, go to Settings → Live TV & DVR (Plex Pass). "
                "If you already see an OTA or HDHomeRun device, leave it configured — "
                "you will add Tunarr next to it, not instead of it."
            ),
        },
        {
            "title": "Add another network tuner (Tunarr)",
            "body": (
                "Choose Add device / Set up Plex DVR → add a network tuner / HDHomeRun. "
                "Paste the Tunarr tuner URL below (or the host if Plex only wants an IP). "
                "Use a LAN address your Plex server can reach — not host.docker.internal. "
                "Do not remove your existing OTA tuner during this step."
            ),
        },
        {
            "title": "Attach Tunarr’s XMLTV guide for that tuner",
            "body": (
                "When Plex asks for an EPG / guide source for the *new* tuner, paste "
                "the guide URL. Your OTA guide mapping can stay as it is — Plex merges "
                "sources per tuner. You do not need Tunarr’s admin UI."
            ),
        },
        {
            "title": "Scan channels; mind number ranges",
            "body": (
                f"Let Plex scan the new Tunarr device. Starter stations use virtual "
                f"channel numbers from {_VIRTUAL_CHANNEL_FLOOR}+ so they usually sit "
                "above typical OTA majors — if a number collides, renumber in Tunarr "
                "or Plex. Then watch from Plex Live TV (Projectionist does not play "
                "channels in-app)."
            ),
        },
    ]

    discovered: Optional[bool] = discovery_ok
    discovery_message = ""
    if discovered is True:
        discovery_message = "Tuner looks reachable from Projectionist."
    elif discovered is False:
        discovery_message = (
            "Could not probe the tuner from here — paste the URLs into Plex anyway "
            "if Tunarr is up on your network."
        )
    else:
        discovery_message = "Discovery check not run yet."

    docker_only = bool(facing.get("docker_only")) or is_docker_only_host(host)
    # Harden: never put sibling DNS / loopback into Plex paste fields.
    if docker_only or not url:
        hdhr = ""
        xmltv = ""
        host = ""
        url = ""
        warning = (
            "Set a LAN Tunarr address so Plex can reach the tuner. "
            "Projectionist talks to Tunarr over host.docker.internal internally — "
            "that address must never be pasted into Plex. Set tunarr.public_url "
            "(e.g. http://10.10.1.202:8000), PROJECTIONIST_HOST_IP, or "
            "PROJECTIONIST_TUNARR_PUBLIC_URL, then reopen these steps."
        )
    else:
        warning = ""

    return {
        "tunarr_url": url,
        "tunarr_api_url": api_url,
        "tuner_url": hdhr,
        "guide_url": xmltv,
        "hdhr_url": hdhr,
        "xmltv_url": xmltv,
        "host_hint": host,
        "url_source": facing.get("source") or "",
        "docker_only_url": docker_only or not bool(hdhr),
        "needs_lan_url": not bool(hdhr),
        "warning": warning,
        "steps": steps,
        "coexistence": {
            "mode": "additional_tuner",
            "note": coexist_note,
            "virtual_channel_floor": _VIRTUAL_CHANNEL_FLOOR,
            "existing_livetv": livetv,
        },
        "existing_livetv": livetv,
        "discovery": {
            "ok": discovered,
            "message": discovery_message,
            "probed_base": discovery_base_url or api_url,
        },
        "copy": {
            "tuner": hdhr,
            "guide": xmltv,
        },
    }


def probe_tuner_discovery(tunarr_base: str, *, timeout: int = 5) -> Dict[str, Any]:
    """Best-effort GET of Tunarr device / discover endpoint."""
    base = normalize_tunarr_base(tunarr_base)
    if not base:
        return {"ok": False, "message": "Tunarr URL is not configured"}
    from projectionist.connectors.http import request_json

    # Prefer device.xml / discover.json style probes; fall back to system health.
    candidates = (
        f"{base}/discover.json",
        f"{base}/device.xml",
        f"{base}/api/system/health",
    )
    last_error = ""
    for url in candidates:
        try:
            if url.endswith(".xml"):
                # request_json may fail on XML — use raw health instead
                continue
            payload = request_json(url, timeout=timeout)
            if payload is not None:
                return {"ok": True, "message": "Tuner / Tunarr endpoint responded.", "probed": url}
        except Exception as error:  # noqa: BLE001
            last_error = str(error)[:200]
    # Final health probe via client
    try:
        from projectionist.connectors.tunarr import tunarr_reachable

        reach = tunarr_reachable(base, timeout=timeout)
        if reach.get("reachable"):
            return {
                "ok": True,
                "message": "Tunarr is reachable (health). Confirm tuner in Plex if needed.",
            }
        last_error = str(reach.get("error") or last_error)
    except Exception as error:  # noqa: BLE001
        last_error = str(error)[:200]
    return {"ok": False, "message": last_error or "Discovery probe failed"}
