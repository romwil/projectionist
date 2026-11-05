"""Where the channel is pointed: coordinates plus the geocoded city, region, and country."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# Country names as Open-Meteo geocoding returns them → ISO 3166-1 alpha-2.
COUNTRY_CODES = {
    "united states": "US", "united states of america": "US", "usa": "US",
    "canada": "CA", "mexico": "MX", "united kingdom": "GB", "ireland": "IE",
    "australia": "AU", "new zealand": "NZ", "india": "IN", "france": "FR",
    "germany": "DE", "spain": "ES", "italy": "IT", "portugal": "PT",
    "netherlands": "NL", "belgium": "BE", "switzerland": "CH", "austria": "AT",
    "sweden": "SE", "norway": "NO", "denmark": "DK", "finland": "FI",
    "poland": "PL", "czechia": "CZ", "czech republic": "CZ", "greece": "GR",
    "turkey": "TR", "türkiye": "TR", "israel": "IL", "egypt": "EG",
    "south africa": "ZA", "nigeria": "NG", "kenya": "KE", "japan": "JP",
    "south korea": "KR", "china": "CN", "taiwan": "TW", "hong kong": "HK",
    "singapore": "SG", "malaysia": "MY", "philippines": "PH", "indonesia": "ID",
    "thailand": "TH", "vietnam": "VN", "pakistan": "PK", "bangladesh": "BD",
    "brazil": "BR", "argentina": "AR", "chile": "CL", "colombia": "CO",
    "peru": "PE", "venezuela": "VE", "ukraine": "UA", "romania": "RO",
    "hungary": "HU", "saudi arabia": "SA", "united arab emirates": "AE",
    "puerto rico": "PR",
}

# Google News editions that exist with an English front page. Others fall back
# to world headlines only rather than guessing a language.
GOOGLE_NEWS_ENGLISH_EDITIONS = {
    "US", "CA", "GB", "IE", "AU", "NZ", "IN", "ZA", "NG", "KE", "SG", "MY",
    "PH", "PK", "BD", "IL", "AE", "SA",
}

_US_BOXES = (
    (24.4, 49.5, -125.0, -66.9),  # contiguous states
    (51.0, 71.5, -180.0, -129.9),  # Alaska
    (18.9, 22.3, -160.3, -154.8),  # Hawaii
    (17.8, 18.6, -67.3, -65.2),  # Puerto Rico
)


@dataclass(frozen=True)
class Place:
    label: str
    latitude: float
    longitude: float
    city: str = ""
    region: str = ""
    country: str = ""

    @property
    def key(self) -> str:
        return f"{self.latitude:.2f},{self.longitude:.2f}"

    @property
    def country_code(self) -> str:
        return COUNTRY_CODES.get(self.country.strip().lower(), "")

    @property
    def is_us(self) -> bool:
        code = self.country_code
        if code:
            return code in {"US", "PR"}
        if self.country:
            return False
        return point_in_us(self.latitude, self.longitude)


def point_in_us(latitude: float, longitude: float) -> bool:
    return any(lo_lat <= latitude <= hi_lat and lo_lon <= longitude <= hi_lon for lo_lat, hi_lat, lo_lon, hi_lon in _US_BOXES)


def place_from_label(label: str, latitude: float, longitude: float) -> Place:
    """Split a stored ``name, admin1, country`` label (the geocode format)."""
    text = " ".join(str(label or "").split())
    parts = [p.strip() for p in text.split(",") if p.strip()]
    city = parts[0] if parts else ""
    region = parts[1] if len(parts) >= 3 else ""
    country = parts[-1] if len(parts) >= 2 else ""
    if country and country.lower() not in COUNTRY_CODES and len(parts) == 2:
        # "Springfield, Illinois" — a region, not a country.
        region, country = country, ""
    if city.lower() in {"your area", ""}:
        city = ""
    return Place(
        label=text or "your area",
        latitude=float(latitude),
        longitude=float(longitude),
        city=city,
        region=region,
        country=country,
    )


def short_place(place: Optional[Place]) -> str:
    if place is None:
        return "your area"
    return place.city or place.label or "your area"
