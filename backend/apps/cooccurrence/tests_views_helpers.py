"""SimpleTestCase coverage for pure helpers extracted from views.py.

Mirrors the shape of ``tests_services_helpers.py``: each test class
targets one extracted helper so failures point directly at the broken
function. No DB, no Docker — these run in milliseconds.
"""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.cooccurrence.views import (
    DEFAULT_COOCCURRENCE_SETTINGS,
    _COOCCURRENCE_SETTING_SPECS,
    _SettingSpec,
    _coerce_setting_value,
    _validate_cooccurrence_settings,
)


# ---------------------------------------------------------------------------
# _coerce_setting_value — single-field validator
# ---------------------------------------------------------------------------


class CoerceSettingValueBoolTests(SimpleTestCase):
    _SPEC = _SettingSpec("k", "f", "bool")

    def test_truthy_returns_true_string(self) -> None:
        db_value, err = _coerce_setting_value(self._SPEC, True)
        self.assertEqual(db_value, "true")
        self.assertIsNone(err)

    def test_falsy_returns_false_string(self) -> None:
        db_value, err = _coerce_setting_value(self._SPEC, False)
        self.assertEqual(db_value, "false")
        self.assertIsNone(err)

    def test_truthy_int_returns_true_string(self) -> None:
        db_value, err = _coerce_setting_value(self._SPEC, 1)
        self.assertEqual(db_value, "true")
        self.assertIsNone(err)

    def test_zero_int_returns_false_string(self) -> None:
        db_value, err = _coerce_setting_value(self._SPEC, 0)
        self.assertEqual(db_value, "false")
        self.assertIsNone(err)


class CoerceSettingValueIntTests(SimpleTestCase):
    _SPEC = _SettingSpec("k", "f", "int", (5, 100))

    def test_in_range_returns_str_value(self) -> None:
        db_value, err = _coerce_setting_value(self._SPEC, 42)
        self.assertEqual(db_value, "42")
        self.assertIsNone(err)

    def test_below_lo_returns_error(self) -> None:
        db_value, err = _coerce_setting_value(self._SPEC, 4)
        self.assertIsNone(db_value)
        self.assertIsNotNone(err)

    def test_above_hi_returns_error(self) -> None:
        db_value, err = _coerce_setting_value(self._SPEC, 1000)
        self.assertIsNone(db_value)
        self.assertIsNotNone(err)

    def test_non_numeric_string_returns_error(self) -> None:
        db_value, err = _coerce_setting_value(self._SPEC, "not-a-number")
        self.assertIsNone(db_value)
        self.assertIsNotNone(err)

    def test_numeric_string_in_range_accepted(self) -> None:
        db_value, err = _coerce_setting_value(self._SPEC, "42")
        self.assertEqual(db_value, "42")
        self.assertIsNone(err)


class CoerceSettingValueFloatTests(SimpleTestCase):
    _SPEC = _SettingSpec("k", "f", "float", (0.0, 1.0))

    def test_in_range_returns_str_value(self) -> None:
        db_value, err = _coerce_setting_value(self._SPEC, 0.5)
        self.assertEqual(db_value, "0.5")
        self.assertIsNone(err)

    def test_above_hi_returns_error(self) -> None:
        db_value, err = _coerce_setting_value(self._SPEC, 1.5)
        self.assertIsNone(db_value)
        self.assertIsNotNone(err)

    def test_below_lo_returns_error(self) -> None:
        db_value, err = _coerce_setting_value(self._SPEC, -0.1)
        self.assertIsNone(db_value)
        self.assertIsNotNone(err)

    def test_non_numeric_string_returns_error(self) -> None:
        db_value, err = _coerce_setting_value(self._SPEC, "abc")
        self.assertIsNone(db_value)
        self.assertIsNotNone(err)


class CoerceSettingValueUnknownKindTests(SimpleTestCase):
    def test_unknown_kind_raises_value_error(self) -> None:
        bad_spec = _SettingSpec("k", "f", "octopus")
        with self.assertRaises(ValueError):
            _coerce_setting_value(bad_spec, "anything")


# ---------------------------------------------------------------------------
# _validate_cooccurrence_settings — full validator
# ---------------------------------------------------------------------------


class ValidateCooccurrenceSettingsEmptyDataTests(SimpleTestCase):
    def test_empty_dict_returns_no_writes_no_errors(self) -> None:
        writes, errors = _validate_cooccurrence_settings({})
        self.assertEqual(writes, [])
        self.assertEqual(errors, {})

    def test_explicit_none_values_are_skipped(self) -> None:
        data = {field: None for _, field, _, _ in _materialise_specs()}
        writes, errors = _validate_cooccurrence_settings(data)
        self.assertEqual(writes, [])
        self.assertEqual(errors, {})


