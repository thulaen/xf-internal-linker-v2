"""Tests for the validate-side coercer helpers in settings_helpers.py.

These four helpers (``coerce_setting_float``, ``coerce_setting_int``,
``coerce_setting_bool``, ``enforce_bounds``) replaced ~17 duplicated
``_coerce_*`` closures previously inlined in apps/core/views.py settings
validators. The closures had identical contracts so behaviour parity is
the contract these tests enforce — any future tweak (e.g. swapping the
underlying coerce_bool, changing the error-message format) must keep
parity or every settings PUT endpoint regresses simultaneously.

Sister-bug fix verified: ``_validate_feedback_rerank_settings`` previously
rolled its own bool-coercer that did NOT strip surrounding whitespace
(`" true "` would be rejected). ``coerce_setting_bool`` delegates to
the shared ``coerce_bool`` which strips, so all endpoints accept the
same truthy values now. The truthy set itself is identical:
``{"true", "1", "yes", "on"}`` (case-insensitive).
"""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.core.services.settings_helpers import (
    coerce_setting_bool,
    coerce_setting_float,
    coerce_setting_int,
    enforce_bounds,
)


class CoerceSettingFloatTests(SimpleTestCase):
    """Verify the float coercer matches the prior closures' contract."""

    def test_uses_payload_value_when_present(self):
        result = coerce_setting_float({"x": "1.5"}, {"x": 99.0}, "x")
        self.assertEqual(result, 1.5)

    def test_falls_back_to_current_when_missing(self):
        result = coerce_setting_float({}, {"x": 0.25}, "x")
        self.assertEqual(result, 0.25)

    def test_accepts_int_input(self):
        # int is implicitly castable to float — must not raise.
        result = coerce_setting_float({"x": 7}, {"x": 0.0}, "x")
        self.assertEqual(result, 7.0)

    def test_raises_named_error_on_non_numeric(self):
        with self.assertRaises(ValueError) as ctx:
            coerce_setting_float({"x": "abc"}, {"x": 0.0}, "x")
        self.assertIn("x must be numeric", str(ctx.exception))

    def test_raises_named_error_on_none(self):
        with self.assertRaises(ValueError) as ctx:
            coerce_setting_float({"x": None}, {"x": 0.0}, "x")
        self.assertIn("x must be numeric", str(ctx.exception))

    def test_raises_on_inf_when_finite_required(self):
        with self.assertRaises(ValueError) as ctx:
            coerce_setting_float({"x": float("inf")}, {"x": 0.0}, "x")
        self.assertIn("x must be finite", str(ctx.exception))

    def test_raises_on_nan_when_finite_required(self):
        with self.assertRaises(ValueError) as ctx:
            coerce_setting_float({"x": float("nan")}, {"x": 0.0}, "x")
        self.assertIn("x must be finite", str(ctx.exception))

    def test_allows_inf_when_finite_check_disabled(self):
        # Silo settings historically allow inf — opt-out via require_finite=False.
        result = coerce_setting_float(
            {"x": float("inf")},
            {"x": 0.0},
            "x",
            require_finite=False,
        )
        self.assertEqual(result, float("inf"))


class CoerceSettingIntTests(SimpleTestCase):
    """Verify the int coercer matches the prior closures' contract."""

    def test_uses_payload_value_when_present(self):
        result = coerce_setting_int({"n": "5"}, {"n": 99}, "n")
        self.assertEqual(result, 5)

    def test_falls_back_to_current_when_missing(self):
        result = coerce_setting_int({}, {"n": 42}, "n")
        self.assertEqual(result, 42)

    def test_accepts_int_input(self):
        result = coerce_setting_int({"n": 7}, {"n": 0}, "n")
        self.assertEqual(result, 7)

    def test_raises_named_error_on_non_int(self):
        with self.assertRaises(ValueError) as ctx:
            coerce_setting_int({"n": "abc"}, {"n": 0}, "n")
        self.assertIn("n must be an integer", str(ctx.exception))

    def test_raises_named_error_on_float_string(self):
        # int("1.5") raises — match the closures' historical behaviour.
        with self.assertRaises(ValueError) as ctx:
            coerce_setting_int({"n": "1.5"}, {"n": 0}, "n")
        self.assertIn("n must be an integer", str(ctx.exception))

    def test_raises_named_error_on_none(self):
        with self.assertRaises(ValueError) as ctx:
            coerce_setting_int({"n": None}, {"n": 0}, "n")
        self.assertIn("n must be an integer", str(ctx.exception))


