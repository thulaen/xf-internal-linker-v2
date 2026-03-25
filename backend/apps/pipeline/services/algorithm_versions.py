"""Helpers for dated algorithm version labels and record-keeping metadata."""

from __future__ import annotations

from datetime import date


def build_algorithm_version_metadata(
    *,
    algorithm_key: str,
    version_date: date,
) -> dict[str, str | int]:
    """Return a JSON-safe version stamp with full day, month, and year parts."""
    month_name = version_date.strftime("%B")
    return {
        "algorithm_key": algorithm_key,
        "version_date": version_date.isoformat(),
        "version_day": version_date.day,
        "version_month": month_name,
        "version_year": version_date.year,
        "version_slug": version_date.strftime("%Y_%m_%d"),
        "version_label": f"{month_name} {version_date.day}, {version_date.year}",
        "field_suffix": f"{month_name.lower()}_{version_date.day:02d}_{version_date.year}",
    }


WEIGHTED_AUTHORITY_VERSION = build_algorithm_version_metadata(
    algorithm_key="weighted_authority_pagerank",
    version_date=date(2026, 3, 25),
)

PHRASE_MATCHING_VERSION = build_algorithm_version_metadata(
    algorithm_key="phrase_matching_anchor_expansion",
    version_date=date(2026, 3, 25),
)

LEARNED_ANCHOR_VERSION = build_algorithm_version_metadata(
    algorithm_key="learned_anchor_vocabulary_corroboration",
    version_date=date(2026, 3, 25),
)
