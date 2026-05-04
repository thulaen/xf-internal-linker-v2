"""Shared helpers for safely coercing DRF request query params.

Plain-English: every list endpoint takes optional URL params like
``?page=2&page_size=50&min_score=0.4``. If the operator types
``?page=foo`` by accident, the naive ``int(request.query_params.get("page"))``
call raises ``ValueError`` which Django turns into HTTP 500 — and the
operator sees a generic crash page with no hint about what went wrong.

This module gives every view a single set of helpers that:

    * never raise on bad input — coerce to a sensible default instead
    * clamp numeric inputs to a safe range so an operator can't trigger
      a slow query by asking for ``?page_size=10000`` or ``?page=-5``
    * collect validation errors so the view can return HTTP 400 with
      per-field reasons when the operator wants strict feedback

Use ``coerce_int`` / ``coerce_float`` for the silent-fallback path
(list endpoints where bad input should be ignored rather than rejected),
and ``parse_int_strict`` / ``parse_float_strict`` for the strict path
(settings PUTs where bad input must surface to the operator).

Storage discipline: pure functions, no I/O. No new tables.

Citations: pattern derived from FastAPI's ``Query(...)`` dependency
injection (Tiangolo 2021) and Django REST Framework's
``serializers.IntegerField(min_value=...)`` validators.
"""

from __future__ import annotations

from typing import Any


def coerce_int(
    value: Any,
    *,
    default: int,
    min_value: int | None = None,
    max_value: int | None = None,
) -> int:
    """Best-effort int coercion with sensible default + range clamp.

    Plain-English: turns the raw query-string value into an int. If the
    input is missing, blank, or not a number, returns ``default``. If a
    range is given, the result is clamped into ``[min_value, max_value]``
    so an operator can't trigger a slow query by asking for
    ``?page_size=10000``.

    Use this for list-endpoint paginators where silent fallback is the
    right UX. For settings PUTs (where the operator must see what
    failed), use ``parse_int_strict`` instead.
    """
    if value is None or value == "":
        result = default
    else:
        try:
            result = int(value)
        except (TypeError, ValueError):
            result = default
    if min_value is not None and result < min_value:
        result = min_value
    if max_value is not None and result > max_value:
        result = max_value
    return result


def coerce_float(
    value: Any,
    *,
    default: float,
    min_value: float | None = None,
    max_value: float | None = None,
) -> float:
    """Best-effort float coercion with sensible default + range clamp.

    Same UX rules as ``coerce_int`` — silent fallback to ``default``
    on malformed input.
    """
    if value is None or value == "":
        result = default
    else:
        try:
            result = float(value)
        except (TypeError, ValueError):
            result = default
    if min_value is not None and result < min_value:
        result = min_value
    if max_value is not None and result > max_value:
        result = max_value
    return result


def parse_int_strict(
    value: Any,
    *,
    field_name: str,
    min_value: int | None = None,
    max_value: int | None = None,
) -> tuple[int | None, str | None]:
    """Strict int parser. Returns (parsed_value, error_message).

    Plain-English: use this for settings PUTs where the operator must
    see what failed. Returns ``(value, None)`` on success, or
    ``(None, "<field> must be an integer between X and Y")`` on
    failure. The caller is expected to collect errors into a single
    HTTP 400 response per the cooccurrence settings PUT pattern.
    """
    if value is None or value == "":
        return None, f"{field_name} is required"
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None, _range_error(field_name, "an integer", min_value, max_value)
    if min_value is not None and parsed < min_value:
        return None, _range_error(field_name, "an integer", min_value, max_value)
    if max_value is not None and parsed > max_value:
        return None, _range_error(field_name, "an integer", min_value, max_value)
    return parsed, None


def parse_float_strict(
    value: Any,
    *,
    field_name: str,
    min_value: float | None = None,
    max_value: float | None = None,
) -> tuple[float | None, str | None]:
    """Strict float parser. Same contract as ``parse_int_strict``."""
    if value is None or value == "":
        return None, f"{field_name} is required"
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None, _range_error(field_name, "a number", min_value, max_value)
    if min_value is not None and parsed < min_value:
        return None, _range_error(field_name, "a number", min_value, max_value)
    if max_value is not None and parsed > max_value:
        return None, _range_error(field_name, "a number", min_value, max_value)
    return parsed, None


