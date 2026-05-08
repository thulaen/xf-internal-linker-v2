"""Tests for the apps.api package.

The api app is a thin DRF view layer over services that already have
their own dedicated test suites. The QueryParamsHelperTests below
exercise the `apps.api.query_params` module — the foundational
type-coercion + pagination helpers that every list / filter view
across the codebase depends on. These tests prevent silent regressions
in the truthy-string semantics that were a long-standing source of
copy-pasted bugs (``bool("no") == True`` was the original).
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

from django.test import SimpleTestCase

from apps.api.query_params import (
    FALSY_STRING_VALUES,
    TRUTHY_STRING_VALUES,
    coerce_bool,
    coerce_float,
    coerce_int,
    coerce_pagination,
    coerce_uuid,
    parse_bool_strict,
    parse_float_strict,
    parse_int_strict,
)


class ApiPackageImportTests(SimpleTestCase):
    """Verify every public module in apps.api imports cleanly."""

    def test_embedding_views_imports(self) -> None:
        from apps.api import embedding_views  # noqa: F401

    def test_ml_views_imports(self) -> None:
        from apps.api import ml_views  # noqa: F401

    def test_throttles_imports(self) -> None:
        from apps.api import throttles  # noqa: F401

    def test_urls_imports(self) -> None:
        from apps.api import urls  # noqa: F401

    def test_query_params_imports(self) -> None:
        from apps.api import query_params  # noqa: F401


# ── coerce_int ───────────────────────────────────────────────────


class CoerceIntTests(SimpleTestCase):
    """``coerce_int`` is the safe-fallback integer parser used by every
    list endpoint's pagination + filter coercion. These cases exercise
    the documented contract end-to-end."""

    def test_parses_valid_int_string(self) -> None:
        self.assertEqual(coerce_int("42", default=10), 42)

    def test_parses_valid_int_value(self) -> None:
        self.assertEqual(coerce_int(42, default=10), 42)

    def test_returns_default_on_none(self) -> None:
        self.assertEqual(coerce_int(None, default=10), 10)

    def test_returns_default_on_empty_string(self) -> None:
        self.assertEqual(coerce_int("", default=10), 10)

    def test_returns_default_on_garbage_string(self) -> None:
        self.assertEqual(coerce_int("foo", default=10), 10)

    def test_returns_default_on_unsupported_type(self) -> None:
        self.assertEqual(coerce_int(["weird"], default=10), 10)

    def test_clamps_to_max(self) -> None:
        self.assertEqual(coerce_int("1000", default=10, max_value=100), 100)

    def test_clamps_to_min(self) -> None:
        self.assertEqual(coerce_int("-5", default=10, min_value=1), 1)

    def test_clamps_default_into_range(self) -> None:
        # Default outside [min, max] gets clamped too — guards against a
        # caller who passes default=50 with min_value=100.
        self.assertEqual(coerce_int(None, default=50, min_value=100), 100)

    def test_negative_int_passes_through_when_no_min(self) -> None:
        self.assertEqual(coerce_int("-42", default=0), -42)


# ── coerce_float ─────────────────────────────────────────────────


class CoerceFloatTests(SimpleTestCase):
    def test_parses_valid_float_string(self) -> None:
        self.assertEqual(coerce_float("0.5", default=1.0), 0.5)

    def test_parses_valid_int_string_as_float(self) -> None:
        self.assertEqual(coerce_float("42", default=1.0), 42.0)

    def test_returns_default_on_garbage(self) -> None:
        self.assertEqual(coerce_float("half", default=0.5), 0.5)

    def test_clamps_to_range(self) -> None:
        self.assertEqual(
            coerce_float("99.9", default=0.5, min_value=0.0, max_value=1.0), 1.0
        )

    def test_returns_default_on_none(self) -> None:
        self.assertEqual(coerce_float(None, default=0.42), 0.42)


# ── coerce_bool ──────────────────────────────────────────────────


class CoerceBoolTests(SimpleTestCase):
    """The most-critical helper — silently flipping ``"no"`` to True was
    a real bug across multiple endpoints before this helper landed."""

    def test_truthy_strings(self) -> None:
        for value in ("true", "True", "TRUE", "1", "yes", "YES", "on", "ON", " on "):
            with self.subTest(value=value):
                self.assertTrue(coerce_bool(value), f"{value!r} should be True")

    def test_falsy_strings(self) -> None:
        # The bug fix that motivated this whole helper: `bool("no")` returns
        # True (any non-empty string is truthy in Python) — we explicitly
        # require the value to be in the truthy set.
        for value in ("no", "false", "0", "off", "", "maybe", "anything"):
            with self.subTest(value=value):
                self.assertFalse(coerce_bool(value), f"{value!r} should be False")

    def test_native_bool(self) -> None:
        self.assertTrue(coerce_bool(True))
        self.assertFalse(coerce_bool(False))

    def test_native_int_zero_is_false(self) -> None:
        self.assertFalse(coerce_bool(0))

    def test_native_int_nonzero_is_true(self) -> None:
        self.assertTrue(coerce_bool(42))
        self.assertTrue(coerce_bool(-1))

    def test_native_float(self) -> None:
        self.assertFalse(coerce_bool(0.0))
        self.assertTrue(coerce_bool(0.5))

    def test_none_returns_default(self) -> None:
        self.assertTrue(coerce_bool(None, default=True))
        self.assertFalse(coerce_bool(None, default=False))

    def test_unsupported_types_return_default(self) -> None:
        self.assertTrue(coerce_bool(["weird"], default=True))
        self.assertFalse(coerce_bool({"still": "weird"}, default=False))


# ── parse_bool_strict ────────────────────────────────────────────


class ParseBoolStrictTests(SimpleTestCase):
    """The 3-way variant — required by AppSetting.get_bool to preserve
    operator intent on unknown strings."""

    def test_truthy_strings(self) -> None:
        self.assertTrue(parse_bool_strict("true", default=False))
        self.assertTrue(parse_bool_strict("YES", default=False))

    def test_falsy_strings(self) -> None:
        self.assertFalse(parse_bool_strict("false", default=True))
        self.assertFalse(parse_bool_strict("NO", default=True))
        self.assertFalse(parse_bool_strict("0", default=True))
        self.assertFalse(parse_bool_strict("off", default=True))

    def test_unknown_string_returns_default(self) -> None:
        # This is the core difference vs coerce_bool — unknown strings
        # don't silently flip to False.
        self.assertTrue(parse_bool_strict("maybe", default=True))
        self.assertFalse(parse_bool_strict("?", default=False))

    def test_empty_string_returns_default(self) -> None:
        self.assertTrue(parse_bool_strict("", default=True))
        self.assertFalse(parse_bool_strict("", default=False))

    def test_native_bool(self) -> None:
        self.assertTrue(parse_bool_strict(True, default=False))
        self.assertFalse(parse_bool_strict(False, default=True))

    def test_unsupported_types_return_default(self) -> None:
        self.assertTrue(parse_bool_strict(["weird"], default=True))


# ── parse_int_strict / parse_float_strict ───────────────────────


class ParseIntStrictTests(SimpleTestCase):
    """Returns ``(value, error)`` tuple for settings PUTs."""

    def test_happy_path(self) -> None:
        value, err = parse_int_strict("42", field_name="x", min_value=1, max_value=100)
        self.assertEqual(value, 42)
        self.assertIsNone(err)

    def test_garbage_returns_error_with_field_name(self) -> None:
        value, err = parse_int_strict(
            "foo", field_name="page_size", min_value=1, max_value=100
        )
        self.assertIsNone(value)
        self.assertIsNotNone(err)
        self.assertIn("page_size", err)
        self.assertIn("1", err)
        self.assertIn("100", err)

    def test_below_min_returns_error(self) -> None:
        value, err = parse_int_strict("0", field_name="x", min_value=1)
        self.assertIsNone(value)
        self.assertIsNotNone(err)

    def test_above_max_returns_error(self) -> None:
        value, err = parse_int_strict("9999", field_name="x", max_value=100)
        self.assertIsNone(value)
        self.assertIsNotNone(err)

    def test_none_returns_required_error(self) -> None:
        value, err = parse_int_strict(None, field_name="x")
        self.assertIsNone(value)
        self.assertIsNotNone(err)
        self.assertIn("required", err.lower())


class ParseFloatStrictTests(SimpleTestCase):
    def test_happy_path(self) -> None:
        value, err = parse_float_strict(
            "0.5", field_name="x", min_value=0.0, max_value=1.0
        )
        self.assertEqual(value, 0.5)
        self.assertIsNone(err)

    def test_out_of_range(self) -> None:
        value, err = parse_float_strict(
            "1.5", field_name="threshold", min_value=0.0, max_value=1.0
        )
        self.assertIsNone(value)
        self.assertIn("threshold", err)


# ── coerce_uuid ──────────────────────────────────────────────────


class CoerceUuidTests(SimpleTestCase):
    def test_valid_uuid_string(self) -> None:
        u = "00000000-0000-0000-0000-000000000000"
        result = coerce_uuid(u)
        self.assertIsNotNone(result)
        self.assertEqual(str(result), u)

    def test_garbage_returns_none(self) -> None:
        self.assertIsNone(coerce_uuid("not-a-uuid"))

    def test_empty_string_returns_none(self) -> None:
        self.assertIsNone(coerce_uuid(""))

    def test_none_returns_none(self) -> None:
        self.assertIsNone(coerce_uuid(None))

    def test_non_string_returns_none(self) -> None:
        # Numbers, lists, dicts — all should silently fall back
        self.assertIsNone(coerce_uuid(123))
        self.assertIsNone(coerce_uuid([1, 2, 3]))

    def test_already_uuid_object_pass_through(self) -> None:
        u = uuid.uuid4()
        result = coerce_uuid(u)
        self.assertEqual(result, u)


# ── coerce_pagination ────────────────────────────────────────────


def _mock_query_params(params: dict[str, str]) -> MagicMock:
    """Build a MagicMock that mimics DRF's request.query_params.get()."""
    mock = MagicMock()
    mock.get.side_effect = lambda key, default=None: params.get(key, default)
    return mock


