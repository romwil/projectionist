"""Plain-language Plex Live TV attach helpers (HDHR + XMLTV URLs).

Tunarr is added as an *additional* network tuner alongside any existing OTA /
HDHomeRun / DVR setup. Projectionist never instructs owners to remove or replace
existing Live TV hardware.
"""

from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Mapping, Optional, Tuple
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


def host_port_for_plex(tunarr_base: str) -> str:
    """Bare ``host:port`` for Plex's manual HDHomeRun network-address field."""
    base = normalize_tunarr_base(tunarr_base)
    if not base:
        return ""
    parsed = urlparse(base if "://" in base else f"http://{base}")
    host = str(parsed.hostname or "").strip()
    if not host or is_docker_only_host(host):
        return ""
    port = parsed.port or tunarr_port_from_url(base)
    return f"{host}:{port}"


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
    manual_address = host_port_for_plex(url)

    livetv = existing_livetv if isinstance(existing_livetv, dict) else None
    if livetv is None:
        livetv = probe_existing_plex_livetv(settings)

    coexist_note = (
        "Plex supports multiple tuners. Tunarr is an *additional* HDHomeRun-style "
        "network tuner — leave any OTA / antenna DVR in place. The Plex UI has no "
        "XMLTV field in Tuner Setup, Device Settings, or DVR Settings once a "
        "commercial ZIP guide is on the server. After Tunarr is added as a tuner, "
        "use Admin → Attach Tunarr guide in Plex (PMS API) to put Tunarr on its "
        "own XMLTV DVR — OTA commercial guide stays untouched."
    )

    address_hint = manual_address or "host:port from the tuner URL below"
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
            "title": "Tuner Setup — select Tunarr only",
            "body": (
                "Start Set up Plex DVR / Add device. Select the discovered Tunarr card "
                f"(for example {address_hint}). There is no XMLTV option on this screen. "
                "Only if it is missing: open "
                '"Don\'t see your HDHomeRun device? Enter its network address manually" '
                f"and paste {address_hint}."
            ),
        },
        {
            "title": "Postal code + temporary commercial EPG",
            "body": (
                "Enter any US ZIP so Next unlocks (wizard gate only). EPG Location lists "
                "commercial lineups only (Fios / DIRECTV / Local Broadcast) — pick any "
                "temporary lineup so Plex finishes adding the tuner. Fake cable names on "
                "Tunarr stations are expected until you attach the guide in Admin."
            ),
        },
        {
            "title": "Attach Tunarr XMLTV via Projectionist (not Plex UI)",
            "body": (
                "Plex Device Settings and DVR Settings do not offer an XMLTV URL. "
                "Back in Admin → Live Channels, click Attach Tunarr guide in Plex. "
                "Projectionist calls the PMS API: moves Tunarr onto its own DVR with "
                f"Tunarr XMLTV ({xmltv or 'the guide URL below'}) and maps channels. "
                "Your OTA DVR and commercial guide stay untouched. Then refresh / watch "
                "in Plex Live TV."
            ),
        },
        {
            "title": "Scan channels; mind number ranges",
            "body": (
                f"Starter stations use virtual channel numbers from {_VIRTUAL_CHANNEL_FLOOR}+ "
                "so they usually sit above typical OTA majors — if a number collides, "
                "renumber in Tunarr or Plex. Watch here (/live) or in Plex Live TV."
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
        manual_address = ""
        warning = (
            "Set a LAN Tunarr address so Plex can reach the tuner. "
            "Projectionist talks to Tunarr over host.docker.internal internally — "
            "that address must never be pasted into Plex. Set tunarr.public_url "
            "(e.g. http://10.10.1.202:18765), PROJECTIONIST_HOST_IP, or "
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
        "manual_address": manual_address,
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
            "guide_warning": (
                "Plex UI has no XMLTV paste in Tuner Setup, Device Settings, or DVR "
                "Settings when a commercial ZIP guide is already configured. After "
                "the Tunarr tuner exists, use Admin → Attach Tunarr guide in Plex "
                "(PMS API) — that creates a separate XMLTV DVR for Tunarr and leaves "
                "OTA commercial guide alone."
            ),
            "api_attach": True,
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
            "manual_address": manual_address,
        },
    }



def xmltv_lineup_uri(xmltv: str, *, friendly_name: str = "Projectionist") -> str:
    """Plex EPG lineup URI for an HTTP XMLTV guide URL."""
    guide = normalize_tunarr_base(xmltv)
    name = str(friendly_name or "Projectionist").strip() or "Projectionist"
    # PMS accepts the raw URL in the lineup path (verified on Automat / PMS Pass).
    return f"lineup://tv.plex.providers.epg.xmltv/{guide}#{name}"


def _plex_xml(client: Any, path: str, *, method: str = "GET", timeout: Optional[int] = None):
    from urllib.parse import quote

    from projectionist.connectors.http import request_xml

    separator = "&" if "?" in path else "?"
    url = f"{client.base_url}{path}{separator}X-Plex-Token={quote(client.token)}"
    return request_xml(
        url,
        method=method,
        headers={"Accept": "application/xml"},
        timeout=timeout or getattr(client, "timeout", 30),
    )


def _mc_error(root: Any) -> str:
    if root is None:
        return "empty Plex response"
    status = str(root.attrib.get("status") or "").strip()
    message = str(root.attrib.get("message") or "").strip()
    if message and status == "-1":
        return message
    if status and status not in ("0", "200", "") and message:
        return message
    return ""


def _iter_devices(root: Any) -> List[Any]:
    if root is None:
        return []
    return list(root.iter("Device"))


def _iter_dvrs(root: Any) -> List[Any]:
    if root is None:
        return []
    return [n for n in root.iter("Dvr") if str(getattr(n, "tag", "")) == "Dvr"]


def _device_matches_tunarr(device: Any, *, tunarr_base: str, manual_address: str) -> bool:
    uri = str(device.attrib.get("uri") or "").strip().rstrip("/")
    device_id = str(device.attrib.get("deviceId") or "").strip().lower()
    title = str(device.attrib.get("title") or device.attrib.get("name") or "").strip().lower()
    make = str(device.attrib.get("make") or "").strip().lower()
    base = normalize_tunarr_base(tunarr_base)
    hostport = str(manual_address or "").strip()
    if device_id == "tunarr":
        return True
    if "tunarr" in make:
        return True
    if "projectionist" in title and ("tunarr" in title or "tunarr" in make):
        return True
    if base and uri.rstrip("/") == base.rstrip("/"):
        return True
    if hostport and hostport in uri:
        return True
    if base:
        host = _hostname_from_url_or_host(base)
        port = str(tunarr_port_from_url(base))
        if host and host in uri and port in uri:
            return True
    return False


def _lineup_matches_xmltv(lineup: str, xmltv: str) -> bool:
    lu = str(lineup or "")
    guide = normalize_tunarr_base(xmltv)
    return "tv.plex.providers.epg.xmltv" in lu and bool(guide) and guide in lu


def count_tunarr_hdhr_channels(tunarr_base: str, *, timeout: int = 8) -> int:
    """How many stations Tunarr advertises on its HDHomeRun lineup (truth for Plex)."""
    base = normalize_tunarr_base(tunarr_base)
    if not base:
        return 0
    from projectionist.connectors.http import request_json

    try:
        payload = request_json(f"{base}/lineup.json", timeout=timeout)
    except Exception:  # noqa: BLE001
        return 0
    if isinstance(payload, list):
        return len(payload)
    return 0


def count_plex_device_channels(client: Any, device_key: str, *, timeout: int = 20) -> int:
    """Channels Plex currently knows on a grabber device (post-scan cache)."""
    key = str(device_key or "").strip()
    if not key:
        return 0
    root = _plex_xml(client, f"/media/grabbers/devices/{key}/channels", timeout=timeout)
    if root is None:
        return 0
    return len(list(root.iter("DeviceChannel")))


def scan_plex_device_channels(
    client: Any,
    device_key: str,
    *,
    expected: int = 0,
    timeout: int = 45,
) -> Dict[str, Any]:
    """POST device scan and poll until DeviceChannel count reaches ``expected``."""
    key = str(device_key or "").strip()
    if not key:
        return {"ok": False, "count": 0, "message": "Missing device key for scan."}
    # Best-effort scan kick; some PMS builds return empty bodies or
    # ``Unknown source`` 500 for Tunarr HDHR — ignore and poll channels.
    try:
        from urllib.parse import quote

        from projectionist.connectors.http import request_empty

        scan_url = (
            f"{client.base_url}/media/grabbers/devices/{key}/scan"
            f"?X-Plex-Token={quote(client.token)}"
        )
        request_empty(scan_url, method="POST", timeout=min(timeout, 20))
    except Exception:  # noqa: BLE001
        pass
    try:
        _plex_xml(
            client,
            f"/media/grabbers/devices/{key}/channels",
            method="GET",
            timeout=min(timeout, 20),
        )
    except Exception:  # noqa: BLE001
        pass

    deadline = time.time() + max(5, int(timeout))
    last = 0
    stable = 0
    while time.time() < deadline:
        last = count_plex_device_channels(client, key, timeout=min(15, timeout))
        if expected > 0 and last >= expected:
            return {
                "ok": True,
                "count": last,
                "message": f"Plex device sees {last} Tunarr channel(s).",
            }
        if expected <= 0 and last > 0:
            stable += 1
            if stable >= 2:
                return {
                    "ok": True,
                    "count": last,
                    "message": f"Plex device sees {last} Tunarr channel(s).",
                }
        else:
            stable = 0
        time.sleep(1.0)
    return {
        "ok": bool(last) and (expected <= 0 or last >= expected),
        "count": last,
        "message": (
            f"Plex device scan timed out with {last} channel(s)"
            + (f" (expected {expected})." if expected else ".")
        ),
    }


def _put_device_channelmap(
    client: Any,
    *,
    device_key: str,
    device_uuid: str,
    lineup: str,
    timeout: int = 45,
) -> Tuple[List[Any], Optional[str]]:
    """Fetch EPG channelmap and PUT full mapping. Returns (mappings, error)."""
    from urllib.parse import quote, urlencode

    cmap = _plex_xml(
        client,
        "/livetv/epg/channelmap?" + urlencode({"device": device_uuid, "lineup": lineup}),
        timeout=timeout,
    )
    mappings = [
        m
        for m in (cmap.iter("ChannelMapping") if cmap is not None else [])
        if m.attrib.get("deviceIdentifier")
        and m.attrib.get("channelKey")
        and m.attrib.get("lineupIdentifier")
    ]
    if not mappings:
        return [], None
    enabled = [m.attrib["deviceIdentifier"] for m in mappings]
    parts = ["channelsEnabled=" + ",".join(enabled)]
    for m in mappings:
        di = m.attrib["deviceIdentifier"]
        parts.append(
            f"channelMappingByKey[{quote(di, safe='')}]="
            f"{quote(m.attrib['channelKey'], safe='')}"
        )
        parts.append(
            f"channelMapping[{quote(di, safe='')}]="
            f"{quote(m.attrib['lineupIdentifier'], safe='')}"
        )
    put = _plex_xml(
        client,
        f"/media/grabbers/devices/{device_key}/channelmap?" + "&".join(parts),
        method="PUT",
        timeout=timeout,
    )
    err = _mc_error(put)
    return mappings, (err or None)


def _reload_dvr_guide(client: Any, dvr_key: str, *, timeout: int = 45) -> None:
    from urllib.parse import quote

    from projectionist.connectors.http import request_empty

    reload_url = (
        f"{client.base_url}/livetv/dvrs/{dvr_key}/reloadGuide"
        f"?X-Plex-Token={quote(client.token)}"
    )
    request_empty(reload_url, method="POST", timeout=timeout)


def _mapping_complete(mapped: int, expected: int) -> bool:
    """True when Plex mapped at least every Tunarr HDHR station."""
    if expected <= 0:
        return mapped > 0
    return mapped >= expected


def _find_tunarr_device(
    devices_root: Any, *, tunarr_base: str, manual_address: str
) -> Any:
    return next(
        (
            d
            for d in _iter_devices(devices_root)
            if _device_matches_tunarr(d, tunarr_base=tunarr_base, manual_address=manual_address)
        ),
        None,
    )


def _plex_delete_empty(client: Any, path: str, *, timeout: int = 45) -> str:
    """DELETE that tolerates empty bodies / slow PMS (DVR delete often hangs)."""
    from urllib.parse import quote

    from projectionist.connectors.http import request_empty

    url = f"{client.base_url}{path}?X-Plex-Token={quote(client.token)}"
    try:
        request_empty(url, method="DELETE", timeout=timeout)
        return ""
    except Exception as error:  # noqa: BLE001
        return str(error)[:160]


def _delete_tunarr_xmltv_stack(
    client: Any,
    *,
    device_key: str,
    device_uuid: str,
    xmltv: str,
    timeout: int = 45,
) -> List[str]:
    """Remove Tunarr grabber + its XMLTV DVR only (never OTA cloud DVR)."""
    steps: List[str] = []
    dvrs_root = _plex_xml(client, "/livetv/dvrs", timeout=timeout)
    for dvr in _iter_dvrs(dvrs_root):
        lineup_attr = str(dvr.attrib.get("lineup") or "")
        dvr_key = str(dvr.attrib.get("key") or "").strip()
        owns = any(
            str(dev.attrib.get("uuid") or "") == device_uuid for dev in dvr.findall("Device")
        )
        if not dvr_key:
            continue
        if _lineup_matches_xmltv(lineup_attr, xmltv) or (
            owns and "tv.plex.providers.epg.xmltv" in lineup_attr
        ):
            # Detach device first when present, then drop the XMLTV DVR.
            if owns and device_key:
                err = _plex_delete_empty(
                    client,
                    f"/livetv/dvrs/{dvr_key}/devices/{device_key}",
                    timeout=min(timeout, 30),
                )
                if err:
                    steps.append(f"detach_device_warn_{dvr_key}")
            err = _plex_delete_empty(
                client,
                f"/livetv/dvrs/{dvr_key}",
                timeout=min(timeout, 45),
            )
            steps.append(
                f"deleted_xmltv_dvr_{dvr_key}" if not err else f"delete_dvr_warn_{dvr_key}"
            )
    if device_key:
        err = _plex_delete_empty(
            client,
            f"/media/grabbers/devices/{device_key}",
            timeout=min(timeout, 30),
        )
        steps.append(
            f"deleted_device_{device_key}" if not err else f"delete_device_warn_{device_key}"
        )
    return steps


def _is_safe_dead_grabber(device: Any, *, tunarr_base: str, manual_address: str) -> bool:
    """True for orphan dead tuners safe to delete (never OTA / Tunarr / alive)."""
    if device is None:
        return False
    status = str(device.attrib.get("status") or "").strip().lower()
    if status != "dead":
        return False
    if _device_matches_tunarr(device, tunarr_base=tunarr_base, manual_address=manual_address):
        return False
    device_id = str(device.attrib.get("deviceId") or "").strip()
    make = str(device.attrib.get("make") or "").strip().lower()
    uri = str(device.attrib.get("uri") or "").strip().lower()
    # Real Silicondust OTA boxes keep a hardware deviceId even when briefly dead.
    if device_id and make in {"silicondust", "hdhomerun"}:
        return False
    if "silicondust" in make and device_id:
        return False
    # Empty deviceId + unknown make (Automat: stale :7007 M3U) is the common junk.
    if not device_id and (make in {"", "unknown"} or "channels.m3u" in uri):
        return True
    return False


def prune_dead_grabber_devices(
    settings: Any = None,
    *,
    tunarr_url: Optional[str] = None,
    request_host: Optional[str] = None,
    timeout: int = 30,
) -> Dict[str, Any]:
    """Delete orphan dead HDHomeRun grabbers that are not OTA or Tunarr.

    Safe filter: ``status=dead``, not matching Tunarr, and either empty
    ``deviceId`` with Unknown make or a leftover ``channels.m3u`` URI. Never
    deletes alive devices or Silicondust hardware tuners.
    """
    if settings is None:
        return {"ok": False, "deleted": [], "message": "Settings required."}
    plex_url = str(getattr(settings, "plex_url", "") or "").strip()
    plex_token = str(getattr(settings, "plex_token", "") or "").strip()
    if not plex_url or not plex_token:
        return {"ok": False, "deleted": [], "message": "Plex not configured."}

    from projectionist.connectors.plex import PlexClient

    facing = resolve_plex_facing_tunarr_base(
        settings, tunarr_url=tunarr_url, request_host=request_host
    )
    base = str(facing.get("base_url") or "").strip()
    manual = host_port_for_plex(base)
    client = PlexClient(plex_url, plex_token, timeout=timeout)
    root = _plex_xml(client, "/media/grabbers/devices", timeout=timeout)
    deleted: List[Dict[str, str]] = []
    for device in _iter_devices(root):
        if not _is_safe_dead_grabber(
            device, tunarr_base=base, manual_address=manual
        ):
            continue
        key = str(device.attrib.get("key") or "").strip()
        if not key:
            continue
        det = _plex_xml(
            client,
            f"/media/grabbers/devices/{key}",
            method="DELETE",
            timeout=timeout,
        )
        err = _mc_error(det)
        if err:
            continue
        deleted.append(
            {
                "key": key,
                "uri": str(device.attrib.get("uri") or ""),
                "title": str(device.attrib.get("title") or ""),
            }
        )
    return {
        "ok": True,
        "deleted": deleted,
        "message": (
            f"Removed {len(deleted)} dead leftover tuner(s)."
            if deleted
            else "No orphan dead tuners to remove."
        ),
    }


def attach_tunarr_xmltv_to_plex(
    settings: Any = None,
    *,
    tunarr_url: Optional[str] = None,
    request_host: Optional[str] = None,
    friendly_name: str = "Projectionist",
    timeout: int = 90,
    force_recreate: bool = False,
    _recreate_attempted: bool = False,
) -> Dict[str, Any]:
    """Move Tunarr onto its own Plex DVR with Tunarr XMLTV via PMS API.

    Verified on Automat: Plex refuses to mix cloud EPG + XMLTV on one DVR
    (``Lineup is from a different provider``). Safe path is:
    register/find Tunarr device → remove it from any commercial-EPG DVR →
    ``POST /livetv/dvrs`` with ``lineup://tv.plex.providers.epg.xmltv/<url>#Name`` →
    device scan → channelmap → ``reloadGuide``. OTA devices on the cloud DVR
    are left alone.

    Success requires mapped count ≥ Tunarr HDHR lineup count (Mapped N/N).
    Stale short maps trigger one automatic Tunarr-only recreate.
    """
    from urllib.parse import urlencode

    from projectionist.connectors.plex import PlexClient

    if settings is None:
        return {"ok": False, "error": "Settings are required to reach Plex."}

    plex_url = str(getattr(settings, "plex_url", "") or "").strip()
    plex_token = str(getattr(settings, "plex_token", "") or "").strip()
    if not plex_url or not plex_token:
        return {"ok": False, "error": "Configure Plex URL and token first."}

    facing = resolve_plex_facing_tunarr_base(
        settings, tunarr_url=tunarr_url, request_host=request_host
    )
    base = str(facing.get("base_url") or "").strip()
    if not base or bool(facing.get("docker_only")):
        return {
            "ok": False,
            "error": (
                "Set a LAN Tunarr address (tunarr.public_url / HOST_IP) before "
                "attaching the guide — Plex cannot reach host.docker.internal."
            ),
        }

    xmltv = xmltv_url(base)
    manual = host_port_for_plex(base)
    lineup = xmltv_lineup_uri(xmltv, friendly_name=friendly_name)
    expected = count_tunarr_hdhr_channels(base, timeout=min(timeout, 10))
    client = PlexClient(plex_url, plex_token, timeout=timeout)
    steps_done: List[str] = []

    pruned = prune_dead_grabber_devices(
        settings,
        tunarr_url=tunarr_url,
        request_host=request_host,
        timeout=min(timeout, 30),
    )
    if pruned.get("deleted"):
        steps_done.append(f"pruned_dead_grabbers_{len(pruned['deleted'])}")

    devices_root = _plex_xml(client, "/media/grabbers/devices", timeout=timeout)
    device = _find_tunarr_device(
        devices_root, tunarr_base=base, manual_address=manual
    )

    if force_recreate and device is not None and not _recreate_attempted:
        steps_done.extend(
            _delete_tunarr_xmltv_stack(
                client,
                device_key=str(device.attrib.get("key") or ""),
                device_uuid=str(device.attrib.get("uuid") or ""),
                xmltv=xmltv,
                timeout=timeout,
            )
        )
        device = None
        steps_done.append("force_recreate")

    if device is None:
        reg = _plex_xml(
            client,
            "/media/grabbers/tv.plex.grabbers.hdhomerun/devices?"
            + urlencode({"uri": base}),
            method="POST",
            timeout=timeout,
        )
        err = _mc_error(reg)
        device = _find_tunarr_device(reg, tunarr_base=base, manual_address=manual)
        if device is None:
            devices_root = _plex_xml(client, "/media/grabbers/devices", timeout=timeout)
            device = _find_tunarr_device(
                devices_root, tunarr_base=base, manual_address=manual
            )
        if device is None:
            return {
                "ok": False,
                "error": err
                or "Plex did not register the Tunarr HDHomeRun device. Add it in Tuner Setup first.",
                "xmltv_url": xmltv,
                "expected": expected,
                "mapped": 0,
                "steps": steps_done,
            }
        steps_done.append("registered_device")

    device_uuid = str(device.attrib.get("uuid") or "").strip()
    device_key = str(device.attrib.get("key") or "").strip()
    if not device_uuid:
        return {
            "ok": False,
            "error": "Tunarr device has no Plex UUID.",
            "xmltv_url": xmltv,
            "expected": expected,
            "mapped": 0,
        }

    # Enable device if Plex left it disabled/dead in Channel Sources.
    status = str(device.attrib.get("status") or "").strip().lower()
    state = str(device.attrib.get("state") or "").strip().lower()
    if status == "dead" or state in {"disabled", "off"}:
        en = _plex_xml(
            client,
            f"/media/grabbers/devices/{device_key}?enabled=1",
            method="PUT",
            timeout=timeout,
        )
        if not _mc_error(en):
            steps_done.append("enabled_device")

    dvrs_root = _plex_xml(client, "/livetv/dvrs", timeout=timeout)
    home_dvr = None
    xmltv_dvr = None
    for dvr in _iter_dvrs(dvrs_root):
        lineup_attr = str(dvr.attrib.get("lineup") or "")
        owns = any(
            str(dev.attrib.get("uuid") or "") == device_uuid for dev in dvr.findall("Device")
        )
        if _lineup_matches_xmltv(lineup_attr, xmltv):
            xmltv_dvr = dvr
        if owns:
            home_dvr = dvr

    if home_dvr is not None:
        home_key = str(home_dvr.attrib.get("key") or "")
        home_lineup = str(home_dvr.attrib.get("lineup") or "")
        if not _lineup_matches_xmltv(home_lineup, xmltv):
            det = _plex_xml(
                client,
                f"/livetv/dvrs/{home_key}/devices/{device_key}",
                method="DELETE",
                timeout=timeout,
            )
            err = _mc_error(det)
            if err:
                return {
                    "ok": False,
                    "error": f"Could not detach Tunarr from commercial DVR: {err}",
                    "xmltv_url": xmltv,
                    "expected": expected,
                    "mapped": 0,
                }
            steps_done.append(f"detached_from_dvr_{home_key}")
            home_dvr = None

    dvr_key = ""
    if home_dvr is not None and _lineup_matches_xmltv(
        str(home_dvr.attrib.get("lineup") or ""), xmltv
    ):
        dvr_key = str(home_dvr.attrib.get("key") or "")
        steps_done.append("reused_xmltv_dvr")
    elif xmltv_dvr is not None and home_dvr is None:
        dvr_key = str(xmltv_dvr.attrib.get("key") or "")
        add = _plex_xml(
            client,
            f"/livetv/dvrs/{dvr_key}/devices/{device_key}",
            method="PUT",
            timeout=timeout,
        )
        if not _mc_error(add):
            steps_done.append(f"added_device_to_dvr_{dvr_key}")
        else:
            dvr_key = ""

    if not dvr_key:
        created = _plex_xml(
            client,
            "/livetv/dvrs?"
            + urlencode({"language": "eng", "device": device_uuid, "lineup": lineup}),
            method="POST",
            timeout=timeout,
        )
        err = _mc_error(created)
        dvr_node = next(iter(_iter_dvrs(created)), None)
        if dvr_node is None:
            dvrs_root = _plex_xml(client, "/livetv/dvrs", timeout=timeout)
            for dvr in _iter_dvrs(dvrs_root):
                if any(
                    str(dev.attrib.get("uuid") or "") == device_uuid
                    for dev in dvr.findall("Device")
                ) and _lineup_matches_xmltv(str(dvr.attrib.get("lineup") or ""), xmltv):
                    dvr_node = dvr
                    break
            if dvr_node is None:
                return {
                    "ok": False,
                    "error": err or "Plex did not create an XMLTV DVR for Tunarr.",
                    "xmltv_url": xmltv,
                    "lineup": lineup,
                    "expected": expected,
                    "mapped": 0,
                    "steps": steps_done,
                }
        dvr_key = str(dvr_node.attrib.get("key") or "")
        steps_done.append(f"created_dvr_{dvr_key}")
        for dev in dvr_node.findall("Device"):
            if str(dev.attrib.get("uuid") or "") == device_uuid:
                device_key = str(dev.attrib.get("key") or device_key)

    if not dvr_key or not device_key:
        return {
            "ok": False,
            "error": "Missing DVR or device key after attach.",
            "expected": expected,
            "mapped": 0,
            "steps": steps_done,
        }

    scan = scan_plex_device_channels(
        client,
        device_key,
        expected=expected,
        timeout=min(timeout, 60),
    )
    steps_done.append(f"scanned_device_{scan.get('count', 0)}")
    device_channel_count = int(scan.get("count") or 0)

    mappings, map_err = _put_device_channelmap(
        client,
        device_key=device_key,
        device_uuid=device_uuid,
        lineup=lineup,
        timeout=timeout,
    )
    if map_err:
        return {
            "ok": False,
            "error": f"DVR created but channel mapping failed: {map_err}",
            "dvr_key": dvr_key,
            "xmltv_url": xmltv,
            "mapped": 0,
            "expected": expected,
            "device_channels": device_channel_count,
            "steps": steps_done,
        }
    if mappings:
        steps_done.append(f"mapped_{len(mappings)}_channels")
    else:
        steps_done.append("no_channel_mappings")

    _reload_dvr_guide(client, dvr_key, timeout=timeout)
    steps_done.append("reload_guide")

    mapped = len(mappings)
    complete = _mapping_complete(mapped, expected)

    # Stale HDHR cache / orphan XMLTV DVR: recreate Tunarr stack once.
    if not complete and not _recreate_attempted:
        steps_done.extend(
            _delete_tunarr_xmltv_stack(
                client,
                device_key=device_key,
                device_uuid=device_uuid,
                xmltv=xmltv,
                timeout=timeout,
            )
        )
        retry = attach_tunarr_xmltv_to_plex(
            settings,
            tunarr_url=tunarr_url,
            request_host=request_host,
            friendly_name=friendly_name,
            timeout=timeout,
            force_recreate=False,
            _recreate_attempted=True,
        )
        retry_steps = list(retry.get("steps") or [])
        retry["steps"] = steps_done + ["recreate_after_short_map"] + retry_steps
        return retry

    message = (
        f"Mapped {mapped}/{expected or mapped} Tunarr channel(s) on Plex DVR {dvr_key}."
        if expected
        else f"Mapped {mapped} Tunarr channel(s) on Plex DVR {dvr_key}."
    )
    if complete:
        message += " OTA commercial DVR left in place."
    else:
        message = (
            f"Plex still maps only {mapped}/{expected} Tunarr channels after attach. "
            "Open Admin → Repair Plex tuner/guide, or re-add the tuner in Plex Channel Sources."
        )

    return {
        "ok": complete,
        "dvr_key": dvr_key,
        "device_key": device_key,
        "device_uuid": device_uuid,
        "xmltv_url": xmltv,
        "lineup": lineup,
        "mapped": mapped,
        "expected": expected,
        "device_channels": device_channel_count,
        "device_present": True,
        "steps": steps_done,
        "error": None if complete else message,
        "message": message,
    }


def refresh_plex_live_tv_channels(
    settings: Any = None,
    *,
    tunarr_url: Optional[str] = None,
    request_host: Optional[str] = None,
    friendly_name: str = "Projectionist",
    timeout: int = 90,
    allow_attach: bool = True,
) -> Dict[str, Any]:
    """Scan Tunarr HDHR → remap all channels → reloadGuide.

    After publish: always force a device scan so new channel numbers appear.
    When the Tunarr device or XMLTV DVR is missing, runs the full attach path
    (never a silent no-op). Returns ``ok`` only when Mapped N/N.
    """
    from projectionist.connectors.plex import PlexClient

    if settings is None:
        return {
            "ok": False,
            "attach_needed": True,
            "mapped": 0,
            "expected": 0,
            "message": "Settings required to refresh Plex channels.",
        }
    plex_url = str(getattr(settings, "plex_url", "") or "").strip()
    plex_token = str(getattr(settings, "plex_token", "") or "").strip()
    if not plex_url or not plex_token:
        return {
            "ok": False,
            "attach_needed": True,
            "mapped": 0,
            "expected": 0,
            "message": "Configure Plex URL and token first.",
        }

    facing = resolve_plex_facing_tunarr_base(
        settings, tunarr_url=tunarr_url, request_host=request_host
    )
    base = str(facing.get("base_url") or "").strip()
    if not base or bool(facing.get("docker_only")):
        return {
            "ok": False,
            "attach_needed": True,
            "mapped": 0,
            "expected": 0,
            "message": (
                "Set a LAN Tunarr address (tunarr.public_url / HOST_IP) before "
                "Plex can map new channels."
            ),
        }

    xmltv = xmltv_url(base)
    manual = host_port_for_plex(base)
    lineup = xmltv_lineup_uri(xmltv, friendly_name=friendly_name)
    expected = count_tunarr_hdhr_channels(base, timeout=min(timeout, 10))
    client = PlexClient(plex_url, plex_token, timeout=timeout)
    steps_done: List[str] = []

    devices_root = _plex_xml(client, "/media/grabbers/devices", timeout=timeout)
    device = _find_tunarr_device(
        devices_root, tunarr_base=base, manual_address=manual
    )
    if device is None:
        if not allow_attach:
            return {
                "ok": False,
                "attach_needed": True,
                "mapped": 0,
                "expected": expected,
                "device_present": False,
                "xmltv_url": xmltv,
                "message": (
                    f"Tunarr device missing from Plex Channel Sources "
                    f"(Tunarr has {expected} channel(s)). Run Repair Plex tuner/guide."
                ),
            }
        attached = attach_tunarr_xmltv_to_plex(
            settings,
            tunarr_url=tunarr_url,
            request_host=request_host,
            friendly_name=friendly_name,
            timeout=timeout,
            force_recreate=True,
        )
        attached["attach_needed"] = not bool(attached.get("ok"))
        attached.setdefault("expected", expected)
        attached.setdefault("device_present", bool(attached.get("ok")))
        return attached

    device_uuid = str(device.attrib.get("uuid") or "").strip()
    device_key = str(device.attrib.get("key") or "").strip()
    if not device_uuid or not device_key:
        if allow_attach:
            return attach_tunarr_xmltv_to_plex(
                settings,
                tunarr_url=tunarr_url,
                request_host=request_host,
                friendly_name=friendly_name,
                timeout=timeout,
                force_recreate=True,
            )
        return {
            "ok": False,
            "attach_needed": True,
            "mapped": 0,
            "expected": expected,
            "device_present": False,
            "message": "Tunarr grabber is missing Plex keys — run Repair Plex tuner/guide.",
        }

    status = str(device.attrib.get("status") or "").strip().lower()
    if status == "dead":
        if allow_attach:
            attached = attach_tunarr_xmltv_to_plex(
                settings,
                tunarr_url=tunarr_url,
                request_host=request_host,
                friendly_name=friendly_name,
                timeout=timeout,
                force_recreate=True,
            )
            attached["attach_needed"] = not bool(attached.get("ok"))
            return attached
        return {
            "ok": False,
            "attach_needed": True,
            "mapped": 0,
            "expected": expected,
            "device_present": True,
            "device_status": "dead",
            "xmltv_url": xmltv,
            "message": (
                "Tunarr device is dead in Plex Channel Sources — "
                "run Repair Plex tuner/guide."
            ),
        }

    dvrs_root = _plex_xml(client, "/livetv/dvrs", timeout=timeout)
    dvr_key = ""
    for dvr in _iter_dvrs(dvrs_root):
        owns = any(
            str(dev.attrib.get("uuid") or "") == device_uuid for dev in dvr.findall("Device")
        )
        if owns and _lineup_matches_xmltv(str(dvr.attrib.get("lineup") or ""), xmltv):
            dvr_key = str(dvr.attrib.get("key") or "")
            break
        if _lineup_matches_xmltv(str(dvr.attrib.get("lineup") or ""), xmltv) and not dvr_key:
            dvr_key = str(dvr.attrib.get("key") or "")

    if not dvr_key:
        if allow_attach:
            attached = attach_tunarr_xmltv_to_plex(
                settings,
                tunarr_url=tunarr_url,
                request_host=request_host,
                friendly_name=friendly_name,
                timeout=timeout,
            )
            attached["attach_needed"] = not bool(attached.get("ok"))
            return attached
        return {
            "ok": False,
            "attach_needed": True,
            "mapped": 0,
            "expected": expected,
            "device_present": True,
            "xmltv_url": xmltv,
            "message": "No Tunarr XMLTV DVR found — run Attach / Repair Plex tuner/guide.",
        }

    scan = scan_plex_device_channels(
        client,
        device_key,
        expected=expected,
        timeout=min(timeout, 60),
    )
    steps_done.append(f"scanned_device_{scan.get('count', 0)}")
    device_channel_count = int(scan.get("count") or 0)

    # Plex still only sees the old 4 → recreate Tunarr stack.
    if expected > 0 and device_channel_count < expected and allow_attach:
        attached = attach_tunarr_xmltv_to_plex(
            settings,
            tunarr_url=tunarr_url,
            request_host=request_host,
            friendly_name=friendly_name,
            timeout=timeout,
            force_recreate=True,
        )
        attached["attach_needed"] = not bool(attached.get("ok"))
        attached.setdefault("steps", [])
        attached["steps"] = steps_done + ["recreate_stale_device_channels"] + list(
            attached.get("steps") or []
        )
        return attached

    mappings, map_err = _put_device_channelmap(
        client,
        device_key=device_key,
        device_uuid=device_uuid,
        lineup=lineup,
        timeout=timeout,
    )
    if map_err:
        return {
            "ok": False,
            "attach_needed": False,
            "mapped": 0,
            "expected": expected,
            "device_present": True,
            "device_channels": device_channel_count,
            "dvr_key": dvr_key,
            "error": f"Channel mapping failed: {map_err}",
            "message": f"Channel mapping failed: {map_err}",
            "steps": steps_done,
        }
    if mappings:
        steps_done.append(f"mapped_{len(mappings)}_channels")
    else:
        steps_done.append("no_channel_mappings")

    _reload_dvr_guide(client, dvr_key, timeout=timeout)
    steps_done.append("reload_guide")

    mapped = len(mappings)
    complete = _mapping_complete(mapped, expected)
    if not complete and allow_attach:
        attached = attach_tunarr_xmltv_to_plex(
            settings,
            tunarr_url=tunarr_url,
            request_host=request_host,
            friendly_name=friendly_name,
            timeout=timeout,
            force_recreate=True,
        )
        attached["attach_needed"] = not bool(attached.get("ok"))
        attached.setdefault("steps", [])
        attached["steps"] = steps_done + ["recreate_short_channelmap"] + list(
            attached.get("steps") or []
        )
        return attached

    if complete:
        message = (
            f"Mapped {mapped}/{expected} Tunarr channel(s) in Plex · guide reloading."
            if expected
            else f"Mapped {mapped} channel(s) in Plex · guide reloading."
        )
    else:
        message = (
            f"Plex mapped only {mapped}/{expected} Tunarr channels — "
            "run Repair Plex tuner/guide."
        )

    return {
        "ok": complete,
        "attach_needed": not complete,
        "mapped": mapped,
        "expected": expected,
        "device_present": True,
        "device_channels": device_channel_count,
        "dvr_key": dvr_key,
        "device_key": device_key,
        "device_uuid": device_uuid,
        "xmltv_url": xmltv,
        "steps": steps_done,
        "error": None if complete else message,
        "message": message,
    }


def probe_plex_tunarr_mapping(
    settings: Any = None,
    *,
    tunarr_url: Optional[str] = None,
    request_host: Optional[str] = None,
    timeout: int = 20,
) -> Dict[str, Any]:
    """Honest Admin status: HDHR reachable? device present? Mapped N/N?"""
    facing = resolve_plex_facing_tunarr_base(
        settings, tunarr_url=tunarr_url, request_host=request_host
    )
    base = str(facing.get("base_url") or "").strip()
    hdhr_ok = False
    expected = 0
    if base and not facing.get("docker_only"):
        expected = count_tunarr_hdhr_channels(base, timeout=min(timeout, 8))
        hdhr_ok = expected > 0 or bool(probe_tuner_discovery(base, timeout=5).get("ok"))

    plex_url = str(getattr(settings, "plex_url", "") or "").strip() if settings else ""
    plex_token = str(getattr(settings, "plex_token", "") or "").strip() if settings else ""
    if not plex_url or not plex_token or not base:
        return {
            "ok": False,
            "hdhr_ok": hdhr_ok,
            "device_present": False,
            "mapped": 0,
            "expected": expected,
            "message": (
                f"Tunarr HDHR {'reachable' if hdhr_ok else 'unreachable'}; "
                "Plex not configured for mapping probe."
            ),
        }

    from projectionist.connectors.plex import PlexClient

    xmltv = xmltv_url(base)
    manual = host_port_for_plex(base)
    client = PlexClient(plex_url, plex_token, timeout=timeout)
    try:
        devices_root = _plex_xml(client, "/media/grabbers/devices", timeout=timeout)
    except Exception as error:  # noqa: BLE001
        return {
            "ok": False,
            "hdhr_ok": hdhr_ok,
            "device_present": False,
            "mapped": 0,
            "expected": expected,
            "message": f"Could not list Plex devices ({str(error)[:120]}).",
        }
    device = _find_tunarr_device(
        devices_root, tunarr_base=base, manual_address=manual
    )
    if device is None:
        return {
            "ok": False,
            "hdhr_ok": hdhr_ok,
            "device_present": False,
            "mapped": 0,
            "expected": expected,
            "message": (
                f"Tunarr HDHR {'up' if hdhr_ok else 'down'} with {expected} channel(s); "
                "Plex Channel Sources has no Tunarr/Projectionist device — "
                "run Repair Plex tuner/guide."
            ),
        }

    device_key = str(device.attrib.get("key") or "")
    device_uuid = str(device.attrib.get("uuid") or "")
    device_status = str(device.attrib.get("status") or "")
    device_channels = count_plex_device_channels(client, device_key, timeout=timeout)
    mapped = 0
    dvr_key = ""
    dvr_error = ""
    try:
        dvrs_root = _plex_xml(client, "/livetv/dvrs", timeout=timeout)
        for dvr in _iter_dvrs(dvrs_root):
            if not _lineup_matches_xmltv(str(dvr.attrib.get("lineup") or ""), xmltv):
                continue
            dvr_key = str(dvr.attrib.get("key") or "")
            mapped = len(
                [
                    m
                    for m in dvr.iter("ChannelMapping")
                    if str(m.attrib.get("enabled") or "1") not in {"0", "false", "False"}
                    and m.attrib.get("deviceIdentifier")
                ]
            )
            if mapped == 0:
                # ChannelMapping nodes may omit enabled; count all.
                mapped = len(list(dvr.iter("ChannelMapping")))
            break
    except Exception as error:  # noqa: BLE001
        dvr_error = str(error)[:120]

    # If DVR listing is briefly wedged (PMS after delete), still report device + HDHR.
    if dvr_error and not mapped and device_channels:
        mapped = device_channels

    complete = (
        bool(device)
        and device_status.lower() != "dead"
        and not dvr_error
        and _mapping_complete(mapped, expected)
    )
    message = (
        f"Mapped {mapped}/{expected or mapped} · "
        f"Tunarr HDHR {'ok' if hdhr_ok else 'down'} · "
        f"Plex device {device_status or 'present'}"
        + (f" · DVR {dvr_key}" if dvr_key else "")
    )
    if dvr_error:
        message += f" · DVR list busy ({dvr_error})"
    return {
        "ok": complete,
        "hdhr_ok": hdhr_ok,
        "device_present": True,
        "device_key": device_key,
        "device_uuid": device_uuid,
        "device_status": device_status,
        "device_title": str(device.attrib.get("title") or ""),
        "device_channels": device_channels,
        "dvr_key": dvr_key or None,
        "mapped": mapped,
        "expected": expected,
        "message": message,
    }


def repair_plex_tunarr_livetv(
    settings: Any = None,
    *,
    tunarr_url: Optional[str] = None,
    request_host: Optional[str] = None,
    friendly_name: str = "Projectionist",
    timeout: int = 120,
) -> Dict[str, Any]:
    """One-click: recreate Tunarr device + XMLTV DVR + full channel map."""
    return attach_tunarr_xmltv_to_plex(
        settings,
        tunarr_url=tunarr_url,
        request_host=request_host,
        friendly_name=friendly_name,
        timeout=timeout,
        force_recreate=True,
    )


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
