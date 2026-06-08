from __future__ import annotations

import gzip
import importlib
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from unittest import skipUnless
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIClient

from apps.auto_issues.models import AutoIssue, FindBugsLearnedLesson

try:
    importlib.import_module("extensions.papertrail_dedup")
    _RUST_KERNEL_AVAILABLE = True
except ImportError:
    _RUST_KERNEL_AVAILABLE = False


@skipUnless(_RUST_KERNEL_AVAILABLE, "papertrail_dedup Rust kernel not built in this environment")
class FindBugsOperationalTests(TestCase):
    def setUp(self) -> None:
        AutoIssue.objects.filter(source=AutoIssue.SOURCE_RUST_DEFECT).delete()
        self.client = APIClient()
        self.client.force_authenticate(get_user_model().objects.create_user("operator"))

    def test_summary_endpoint_reports_deduped_counts_and_artifact_state(self):
        _issue("RUSTBUG-SEC-002", "critical")
        _issue("RUSTBUG-PERF-001", "high", status=AutoIssue.STATUS_RESOLVED)

        with TemporaryDirectory() as tmpdir:
            model_dir = Path(tmpdir) / "model"
            model_dir.mkdir()
            (model_dir / "latest.json").write_text(
                json.dumps({"status": "skipped", "reason": "embeddings_busy"}),
                encoding="utf-8",
            )
            (model_dir / "batch-checkpoint.json").write_text(
                json.dumps(
                    {
                        "progress": {
                            "total": 4,
                            "processed": 2,
                            "remaining": 2,
                            "state": "sleeping",
                        },
                        "updated_at": "2026-05-21T16:30:00Z",
                    }
                ),
                encoding="utf-8",
            )
            response = self.client.get(
                "/api/find-bugs/summary/",
                HTTP_X_FINDBUGS_ARTIFACT_ROOT=tmpdir,
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["counts"]["open"], 1)
        self.assertEqual(payload["counts"]["closed"], 1)
        self.assertEqual(payload["severity"]["critical"], 1)
        self.assertEqual(payload["level_a"]["statement"], 100)
        self.assertEqual(payload["artifacts"]["limit_bytes"], 1_073_741_824)
        self.assertEqual(payload["model"]["status"], "skipped")
        self.assertEqual(payload["model_batch"]["state"], "sleeping")

    def test_findings_endpoint_filters_search_and_dedupes_by_canonical(self):
        first = _issue("RUSTBUG-SEC-002", "critical", canonical="shared")
        _issue(
            "RUSTBUG-SEC-002", "critical", canonical="shared", title_suffix="duplicate"
        )
        _issue("RUSTBUG-PERF-001", "high", canonical="other")

        response = self.client.get("/api/find-bugs/findings/?search=SEC-002")

        self.assertEqual(response.status_code, 200)
        results = response.json()["results"]
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], first.id)
        self.assertEqual(results[0]["canonical_fingerprint"], "shared")
        self.assertEqual(results[0]["occurrence_count"], first.occurrence_count)
        self.assertEqual(results[0]["affected_files"], ["backend/apps/example.py"])
        self.assertIn("suggested_fix", results[0]["description"])

    def test_prune_action_deletes_old_artifacts_and_refuses_repo_root(self):
        from apps.auto_issues.services.findbugs import prune_findbugs_artifacts

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            old_file = root / "old.json"
            old_file.write_text("old", encoding="utf-8")
            stale_time = old_file.stat().st_mtime - (9 * 24 * 60 * 60)
            old_file.touch()
            import os

            os.utime(old_file, (stale_time, stale_time))

            result = prune_findbugs_artifacts(root=root, now=None)

            self.assertGreaterEqual(result["deleted_files"], 1)
            self.assertFalse(old_file.exists())

        with self.assertRaises(CommandError):
            prune_findbugs_artifacts(root=Path("/repo"), now=None)

    def test_degraded_observability_duplicate_files_health_issue_without_noise(self):
        first = _report(_bug_candidate("RUSTBUG-SEC-002"))
        degraded = _report(_bug_candidate("RUSTBUG-SEC-002"))
        degraded["metadata"]["observability_snapshot"] = {
            "healthy": False,
            "degraded_services": ["VictoriaMetrics"],
            "captured_at": "2026-05-21T16:30:00Z",
        }

        with TemporaryDirectory() as tmpdir:
            first_path = Path(tmpdir) / "first.json"
            degraded_path = Path(tmpdir) / "degraded.json"
            first_path.write_text(json.dumps(first), encoding="utf-8")
            degraded_path.write_text(json.dumps(degraded), encoding="utf-8")
            call_command("import_rust_findings", "--report", str(first_path))
            call_command("import_rust_findings", "--report", str(degraded_path))

        rust_rows = AutoIssue.objects.filter(source=AutoIssue.SOURCE_RUST_DEFECT)
        self.assertEqual(rust_rows.filter(title__contains="RUSTBUG-SEC-002").count(), 1)
        self.assertTrue(rust_rows.filter(title__contains="FindBugs health").exists())

    def test_full_speccheck_report_resolves_stale_findbugs_rows(self):
        first = _full_speccheck_report(_bug_candidate("RUSTBUG-SEC-002"))
        empty = _full_speccheck_report()

        with TemporaryDirectory() as tmpdir:
            first_path = Path(tmpdir) / "first.json"
            empty_path = Path(tmpdir) / "empty.json"
            first_path.write_text(json.dumps(first), encoding="utf-8")
            empty_path.write_text(json.dumps(empty), encoding="utf-8")
            call_command("import_rust_findings", "--report", str(first_path))
            call_command("import_rust_findings", "--report", str(empty_path))

        issue = AutoIssue.objects.get(source=AutoIssue.SOURCE_RUST_DEFECT)
        self.assertEqual(issue.status, AutoIssue.STATUS_RESOLVED)
        self.assertIn("Trap:", issue.lessons_learned)
        self.assertIn("Fix shape:", issue.lessons_learned)

    def test_false_positive_moves_to_deduped_compressed_learned_lesson(self):
        from apps.auto_issues.services.findbugs import move_issue_to_learned_lesson

        issue = _issue("RUSTBUG-SEC-002", "critical", canonical="lesson-shared")

        first = move_issue_to_learned_lesson(
            issue_id=issue.id,
            classification=FindBugsLearnedLesson.CLASS_FALSE_POSITIVE,
            lesson="Trap: scanner saw safe test data. Fix shape: ignore this fixture shape.",
            agent="codex",
        )
        second = move_issue_to_learned_lesson(
            issue_id=issue.id,
            classification=FindBugsLearnedLesson.CLASS_FALSE_POSITIVE,
            lesson="Trap: scanner saw safe test data. Fix shape: ignore this fixture shape.",
            agent="codex",
        )

        issue.refresh_from_db()
        first.refresh_from_db()
        self.assertEqual(issue.status, AutoIssue.STATUS_RESOLVED)
        self.assertEqual(first.id, second.id)
        self.assertEqual(first.occurrence_count, 2)
        self.assertLess(first.compressed_bytes, first.uncompressed_bytes)
        self.assertEqual(
            first.classification, FindBugsLearnedLesson.CLASS_FALSE_POSITIVE
        )

    def test_action_endpoints_confirm_check_report_and_sync_context(self):
        issue = _issue("RUSTBUG-SEC-002", "critical", canonical="action-shared")
        _issue(
            "RUSTBUG-SEC-002",
            "critical",
            canonical="action-shared",
            title_suffix="duplicate",
        )

        confirm = self.client.post(
            "/api/find-bugs/confirm/",
            {"issue_id": issue.id},
            format="json",
        )
        duplicate = self.client.post(
            "/api/find-bugs/duplicate-check/",
            {"issue_id": issue.id},
            format="json",
        )
        regression = self.client.post(
            "/api/find-bugs/regression-check/",
            {"issue_id": issue.id},
            format="json",
        )
        report = self.client.post("/api/find-bugs/generate-report/", {}, format="json")

        with TemporaryDirectory() as tmpdir:
            sync = self.client.post(
                "/api/find-bugs/sync-context/",
                {},
                format="json",
                HTTP_X_FINDBUGS_ARTIFACT_ROOT=tmpdir,
            )

        issue.refresh_from_db()
        self.assertEqual(confirm.status_code, 200)
        self.assertIn("confirmed as a real bug", issue.lessons_learned)
        self.assertEqual(duplicate.json()["duplicate_count"], 2)
        self.assertEqual(regression.json()["lesson_count"], 0)
        self.assertEqual(report.json()["summary"]["open"], 2)
        self.assertEqual(sync.status_code, 200)
        self.assertEqual(sync.json()["status"], "ok")

    def test_generated_report_compares_findbugs_with_glitchtip_and_sonarqube(self):
        from apps.auto_issues.services.findbugs import generate_findbugs_report

        _issue("RUSTBUG-SEC-002", "critical", canonical="shared-glitchtip")
        _issue("RUSTBUG-PERF-001", "high", canonical="shared-sonarqube")
        _issue("RUSTBUG-RES-001", "medium", canonical="rust-only")
        _external_issue(AutoIssue.SOURCE_GLITCHTIP, canonical="shared-glitchtip")
        _external_issue(AutoIssue.SOURCE_SONARQUBE, canonical="shared-sonarqube")

        report = generate_findbugs_report()

        self.assertEqual(
            report["source_comparison"],
            {
                "findbugs_total": 3,
                "glitchtip_overlap": 1,
                "sonarqube_overlap": 1,
                "findbugs_unique": 1,
                "unique_fingerprints": ["rust-only"],
            },
        )

    def test_approve_lesson_endpoint_marks_latest_issue_lesson_approved(self):
        from apps.auto_issues.services.findbugs import move_issue_to_learned_lesson

        issue = _issue("RUSTBUG-SEC-002", "critical", canonical="approve-lesson")
        lesson = move_issue_to_learned_lesson(
            issue_id=issue.id,
            classification=FindBugsLearnedLesson.CLASS_FALSE_POSITIVE,
            lesson="Trap: scanner matched a documented safe fixture. Fix shape: approve the lesson before future agents use it.",
            agent="codex",
        )

        response = self.client.post(
            "/api/find-bugs/approve-lesson/",
            {"issue_id": issue.id},
            format="json",
        )

        lesson.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(lesson.approved)
        self.assertEqual(response.json()["lesson_id"], lesson.id)

    @patch("apps.auto_issues.services.findbugs.subprocess.run")
    @patch("apps.auto_issues.services.findbugs._findbugs_model_resource_comfort")
    @patch.dict(
        "apps.auto_issues.services.findbugs.os.environ",
        {
            "FINDBUGS_SMOLLM2_SERVER_URL": "",
            "FINDBUGS_SMOLLM2_RUNNER": "/missing/llama-cli",
            "FINDBUGS_SMOLLM2_MODEL": "/missing/smollm2.gguf",
        },
    )
    def test_smollm2_advisory_runs_when_embeddings_are_busy_and_records_comfort(
        self,
        comfort_mock,
        run_mock,
    ):
        from apps.auto_issues.services.findbugs import maybe_run_smollm2_advisory

        comfort_mock.return_value = {
            "comfortable": False,
            "embedding_busy": True,
            "reason": "embedding_queue_pressure",
            "autoissue": 123,
        }
        run_mock.return_value.returncode = 0
        run_mock.return_value.stdout = '{"patterns": []}'
        run_mock.return_value.stderr = ""

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            runner = root / "llama-cli"
            model = root / "smollm2.gguf"
            runner.write_text("#!/bin/sh\n", encoding="utf-8")
            runner.chmod(0o755)
            model.write_text("model", encoding="utf-8")

            result = maybe_run_smollm2_advisory(
                root=root,
                embedding_busy=lambda: True,
                runner_path=runner,
                model_path=model,
            )

            artifact = root / "model" / "latest.json"
            status_payload = json.loads(artifact.read_text(encoding="utf-8"))

        self.assertEqual(result["status"], "ok")
        self.assertEqual(
            result["resource_comfort"]["reason"], "embedding_queue_pressure"
        )
        self.assertEqual(status_payload["model"], "SmolLM2-1.7B-Instruct Q4_K_S")
        self.assertEqual(status_payload["status"], "ok")
        self.assertFalse(status_payload["resource_comfort"]["comfortable"])
        run_mock.assert_called_once()
        command = run_mock.call_args.args[0]
        self.assertIn("--single-turn", command)
        self.assertIn("--simple-io", command)
        self.assertEqual(command[command.index("-n") + 1], "32")
        self.assertEqual(command[command.index("-c") + 1], "512")
        self.assertEqual(command[command.index("-b") + 1], "64")
        self.assertEqual(command[command.index("-ub") + 1], "64")

    def test_victoriametrics_pressure_files_deduped_findbugs_tuning_issue(self):
        from apps.auto_issues.services import findbugs

        def fake_query(query: str) -> float | None:
            if "xf_queue_depth" in query:
                return 42.0
            if "up{" in query:
                return 1.0
            return None

        with patch.object(
            findbugs, "_victoriametrics_instant_query", side_effect=fake_query
        ):
            first = findbugs._findbugs_model_resource_comfort(embedding_busy=True)
            second = findbugs._findbugs_model_resource_comfort(embedding_busy=True)

        self.assertFalse(first["comfortable"])
        self.assertEqual(first["reason"], "embedding_queue_pressure")
        self.assertEqual(second["autoissue"], first["autoissue"])
        self.assertEqual(
            AutoIssue.objects.filter(
                source=AutoIssue.SOURCE_RUST_DEFECT,
                title__contains="model resource tuning needed",
            ).count(),
            1,
        )

    def test_missing_smollm2_runner_or_model_files_health_issue(self):
        from apps.auto_issues.services.findbugs import maybe_run_smollm2_advisory

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)

            missing_runner = root / "missing-llama-cli"
            missing_model = root / "missing-smollm2.gguf"

            with patch.dict(
                "apps.auto_issues.services.findbugs.os.environ",
                {"FINDBUGS_SMOLLM2_SERVER_URL": ""},
            ):
                result = maybe_run_smollm2_advisory(
                    root=root,
                    embedding_busy=lambda: False,
                    runner_path=missing_runner,
                    model_path=missing_model,
                )
                second = maybe_run_smollm2_advisory(
                    root=root,
                    embedding_busy=lambda: False,
                    runner_path=missing_runner,
                    model_path=missing_model,
                )

        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["reason"], "runner_or_model_missing")
        self.assertEqual(second["autoissue"], result["autoissue"])
        self.assertEqual(
            AutoIssue.objects.filter(
                source=AutoIssue.SOURCE_RUST_DEFECT,
                title__contains="model runner or GGUF missing",
            ).count(),
            1,
        )

    @patch("apps.auto_issues.services.findbugs.subprocess.run")
    @patch("apps.auto_issues.services.findbugs.urllib.request.urlopen")
    @patch("apps.auto_issues.services.findbugs._findbugs_model_resource_comfort")
    @patch.dict(
        "apps.auto_issues.services.findbugs.os.environ",
        {
            "FINDBUGS_SMOLLM2_SERVER_URL": "http://10.10.10.91:8088",
            "FINDBUGS_SMOLLM2_DISABLE_DEFAULT_SERVER": "true",
        },
    )
    def test_smollm2_advisory_uses_mint_cable_server_from_environment(
        self,
        comfort_mock,
        urlopen_mock,
        run_mock,
    ):
        from apps.auto_issues.services.findbugs import maybe_run_smollm2_advisory

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def read(self):
                return b'{"content":"{\\"patterns\\": []}"}'

        comfort_mock.return_value = {
            "comfortable": True,
            "embedding_busy": False,
            "reason": "metrics_comfortable",
        }
        urlopen_mock.return_value = Response()

        with TemporaryDirectory() as tmpdir:
            result = maybe_run_smollm2_advisory(root=Path(tmpdir))

        request = urlopen_mock.call_args.args[0]
        body = json.loads(request.data.decode("utf-8"))
        self.assertEqual(request.full_url, "http://10.10.10.91:8088/completion")
        self.assertEqual(body["n_predict"], 32)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["reason"], "server_completed")
        run_mock.assert_not_called()
        self.assertFalse(
            AutoIssue.objects.filter(
                source=AutoIssue.SOURCE_RUST_DEFECT,
                title__contains="FindBugs health",
            ).exists(),
        )

    @patch("apps.auto_issues.services.findbugs._find_speccheck_binary")
    @patch("apps.auto_issues.services.findbugs.subprocess.run")
    def test_run_scan_imports_findbugs_rows_when_ai_model_is_removed(
        self,
        run_mock,
        binary_mock,
    ):
        from apps.auto_issues.services import findbugs

        binary_mock.return_value = Path("/bin/true")
        run_mock.return_value = _completed(
            json.dumps(_report(_bug_candidate("RUSTBUG-SEC-002")))
        )

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source = root / "source.py"
            source.write_text("return pickle.loads(request.body)\n", encoding="utf-8")
            with patch.object(findbugs, "DEFAULT_ARTIFACT_ROOT", root):
                with patch.object(
                    findbugs, "_iter_findbugs_source_files", return_value=[source]
                ):
                    result = findbugs.run_findbugs_scan()

            status_path = root / "model" / "latest.json"
            status_payload = json.loads(status_path.read_text(encoding="utf-8"))

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["model"]["status"], "removed")
        self.assertEqual(status_payload["reason"], "operator_removed_ai_model")
        self.assertEqual(result["imported"]["created"], 1)
        self.assertFalse(
            AutoIssue.objects.filter(
                source=AutoIssue.SOURCE_RUST_DEFECT,
                title__contains="model runner or GGUF missing",
            ).exists(),
        )

    @patch("apps.auto_issues.services.findbugs._find_speccheck_binary")
    @patch("apps.auto_issues.services.findbugs.subprocess.run")
    def test_run_scan_calls_real_speccheck_file_shape_and_writes_merged_report(
        self,
        run_mock,
        binary_mock,
    ):
        from apps.auto_issues.services import findbugs

        binary_mock.return_value = Path("/opt/xf/compiled/active/speccheck")

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            first = root / "first.py"
            second = root / "second.py"
            first.write_text("return pickle.loads(request.body)\n", encoding="utf-8")
            second.write_text("with open(path): pass\n", encoding="utf-8")
            reports = [
                _report(_bug_candidate("RUSTBUG-SEC-002")),
                _report(_bug_candidate("RUSTBUG-RES-001")),
            ]
            run_mock.side_effect = [
                _completed(json.dumps(report)) for report in reports
            ]

            with patch.object(findbugs, "DEFAULT_ARTIFACT_ROOT", root):
                with patch.object(
                    findbugs,
                    "_iter_findbugs_source_files",
                    return_value=[first, second],
                    create=True,
                ):
                    result = findbugs.run_findbugs_scan()

            merged = json.loads(Path(result["report"]).read_text(encoding="utf-8"))

        self.assertEqual(result["status"], "ok")
        self.assertEqual(len(merged["bug_candidates"]), 2)
        self.assertEqual(merged["summary"]["scanned_files"], 2)
        self.assertEqual(merged["metadata"]["scanner_version"], "speccheck")
        self.assertEqual(
            [call.args[0][0:2] for call in run_mock.call_args_list],
            [
                ["/opt/xf/compiled/active/speccheck", "find-bugs"],
                ["/opt/xf/compiled/active/speccheck", "find-bugs"],
            ],
        )

    @patch("apps.auto_issues.services.findbugs._find_speccheck_binary")
    @patch("apps.auto_issues.services.findbugs.subprocess.run")
    def test_run_scan_imports_confirmed_findbugs_rows_to_autoissues(
        self,
        run_mock,
        binary_mock,
    ):
        from apps.auto_issues.services import findbugs

        binary_mock.return_value = Path("/opt/xf/compiled/active/speccheck")

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source = root / "source.py"
            source.write_text("return pickle.loads(request.body)\n", encoding="utf-8")
            run_mock.return_value = _completed(
                json.dumps(_report(_bug_candidate("RUSTBUG-SEC-002")))
            )

            with patch.object(findbugs, "DEFAULT_ARTIFACT_ROOT", root):
                with patch.object(
                    findbugs,
                    "_iter_findbugs_source_files",
                    return_value=[source],
                    create=True,
                ):
                    result = findbugs.run_findbugs_scan()

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["imported"]["created"], 1)
        self.assertEqual(
            AutoIssue.objects.filter(
                source=AutoIssue.SOURCE_RUST_DEFECT,
                title__contains="RUSTBUG-SEC-002",
            ).count(),
            1,
        )

    def test_refresh_knowledge_writes_compressed_artifact(self):
        from apps.auto_issues.services.findbugs import refresh_findbugs_knowledge

        _issue("RUSTBUG-SEC-002", "critical", canonical="knowledge-open")

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            result = refresh_findbugs_knowledge(root=root)
            artifact = Path(result["artifact"])
            payload = json.loads(gzip.decompress(artifact.read_bytes()).decode("utf-8"))

        self.assertEqual(result["status"], "ok")
        self.assertEqual(artifact.name, "latest.json.gz")
        self.assertEqual(payload["open"], 1)

    def test_source_walker_skips_local_virtual_environment_packages(self):
        from apps.auto_issues.services import findbugs

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            app_file = root / "backend" / "apps" / "example.py"
            venv_file = root / ".venv" / "Lib" / "site-packages" / "vendor.py"
            static_file = root / "backend" / "static" / "chunk.js"
            build_test_file = (
                root / "backend" / "extensions" / "build_tests" / "test.cpp"
            )
            test_file = root / "backend" / "apps" / "tests_example.py"
            compiled_ts_file = root / "frontend" / "out-tsc" / "app" / "component.js"
            app_file.parent.mkdir(parents=True)
            venv_file.parent.mkdir(parents=True)
            static_file.parent.mkdir(parents=True)
            build_test_file.parent.mkdir(parents=True)
            test_file.parent.mkdir(parents=True, exist_ok=True)
            compiled_ts_file.parent.mkdir(parents=True)
            app_file.write_text("pickle.loads(request.body)\n", encoding="utf-8")
            venv_file.write_text(
                "this file belongs to a dependency\n", encoding="utf-8"
            )
            static_file.write_text("observable.subscribe(value)\n", encoding="utf-8")
            build_test_file.write_text("if (x = y) { return x; }\n", encoding="utf-8")
            test_file.write_text("eval(user_input)\n", encoding="utf-8")
            compiled_ts_file.write_text("thing.subscribe(value)\n", encoding="utf-8")

            with patch.object(findbugs.settings, "REPO_ROOT", str(root), create=True):
                files = findbugs._iter_findbugs_source_files()

        self.assertEqual(files, [app_file])

    @patch("apps.observability.services.stack_status.build_stack_status")
    def test_observability_snapshot_names_degraded_services_from_stack_payload(
        self,
        stack_status_mock,
    ):
        from apps.auto_issues.services import findbugs

        stack_status_mock.return_value = [
            {"service_name": "VictoriaMetrics", "state": "planned_only"},
            {"service_name": "Grafana", "state": "healthy"},
        ]

        snapshot = findbugs._observability_snapshot()

        self.assertFalse(snapshot["healthy"])
        self.assertEqual(snapshot["degraded_services"], ["VictoriaMetrics"])

    @patch("apps.auto_issues.services.findbugs.subprocess.run")
    @patch.dict(
        "apps.auto_issues.services.findbugs.os.environ",
        {"FINDBUGS_SMOLLM2_SERVER_URL": ""},
    )
    def test_smollm2_advisory_runs_local_runner_when_idle(self, run_mock):
        from apps.auto_issues.services.findbugs import maybe_run_smollm2_advisory

        run_mock.return_value.returncode = 0
        run_mock.return_value.stdout = '{"patterns": [{"id": "candidate"}]}'
        run_mock.return_value.stderr = ""

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            runner = root / "llama-cli"
            model = root / "smollm2.gguf"
            runner.write_text("#!/bin/sh\n", encoding="utf-8")
            runner.chmod(0o755)
            model.write_text("model", encoding="utf-8")

            result = maybe_run_smollm2_advisory(
                root=root,
                embedding_busy=lambda: False,
                runner_path=runner,
                model_path=model,
                prompt="summarize bug candidates",
            )
            output_payload = json.loads(
                Path(result["artifact"]).read_text(encoding="utf-8")
            )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["reason"], "runner_completed")
        self.assertIn("candidate", output_payload["raw_output"])
        self.assertEqual(AutoIssue.objects.filter(title__contains="SmolLM2").count(), 0)
        run_mock.assert_called_once()
        command = run_mock.call_args.args[0]
        self.assertIn("--single-turn", command)
        self.assertIn("--simple-io", command)
        self.assertEqual(command[command.index("-n") + 1], "32")
        self.assertEqual(command[command.index("-c") + 1], "512")
        self.assertEqual(command[command.index("-b") + 1], "64")
        self.assertEqual(command[command.index("-ub") + 1], "64")

    @patch("apps.auto_issues.services.findbugs.subprocess.run")
    @patch.dict(
        "apps.auto_issues.services.findbugs.os.environ",
        {"FINDBUGS_SMOLLM2_SERVER_URL": ""},
    )
    def test_smollm2_advisory_files_health_issue_when_local_runner_fails(
        self, run_mock
    ):
        from apps.auto_issues.services.findbugs import maybe_run_smollm2_advisory

        run_mock.return_value.returncode = 137
        run_mock.return_value.stdout = ""
        run_mock.return_value.stderr = "Killed"

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            runner = root / "llama-cli"
            model = root / "smollm2.gguf"
            runner.write_text("#!/bin/sh\n", encoding="utf-8")
            runner.chmod(0o755)
            model.write_text("model", encoding="utf-8")

            result = maybe_run_smollm2_advisory(
                root=root,
                embedding_busy=lambda: False,
                runner_path=runner,
                model_path=model,
            )
            status_payload = json.loads(
                (root / "model" / "latest.json").read_text(encoding="utf-8")
            )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["reason"], "runner_failed")
        self.assertEqual(status_payload["reason"], "runner_failed")
        self.assertEqual(status_payload["autoissue"], result["autoissue"])
        self.assertEqual(
            AutoIssue.objects.filter(
                source=AutoIssue.SOURCE_RUST_DEFECT,
                title__contains="model runner failed",
            ).count(),
            1,
        )

    @patch("apps.auto_issues.services.findbugs.subprocess.run")
    @patch.dict(
        "apps.auto_issues.services.findbugs.os.environ",
        {"FINDBUGS_SMOLLM2_SERVER_URL": ""},
    )
    def test_smollm2_advisory_files_health_issue_when_local_runner_times_out(
        self, run_mock
    ):
        from apps.auto_issues.services.findbugs import maybe_run_smollm2_advisory

        run_mock.side_effect = subprocess.TimeoutExpired(
            cmd=["llama-cli"],
            timeout=60,
            output="partial output",
            stderr="still loading",
        )

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            runner = root / "llama-cli"
            model = root / "smollm2.gguf"
            runner.write_text("#!/bin/sh\n", encoding="utf-8")
            runner.chmod(0o755)
            model.write_text("model", encoding="utf-8")

            result = maybe_run_smollm2_advisory(
                root=root,
                embedding_busy=lambda: False,
                runner_path=runner,
                model_path=model,
            )
            status_payload = json.loads(
                (root / "model" / "latest.json").read_text(encoding="utf-8")
            )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["reason"], "runner_timeout")
        self.assertEqual(status_payload["reason"], "runner_timeout")

    @patch("apps.auto_issues.services.findbugs.subprocess.run")
    @patch("apps.auto_issues.services.findbugs.urllib.request.urlopen")
    def test_smollm2_advisory_prefers_warm_llama_server(self, urlopen_mock, run_mock):
        from apps.auto_issues.services.findbugs import maybe_run_smollm2_advisory

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def read(self):
                return b'{"content":"{\\"patterns\\": []}"}'

        urlopen_mock.return_value = Response()

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            result = maybe_run_smollm2_advisory(
                root=root,
                embedding_busy=lambda: False,
                server_url="http://findbugs-model-server:8080",
            )
            payload = json.loads(Path(result["artifact"]).read_text(encoding="utf-8"))

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["reason"], "server_completed")
        self.assertEqual(payload["model"], "SmolLM2-1.7B-Instruct Q4_K_S")
        self.assertIn("patterns", payload["raw_output"])
        run_mock.assert_not_called()

    @patch("apps.auto_issues.services.findbugs._embeddings_are_busy", return_value=True)
    @patch("apps.auto_issues.services.findbugs.maybe_run_smollm2_advisory")
    def test_model_batch_reports_removed_without_advisory(
        self, advisory_mock, busy_mock
    ):
        from apps.auto_issues.services.findbugs import run_smollm2_batch_advisory

        _issue("RUSTBUG-SEC-002", "critical", canonical="embedding-busy")

        result = run_smollm2_batch_advisory(max_items=10)

        self.assertEqual(result["status"], "removed")
        self.assertEqual(result["reason"], "operator_removed_ai_model")
        advisory_mock.assert_not_called()
        busy_mock.assert_not_called()

    def test_model_batch_writes_removed_status_artifact_without_checkpoint(self):
        from apps.auto_issues.services.findbugs import run_smollm2_batch_advisory

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            result = run_smollm2_batch_advisory(max_items=10, root=root)
            status_payload = json.loads(
                (root / "model" / "latest.json").read_text(encoding="utf-8")
            )

        self.assertEqual(result["status"], "removed")
        self.assertEqual(result["reason"], "operator_removed_ai_model")
        self.assertEqual(status_payload["status"], "removed")
        self.assertEqual(status_payload["reason"], "operator_removed_ai_model")
        self.assertFalse((root / "model" / "batch-checkpoint.json").exists())

    def test_model_batch_ignores_legacy_pause_file_when_model_removed(self):
        from apps.auto_issues.services.findbugs import run_smollm2_batch_advisory

        with TemporaryDirectory() as tmpdir:
            pause_file = Path(tmpdir) / "model" / "pause"
            pause_file.parent.mkdir()
            pause_file.write_text("pause", encoding="utf-8")
            result = run_smollm2_batch_advisory(max_items=10, root=Path(tmpdir))

        self.assertEqual(result["status"], "removed")
        self.assertEqual(result["reason"], "operator_removed_ai_model")


