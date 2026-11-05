"""Per-location cache, active-viewer tracking, and the background refresh loop.

- One shared cache per location (rounded coordinates).
- Forecast every 30 minutes, alerts every 5, maps every 10, archive/almanac once a
  day, headlines every 30. Regional cities and air quality ride the forecast timer.
- Only a location someone viewed in the last few minutes refreshes. A saved
  profile place nobody is watching costs nothing: no fetch, no LLM, no TTS.
- Scripts and audio are generated here, in the background, never on a request.
  A cold location gets template scripts until the variants are ready.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from projectionist.theater.weather_channel import scripts as script_writer
from projectionist.theater.weather_channel.http import Fetcher, WeatherFetchError
from projectionist.theater.weather_channel.images import ImageStore
from projectionist.theater.weather_channel.place import Place, short_place
from projectionist.theater.weather_channel.sources import almanac, alerts, forecast, headlines, maps, regional, seasonal, webcams
from projectionist.theater.weather_channel.tts import TtsRenderer, normalize_choice, script_hash

logger = logging.getLogger(__name__)

TTL_S = {
    "forecast": 30 * 60,
    "regional": 30 * 60,
    "air": 30 * 60,
    "alerts": 5 * 60,
    "maps": 10 * 60,
    "webcams": 10 * 60,
    "archive": 24 * 3600,
    "headlines": 30 * 60,
}
RETRY_S = 2 * 60
ACTIVE_VIEWER_S = 3 * 60
RENDERS_PER_TICK = 6


@dataclass
class NarrationSettings:
    enabled: bool = False
    engine: str = "kokoro"
    voice: str = ""
    rate: float = 1.0
    windy_api_key: str = ""


@dataclass
class LocationState:
    place: Place
    last_viewed: float = 0.0
    data: Dict[str, Any] = field(default_factory=dict)
    fetched_at: Dict[str, float] = field(default_factory=dict)
    attempted_at: Dict[str, float] = field(default_factory=dict)
    errors: Dict[str, str] = field(default_factory=dict)
    scripts: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    script_keys: Dict[str, str] = field(default_factory=dict)
    scripts_version: int = 0
    lock: threading.RLock = field(default_factory=threading.RLock)


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()[:16]


def segment_facts(state: LocationState, *, today: date, holidays: Sequence[Dict[str, Any]] = ()) -> Dict[str, Dict[str, Any]]:
    """The structured data each segment's script may use — and nothing else."""
    fc = state.data.get("forecast") or {}
    out: Dict[str, Dict[str, Any]] = {}
    if fc.get("current"):
        out["current"] = {"current": fc["current"]}
    if fc.get("daily"):
        out["overview"] = {"daily": fc["daily"][:2], "hourly": fc.get("hourly", [])[:12]}
    if len(fc.get("hourly") or []) >= 2:
        out["hourly"] = {"hourly": fc["hourly"], "hours": len(fc["hourly"])}
    if len(fc.get("daily") or []) >= 2:
        out["five_day"] = {"daily": fc["daily"], "days": len(fc["daily"])}
    if state.data.get("alerts"):
        out["alerts"] = {"alerts": state.data["alerts"]}
    if len(state.data.get("regional") or []) >= 3:
        out["regional"] = {"regional": state.data["regional"]}
    map_data = state.data.get("maps") or {}
    if (map_data.get("radar") or {}).get("frames"):
        out["radar"] = {"radar": True}
    if map_data.get("satellite"):
        out["satellite"] = {"satellite": True}
    if state.data.get("webcams"):
        out["webcams"] = {"webcams": [w.get("title") for w in state.data["webcams"]]}
    sun = almanac.sun_facts(fc) if fc else {}
    archive = state.data.get("archive") or {}
    if sun or archive.get("record_high"):
        out["almanac"] = {"sun": sun, "moon": almanac.moon_phase(), "archive": archive}
    seasonal_facts = dict(state.data.get("air") or {})
    seasonal_facts["next_season"] = almanac.next_season(today, southern=state.place.latitude < 0)
    if archive.get("frost"):
        seasonal_facts["frost"] = archive["frost"]
    if archive.get("first_snow_by"):
        seasonal_facts["first_snow_by"] = archive["first_snow_by"]
    ties = seasonal.holiday_ties(holidays, fc, archive, today=today) if fc else []
    if ties:
        seasonal_facts["holidays"] = ties
    if seasonal_facts.get("next_season") or len(seasonal_facts) > 1:
        out["seasonal"] = seasonal_facts
    return out


