import json

import lz4.frame
from django.core.management import call_command
from django.test import TestCase

from apps.auto_issues.models import AutoIssue, BuildFailureEvidence
from apps.auto_issues.services.build_failures import BuildFailure, ingest_build_failure


class BuildFailureIngestTests(TestCase):
    def test_ingest_creates_autoissue_with_lz4_evidence(self):
        failure = BuildFailure(
            builder="mint",
            targets=["backend"],
            command=["docker", "--context", "mint", "compose", "build", "backend"],
            exit_code=17,
            stdout="compile started",
            stderr="backend/extensions/native.cpp:10: error: missing symbol",
        )

        issue, outcome = ingest_build_failure(failure)

        self.assertEqual(outcome, "created")
        self.assertEqual(issue.status, AutoIssue.STATUS_OPEN)
        self.assertIn("build_compile", issue.concept_tags)
        evidence = BuildFailureEvidence.objects.get(issue=issue)
        self.assertEqual(evidence.compression, "lz4")
        payload = json.loads(lz4.frame.decompress(evidence.compressed_payload))
        self.assertEqual(payload["builder"], "mint")
        self.assertEqual(payload["targets"], ["backend"])
        self.assertEqual(payload["exit_code"], 17)
        self.assertIn("missing symbol", payload["stderr"])

    def test_repeated_same_failure_updates_one_issue_without_clones(self):
        failure = BuildFailure(
            builder="mint",
            targets=["backend"],
            command=["docker", "--context", "mint", "compose", "build", "backend"],
            exit_code=17,
            stdout="compile started",
            stderr="backend/extensions/native.cpp:10: error: missing symbol",
        )

        first, first_outcome = ingest_build_failure(failure)
        second, second_outcome = ingest_build_failure(failure)

        self.assertEqual(first_outcome, "created")
        self.assertEqual(second_outcome, "updated")
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(AutoIssue.objects.filter(concept_tags__contains=["build_compile"]).count(), 1)
        evidence = BuildFailureEvidence.objects.get(issue=first)
        self.assertEqual(evidence.occurrence_count, 2)

    def test_management_command_ingests_payload_json(self):
        payload = {
            "builder": "desktop-linux",
            "targets": ["frontend-build"],
            "command": ["docker", "--context", "desktop-linux", "compose", "build", "frontend-build"],
            "exit_code": 2,
            "stdout": "",
            "stderr": "frontend/src/main.ts:5: error TS2304: Cannot find name",
        }

        call_command("ingest_build_failure_autoissue", payload_json=json.dumps(payload))

        issue = AutoIssue.objects.get(concept_tags__contains=["build_compile"])
        self.assertIn("frontend-build", issue.title)
        evidence = BuildFailureEvidence.objects.get(issue=issue)
        self.assertEqual(evidence.builder, "desktop-linux")
