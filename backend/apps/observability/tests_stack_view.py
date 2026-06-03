from __future__ import annotations

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.observability.services.stack_status import build_stack_status


class ObservabilityStackViewTests(TestCase):
    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(get_user_model().objects.create_user("operator"))

    @override_settings(ALLOWED_HOSTS=["testserver"])
    def test_stack_view_lists_twelve_services(self):
        """Given observability stack page, When API loads, Then 12 tiles exist."""
        response = self.client.get("/api/observability/stack/")

        self.assertEqual(response.status_code, 200)
        services = response.json()["services"]
        self.assertEqual(len(services), 12)
        names = {row["service_name"] for row in services}
        self.assertIn("VictoriaMetrics", names)
        self.assertIn("Grafana", names)

    def test_stack_status_marks_victoriametrics_services_healthy_when_endpoints_answer(self):
        """Given VM endpoints answer, When status builds, Then stack is healthy."""
        answers = {
            "http://10.10.10.91:8428/health": True,
            "http://10.10.10.91:8429/metrics": True,
            "http://10.10.10.91:8880/health": True,
        }

        with patch(
            "apps.observability.services.stack_status._endpoint_responds",
            side_effect=lambda url: answers[url],
        ):
            services = build_stack_status()

        states = {service["service_name"]: service["state"] for service in services}
        self.assertEqual(states["VictoriaMetrics"], "healthy")
        self.assertEqual(states["vmagent"], "healthy")
        self.assertEqual(states["vmalert"], "healthy")
