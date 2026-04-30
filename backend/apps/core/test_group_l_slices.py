from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import resolve

from apps.audit.models import AuditEvent, FeatureFlag
from apps.audit.services.audit_logger import record_audit
from apps.audit.services.feature_flags import _get_bucket, is_flag_enabled
from apps.core.services import self_test_smoke
from apps.ops_feed.models import OperationEvent
from apps.ops_feed.services import emit


class GroupLInfrastructureSmokeTests(TestCase):
    def test_self_test_reports_missing_no_dups_invariant(self):
        rule = self_test_smoke.ArtifactRule("auth.User", ("email",), None)
        with (
            mock.patch.object(self_test_smoke, "ARTIFACT_RULES", (rule,)),
            mock.patch.object(self_test_smoke, "_discover_content_artifact_models", return_value=[]),
            mock.patch.object(self_test_smoke, "startup_smoke_test_enabled", return_value=True),
            mock.patch.object(self_test_smoke, "_log_warning"),
        ):
            warnings = self_test_smoke.run_startup_smoke_tests()

        self.assertEqual(len(warnings), 1)
        self.assertIn("without no-dups invariant", warnings[0])
        self.assertIn("NO-DUPLICATES.md", warnings[0])

    def test_record_audit_writes_unified_event(self):
        row = record_audit(
            "settings.update",
            ("app_setting", "example.flag"),
            actor="tester",
            message="Example setting changed.",
            metadata={"enabled": True},
        )

        self.assertEqual(AuditEvent.objects.count(), 1)
        self.assertEqual(row.subject_type, "app_setting")
        self.assertEqual(row.metadata["enabled"], True)

    def test_feature_flag_admin_toggle_and_sticky_bucket(self):
        user = get_user_model().objects.create(username="operator")
        self.client.force_login(user)
        FeatureFlag.objects.create(key="slice-test", enabled=True, rollout_percent=50)

        buckets = [_get_bucket(user.id, "slice-test") for _ in range(100)]
        self.assertEqual(len(set(buckets)), 1)

        response = self.client.patch(
            "/api/feature-flags/admin/slice-test/",
            data={"enabled": False},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(FeatureFlag.objects.get(key="slice-test").enabled)
        self.assertFalse(is_flag_enabled("slice-test", user.id))

    def test_ops_feed_dedupes_within_window(self):
        emit(
            "slice.smoke",
            "Slice smoke event",
            source="test",
            related_entity_type="row",
            related_entity_id="1",
        )
        emit(
            "slice.smoke",
            "Slice smoke event updated",
            source="test",
            related_entity_type="row",
            related_entity_id="1",
        )

        event = OperationEvent.objects.get(event_type="slice.smoke")
        self.assertEqual(event.occurrence_count, 2)
        self.assertEqual(event.plain_english, "Slice smoke event updated")

    def test_readiness_route_is_owned_by_suggestions_urls(self):
        match = resolve("/api/suggestions/readiness/")
        self.assertEqual(match.url_name, "suggestion-readiness")
