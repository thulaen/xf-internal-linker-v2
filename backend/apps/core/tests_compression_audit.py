"""Tests for ``apps.core.services.compression_audit`` (Phase 4.9).

The most important test in this file is
``CandidateColumnNamesValidTests`` — it pins the curated list of
(model, column) tuples against the live model schemas. Three wrong
column names shipped during the original Phase 4.9 commit and were
caught only by an interactive smoke test; this regression test
catches the same class of bug at unit-test time.

The compression-math tests use synthetic in-memory bytes so they're
deterministic + fast (no DB seed required).
"""

from __future__ import annotations

import json
import zlib
from importlib import import_module
from unittest.mock import patch

from django.core.exceptions import FieldError
from django.test import SimpleTestCase, TestCase

from apps.core.models import AppSetting
from apps.core.services import compression_audit as ca


class CandidateColumnNamesValidTests(TestCase):
    """Pin every entry in ``_CANDIDATES`` against the live model schema.

    This catches the wrong-column-name class of bug (3 such bugs shipped
    in the original 4.9 commit; each silently produced 0 candidates for
    its table because the audit's defensive design swallowed FieldError).
    """

    def test_every_candidate_resolves_to_real_columns(self) -> None:
        for dotted_name, columns, label, _notes in ca._CANDIDATES:
            with self.subTest(table=label):
                module_path, _, class_name = dotted_name.rpartition(".")
                module = import_module(module_path)
                model_class = getattr(module, class_name, None)
                self.assertIsNotNone(
                    model_class,
                    f"Could not import {dotted_name}",
                )
                # Issue a 0-row .values(*columns) query — Django raises
                # FieldError if any column name is wrong, even on an
                # empty table. Cheap + definitive.
                try:
                    list(model_class.objects.values(*columns)[:0])
                except FieldError as exc:  # pragma: no cover — diagnostic message
                    self.fail(
                        f"{dotted_name} candidate references a non-existent "
                        f"column. Detail: {exc}"
                    )


class ValueToBytesTests(SimpleTestCase):
    """Pure function — no DB needed."""

    def test_none(self) -> None:
        self.assertEqual(ca._value_to_bytes(None), b"")

    def test_bytes_passthrough(self) -> None:
        self.assertEqual(ca._value_to_bytes(b"hello"), b"hello")

    def test_bytearray_converted(self) -> None:
        self.assertEqual(ca._value_to_bytes(bytearray(b"hi")), b"hi")

    def test_memoryview_converted(self) -> None:
        self.assertEqual(ca._value_to_bytes(memoryview(b"abc")), b"abc")

    def test_string_utf8(self) -> None:
        self.assertEqual(
            ca._value_to_bytes("héllo"), "héllo".encode("utf-8")
        )

    def test_dict_via_json(self) -> None:
        result = ca._value_to_bytes({"a": 1, "b": "two"})
        # Order isn't critical for compression — just that it's valid JSON
        self.assertEqual(json.loads(result), {"a": 1, "b": "two"})

    def test_list_via_json(self) -> None:
        result = ca._value_to_bytes([1, 2, "three"])
        self.assertEqual(json.loads(result), [1, 2, "three"])

    def test_int(self) -> None:
        self.assertEqual(ca._value_to_bytes(42), b"42")

    def test_float(self) -> None:
        self.assertEqual(ca._value_to_bytes(3.14), b"3.14")

    def test_unhashable_dict_falls_back_to_repr(self) -> None:
        """JSON.dumps fails on non-serialisable values — fallback should
        not crash the audit row."""

        class Weird:
            def __repr__(self) -> str:
                return "<weird>"

        # JSON-encoding a dict containing Weird raises TypeError; we want
        # the fallback to repr instead of propagating.
        result = ca._value_to_bytes({"a": Weird()})
        self.assertIn(b"<weird>", result)


