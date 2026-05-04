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
            {"x": float("inf")}, {"x": 0.0}, "x", require_finite=False,
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
            {"a": 0.5, "b": 5}, {"a": (0.0, 1.0), "b": (1, 10)},
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
                {"a": -0.1, "b": -1}, {"a": (0.0, 1.0), "b": (1, 10)},
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
