"""Plain-language Plex Live TV attach helpers (HDHR + XMLTV URLs).

Tunarr is added as an *additional* network tuner alongside any existing OTA /
HDHomeRun / DVR setup. Projectionist never instructs owners to remove or replace
existing Live TV hardware.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

# Starter channels publish from 100+ (see starter_pack._BASE_CHANNEL_NUMBER).
_VIRTUAL_CHANNEL_FLOOR = 100


def normalize_tunarr_base(url: str) -> str:
    cleaned = str(url or "").strip().rstrip("/")
    return cleaned


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
    discovery_ok: Optional[bool] = None,
    existing_livetv: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Checklist + copy URLs for adding Tunarr *alongside* existing Plex Live TV."""
    tunarr = getattr(settings, "tunarr", None) if settings is not None else None
    url = str(tunarr_url or (getattr(tunarr, "url", "") if tunarr else "") or "").strip()
    hdhr = hdhr_url(url)
    xmltv = xmltv_url(url)
    host = ""
    if url:
        parsed = urlparse(url if "://" in url else f"http://{url}")
        host = parsed.hostname or ""

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

    return {
        "tunarr_url": url,
        "tuner_url": hdhr,
        "guide_url": xmltv,
        "hdhr_url": hdhr,
        "xmltv_url": xmltv,
        "host_hint": host,
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
