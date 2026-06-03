"""dump_cluster_corpus — write a labeled multi-source error corpus for tuning.

Runs in the backend (real DB + network to GlitchTip/SonarQube/Loki). Gathers up
to --limit samples via apps.auto_issues.services.sample_corpus and writes them
to a JSONL file the tune_clustering command (in backend-quality, with Optuna)
reads. Read-only by default; --dry-run reports counts without writing.
"""
from __future__ import annotations

import json
import os

from django.core.management.base import BaseCommand

from apps.auto_issues.services import sample_corpus

CORPUS_PATH = os.path.join(
    os.environ.get("REPO_ROOT", "."), "audit", "cluster_corpus.jsonl"
)


class Command(BaseCommand):
    help = "Dump a labeled multi-source error corpus (GlitchTip/Sonar/Loki/AutoIssue)."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=sample_corpus.DEFAULT_LIMIT)
        parser.add_argument("--out", default=CORPUS_PATH)
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Report counts without writing the corpus file.",
        )

    def handle(self, *args, **opts):
        samples = sample_corpus.gather(opts["limit"])
        labeled = sum(1 for s in samples if s.label)
        by_source: dict[str, int] = {}
        for sample in samples:
            by_source[sample.source] = by_source.get(sample.source, 0) + 1
        self.stdout.write(
            f"[CORPUS: total={len(samples)} labeled={labeled} by_source={by_source}]"
        )
        if opts["dry_run"]:
            return
        os.makedirs(os.path.dirname(opts["out"]), exist_ok=True)
        with open(opts["out"], "w", encoding="utf-8") as handle:
            for sample in samples:
                handle.write(
                    json.dumps(
                        {
                            "id": sample.sample_id,
                            "text": sample.text,
                            "paths": sample.paths,
                            "label": sample.label,
                            "source": sample.source,
                        }
                    )
                    + "\n"
                )
        self.stdout.write(f"[CORPUS WRITTEN: {opts['out']} ({len(samples)} samples)]")
