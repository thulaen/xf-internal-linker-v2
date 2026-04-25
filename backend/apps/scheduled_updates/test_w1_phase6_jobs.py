"""W1 wirings for Phase 6 pip-deferred picks (#23, #37, #38, #39).

Each test exercises the entrypoint via the same checkpoint fake the
real runner uses, then asserts on the outcome:

- Pip dep available + corpus too small → no-op with "skipped" message.
- Pip dep missing → DeferredPickError (only if the helper's
  is_available() honestly returns False; we mock it to make the
  install-state predictable).

These are unit tests on the entrypoints, not the runner — runner
machinery has its own coverage in tests_runner.py.
"""

from __future__ import annotations

from unittest import mock

from django.test import TestCase

from apps.scheduled_updates.jobs import DeferredPickError


class _CheckpointRecorder:
    """Stand-in for the runner's checkpoint(progress_pct=, message=) fn."""

    def __init__(self) -> None:
        self.calls: list[tuple[float, str]] = []

    def __call__(self, *, progress_pct: float, message: str) -> None:
        self.calls.append((float(progress_pct), str(message)))

    @property
    def last_message(self) -> str:
        return self.calls[-1][1] if self.calls else ""


class Node2VecW1Tests(TestCase):
    def test_deferred_when_pip_missing(self) -> None:
        from apps.scheduled_updates.jobs import run_node2vec_walks

        with mock.patch(
            "apps.pipeline.services.node2vec_embeddings.is_available",
            return_value=False,
        ):
            cp = _CheckpointRecorder()
            with self.assertRaises(DeferredPickError):
                run_node2vec_walks(job=None, checkpoint=cp)
        self.assertIn("install `node2vec`", cp.last_message)

    def test_empty_graph_no_ops(self) -> None:
        """Pip dep available but graph has < 2 nodes → clean skip."""
        from apps.scheduled_updates.jobs import run_node2vec_walks

        # Patch is_available True, but make _load_networkx_graph
        # return an empty DiGraph.
        import networkx as nx

        empty_graph = nx.DiGraph()
        with mock.patch(
            "apps.pipeline.services.node2vec_embeddings.is_available",
            return_value=True,
        ), mock.patch(
            "apps.scheduled_updates.jobs._load_networkx_graph",
            return_value=empty_graph,
        ):
            cp = _CheckpointRecorder()
            run_node2vec_walks(job=None, checkpoint=cp)  # should NOT raise
        self.assertIn("only", cp.last_message)


class BprW1Tests(TestCase):
    def test_deferred_when_implicit_missing(self) -> None:
        from apps.scheduled_updates.jobs import run_bpr_refit

        with mock.patch(
            "apps.pipeline.services.bpr_ranking.is_available",
            return_value=False,
        ):
            cp = _CheckpointRecorder()
            with self.assertRaises(DeferredPickError):
                run_bpr_refit(job=None, checkpoint=cp)
        self.assertIn("install `implicit`", cp.last_message)

    def test_no_interactions_no_ops(self) -> None:
        """Empty Suggestion table → no-op clean."""
        from apps.scheduled_updates.jobs import run_bpr_refit

        with mock.patch(
            "apps.pipeline.services.bpr_ranking.is_available",
            return_value=True,
        ):
            cp = _CheckpointRecorder()
            run_bpr_refit(job=None, checkpoint=cp)  # no exception
        self.assertIn("0 approve/reject rows", cp.last_message)


class FmW1Tests(TestCase):
    def test_deferred_when_pyfm_missing(self) -> None:
        from apps.scheduled_updates.jobs import run_factorization_machines_refit

        with mock.patch(
            "apps.pipeline.services.factorization_machines.is_available",
            return_value=False,
        ):
            cp = _CheckpointRecorder()
            with self.assertRaises(DeferredPickError):
                run_factorization_machines_refit(job=None, checkpoint=cp)
        self.assertIn("install `pyfm`", cp.last_message)

    def test_no_reviewed_rows_no_ops(self) -> None:
        from apps.scheduled_updates.jobs import run_factorization_machines_refit

        with mock.patch(
            "apps.pipeline.services.factorization_machines.is_available",
            return_value=True,
        ):
            cp = _CheckpointRecorder()
            run_factorization_machines_refit(job=None, checkpoint=cp)
        self.assertIn("0 reviewed rows", cp.last_message)


class KenlmW1Tests(TestCase):
    def test_deferred_when_neither_dep_present(self) -> None:
        from apps.scheduled_updates.jobs import run_kenlm_retrain

        with mock.patch(
            "apps.pipeline.services.kenlm_fluency.is_available",
            return_value=False,
        ), mock.patch(
            "apps.pipeline.services.kenlm_fluency.lmplz_available",
            return_value=False,
        ):
            cp = _CheckpointRecorder()
            with self.assertRaises(DeferredPickError):
                run_kenlm_retrain(job=None, checkpoint=cp)
        self.assertIn("install `kenlm`", cp.last_message)

    def test_deferred_when_only_pip_present(self) -> None:
        """`kenlm` pip installed but `lmplz` binary missing → still deferred."""
        from apps.scheduled_updates.jobs import run_kenlm_retrain

        with mock.patch(
            "apps.pipeline.services.kenlm_fluency.is_available",
            return_value=True,
        ), mock.patch(
            "apps.pipeline.services.kenlm_fluency.lmplz_available",
            return_value=False,
        ):
            cp = _CheckpointRecorder()
            with self.assertRaises(DeferredPickError):
                run_kenlm_retrain(job=None, checkpoint=cp)
        self.assertIn("`lmplz` binary not on PATH", cp.last_message)

    def test_empty_corpus_no_ops_when_both_deps_present(self) -> None:
        """Both deps present + empty Sentence table → clean skip."""
        from apps.scheduled_updates.jobs import run_kenlm_retrain

        with mock.patch(
            "apps.pipeline.services.kenlm_fluency.is_available",
            return_value=True,
        ), mock.patch(
            "apps.pipeline.services.kenlm_fluency.lmplz_available",
            return_value=True,
        ):
            cp = _CheckpointRecorder()
            run_kenlm_retrain(job=None, checkpoint=cp)  # no exception
        self.assertIn("0 sentences", cp.last_message)