class CoerceSettingBoolTests(SimpleTestCase):
    """Verify the bool coercer + the y/Y sister-bug fix."""

    def test_uses_payload_value_when_present(self):
        self.assertTrue(coerce_setting_bool({"b": True}, {"b": False}, "b"))
        self.assertFalse(coerce_setting_bool({"b": False}, {"b": True}, "b"))

    def test_falls_back_to_current_when_missing(self):
        self.assertTrue(coerce_setting_bool({}, {"b": True}, "b"))
        self.assertFalse(coerce_setting_bool({}, {"b": False}, "b"))

    def test_accepts_string_truthy_values(self):
        # The 4 truthy strings the project-wide coerce_bool accepts
        # (per TRUTHY_STRING_VALUES in apps.api.query_params).
        for truthy in ("1", "true", "yes", "on"):
            self.assertTrue(
                coerce_setting_bool({"b": truthy}, {"b": False}, "b"),
                msg=f"{truthy!r} should be truthy",
            )

    def test_accepts_string_truthy_values_case_insensitive(self):
        for truthy in ("True", "TRUE", "YES", "ON", "1"):
            self.assertTrue(
                coerce_setting_bool({"b": truthy}, {"b": False}, "b"),
                msg=f"{truthy!r} should be truthy (case-insensitive)",
            )

    def test_accepts_string_truthy_values_with_whitespace(self):
        # Sister-bug fix vs the old _validate_feedback_rerank_settings
        # closure: old code didn't strip — " true " would silently be False.
        for truthy in (" true", "true ", "  yes  ", "\ton\n"):
            self.assertTrue(
                coerce_setting_bool({"b": truthy}, {"b": False}, "b"),
                msg=f"{truthy!r} should be truthy (whitespace-tolerant)",
            )

    def test_treats_string_falsy_values_as_false(self):
        for falsy in ("0", "false", "no", "off"):
            self.assertFalse(
                coerce_setting_bool({"b": falsy}, {"b": True}, "b"),
                msg=f"{falsy!r} should be falsy",
            )

    def test_unknown_strings_become_false_not_default(self):
        # Document behaviour: per coerce_bool docstring, unknown strings
        # always become False — the `default` kwarg only fires for None
        # / unsupported types. Use parse_bool_strict if you need
        # unknown-vs-explicit-false distinction.
        self.assertFalse(coerce_setting_bool({"b": "maybe"}, {"b": False}, "b"))
        self.assertFalse(
            coerce_setting_bool({"b": "maybe"}, {"b": False}, "b", default=True),
        )


class EnforceBoundsTests(SimpleTestCase):
    """Verify the bounds enforcer matches the prior inline check pattern."""

    def test_passes_when_all_values_in_range(self):
        # Should not raise.
        enforce_bounds(
            {"a": 0.5, "b": 5},
            {"a": (0.0, 1.0), "b": (1, 10)},
        )

    def test_passes_at_inclusive_minimum(self):
        enforce_bounds({"a": 0.0}, {"a": (0.0, 1.0)})

    def test_passes_at_inclusive_maximum(self):
        enforce_bounds({"a": 1.0}, {"a": (0.0, 1.0)})

    def test_raises_below_minimum(self):
        with self.assertRaises(ValueError) as ctx:
            enforce_bounds({"a": -0.1}, {"a": (0.0, 1.0)})
        self.assertIn("a must be between 0.0 and 1.0", str(ctx.exception))

    def test_raises_above_maximum(self):
        with self.assertRaises(ValueError) as ctx:
            enforce_bounds({"a": 1.1}, {"a": (0.0, 1.0)})
        self.assertIn("a must be between 0.0 and 1.0", str(ctx.exception))

    def test_first_failing_key_wins(self):
        # If two keys are both out of bounds, the first one in dict-iteration
        # order is the one reported — matches the prior loop's behaviour.
        with self.assertRaises(ValueError) as ctx:
            enforce_bounds(
                {"a": -0.1, "b": -1},
                {"a": (0.0, 1.0), "b": (1, 10)},
            )
        self.assertIn("a must be between", str(ctx.exception))

    def test_works_with_int_bounds(self):
        # Mixed int/float bounds should both work.
        enforce_bounds({"n": 5}, {"n": (1, 10)})
        with self.assertRaises(ValueError):
            enforce_bounds({"n": 11}, {"n": (1, 10)})


