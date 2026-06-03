"""tune_clustering — conservatively tune clustering params with Optuna.

Runs in backend-quality (Optuna + grpc), with the clusterd socket mounted. Reads
the corpus written by dump_cluster_corpus, then searches the acceptance
threshold and shingle size with a precision-first objective: maximise duplicate
recall **subject to** a precision floor measured against the corpus labels, so
the tuner can never trade false merges for more collapsing. Best params are
written to a JSON file that cluster_autoissues reads as defaults.
"""
from __future__ import annotations

import json
import os

from django.core.management.base import BaseCommand, CommandError

from apps.auto_issues._clusterd_client import ClusterdClient
from apps.auto_issues.services.clustering_features import feature_hashes
from apps.auto_issues.services.sample_corpus import precision_recall

CORPUS_PATH = os.path.join(
    os.environ.get("REPO_ROOT", "."), "audit", "cluster_corpus.jsonl"
)
PARAMS_OUT = os.path.join(
    os.environ.get("REPO_ROOT", "."), "audit", "cluster_tuned_params.json"
)


class Command(BaseCommand):
    help = "Tune clustering threshold + shingle size with Optuna (precision-first)."

    def add_arguments(self, parser):
        parser.add_argument("--corpus", default=CORPUS_PATH)
        parser.add_argument("--trials", type=int, default=30)
        parser.add_argument("--precision-floor", type=float, default=0.97)
        parser.add_argument("--out", default=PARAMS_OUT)
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Run the study but do not write the tuned-params file.",
        )

    def handle(self, *args, **opts):
        import optuna

        samples = self._load(opts["corpus"])
        labels = {s["id"]: s["label"] for s in samples if s.get("label")}
        if not labels:
            raise CommandError(
                "corpus has no labeled samples — cannot tune (need GlitchTip/"
                "Sonar/fingerprint labels). Run dump_cluster_corpus first."
            )
        sid_for = {i: s["id"] for i, s in enumerate(samples)}
        client = ClusterdClient()
        floor = opts["precision_floor"]

        def objective(trial):
            tau = trial.suggest_float("threshold", 0.80, 0.98)
            k = trial.suggest_int("shingle_k", 3, 5)
            items = [
                (i, feature_hashes(s["text"], "", s.get("paths") or [], k))
                for i, s in enumerate(samples)
            ]
            results = client.cluster(items, tau)
            clusters = [[sid_for[m] for m in r.member_ids] for r in results]
            precision, recall = precision_recall(clusters, labels)
            trial.set_user_attr("precision", precision)
            trial.set_user_attr("recall", recall)
            # Precision is the hard constraint: sub-floor trials score negative
            # (proportional to the shortfall) so the tuner avoids them.
            return recall if precision >= floor else (precision - floor)

        optuna.logging.set_verbosity(optuna.logging.WARNING)
        study = optuna.create_study(direction="maximize")
        study.optimize(objective, n_trials=opts["trials"])

        best = study.best_trial
        precision = best.user_attrs.get("precision", 0.0)
        recall = best.user_attrs.get("recall", 0.0)
        met = precision >= floor
        self.stdout.write(
            f"[TUNE BEST: threshold={best.params['threshold']:.3f} "
            f"shingle_k={best.params['shingle_k']} precision={precision:.3f} "
            f"recall={recall:.3f} floor={floor} precision_floor_met={met}]"
        )
        if opts["dry_run"]:
            return
        payload = {
            "threshold": round(best.params["threshold"], 4),
            "shingle_k": best.params["shingle_k"],
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "precision_floor": floor,
            "trials": opts["trials"],
            "labeled_samples": len(labels),
            "total_samples": len(samples),
        }
        os.makedirs(os.path.dirname(opts["out"]), exist_ok=True)
        with open(opts["out"], "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
        self.stdout.write(f"[TUNE PARAMS WRITTEN: {opts['out']}]")

    @staticmethod
    def _load(path):
        if not os.path.exists(path):
            raise CommandError(f"corpus file not found: {path} (run dump_cluster_corpus)")
        with open(path, encoding="utf-8") as handle:
            return [json.loads(line) for line in handle if line.strip()]
