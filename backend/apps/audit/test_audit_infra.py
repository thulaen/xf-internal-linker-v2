"""Audit-app infrastructure tests (Django TestCase form).

Covers `record_audit`, FeatureFlag sticky bucketing + variant distribution,
and the cross-session duplicate detector in `verify_artefact_integrity`.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.audit.integrity import verify_artefact_integrity
from apps.audit.models import ErrorLog, FeatureFlag
from apps.audit.services.audit_logger import record_audit
from apps.audit.services.feature_flags import get_flag_variant, is_flag_enabled
from apps.crawler.models import CrawledPageMeta, CrawlSession

User = get_user_model()


class AuditInfraTests(TestCase):

    def test_record_audit_creates_row_with_target(self):
        user = User.objects.create_user(username="testuser")
        entry = record_audit(
            action="approve",
            target=user,
            detail={"reason": "test"},
        )
        # `record_audit` returns an `AuditEvent` whose fields use the
        # `subject_*` / `metadata` names. The original test (never run because
        # of the pytest import error) used the older `target_*` / `detail`
        # names that no longer exist on the model.
        self.assertEqual(entry.action, "approve")
        self.assertEqual(entry.subject_type, "user")
        self.assertEqual(entry.subject_id, str(user.pk))
        self.assertEqual(entry.metadata, {"reason": "test"})

    def test_feature_flag_sticky_bucketing(self):
        flag = FeatureFlag.objects.create(
            key="test-flag",
            enabled=True,
            rollout_percent=50,
        )
        users = list(range(1, 11))
        results = [is_flag_enabled("test-flag", u, log_exposure=False) for u in users]
        results2 = [is_flag_enabled("test-flag", u, log_exposure=False) for u in users]
        self.assertEqual(results, results2)
        flag.enabled = False
        flag.save()
        self.assertFalse(
            any(is_flag_enabled("test-flag", u, log_exposure=False) for u in users)
        )

    def test_feature_flag_variant_distribution(self):
        FeatureFlag.objects.create(
            key="test-variants",
            enabled=True,
            variants=[
                {"name": "a", "weight": 1},
                {"name": "b", "weight": 1},
            ],
        )
        variants = [get_flag_variant("test-variants", u) for u in range(100)]
        self.assertIn("a", variants)
        self.assertIn("b", variants)
        # Sticky: same user → same variant on repeat call.
        self.assertEqual(
            get_flag_variant("test-variants", 1),
            get_flag_variant("test-variants", 1),
        )

    def test_integrity_check_detects_cross_session_duplicates(self):
        session = CrawlSession.objects.create(site_domain="example.com")
        CrawledPageMeta.objects.create(
            url="http://example.com/1",
            normalized_url="http://example.com/1",
            content_hash="same-content",
            session=session,
        )
        session2 = CrawlSession.objects.create(site_domain="example.com")
        CrawledPageMeta.objects.create(
            url="http://example.com/1",
            normalized_url="http://example.com/1",
            content_hash="same-content",
            session=session2,
        )
        verify_artefact_integrity()
        self.assertTrue(
            ErrorLog.objects.filter(
                job_type="integrity_check", step="CrawledPageMeta"
            ).exists()
        )
