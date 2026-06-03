"""Tests for importing CodeQL SARIF findings into AutoIssues."""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

import lz4.frame
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from apps.auto_issues.models import AutoIssue, CodeQLFindingEvidence
from apps.auto_issues.services import codeql as codeql_service


def _sample_sarif(path: str = "backend/apps/api/views.py") -> dict:
    return {
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "CodeQL",
                        "rules": [
                            {
                                "id": "py/sql-injection",
                                "shortDescription": {"text": "SQL built from user input"},
                                "help": {"text": "Use parameterized database queries."},
                                "properties": {"security-severity": "8.2"},
                            }
                        ],
                    }
                },
                "results": [
                    {
                        "ruleId": "py/sql-injection",
                        "level": "error",
                        "message": {"text": "Query text uses request data."},
                        "locations": [
                            {
                                "physicalLocation": {
                                    "artifactLocation": {"uri": path},
                                    "region": {"startLine": 42},
                                }
                            }
                        ],
                    }
                ],
            }
        ],
    }


def _sample_sarif_with_many_results(count: int) -> dict:
    report = _sample_sarif()
    results = []
    for index in range(count):
        result = report["runs"][0]["results"][0].copy()
        result["message"] = {"text": f"Query text uses request data {index}."}
        result["locations"] = [
            {
                "physicalLocation": {
                    "artifactLocation": {"uri": f"backend/apps/api/views_{index}.py"},
                    "region": {"startLine": 42 + index},
                }
            }
        ]
        results.append(result)
    report["runs"][0]["results"] = results
    return report


class CodeQLImportTests(TestCase):
    def test_import_creates_deduped_rich_autoissue(self) -> None:
        with TemporaryDirectory() as tmp:
            report = Path(tmp) / "python.sarif"
            report.write_text(json.dumps(_sample_sarif()), encoding="utf-8")

            created = codeql_service.ingest_sarif_paths([report], language="python")
            created_again = codeql_service.ingest_sarif_paths([report], language="python")

        issue = AutoIssue.objects.get(concept_tags__contains=["codeql"])
        evidence = CodeQLFindingEvidence.objects.get(issue=issue)
        payload = json.loads(lz4.frame.decompress(evidence.compressed_payload))
        self.assertEqual(created.created, 1)
        self.assertEqual(created_again.created, 0)
        self.assertEqual(AutoIssue.objects.filter(concept_tags__contains=["codeql"]).count(), 1)
        self.assertEqual(CodeQLFindingEvidence.objects.count(), 1)
        self.assertEqual(evidence.compression, "lz4")
        self.assertEqual(bytes(evidence.compressed_payload[:4]), b"\x04\x22\x4d\x18")
        self.assertEqual(payload["alert_type"], "py/sql-injection")
        self.assertEqual(payload["affected_file"], "backend/apps/api/views.py:42")
        self.assertEqual(payload["evidence"], "Query text uses request data.")
        self.assertEqual(payload["severity"], "critical")
        self.assertIn("run_codeql.py", payload["reproduction_command"])
        self.assertEqual(payload["recommended_fix"], "Use parameterized database queries.")
        self.assertEqual(payload["true_positive_status"], "needs review")

    def test_import_does_not_exceed_ten_open_codeql_issues(self) -> None:
        with TemporaryDirectory() as tmp:
            report = Path(tmp) / "python.sarif"
            report.write_text(json.dumps(_sample_sarif_with_many_results(11)), encoding="utf-8")

            result = codeql_service.ingest_sarif_paths([report], language="python", max_open=10)

        self.assertEqual(result.created, 10)
        self.assertEqual(result.skipped, 1)
        self.assertEqual(AutoIssue.objects.filter(concept_tags__contains=["codeql"]).count(), 10)
        self.assertEqual(CodeQLFindingEvidence.objects.count(), 10)

    def test_verify_blocks_any_open_codeql_issue(self) -> None:
        AutoIssue.objects.create(
            source=AutoIssue.SOURCE_AGENT,
            external_id="codeql::python::one",
            fingerprint="codeql-one",
            canonical_fingerprint="codeql-one",
            title="CodeQL issue",
            description="CodeQL finding",
            concept_tags=["codeql"],
            affected_files=["backend/apps/api/views.py"],
        )

        with self.assertRaises(CommandError):
            call_command("verify_codeql_autoissues", block_open=True, max_open=10)

    def test_verify_blocks_more_than_ten_open_codeql_issues(self) -> None:
        for index in range(11):
            AutoIssue.objects.create(
                source=AutoIssue.SOURCE_AGENT,
                external_id=f"codeql::python::{index}",
                fingerprint=f"codeql-{index}",
                canonical_fingerprint=f"codeql-{index}",
                title=f"CodeQL issue {index}",
                description="CodeQL finding",
                concept_tags=["codeql"],
                affected_files=["backend/apps/api/views.py"],
            )

        with self.assertRaises(CommandError):
            call_command("verify_codeql_autoissues", max_open=10)
