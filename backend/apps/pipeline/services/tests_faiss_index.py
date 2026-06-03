"""Convention-named SimpleTestCase coverage for services/faiss_index.py.

The GPU branch was removed: ``build_faiss_index`` now always builds a CPU
``IndexFlatIP`` and labels ``device = "CPU"`` with no
``faiss.index_cpu_to_gpu`` / ``faiss.StandardGpuResources`` call. These tests
pin the CPU-only behaviour.

Hang-safe: ``faiss`` is replaced with a MagicMock and the DB query is stubbed,
so no real FAISS library, GPU, or database is touched. ``IndexFlatIP`` is the
first post-setup FAISS call in ``build_faiss_index``; mocking the whole module
keeps every mutant under the runner's time budget.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
from django.test import SimpleTestCase

from apps.pipeline.services import faiss_index


class _FakeQuerySet:
    """Minimal stand-in for the ContentItem.values_list() iterator."""

    def __init__(self, rows: list[tuple]) -> None:
        self._rows = rows

    def __iter__(self):
        return iter(self._rows)


class BuildFaissIndexCpuOnlyTests(SimpleTestCase):
    """build_faiss_index builds a CPU IndexFlatIP and never calls GPU APIs."""

    def setUp(self) -> None:
        faiss_index._faiss_index = None
        faiss_index._faiss_id_map = []
        faiss_index._faiss_content_type_map = []
        self.addCleanup(setattr, faiss_index, "_faiss_index", None)

    def _run_build(self, fake_faiss: MagicMock) -> MagicMock:
        rows = [(7, "post", [1.0, 0.0])]
        fake_qs = _FakeQuerySet(rows)
        with patch.object(faiss_index, "HAS_FAISS", True), patch.object(
            faiss_index, "faiss", fake_faiss
        ), patch.object(
            faiss_index, "get_current_embedding_filter", return_value={}
        ), patch(
            "apps.content.models.ContentItem"
        ) as content_item, patch(
            "apps.pipeline.services.pipeline._coerce_embedding_vector",
            return_value=np.asarray([1.0, 0.0], dtype=np.float32),
        ), patch.object(
            faiss_index, "emit", MagicMock()
        ):
            content_item.objects.filter.return_value.values_list.return_value = fake_qs
            faiss_index.build_faiss_index()
        return fake_faiss

    def test_build_uses_cpu_indexflatip_only(self) -> None:
        fake_faiss = MagicMock()
        self._run_build(fake_faiss)
        fake_faiss.IndexFlatIP.assert_called_once_with(2)
        # GPU branch is gone: these symbols must never be touched.
        fake_faiss.StandardGpuResources.assert_not_called()
        fake_faiss.index_cpu_to_gpu.assert_not_called()

    def test_build_emit_reports_device_cpu_exactly(self) -> None:
        fake_emit = MagicMock()
        fake_faiss = MagicMock()
        with patch.object(faiss_index, "emit", fake_emit):
            with patch.object(faiss_index, "HAS_FAISS", True), patch.object(
                faiss_index, "faiss", fake_faiss
            ), patch.object(
                faiss_index, "get_current_embedding_filter", return_value={}
            ), patch(
                "apps.content.models.ContentItem"
            ) as content_item, patch(
                "apps.pipeline.services.pipeline._coerce_embedding_vector",
                return_value=np.asarray([1.0, 0.0], dtype=np.float32),
            ):
                content_item.objects.filter.return_value.values_list.return_value = (
                    _FakeQuerySet([(7, "post", [1.0, 0.0])])
                )
                faiss_index.build_faiss_index()
        ready_calls = [c for c in fake_emit.call_args_list if c.args[0] == "faiss.index_ready"]
        self.assertEqual(len(ready_calls), 1)
        # Exact-equality (not substring): kills a "CPU" -> "XXCPUXX" string mutant.
        self.assertEqual(ready_calls[0].kwargs["runtime_context"]["device"], "CPU")


class FaissStatusDeviceTests(SimpleTestCase):
    """get_faiss_status reports the CPU device exactly when active."""

    def setUp(self) -> None:
        self.addCleanup(setattr, faiss_index, "_faiss_index", None)

    def test_status_active_device_is_cpu_exactly(self) -> None:
        with patch.object(faiss_index, "HAS_FAISS", True):
            faiss_index._faiss_index = MagicMock()
            faiss_index._faiss_id_map = [1, 2, 3]
            status = faiss_index.get_faiss_status()
        self.assertEqual(status["device"], "CPU")
        self.assertEqual(status["active"], True)
        self.assertEqual(status["vectors"], 3)

    def test_status_inactive_device_is_none_exactly(self) -> None:
        faiss_index._faiss_index = None
        status = faiss_index.get_faiss_status()
        self.assertEqual(status["device"], "none")
        self.assertEqual(status["active"], False)
        self.assertEqual(status["vectors"], 0)
