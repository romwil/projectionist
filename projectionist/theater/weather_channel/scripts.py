"""Voiceover scripts: LLM variants from raw data, checkers, and template variants.

The LLM gets the structured weather data and the place name, nothing about a
member. Every script it writes is checked against that data. A script that names
a number, day, or month the data does not hold is dropped and the template for
that slot is used. Headline recaps get the fetched titles and sources only, and a
recap that names a story not in that list is dropped (no spoken recap then).
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence

logger = logging.getLogger(__name__)

LlmComplete = Callable[[List[Mapping[str, str]]], str]

VARIANTS = 3
LLM_SEGMENTS = ("current", "overview", "hourly", "five_day", "regional", "almanac", "seasonal")
WEATHER_SEGMENTS = (
    "current", "overview", "hourly", "five_day", "alerts", "regional",
    "radar", "satellite", "webcams", "almanac", "seasonal",
)

_WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
_MONTHS = (
    "january", "february", "march", "april", "may", "june", "july",
    "august", "september", "october", "november", "december",
)
_UNITS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
    "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
}
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}
# Small spoken counts ("one or two showers") are not data claims.
_FREE_NUMBER_WORDS = {0, 1, 2, 3}
_ACTION_WORDS = (
    "stay", "move", "avoid", "take", "seek", "keep", "prepare", "do not", "don't", "check",
    "slow", "use", "allow", "limit", "monitor", "have", "go ", "get ", "bring", "secure", "turn around",
    "follow", "listen", "dress", "cover", "drink",
)


# --------------------------------------------------------------------------- facts


def _walk(value: Any) -> Iterable[Any]:
    if isinstance(value, Mapping):
        for item in value.values():
            yield from _walk(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _walk(item)
    else:
        yield value


def allowed_values(facts: Any) -> Dict[str, set]:
    ints: set = set()
    decimals: set = set()
    words: set = set()
    for value in _walk(facts):
        if isinstance(value, bool) or value is None:
            continue
        if isinstance(value, (int, float)):
            ints.add(int(round(value)))
            ints.add(int(value))
            ints.add(abs(int(round(value))))
            if isinstance(value, float):
                decimals.add(f"{value:.1f}")
                decimals.add(f"{value:.2f}")
                decimals.add(f"{value:g}")
            continue
        text = str(value)
        for token in re.findall(r"\d+(?:\.\d+)?", text):
            if "." in token:
                decimals.add(token)
                ints.add(int(round(float(token))))
            else:
                ints.add(int(token))
        words.update(w.lower() for w in re.findall(r"[A-Za-z]+", text))
    return {"ints": ints, "decimals": decimals, "words": words}


def _number_words(text: str) -> List[int]:
    out: List[int] = []
    tokens = re.findall(r"[a-z]+(?:-[a-z]+)?", text.lower())
    for token in tokens:
        parts = token.split("-")
        if len(parts) == 2 and parts[0] in _TENS and parts[1] in _UNITS and _UNITS[parts[1]] < 10:
            out.append(_TENS[parts[0]] + _UNITS[parts[1]])
        elif token in _TENS:
            out.append(_TENS[token])
        elif token in _UNITS:
            out.append(_UNITS[token])
        elif token == "hundred":
            out.append(100)
    return out


def check_script(text: str, facts: Any) -> Optional[str]:
    """Return why a script fails the data, or None when every value is in the data."""
    body = " ".join(str(text or "").split())
    if not body:
        return "empty"
    if len(body) > 900:
        return "too long"
    allowed = allowed_values(facts)
    for token in re.findall(r"(?<![\w.])\d+(?:\.\d+)?", body):
        if "." in token:
            if token not in allowed["decimals"] and token.rstrip("0").rstrip(".") not in allowed["decimals"]:
                return f"value {token} is not in the data"
        elif int(token) not in allowed["ints"]:
            return f"value {token} is not in the data"
    for value in _number_words(body):
        if value not in _FREE_NUMBER_WORDS and value not in allowed["ints"]:
            return f"value {value} is not in the data"
    lowered = re.findall(r"[a-z]+", body.lower())
    for word in lowered:
        if word in _WEEKDAYS and word not in allowed["words"]:
            return f"day {word} is not in the data"
        if word in _MONTHS and word != "may" and word not in allowed["words"]:
            return f"month {word} is not in the data"
    return None


def check_alert_script(text: str, alert: Mapping[str, Any]) -> Optional[str]:
    """An alert script keeps event, severity, area, until-when, and what to do."""
    reason = check_script(text, alert)
    if reason:
        return reason
    lowered = text.lower()
    for key, name in (("event", "event"), ("severity", "severity"), ("area_short", "area"), ("ends_label", "end time")):
        value = str(alert.get(key) or "").strip().lower()
        if value and value not in lowered:
            return f"alert script dropped the {name}"
    if not any(word in lowered for word in _ACTION_WORDS):
        return "alert script does not say what to do"
    return None


_RECAP_STARTERS = {
    "a", "an", "the", "and", "but", "in", "on", "at", "from", "meanwhile", "also", "elsewhere", "today",
    "tonight", "here", "there", "this", "that", "those", "these", "it", "its", "and", "plus", "finally",
    "first", "next", "closer", "around", "across", "overseas", "nationally", "locally", "abroad", "back",
    "now", "over", "for", "with", "according", "headlines", "news", "world", "top", "stories", "in",
    "reports", "report", "officials", "while", "after", "as", "if", "one", "another", "of", "to",
}


def _words(text: str) -> List[str]:
    return re.findall(r"[A-Za-z][A-Za-z'’.-]*[A-Za-z]|[A-Za-z]", text)


def check_recap(text: str, headlines: Sequence[Mapping[str, Any]]) -> Optional[str]:
    """Drop a recap that names a person, place, or number missing from the titles."""
    body = " ".join(str(text or "").split())
    if not body:
        return "empty"
    if len(body) > 600:
        return "too long"
    corpus = " ".join(f"{h.get('title', '')} {h.get('source', '')}" for h in headlines)
    known = {w.lower().strip("'’.").removesuffix("'s").removesuffix("’s") for w in _words(corpus)}
    known_numbers = set(re.findall(r"\d+(?:\.\d+)?", corpus))
    for token in re.findall(r"(?<![\w.])\d+(?:\.\d+)?", body):
        if token not in known_numbers:
            return f"number {token} is not in the headlines"
    for sentence in re.split(r"(?<=[.!?])\s+", body):
        words = _words(sentence)
        for index, word in enumerate(words):
            if not word[:1].isupper():
                continue
            key = word.lower().strip("'’.").removesuffix("'s").removesuffix("’s")
            if key in known:
                continue
            if index == 0 and key in _RECAP_STARTERS:
                continue
            return f"'{word}' is not in the headlines"
    return None


# ----------------------------------------------------------------------- templates


def _deg(value: Any) -> str:
    return f"{value} degrees" if value is not None else ""


def _pct(value: Any) -> str:
    return f"{value} percent" if value is not None else ""


def template_variants(segment: str, facts: Mapping[str, Any], place: str) -> List[str]:
    builder = _TEMPLATES.get(segment)
    if builder is None:
        return []
    try:
        lines = [" ".join(line.split()) for line in builder(facts, place) if line and line.strip()]
    except (KeyError, IndexError, TypeError):
        return []
    return lines[:4]


def _t_current(f: Mapping[str, Any], place: str) -> List[str]:
    c = f.get("current") or {}
    if not c:
        return []
    sky = str(c.get("sky") or "mixed skies").lower()
    temp = c.get("temp")
    feels = c.get("feels_like")
    wind = c.get("wind")
    wind_dir = c.get("wind_dir") or ""
    humidity = c.get("humidity")
    lines = [
        f"Here in {place}, it's {sky} right now at {_deg(temp)}."
        + (f" It feels like {feels}." if feels is not None and feels != temp else "")
        + (f" Wind {wind_dir} at {wind} miles an hour." if wind is not None else ""),
        f"Your current conditions for {place}: {_deg(temp)} under {sky}."
        + (f" Humidity is {_pct(humidity)}." if humidity is not None else ""),
        f"Right now in {place} we have {sky} and {_deg(temp)}."
        + (f" The dew point sits at {c['dew_point']}." if c.get("dew_point") is not None else ""),
        f"Checking in on {place}: {_deg(temp)} and {sky}."
        + (f" Gusts up to {c['gusts']}." if c.get("gusts") is not None else ""),
    ]
    return lines


def _t_overview(f: Mapping[str, Any], place: str) -> List[str]:
    days = f.get("daily") or []
    if not days:
        return []
    today = days[0]
    tomorrow = days[1] if len(days) > 1 else None
    first = f"Tonight, {str(today.get('sky') or 'mixed skies').lower()} with a low near {today.get('low')}."
    if tomorrow:
        second = (
            f"{tomorrow.get('weekday_name')} brings {str(tomorrow.get('sky') or 'mixed skies').lower()}"
            f" and a high of {tomorrow.get('high')}"
            + (f", with a {_pct(tomorrow.get('precip'))} chance of rain or snow." if tomorrow.get("precip") else ".")
        )
    else:
        second = f"Today's high reaches {today.get('high')}."
    return [
        f"{first} {second}",
        f"Here's the big picture for {place}. {first} {second}",
        f"{second} Before that, {first[0].lower()}{first[1:]}",
    ]


def _t_hourly(f: Mapping[str, Any], place: str) -> List[str]:
    hours = f.get("hourly") or []
    if len(hours) < 2:
        return []
    first, last = hours[0], hours[-1]
    wettest = max(hours, key=lambda h: h.get("precip") or 0)
    rain = (
        f" The best chance of rain or snow is around {wettest['label']}, at {_pct(wettest.get('precip'))}."
        if (wettest.get("precip") or 0) >= 20
        else " Rain or snow chances stay low."
    )
    return [
        f"Over the next several hours, {first['temp']} degrees at {first['label']}, heading to {last['temp']} by {last['label']}.{rain}",
        f"Hour by hour: {first['label']}, {first['temp']}; {last['label']}, {last['temp']}.{rain}",
        f"Through {last['label']}, temperatures go from {first['temp']} to {last['temp']}.{rain}",
    ]


def _t_five_day(f: Mapping[str, Any], place: str) -> List[str]:
    days = f.get("daily") or []
    if len(days) < 2:
        return []
    bits = [f"{d['weekday_name']}, {str(d.get('sky') or '').lower()}, high {d.get('high')}" for d in days[:5]]
    warmest = max(days, key=lambda d: d.get("high") if d.get("high") is not None else -999)
    coolest = min(days, key=lambda d: d.get("low") if d.get("low") is not None else 999)
    return [
        "Your five-day forecast. " + ". ".join(bits) + ".",
        f"Looking at the week ahead, {warmest['weekday_name']} is the warmest at {warmest.get('high')}, "
        f"and the coolest night is {coolest['weekday_name']} at {coolest.get('low')}.",
        f"The extended outlook for {place}: " + "; ".join(bits[:3]) + ".",
    ]


def _t_regional(f: Mapping[str, Any], place: str) -> List[str]:
    cities = f.get("regional") or []
    if len(cities) < 3:
        return []
    bits = [f"{c['name']}, {c['temp']}" for c in cities[:6]]
    return [
        "Around the region: " + "; ".join(bits) + ".",
        "Let's check the travel cities. " + ". ".join(bits[:4]) + ".",
        f"Near {place}, " + "; ".join(bits[:5]) + ".",
    ]


def _t_almanac(f: Mapping[str, Any], place: str) -> List[str]:
    sun = f.get("sun") or {}
    moon = f.get("moon") or {}
    archive = f.get("archive") or {}
    lines = []
    if sun.get("sunrise"):
        base = f"Sunrise today was {sun['sunrise']}, and sunset comes at {sun['sunset']}."
        if moon.get("name"):
            base += f" Tonight's moon: {str(moon['name']).lower()}."
        lines.append(base)
    trivia = trivia_line(archive, place)
    if trivia:
        lines.append(trivia)
        if sun.get("sunset"):
            lines.append(f"Sunset tonight at {sun['sunset']}. {trivia}")
    return lines


def trivia_line(archive: Mapping[str, Any], place: str) -> str:
    high = archive.get("record_high") or {}
    low = archive.get("record_low") or {}
    day = archive.get("today") or "this date"
    if high and low:
        return (
            f"On {day}, the warmest on record here was {high['value']} degrees in {high['year']}, "
            f"and the coldest was {low['value']} in {low['year']}."
        )
    if high:
        return f"The record high for {day} here is {high['value']} degrees, set in {high['year']}."
    return ""


def _t_seasonal(f: Mapping[str, Any], place: str) -> List[str]:
    s = f.get("seasonal") or {}
    lines = []
    parts = []
    if s.get("uv_index") is not None:
        parts.append(f"The UV index is {s['uv_index']}, {str(s.get('uv_label') or '').lower()}.")
    if s.get("aqi") is not None:
        parts.append(f"Air quality is {str(s.get('aqi_label') or '').lower()}, at {s['aqi']}.")
    season = s.get("next_season") or {}
    if season:
        parts.append(f"The {season['name']} is {season['days']} days away.")
    if parts:
        lines.append(" ".join(parts))
    frost = s.get("frost") or {}
    if frost:
        lines.append(f"Around here, the first frost usually arrives by {frost['first_fall']}, and the last one by {frost['last_spring']}.")
    for tie in s.get("holidays") or []:
        if tie.get("kind") == "forecast":
            lines.append(
                f"For {tie['name']} on {tie.get('weekday_name')}, look for {str(tie.get('sky') or '').lower()}, "
                f"a high of {tie.get('high')} and a low of {tie.get('low')}."
            )
        elif tie.get("kind") == "first_snow":
            lines.append(f"Most years, the first snow arrives by {tie.get('first_snow_by')}, ahead of {tie['name']}.")
    if s.get("first_snow_by") and len(lines) < 3:
        lines.append(f"Most years, the first snow here arrives by {s['first_snow_by']}.")
    return lines


def _t_radar(f: Mapping[str, Any], place: str) -> List[str]:
    return [
        f"Here's the radar around {place}.",
        "Let's take a look at the radar.",
        f"Radar for {place} and the surrounding area.",
    ]


def _t_satellite(f: Mapping[str, Any], place: str) -> List[str]:
    return [
        "And the view from the satellite.",
        "Here's the latest satellite picture for the region.",
        "From space, here's the cloud cover across the region.",
    ]


def _t_webcams(f: Mapping[str, Any], place: str) -> List[str]:
    return [
        f"A look outside, from cameras near {place}.",
        "Here's what the sky looks like from cameras around the area.",
    ]


_TEMPLATES: Dict[str, Callable[[Mapping[str, Any], str], List[str]]] = {
    "current": _t_current,
    "overview": _t_overview,
    "hourly": _t_hourly,
    "five_day": _t_five_day,
    "regional": _t_regional,
    "almanac": _t_almanac,
    "seasonal": _t_seasonal,
    "radar": _t_radar,
    "satellite": _t_satellite,
    "webcams": _t_webcams,
}


def alert_lead(alert: Mapping[str, Any]) -> str:
    event = alert.get("event") or "weather alert"
    area = alert.get("area_short") or "the area"
    until = f" until {alert['ends_label']}" if alert.get("ends_label") else ""
    severity = str(alert.get("severity") or "Unknown")
    if alert.get("is_warning"):
        return f"This is a weather bulletin. The National Weather Service has issued a {event} for {area}{until}. Severity: {severity}."
    return f"The National Weather Service has a {event} for {area}{until}. Severity: {severity}."


def _first_sentence(text: str) -> str:
    parts = re.split(r"(?<=[.!?])\s+", str(text or "").strip())
    return parts[0] if parts and parts[0] else ""


def alert_template_variants(alert: Mapping[str, Any]) -> List[str]:
    lead = alert_lead(alert)
    action = _first_sentence(alert.get("instruction") or "")
    if not action or not any(w in action.lower() for w in _ACTION_WORDS):
        action = "Stay alert and follow guidance from local officials."
    return [
        f"{lead} {action}",
        f"{lead} The full statement is on your screen. {action}",
        f"{lead} {action} Details are on screen now.",
    ]


# ---------------------------------------------------------------------------- LLM

_WEATHER_SYSTEM = (
    "You are the warm, unhurried narrator of a local cable weather channel. "
    "Write short spoken scripts from the JSON data only. Rules: use digits for every number; "
    "never state a number, time, weekday, or month that is not in the data; never invent records or trivia "
    "beyond the archive facts given; no greetings with names; one to three sentences, under 60 words each. "
    "Reply with JSON only: {\"segments\": {\"<segment>\": [\"variant\", ...]}} with "
    f"{VARIANTS} different variants for each segment you are given."
)

_ALERT_SYSTEM = (
    "You explain an official National Weather Service alert for a local weather channel. "
    "Do not soften it. In two or three plain sentences say what it means and what people should do. "
    "Mention the event name, the severity, the area, and when it ends exactly as given. "
    "Use digits; no numbers or days that are not in the alert. "
    f"Reply with JSON only: {{\"variants\": [\"...\"]}} with {VARIANTS} variants."
)

_RECAP_SYSTEM = (
    "You write a two or three sentence spoken headline recap for a local weather channel, "
    "between weather segments. Use only the titles and sources given. Do not add names, places, "
    "numbers, or facts that are not in a title. No opinions. "
    f"Reply with JSON only: {{\"variants\": [\"...\"]}} with {VARIANTS} variants."
)


def _extract_json(raw: str) -> Dict[str, Any]:
    text = str(raw or "").strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text, flags=re.I)
    if fence:
        text = fence.group(1).strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return {}
    try:
        payload = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _call(llm: Optional[LlmComplete], system: str, user: Any) -> Dict[str, Any]:
    if llm is None:
        return {}
    try:
        raw = llm([{"role": "system", "content": system}, {"role": "user", "content": json.dumps(user, sort_keys=True)}])
    except Exception as exc:  # noqa: BLE001 — a failed model call falls back to templates
        logger.info("weather script LLM call failed: %s", exc)
        return {}
    return _extract_json(raw)


def _variant(text: str, source: str) -> Dict[str, Any]:
    return {"text": " ".join(str(text).split()), "source": source}


def merge_variants(segment: str, written: Sequence[Any], facts: Mapping[str, Any], place: str) -> List[Dict[str, Any]]:
    """Keep each LLM variant that passes; replace a dropped one with a template."""
    templates = template_variants(segment, facts, place)
    if not templates:
        return []
    out: List[Dict[str, Any]] = []
    for index in range(max(VARIANTS, min(len(written), 4))):
        candidate = written[index] if index < len(written) and isinstance(written[index], str) else ""
        if candidate and check_script(candidate, facts) is None:
            out.append(_variant(candidate, "llm"))
        elif index < len(templates):
            out.append(_variant(templates[index], "template"))
    return out or [_variant(t, "template") for t in templates]


def weather_scripts(
    facts_by_segment: Mapping[str, Mapping[str, Any]],
    place: str,
    *,
    llm: Optional[LlmComplete],
) -> Dict[str, List[Dict[str, Any]]]:
    llm_input = {seg: facts for seg, facts in facts_by_segment.items() if seg in LLM_SEGMENTS and facts}
    written = (_call(llm, _WEATHER_SYSTEM, {"place": place, "segments": llm_input}).get("segments") or {}) if llm_input else {}
    if not isinstance(written, dict):
        written = {}
    out: Dict[str, List[Dict[str, Any]]] = {}
    for segment, facts in facts_by_segment.items():
        if segment == "alerts":
            continue
        rows = written.get(segment) if segment in LLM_SEGMENTS else None
        variants = merge_variants(segment, rows if isinstance(rows, list) else [], facts, place)
        if variants:
            out[segment] = variants
    return out


def alert_scripts(alerts: Sequence[Mapping[str, Any]], *, llm: Optional[LlmComplete]) -> List[Dict[str, Any]]:
    if not alerts:
        return []
    top = alerts[0]
    templates = alert_template_variants(top)
    lead = alert_lead(top)
    fields = {k: top.get(k) for k in ("event", "severity", "urgency", "area_short", "ends_label", "headline", "description", "instruction")}
    rows = _call(llm, _ALERT_SYSTEM, fields).get("variants") or []
    out: List[Dict[str, Any]] = []
    more = " Other alerts are listed on screen." if len(alerts) > 1 else ""
    for index in range(VARIANTS):
        body = rows[index] if index < len(rows) and isinstance(rows[index], str) else ""
        candidate = f"{lead} {body}".strip() if body else ""
        if candidate and check_alert_script(candidate, top) is None:
            out.append(_variant(candidate + more, "llm"))
        else:
            out.append(_variant(templates[index % len(templates)] + more, "template"))
    return out


def recap_scripts(headlines: Sequence[Mapping[str, Any]], *, llm: Optional[LlmComplete]) -> List[Dict[str, Any]]:
    """Spoken recap variants. Empty when no LLM or every variant fails the checker."""
    items = [{"title": h.get("title"), "source": h.get("source")} for h in headlines if h.get("title")]
    if not items or llm is None:
        return []
    rows = _call(llm, _RECAP_SYSTEM, {"headlines": items}).get("variants") or []
    out = []
    for row in rows[:4]:
        if isinstance(row, str) and check_recap(row, items) is None:
            out.append(_variant(row, "llm"))
        elif isinstance(row, str):
            logger.info("weather recap dropped: %s", check_recap(row, items))
    return out
