from __future__ import annotations

from pathlib import Path

from django.test import SimpleTestCase
import yaml


ROOT = Path("/repo") if Path("/repo/config/vmalert/rules.yml").exists() else Path(__file__).resolve().parents[3]


class VmalertRulesTests(SimpleTestCase):
    def test_reserved_alerts_have_two_part_repair_annotations(self):
        rules = _alert_rules_by_name()
        expected = {
            "ImportFailuresHigh",
            "WebhookBacklogGrowing",
            "EmbeddingQueueAgeHigh",
            "FaissSearchLatencyHigh",
            "SuggestionGenerationStopped",
            "DatabaseWriteErrors",
            "DiskSpaceLow",
            "ReviewBacklogTooLarge",
        }

        self.assertTrue(expected.issubset(rules))
        for name in expected:
            annotations = rules[name]["annotations"]
            self.assertTrue(annotations["summary"])
            self.assertTrue(annotations["description"])
            self.assertTrue(annotations["trap"])
            self.assertTrue(annotations["fix_shape"])

    def test_anomaly_and_cardinality_rules_are_present(self):
        rules = _alert_rules_by_name()
        expected = {
            "VictoriaMetricsStorageOverflow",
            "CardinalityBudgetExceeded",
            "ImportRateDropPredicted",
            "EmbeddingLatencyDrift",
            "ReservedMetricStale",
            "ScoreDistributionShift",
        }

        self.assertTrue(expected.issubset(rules))
        self.assertIn("predict_linear", rules["ImportRateDropPredicted"]["expr"])
        self.assertIn("xf_active_series_per_tenant", rules["CardinalityBudgetExceeded"]["expr"])


def _alert_rules_by_name() -> dict[str, dict]:
    payload = yaml.safe_load((ROOT / "config/vmalert/rules.yml").read_text())
    rules: dict[str, dict] = {}
    for group in payload["groups"]:
        for rule in group.get("rules", []):
            if "alert" in rule:
                rules[rule["alert"]] = rule
    return rules

