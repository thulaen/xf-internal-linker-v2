"""Tests for the Google Cloud burst mutation planner."""

from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from gcp_burst_executor import (
    BurstConfig,
    build_gcloud_batch_command,
    build_plan,
    build_result_record,
    main,
    parse_args,
)
from gcp_spend_guard import (
    SpendGuardConfig,
    SpendGuardResult,
    build_bq_command,
    build_month_to_date_query,
    check_spend_guard,
    evaluate_billing_rows,
    main as spend_guard_main,
)


class GcpBurstExecutorTests(unittest.TestCase):
    def test_when_required_values_missing_then_config_reports_errors(self) -> None:
        config = BurstConfig(
            project="",
            region="",
            budget_cap_eur=0,
            max_vms=0,
            refuse_at_eur=18,
            max_vm_minutes=0,
            machine_type="",
        )

        self.assertEqual(
            config.validation_errors(),
            (
                "GCP project is required.",
                "GCP region is required.",
                "Monthly budget cap must be greater than zero.",
                "Maximum VM count must be between 1 and 50.",
                "Spend refusal limit must be greater than zero and at or below the budget cap.",
                "Maximum VM minutes must be greater than zero.",
                "Google Cloud machine type is required.",
            ),
        )

    def test_when_confirm_missing_then_paid_run_refuses(self) -> None:
        args = parse_args(["--project", "xf", "--region", "europe-west1"])

        self.assertFalse(args.confirm_paid_run)

    def test_when_paid_run_has_no_confirm_then_main_refuses(self) -> None:
        spend_path = Path("tmp/test-gcp-spend-no-confirm.json")
        spend_path.parent.mkdir(parents=True, exist_ok=True)
        spend_path.write_text(
            json.dumps(SpendGuardResult(True, "ok", 1.0, 18.0, "Spend is safe.").to_mapping()),
            encoding="utf-8",
        )

        rc = main(["--project", "xf", "--region", "europe-west1", "--spend-json", str(spend_path)])

        self.assertEqual(rc, 2)

    def test_when_config_invalid_then_main_reports_validation_failure(self) -> None:
        rc = main(["--project", "", "--region", "", "--dry-run"])

        self.assertEqual(rc, 2)

    def test_when_config_valid_then_batch_command_uses_gcloud(self) -> None:
        config = BurstConfig(
            project="xf",
            region="europe-west1",
            budget_cap_eur=20,
            max_vms=12,
            refuse_at_eur=18,
            max_vm_minutes=20,
            machine_type="c3-highcpu-8",
        )

        command = build_gcloud_batch_command(config, job_name="xf-mutation-123")

        self.assertEqual(command[:3], ["gcloud", "batch", "jobs"])
        self.assertIn("batch", command)
        self.assertIn("xf-mutation-123", command)

    def test_when_requested_vms_exceed_slice_cap_then_plan_clamps_to_twelve(self) -> None:
        args = parse_args(["--project", "xf", "--region", "europe-west1", "--max-vms", "50"])
        spend = SpendGuardResult(True, "ok", 1.0, 18.0, "Spend is safe.")

        plan = build_plan(args, spend)

        self.assertEqual(plan.to_record()["planned-vms"], 12)
        self.assertEqual(plan.to_record()["requested-vms"], 50)

    def test_when_dry_run_then_json_contains_no_spend_fields(self) -> None:
        spend_path = Path("tmp/test-gcp-spend-ok.json")
        spend_path.parent.mkdir(parents=True, exist_ok=True)
        spend_path.write_text(
            json.dumps(SpendGuardResult(True, "ok", 1.0, 18.0, "Spend is safe.").to_mapping()),
            encoding="utf-8",
        )

        with patch("builtins.print") as printed:
            rc = main([
                "--project",
                "xf",
                "--region",
                "europe-west1",
                "--spend-json",
                str(spend_path),
                "--dry-run",
            ])

        self.assertEqual(rc, 0)
        payload = json.loads(printed.call_args.args[0])
        self.assertEqual(payload["spend-check-status"], "ok")
        self.assertTrue(payload["paid-run-required"])
        self.assertEqual(payload["planned-vms"], 12)

    def test_when_spend_guard_refuses_then_paid_run_refuses(self) -> None:
        spend_path = Path("tmp/test-gcp-spend-refused.json")
        spend_path.parent.mkdir(parents=True, exist_ok=True)
        spend_path.write_text(
            json.dumps(
                SpendGuardResult(
                    False,
                    "refused",
                    19.0,
                    18.0,
                    "Spend too high.",
                ).to_mapping()
            ),
            encoding="utf-8",
        )

        rc = main([
            "--project",
            "xf",
            "--region",
            "europe-west1",
            "--spend-json",
            str(spend_path),
            "--confirm-paid-run",
        ])

        self.assertEqual(rc, 2)

    def test_when_spend_guard_allows_then_paid_run_submits_batch_command(self) -> None:
        spend_path = Path("tmp/test-gcp-spend-submit.json")
        spend_path.parent.mkdir(parents=True, exist_ok=True)
        spend_path.write_text(
            json.dumps(SpendGuardResult(True, "ok", 1.0, 18.0, "Spend is safe.").to_mapping()),
            encoding="utf-8",
        )

        with patch("subprocess.run") as run:
            rc = main([
                "--project",
                "xf",
                "--region",
                "europe-west1",
                "--spend-json",
                str(spend_path),
                "--confirm-paid-run",
            ])

        self.assertEqual(rc, 0)
        self.assertEqual(run.call_args.args[0][:3], ["gcloud", "batch", "jobs"])

    def test_when_preempted_then_result_record_is_retryable_local_only(self) -> None:
        config = BurstConfig("xf", "europe-west1", 20, 12, 18, 20, "c3-highcpu-8")
        spend = SpendGuardResult(False, "preempted", None, 18, "Shard was preempted.")

        record = build_result_record(config, "xf-mutation-123", spend)

        self.assertEqual(record["status"], "local_only")
        self.assertTrue(record["retryable"])

    def test_when_spend_file_is_invalid_then_plan_fails_closed(self) -> None:
        spend_path = Path("tmp/test-gcp-spend-invalid.json")
        spend_path.parent.mkdir(parents=True, exist_ok=True)
        spend_path.write_text("{", encoding="utf-8")
        args = parse_args([
            "--project",
            "xf",
            "--region",
            "europe-west1",
            "--spend-json",
            str(spend_path),
        ])

        plan = build_plan(args)

        self.assertFalse(plan.spend.allowed)
        self.assertEqual(plan.spend.status, "unavailable")

    def test_when_spend_file_has_bad_fields_then_plan_fails_closed(self) -> None:
        spend_path = Path("tmp/test-gcp-spend-bad-fields.json")
        spend_path.parent.mkdir(parents=True, exist_ok=True)
        spend_path.write_text(
            json.dumps({"allowed": "yes", "refuse_at_eur": "bad"}),
            encoding="utf-8",
        )
        args = parse_args([
            "--project",
            "xf",
            "--region",
            "europe-west1",
            "--spend-json",
            str(spend_path),
        ])

        plan = build_plan(args)

        self.assertFalse(plan.spend.allowed)
        self.assertEqual(plan.spend.status, "unavailable")


