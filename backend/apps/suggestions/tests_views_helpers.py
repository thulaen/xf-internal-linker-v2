"""Tests for the pure-function helpers extracted from suggestions/views.py.

These helpers replaced ~400 lines of inlined branching across the 6 long
view methods. Each is independently testable in ``SimpleTestCase`` (no DB)
so a future tweak to a validation rule or status string shows up here
before it ships.
"""

from __future__ import annotations

from unittest import mock

from django.test import SimpleTestCase

from apps.suggestions.views import (
    _apply_meta_query_filters,
    _detect_reviewer_anchor_edit,
    _filter_to_existing_suggestion_ids,
    _meta_row_payload,
    _parse_impression_rows,
    _resolve_meta_status,
    _validate_batch_action_inputs,
    _validate_meta_toggle_inputs,
)


class DetectReviewerAnchorEditTests(SimpleTestCase):
    """``_detect_reviewer_anchor_edit`` flags meaningful operator overrides."""

    def _request(self, **data):
        r = mock.Mock()
        r.data = data
        return r

    def test_no_anchor_edited_field(self):
        was, val = _detect_reviewer_anchor_edit(self._request(), "system phrase")
        self.assertFalse(was)
        self.assertIsNone(val)

    def test_empty_string_not_an_edit(self):
        was, _ = _detect_reviewer_anchor_edit(self._request(anchor_edited=""), "x")
        self.assertFalse(was)

    def test_whitespace_only_not_an_edit(self):
        was, _ = _detect_reviewer_anchor_edit(self._request(anchor_edited="   "), "x")
        self.assertFalse(was)

    def test_same_as_original_not_an_edit(self):
        was, _ = _detect_reviewer_anchor_edit(
            self._request(anchor_edited="same phrase"), "same phrase",
        )
        self.assertFalse(was)

    def test_real_edit_returns_true(self):
        was, val = _detect_reviewer_anchor_edit(
            self._request(anchor_edited="new phrase"), "old phrase",
        )
        self.assertTrue(was)
        self.assertEqual(val, "new phrase")


class ValidateBatchActionInputsTests(SimpleTestCase):
    """``_validate_batch_action_inputs`` enforces action + ids contract."""

    def test_invalid_action_returns_400(self):
        result = _validate_batch_action_inputs("delete", ["id1"])
        self.assertEqual(result.status_code, 400)

    def test_non_list_ids_returns_400(self):
        result = _validate_batch_action_inputs("approve", "not a list")
        self.assertEqual(result.status_code, 400)

    def test_too_many_ids_returns_400(self):
        result = _validate_batch_action_inputs("approve", list(range(501)))
        self.assertEqual(result.status_code, 400)

    def test_empty_ids_returns_400(self):
        result = _validate_batch_action_inputs("approve", [])
        self.assertEqual(result.status_code, 400)

    def test_valid_returns_none(self):
        self.assertIsNone(_validate_batch_action_inputs("approve", ["id1"]))


class ResolveMetaStatusTests(SimpleTestCase):
    """``_resolve_meta_status`` picks the right operator-visible status."""

    def _meta(self, status: str):
        m = mock.Mock()
        m.status = status
        return m

    def test_forward_declared_overrides(self):
        self.assertEqual(
            _resolve_meta_status(self._meta("forward-declared"), enabled_raw="true", enabled=True),
            "disabled-pending-implementation",
        )

    def test_explicit_disable_wins_over_active(self):
        self.assertEqual(
            _resolve_meta_status(self._meta("active"), enabled_raw="false", enabled=False),
            "disabled",
        )

    def test_default_returns_meta_status(self):
        self.assertEqual(
            _resolve_meta_status(self._meta("active"), enabled_raw=None, enabled=True),
            "active",
        )


class MetaRowPayloadTests(SimpleTestCase):
    """``_meta_row_payload`` returns the JSON shape the Settings page expects."""

    def _meta(self, **kwargs):
        defaults = {
            "id": "m1", "meta_code": "P1", "family": "P", "title": "Title",
            "status": "active", "enabled_key": "m1.enabled",
            "weight_key": "m1.weight", "spec_path": "docs/m1.md",
            "cpp_kernel": None, "param_keys": [],
        }
        defaults.update(kwargs)
        m = mock.Mock(**defaults)
        return m

    def test_full_shape(self):
        row = _meta_row_payload(
            self._meta(),
            {"m1.enabled": "true", "m1.weight": "0.05"},
        )
        self.assertEqual(row["id"], "m1")
        self.assertTrue(row["enabled"])
        self.assertEqual(row["weight_value"], "0.05")
        self.assertEqual(row["status"], "active")

    def test_missing_setting_default_disabled_falsy(self):
        row = _meta_row_payload(self._meta(), {})
        self.assertFalse(row["enabled"])
        self.assertIsNone(row["weight_value"])


