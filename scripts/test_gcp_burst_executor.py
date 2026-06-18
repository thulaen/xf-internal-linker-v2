"""Tests for the Google Cloud burst mutation runner."""

from __future__ import annotations

import unittest

from gcp_burst_executor import BurstConfig, build_gcloud_container_command, parse_args


class GcpBurstExecutorTests(unittest.TestCase):
    def test_when_required_values_missing_then_config_reports_errors(self) -> None:
        config = BurstConfig(project="", region="", budget_cap_eur=0, max_vms=0)

        self.assertEqual(
            config.validation_errors(),
            (
                "GCP project is required.",
                "GCP region is required.",
                "Monthly budget cap must be greater than zero.",
                "Maximum VM count must be between 1 and 50.",
            ),
        )

    def test_when_confirm_missing_then_paid_run_refuses(self) -> None:
        args = parse_args(["--project", "xf", "--region", "europe-west1"])

        self.assertFalse(args.confirm_paid_run)

    def test_when_config_valid_then_container_command_uses_gcloud_image(self) -> None:
        config = BurstConfig(project="xf", region="europe-west1", budget_cap_eur=20, max_vms=12)

        command = build_gcloud_container_command(config, job_name="xf-mutation-123")

        self.assertEqual(command[:3], ["docker", "run", "--rm"])
        self.assertIn("gcr.io/google.com/cloudsdktool/google-cloud-cli:stable", command)
        self.assertIn("batch", command)
        self.assertIn("xf-mutation-123", command)


if __name__ == "__main__":
    unittest.main()
