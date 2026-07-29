"""Plain-language Plex Live TV attach helpers (HDHR + XMLTV URLs)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from urllib.parse import urlparse


def normalize_tunarr_base(url: str) -> str:
    cleaned = str(url or "").strip().rstrip("/")
    return cleaned


def hdhr_url(tunarr_base: str) -> str:
    """Tuner discovery URL Plex accepts for Tunarr's HDHomeRun emulator."""
    base = normalize_tunarr_base(tunarr_base)
    if not base:
        return ""
    return f"{base}/"
    # Tunarr serves HDHR device XML at root; Plex "HDHomeRun" tuner uses the base host.


def xmltv_url(tunarr_base: str) -> str:
    base = normalize_tunarr_base(tunarr_base)
    if not base:
        return ""
    return f"{base}/api/xmltv.xml"


def build_plex_attach(
    settings: Any = None,
    *,
    tunarr_url: Optional[str] = None,
    discovery_ok: Optional[bool] = None,
) -> Dict[str, Any]:
    """Checklist + copy URLs for adding Tunarr to Plex Live TV / DVR."""
    tunarr = getattr(settings, "tunarr", None) if settings is not None else None
    url = str(tunarr_url or (getattr(tunarr, "url", "") if tunarr else "") or "").strip()
    hdhr = hdhr_url(url)
    xmltv = xmltv_url(url)
    host = ""
    if url:
        parsed = urlparse(url if "://" in url else f"http://{url}")
        host = parsed.hostname or ""

    steps: List[Dict[str, str]] = [
        {
            "title": "Open Plex Live TV & DVR settings",
            "body": (
                "In Plex, go to Settings → Live TV & DVR (Plex Pass). "
                "You need an active Plex Pass for this step."
            ),
        },
        {
            "title": "Add a network tuner",
            "body": (
                "Choose to add a tuner / HDHomeRun device. When Plex asks for a "
                "device address, paste the tuner URL below (or the host if your "
                "Plex build only wants an IP)."
            ),
        },
        {
            "title": "Point the guide at the XMLTV feed",
            "body": (
                "When Plex asks for an EPG / guide source, paste the guide URL. "
                "You do not need to open Tunarr’s admin UI."
            ),
        },
        {
            "title": "Finish setup in Plex",
            "body": (
                "Let Plex scan channels, then watch from Plex Live TV. "
                "Projectionist will not play channels in-app."
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