class ApplyMetaQueryFiltersTests(SimpleTestCase):
    """``_apply_meta_query_filters`` filters by family / status / search."""

    def _rows(self):
        return [
            {"id": "p1.x", "family": "P1", "status": "active", "meta_code": "P1A", "title": "Alpha"},
            {"id": "p2.y", "family": "P2", "status": "active", "meta_code": "P2B", "title": "Beta"},
            {"id": "p3.z", "family": "P3", "status": "disabled", "meta_code": "P3C", "title": "Charlie"},
        ]

    def test_family_filter(self):
        params = {"family": "P1", "status": "", "q": ""}
        rows = _apply_meta_query_filters(self._rows(), params)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], "p1.x")

    def test_status_filter(self):
        params = {"family": "", "status": "disabled", "q": ""}
        rows = _apply_meta_query_filters(self._rows(), params)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], "p3.z")

    def test_query_matches_title_substring(self):
        params = {"family": "", "status": "", "q": "char"}
        rows = _apply_meta_query_filters(self._rows(), params)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], "p3.z")

    def test_query_matches_meta_code(self):
        params = {"family": "", "status": "", "q": "p2b"}
        rows = _apply_meta_query_filters(self._rows(), params)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], "p2.y")


class ValidateMetaToggleInputsTests(SimpleTestCase):
    """``_validate_meta_toggle_inputs`` enforces meta + body contract."""

    def _meta(self, status="active"):
        m = mock.Mock()
        m.status = status
        return m

    def test_unknown_meta_returns_404(self):
        result = _validate_meta_toggle_inputs(None, "x.y", {"enabled": True})
        self.assertEqual(result.status_code, 404)

    def test_forward_declared_returns_400(self):
        result = _validate_meta_toggle_inputs(
            self._meta(status="forward-declared"), "x.y", {"enabled": True},
        )
        self.assertEqual(result.status_code, 400)

    def test_missing_enabled_returns_400(self):
        result = _validate_meta_toggle_inputs(
            self._meta(), "x.y", {},
        )
        self.assertEqual(result.status_code, 400)

    def test_valid_returns_none(self):
        self.assertIsNone(
            _validate_meta_toggle_inputs(self._meta(), "x.y", {"enabled": True}),
        )


class ParseImpressionRowsTests(SimpleTestCase):
    """``_parse_impression_rows`` validates + normalises impression payloads."""

    def test_valid_rows_pass_through(self):
        prepared, ids = _parse_impression_rows([
            {"suggestion_id": "abc", "position": 1, "clicked": True, "dwell_ms": 5000},
        ])
        self.assertEqual(len(prepared), 1)
        self.assertEqual(prepared[0]["dwell_ms"], 5000)
        self.assertIn("abc", ids)

    def test_drops_non_dict_rows(self):
        prepared, _ = _parse_impression_rows(["not a dict", 42])
        self.assertEqual(prepared, [])

    def test_drops_missing_suggestion_id(self):
        prepared, _ = _parse_impression_rows([{"position": 1}])
        self.assertEqual(prepared, [])

    def test_drops_invalid_position(self):
        prepared, _ = _parse_impression_rows([
            {"suggestion_id": "abc", "position": "not-a-number"},
        ])
        self.assertEqual(prepared, [])

    def test_dwell_ms_optional(self):
        prepared, _ = _parse_impression_rows([
            {"suggestion_id": "abc", "position": 1},
        ])
        self.assertEqual(prepared[0]["dwell_ms"], None)

    def test_clicked_default_false(self):
        prepared, _ = _parse_impression_rows([
            {"suggestion_id": "abc", "position": 1},
        ])
        self.assertFalse(prepared[0]["clicked"])

    def test_invalid_dwell_ms_becomes_none(self):
        prepared, _ = _parse_impression_rows([
            {"suggestion_id": "abc", "position": 1, "dwell_ms": "not-a-number"},
        ])
        self.assertEqual(prepared[0]["dwell_ms"], None)
