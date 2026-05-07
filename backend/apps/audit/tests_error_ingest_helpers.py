"""SimpleTestCase + TestCase coverage for the helpers in apps.audit.error_ingest.

Pure helpers (`_compute_fingerprint`, `_gather_context`, `_emit_ops_feed`)
run in SimpleTestCase — no DB, no Docker. DB helpers (`_bump_existing`,
`_create_new`, `_dedup_or_create`, `_recover_race`) need TestCase for
transaction support but use minimal fixtures. The orchestrator class
verifies that `ingest_error` glues the helpers together correctly and
always emits the ops-feed event regardless of which branch returns.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

from django.db import IntegrityError
from django.test import SimpleTestCase, TestCase

from apps.audit.error_ingest import (
    _bump_existing,
    _compute_fingerprint,
    _create_new,
    _dedup_or_create,
    _emit_ops_feed,
    _ErrorPayload,
    _gather_context,
    _recover_race,
    ingest_error,
)
from apps.audit.models import ErrorLog
from apps.audit.runtime_context import local_node_identity


def _make_payload(**overrides) -> _ErrorPayload:
    """Build an _ErrorPayload with sensible defaults; override per-test."""
    base = {
        "job_type": "pipeline",
        "step": "score",
        "error_message": "boom",
        "raw_exception": "Traceback ...",
        "why": "test why",
        "severity": ErrorLog.SEVERITY_MEDIUM,
    }
    base.update(overrides)
    return _ErrorPayload(**base)


# ───────────────── Pure helpers (SimpleTestCase, no DB) ─────────────────


class ComputeFingerprintTests(SimpleTestCase):
    """SHA1 over (job_type | step | normalize(msg)). Normaliser collapses
    digit-runs (>=2), hex blobs (>=8 hex chars), UNIX paths, and 0x
    pointer addresses into a literal `*` so messages that only differ in
    ephemeral values land on the same hash."""

    def test_normalises_2plus_digit_runs(self):
        fp1 = _compute_fingerprint("job", "step", "task 12 failed")
        fp2 = _compute_fingerprint("job", "step", "task 999 failed")
        self.assertEqual(fp1, fp2)

    def test_single_digit_not_normalised(self):
        # The pattern is `\d{2,}` so a lone digit is preserved.
        fp1 = _compute_fingerprint("job", "step", "retry 1")
        fp2 = _compute_fingerprint("job", "step", "retry 9")
        self.assertNotEqual(fp1, fp2)

    def test_normalises_unix_paths(self):
        fp1 = _compute_fingerprint("job", "step", "open /tmp/abc/def.log")
        fp2 = _compute_fingerprint("job", "step", "open /var/log/some.log")
        self.assertEqual(fp1, fp2)

    def test_normalises_hex_blobs(self):
        fp1 = _compute_fingerprint("job", "step", "uuid deadbeef1234 mismatch")
        fp2 = _compute_fingerprint("job", "step", "uuid cafebabe5678 mismatch")
        self.assertEqual(fp1, fp2)

    def test_normalises_0x_pointers(self):
        fp1 = _compute_fingerprint("job", "step", "segfault at 0xdeadbeef")
        fp2 = _compute_fingerprint("job", "step", "segfault at 0xcafe1234")
        self.assertEqual(fp1, fp2)

    def test_dedup_canonical_example(self):
        # The example from the module docstring.
        fp1 = _compute_fingerprint("import", "fetch", "task 123 failed at /tmp/abc")
        fp2 = _compute_fingerprint("import", "fetch", "task 456 failed at /tmp/def")
        self.assertEqual(fp1, fp2)

    def test_different_job_types_yield_different_fingerprints(self):
        fp1 = _compute_fingerprint("import", "fetch", "boom")
        fp2 = _compute_fingerprint("embed", "fetch", "boom")
        self.assertNotEqual(fp1, fp2)

    def test_empty_message_handled(self):
        # The `or ""` guard means None never reaches re.sub.
        fp = _compute_fingerprint("job", "step", "")
        self.assertEqual(len(fp), 40)


class LocalNodeIdentityTests(SimpleTestCase):
    """Single-source-of-truth helper for ``(node_id, node_role)``.

    Replaces the previously duplicated 2-line env-read+fallback pattern
    that lived in three sites: error_ingest, runtime_context.snapshot,
    and diagnostics views NodesView.
    """

    def test_uses_env_overrides(self):
        with patch.dict(
            os.environ,
            {"NODE_ID": "node-A", "NODE_ROLE": "worker"},
            clear=False,
        ):
            self.assertEqual(local_node_identity(), ("node-A", "worker"))

    @patch("apps.audit.runtime_context.socket.gethostname", return_value="host-X")
    def test_falls_back_to_hostname_and_primary(self, _mock_hostname):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(local_node_identity(), ("host-X", "primary"))


class GatherContextTests(SimpleTestCase):
    """Bundles fingerprint + node identity + runtime snapshot for callers."""

    @patch("apps.audit.error_ingest.runtime_snapshot", return_value={"k": "v"})
    def test_uses_env_overrides(self, _mock_snapshot):
        with patch.dict(
            os.environ,
            {"NODE_ID": "node-A", "NODE_ROLE": "worker"},
            clear=False,
        ):
            fp, node_id, node_role, ctx = _gather_context("job", "step", "msg")
        self.assertEqual(node_id, "node-A")
        self.assertEqual(node_role, "worker")
        self.assertEqual(ctx, {"k": "v"})
        self.assertEqual(len(fp), 40)

    @patch("apps.audit.error_ingest.runtime_snapshot", return_value={})
    @patch("apps.audit.runtime_context.socket.gethostname", return_value="host-fallback")
    def test_falls_back_to_hostname_and_primary_role(
        self, _mock_hostname, _mock_snapshot
    ):
        # Strip both env vars so the defaults fire (the helper reads
        # ``socket.gethostname`` for node_id and the literal "primary"
        # for node_role).
        with patch.dict(os.environ, {}, clear=True):
            _fp, node_id, node_role, _ctx = _gather_context("job", "step", "msg")
        self.assertEqual(node_id, "host-fallback")
        self.assertEqual(node_role, ErrorLog.NODE_ROLE_PRIMARY)

    @patch("apps.audit.error_ingest.runtime_snapshot", return_value={"runtime": "ok"})
    def test_returns_4tuple_with_fingerprint_first(self, _mock_snapshot):
        result = _gather_context("import", "fetch", "boom")
        self.assertEqual(len(result), 4)
        self.assertEqual(result[0], _compute_fingerprint("import", "fetch", "boom"))


class EmitOpsFeedTests(SimpleTestCase):
    """Severity mapping + None-row no-op + downstream-failure swallowing."""

    def test_no_op_on_none_row(self):
        # No exception should be raised; nothing patched because the
        # function returns at the `if row is None` guard.
        self.assertIsNone(_emit_ops_feed(None))

    def _make_row(self, **overrides) -> MagicMock:
        row = MagicMock(spec=ErrorLog)
        row.pk = 42
        row.job_type = "pipeline"
        row.error_message = "boom"
        row.how_to_fix = "restart redis"
        row.severity = ErrorLog.SEVERITY_MEDIUM
        row.runtime_context = {"node_id": "primary"}
        for k, v in overrides.items():
            setattr(row, k, v)
        return row

    @patch("apps.ops_feed.services.emit")
    def test_critical_severity_maps_to_error(self, mock_emit):
        row = self._make_row(severity=ErrorLog.SEVERITY_CRITICAL)
        _emit_ops_feed(row)
        mock_emit.assert_called_once()
        self.assertEqual(mock_emit.call_args.kwargs["severity"], "error")

    @patch("apps.ops_feed.services.emit")
    def test_high_severity_maps_to_error(self, mock_emit):
        row = self._make_row(severity=ErrorLog.SEVERITY_HIGH)
        _emit_ops_feed(row)
        self.assertEqual(mock_emit.call_args.kwargs["severity"], "error")

    @patch("apps.ops_feed.services.emit")
    def test_medium_severity_maps_to_warning(self, mock_emit):
        row = self._make_row(severity=ErrorLog.SEVERITY_MEDIUM)
        _emit_ops_feed(row)
        self.assertEqual(mock_emit.call_args.kwargs["severity"], "warning")

    @patch("apps.ops_feed.services.emit", side_effect=Exception("ops_feed down"))
    def test_swallows_downstream_failures(self, _mock_emit):
        # Contract: ops-feed emission can never break error ingestion.
        # If _emit_ops_feed leaks the exception, the test framework
        # surfaces it as an error and this assertion is irrelevant —
        # the bare call is the actual test.
        row = self._make_row()
        self.assertIsNone(_emit_ops_feed(row))


# ───────────────────── DB helpers (TestCase) ─────────────────────


class BumpExistingTests(TestCase):
    """Mutate-in-place: bump count, regression-reopen, refresh raw/sev/ctx."""

    def _create_target(self, **overrides) -> ErrorLog:
        base = {
            "source": ErrorLog.SOURCE_INTERNAL,
            "job_type": "pipeline",
            "step": "score",
            "error_message": "boom",
            "raw_exception": "old traceback",
            "fingerprint": "f" * 40,
            "severity": ErrorLog.SEVERITY_LOW,
            "node_id": "node-A",
            "node_role": ErrorLog.NODE_ROLE_PRIMARY,
            "occurrence_count": 1,
            "acknowledged": False,
            "runtime_context": {"old": "ctx"},
        }
        base.update(overrides)
        return ErrorLog.objects.create(**base)

    def test_bumps_count_and_returns_same_row(self):
        target = self._create_target()
        result = _bump_existing(target, "new traceback", ErrorLog.SEVERITY_HIGH, {"new": "ctx"})
        self.assertEqual(result.pk, target.pk)
        target.refresh_from_db()
        self.assertEqual(target.occurrence_count, 2)

    def test_resets_acknowledged_for_regression_reopen(self):
        target = self._create_target(acknowledged=True)
        _bump_existing(target, "tb", ErrorLog.SEVERITY_HIGH, {})
        target.refresh_from_db()
        self.assertFalse(target.acknowledged)

    def test_overwrites_severity_and_ctx_but_keeps_old_raw_when_blank(self):
        target = self._create_target()
        _bump_existing(target, "", ErrorLog.SEVERITY_CRITICAL, {"new": "ctx"})
        target.refresh_from_db()
        self.assertEqual(target.severity, ErrorLog.SEVERITY_CRITICAL)
        self.assertEqual(target.runtime_context, {"new": "ctx"})
        # Empty raw_exception is treated as "no update" so we keep the
        # previous traceback rather than overwriting useful debug data.
        self.assertEqual(target.raw_exception, "old traceback")


class CreateNewTests(TestCase):
    """Insert path with size-bounded fields and how_to_fix lookup."""

    def test_inserts_row_with_all_fields_populated(self):
        payload = _make_payload(error_message="brand new error")
        row = _create_new("a" * 40, "node-A", "primary", {"runtime": "ok"}, payload)
        self.assertEqual(row.fingerprint, "a" * 40)
        self.assertEqual(row.node_id, "node-A")
        self.assertEqual(row.node_role, "primary")
        self.assertEqual(row.runtime_context, {"runtime": "ok"})
        self.assertEqual(row.source, ErrorLog.SOURCE_INTERNAL)
        self.assertTrue(row.how_to_fix)  # at least the generic hint
        self.assertEqual(row.occurrence_count, 1)

    def test_truncates_oversized_field_inputs(self):
        payload = _make_payload(
            job_type="x" * 200,
            step="y" * 500,
            error_message="z" * 9000,
        )
        row = _create_new("b" * 40, "node-A", "primary", {}, payload)
        self.assertEqual(len(row.job_type), 50)
        self.assertEqual(len(row.step), 100)
        self.assertEqual(len(row.error_message), 4000)

    def test_persists_fix_suggestion_from_suggest(self):
        payload = _make_payload(error_message="CUDA out of memory")
        row = _create_new("c" * 40, "node-A", "primary", {}, payload)
        self.assertIn("VRAM", row.how_to_fix)


class DedupOrCreateTests(TestCase):
    """Bump-existing-or-insert-new under transaction.atomic. Public surface
    callers always go through `ingest_error`; these tests pin the helper's
    direct contract so a future refactor can't drift the dedup invariant."""

    def _kwargs(self, **overrides) -> dict:
        kw = {
            "fp": "d" * 40,
            "node_id": "node-test",
            "node_role": ErrorLog.NODE_ROLE_PRIMARY,
            "ctx": {"runtime": "test"},
            "payload": _make_payload(),
        }
        kw.update(overrides)
        return kw

    def test_creates_new_row_when_no_existing(self):
        kw = self._kwargs()
        row = _dedup_or_create(**kw)
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row.fingerprint, kw["fp"])
        self.assertEqual(row.occurrence_count, 1)

    def test_bumps_existing_row_with_same_fp_and_node(self):
        kw = self._kwargs()
        first = _dedup_or_create(**kw)
        assert first is not None
        second = _dedup_or_create(**kw)
        assert second is not None
        self.assertEqual(first.pk, second.pk)
        second.refresh_from_db()
        self.assertEqual(second.occurrence_count, 2)

    def test_integrity_error_falls_back_to_recover_race(self):
        # Pre-create a row so _recover_race has something to find.
        kw = self._kwargs()
        first = _dedup_or_create(**kw)
        assert first is not None

        # Force the SELECT-FOR-UPDATE to raise IntegrityError so the
        # except branch fires; verify _recover_race is the fallback path.
        with patch(
            "apps.audit.error_ingest.ErrorLog.objects.select_for_update"
        ) as mock_sfu:
            mock_sfu.side_effect = IntegrityError("simulated race")
            recovered = _dedup_or_create(**kw)
        assert recovered is not None
        self.assertEqual(recovered.pk, first.pk)
        recovered.refresh_from_db()
        self.assertEqual(recovered.occurrence_count, 2)