class FindBugsScheduleTests(SimpleTestCase):
    def test_findbugs_tasks_are_scheduled_for_scan_prune_and_knowledge_refresh(self):
        from config.settings.celery_schedules import CELERY_BEAT_SCHEDULE

        self.assertEqual(
            CELERY_BEAT_SCHEDULE["findbugs-run-scan"]["task"],
            "findbugs.run_scan",
        )
        self.assertNotIn("findbugs-model-advisory", CELERY_BEAT_SCHEDULE)
        self.assertEqual(
            CELERY_BEAT_SCHEDULE["findbugs-prune-artifacts"]["task"],
            "findbugs.prune_artifacts",
        )
        self.assertEqual(
            CELERY_BEAT_SCHEDULE["findbugs-refresh-knowledge"]["task"],
            "findbugs.refresh_knowledge",
        )

    def test_removed_model_advisory_task_is_registered_but_not_scheduled(self):
        from apps.auto_issues.tasks import removed_findbugs_model_advisory_task
        from config.settings.celery_schedules import CELERY_BEAT_SCHEDULE

        result = removed_findbugs_model_advisory_task()

        self.assertEqual(result["status"], "removed")
        self.assertEqual(result["reason"], "operator_removed_ai_model")
        self.assertNotIn("findbugs-model-advisory", CELERY_BEAT_SCHEDULE)
        self.assertNotIn(
            "findbugs.run_model_advisory",
            {entry["task"] for entry in CELERY_BEAT_SCHEDULE.values()},
        )


