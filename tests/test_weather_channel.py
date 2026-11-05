"""Weather Channel expansion: sources, scripts, checkers, TTS cache, refresh rules.

Every outbound call goes through a fake fetcher backed by tests/fixtures/weather.
"""

from __future__ import annotations

import json
import tempfile
import unittest
import urllib.parse
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

from projectionist.theater.weather_channel import scripts as sw
from projectionist.theater.weather_channel.http import FetchResult, WeatherFetchError, host_allowed
from projectionist.theater.weather_channel.payload import available_segments, build_payload, chyron_items
from projectionist.theater.weather_channel.place import place_from_label
from projectionist.theater.weather_channel.service import NarrationSettings, WeatherService, segment_facts
from projectionist.theater.weather_channel.sources import alerts as nws
from projectionist.theater.weather_channel.sources import almanac, forecast, headlines, maps, regional, seasonal
from projectionist.theater.weather_channel.tts import TtsRenderer, script_hash

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "weather"
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32
JPG = b"\xff\xd8\xff\xe0" + b"0" * 32
TODAY = date(2026, 11, 4)
NOW = 1793854800.0  # 2026-11-05T05:00Z (11 PM in Chicago on Nov 4)


def _fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


class FakeNet:
    """Routes fixture bodies by host. Records every URL. ``fail`` holds URL substrings that error."""

    def __init__(self, *, alerts: str = "nws_alerts_warning.json") -> None:
        self.calls: List[str] = []
        self.fail: set = set()
        self.alerts = alerts
        self.forecast_overrides: Dict[str, Any] = {}

    def __call__(self, url: str, *, headers: Optional[Dict[str, str]] = None, timeout: float = 10.0) -> FetchResult:
        self.calls.append(url)
        if not host_allowed(url):
            raise WeatherFetchError(f"unlisted host {url}")
        if any(part in url for part in self.fail):
            raise WeatherFetchError("simulated outage")
        parts = urllib.parse.urlsplit(url)
        query = urllib.parse.parse_qs(parts.query)
        host = parts.hostname
        if host == "api.open-meteo.com":
            lats = (query.get("latitude") or [""])[0].split(",")
            if len(lats) > 1:
                body = [{"current": {"temperature_2m": 40 + i, "weather_code": i % 4}} for i in range(len(lats))]
                return FetchResult(json.dumps(body).encode())
            data = json.loads(_fixture("forecast_chicago.json"))
            data["current"].update(self.forecast_overrides)
            return FetchResult(json.dumps(data).encode())
        if host == "api.weather.gov":
            return FetchResult(_fixture(self.alerts))
        if host == "archive-api.open-meteo.com":
            return FetchResult(_fixture("archive_chicago.json"))
        if host == "air-quality-api.open-meteo.com":
            return FetchResult(_fixture("air_chicago.json"))
        if host == "api.rainviewer.com":
            return FetchResult(_fixture("rainviewer.json"))
        if host in {"mesonet.agron.iastate.edu", "tilecache.rainviewer.com"}:
            return FetchResult(PNG)
        if host == "cdn.star.nesdis.noaa.gov":
            return FetchResult(JPG, {"last-modified": "Thu, 05 Nov 2026 04:50:00 GMT"})
        if host == "news.google.com":
            name = "rss_google_local.xml" if "/search" in parts.path else "rss_google_national.xml"
            return FetchResult(_fixture(name))
        if host == "feeds.bbci.co.uk":
            return FetchResult(_fixture("rss_bbc_world.xml"))
        raise WeatherFetchError(f"no fixture for {url}")

    def hosts(self) -> set:
        return {urllib.parse.urlsplit(u).hostname for u in self.calls}


CHICAGO = place_from_label("Chicago, Illinois, United States", 41.88, -87.63)
PARIS = place_from_label("Paris, Ile-de-France, France", 48.86, 2.35)


class FakeLLM:
    def __init__(self, reply: Any = None) -> None:
        self.calls: List[List[Dict[str, str]]] = []
        self.reply = reply
        self.counter = 0

    def __call__(self, messages: List[Dict[str, str]]) -> str:
        self.calls.append(messages)
        self.counter += 1
        system = messages[0]["content"]
        if callable(self.reply):
            return self.reply(system, json.loads(messages[1]["content"]), self.counter)
        if self.reply is not None:
            return self.reply
        return json.dumps({"segments": {}, "variants": []})

    def systems(self) -> List[str]:
        return [m[0]["content"] for m in self.calls]


