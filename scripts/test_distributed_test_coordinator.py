"""Tests for the distributed quality coordinator dry-run."""

from __future__ import annotations

from pathlib import Path
from unittest import TestCase

import distributed_test_coordinator as coordinator


class TestDistributedCoordinator(TestCase):
    def test_preflight_check_count_is_twelve(self) -> None:
        self.assertEqual(len(coordinator.PREFLIGHT_CHECKS), 12)
        self.assertIn("msi-docker-free", coordinator.PREFLIGHT_CHECKS)

    def test_all_default_shards_are_dell_only(self) -> None:
        plan = coordinator.build_plan("proof", 30)
        placements = {shard["placement"] for shard in plan["shards"]}
        self.assertEqual(placements, {"dell"})

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
