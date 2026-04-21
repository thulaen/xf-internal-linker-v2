from unittest import mock

from django.test import TestCase, override_settings

from apps.core.models import AppSetting
from apps.pipeline.services import embeddings


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
