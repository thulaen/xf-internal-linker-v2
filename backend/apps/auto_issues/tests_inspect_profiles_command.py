"""Tests for the profile-inspection management command."""

from __future__ import annotations

from io import StringIO
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from django.core.management import call_command
from django.test import TestCase

from apps.auto_issues.management.commands import inspect_profiles
from apps.auto_issues.models import AutoIssue


class InspectProfilesCommandTests(TestCase):
    @mock.patch(
        "apps.auto_issues.management.commands.inspect_profiles._profile_pipeline_ready",
        return_value=True,
    )
    @mock.patch(
        "apps.auto_issues.management.commands.inspect_profiles._collect_hotspots",
        return_value=[("Scheduler.run", 1000.0), ("sleep", 500.0)],
    )
    def test_prints_profiling_proof_when_pipeline_is_ready(
        self, _hotspots, _pipeline_ready
    ) -> None:
        out = StringIO()

        call_command(
            "inspect_profiles",
            "--service",
            "xf-linker-backend",
            "--scope",
            ".githooks",
            stdout=out,
        )

        text = out.getvalue()
        self.assertIn("[PROFILING PROOF:", text)
        self.assertIn("source=pyroscope+otel_profiles", text)
        self.assertIn("hotspots=2", text)

    @mock.patch(
        "apps.auto_issues.management.commands.inspect_profiles._profile_pipeline_ready",
        return_value=False,
    )
    @mock.patch(
        "apps.auto_issues.management.commands.inspect_profiles._collect_hotspots",
        return_value=[],
    )
    def test_missing_pipeline_files_deduped_autoissues(
        self, _hotspots, _pipeline_ready
    ) -> None:
        out = StringIO()

        call_command("inspect_profiles", "--scope", ".githooks", stdout=out)
        call_command("inspect_profiles", "--scope", ".githooks", stdout=StringIO())

        text = out.getvalue()
        self.assertIn("[PROFILING PIPELINE GAP:", text)
        self.assertIn("trace-profile-correlation", text)
        self.assertEqual(
            AutoIssue.objects.filter(
                external_id__startswith="profiling-pipeline-gap::"
            ).count(),
            8,
        )

    @mock.patch(
        "apps.auto_issues.management.commands.inspect_profiles._profile_pipeline_ready",
        return_value=False,
    )
    @mock.patch(
        "apps.auto_issues.management.commands.inspect_profiles._collect_hotspots",
        return_value=[],
    )
    def test_dry_run_does_not_create_autoissues(self, _hotspots, _pipeline_ready) -> None:
        out = StringIO()

        call_command("inspect_profiles", "--scope", ".githooks", "--dry-run", stdout=out)

        self.assertIn("[PROFILING PIPELINE GAP DRY RUN:", out.getvalue())
        self.assertEqual(AutoIssue.objects.count(), 0)

    @mock.patch.object(inspect_profiles, "_extract_function_totals")
    @mock.patch.object(inspect_profiles, "_query_pyroscope_render")
    def test_collect_hotspots_orders_and_limits_results(self, query, extract) -> None:
        query.return_value = {"flamebearer": {}}
        extract.return_value = {"slow": 300.0, "fast": 100.0}

        result = inspect_profiles._collect_hotspots(
            server="http://pyroscope:4040",
            service="xf-linker-backend",
            span_seconds=60,
            limit=1,
        )

        self.assertEqual(result, [("slow", 300.0)])
        query.assert_called_once()

    def test_profile_pipeline_ready_reads_config_and_handles_missing_file(self) -> None:
        with TemporaryDirectory() as temp_dir:
            _write_profile_ready_files(Path(temp_dir))
            with mock.patch.dict(os.environ, {"REPO_ROOT": temp_dir}):
                self.assertTrue(inspect_profiles._profile_pipeline_ready())

        with TemporaryDirectory() as temp_dir:
            with mock.patch.dict(os.environ, {"REPO_ROOT": temp_dir}):
                self.assertFalse(inspect_profiles._profile_pipeline_ready())

    def test_profile_pipeline_rejects_missing_feature_gate(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_profile_ready_files(root)
            compose_path = root / "docker-compose.yml"
            compose_path.write_text(
                compose_path.read_text().replace(
                    "--feature-gates=service.profilesSupport",
                    "--config=/etc/otelcol/config.yaml",
                ),
                encoding="utf-8",
            )

            with mock.patch.dict(os.environ, {"REPO_ROOT": temp_dir}):
                self.assertFalse(inspect_profiles._profile_pipeline_ready())

    def test_profile_pipeline_rejects_incompatible_versions(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_profile_ready_files(root)
            compose_path = root / "docker-compose.yml"
            compose_path.write_text(
                compose_path.read_text()
                .replace("grafana/pyroscope:1.18.1", "grafana/pyroscope:1.9.0")
                .replace(
                    "otel/opentelemetry-collector-contrib:0.147.0",
                    "otel/opentelemetry-collector-contrib:0.106.1",
                ),
                encoding="utf-8",
            )

            with mock.patch.dict(os.environ, {"REPO_ROOT": temp_dir}):
                self.assertFalse(inspect_profiles._profile_pipeline_ready())


def _write_profile_ready_files(root: Path) -> None:
    (root / "otelcol-config.yaml").write_text(
        """
exporters:
  otlp/pyroscope:
    endpoint: pyroscope:4040
    tls:
      insecure: true
service:
  pipelines:
    profiles:
      receivers: [otlp]
      exporters: [otlp/pyroscope]
""",
        encoding="utf-8",
    )
    (root / "docker-compose.yml").write_text(
        """
services:
  pyroscope:
    image: grafana/pyroscope:1.18.1
  otel-collector:
    image: otel/opentelemetry-collector-contrib:0.147.0
    command:
      - --config=/etc/otelcol/config.yaml
      - --feature-gates=service.profilesSupport
""",
        encoding="utf-8",
    )
