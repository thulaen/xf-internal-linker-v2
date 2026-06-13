"""The observability gap detector must PROVE reserved metrics against the live
registry, not flag every reserved name unconditionally.

Before this fix, ``build_gap_findings`` filed a "Reserved metric not yet proven"
finding for every name in the spec — even though all reserved metrics are
registered in the app's Prometheus registry at import (``api.initialise_reserved_metrics``)
and therefore already present in the ``/metrics`` exposition that vmagent
scrapes. That flooded the AutoIssue queue with ~50 false "not yet proven" rows.

A reserved metric is "proven" when it is registered in the live registry. Only
a genuinely-unregistered name is a real gap.
"""

from django.test import SimpleTestCase


class GapDetectorProvingTests(SimpleTestCase):
    def test_registered_reserved_metrics_are_not_flagged(self):
        from apps.observability.services.gap_detector import build_gap_findings

        findings = build_gap_findings()
        metric_gaps = [
            f for f in findings if f.external_id.startswith("metric-gap:")
        ]
        self.assertEqual(
            metric_gaps,
            [],
            f"registered reserved metrics were wrongly flagged: "
            f"{[f.external_id for f in metric_gaps]}",
        )

    def test_genuinely_unregistered_metric_is_still_flagged(self):
        from apps.observability.services.gap_detector import build_gap_findings

        # The default infra probe is unreachable in the test environment, so the
        # five infra gaps are emitted alongside the genuine metric gap.
        findings = build_gap_findings(metric_names=["xf_not_a_real_registered_metric"])
        ids = {f.external_id for f in findings}
        self.assertIn("metric-gap:xf_not_a_real_registered_metric", ids)

    def test_healthy_live_stack_proves_all_infra_gaps(self):
        from apps.observability.services.gap_detector import build_gap_findings

        def healthy_probe(url: str) -> dict:
            if "targets" in url:
                return {"data": {"activeTargets": [{"health": "up", "labels": {"job": "backend"}}]}}
            if "rules" in url:
                return {"data": {"groups": [{"rules": [{"health": "ok"}]}]}}
            if "query" in url:
                return {"status": "success", "data": {"result": [{"value": [0, "5938"]}]}}
            if "health" in url:
                return {"database": "ok"}
            return {}

        # A registered metric + a healthy stack => zero findings of any kind.
        findings = build_gap_findings(
            metric_names=["xf_import_posts_total"], infra_probe=healthy_probe
        )
        self.assertEqual(findings, [])