class CoercerIntegrationTests(SimpleTestCase):
    """End-to-end: coerce + enforce_bounds together (the typical validator pattern)."""

    def test_full_validator_flow_passes(self):
        payload = {"weight": "0.5", "count": "5", "enabled": "yes"}
        current = {"weight": 0.0, "count": 1, "enabled": False}
        validated = {
            "weight": coerce_setting_float(payload, current, "weight"),
            "count": coerce_setting_int(payload, current, "count"),
            "enabled": coerce_setting_bool(payload, current, "enabled"),
        }
        enforce_bounds(validated, {"weight": (0.0, 1.0), "count": (1, 10)})
        self.assertEqual(validated, {"weight": 0.5, "count": 5, "enabled": True})

    def test_full_validator_flow_raises_on_bounds_violation(self):
        payload = {"weight": "1.5"}
        current = {"weight": 0.0}
        validated = {"weight": coerce_setting_float(payload, current, "weight")}
        with self.assertRaises(ValueError) as ctx:
            enforce_bounds(validated, {"weight": (0.0, 1.0)})
        self.assertIn("weight must be between 0.0 and 1.0", str(ctx.exception))

    def test_finite_check_still_runs_inside_full_flow(self):
        payload = {"weight": float("inf")}
        current = {"weight": 0.0}
        with self.assertRaises(ValueError) as ctx:
            coerce_setting_float(payload, current, "weight")
        self.assertIn("weight must be finite", str(ctx.exception))


# ---------------------------------------------------------------------------
# Tests for the clamp variants (lenient — silently clamps instead of raising)
# ---------------------------------------------------------------------------


class CoerceClampFloatTests(SimpleTestCase):
    """Verify the clamp-float helper used by value-model settings."""

    def test_in_range_passes_through(self):
        from apps.core.services.settings_helpers import coerce_clamp_float

        result = coerce_clamp_float({"x": 0.5}, {"x": 0.0}, "x", 0.0, 1.0)
        self.assertEqual(result, 0.5)

    def test_below_min_clamps_to_min(self):
        from apps.core.services.settings_helpers import coerce_clamp_float

        result = coerce_clamp_float({"x": -1.0}, {"x": 0.0}, "x", 0.0, 1.0)
        self.assertEqual(result, 0.0)

    def test_above_max_clamps_to_max(self):
        from apps.core.services.settings_helpers import coerce_clamp_float

        result = coerce_clamp_float({"x": 5.0}, {"x": 0.0}, "x", 0.0, 1.0)
        self.assertEqual(result, 1.0)

    def test_bad_string_falls_back_to_current(self):
        from apps.core.services.settings_helpers import coerce_clamp_float

        result = coerce_clamp_float({"x": "abc"}, {"x": 0.7}, "x", 0.0, 1.0)
        self.assertEqual(result, 0.7)

    def test_bad_string_with_no_current_falls_back_to_zero(self):
        from apps.core.services.settings_helpers import coerce_clamp_float

        # Spec: missing-from-current AND non-numeric → 0.0 (then clamped).
        result = coerce_clamp_float({"x": "abc"}, {}, "x", 0.5, 1.0)
        self.assertEqual(result, 0.5)  # clamps 0.0 up to 0.5 (the lo bound)

    def test_uses_current_when_payload_missing(self):
        from apps.core.services.settings_helpers import coerce_clamp_float

        result = coerce_clamp_float({}, {"x": 0.42}, "x", 0.0, 1.0)
        self.assertEqual(result, 0.42)


class CoerceClampIntTests(SimpleTestCase):
    """Verify the clamp-int helper used by value-model settings."""

    def test_in_range_passes_through(self):
        from apps.core.services.settings_helpers import coerce_clamp_int

        self.assertEqual(coerce_clamp_int({"n": 5}, {"n": 0}, "n", 1, 10), 5)

    def test_below_min_clamps_to_min(self):
        from apps.core.services.settings_helpers import coerce_clamp_int

        self.assertEqual(coerce_clamp_int({"n": -5}, {"n": 0}, "n", 1, 10), 1)

    def test_above_max_clamps_to_max(self):
        from apps.core.services.settings_helpers import coerce_clamp_int

        self.assertEqual(coerce_clamp_int({"n": 99}, {"n": 0}, "n", 1, 10), 10)

    def test_bad_string_falls_back_to_current_then_clamps(self):
        from apps.core.services.settings_helpers import coerce_clamp_int

        # "abc" -> int() raises -> falls back to current["n"]=7 -> in range -> 7
        self.assertEqual(coerce_clamp_int({"n": "abc"}, {"n": 7}, "n", 1, 10), 7)