class MeasureRowTests(SimpleTestCase):
    """Compression-ratio math is deterministic — exercise it directly."""

    def test_empty_row_returns_zero(self) -> None:
        raw, compressed = ca._measure_row({}, ("col",))
        self.assertEqual((raw, compressed), (0, 0))

    def test_compression_actually_compresses_repeating_data(self) -> None:
        # 1 KB of repeated bytes — should compress to ~10-30 bytes.
        long_string = "x" * 1024
        raw, compressed = ca._measure_row(
            {"col": long_string}, ("col",)
        )
        self.assertEqual(raw, 1024)
        # zlib should reduce 1 KB of "x" to under 50 bytes
        self.assertLess(compressed, 50)

    def test_random_data_barely_compresses(self) -> None:
        # zlib + truly random bytes ≈ 1.0 ratio (no compression possible)
        import os

        random_bytes = os.urandom(1024)
        raw, compressed = ca._measure_row(
            {"col": random_bytes}, ("col",)
        )
        self.assertEqual(raw, 1024)
        # Random data should compress to AT LEAST 95% of original
        self.assertGreater(compressed, 0.9 * raw)

    def test_multiple_columns_concatenated(self) -> None:
        raw, _compressed = ca._measure_row(
            {"a": "hello", "b": "world"}, ("a", "b")
        )
        self.assertEqual(raw, len(b"helloworld"))

    def test_compression_ratio_matches_zlib_ground_truth(self) -> None:
        payload = "hello world " * 100  # 1200 bytes, highly compressible
        ground_truth = len(zlib.compress(payload.encode(), level=6))
        raw, compressed = ca._measure_row({"col": payload}, ("col",))
        self.assertEqual(raw, len(payload.encode()))
        self.assertEqual(compressed, ground_truth)


class RunCompressionAuditTests(TestCase):
    """End-to-end + persistence."""

    def setUp(self) -> None:
        AppSetting.objects.filter(key__startswith="compression_audit.").delete()

    def test_empty_db_produces_empty_report(self) -> None:
        """Audit completes cleanly when every candidate table is empty."""
        # Patch _CANDIDATES to an empty tuple so we exercise the
        # report-build path without depending on real model state.
        with patch.object(ca, "_CANDIDATES", ()):
            report = ca.run_compression_audit(sample_size=100)
        self.assertEqual(report.candidates, [])
        self.assertEqual(report.total_estimated_savings_bytes, 0)
        self.assertIn("0 candidate", report.note)

    def test_report_persisted_to_appsetting(self) -> None:
        with patch.object(ca, "_CANDIDATES", ()):
            report = ca.run_compression_audit(sample_size=100)
        # The single-row + timestamp pattern: NO new tables, just two
        # AppSetting rows.
        report_row = AppSetting.objects.filter(
            key="compression_audit.last_report"
        ).first()
        time_row = AppSetting.objects.filter(
            key="compression_audit.last_run_at"
        ).first()
        self.assertIsNotNone(report_row)
        self.assertIsNotNone(time_row)
        self.assertEqual(time_row.value, report.run_at_iso)

    def test_get_last_report_round_trip(self) -> None:
        with patch.object(ca, "_CANDIDATES", ()):
            ca.run_compression_audit(sample_size=100)
        loaded = ca.get_last_compression_audit()
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.candidates, [])

    def test_get_last_report_returns_none_before_first_run(self) -> None:
        self.assertIsNone(ca.get_last_compression_audit())

    def test_savings_filter_drops_marginal_candidates(self) -> None:
        """Tables with <1 MB projected savings should not make the list."""
        # Build a synthetic candidate that would only save a few KB.
        marginal = ca.CompressionCandidate(
            table_label="tiny table",
            model_dotted_name="x.y.Z",
            columns=("col",),
            rows_sampled=10,
            raw_bytes_per_row_avg=100,
            compressed_bytes_per_row_avg=50,
            compression_ratio=0.5,
            estimated_total_rows=100,
            estimated_savings_bytes=5000,  # 5 KB — well below the 1 MB threshold
        )
        big = ca.CompressionCandidate(
            table_label="big table",
            model_dotted_name="x.y.Z",
            columns=("col",),
            rows_sampled=1000,
            raw_bytes_per_row_avg=2000,
            compressed_bytes_per_row_avg=400,
            compression_ratio=0.2,
            estimated_total_rows=10_000,
            estimated_savings_bytes=16_000_000,  # 16 MB
        )
        # Stub _audit_one_table to return our two synthetic candidates.
        with patch.object(
            ca, "_CANDIDATES", (("a.M", ("c",), "tiny", ""), ("b.M", ("c",), "big", ""))
        ):
            with patch.object(
                ca, "_audit_one_table", side_effect=[marginal, big]
            ):
                report = ca.run_compression_audit(sample_size=10)
        labels = [c.table_label for c in report.candidates]
        self.assertEqual(labels, ["big table"])  # marginal filtered out
        self.assertEqual(report.total_estimated_savings_bytes, 16_000_000)

    def test_top_n_capped_at_ten(self) -> None:
        """If 12 candidates qualify, only top-10 are persisted."""
        big_savings = lambda i: ca.CompressionCandidate(  # noqa: E731
            table_label=f"table_{i}",
            model_dotted_name="x.y.Z",
            columns=("c",),
            rows_sampled=1000,
            raw_bytes_per_row_avg=2000,
            compressed_bytes_per_row_avg=400,
            compression_ratio=0.2,
            estimated_total_rows=10_000,
            estimated_savings_bytes=16_000_000 - i * 10_000,
        )
        candidates = [big_savings(i) for i in range(12)]
        with patch.object(
            ca,
            "_CANDIDATES",
            tuple(("a.M", ("c",), f"t_{i}", "") for i in range(12)),
        ):
            with patch.object(ca, "_audit_one_table", side_effect=candidates):
                report = ca.run_compression_audit(sample_size=10)
        self.assertEqual(len(report.candidates), 10)
        # Sorted by savings descending — first should have the highest
        self.assertEqual(report.candidates[0].table_label, "table_0")