def headline_items(state: LocationState) -> List[Dict[str, Any]]:
    news = state.data.get("headlines") or {}
    return [item for scope in news.get("scopes") or [] for item in scope.get("items") or []]


class WeatherService:
    def __init__(
        self,
        data_dir: Path,
        *,
        fetch: Optional[Fetcher] = None,
        llm_factory: Callable[[], Optional[script_writer.LlmComplete]] = lambda: None,
        settings_factory: Callable[[], NarrationSettings] = NarrationSettings,
        holidays_factory: Callable[[], Sequence[Dict[str, Any]]] = lambda: (),
        tts: Optional[TtsRenderer] = None,
        clock: Callable[[], float] = time.time,
        today: Callable[[], date] = date.today,
        autostart: bool = True,
    ) -> None:
        self.data_dir = Path(data_dir)
        self.fetch = fetch
        self.llm_factory = llm_factory
        self.settings_factory = settings_factory
        self.holidays_factory = holidays_factory
        self.tts = tts or TtsRenderer(self.data_dir)
        self.images = ImageStore(self.data_dir)
        self.clock = clock
        self.today = today
        self.autostart = autostart
        self.states: Dict[str, LocationState] = {}
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # -- viewers ---------------------------------------------------------

    def view(self, place: Place) -> LocationState:
        """A viewer is on this place. Cold places fetch the forecast now; the rest follows in the background."""
        now = self.clock()
        with self._lock:
            state = self.states.get(place.key)
            if state is None or state.place != place:
                previous = state
                state = LocationState(place=place)
                if previous is not None and previous.place.key == place.key:
                    state.data, state.fetched_at = dict(previous.data), dict(previous.fetched_at)
                self.states[place.key] = state
            state.last_viewed = now
        if "forecast" not in state.fetched_at:
            self._refresh_source(state, "forecast", now)
        if not state.scripts:
            self._template_scripts(state)
        self._ensure_worker()
        self._wake.set()
        return state

    def active_states(self, now: Optional[float] = None) -> List[LocationState]:
        cutoff = (now if now is not None else self.clock()) - ACTIVE_VIEWER_S
        with self._lock:
            return [s for s in self.states.values() if s.last_viewed >= cutoff]

    # -- refresh ---------------------------------------------------------

    def _due(self, state: LocationState, source: str, now: float) -> bool:
        fetched = state.fetched_at.get(source)
        attempted = state.attempted_at.get(source, 0.0)
        if source in state.errors and now - attempted < RETRY_S:
            return False
        return fetched is None or now - fetched >= TTL_S[source]

    def _sources_for(self, state: LocationState, settings: NarrationSettings) -> List[str]:
        names = ["forecast", "alerts", "regional", "air", "maps", "archive", "headlines"]
        if not state.place.is_us:
            names.remove("alerts")
        if settings.windy_api_key:
            names.append("webcams")
        return names

    def _load(self, state: LocationState, source: str, settings: NarrationSettings) -> Any:
        lat, lon, fetch = state.place.latitude, state.place.longitude, self.fetch
        if source == "forecast":
            return forecast.fetch_forecast(lat, lon, fetch=fetch)
        if source == "alerts":
            return alerts.fetch_alerts(lat, lon, fetch=fetch)
        if source == "regional":
            return regional.fetch_regional(lat, lon, fetch=fetch)
        if source == "air":
            return seasonal.fetch_air(lat, lon, fetch=fetch)
        if source == "archive":
            return almanac.fetch_archive_facts(lat, lon, today=self.today(), fetch=fetch)
        if source == "headlines":
            return headlines.fetch_headlines(state.place, fetch=fetch)
        if source == "webcams":
            rows = webcams.fetch_webcams(lat, lon, api_key=settings.windy_api_key, fetch=fetch)
            return self._store_images(rows)
        if source == "maps":
            return self._load_maps(state)
        raise KeyError(source)

    def _store_images(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        out = []
        for row in rows:
            try:
                stored = self.images.put(row["source_url"], fetch=self.fetch, version=str(int(self.clock())))
            except WeatherFetchError:
                continue
            out.append({k: v for k, v in row.items() if k != "source_url"} | {"image_id": stored.image_id})
        return out

    def _load_maps(self, state: LocationState) -> Dict[str, Any]:
        lat, lon = state.place.latitude, state.place.longitude
        out: Dict[str, Any] = {}
        if state.place.is_us:
            frames = maps.us_radar_frames(lat, lon, now=datetime.fromtimestamp(self.clock(), tz=timezone.utc))
            radar = {"source": "Iowa Environmental Mesonet NEXRAD", "marker": {"x": 0.5, "y": 0.5}}
        else:
            got = maps.global_radar_frames(lat, lon, fetch=self.fetch)
            frames = got["frames"]
            radar = {"source": "RainViewer", "marker": got["marker"]}
        stored = []
        for frame in frames:
            try:
                image = self.images.put(frame["source_url"], fetch=self.fetch)
            except WeatherFetchError:
                continue
            stored.append({"image_id": image.image_id, "time": frame["time"]})
        if stored:
            out["radar"] = radar | {"frames": stored}
        sat = maps.satellite_source(lat, lon) if state.place.is_us else None
        if sat:
            try:
                image = self.images.put(sat["source_url"], fetch=self.fetch, version=str(int(self.clock())))
                out["satellite"] = {
                    "image_id": image.image_id,
                    "source": sat["label"],
                    "time": image.last_modified or datetime.fromtimestamp(image.fetched_at, tz=timezone.utc).isoformat(),
                }
            except WeatherFetchError:
                pass
        self.images.prune(now=self.clock())
        return out

    def _refresh_source(self, state: LocationState, source: str, now: float, settings: Optional[NarrationSettings] = None) -> bool:
        settings = settings or self.settings_factory()
        state.attempted_at[source] = now
        try:
            value = self._load(state, source, settings)
        except WeatherFetchError as exc:
            logger.info("weather %s fetch failed for %s: %s", source, state.place.key, exc)
            with state.lock:
                state.errors[source] = str(exc)[:200]
            return False
        with state.lock:
            changed = state.data.get(source) != value
            state.data[source] = value
            state.fetched_at[source] = now
            state.errors.pop(source, None)
        return changed

    def refresh(self, state: LocationState, now: Optional[float] = None) -> List[str]:
        now = self.clock() if now is None else now
        settings = self.settings_factory()
        changed = []
        for source in self._sources_for(state, settings):
            if self._due(state, source, now) and self._refresh_source(state, source, now, settings):
                changed.append(source)
        return changed

    # -- scripts ---------------------------------------------------------

    def _template_scripts(self, state: LocationState) -> None:
        facts = segment_facts(state, today=self.today(), holidays=self.holidays())
        place = short_place(state.place)
        scripts = script_writer.weather_scripts(facts, place, llm=None)
        if state.data.get("alerts"):
            scripts["alerts"] = script_writer.alert_scripts(state.data["alerts"], llm=None)
        with state.lock:
            state.scripts = scripts
            state.scripts_version += 1

    def holidays(self) -> Sequence[Dict[str, Any]]:
        try:
            return list(self.holidays_factory() or [])
        except Exception:  # noqa: BLE001 — holidays are a garnish
            return []

    def regenerate(self, state: LocationState) -> List[str]:
        """Rewrite whichever script groups have new input. Returns the groups rewritten."""
        facts = segment_facts(state, today=self.today(), holidays=self.holidays())
        weather_facts = {k: v for k, v in facts.items() if k != "alerts"}
        keys = {
            "weather": _hash(weather_facts),
            "alerts": alerts.alerts_fingerprint(state.data.get("alerts") or []),
            "headlines": _hash([(h.get("title"), h.get("source")) for h in headline_items(state)]),
        }
        stale = [group for group, key in keys.items() if state.script_keys.get(group) != key]
        if not stale:
            return []
        llm = self.llm_factory()
        place = short_place(state.place)
        updates: Dict[str, List[Dict[str, Any]]] = {}
        drop: List[str] = []
        if "weather" in stale:
            updates.update(script_writer.weather_scripts(weather_facts, place, llm=llm))
        if "alerts" in stale:
            rows = script_writer.alert_scripts(state.data.get("alerts") or [], llm=llm)
            if rows:
                updates["alerts"] = rows
            else:
                drop.append("alerts")
        if "headlines" in stale:
            rows = script_writer.recap_scripts(headline_items(state), llm=llm)
            if rows:
                updates["headlines"] = rows
            else:
                drop.append("headlines")
        with state.lock:
            scripts = dict(state.scripts)
            if "weather" in stale:
                scripts = {k: v for k, v in scripts.items() if k in {"alerts", "headlines"}}
            for key in drop:
                scripts.pop(key, None)
            scripts.update(updates)
            state.scripts = scripts
            state.script_keys.update({group: keys[group] for group in stale})
            state.scripts_version += 1
        return stale

    # -- audio -----------------------------------------------------------

    def voice_choice(self) -> Optional[tuple]:
        settings = self.settings_factory()
        if not settings.enabled:
            return None
        return normalize_choice(settings.engine, settings.voice, settings.rate)

    def audio_for(self, text: str) -> Optional[str]:
        choice = self.voice_choice()
        if choice is None:
            return None
        digest = script_hash(text, *choice)
        return digest if self.tts.audio_path(digest) else None

    def render_pending(self, state: LocationState, *, limit: int = RENDERS_PER_TICK) -> int:
        choice = self.voice_choice()
        if choice is None:
            return 0
        engine, voice, rate = choice
        if not self.tts.installed(engine, voice) and self.tts.engine_factory is None:
            return 0
        with state.lock:
            scripts = {k: list(v) for k, v in state.scripts.items()}
        queue: List[str] = []
        depth = max((len(v) for v in scripts.values()), default=0)
        for index in range(depth):
            for rows in scripts.values():
                if index < len(rows):
                    queue.append(rows[index]["text"])
        rendered = 0
        for text in queue:
            if rendered >= limit:
                break
            if self.tts.audio_path(script_hash(text, engine, voice, rate)):
                continue
            self.tts.render(text, engine=engine, voice=voice, rate=rate)
            rendered += 1
        return rendered

    # -- loop ------------------------------------------------------------

    def tick(self, now: Optional[float] = None) -> Dict[str, Any]:
        now = self.clock() if now is None else now
        report: Dict[str, Any] = {}
        for state in self.active_states(now):
            changed = self.refresh(state, now)
            rewritten = self.regenerate(state)
            rendered = self.render_pending(state)
            report[state.place.key] = {"changed": changed, "rewritten": rewritten, "rendered": rendered}
        return report

    def _ensure_worker(self) -> None:
        if not self.autostart or (self._thread and self._thread.is_alive()):
            return
        self._thread = threading.Thread(target=self._run, name="weather-channel", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        while True:
            self._wake.wait(timeout=10.0)
            self._wake.clear()
            try:
                report = self.tick()
            except Exception:  # noqa: BLE001 — keep the loop alive
                logger.exception("weather channel tick failed")
                continue
            if any(row.get("rendered") for row in report.values()):
                self._wake.set()
