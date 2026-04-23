from io import StringIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from rest_framework.test import APITestCase

from apps.core.models import AppSetting
from apps.core.performance_mode import (
    PERFORMANCE_MODE_BALANCED,
    PERFORMANCE_MODE_HIGH,
    get_requested_performance_mode,
    normalize_performance_mode,
)
from apps.core.views import RuntimeConfigView


class RuntimeConfigViewTests(APITestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(
            username="runtime-controls-user",
            password="pass",
        )
        self.client.force_authenticate(user=user)

    @override_settings(
        CUDA_MEMORY_FRACTION_SAFE=0.25,
        CUDA_MEMORY_FRACTION_HIGH=0.80,
        GPU_TEMP_CEILING_C=90,
        CELERY_WORKER_CONCURRENCY=2,
    )
    def test_get_returns_new_runtime_controls_and_legacy_aliases(self):
        AppSetting.objects.update_or_create(
            key="system.performance_mode",
            defaults={
                "value": "high",
                "value_type": "str",
                "category": "performance",
                "description": "Current performance mode",
            },
        )

        response = self.client.get("/api/settings/runtime-config/")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["gpu_memory_budget_pct"], 80)
        self.assertEqual(data["default_queue_concurrency"], 2)
        self.assertEqual(data["celery_concurrency"], 2)
        self.assertEqual(data["celery_concurrency_range"], [1, 6])
        self.assertTrue(data["celery_concurrency_requires_restart"])
        self.assertTrue(data["aggressive_oom_backoff"])

    @mock.patch.object(RuntimeConfigView, "_cpu_thread_cap", return_value=10)
    def test_post_persists_runtime_controls_with_descriptions(self, _cpu_cap):
        payload = {
            "gpu_memory_budget_pct": 60,
            "gpu_temp_pause_c": 88,
            "cpu_encode_threads": 6,
            "default_queue_concurrency": 4,
            "aggressive_oom_backoff": "false",
        }

        response = self.client.post(
            "/api/settings/runtime-config/",
            payload,
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["updated"]["celery_concurrency"], 4)
        self.assertEqual(
            AppSetting.objects.get(key="system.gpu_memory_budget_pct").description,
            "Maximum GPU memory budget percentage for embeddings.",
        )
        self.assertEqual(
            AppSetting.objects.get(key="system.default_queue_concurrency").value,
            "4",
        )
        self.assertEqual(
            AppSetting.objects.get(key="system.aggressive_oom_backoff").value,
            "false",
        )

    @mock.patch.object(RuntimeConfigView, "_cpu_thread_cap", return_value=10)
    def test_post_rejects_invalid_cpu_threads_and_bool(self, _cpu_cap):
        response = self.client.post(
            "/api/settings/runtime-config/",
            {
                "cpu_encode_threads": 11,
                "aggressive_oom_backoff": "maybe",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["errors"]["cpu_encode_threads"],
            "Must be between 1 and 10.",
        )
        self.assertEqual(
            response.json()["errors"]["aggressive_oom_backoff"],
            "Must be true or false.",
        )


class DefaultQueueConcurrencyCommandTests(TestCase):
    @override_settings(CELERY_WORKER_CONCURRENCY=2)
    def test_command_prefers_app_setting_override(self):
        AppSetting.objects.update_or_create(
            key="system.default_queue_concurrency",
            defaults={
                "value": "5",
                "value_type": "int",
                "category": "performance",
                "description": "Worker concurrency for the default Celery queue.",
            },
        )
        output = StringIO()

        call_command("print_default_queue_concurrency", stdout=output)

        self.assertEqual(output.getvalue().strip(), "5")

    @override_settings(CELERY_WORKER_CONCURRENCY=9)
    def test_command_clamps_setting_fallback(self):
        output = StringIO()

        call_command("print_default_queue_concurrency", stdout=output)

        self.assertEqual(output.getvalue().strip(), "6")


class PerformanceModeResolverTests(TestCase):
    def tearDown(self):
        AppSetting.objects.filter(key="system.performance_mode").delete()

    @mock.patch.dict("os.environ", {"ML_PERFORMANCE_MODE": "BALANCED"}, clear=False)
    def test_db_high_overrides_balanced_env(self):
        AppSetting.objects.update_or_create(
            key="system.performance_mode",
            defaults={
                "value": "high",
                "value_type": "str",
                "category": "performance",
            },
        )

        self.assertEqual(get_requested_performance_mode(), PERFORMANCE_MODE_HIGH)

    @mock.patch.dict(
        "os.environ", {"ML_PERFORMANCE_MODE": "HIGH_PERFORMANCE"}, clear=False
    )
    def test_missing_db_setting_falls_back_to_env(self):
        AppSetting.objects.filter(key="system.performance_mode").delete()
        self.assertEqual(get_requested_performance_mode(), PERFORMANCE_MODE_HIGH)

    def test_legacy_high_performance_alias_normalizes_to_high(self):
        self.assertEqual(
            normalize_performance_mode("HIGH_PERFORMANCE"),
            PERFORMANCE_MODE_HIGH,
        )

    def test_unknown_mode_falls_back_to_balanced(self):
        self.assertEqual(
            normalize_performance_mode("turbo-boost-9000"),
            PERFORMANCE_MODE_BALANCED,
        )


class RuntimeSettingsViewTests(APITestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(
            username="runtime-settings-user",
            password="pass",
        )
        self.client.force_authenticate(user=user)

    @mock.patch(
        "apps.pipeline.services.embeddings.get_effective_runtime_resolution",
        return_value={
            "performance_mode": "high",
            "effective_runtime_mode": "gpu",
            "device": "cuda",
            "reason": "",
        },
    )
    def test_runtime_settings_reports_effective_runtime_mode(self, _runtime_resolution):
        AppSetting.objects.update_or_create(
            key="system.performance_mode",
            defaults={
                "value": "high",
                "value_type": "str",
                "category": "performance",
            },
        )
        AppSetting.objects.update_or_create(
            key="system.runtime_mode",
            defaults={
                "value": "cpu",
                "value_type": "str",
                "category": "performance",
            },
        )

        response = self.client.get("/api/settings/runtime/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["performance_mode"], "high")
        self.assertEqual(response.json()["runtime_mode"], "cpu")
        self.assertEqual(response.json()["effective_runtime_mode"], "gpu")

    @mock.patch(
        "apps.pipeline.services.embeddings.get_effective_runtime_resolution",
        return_value={
            "performance_mode": "high",
            "effective_runtime_mode": "cpu",
            "device": "cpu",
            "reason": "CUDA unavailable",
        },
    )
    def test_runtime_settings_reports_cpu_effective_mode_when_gpu_unavailable(
        self, _runtime_resolution
    ):
        AppSetting.objects.update_or_create(
            key="system.performance_mode",
            defaults={
                "value": "high",
                "value_type": "str",
                "category": "performance",
            },
        )

        response = self.client.get("/api/settings/runtime/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["performance_mode"], "high")
        self.assertEqual(response.json()["effective_runtime_mode"], "cpu")
