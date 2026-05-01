from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.core.models import AppSetting
from apps.core.runtime_models import RuntimeModelRegistry


class RuntimeModelPauseSummaryTests(TestCase):
    def setUp(self) -> None:
        self.user = get_user_model().objects.create_user(
            username="runtime-operator",
            password="not-used",
        )
        self.client.force_login(self.user)
        self.model = RuntimeModelRegistry.objects.create(
            task_type="embedding",
            model_name="BAAI/bge-m3",
            model_family="sentence-transformers",
            dimension=1024,
            role="champion",
            status="ready",
        )

    def _get_summary(self) -> dict:
        response = self.client.get(
            "/api/settings/runtime/models/",
            {"task_type": "embedding"},
        )
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_summary_reports_master_pause_state(self) -> None:
        self.assertFalse(self._get_summary()["master_paused"])

        response = self.client.post(
            f"/api/settings/runtime/models/{self.model.id}/action/",
            data={"action": "pause"},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            AppSetting.objects.get(key="system.master_pause").value,
            "true",
        )
        self.assertTrue(self._get_summary()["master_paused"])

        response = self.client.post(
            f"/api/settings/runtime/models/{self.model.id}/action/",
            data={"action": "resume"},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            AppSetting.objects.get(key="system.master_pause").value,
            "false",
        )
        self.assertFalse(self._get_summary()["master_paused"])