# Shared truthy/falsy string sets — operators can spell "true" any of
# these ways. Module-level constants so callers (`coerce_bool` plus
# `AppSetting.get_bool`'s explicit 3-way parser) all read from one
# source of truth.
TRUTHY_STRING_VALUES: frozenset[str] = frozenset({"true", "1", "yes", "on"})
FALSY_STRING_VALUES: frozenset[str] = frozenset({"false", "0", "no", "off"})


def coerce_bool(value: Any, *, default: bool = False) -> bool:
    """Type-aware boolean coercion. Single source of truth across the app.

    Plain-English: parses a value into True/False the way an operator
    would expect. ``True``/``False`` pass through; integers/floats
    bool-cast (0 = False, anything else = True); strings parse case-
    insensitive ``"true"|"1"|"yes"|"on"`` as True (every other string
    → False); ``None`` and unsupported types return *default*.

    Why a single helper: previously this exact 3-branch parser appeared
    inline in 15+ sites (every `_coerce_bool` and the body of every
    `setting_bool` / runtime-flag reader). Each copy could (and one did)
    have a subtle bug — e.g. ``bool("no")`` returns True (any non-empty
    string is truthy), so handlers that did ``bool(request.data["x"])``
    silently flipped to True for any string input.

    Note on string semantics: this helper treats unknown strings (e.g.
    "maybe") as False. Use ``parse_bool_strict`` if you need to
    distinguish unknown-string from explicit-false.

    Citation: Django's ``BooleanField.to_python`` does the same
    truthy-set test; this helper is a deliberate re-implementation so
    callers don't have to import django.db.models.fields.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in TRUTHY_STRING_VALUES
    return default


def parse_bool_strict(value: Any, *, default: bool) -> bool:
    """3-way bool parser: explicit-true / explicit-false / unknown→default.

    Plain-English: like ``coerce_bool`` but distinguishes "I typed
    something I don't recognise" from "I explicitly said false". Used
    by ``AppSetting.get_bool`` so an unknown operator value falls back
    to the per-call default rather than silently meaning False.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        v = value.strip().lower()
        if v in TRUTHY_STRING_VALUES:
            return True
        if v in FALSY_STRING_VALUES:
            return False
        return default
    return default


def coerce_uuid(value: Any) -> Any:
    """Best-effort UUID coercion. Returns the UUID or None if invalid.

    Plain-English: callers want either a real ``uuid.UUID`` to pass into
    a queryset filter, or ``None`` so the filter is dropped silently.
    Never raises.
    """
    if value is None or value == "":
        return None
    try:
        import uuid as _uuid

        return _uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        return None


def coerce_pagination(
    query_params,
    *,
    default_page_size: int = 50,
    max_page_size: int = 200,
) -> tuple[int, int, int]:
    """Read ``?page=`` + ``?page_size=`` and return ``(page, page_size, offset)``.

    Plain-English: every list endpoint repeats this same 6-line dance.
    Bad inputs fall back to defaults; both values are clamped to safe
    ranges. The returned ``offset`` is ready to slice a queryset:
    ``qs[offset : offset + page_size]``.
    """
    page = coerce_int(
        query_params.get("page"), default=1, min_value=1
    )
    page_size = coerce_int(
        query_params.get("page_size"),
        default=default_page_size,
        min_value=1,
        max_value=max_page_size,
    )
    offset = (page - 1) * page_size
    return page, page_size, offset


def _range_error(
    field_name: str,
    type_label: str,
    min_value: float | int | None,
    max_value: float | int | None,
) -> str:
    """Build a single-line plain-English range message."""
    if min_value is not None and max_value is not None:
        return f"{field_name} must be {type_label} between {min_value} and {max_value}"
    if min_value is not None:
        return f"{field_name} must be {type_label} ≥ {min_value}"
    if max_value is not None:
        return f"{field_name} must be {type_label} ≤ {max_value}"
    return f"{field_name} must be {type_label}"
