"""HTML shell stamps Live from settings so the icon bar skips the session lookup."""

from types import SimpleNamespace

from projectionist.web.nav_bootstrap import (
    inject_nav_bootstrap,
    live_channels_nav_ready,
    nav_bootstrap_markup,
)


def test_live_nav_ready_requires_flag_and_tunarr_url():
    off = SimpleNamespace(
        features=SimpleNamespace(live_channels_enabled=False),
        tunarr=SimpleNamespace(url="http://tunarr:8000"),
    )
    missing = SimpleNamespace(
        features=SimpleNamespace(live_channels_enabled=True),
        tunarr=SimpleNamespace(url="  "),
    )
    on = SimpleNamespace(
        features=SimpleNamespace(live_channels_enabled=True),
        tunarr=SimpleNamespace(url="http://10.10.1.202:18765"),
    )
    assert live_channels_nav_ready(off) is False
    assert live_channels_nav_ready(missing) is False
    assert live_channels_nav_ready(on) is True


def test_bootstrap_markup_is_a_boolean_stamp():
    assert nav_bootstrap_markup(True) == (
        '<script>window.__PROJECTIONIST_NAV__={"liveChannelsReady":true}</script>'
    )
    html = inject_nav_bootstrap("<html><head><title>x</title></head><body></body></html>", ready=False)
    assert html.index("liveChannelsReady") < html.index("</head>")
    assert "false" in html
