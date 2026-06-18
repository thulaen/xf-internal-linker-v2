"""Tests for the distributed quality coordinator dry-run."""

from __future__ import annotations

import json
from pathlib import Path
from unittest import TestCase

import distributed_test_coordinator as coordinator
from gcp_spend_guard import SpendGuardResult


class TestDistributedCoordinator(TestCase):
    def test_preflight_check_count_is_twelve(self) -> None:
        self.assertEqual(len(coordinator.PREFLIGHT_CHECKS), 12)
        self.assertIn("msi-docker-free", coordinator.PREFLIGHT_CHECKS)

    def test_all_default_shards_are_dell_only(self) -> None:
        plan = coordinator.build_plan("proof", 30)
        placements = {shard["placement"] for shard in plan["shards"]}
        self.assertEqual(placements, {"dell"})
        self.assertEqual(plan["burst"]["status"], "local-only")

    def test_when_gcp_burst_requested_and_spend_ok_then_gcp_shards_are_planned(self) -> None:
        spend = SpendGuardResult(True, "ok", 1.0, 18.0, "Spend is safe.")

        plan = coordinator.build_plan("proof", 30, burst="gcp", full=True, spend=spend)

        placements = {shard["placement"] for shard in plan["shards"]}
        self.assertIn("gcp-spot", placements)
        self.assertEqual(plan["burst"]["status"], "planned")

    def test_when_gcp_spend_unavailable_then_plan_stays_local_only(self) -> None:
        spend = SpendGuardResult.fail_closed("Spend guard missing.")

        plan = coordinator.build_plan("proof", 30, burst="gcp", full=True, spend=spend)

        placements = {shard["placement"] for shard in plan["shards"]}
        self.assertEqual(placements, {"dell"})
        self.assertEqual(plan["burst"]["status"], "local-only")

    def test_when_gcp_shards_render_then_node_selector_marks_cloud_burst(self) -> None:
        spend = SpendGuardResult(True, "ok", 1.0, 18.0, "Spend is safe.")
        plan = coordinator.build_plan("proof", 30, burst="gcp", full=True, spend=spend)

        rendered = coordinator.render_shard_jobs(plan)

        self.assertIn('xf.io/cloud-burst: "gcp"', rendered)

    def test_main_refuses_to_write_jobs_without_dry_run(self) -> None:
        rc = coordinator.main(["--run-id", "proof"])

        self.assertEqual(rc, 2)

    def test_main_dry_run_writes_expected_outputs(self) -> None:
        outdir = Path("tmp/test-distributed-main")

        rc = coordinator.main(["--dry-run", "--run-id", "proof-main", "--outdir", str(outdir)])

        self.assertEqual(rc, 0)
        self.assertTrue((outdir / "final-report.md").exists())

    def test_main_gcp_full_dry_run_writes_planned_gcp_shards(self) -> None:
        outdir = Path("tmp/test-distributed-main-gcp")

        rc = coordinator.main([
            "--dry-run",
            "--burst",
            "gcp",
            "--full",
            "--run-id",
            "proof-gcp",
            "--outdir",
            str(outdir),
        ])

        self.assertEqual(rc, 0)
        plan = json.loads((outdir / "plan.json").read_text(encoding="utf-8"))
        self.assertEqual(plan["burst"]["status"], "planned")
        self.assertIn("gcp-spot", {shard["placement"] for shard in plan["shards"]})

    def test_job_templates_include_timeout(self) -> None:
        plan = coordinator.build_plan("proof", 7)
        self.assertIn("activeDeadlineSeconds: 420", coordinator.render_shard_jobs(plan))
        self.assertIn("activeDeadlineSeconds: 420", coordinator.render_merge_job(plan))

    def test_final_report_lists_failures(self) -> None:
        plan = coordinator.build_plan("proof", 30)
        report = coordinator.render_final_report(plan, ["python-tests timed out"])
        self.assertIn("Status: failed", report)
        self.assertIn("python-tests timed out", report)

    def test_write_outputs_creates_expected_files(self) -> None:
        outdir = Path("tmp/test-distributed-coordinator")
        plan = coordinator.build_plan("proof", 5)
        coordinator.write_outputs(plan, outdir)
        self.assertTrue((outdir / "plan.json").exists())
        self.assertTrue((outdir / "shard-jobs.yaml").exists())
        self.assertTrue((outdir / "merge-job.yaml").exists())
        self.assertTrue((outdir / "final-report.md").exists())