def _service(tmp: str, net: FakeNet, **kwargs: Any) -> WeatherService:
    clock = kwargs.pop("clock", lambda: NOW)
    return WeatherService(Path(tmp), fetch=net, clock=clock, today=lambda: TODAY, autostart=False, **kwargs)


class ForecastAndAlertsTests(unittest.TestCase):
    def test_forecast_normalizes_current_hourly_and_five_days(self) -> None:
        fc = forecast.normalize_forecast(json.loads(_fixture("forecast_chicago.json")))
        current = fc["current"]
        self.assertEqual(current["temp"], 45)
        self.assertEqual(current["feels_like"], 39)
        self.assertEqual(current["wind_dir"], "SW")
        self.assertEqual(current["gusts"], 22)
        self.assertEqual(current["dew_point"], 36)
        self.assertEqual(current["visibility_mi"], 10.0)
        self.assertEqual(current["pressure_trend"], "falling")
        self.assertEqual(len(fc["hourly"]), 12)
        self.assertEqual(fc["hourly"][0]["label"], "12 AM")
        self.assertEqual([d["weekday"] for d in fc["daily"]], ["WED", "THU", "FRI", "SAT", "SUN"])
        self.assertEqual(fc["yesterday"]["date"], "2026-11-03")

    def test_nws_alert_parsing_puts_warning_first_and_skips_tests(self) -> None:
        rows = nws.parse_alerts(json.loads(_fixture("nws_alerts_warning.json")))
        self.assertEqual([r["event"] for r in rows], ["Severe Thunderstorm Warning", "Wind Advisory"])
        warning = rows[0]
        self.assertTrue(warning["is_warning"])
        self.assertEqual(warning["severity"], "Severe")
        self.assertEqual(warning["area_short"], "Cook")
        self.assertEqual(warning["ends_label"], "11:30 PM Wednesday")
        self.assertIn("interior room", warning["instruction"])
        self.assertFalse(rows[1]["is_warning"])

    def test_non_us_location_has_no_alerts_board_and_never_calls_nws(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            net = FakeNet()
            service = _service(tmp, net)
            state = service.view(PARIS)
            service.tick(NOW)
            self.assertNotIn("api.weather.gov", net.hosts())
            payload = build_payload(service, state, location_source="profile", household_place="", music=[], music_note="")
            self.assertFalse(payload["boards"]["alerts"]["supported"])
            self.assertNotIn("alerts", [s["id"] for s in payload["segments"]])
            self.assertNotIn("api.weather.gov", {e["host"] for e in payload["egress"]})

    def test_us_location_shows_bulletin_with_warning_first(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = _service(tmp, FakeNet())
            state = service.view(CHICAGO)
            service.tick(NOW)
            payload = build_payload(service, state, location_source="profile", household_place="", music=[], music_note="")
            items = payload["boards"]["alerts"]["items"]
            self.assertTrue(items[0]["is_warning"])
            self.assertIn("alerts", [s["id"] for s in payload["segments"]])
            spoken = payload["scripts"]["alerts"][0]["text"]
            self.assertTrue(spoken.startswith("This is a weather bulletin."))


class ScriptCheckerTests(unittest.TestCase):
    facts = {"current": {"temp": 45, "sky": "Partly cloudy", "wind": 11}, "daily": [{"weekday_name": "Thursday", "high": 57}]}

    def test_rejects_a_temperature_not_in_the_data(self) -> None:
        self.assertIsNone(sw.check_script("It's 45 degrees, wind at 11, Thursday high 57.", self.facts))
        self.assertIn("62", sw.check_script("It's 45 now and 62 tomorrow.", self.facts) or "")
        self.assertIsNotNone(sw.check_script("Expect a high of seventy-two.", self.facts))

    def test_rejects_a_day_not_in_the_data(self) -> None:
        self.assertIn("friday", sw.check_script("Friday looks dry at 45.", self.facts) or "")
        self.assertIsNone(sw.check_script("Thursday reaches 57.", self.facts))

    def test_dropped_llm_variant_is_replaced_by_the_template(self) -> None:
        facts = {"current": {"temp": 45, "sky": "Partly cloudy", "wind": 11, "wind_dir": "SW", "feels_like": 39, "humidity": 71}}
        rows = sw.merge_variants("current", ["A mild 45 under partly cloudy skies.", "A balmy 88 degrees!", "Wind at 11."], facts, "Chicago")
        self.assertEqual([r["source"] for r in rows], ["llm", "template", "llm"])
        self.assertNotIn("88", rows[1]["text"])

    def test_alert_script_keeps_event_area_end_time_and_action(self) -> None:
        alert = nws.parse_alerts(json.loads(_fixture("nws_alerts_warning.json")))[0]
        good = sw.alert_lead(alert) + " Storms bring damaging winds. Move to an interior room now."
        self.assertIsNone(sw.check_alert_script(good, alert))
        missing_end = good.replace("until 11:30 PM Wednesday", "")
        self.assertIn("end time", sw.check_alert_script(missing_end, alert) or "")
        softened = sw.alert_lead(alert) + " Nothing to worry about tonight."
        self.assertIn("what to do", sw.check_alert_script(softened, alert) or "")
        for row in sw.alert_template_variants(alert):
            self.assertIsNone(sw.check_alert_script(row, alert), row)

    def test_trivia_uses_only_archive_facts(self) -> None:
        archive = almanac.archive_facts(json.loads(_fixture("archive_chicago.json")), today=TODAY)
        self.assertEqual(archive["record_high"], {"value": 69, "year": 2025})
        self.assertEqual(archive["record_low"]["value"], 26)
        line = sw.trivia_line(archive, "Chicago")
        self.assertIn("69 degrees in 2025", line)
        facts = {"sun": {}, "moon": {}, "archive": archive}
        self.assertIsNone(sw.check_script(line, facts))
        self.assertIsNotNone(sw.check_script("The record high here is 81, set in 1931.", facts))
        self.assertIn("frost", archive)
        self.assertEqual(archive["first_snow_by"], "November 28")


class VariantRefreshTests(unittest.TestCase):
    @staticmethod
    def _reply(system: str, data: Dict[str, Any], counter: int) -> str:
        if "segments" in data:
            temp = data["segments"]["current"]["current"]["temp"]
            return json.dumps(
                {"segments": {"current": [f"A calm {temp} degrees now.", f"Still {temp} out there.", f"It is {temp}."]}}
            )
        if "event" in data:
            lead_free = "Move to shelter and stay away from windows."
            return json.dumps({"variants": [lead_free, lead_free, lead_free]})
        return json.dumps({"variants": []})

    def test_variants_are_rewritten_on_refresh_and_alert_change_touches_only_alerts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            net = FakeNet(alerts="nws_alerts_advisory.json")
            llm = FakeLLM(self._reply)
            clock = {"now": NOW}
            service = _service(tmp, net, llm_factory=lambda: llm, clock=lambda: clock["now"])
            state = service.view(CHICAGO)
            service.tick(clock["now"])
            first_current = [r["text"] for r in state.scripts["current"]]
            first_alerts = [r["text"] for r in state.scripts["alerts"]]
            self.assertTrue(all(r["source"] == "llm" for r in state.scripts["current"]))
            self.assertEqual(len(first_current), 3)

            # Five minutes later only the alert feed is due; a new Warning arrives.
            net.alerts = "nws_alerts_warning.json"
            clock["now"] += 5 * 60
            service.view(CHICAGO)
            llm.calls.clear()
            report = service.tick(clock["now"])
            self.assertEqual(report[CHICAGO.key]["rewritten"], ["alerts"])
            self.assertEqual([r["text"] for r in state.scripts["current"]], first_current)
            self.assertNotEqual([r["text"] for r in state.scripts["alerts"]], first_alerts)
            self.assertTrue(all("weather bulletin" in s.lower() or "explain" in s.lower() for s in llm.systems()))
            self.assertEqual(len(llm.calls), 1)

            # Thirty minutes later the forecast refreshes with new data: weather variants are rewritten.
            net.forecast_overrides = {"temperature_2m": 41.0}
            clock["now"] += 30 * 60
            service.view(CHICAGO)
            report = service.tick(clock["now"])
            self.assertIn("weather", report[CHICAGO.key]["rewritten"])
            self.assertNotEqual([r["text"] for r in state.scripts["current"]], first_current)
            self.assertIn("41", state.scripts["current"][0]["text"])

    def test_no_llm_means_template_variants(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = _service(tmp, FakeNet())
            state = service.view(CHICAGO)
            service.tick(NOW)
            for segment in ("current", "overview", "hourly", "five_day", "almanac", "regional"):
                rows = state.scripts.get(segment) or []
                self.assertGreaterEqual(len(rows), 2, segment)
                self.assertTrue(all(r["source"] == "template" for r in rows), segment)
            facts = segment_facts(state, today=TODAY)
            for segment, rows in state.scripts.items():
                if segment in facts and segment != "alerts":
                    for row in rows:
                        self.assertIsNone(sw.check_script(row["text"], facts[segment]), (segment, row["text"]))


class TtsTests(unittest.TestCase):
    class _Engine:
        def __init__(self, log: List[str], fail: bool = False) -> None:
            self.log, self.fail = log, fail

        def synthesize(self, text: str, wav_path: Path) -> None:
            if self.fail:
                raise RuntimeError("model crashed")
            self.log.append(text)
            wav_path.write_bytes(b"RIFF")

    @staticmethod
    def _encode(wav: Path, out: Path) -> None:
        out.write_bytes(b"OggS" + wav.read_bytes())

    def test_render_is_cached_by_script_hash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log: List[str] = []
            tts = TtsRenderer(Path(tmp), engine_factory=lambda *a: self._Engine(log), encoder=self._encode)
            first = tts.render("Forty-five and breezy.", engine="kokoro", voice="af_heart", rate=1.0)
            second = tts.render("Forty-five  and breezy.", engine="kokoro", voice="af_heart", rate=1.0)
            self.assertEqual(first, second)
            self.assertEqual(first, script_hash("Forty-five and breezy.", "kokoro", "af_heart", 1.0))
            self.assertEqual(log, ["Forty-five and breezy."])
            path = tts.audio_path(first)
            self.assertEqual(path, Path(tmp) / "weather" / "audio" / f"{first}.opus")
            other = tts.render("Forty-five and breezy.", engine="kokoro", voice="am_michael", rate=1.0)
            self.assertNotEqual(first, other)
            self.assertIsNone(tts.audio_path("../../etc/passwd"))

    def test_tts_failure_leaves_captions_with_no_audio(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tts = TtsRenderer(Path(tmp), engine_factory=lambda *a: self._Engine([], fail=True), encoder=self._encode)
            service = _service(tmp, FakeNet(), tts=tts, settings_factory=lambda: NarrationSettings(enabled=True))
            state = service.view(CHICAGO)
            service.tick(NOW)
            payload = build_payload(service, state, location_source="profile", household_place="", music=[], music_note="")
            current = payload["scripts"]["current"]
            self.assertTrue(current[0]["text"])
            self.assertTrue(all(row["audio_url"] is None for row in current))
            self.assertGreater(tts.failures, 0)
            self.assertFalse(list((Path(tmp) / "weather" / "audio").glob("*.part")))

    def test_rendered_audio_reaches_the_payload_when_narration_is_on(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tts = TtsRenderer(Path(tmp), engine_factory=lambda *a: self._Engine([]), encoder=self._encode)
            service = _service(tmp, FakeNet(), tts=tts, settings_factory=lambda: NarrationSettings(enabled=True))
            state = service.view(CHICAGO)
            for _ in range(12):
                service.tick(NOW)
            payload = build_payload(service, state, location_source="profile", household_place="", music=[], music_note="")
            url = payload["scripts"]["current"][0]["audio_url"]
            self.assertRegex(url, r"^/api/live/weather/audio/[0-9a-f]{32}\.opus$")

    def test_narration_off_renders_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log: List[str] = []
            tts = TtsRenderer(Path(tmp), engine_factory=lambda *a: self._Engine(log), encoder=self._encode)
            service = _service(tmp, FakeNet(), tts=tts)
            service.view(CHICAGO)
            service.tick(NOW)
            self.assertEqual(log, [])

    def test_voice_download_only_when_asked_and_reports_size(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fetched: List[str] = []

            def downloader(url: str, dest: Path, progress) -> None:
                fetched.append(url)
                dest.write_bytes(b"model")
                progress(5)

            tts = TtsRenderer(Path(tmp), downloader=downloader)
            status = tts.status("kokoro", "af_heart", 1.0, False)
            self.assertFalse(status["installed"])
            self.assertGreater(status["download_bytes"], 50_000_000)
            self.assertEqual(fetched, [])
            tts.start_download("kokoro", "af_heart", background=False)
            self.assertTrue(tts.installed("kokoro", "af_heart"))
            self.assertTrue(all(u.startswith("https://github.com/") for u in fetched))
            self.assertTrue((Path(tmp) / "weather" / "tts" / "kokoro" / "voices-v1.0.bin").is_file())


class RefreshRulesTests(unittest.TestCase):
    def test_no_outbound_call_when_nobody_is_watching(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            net = FakeNet()
            llm = FakeLLM()
            service = _service(tmp, net, llm_factory=lambda: llm)
            service.tick(NOW)
            self.assertEqual(net.calls, [])
            self.assertEqual(llm.calls, [])

    def test_only_active_viewer_locations_refresh(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            net = FakeNet()
            clock = {"now": NOW}
            service = _service(tmp, net, clock=lambda: clock["now"])
            service.view(PARIS)
            clock["now"] += 10 * 60  # Paris viewer left ten minutes ago.
            service.view(CHICAGO)
            clock["now"] += 31 * 60
            service.view(CHICAGO)  # still watching Chicago; Paris has been gone 41 minutes
            net.calls.clear()
            service.tick(clock["now"])
            lats = {urllib.parse.parse_qs(urllib.parse.urlsplit(u).query).get("latitude", [""])[0] for u in net.calls}
            self.assertTrue(any(lat.startswith("41.8") for lat in lats))
            self.assertFalse(any(lat.startswith("48.8") for lat in lats))

    def test_timers_follow_the_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            net = FakeNet()
            clock = {"now": NOW}
            service = _service(tmp, net, clock=lambda: clock["now"])
            service.view(CHICAGO)
            service.tick(clock["now"])
            for minutes, expected in ((5, {"api.weather.gov"}), (10, {"api.weather.gov", "mesonet.agron.iastate.edu", "cdn.star.nesdis.noaa.gov"})):
                net.calls.clear()
                clock["now"] = NOW + minutes * 60
                service.view(CHICAGO)
                service.tick(clock["now"])
                self.assertEqual(net.hosts(), expected, minutes)
            net.calls.clear()
            clock["now"] = NOW + 30 * 60
            service.view(CHICAGO)
            service.tick(clock["now"])
            self.assertIn("api.open-meteo.com", net.hosts())
            self.assertIn("news.google.com", net.hosts())
            self.assertNotIn("archive-api.open-meteo.com", net.hosts())

    def test_cold_viewer_gets_template_scripts_before_any_llm(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            llm = FakeLLM()
            service = _service(tmp, FakeNet(), llm_factory=lambda: llm)
            state = service.view(CHICAGO)
            self.assertEqual(llm.calls, [])
            self.assertTrue(state.scripts["current"])
            self.assertEqual(state.scripts["current"][0]["source"], "template")


class BoardsAndChyronTests(unittest.TestCase):
    def test_empty_boards_are_skipped(self) -> None:
        boards = {"current": None, "overview": None, "hourly": [], "five_day": [{"x": 1}, {"x": 2}], "alerts": {"supported": True, "items": []},
                  "regional": [{"n": 1}], "radar": None, "satellite": None, "webcams": [], "almanac": None, "seasonal": None}
        self.assertEqual(available_segments(boards, False), ["five_day"])

    def test_chyron_is_weather_only_and_renders_while_headlines_pending_or_failed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            net = FakeNet()
            net.fail = {"news.google.com", "feeds.bbci.co.uk"}
            service = _service(tmp, net)
            state = service.view(CHICAGO)
            pending = build_payload(service, state, location_source="profile", household_place="", music=[], music_note="")
            self.assertEqual(pending["headlines"]["status"], "pending")
            groups = [item["group"] for item in pending["chyron"]]
            self.assertEqual(groups[0], "NOW")
            self.assertIn("HOURLY", groups)
            self.assertIn("5-DAY", groups)
            service.tick(NOW)
            failed = build_payload(service, state, location_source="profile", household_place="", music=[], music_note="")
            self.assertEqual(failed["headlines"]["status"], "failed")
            self.assertEqual(failed["chyron"], chyron_items(state))
            self.assertEqual({i["group"] for i in failed["chyron"]}, {"NOW", "HOURLY", "5-DAY"})
            self.assertNotIn("headlines", [s["id"] for s in failed["segments"]])
            self.assertTrue(failed["boards"]["current"])
            self.assertIn("NOW:", failed["chyron_summary"])

    def test_payload_lists_maps_regional_almanac_seasonal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = _service(tmp, FakeNet())
            state = service.view(CHICAGO)
            service.tick(NOW)
            payload = build_payload(service, state, location_source="profile", household_place="", music=[], music_note="")
            ids = [s["id"] for s in payload["segments"]]
            for expected in ("current", "overview", "hourly", "five_day", "alerts", "regional", "radar", "satellite", "almanac", "seasonal", "headlines"):
                self.assertIn(expected, ids)
            self.assertNotIn("webcams", ids)
            self.assertEqual(payload["local_on_the_8s"], ["current", "overview", "hourly"])
            radar = payload["boards"]["radar"]
            self.assertEqual(len(radar["frames"]), maps.RADAR_FRAMES)
            self.assertTrue(radar["frames"][0]["url"].startswith("/api/live/weather/image/"))
            self.assertIn("Mesonet", radar["source"])
            self.assertIn("GOES", payload["boards"]["satellite"]["source"])
            self.assertEqual(payload["boards"]["almanac"]["sunrise"], "6:21 AM")
            self.assertEqual(payload["boards"]["almanac"]["day_length_change_s"], -120)
            self.assertEqual(payload["boards"]["seasonal"]["aqi"], 42)
            self.assertGreaterEqual(len(payload["boards"]["regional"]), 6)
            self.assertNotIn("Chicago", [c["name"] for c in payload["boards"]["regional"]])

    def test_webcams_only_with_a_windy_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            net = FakeNet()
            service = _service(tmp, net)
            service.view(CHICAGO)
            service.tick(NOW)
            self.assertNotIn("api.windy.com", net.hosts())

    def test_global_radar_uses_rainviewer_tiles(self) -> None:
        got = maps.global_radar_frames(48.86, 2.35, fetch=FakeNet())
        self.assertEqual(len(got["frames"]), maps.RADAR_FRAMES)
        self.assertTrue(got["frames"][0]["source_url"].startswith("https://tilecache.rainviewer.com/v2/radar/"))
        self.assertTrue(0 <= got["marker"]["x"] <= 1)

    def test_seasonal_holiday_ties_use_forecast_days(self) -> None:
        fc = forecast.normalize_forecast(json.loads(_fixture("forecast_chicago.json")))
        ties = seasonal.holiday_ties([{"name": "Movie Marathon", "grounding_date": "2026-11-06"}], fc, {}, today=TODAY)
        self.assertEqual(ties[0]["kind"], "forecast")
        self.assertEqual(ties[0]["low"], 35)
        self.assertEqual(almanac.next_season(TODAY)["name"], "winter solstice")
        self.assertEqual(almanac.next_season(TODAY, southern=True)["name"], "summer solstice")

    def test_regional_picks_nearby_cities(self) -> None:
        cities = regional.nearby_cities(41.88, -87.63)
        names = [c["name"] for c in cities]
        self.assertIn("Milwaukee", names)
        self.assertNotIn("Chicago", names)
        self.assertLessEqual(len(names), regional.MAX_CITIES)


class HeadlineTests(unittest.TestCase):
    def test_city_with_country_gets_local_national_and_world(self) -> None:
        got = headlines.fetch_headlines(CHICAGO, fetch=FakeNet())
        self.assertEqual([s["scope"] for s in got["scopes"]], ["local", "national", "world"])
        local = got["scopes"][0]["items"][0]
        self.assertEqual(local["title"], "Chicago Transit Authority adds late-night Blue Line service")
        self.assertEqual(local["source"], "Chicago Tribune")
        self.assertEqual(got["scopes"][2]["items"][0]["source"], "BBC News")

    def test_feed_urls_send_city_or_country_and_bbc_gets_nothing(self) -> None:
        feeds = {f["scope"]: f["url"] for f in headlines.headline_feeds(CHICAGO)}
        self.assertIn("q=Chicago+Illinois", feeds["local"])
        self.assertIn("gl=US", feeds["national"])
        self.assertEqual(feeds["world"], headlines.BBC_WORLD_URL)

    def test_missing_country_is_world_only(self) -> None:
        place = place_from_label("your area", 41.88, -87.63)
        self.assertEqual([f["scope"] for f in headlines.headline_feeds(place)], ["world"])

    def test_failed_local_feed_still_shows_the_other_two(self) -> None:
        net = FakeNet()
        net.fail = {"/rss/search"}
        got = headlines.fetch_headlines(CHICAGO, fetch=net)
        self.assertEqual([s["scope"] for s in got["scopes"]], ["national", "world"])
        self.assertEqual(got["failed"], ["local"])

    def test_rss_with_entity_declarations_is_refused(self) -> None:
        with self.assertRaises(WeatherFetchError):
            headlines.parse_rss(b'<?xml version="1.0"?><!DOCTYPE r [<!ENTITY a "x">]><rss><channel></channel></rss>')

    def test_recap_naming_a_story_not_in_the_list_is_dropped_and_titles_still_show(self) -> None:
        def reply(system: str, data: Dict[str, Any], counter: int) -> str:
            if "headlines" in data:
                return json.dumps(
                    {
                        "variants": [
                            "In Chicago, the Blue Line adds late-night service. The Senate passes a highway funding bill.",
                            "The Pope visits Chicago this weekend, and the Senate passes a highway bill.",
                            "Elsewhere, a volcano erupts in Iceland and the Federal Reserve holds rates steady.",
                        ]
                    }
                )
            return json.dumps({"segments": {}, "variants": []})

        with tempfile.TemporaryDirectory() as tmp:
            service = _service(tmp, FakeNet(), llm_factory=lambda: FakeLLM(reply))
            state = service.view(CHICAGO)
            service.tick(NOW)
            recap = [r["text"] for r in state.scripts["headlines"]]
            self.assertEqual(len(recap), 2)
            self.assertFalse(any("Pope" in r for r in recap))
            payload = build_payload(service, state, location_source="profile", household_place="", music=[], music_note="")
            self.assertEqual(payload["headlines"]["status"], "ready")
            self.assertIn("headlines", [s["id"] for s in payload["segments"]])

    def test_every_recap_dropped_means_titles_with_no_spoken_recap(self) -> None:
        reply = json.dumps({"variants": ["Mayor Johnson unveils a new plan."], "segments": {}})
        with tempfile.TemporaryDirectory() as tmp:
            service = _service(tmp, FakeNet(), llm_factory=lambda: FakeLLM(reply))
            state = service.view(CHICAGO)
            service.tick(NOW)
            payload = build_payload(service, state, location_source="profile", household_place="", music=[], music_note="")
            self.assertEqual(payload["scripts"]["headlines"], [])
            self.assertTrue(payload["headlines"]["scopes"])

    def test_recap_llm_sees_titles_and_sources_only(self) -> None:
        llm = FakeLLM(json.dumps({"variants": [], "segments": {}}))
        with tempfile.TemporaryDirectory() as tmp:
            service = _service(tmp, FakeNet(), llm_factory=lambda: llm)
            service.view(CHICAGO)
            service.tick(NOW)
        recap_calls = [json.loads(m[1]["content"]) for m in llm.calls if "headline recap" in m[0]["content"]]
        self.assertEqual(len(recap_calls), 1)
        self.assertEqual(set(recap_calls[0]), {"headlines"})
        for item in recap_calls[0]["headlines"]:
            self.assertEqual(set(item), {"title", "source"})
        weather_calls = [json.loads(m[1]["content"]) for m in llm.calls if "cable weather channel" in m[0]["content"]]
        blob = json.dumps(weather_calls)
        self.assertNotIn("41.88", blob)
        self.assertNotIn("-87.63", blob)

    def test_no_llm_means_no_spoken_recap(self) -> None:
        self.assertEqual(sw.recap_scripts([{"title": "Senate passes bill", "source": "AP"}], llm=None), [])


class HostAllowlistTests(unittest.TestCase):
    def test_only_listed_https_hosts(self) -> None:
        self.assertTrue(host_allowed("https://api.weather.gov/alerts/active?point=1,2"))
        self.assertFalse(host_allowed("http://api.weather.gov/alerts"))
        self.assertFalse(host_allowed("https://169.254.169.254/latest"))
        self.assertFalse(host_allowed("https://evil.example/radar.png"))

    def test_image_store_refuses_unlisted_hosts(self) -> None:
        from projectionist.theater.weather_channel.images import ImageStore

        with tempfile.TemporaryDirectory() as tmp:
            store = ImageStore(Path(tmp))
            with self.assertRaises(WeatherFetchError):
                store.put("https://evil.example/cam.jpg", fetch=FakeNet())
            stored = store.put("https://cdn.star.nesdis.noaa.gov/GOES19/ABI/SECTOR/umv/GEOCOLOR/600x600.jpg", fetch=FakeNet())
            self.assertEqual(stored.content_type, "image/jpeg")
            self.assertTrue(stored.last_modified.startswith("2026-11-05T04:50"))


class WeatherRoutesTests(unittest.TestCase):
    """Admin narration settings are owner-only; audio and image routes serve only what was rendered."""

    def setUp(self) -> None:
        import importlib
        import os

        from projectionist.web.auth import _hash_password, clear_pin_bindings
        from projectionist.web.rate_limit import clear_rate_limits
        from projectionist.web.session_tokens import clear_session_secret_cache

        self._tmp = tempfile.TemporaryDirectory()
        self._env = {
            "DATA_DIR": self._tmp.name,
            "PROJECTIONIST_SKIP_DOTENV": "1",
            "LLM_PROVIDER": "ollama",
            "PROJECTIONIST_SESSION_SECRET": "test-weather-session-secret-value",
            "PROJECTIONIST_SETUP_STATE": "active",
        }
        os.environ.update(self._env)
        clear_session_secret_cache()
        clear_rate_limits()
        clear_pin_bindings()
        Path(self._tmp.name, "settings.json").write_text(
            json.dumps(
                {
                    "features": {"multi_user_enabled": True},
                    "auth": {"mode": "local", "plex_login_enabled": False, "local_login_enabled": True},
                    "llm_provider": "ollama",
                }
            ),
            encoding="utf-8",
        )
        import projectionist.web.jobs as jobs
        from fastapi.testclient import TestClient

        jobs._manager = None
        import projectionist.web.app as app_mod

        importlib.reload(app_mod)
        self.client = TestClient(app_mod.app)
        db = jobs.get_job_manager().db
        for name, role in (("owner", "owner"), ("alice", "member")):
            db.create_local_user(user_id=f"local-{name}", display_name=name, password_hash=_hash_password("password123"), role=role)

    def tearDown(self) -> None:
        import os

        import projectionist.web.jobs as jobs
        from projectionist.web.rate_limit import clear_rate_limits
        from projectionist.web.session_tokens import clear_session_secret_cache

        jobs._manager = None
        clear_session_secret_cache()
        clear_rate_limits()
        for key in self._env:
            os.environ.pop(key, None)
        self._tmp.cleanup()

    def _login(self, name: str) -> None:
        self.client.cookies.clear()
        resp = self.client.post("/api/auth/local/login", json={"username": name, "password": "password123"})
        self.assertEqual(resp.status_code, 200, resp.text)

    def test_narration_admin_is_owner_only_and_key_is_masked(self) -> None:
        self._login("alice")
        self.assertEqual(self.client.get("/api/admin/live/weather").status_code, 403)
        self.assertEqual(self.client.put("/api/admin/live/weather", json={"tts_engine": "piper"}).status_code, 403)
        self._login("owner")
        status = self.client.get("/api/admin/live/weather").json()
        self.assertFalse(status["narration"]["enabled"])
        self.assertFalse(status["narration"]["installed"])
        self.assertGreater(status["narration"]["download_bytes"], 0)
        self.assertIn("US places only", status["alerts_note"])
        saved = self.client.put(
            "/api/admin/live/weather",
            json={"tts_engine": "piper", "tts_voice": "en_GB-alan-medium", "tts_rate": 1.1, "windy_api_key": "windy-secret-123"},
        )
        self.assertEqual(saved.status_code, 200, saved.text)
        body = saved.json()
        self.assertEqual(body["narration"]["engine"], "piper")
        self.assertEqual(body["narration"]["voice"], "en_GB-alan-medium")
        self.assertTrue(body["windy_api_key_set"])
        self.assertNotIn("windy-secret-123", saved.text)
        self.assertFalse(body["narration"]["downloading"])
        on_disk = Path(self._tmp.name, "settings.json").read_text(encoding="utf-8")
        self.assertNotIn("windy-secret-123", on_disk)
        settings = self.client.get("/api/settings")
        if settings.status_code == 200:
            self.assertNotIn("windy-secret-123", settings.text)

    def test_audio_and_image_routes_only_serve_rendered_files(self) -> None:
        self._login("alice")
        self.assertEqual(self.client.get("/api/live/weather/audio/" + "a" * 32 + ".opus").status_code, 404)
        self.assertEqual(self.client.get("/api/live/weather/audio/..%2F..%2Fsettings.json").status_code, 404)
        self.assertEqual(self.client.get("/api/live/weather/image/" + "b" * 32).status_code, 404)
        self.client.cookies.clear()
        self.assertIn(self.client.get("/api/live/weather/audio/" + "a" * 32 + ".opus").status_code, {401, 403})


if __name__ == "__main__":
    unittest.main()
