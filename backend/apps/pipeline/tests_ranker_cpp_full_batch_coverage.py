"""Coverage for the Rust full-batch scoring path in ``ranker.py``.

The ranker's final composite-score kernel was ported from C++ to Rust
(rust/extensions/scoring) and is loaded through the shared ``load_kernel``
helper (RUST-FIRST.md zero-fallback). ``HAS_CPP_FULL_BATCH`` now reflects
whether ``load_kernel("extensions.scoring",
"calculate_composite_scores_full_batch")`` succeeded at module import. The batch
call site in :func:`score_destination_matches` calls the kernel unconditionally
through ``load_kernel`` — there is no Python-fallback branch.

``_calculate_composite_scores_full_batch_py`` is retained ONLY as the
cross-language parity oracle these tests (and the health benchmark) drive; it is
NOT a silent runtime fallback.

These ``SimpleTestCase`` tests pin:

* ``HAS_CPP_FULL_BATCH`` is ``True`` in the quality/runtime image (the Rust
  kernel is built and exports ``calculate_composite_scores_full_batch``).
* The Rust batch call site returns a real finite composite ``score_final``.
* The Rust kernel and the pure-Python parity oracle agree to 1e-5 on the same
  inputs, proving the kernel is wired correctly and is not a no-op.

``score_destination_matches`` is documented as pure-Python with only a
best-effort, try/except-guarded ContentItem/Sentence prefetch, so these tests
run without a database: the prefetch raises, is caught, logs a neutral-fallback
warning, and scoring proceeds.
"""

from __future__ import annotations

import numpy as np

from django.test import SimpleTestCase

from apps.pipeline.services import ranker as ranker_service
from apps.pipeline.services.ranker import (
    ContentRecord,
    SentenceRecord,
    SentenceSemanticMatch,
    SiloSettings,
    score_destination_matches,
)


def _content_record(*, content_id: int, silo_group_id: int | None) -> ContentRecord:
    return ContentRecord(
        content_id=content_id,
        content_type="thread",
        title=f"Item {content_id}",
        distilled_text="Topic body",
        scope_id=content_id,
        scope_type="node",
        parent_id=None,
        parent_type="",
        grandparent_id=None,
        grandparent_type="",
        silo_group_id=silo_group_id,
        silo_group_name=f"Silo {silo_group_id}" if silo_group_id else "",
        reply_count=5,
        march_2026_pagerank_score=0.0,
        link_freshness_score=0.5,
        content_value_score=0.0,
        primary_post_char_count=500,
        tokens=frozenset({"topic", str(content_id)}),
    )


class RustFullBatchScoringPathTests(SimpleTestCase):
    """The Rust batch call must activate and match the Python parity oracle."""

    def setUp(self) -> None:
        self.destination = _content_record(content_id=1, silo_group_id=10)
        self.host = _content_record(content_id=2, silo_group_id=10)
        self.sentence_records = {
            20: SentenceRecord(
                20, 2, "thread", "Useful same silo sentence", 80, frozenset({"topic"})
            ),
        }
        self.match = [SentenceSemanticMatch(2, "thread", 20, 0.8)]
        self.records = {
            self.destination.key: self.destination,
            self.host.key: self.host,
        }
        self.weights = {
            "w_semantic": 0.55,
            "w_keyword": 0.20,
            "w_node": 0.10,
            "w_quality": 0.15,
        }
        self.bounds = (0.1, 2.0)

    def _score(self) -> list:
        return score_destination_matches(
            self.destination,
            self.match,
            content_records=self.records,
            sentence_records=self.sentence_records,
            existing_links=set(),
            weights=self.weights,
            march_2026_pagerank_bounds=self.bounds,
            silo_settings=SiloSettings(mode="disabled"),
        )

    def test_rust_full_batch_flag_is_enabled_in_runtime_image(self) -> None:
        # The Rust kernel is built and loaded at module import, so the flag is
        # True and the loaded module exposes the real export.
        self.assertTrue(
            ranker_service.HAS_CPP_FULL_BATCH,
            "The Rust kernel exports calculate_composite_scores_full_batch, so "
            "HAS_CPP_FULL_BATCH must be True after the Rust port.",
        )
        self.assertIsNotNone(ranker_service.scoring)
        self.assertTrue(
            hasattr(
                ranker_service.scoring, "calculate_composite_scores_full_batch"
            )
        )

    def test_rust_batch_path_returns_scored_candidate(self) -> None:
        # Exercises the calculate_composite_scores_full_batch call site end to
        # end through the Rust kernel.
        results = self._score()
        self.assertEqual(len(results), 1)
        candidate = results[0]
        self.assertEqual(candidate.destination_content_id, 1)
        self.assertEqual(candidate.host_content_id, 2)
        # The composite must be a real finite score, not the empty/zero sentinel.
        self.assertIsInstance(candidate.score_final, float)
        self.assertGreater(candidate.score_final, 0.0)

    def test_rust_kernel_and_python_oracle_agree(self) -> None:
        # The Rust kernel and the pure-Python parity oracle must produce the
        # same composite scores on the same float32 inputs (1e-5 contract). This
        # proves the Rust call is correctly wired and not returning wrong values.
        rng = np.random.default_rng(11)
        component_scores = rng.uniform(-1.0, 1.0, size=(64, 12)).astype(np.float32)
        weights = rng.uniform(-0.75, 0.75, size=(12,)).astype(np.float32)
        silo = rng.uniform(-0.5, 0.5, size=(64,)).astype(np.float32)

        kernel = ranker_service.load_kernel(
            "extensions.scoring", "calculate_composite_scores_full_batch"
        )
        rust_out = kernel.calculate_composite_scores_full_batch(
            np.ascontiguousarray(component_scores, dtype=np.float32),
            np.ascontiguousarray(weights, dtype=np.float32),
            np.ascontiguousarray(silo, dtype=np.float32),
        )
        oracle_out = ranker_service._calculate_composite_scores_full_batch_py(
            component_scores, weights, silo
        )
        np.testing.assert_allclose(rust_out, oracle_out, rtol=1e-5, atol=1e-5)