class GcpSpendGuardTests(unittest.TestCase):
    def test_when_guard_config_missing_values_then_validation_names_each_gap(self) -> None:
        config = SpendGuardConfig("", "bad-table", "", 0)

        self.assertEqual(
            config.validation_errors(),
            (
                "Billing project is required for the spend guard.",
                "Billing export table must be project.dataset.table.",
                "Google Cloud project is required for the spend guard.",
                "Spend refusal limit must be greater than zero.",
            ),
        )

    def test_when_query_built_then_project_filter_is_escaped(self) -> None:
        config = SpendGuardConfig("billing", "billing.dataset.table", "xf'prod", 18)

        query = build_month_to_date_query(config)

        self.assertIn("project.id = 'xf\\'prod'", query)

    def test_when_bq_command_built_then_it_uses_standard_sql(self) -> None:
        config = SpendGuardConfig("billing", "billing.dataset.table", "xf", 18)

        command = build_bq_command(config)

        self.assertEqual(command[:4], ["bq", "--project_id", "billing", "query"])
        self.assertIn("--use_legacy_sql=false", command)

    def test_when_spend_is_at_refusal_limit_then_guard_refuses(self) -> None:
        result = evaluate_billing_rows('[{"month_to_date_eur": "18.00"}]', refuse_at_eur=18.0)

        self.assertFalse(result.allowed)
        self.assertEqual(result.status, "refused")

    def test_when_billing_command_fails_then_guard_fails_closed(self) -> None:
        def failing_runner(*args: object, **kwargs: object) -> object:
            raise subprocess.TimeoutExpired("bq", 30)

        config = SpendGuardConfig("billing", "billing.dataset.table", "xf", 18.0)

        result = check_spend_guard(config, runner=failing_runner)

        self.assertFalse(result.allowed)
        self.assertEqual(result.status, "unavailable")

    def test_when_billing_rows_are_invalid_then_guard_fails_closed(self) -> None:
        result = evaluate_billing_rows('[{"wrong": "12.25"}]', refuse_at_eur=18.0)

        self.assertFalse(result.allowed)
        self.assertEqual(result.status, "unavailable")

    def test_when_runner_returns_json_then_guard_allows(self) -> None:
        completed = subprocess.CompletedProcess([], 0, stdout='[{"month_to_date_eur": "2.50"}]')

        def runner(*args: object, **kwargs: object) -> subprocess.CompletedProcess:
            return completed

        config = SpendGuardConfig("billing", "billing.dataset.table", "xf", 18)

        result = check_spend_guard(config, runner=runner)

        self.assertTrue(result.allowed)
        self.assertEqual(result.month_to_date_eur, 2.5)

    def test_when_spend_is_below_limit_then_guard_allows(self) -> None:
        result = evaluate_billing_rows('[{"month_to_date_eur": "12.25"}]', refuse_at_eur=18.0)

        self.assertTrue(result.allowed)
        self.assertEqual(result.status, "ok")

    def test_when_spend_guard_cli_is_dry_run_then_it_prints_command(self) -> None:
        with patch("builtins.print") as printed:
            rc = spend_guard_main([
                "--billing-project",
                "billing",
                "--billing-export-table",
                "billing.dataset.table",
                "--gcp-project",
                "xf",
                "--dry-run",
            ])

        self.assertEqual(rc, 0)
        self.assertIn("command", printed.call_args.args[0])

    def test_when_spend_guard_cli_has_missing_config_then_it_refuses(self) -> None:
        with patch("builtins.print"):
            rc = spend_guard_main([])

        self.assertEqual(rc, 2)


if __name__ == "__main__":
    unittest.main()
