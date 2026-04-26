from unittest import mock
from types import SimpleNamespace

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

    @override_settings(CUDA_MEMORY_FRACTION_SAFE=0.25, CUDA_MEMORY_FRACTION_HIGH=0.80)
    def test_gpu_memory_budget_uses_app_setting_override(self):
        AppSetting.objects.update_or_create(
            key="system.gpu_memory_budget_pct",
            defaults={
                "value": "60",
                "value_type": "int",
                "category": "performance",
                "description": "Maximum GPU memory budget percentage for embeddings.",
            },
        )

        self.assertEqual(embeddings._get_gpu_memory_budget_fraction(), 0.60)

    def test_gpu_resume_temp_tracks_pause_setting(self):
        AppSetting.objects.update_or_create(
            key="system.gpu_temp_pause_c",
            defaults={
                "value": "92",
                "value_type": "int",
                "category": "performance",
                "description": "GPU temperature threshold that pauses embedding work.",
            },
        )

        self.assertEqual(embeddings._get_gpu_temp_resume_c(), 82)

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
            model_name="BAAI/bge-m3",
            failed_batch_size=32,
            exc=RuntimeError("cuda out of memory"),
        )

        self.assertIsNone(retry_size)
        clear_memory.assert_called_once_with()
        record_backoff.assert_not_called()

    @mock.patch(
        "apps.pipeline.services.embeddings._apply_vram_fraction",
    )
    @mock.patch(
        "apps.pipeline.services.embeddings._cuda_warmup_ok",
        return_value=True,
    )
    @mock.patch.dict(
        "sys.modules",
        {
            "torch": SimpleNamespace(
                cuda=SimpleNamespace(
                    is_available=lambda: True,
                )
            )
        },
    )
    def test_high_mode_resolves_to_cuda_when_available(
        self,
        _warmup_ok,
        apply_vram_fraction,
    ):
        AppSetting.objects.update_or_create(
            key="system.performance_mode",
            defaults={
                "value": "high",
                "value_type": "str",
                "category": "performance",
            },
        )

        self.assertEqual(embeddings._resolve_device(), "cuda")
        apply_vram_fraction.assert_called_once_with()

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

    @mock.patch(
        "apps.pipeline.services.embeddings._emit_gpu_fallback_alert",
    )
    @mock.patch.dict(
        "sys.modules",
        {
            "torch": SimpleNamespace(
                cuda=SimpleNamespace(
                    is_available=lambda: False,
                )
            )
        },
    )
    def test_high_mode_falls_back_to_cpu_when_cuda_unavailable(
        self,
        emit_alert,
    ):
        AppSetting.objects.update_or_create(
            key="system.performance_mode",
            defaults={
                "value": "high",
                "value_type": "str",
                "category": "performance",
            },
        )

        self.assertEqual(embeddings._resolve_device(), "cpu")
        emit_alert.assert_called_once_with("CUDA unavailable")

    @mock.patch(
        "apps.pipeline.services.embeddings.get_effective_runtime_resolution",
        return_value={
            "performance_mode": "high",
            "effective_runtime_mode": "gpu",
            "device": "cuda",
            "reason": "",
        },
    )
    @mock.patch.object(embeddings, "_get_configured_batch_size", return_value=32)
    def test_model_status_reports_canonical_high_mode_and_fp16(
        self,
        _configured_batch_size,
        _runtime_resolution,
    ):
        status = embeddings.get_model_status()

        self.assertEqual(status["mode"], "high")
        self.assertEqual(status["effective_runtime_mode"], "gpu")
        self.assertTrue(status["fp16"])

    @mock.patch("apps.pipeline.services.embeddings._emit_model_alert")
    @mock.patch(
        "apps.pipeline.services.embeddings._assert_model_dimension_supported",
        return_value={
            "recommended_batch_size": 32,
            "configured_batch_size": 32,
            "embedding_dim": 1024,
        },
    )
    def test_load_model_caches_cpu_and_cuda_variants_separately(
        self,
        _dimension_support,
        _emit_model_alert,
    ):
        embeddings._model_cache.clear()
        cpu_model = mock.Mock()
        gpu_model = mock.Mock()

        with (
            mock.patch(
                "apps.pipeline.services.embeddings._resolve_device",
                side_effect=["cpu", "cuda"],
            ),
            mock.patch.dict(
                "sys.modules",
                {
                    "sentence_transformers": SimpleNamespace(
                        SentenceTransformer=mock.Mock(
                            side_effect=[cpu_model, gpu_model]
                        )
                    )
                },
            ),
        ):
            self.assertIs(embeddings._load_model("BAAI/bge-m3"), cpu_model)
            self.assertIs(embeddings._load_model("BAAI/bge-m3"), gpu_model)

        self.assertIn("BAAI/bge-m3::cpu", embeddings._model_cache)
        self.assertIn("BAAI/bge-m3::cuda", embeddings._model_cache)
        embeddings._model_cache.clear()

    @mock.patch(
        "apps.pipeline.services.faiss_index.get_current_embedding_filter",
        return_value={},
    )
    @mock.patch(
        "apps.pipeline.services.pipeline._coerce_embedding_vector",
        side_effect=lambda emb: np.asarray(emb, dtype=np.float32),
    )
    @mock.patch("apps.content.models.ContentItem")
    def test_faiss_uses_gpu_in_high_mode(
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

        fake_faiss.index_cpu_to_gpu.assert_called_once()

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
