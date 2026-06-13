"""Convention-named SimpleTestCase coverage for the PURE builders in
services/gap_detector.py.

The database-touching paths (``detect_observability_gaps`` and ``_file_gap``,
which run the AutoIssue dedup upsert) are exercised by the existing
``tests_gap_detector.py`` ``TestCase``. This file covers only the pure, in-memory
finding builders — ``build_gap_findings``, ``_gap``, ``_reserved_metric_gap`` and
``_lesson_for`` — with exact ``assertEqual`` so the diff-scoped mutation gate
cannot survive a changed string literal, a flipped default, or an off-by-one
slice. No database, no Redis, no network: SimpleTestCase only.
"""

from __future__ import annotations

from unittest.mock import patch

from django.test import SimpleTestCase

from apps.auto_issues.models import AutoIssue
from apps.observability.services import gap_detector


class GapHelperTests(SimpleTestCase):
    def test_gap_prefixes_title_and_keeps_defaults(self) -> None:
        finding = gap_detector._gap(
            "datasource_down",
            "Grafana datasource health has not been proven",
            "desc",
            "datasource-down:victoriametrics",
            ["grafana/provisioning/datasources/datasources.yaml"],
        )
        # The "[vmalert] " prefix is a literal: exact equality kills the wrap.
        self.assertEqual(
            finding.title,
            "[vmalert] Grafana datasource health has not been proven",
        )
        self.assertEqual(finding.category, "datasource_down")
        self.assertEqual(finding.description, "desc")
        self.assertEqual(finding.external_id, "datasource-down:victoriametrics")
        self.assertEqual(
            finding.affected_files,
            ["grafana/provisioning/datasources/datasources.yaml"],
        )

    def test_finding_default_severity_and_priority_are_exact(self) -> None:
        finding = gap_detector._gap("c", "t", "d", "e", ["f"])
        # Dataclass defaults: medium severity, priority 0.4. Exact values kill a
        # changed default literal.
        self.assertEqual(finding.severity, AutoIssue.SEVERITY_MEDIUM)
        self.assertEqual(finding.priority_score, 0.4)


class ReservedMetricGapTests(SimpleTestCase):
    def test_reserved_metric_gap_embeds_metric_name_exactly(self) -> None:
        finding = gap_detector._reserved_metric_gap("xf_import_posts_total")
        self.assertEqual(finding.category, "observability_gap")
        self.assertEqual(
            finding.title,
            "[vmalert] Reserved metric not yet proven: xf_import_posts_total",
        )
        self.assertEqual(finding.external_id, "metric-gap:xf_import_posts_total")
        self.assertEqual(
            finding.affected_files,
            ["backend/apps/observability/metric_specs.py"],
        )


class LessonForTests(SimpleTestCase):
    def test_lesson_has_both_required_parts_in_exact_form(self) -> None:
        finding = gap_detector._gap("vmalert_rule_broken", "t", "the rule broke", "e", ["f"])
        self.assertEqual(
            gap_detector._lesson_for(finding),
            "Trap: the rule broke "
            "Fix shape: prove or repair vmalert_rule_broken and rerun the detector.",
        )


class BuildGapFindingsTests(SimpleTestCase):
    def test_explicit_metric_names_yield_six_total_findings(self) -> None:
        # The name must be UNREGISTERED so it counts as an unproven gap: a
        # registered reserved metric is now proven against the live registry and
        # produces no finding (see GapDetectorProvingTests).
        findings = gap_detector.build_gap_findings(metric_names=["xf_unregistered_probe_metric"])
        # One reserved-metric gap + five fixed infra gaps = exactly 6. Exact
        # count kills the +1 mutation that a >= length check would survive.
        self.assertEqual(len(findings), 6)
        categories = [f.category for f in findings]
        self.assertEqual(
            categories,
            [
                "observability_gap",
                "cardinality_overflow",
                "dashboard_missing",
                "datasource_down",
                "vmalert_rule_broken",
                "scrape_target_down",
            ],
        )

    def test_cardinality_external_id_uses_first_metric_name(self) -> None:
        findings = gap_detector.build_gap_findings(metric_names=["alpha", "beta"])
        cardinality = next(f for f in findings if f.category == "cardinality_overflow")
        self.assertEqual(cardinality.external_id, "cardinality-overflow:alpha")

    def test_empty_metric_names_falls_back_to_reserved_metrics_label(self) -> None:
        # ``first_metric`` defaults to the literal "reserved-metrics" when the
        # name list is empty. Patching the reserved-name source to [] keeps this
        # pure and exercises both the ``names or ...`` and the ``names[0] if``
        # guards.
        with patch.object(gap_detector, "reserved_metric_names", return_value=[]):
            findings = gap_detector.build_gap_findings(metric_names=[])
        cardinality = next(f for f in findings if f.category == "cardinality_overflow")
        self.assertEqual(cardinality.external_id, "cardinality-overflow:reserved-metrics")
        # With no metric names there are zero reserved-metric gaps, leaving the
        # five fixed infra gaps only.
        self.assertEqual(len(findings), 5)

    def test_default_reserved_names_are_capped_at_seventy_five(self) -> None:
        # The ``[:75]`` slice cap: feed 80 fake names and assert exactly 75
        # reserved-metric gaps survive (plus the 5 infra gaps = 80 total).
        fake = [f"m{i}" for i in range(80)]
        with patch.object(gap_detector, "reserved_metric_names", return_value=fake):
            findings = gap_detector.build_gap_findings(metric_names=None)
        reserved = [f for f in findings if f.category == "observability_gap"]
        self.assertEqual(len(reserved), 75)
        self.assertEqual(len(findings), 80)
