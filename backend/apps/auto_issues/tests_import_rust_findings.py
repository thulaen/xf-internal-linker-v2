from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from apps.auto_issues.models import AutoIssue
from apps.auto_issues.services import rust_findings
from apps.paper_trail.services import dedup as paper_trail_dedup


class RustFindingsImportTests(TestCase):
    def setUp(self) -> None:
        AutoIssue.objects.filter(source=AutoIssue.SOURCE_RUST_DEFECT).delete()

    def test_import_creates_and_reimports_without_duplicates(self):
        report = {
            "metadata": {"tool": "speccheck"},
            "parsed_behaviors": [],
            "test_case_candidates": [],
            "bug_candidates": [_bug_candidate("RUSTBUG-PERF-001")],
            "duplicate_warnings": [],
            "stale_record_warnings": [],
            "summary": {},
        }

        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "speccheck.json"
            path.write_text(json.dumps(report), encoding="utf-8")
            call_command("import_rust_findings", "--report", str(path))
            call_command("import_rust_findings", "--report", str(path))

        rows = AutoIssue.objects.filter(source=AutoIssue.SOURCE_RUST_DEFECT)
        self.assertEqual(rows.count(), 1)
        issue = rows.get()
        self.assertEqual(issue.occurrence_count, 2)
        self.assertEqual(issue.affected_files, ["backend/apps/example.py"])
        self.assertIn("RUSTBUG-PERF-001", issue.title)

    def test_malformed_payload_rejects_without_partial_rows(self):
        report = {
            "metadata": {},
            "parsed_behaviors": [],
            "test_case_candidates": [],
            "bug_candidates": [{"bug_pattern_id": "RUSTBUG-CORR-001"}],
            "duplicate_warnings": [],
            "stale_record_warnings": [],
            "summary": {},
        }

        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "broken.json"
            path.write_text(json.dumps(report), encoding="utf-8")
            with self.assertRaisesMessage(CommandError, "missing required field"):
                call_command("import_rust_findings", "--report", str(path))

        self.assertFalse(AutoIssue.objects.filter(source="rust_defect").exists())

    def test_native_minhash_merges_near_duplicate_bug_candidates(self):
        first = _bug_candidate("RUSTBUG-PERF-001")
        second = _bug_candidate(
            "RUSTBUG-PERF-001",
            line=43,
            evidence=(
                "for parent in parent_rows: "
                "Child.objects.filter(parent=parent).first()"
            ),
            fingerprint="RUSTBUG-PERF-001:backend/apps/example.py:43",
        )

        with TemporaryDirectory() as tmpdir:
            first_path = Path(tmpdir) / "first.json"
            second_path = Path(tmpdir) / "second.json"
            first_path.write_text(json.dumps(_report(first)), encoding="utf-8")
            second_path.write_text(json.dumps(_report(second)), encoding="utf-8")
            call_command("import_rust_findings", "--report", str(first_path))
            call_command("import_rust_findings", "--report", str(second_path))

        rows = AutoIssue.objects.filter(source=AutoIssue.SOURCE_RUST_DEFECT)
        self.assertEqual(rows.count(), 1)
        issue = rows.get()
        self.assertEqual(issue.occurrence_count, 2)
        self.assertEqual(len(issue.source_observations), 2)

    def test_import_accepts_all_35_speccheck_bug_patterns_idempotently(self):
        candidates = [
            _bug_candidate(
                pattern_id,
                title=f"{pattern_id} fixture",
                description=f"Fixture description for {pattern_id}.",
                category=category,
                severity=severity,
                line=index,
                evidence=f"{pattern_id} unique source evidence",
                file=f"backend/apps/example_{index}.py",
                fingerprint=f"{pattern_id}:backend/apps/example_{index}.py:{index}",
                priority_score=priority_score,
            )
            for index, (pattern_id, category, severity, priority_score) in enumerate(
                _all_bug_patterns(),
                start=1,
            )
        ]

        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "all-bugs.json"
            path.write_text(json.dumps(_report_many(candidates)), encoding="utf-8")
            call_command("import_rust_findings", "--report", str(path))
            call_command("import_rust_findings", "--report", str(path))

        rows = AutoIssue.objects.filter(source=AutoIssue.SOURCE_RUST_DEFECT)
        self.assertEqual(rows.count(), 35)
        self.assertEqual(
            rows.filter(occurrence_count=2).count(),
            35,
        )
        self.assertEqual(
            set(rows.values_list("category__key", flat=True)),
            {"performance", "correctness", "concurrency", "resources", "security"},
        )

    def test_existing_occurrence_counts_batches_lookup(self):
        AutoIssue.objects.create(
            source=AutoIssue.SOURCE_RUST_DEFECT,
            external_id="rust_defect:RUSTBUG-PERF-001:aaa",
            fingerprint="aaa",
            title="Existing one",
            severity=AutoIssue.SEVERITY_HIGH,
            occurrence_count=3,
        )
        AutoIssue.objects.create(
            source=AutoIssue.SOURCE_RUST_DEFECT,
            external_id="rust_defect:RUSTBUG-PERF-002:bbb",
            fingerprint="bbb",
            title="Existing two",
            severity=AutoIssue.SEVERITY_HIGH,
            occurrence_count=7,
        )

        with self.assertNumQueries(1):
            counts = rust_findings._existing_occurrence_counts(
                [
                    "rust_defect:RUSTBUG-PERF-001:aaa",
                    "rust_defect:RUSTBUG-PERF-002:bbb",
                    "rust_defect:RUSTBUG-PERF-001:aaa",
                    "rust_defect:RUSTBUG-PERF-003:ccc",
                ]
            )

        self.assertEqual(
            counts,
            {
                "rust_defect:RUSTBUG-PERF-001:aaa": 3,
                "rust_defect:RUSTBUG-PERF-002:bbb": 7,
            },
        )

    def test_native_loader_reuses_paper_trail_package_import(self):
        paper_native = paper_trail_dedup._load_extension()

        rust_native = rust_findings._load_native_dedup_module()

        self.assertIsNotNone(paper_native)
        self.assertIs(rust_native, paper_native)


