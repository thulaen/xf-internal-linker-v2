from django.test import SimpleTestCase
from apps.work_queue.apps import WorkQueueConfig
from apps.work_queue import api
import apps.work_queue

class WorkQueueAppsAndApiTests(SimpleTestCase):
    def test_apps_config(self):
        self.assertEqual(WorkQueueConfig.name, "apps.work_queue")
        self.assertEqual(WorkQueueConfig.verbose_name, "Agent work queue")
        self.assertEqual(WorkQueueConfig.default_auto_field, "django.db.models.BigAutoField")

    def test_api_exports(self):
        expected_exports = [
            "approve_decision",
            "build_cause_groups",
            "build_feed",
            "build_overview",
            "claim_item",
            "historical_fix_suggestions",
            "latest_self_healing_status",
            "record_repair_attempt",
            "rehearse_item",
            "release_item",
        ]
        self.assertEqual(sorted(api.__all__), sorted(expected_exports))

    def test_init(self):
        self.assertIsNotNone(apps.work_queue.__doc__)
