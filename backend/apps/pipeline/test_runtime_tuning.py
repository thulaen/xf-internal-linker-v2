"""Test runtime tuning module for the pipeline app."""

from unittest import mock
from django.test import TestCase, override_settings
import numpy as np

from apps.core.models import AppSetting
from apps.pipeline.services import embeddings, faiss_index


class EmbeddingRuntimeTuningTests(TestCase):
    @mock.patch("apps.pipeline.services.embeddings.os.cpu_count", return_value=12)
    def test_cpu_encode_threads_reads_app_setting(self, _cpu_count):
        AppSetting.objects.update_or_create(
            key="system.cpu_encode_threads",
            defaults={
                "value": "7",
                "value_type": "int",
                "category": "performance",
                "description": "CPU thread cap for CPU-side embedding inference.",
            },
        )

        self.assertEqual(embeddings._get_cpu_encode_threads(), 7)

    @mock.patch("apps.pipeline.services.embeddings._record_embedding_backoff")
    @mock.patch("apps.pipeline.services.embeddings._clear_embedding_runtime_memory")
    def test_oom_toggle_disables_retry_but_still_clears_memory(
        self,
        clear_memory,
        record_backoff,
    ):
        AppSetting.objects.update_or_create(
            key="system.aggressive_oom_backoff",
            defaults={
                "value": "false",
                "value_type": "bool",
                "category": "performance",
                "description": "Whether embedding OOM errors automatically retry with smaller batches.",
            },
        )

        retry_size = embeddings._get_retry_batch_size_after_oom(
            job_id="job-1",
            model_name="text-embedding-3-small",
            failed_batch_size=32,
            exc=RuntimeError("out of memory"),
        )

        self.assertIsNone(retry_size)
        clear_memory.assert_called_once_with()
        record_backoff.assert_not_called()

    def test_high_mode_still_resolves_to_paid_provider_api(self):
        AppSetting.objects.update_or_create(
            key="system.performance_mode",
            defaults={
                "value": "high",
                "value_type": "str",
                "category": "performance",
            },
        )

        self.assertEqual(embeddings._resolve_device(), "api")

    def test_high_mode_uses_high_batch_size(self):
        AppSetting.objects.update_or_create(
            key="system.performance_mode",
            defaults={
                "value": "high",
                "value_type": "str",
                "category": "performance",
            },
        )

        # FR-233 added a hardware-aware tuning layer between the mode
        # default and the AppSetting override. Without isolation that
        # layer reads the test runner's hardware (typically returning
        # 64) and the contract under test ("high mode → high default
        # batch") is masked. Force the auto-tuner to abstain so the
        # function falls through to the mode-based default.
        with mock.patch(
            "apps.pipeline.services.hardware_profile.recommended_batch_size",
            side_effect=RuntimeError("isolated for test"),
        ):
            self.assertEqual(embeddings._get_configured_batch_size(), 128)

    def test_high_mode_runtime_resolution_reports_paid_api(self):
        AppSetting.objects.update_or_create(
            key="system.performance_mode",
            defaults={
                "value": "high",
                "value_type": "str",
                "category": "performance",
            },
        )

        self.assertEqual(
            embeddings.get_effective_runtime_resolution()["effective_runtime_mode"],
            "api",
        )

    @mock.patch(
        "apps.pipeline.services.embeddings.get_effective_runtime_resolution",
        return_value={
            "performance_mode": "high",
            "effective_runtime_mode": "api",
            "device": "api",
            "reason": "paid embedding provider",
        },
    )
    @mock.patch.object(embeddings, "_get_configured_batch_size", return_value=32)
    def test_model_status_reports_paid_provider_runtime(
        self,
        _configured_batch_size,
        _runtime_resolution,
    ):
        status = embeddings.get_model_status()

        self.assertEqual(status["mode"], "high")
        self.assertEqual(status["effective_runtime_mode"], "api")
        self.assertFalse(status["fp16"])

    @mock.patch(
        "apps.pipeline.services.faiss_index.get_current_embedding_filter",
        return_value={},
    )
    @mock.patch(
        "apps.pipeline.services.pipeline._coerce_embedding_vector",
        side_effect=lambda emb: np.asarray(emb, dtype=np.float32),
    )
    @mock.patch("apps.content.models.ContentItem")
    def test_faiss_stays_on_cpu_in_high_mode(
        self,
        content_item_model,
        _coerce_embedding_vector,
        _embedding_filter,
    ):
        fake_faiss = mock.Mock()
        fake_faiss.IndexFlatIP.return_value = mock.Mock(add=mock.Mock())
        fake_faiss.index_cpu_to_gpu.return_value = mock.Mock()
        content_item_model.objects.filter.return_value.values_list.return_value = [
            (1, "thread", [0.25, 0.75]),
        ]
        AppSetting.objects.update_or_create(
            key="system.performance_mode",
            defaults={
                "value": "high",
                "value_type": "str",
                "category": "performance",
            },
        )

        with (
            mock.patch.object(faiss_index, "HAS_FAISS", True),
            mock.patch.object(faiss_index, "faiss", fake_faiss),
        ):
            faiss_index.build_faiss_index()

        fake_faiss.index_cpu_to_gpu.assert_not_called()

    @mock.patch(
        "apps.pipeline.services.faiss_index.get_current_embedding_filter",
        return_value={},
    )
    @mock.patch(
        "apps.pipeline.services.pipeline._coerce_embedding_vector",
        side_effect=lambda emb: np.asarray(emb, dtype=np.float32),
    )
    @mock.patch("apps.content.models.ContentItem")
    def test_faiss_stays_on_cpu_in_balanced_mode(
        self,
        content_item_model,
        _coerce_embedding_vector,
        _embedding_filter,
    ):
        fake_faiss = mock.Mock()
        fake_faiss.IndexFlatIP.return_value = mock.Mock(add=mock.Mock())
        fake_faiss.get_num_gpus.return_value = 1
        fake_faiss.StandardGpuResources.return_value = mock.Mock(
            setTempMemory=mock.Mock()
        )
        fake_faiss.index_cpu_to_gpu.return_value = mock.Mock()
        content_item_model.objects.filter.return_value.values_list.return_value = [
            (1, "thread", [0.25, 0.75]),
        ]
        AppSetting.objects.update_or_create(
            key="system.performance_mode",
            defaults={
                "value": "balanced",
                "value_type": "str",
                "category": "performance",
            },
        )

        with (
            mock.patch.object(faiss_index, "HAS_FAISS", True),
            mock.patch.object(faiss_index, "faiss", fake_faiss),
        ):
            faiss_index.build_faiss_index()

        fake_faiss.index_cpu_to_gpu.assert_not_called()

    @mock.patch(
        "apps.pipeline.services.faiss_index.get_current_embedding_filter",
        return_value={},
    )
    @mock.patch("apps.pipeline.services.faiss_index.emit")
    @mock.patch("apps.content.models.ContentItem")
    def test_empty_faiss_build_is_informational(
        self,
        content_item_model,
        emit_mock,
        _embedding_filter,
    ):
        content_item_model.objects.filter.return_value.values_list.return_value = []

        with (
            mock.patch.object(faiss_index, "HAS_FAISS", True),
            mock.patch.object(faiss_index, "faiss", mock.Mock()),
            self.assertLogs("apps.pipeline.services.faiss_index", level="INFO") as logs,
        ):
            faiss_index.build_faiss_index()

        self.assertTrue(any("no embeddings found" in line for line in logs.output))
        emit_mock.assert_called_once()
        self.assertEqual(emit_mock.call_args.kwargs["severity"], "info")
