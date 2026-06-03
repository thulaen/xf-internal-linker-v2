"""Convention SimpleTestCase coverage for the FAISS-index health check.

After GPU/CUDA removal the check is `check_faiss_index_health` (formerly
`check_gpu_faiss_health`). It now reports a CPU-only vector index: no
`cuda_available`, no VRAM, no GPU device wording. These tests run with no
DB and a mocked `get_faiss_status`, pinning the post-removal metadata
shape and status wording with exact-value asserts.
"""

from __future__ import annotations

from unittest.mock import patch

from django.test import SimpleTestCase

from apps.health.models import ServiceHealthRecord
from apps.health.services import (
    HealthCheckRegistry,
    _build_faiss_metadata,
    _classify_faiss_state,
    check_faiss_index_health,
)


class FaissRegistryMetadataTests(SimpleTestCase):
    """Pin the registered name/description after GPU/CUDA removal.

    The decorator changed the service key to ``faiss_index`` and rewrote the
    human-facing name + description to drop all GPU/CUDA wording. These exact
    assertEquals kill the string mutants mutmut would otherwise keep alive on
    the two changed decorator-argument lines.
    """

    def test_when_registered_then_key_is_faiss_index(self):
        self.assertIn("faiss_index", HealthCheckRegistry.get_checkers())
        self.assertNotIn("gpu_faiss", HealthCheckRegistry.get_checkers())

    def test_when_metadata_read_then_exact_name(self):
        meta = HealthCheckRegistry.get_metadata("faiss_index")
        self.assertEqual(meta["name"], "FAISS Index")

    def test_when_metadata_read_then_exact_description(self):
        meta = HealthCheckRegistry.get_metadata("faiss_index")
        self.assertEqual(
            meta["description"],
            "Persistent CPU FAISS vector index for Stage 1 pipeline search.",
        )
        self.assertNotIn("GPU", meta["description"])
        self.assertNotIn("CUDA", meta["description"])


class BuildFaissMetadataTests(SimpleTestCase):
    """Pure flatten of the faiss_status dict — no GPU/VRAM keys anymore."""

    def test_when_full_status_then_three_keys_only(self):
        meta = _build_faiss_metadata(
            {"active": True, "device": "cpu", "vectors": 4200, "vram_mb": 999}
        )
        self.assertEqual(
            meta,
            {"faiss_active": True, "faiss_device": "cpu", "faiss_vectors": 4200},
        )

    def test_when_empty_status_then_safe_defaults(self):
        meta = _build_faiss_metadata({})
        self.assertEqual(
            meta,
            {"faiss_active": False, "faiss_device": "none", "faiss_vectors": 0},
        )

    def test_when_built_then_no_cuda_key(self):
        meta = _build_faiss_metadata({"active": True, "device": "cpu", "vectors": 1})
        self.assertNotIn("cuda_available", meta)
        self.assertNotIn("vram_total_mb", meta)


class ClassifyFaissStateTests(SimpleTestCase):
    """Two branches only now: not-loaded (warning) and active (healthy)."""

    def test_when_not_active_then_warning_not_loaded(self):
        meta = {"faiss_active": False, "faiss_device": "none", "faiss_vectors": 0}
        decision = _classify_faiss_state(meta)
        self.assertEqual(decision["status"], ServiceHealthRecord.STATUS_WARNING)
        self.assertEqual(decision["label"], "FAISS index not loaded.")
        self.assertFalse(decision["success"])

    def test_when_active_then_healthy_with_vector_count_label(self):
        meta = {"faiss_active": True, "faiss_device": "cpu", "faiss_vectors": 12345}
        decision = _classify_faiss_state(meta)
        self.assertEqual(decision["status"], ServiceHealthRecord.STATUS_HEALTHY)
        self.assertEqual(decision["label"], "FAISS active (12,345 vectors).")
        self.assertEqual(decision["fix"], "No action needed.")
        self.assertTrue(decision["success"])

    def test_when_active_then_no_gpu_wording(self):
        meta = {"faiss_active": True, "faiss_device": "cpu", "faiss_vectors": 7}
        decision = _classify_faiss_state(meta)
        self.assertNotIn("GPU", decision["label"])
        self.assertNotIn("VRAM", decision["label"])


class CheckFaissIndexHealthTests(SimpleTestCase):
    """End-to-end: get_faiss_status mocked, no DB write (result is a dataclass)."""

    @patch("apps.pipeline.services.faiss_index.get_faiss_status")
    def test_when_index_active_then_healthy_result(self, mock_status):
        mock_status.return_value = {"active": True, "device": "cpu", "vectors": 500}
        result = check_faiss_index_health()
        self.assertEqual(result.service_key, "faiss_index")
        self.assertEqual(result.status, ServiceHealthRecord.STATUS_HEALTHY)
        self.assertEqual(result.metadata["faiss_vectors"], 500)

    @patch("apps.pipeline.services.faiss_index.get_faiss_status")
    def test_when_status_raises_then_check_failed_result(self, mock_status):
        mock_status.side_effect = RuntimeError("faiss import boom")
        result = check_faiss_index_health()
        self.assertEqual(result.service_key, "faiss_index")
        self.assertEqual(result.status, ServiceHealthRecord.STATUS_ERROR)
        self.assertEqual(result.status_label, "FAISS check failed.")
        # Exact failure-fix copy after GPU removal — pins the changed string so
        # mutmut cannot keep a wrapped-literal mutant alive on this line.
        self.assertEqual(
            result.suggested_fix,
            "Ensure faiss-cpu is installed in the backend container.",
        )
        self.assertNotIn("faiss-gpu", result.suggested_fix)


class FaissRegisteredCheckerZeroArgTests(SimpleTestCase):
    """Regression for AutoIssue #20221 — the registered checker must be callable
    with zero args.

    ``perform_health_check`` / ``run_all_health_checks`` invoke every registered
    checker as ``checker()`` with no arguments. The ``faiss_index`` decorator was
    on the pure helper ``_build_faiss_metadata(faiss_status)`` which *requires* an
    argument, so a zero-arg call raised ``TypeError: _build_faiss_metadata()
    missing 1 required positional argument: 'faiss_status'`` at runtime. The
    decorator belongs on ``check_faiss_index_health`` (the real zero-arg entry
    point). These tests pin that the registered callable takes zero args and
    returns a ``ServiceHealthResult``.
    """

    @patch("apps.pipeline.services.faiss_index.get_faiss_status")
    def test_when_registered_checker_called_zero_arg_then_no_typeerror(
        self, mock_status
    ):
        mock_status.return_value = {"active": True, "device": "cpu", "vectors": 9}
        checker = HealthCheckRegistry.get_checkers()["faiss_index"]
        result = checker()  # zero-arg call — the live crash path
        self.assertEqual(result.service_key, "faiss_index")
        self.assertEqual(result.status, ServiceHealthRecord.STATUS_HEALTHY)

    def test_when_registered_checker_then_it_is_check_faiss_index_health(self):
        checker = HealthCheckRegistry.get_checkers()["faiss_index"]
        self.assertIs(checker, check_faiss_index_health)