def _issue(
    pattern: str,
    severity: str,
    *,
    status: str = AutoIssue.STATUS_OPEN,
    canonical: str | None = None,
    title_suffix: str = "",
) -> AutoIssue:
    return AutoIssue.objects.create(
        source=AutoIssue.SOURCE_RUST_DEFECT,
        external_id=f"{pattern}:{title_suffix or 'base'}",
        fingerprint=f"{pattern}:{title_suffix or 'base'}",
        canonical_fingerprint=canonical or f"{pattern}:{title_suffix or 'base'}",
        title=f"[{pattern}] Potential bug pattern {title_suffix}",
        description=json.dumps(
            {
                "bug_pattern_id": pattern,
                "message": "Finding details",
                "line": 7,
                "suggested_fix": "Fix it",
                "confidence": "high",
            }
        ),
        affected_files=["backend/apps/example.py"],
        severity=severity,
        status=status,
        priority_score=100.0 if severity == "critical" else 80.0,
    )


def _external_issue(source: str, *, canonical: str) -> AutoIssue:
    return AutoIssue.objects.create(
        source=source,
        external_id=f"{source}:{canonical}",
        fingerprint=f"{source}:{canonical}",
        canonical_fingerprint=canonical,
        title=f"[{source}] Matching finding",
        description="External scanner found the same root cause.",
        severity=AutoIssue.SEVERITY_HIGH,
        status=AutoIssue.STATUS_OPEN,
        priority_score=70.0,
    )


