"""Tests for the cluster_autoissues management command.

The clusterd gRPC client is mocked so the command's issue→items wiring,
reporting, and (non-destructive) --apply persistence are tested without a live
clusterd sidecar.
"""
import os
import tempfile
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.test import TestCase

from apps.auto_issues._clusterd_client import ClusterResult
from apps.auto_issues.models import AutoIssue, AutoIssueCategory

_CLIENT = "apps.auto_issues.management.commands.cluster_autoissues.ClusterdClient"


class LoadTunedDefaultsTests(TestCase):
    def test_reads_tuned_params(self):
        import json as _json

        from apps.auto_issues.management.commands.cluster_autoissues import (
            load_tuned_defaults,
        )

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "p.json")
            with open(path, "w", encoding="utf-8") as fh:
                _json.dump({"threshold": 0.974, "shingle_k": 3}, fh)
            self.assertEqual(
                load_tuned_defaults(path), {"threshold": 0.974, "shingle_k": 3}
            )

    def test_missing_file_returns_empty(self):
        from apps.auto_issues.management.commands.cluster_autoissues import (
            load_tuned_defaults,
        )

        self.assertEqual(load_tuned_defaults("/no/such/file.json"), {})


def _category():
    cat, _ = AutoIssueCategory.objects.get_or_create(
        key="test-cluster",
        defaults={"label": "Test", "description": "t", "sort_order": 200},
    )
    return cat


def _issue(n):
    return AutoIssue.objects.create(
        source=AutoIssue.SOURCE_AGENT,
        external_id=f"clus-{n}",
        fingerprint=f"clus-{n}",
        canonical_fingerprint=f"clus-{n}",
        title=f"connection timeout on node {n}",
        description="boom",
        affected_files=["a/b.py"],
        severity=AutoIssue.SEVERITY_LOW,
        category=_category(),
        status=AutoIssue.STATUS_OPEN,
        priority_score=0.5,
    )


class ClusterAutoissuesTests(TestCase):
    def test_reports_multi_member_cluster(self):
        i1, i2, i3 = _issue(1), _issue(2), _issue(3)
        fake = [
            ClusterResult(i1.id, [i1.id, i2.id]),
            ClusterResult(i3.id, [i3.id]),
        ]
        out = StringIO()
        with mock.patch(_CLIENT) as client_cls:
            client_cls.return_value.cluster.return_value = fake
            call_command("cluster_autoissues", "--limit", "10", stdout=out)
        text = out.getvalue()
        self.assertIn("multi_member=1", text)
        self.assertIn("collapsible=1", text)
        self.assertIn(f"rep=#{i1.id}", text)

    def test_no_open_issues(self):
        out = StringIO()
        with mock.patch(_CLIENT) as client_cls:
            client_cls.return_value.cluster.return_value = []
            call_command("cluster_autoissues", stdout=out)
        # No issues created → command short-circuits before calling the client.
        self.assertIn("no open issues", out.getvalue())
        client_cls.return_value.cluster.assert_not_called()

    def test_never_resolves_rows(self):
        i1, i2 = _issue(1), _issue(2)
        fake = [ClusterResult(i1.id, [i1.id, i2.id])]
        out = StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            audit = os.path.join(tmp, "cluster_assignments.jsonl")
            with mock.patch(_CLIENT) as client_cls, mock.patch(
                "apps.auto_issues.management.commands.cluster_autoissues.AUDIT_PATH",
                audit,
            ):
                client_cls.return_value.cluster.return_value = fake
                call_command("cluster_autoissues", "--apply", stdout=out)
            self.assertTrue(os.path.exists(audit), "groupings should be persisted")
        # The spec guarantees clustering never auto-resolves: both stay open.
        self.assertEqual(
            AutoIssue.objects.filter(status=AutoIssue.STATUS_OPEN).count(), 2
        )