class CoercePaginationTests(SimpleTestCase):
    def test_happy_path(self) -> None:
        page, page_size, offset = coerce_pagination(
            _mock_query_params({"page": "2", "page_size": "50"})
        )
        self.assertEqual(page, 2)
        self.assertEqual(page_size, 50)
        self.assertEqual(offset, 50)

    def test_garbage_falls_back_to_defaults(self) -> None:
        page, page_size, offset = coerce_pagination(
            _mock_query_params({"page": "foo", "page_size": "bar"})
        )
        self.assertEqual(page, 1)
        self.assertEqual(page_size, 50)
        self.assertEqual(offset, 0)

    def test_missing_params_use_defaults(self) -> None:
        page, page_size, offset = coerce_pagination(
            _mock_query_params({}), default_page_size=25, max_page_size=100
        )
        self.assertEqual(page, 1)
        self.assertEqual(page_size, 25)
        self.assertEqual(offset, 0)

    def test_page_size_clamps_to_max(self) -> None:
        _, page_size, _ = coerce_pagination(
            _mock_query_params({"page_size": "10000"}), max_page_size=200
        )
        self.assertEqual(page_size, 200)

    def test_page_clamps_to_min_one(self) -> None:
        page, _, _ = coerce_pagination(_mock_query_params({"page": "-5"}))
        self.assertEqual(page, 1)

    def test_zero_page_clamps_to_one(self) -> None:
        page, _, _ = coerce_pagination(_mock_query_params({"page": "0"}))
        self.assertEqual(page, 1)


# ── module-level constants ───────────────────────────────────────


class StringSetConstantTests(SimpleTestCase):
    """Sanity checks on the canonical truthy/falsy string sets."""

    def test_truthy_set_is_frozen(self) -> None:
        self.assertIsInstance(TRUTHY_STRING_VALUES, frozenset)
        self.assertEqual(set(TRUTHY_STRING_VALUES), {"true", "1", "yes", "on"})

    def test_falsy_set_is_frozen(self) -> None:
        self.assertIsInstance(FALSY_STRING_VALUES, frozenset)
        self.assertEqual(set(FALSY_STRING_VALUES), {"false", "0", "no", "off"})

    def test_truthy_and_falsy_disjoint(self) -> None:
        # Sanity: no string can be both truthy and falsy. If this ever
        # fails, parse_bool_strict's branch order silently determines the
        # winner — better to fail loudly here.
        self.assertEqual(TRUTHY_STRING_VALUES & FALSY_STRING_VALUES, frozenset())