def _report(candidate: dict) -> dict:
    return {
        "metadata": {"tool": "speccheck"},
        "parsed_behaviors": [],
        "test_case_candidates": [],
        "bug_candidates": [candidate],
        "duplicate_warnings": [],
        "stale_record_warnings": [],
        "summary": {},
    }


def _full_speccheck_report(*candidates: dict) -> dict:
    report = _report(_bug_candidate("RUSTBUG-SEC-002"))
    report["metadata"] = {"scanner_version": "speccheck", "source_roots": ["/repo"]}
    report["bug_candidates"] = list(candidates)
    return report


def _bug_candidate(pattern_id: str) -> dict:
    return {
        "bug_pattern_id": pattern_id,
        "title": "Unsafe request deserialisation",
        "description": "Request data is deserialised with pickle.",
        "severity": "critical",
        "category": "security",
        "file": "backend/apps/example.py",
        "line": 7,
        "evidence": "pickle.loads(request.body)",
        "suggested_fix": "Use JSON and validate the schema.",
        "confidence": "high",
        "citation": "doi:10.1145/1052883.1052895",
        "fingerprint": f"{pattern_id}:backend/apps/example.py:7",
        "priority_score": 100.0,
    }


def _completed(stdout: str):
    class Completed:
        returncode = 0
        stderr = ""

        def __init__(self, stdout: str) -> None:
            self.stdout = stdout

    return Completed(stdout)