class CoerceLenientBoolTests(SimpleTestCase):
    """Verify the lenient bool reader used by value-model + similar partial-PUTs."""

    def test_uses_current_get_not_indexer(self):
        from apps.core.services.settings_helpers import coerce_lenient_bool

        # Key missing from BOTH payload and current -> would KeyError on
        # the strict variant; lenient must return False (default).
        self.assertFalse(coerce_lenient_bool({}, {}, "missing"))

    def test_payload_truthy_string_wins(self):
        from apps.core.services.settings_helpers import coerce_lenient_bool

        self.assertTrue(coerce_lenient_bool({"b": "yes"}, {"b": False}, "b"))

    def test_falls_back_to_current_when_payload_missing(self):
        from apps.core.services.settings_helpers import coerce_lenient_bool

        self.assertTrue(coerce_lenient_bool({}, {"b": True}, "b"))


# ---------------------------------------------------------------------------
# Tests for the two-tier AppSetting readers (operator → fallback).
# ---------------------------------------------------------------------------


from django.test import TestCase  # TestCase needed for DB-touching tests
from apps.core.models import AppSetting
from apps.core.services.settings_helpers import (
    read_app_setting_bool,
    read_app_setting_float,
    read_app_setting_int,
)


class ReadAppSettingFloatTests(TestCase):
    """Verify two-tier float reader semantics."""

    def setUp(self):
        AppSetting.objects.filter(key__startswith="test.read_float.").delete()

    def test_returns_default_when_no_app_setting(self):
        self.assertEqual(read_app_setting_float("test.read_float.missing", 0.42), 0.42)

    def test_reads_from_app_setting(self):
        AppSetting.objects.create(
            key="test.read_float.x", value="1.5", value_type="float"
        )
        self.assertEqual(read_app_setting_float("test.read_float.x", 0.0), 1.5)

    def test_falls_back_on_bad_string(self):
        AppSetting.objects.create(
            key="test.read_float.bad", value="abc", value_type="float"
        )
        # Bad operator value falls back silently to default — no exception.
        self.assertEqual(read_app_setting_float("test.read_float.bad", 0.5), 0.5)

    def test_falls_back_on_inf_when_finite_required(self):
        AppSetting.objects.create(
            key="test.read_float.inf", value="inf", value_type="float"
        )
        self.assertEqual(read_app_setting_float("test.read_float.inf", 0.5), 0.5)

    def test_allows_inf_when_finite_check_disabled(self):
        AppSetting.objects.create(
            key="test.read_float.inf2", value="inf", value_type="float"
        )
        result = read_app_setting_float(
            "test.read_float.inf2",
            0.5,
            require_finite=False,
        )
        self.assertEqual(result, float("inf"))


class ReadAppSettingIntTests(TestCase):
    """Verify two-tier int reader semantics."""

    def setUp(self):
        AppSetting.objects.filter(key__startswith="test.read_int.").delete()

    def test_returns_default_when_no_app_setting(self):
        self.assertEqual(read_app_setting_int("test.read_int.missing", 42), 42)

    def test_reads_from_app_setting(self):
        AppSetting.objects.create(key="test.read_int.x", value="7", value_type="int")
        self.assertEqual(read_app_setting_int("test.read_int.x", 0), 7)

    def test_falls_back_on_bad_string(self):
        AppSetting.objects.create(
            key="test.read_int.bad", value="abc", value_type="int"
        )
        self.assertEqual(read_app_setting_int("test.read_int.bad", 99), 99)


class ReadAppSettingBoolTests(TestCase):
    """Verify two-tier bool reader + sister-bug fix vs old _read_bool closures."""

    def setUp(self):
        AppSetting.objects.filter(key__startswith="test.read_bool.").delete()

    def test_returns_default_when_no_app_setting(self):
        self.assertTrue(read_app_setting_bool("test.read_bool.missing", True))
        self.assertFalse(read_app_setting_bool("test.read_bool.missing", False))

    def test_reads_truthy_string_from_app_setting(self):
        # The OLD _read_feedback_rerank_settings closure only accepted "true".
        # The new shared reader also accepts "1" / "yes" / "on", which is
        # the project-wide convention. Test all four to lock the contract.
        for truthy in ("true", "1", "yes", "on"):
            AppSetting.objects.update_or_create(
                key="test.read_bool.x",
                defaults={"value": truthy, "value_type": "bool"},
            )
            self.assertTrue(
                read_app_setting_bool("test.read_bool.x", False),
                msg=f"{truthy!r} should read True",
            )

    def test_reads_falsy_string_from_app_setting(self):
        AppSetting.objects.create(
            key="test.read_bool.f", value="false", value_type="bool"
        )
        self.assertFalse(read_app_setting_bool("test.read_bool.f", True))