class RecoverRaceTests(TestCase):
    """The IntegrityError race-recovery branch — narrow because the DB
    filter is the only operation; everything else is bookkeeping."""

    def _create_target_row(self, fp: str = "e" * 40, node_id: str = "node-A"):
        return ErrorLog.objects.create(
            source=ErrorLog.SOURCE_INTERNAL,
            job_type="pipeline",
            step="score",
            error_message="boom",
            fingerprint=fp,
            severity=ErrorLog.SEVERITY_MEDIUM,
            node_id=node_id,
            node_role=ErrorLog.NODE_ROLE_PRIMARY,
        )

    def test_returns_existing_row_after_race(self):
        target = self._create_target_row()
        original_count = target.occurrence_count

        recovered = _recover_race(target.fingerprint, target.node_id)
        assert recovered is not None
        self.assertEqual(recovered.pk, target.pk)
        recovered.refresh_from_db()
        self.assertEqual(recovered.occurrence_count, original_count + 1)

    def test_resets_acknowledged_when_recovering(self):
        target = self._create_target_row()
        target.acknowledged = True
        target.save(update_fields=["acknowledged"])

        recovered = _recover_race(target.fingerprint, target.node_id)
        assert recovered is not None
        recovered.refresh_from_db()
        self.assertFalse(recovered.acknowledged)

    def test_returns_none_when_no_row_matches(self):
        result = _recover_race("9" * 40, "ghost-node")
        self.assertIsNone(result)

    def test_logs_and_returns_none_on_db_failure(self):
        with patch(
            "apps.audit.error_ingest.ErrorLog.objects.filter",
            side_effect=Exception("db down"),
        ):
            result = _recover_race("e" * 40, "node-A")
        self.assertIsNone(result)