class ValidateCooccurrenceSettingsHappyPathTests(SimpleTestCase):
    def test_all_eight_fields_valid_yields_eight_writes(self) -> None:
        data = {
            "cooccurrence_enabled": True,
            "data_window_days": 90,
            "min_co_session_count": 5,
            "min_jaccard": 0.05,
            "hub_min_jaccard": 0.15,
            "hub_min_members": 3,
            "hub_detection_enabled": True,
            "schedule_weekly": True,
        }
        writes, errors = _validate_cooccurrence_settings(data)
        self.assertEqual(len(writes), 8)
        self.assertEqual(errors, {})

    def test_writes_carry_correct_keys_and_types(self) -> None:
        data = {"data_window_days": 30, "min_jaccard": 0.1}
        writes, _errors = _validate_cooccurrence_settings(data)
        keys = {w[0] for w in writes}
        self.assertIn("cooccurrence.data_window_days", keys)
        self.assertIn("cooccurrence.min_jaccard", keys)
        # Each write tuple is (key, db_value, value_type)
        types = {w[0]: w[2] for w in writes}
        self.assertEqual(types["cooccurrence.data_window_days"], "int")
        self.assertEqual(types["cooccurrence.min_jaccard"], "float")


class ValidateCooccurrenceSettingsErrorPathsTests(SimpleTestCase):
    def test_one_invalid_int_does_not_block_other_writes(self) -> None:
        # Bug fix 2026-05-04 contract preserved: partial-persist + error-collect.
        data = {
            "data_window_days": 5,  # below lo=7 → error
            "min_co_session_count": 5,  # valid
            "cooccurrence_enabled": True,  # valid bool
        }
        writes, errors = _validate_cooccurrence_settings(data)
        self.assertIn("data_window_days", errors)
        write_keys = {w[0] for w in writes}
        self.assertIn("cooccurrence.min_co_session_count", write_keys)
        self.assertIn("cooccurrence.enabled", write_keys)
        self.assertNotIn("cooccurrence.data_window_days", write_keys)

    def test_invalid_int_and_invalid_float_both_reported(self) -> None:
        data = {
            "data_window_days": 99999,  # above hi=365
            "min_jaccard": -0.5,  # below lo=0.0
        }
        _writes, errors = _validate_cooccurrence_settings(data)
        self.assertIn("data_window_days", errors)
        self.assertIn("min_jaccard", errors)

    def test_invalid_field_does_not_lose_other_valid_fields(self) -> None:
        data = {
            "min_jaccard": 2.0,  # above hi=1.0 → error
            "schedule_weekly": False,  # valid
        }
        writes, errors = _validate_cooccurrence_settings(data)
        self.assertIn("min_jaccard", errors)
        write_keys = {w[0] for w in writes}
        self.assertIn("cooccurrence.schedule_weekly", write_keys)


class ValidateCooccurrenceSettingsBoolCoercionTests(SimpleTestCase):
    def test_python_false_persists_as_string_false(self) -> None:
        writes, _errors = _validate_cooccurrence_settings(
            {"cooccurrence_enabled": False}
        )
        # bool kind: False → "false"
        bool_writes = [w for w in writes if w[2] == "bool"]
        self.assertEqual(bool_writes[0][1], "false")

    def test_python_true_persists_as_string_true(self) -> None:
        writes, _errors = _validate_cooccurrence_settings(
            {"cooccurrence_enabled": True}
        )
        bool_writes = [w for w in writes if w[2] == "bool"]
        self.assertEqual(bool_writes[0][1], "true")


class ValidateCooccurrenceSettingsSchemaCompletenessTests(SimpleTestCase):
    """Guard against drift between the spec table and the GET endpoint's
    response shape — every persistable field must also appear as a key in
    ``DEFAULT_COOCCURRENCE_SETTINGS``."""

    def test_every_spec_field_is_a_default_setting_key(self) -> None:
        spec_fields = {spec.field for spec in _COOCCURRENCE_SETTING_SPECS}
        default_keys = set(DEFAULT_COOCCURRENCE_SETTINGS.keys())
        self.assertTrue(
            spec_fields.issubset(default_keys),
            f"Specs without defaults: {spec_fields - default_keys}",
        )

    def test_spec_count_matches_default_count(self) -> None:
        self.assertEqual(
            len(_COOCCURRENCE_SETTING_SPECS), len(DEFAULT_COOCCURRENCE_SETTINGS)
        )

    def test_int_and_float_specs_have_bounds(self) -> None:
        for spec in _COOCCURRENCE_SETTING_SPECS:
            if spec.kind in ("int", "float"):
                self.assertIsNotNone(
                    spec.bounds, f"spec {spec.field} ({spec.kind}) missing bounds"
                )

    def test_bool_specs_have_no_bounds(self) -> None:
        for spec in _COOCCURRENCE_SETTING_SPECS:
            if spec.kind == "bool":
                self.assertIsNone(spec.bounds)


# ---------------------------------------------------------------------------
# Helpers used inside this test module only
# ---------------------------------------------------------------------------


def _materialise_specs():
    """Yield (key, field, kind, bounds) tuples — convenience for None-fill tests."""
    for spec in _COOCCURRENCE_SETTING_SPECS:
        yield spec.key, spec.field, spec.kind, spec.bounds