class SampleAndMeasureTests(TestCase):
    """The extracted helper that keeps _audit_one_table under the limit."""

    def test_returns_zero_tuple_on_empty_iter(self) -> None:
        # Patch _sample_rows to return nothing.
        with patch.object(ca, "_sample_rows", return_value=iter([])):
            result = ca._sample_and_measure(
                AppSetting, ("key",), n=10, dotted_name="x.y.Z"
            )
        self.assertEqual(result, (0, 0, 0))

    def test_returns_none_on_iteration_error(self) -> None:
        def explode(*_args, **_kwargs):
            raise RuntimeError("simulated DB error")

        with patch.object(ca, "_sample_rows", side_effect=explode):
            result = ca._sample_and_measure(
                AppSetting, ("key",), n=10, dotted_name="x.y.Z"
            )
        self.assertIsNone(result)

    def test_aggregates_correctly(self) -> None:
        rows = [{"col": "x" * 100}, {"col": "x" * 200}]
        with patch.object(ca, "_sample_rows", return_value=iter(rows)):
            result = ca._sample_and_measure(
                AppSetting, ("col",), n=2, dotted_name="x.y.Z"
            )
        self.assertIsNotNone(result)
        raw_total, _compressed_total, rows_seen = result
        self.assertEqual(raw_total, 300)
        self.assertEqual(rows_seen, 2)


# ── Endpoint security & contract tests ────────────────────────────


