"""cluster_autoissues — group open AutoIssues by root cause via clusterd.

Read-only by default: prints the proposed clusters. With ``--apply`` it appends
the groupings to ``audit/cluster_assignments.jsonl`` for review. It NEVER
auto-resolves a row — the spec (docs/specs/fr-root-cause-clustering.md)
guarantees clusters are proposals; resolution is a separate reviewed step done
through ``resolve_autoissue`` with two-part lessons.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from django.core.management.base import BaseCommand

from apps.auto_issues._clusterd_client import ClusterdClient
from apps.auto_issues.models import AutoIssue
from apps.auto_issues.services.clustering_features import DEFAULT_K, feature_hashes

AUDIT_PATH = os.path.join(
    os.environ.get("REPO_ROOT", "."), "audit", "cluster_assignments.jsonl"
)
TUNED_PARAMS_PATH = os.path.join(
    os.environ.get("REPO_ROOT", "."), "audit", "cluster_tuned_params.json"
)
DEFAULT_THRESHOLD = 0.80


def load_tuned_defaults(path: str = TUNED_PARAMS_PATH) -> dict:
    """Read Optuna-tuned defaults (threshold, shingle_k) if present, else {}."""
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return {}
    return {
        "threshold": float(data["threshold"]) if "threshold" in data else None,
        "shingle_k": int(data["shingle_k"]) if "shingle_k" in data else None,
    }


class Command(BaseCommand):
    help = "Cluster open AutoIssues by root cause via clusterd (proposals only)."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=600)
        parser.add_argument(
            "--threshold",
            type=float,
            default=None,
            help="Similarity threshold; default = Optuna-tuned value or 0.80.",
        )
        parser.add_argument(
            "--shingle-k",
            type=int,
            default=None,
            help="Feature shingle size; default = Optuna-tuned value or 5.",
        )
        parser.add_argument("--source", default=None, help="Filter to one source.")
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Append groupings to audit/cluster_assignments.jsonl "
            "(never resolves rows).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Explicit no-op flag; the command is read-only unless --apply.",
        )

    def handle(self, *args, **opts):
        tuned = load_tuned_defaults()
        threshold = opts["threshold"]
        if threshold is None:
            threshold = tuned.get("threshold") or DEFAULT_THRESHOLD
        shingle_k = opts["shingle_k"]
        if shingle_k is None:
            shingle_k = tuned.get("shingle_k") or DEFAULT_K
        issues = self._open_issues(opts["limit"], opts["source"])
        if not issues:
            self.stdout.write("[CLUSTERS: no open issues matched]")
            return
        items = [
            (
                issue.id,
                feature_hashes(
                    issue.title,
                    issue.description or "",
                    issue.affected_files or [],
                    shingle_k,
                ),
            )
            for issue in issues
        ]
        clusters = ClusterdClient().cluster(items, threshold)
        multi = [c for c in clusters if len(c.member_ids) > 1]
        collapsible = sum(len(c.member_ids) - 1 for c in multi)
        self.stdout.write(
            f"[CLUSTERS: issues={len(issues)} total={len(clusters)} "
            f"multi_member={len(multi)} collapsible={collapsible} "
            f"threshold={threshold} shingle_k={shingle_k}]"
        )
        for cluster in multi[:50]:
            self.stdout.write(
                f"  rep=#{cluster.representative_id} members={cluster.member_ids}"
            )
        if opts["apply"]:
            self._persist(clusters, threshold)
            self.stdout.write(
                f"[CLUSTERS APPLIED: groupings written to {AUDIT_PATH} "
                "— no rows resolved]"
            )

    @staticmethod
    def _open_issues(limit, source):
        qs = AutoIssue.objects.filter(status="open")
        if source:
            qs = qs.filter(source=source)
        return list(qs.order_by("-priority_score", "-last_seen")[:limit])

    @staticmethod
    def _persist(clusters, threshold):
        os.makedirs(os.path.dirname(AUDIT_PATH), exist_ok=True)
        timestamp = datetime.now(timezone.utc).isoformat()
        with open(AUDIT_PATH, "a", encoding="utf-8") as handle:
            for cluster in clusters:
                handle.write(
                    json.dumps(
                        {
                            "ts": timestamp,
                            "threshold": threshold,
                            "representative_id": cluster.representative_id,
                            "member_ids": cluster.member_ids,
                        }
                    )
                    + "\n"
                )
