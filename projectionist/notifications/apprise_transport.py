"""Apprise notification transport (Discord, Telegram, push, …)."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence

from projectionist.config_store import AppriseSettings, Settings

logger = logging.getLogger(__name__)

_URL_SPLIT = re.compile(r"[\s,;]+")


class AppriseSendError(RuntimeError):
    """Raised when an Apprise notify attempt fails after configuration was present."""


@dataclass(frozen=True)
class AppriseSendResult:
    ok: bool
    notified: int = 0
    detail: str = ""


def split_apprise_urls(raw: str | None) -> List[str]:
    """Split a textarea / comma / newline blob into unique Apprise URL strings."""
    text = str(raw or "").strip()
    if not text:
        return []
    seen: set[str] = set()
    out: List[str] = []
    for line in text.replace(",", "\n").replace(";", "\n").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        for part in _URL_SPLIT.split(stripped):
            url = part.strip()
            if not url or url.startswith("#"):
                continue
            if url in seen:
                continue
            seen.add(url)
            out.append(url)
    return out


def apprise_available() -> bool:
    """True when the optional ``apprise`` package is importable."""
    try:
        import apprise  # noqa: F401
    except ImportError:
        return False
    return True


def apprise_install_configured(settings: Settings | AppriseSettings) -> bool:
    """Return True when install-level Apprise destinations are ready."""
    apprise_settings = (
        settings if isinstance(settings, AppriseSettings) else getattr(settings, "apprise", AppriseSettings())
    )
    if not apprise_settings.enabled:
        return False
    if split_apprise_urls(apprise_settings.urls):
        return True
    return bool(str(apprise_settings.config or "").strip())


def resolve_apprise_targets(
    settings: Settings,
    *,
    user_urls: str | None = None,
    include_install: bool = True,
) -> List[str]:
    """Collect Apprise URLs for a delivery (user self-serve + optional install)."""
    urls: List[str] = []
    urls.extend(split_apprise_urls(user_urls))
    if include_install and apprise_install_configured(settings):
        urls.extend(split_apprise_urls(settings.apprise.urls))
    # Preserve order, drop dupes
    seen: set[str] = set()
    unique: List[str] = []
    for url in urls:
        if url in seen:
            continue
        seen.add(url)
        unique.append(url)
    return unique


def _build_apprise(
    urls: Sequence[str],
    *,
    config_body: str | None = None,
):
    import apprise

    asset = apprise.AppriseAsset(app_id="Projectionist", app_desc="Projectionist")
    app = apprise.Apprise(asset=asset)
    for url in urls:
        if not app.add(url):
            logger.warning("Apprise rejected URL scheme (masked)")
    config_text = str(config_body or "").strip()
    if config_text:
        config = apprise.AppriseConfig()
        if not config.add_config(config_text):
            raise AppriseSendError("Could not parse install Apprise config.")
        app.add(config)
    return app


def send_apprise(
    settings: Settings | AppriseSettings | None = None,
    *,
    title: str,
    body: str,
    urls: Optional[Iterable[str]] = None,
    config_body: str | None = None,
    tag: str | None = None,
) -> AppriseSendResult:
    """Notify one or more Apprise URLs / config entries.

    Prefer passing explicit ``urls``. When ``settings`` is a full Settings object
    and urls are omitted, install-level URLs/config are used.
    """
    if not apprise_available():
        raise AppriseSendError(
            "Apprise is not installed. Reinstall with the web extras: pip install '.[web]'."
        )

    target_urls = list(urls) if urls is not None else []
    install_config = str(config_body or "").strip()
    notify_tag = (tag or "").strip() or None

    if settings is not None:
        if isinstance(settings, AppriseSettings):
            apprise_settings = settings
        else:
            apprise_settings = getattr(settings, "apprise", AppriseSettings())
        if urls is None:
            target_urls = split_apprise_urls(apprise_settings.urls)
        if not install_config:
            install_config = str(apprise_settings.config or "").strip()
        if notify_tag is None:
            notify_tag = str(apprise_settings.tag or "").strip() or None

    if not target_urls and not install_config:
        raise AppriseSendError("No Apprise URLs or config to notify.")

    try:
        app = _build_apprise(target_urls, config_body=install_config or None)
    except AppriseSendError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise AppriseSendError(f"Could not initialize Apprise: {exc}") from exc

    if not len(app):
        raise AppriseSendError("No valid Apprise destinations were loaded.")

    try:
        ok = app.notify(
            title=str(title or "Projectionist").strip() or "Projectionist",
            body=str(body or title or "").strip() or str(title or "Notification"),
            tag=notify_tag,
        )
    except Exception as exc:  # noqa: BLE001
        raise AppriseSendError(str(exc) or "Apprise notify failed") from exc

    if not ok:
        raise AppriseSendError("Apprise notify returned failure for all destinations.")

    return AppriseSendResult(ok=True, notified=len(app), detail="ok")
