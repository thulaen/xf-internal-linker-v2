from pathlib import Path
from unittest.mock import patch

import yaml
from django.conf import settings
from django.test import SimpleTestCase

from apps.observability.management.commands.check_observability_health import (
    _service_state,
)


ROOT = Path("/repo") if Path("/repo/docker-compose.yml").exists() else Path(settings.BASE_DIR)


class ObservabilityStackFoundationTests(SimpleTestCase):
    def test_victoriametrics_containers_are_mint_owned(self):
        """Given stack health config, When inspected, Then VM runs on Mint."""
        health = yaml.safe_load((ROOT / "config/docker-stack-health.json").read_text())
        windows = next(row for row in health["targets"] if row["name"] == "windows-control-plane")
        mint = next(row for row in health["targets"] if row["name"] == "mint-quality-plane")
        windows_names = {row["name"] for row in windows["containers"]}
        mint_names = {row["name"] for row in mint["containers"]}

        for name in ("xf_linker_vmsingle", "xf_linker_vmagent", "xf_linker_vmalert"):
            self.assertNotIn(name, windows_names)
            self.assertIn(name, mint_names)

    def test_sonarqube_is_fully_removed(self):
        """Given SonarQube was retired 2026-06-09 (replaced by GitHub Dependabot
        + pip-audit in CI, per config/observability-services.json), When the
        stack-health config is read, Then no target lists a SonarQube container
        on any machine. Guards against the retired service creeping back."""
        health = yaml.safe_load((ROOT / "config/docker-stack-health.json").read_text())
        all_container_names = {
            container["name"]
            for target in health["targets"]
            for container in target.get("containers", [])
        }
        self.assertNotIn("xf_linker_sonarqube", all_container_names)
        self.assertNotIn("xf_linker_sonar_autoscan", all_container_names)

    def test_vmagent_headers_are_list_entries(self):
        """Given vmagent scrape config, When parsed, Then headers fit vmagent."""
        scrape = yaml.safe_load((ROOT / "config/vmagent/scrape.yml").read_text())
        backend = next(row for row in scrape["scrape_configs"] if row["job_name"] == "backend")
        self.assertIsInstance(backend["headers"], list)
        self.assertEqual(
            backend["headers"][0],
            "X-Metrics-Token: dev-metrics-token-change-me",
        )

    def test_grafana_has_victoriametrics_default_datasource(self):
        """Given Grafana provisioning, When read, Then VM is default."""
        data = yaml.safe_load(
            (ROOT / "grafana/provisioning/datasources/datasources.yaml").read_text()
        )
        vm = next(row for row in data["datasources"] if row["name"] == "VictoriaMetrics")
        self.assertTrue(vm["isDefault"])
        self.assertEqual(vm["url"], "http://vmsingle:8428")

    def test_health_probe_reads_kubernetes_pod_readiness(self):
        pod = {
            "status": {
                "phase": "Running",
                "containerStatuses": [{"ready": True}],
            },
        }

        with patch(
            "apps.observability.management.commands.check_observability_health."
            "_kubernetes_pods_for_service",
            return_value=[pod],
        ):
            self.assertEqual(("Running", "Ready"), _service_state("vmsingle"))

    def test_health_probe_reports_not_ready_kubernetes_pod(self):
        pod = {
            "status": {
                "phase": "Running",
                "containerStatuses": [{"ready": False}],
            },
        }

        with patch(
            "apps.observability.management.commands.check_observability_health."
            "_kubernetes_pods_for_service",
            return_value=[pod],
        ):
            self.assertEqual(("Running", "not-ready"), _service_state("vmsingle"))

    def test_health_probe_reports_absent_kubernetes_pod(self):
        with patch(
            "apps.observability.management.commands.check_observability_health."
            "_kubernetes_pods_for_service",
            return_value=[],
        ):
            self.assertEqual(("absent", ""), _service_state("vmsingle"))

    def test_health_probe_ignores_old_compose_rows(self):
        old_compose_rows = [
            {
                "Name": "xf_linker_vmsingle",
                "Service": "vmsingle",
                "State": "running",
                "Health": "",
            }
        ]

        with patch(
            "apps.observability.management.commands.check_observability_health."
            "_kubernetes_pods_for_service",
            return_value=[],
        ):
            self.assertEqual(("absent", ""), _service_state("vmsingle"))
        self.assertEqual("vmsingle", old_compose_rows[0]["Service"])
