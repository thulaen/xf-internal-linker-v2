from __future__ import annotations

from django.test import TestCase

from apps.auto_issues.models import AutoIssue
from apps.observability.services import gap_detector


class ObservabilityGapDetectorTests(TestCase):
    def test_gap_detector_builds_the_six_reserved_gap_classes(self):
        findings = gap_detector.build_gap_findings(metric_names=["xf_import_posts_total"])
        categories = {finding.category for finding in findings}

        self.assertIn("observability_gap", categories)
        self.assertIn("cardinality_overflow", categories)
        self.assertIn("dashboard_missing", categories)
        self.assertIn("datasource_down", categories)
        self.assertIn("vmalert_rule_broken", categories)
        self.assertIn("scrape_target_down", categories)

    def test_gap_detector_files_deduped_vmalert_autoissues(self):
        first = gap_detector.detect_observability_gaps(metric_names=["xf_import_posts_total"])
        second = gap_detector.detect_observability_gaps(metric_names=["xf_import_posts_total"])

        self.assertEqual(first, second)
        self.assertEqual(
            AutoIssue.objects.filter(source=AutoIssue.SOURCE_VMALERT).count(),
            first,
        )
        lessons = AutoIssue.objects.filter(source=AutoIssue.SOURCE_VMALERT).values_list(
            "lessons_learned", flat=True
        )
        self.assertTrue(all("Trap:" in lesson and "Fix shape:" in lesson for lesson in lessons))

