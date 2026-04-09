"""Hardcoded analytics country exclusions."""

from __future__ import annotations

BLOCKED_COUNTRY_NAMES = ("China", "Singapore", "Vietnam")
BLOCKED_COUNTRY_CODES_ALPHA2 = ("CN", "SG", "VN")
BLOCKED_COUNTRY_CODES_ALPHA3 = ("CHN", "SGP", "VNM")
BLOCKED_TELEMETRY_COUNTRY_VALUES = (
    BLOCKED_COUNTRY_NAMES + BLOCKED_COUNTRY_CODES_ALPHA2 + BLOCKED_COUNTRY_CODES_ALPHA3
)

_BLOCKED_COUNTRY_ALIASES = {
    "china",
    "singapore",
    "vietnam",
    "cn",
    "sg",
    "vn",
    "chn",
    "sgp",
    "vnm",
    "mainland china",
    "people's republic of china",
    "viet nam",
    "socialist republic of vietnam",
}


def is_blocked_country(country: str | None) -> bool:
    normalized = str(country or "").strip().lower()
    return normalized in _BLOCKED_COUNTRY_ALIASES