# ───────────────── Orchestrator integration ─────────────────


class IngestErrorOrchestratorTests(TestCase):
    """End-to-end glue: confirm `ingest_error` calls the right helpers and
    always emits the ops-feed event regardless of which branch produced
    the row (including the failure branches)."""

    @patch("apps.audit.error_ingest._emit_ops_feed")
    def test_emits_ops_feed_on_successful_create(self, mock_emit):
        row = ingest_error(
            job_type="pipeline", step="score", error_message="orchestrator boom"
        )
        self.assertIsNotNone(row)
        mock_emit.assert_called_once_with(row)

    @patch("apps.audit.error_ingest._emit_ops_feed")
    @patch(
        "apps.audit.error_ingest._gather_context",
        side_effect=RuntimeError("simulated boom"),
    )
    def test_swallows_unexpected_failure_and_emits_with_none(
        self, _mock_gather, mock_emit
    ):
        row = ingest_error(
            job_type="pipeline", step="score", error_message="anything"
        )
        self.assertIsNone(row)
        mock_emit.assert_called_once_with(None)

    @patch("apps.audit.error_ingest._emit_ops_feed")
    @patch("apps.audit.error_ingest._dedup_or_create", return_value=None)
    def test_emits_even_when_dedup_returns_none(self, _mock_dedup, mock_emit):
        row = ingest_error(
            job_type="pipeline", step="score", error_message="anything"
        )
        self.assertIsNone(row)
        mock_emit.assert_called_once_with(None)
