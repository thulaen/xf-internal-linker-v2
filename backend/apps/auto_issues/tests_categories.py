"""Tests for AutoIssue categories."""

from __future__ import annotations

from django.test import TestCase

from apps.auto_issues.models import AutoIssue
from apps.auto_issues.services.categories import (
    default_category_for_source,
    get_or_create_category,
    normalize_category_key,
)
from apps.auto_issues.services.dedup import upsert_dedup


class AutoIssueCategoryTests(TestCase):
    def test_default_category_for_observability_sources(self) -> None:
        self.assertEqual(default_category_for_source(AutoIssue.SOURCE_LOKI), "observability")
        self.assertEqual(default_category_for_source(AutoIssue.SOURCE_PYROSCOPE), "performance")

    def test_category_key_validation_is_deliberate(self) -> None:
        self.assertEqual(normalize_category_key("Error_Handling"), "error-handling")
        with self.assertRaises(ValueError):
            normalize_category_key("../random-schema")

    def test_upsert_assigns_category_from_source(self) -> None:
        row, _ = upsert_dedup(
            canonical="category-test",
            source=AutoIssue.SOURCE_PYROSCOPE,
            external_id="hot-fn",
            fingerprint="hot-fn",
            title="Slow function",
            description="A function got slower.",
            affected_files=["backend/apps/example.py"],
            severity=AutoIssue.SEVERITY_MEDIUM,
            priority_score=0.5,
            occurrence_count=1,
        )
        self.assertEqual(row.category.key, "performance")

    def test_upsert_accepts_explicit_existing_category(self) -> None:
        get_or_create_category("security")
        row, _ = upsert_dedup(
            canonical="security-test",
            source=AutoIssue.SOURCE_AGENT,
            external_id="agent-security",
            fingerprint="agent-security",
            title="Secret logged",
            description="A changed log line included a token.",
            affected_files=["backend/apps/example.py"],
            severity=AutoIssue.SEVERITY_HIGH,
            priority_score=0.8,
            occurrence_count=1,
            category_key="security",
        )
        self.assertEqual(row.category.key, "security")

    def test_known_category_helper_is_extensible(self) -> None:
        category = get_or_create_category("future-review-kind")
        self.assertEqual(category.key, "future-review-kind")
        self.assertEqual(category.label, "Future Review Kind")