def _report(candidate: dict) -> dict:
    return _report_many([candidate])


def _report_many(candidates: list[dict]) -> dict:
    return {
        "metadata": {"tool": "speccheck"},
        "parsed_behaviors": [],
        "test_case_candidates": [],
        "bug_candidates": candidates,
        "duplicate_warnings": [],
        "stale_record_warnings": [],
        "summary": {},
    }


def _bug_candidate(
    pattern_id: str,
    *,
    title: str = "Django ORM query inside loop",
    description: str = "A loop performs one database query per parent row.",
    category: str = "performance",
    severity: str = "high",
    file: str = "backend/apps/example.py",
    line: int = 42,
    evidence: str = "for parent in parents: Child.objects.filter(parent=parent).first()",
    fingerprint: str | None = None,
    priority_score: float = 0.85,
) -> dict:
    return {
        "bug_pattern_id": pattern_id,
        "title": title,
        "description": description,
        "severity": severity,
        "category": category,
        "file": file,
        "line": line,
        "evidence": evidence,
        "suggested_fix": "Use prefetch_related or a grouped query.",
        "confidence": "high",
        "citation": "doi:10.1145/1052883.1052895",
        "fingerprint": fingerprint or f"{pattern_id}:{file}:{line}",
        "priority_score": priority_score,
    }


def _all_bug_patterns() -> list[tuple[str, str, str, float]]:
    return [
        *[(f"RUSTBUG-PERF-{index:03}", "performance", "high", 80.0) for index in range(1, 11)],
        *[(f"RUSTBUG-CORR-{index:03}", "correctness", "medium", 50.0) for index in range(1, 11)],
        *[(f"RUSTBUG-CONC-{index:03}", "concurrency", "high", 80.0) for index in range(1, 6)],
        *[(f"RUSTBUG-RES-{index:03}", "resource", "medium", 50.0) for index in range(1, 6)],
        *[(f"RUSTBUG-SEC-{index:03}", "security", "critical", 100.0) for index in range(1, 6)],
    ]