class CompressionAuditEndpointSecurityTests(TestCase):
    """Pin the security contract for the two new endpoints.

    The run-now path is expensive (30-120 s of zlib work + DB scans) so
    we restrict it to staff users + a 3/hour throttle. Anonymous and
    non-staff users must get 401/403; over-limit calls must get 429.
    """

    def setUp(self) -> None:
        from django.contrib.auth import get_user_model
        from rest_framework.test import APIClient

        User = get_user_model()
        self.regular_user = User.objects.create_user(
            username="regular", password="pw"
        )
        self.staff_user = User.objects.create_user(
            username="staff", password="pw", is_staff=True
        )
        self.client = APIClient()

    def test_compression_audit_get_requires_auth(self) -> None:
        # No authentication → 401 (or 403, depending on auth scheme order).
        response = self.client.get("/api/system/compression-audit/")
        self.assertIn(response.status_code, (401, 403))

    def test_compression_audit_get_allows_regular_user(self) -> None:
        # Read-only summary is safe for any authenticated user.
        self.client.force_authenticate(user=self.regular_user)
        response = self.client.get("/api/system/compression-audit/")
        self.assertEqual(response.status_code, 200)

    def test_compression_audit_run_requires_auth(self) -> None:
        response = self.client.post("/api/system/compression-audit/run/")
        self.assertIn(response.status_code, (401, 403))

    def test_compression_audit_run_rejects_non_staff(self) -> None:
        # Regular authenticated user must NOT be able to trigger the
        # synchronous expensive path — security tightening landed
        # because the original commit allowed any authenticated token
        # to DoS the worker pool.
        self.client.force_authenticate(user=self.regular_user)
        response = self.client.post("/api/system/compression-audit/run/")
        self.assertEqual(response.status_code, 403)

    def test_compression_audit_run_allows_staff(self) -> None:
        # Patch _CANDIDATES → empty so the request returns instantly.
        self.client.force_authenticate(user=self.staff_user)
        with patch.object(ca, "_CANDIDATES", ()):
            response = self.client.post("/api/system/compression-audit/run/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("candidates", response.data)
        self.assertEqual(response.data["candidates"], [])


class CompressionAuditViewContractTests(TestCase):
    """Pin the JSON-shape contract the frontend relies on."""

    def setUp(self) -> None:
        from django.contrib.auth import get_user_model
        from rest_framework.test import APIClient

        User = get_user_model()
        self.user = User.objects.create_user(username="u", password="pw")
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        AppSetting.objects.filter(key__startswith="compression_audit.").delete()

    def test_get_before_first_run_returns_helpful_note(self) -> None:
        response = self.client.get("/api/system/compression-audit/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["candidates"], [])
        self.assertEqual(response.data["total_estimated_savings_bytes"], 0)
        self.assertEqual(response.data["total_estimated_savings_mb"], 0)
        self.assertIn("No compression audit has run yet", response.data["note"])

    def test_get_after_run_returns_persisted_payload(self) -> None:
        # Run an empty audit first so a report exists.
        with patch.object(ca, "_CANDIDATES", ()):
            ca.run_compression_audit(sample_size=10)
        response = self.client.get("/api/system/compression-audit/")
        self.assertEqual(response.status_code, 200)
        # Required keys for the frontend
        for key in (
            "run_at_iso",
            "sample_size",
            "candidates",
            "total_estimated_savings_bytes",
            "total_estimated_savings_mb",
            "note",
        ):
            with self.subTest(key=key):
                self.assertIn(key, response.data)

    def test_columns_are_lists_not_tuples(self) -> None:
        """Tuples don't survive JSON serialisation → frontend would crash
        on `response.data.candidates[0].columns.length`. The view must
        explicitly convert."""
        synthetic = ca.CompressionCandidate(
            table_label="t",
            model_dotted_name="x.y.Z",
            columns=("a", "b"),
            rows_sampled=10,
            raw_bytes_per_row_avg=2000.0,
            compressed_bytes_per_row_avg=400.0,
            compression_ratio=0.2,
            estimated_total_rows=10_000,
            estimated_savings_bytes=16_000_000,
        )
        with patch.object(
            ca, "_CANDIDATES", (("a.M", ("c",), "label", ""),)
        ):
            with patch.object(ca, "_audit_one_table", return_value=synthetic):
                ca.run_compression_audit(sample_size=10)
        response = self.client.get("/api/system/compression-audit/")
        self.assertIsInstance(response.data["candidates"][0]["columns"], list)
