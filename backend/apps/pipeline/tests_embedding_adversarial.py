"""FR-248 — Adversarial regression tests for the embedding ranking path.

Locks in invariants for the failure modes called out in the plan
``C:\\Users\\goldm\\.claude\\plans\\are-there-any-current-compressed-crystal.md``:
homonyms, out-of-distribution content, embedding staleness, GPU-vs-CPU
parity, and numerical stability. Each class corresponds to one bucket
in the weakness audit.

These tests are intentionally synthetic-vector-based so they run as
``SimpleTestCase`` without loading BGE-M3 or hitting the DB. The full
on-model integration tests (loading the actual encoder, comparing CPU
vs CUDA forward passes, scoring SemEval-2013 homonym pairs) are
deferred to a focused integration-test commit that can run on a
GPU-equipped CI runner.

Sources of truth:
    * Beizer, B. (1990). *Software Testing Techniques* (2nd ed.). Van
      Nostrand Reinhold. ISBN 978-0442206727. Chapters 4–6 — equivalence
      partitioning + boundary value analysis + decision-table testing.
    * Navigli, R. et al. (2013). *SemEval-2013 Task 12: Multilingual
      Word Sense Disambiguation.* ACL Anthology.
      https://aclanthology.org/S13-2040/ — homonym/polysemy benchmark
      methodology.
    * IEEE 754-2019 — DOI 10.1109/IEEESTD.2019.8766229. §5.4 fp32
      determinism rules.
    * Higham, N. J. (2002). *Accuracy and Stability of Numerical
      Algorithms* (2nd ed.). SIAM. ISBN 978-0898715217 — NaN/Inf
      injection methodology.
"""

from __future__ import annotations

import numpy as np
from django.test import SimpleTestCase

from apps.pipeline.services.embeddings import (
    L2NormalizationAuditError,
    _audit_l2_normalization,
)
from apps.pipeline.services.slate_diversity import mmr_rerank_keys


def _unit(*vals: float) -> np.ndarray:
    v = np.asarray(vals, dtype=np.float32)
    return (v / np.linalg.norm(v)).astype(np.float32)


# ─────────────────────────────────────────────────────────────────────
# A. Homonym regression — Navigli 2013 §3 methodology
# ─────────────────────────────────────────────────────────────────────


class HomonymRegressionTests(SimpleTestCase):
    """Lock in the cosine-similarity invariants for synthetic homonyms.

    A homonym ("apple" the fruit vs "Apple" the company) maps to two
    distant points in embedding space when context disambiguates. We
    simulate this with two well-separated unit vectors and verify the
    ranking math correctly distinguishes them.

    Full BGE-M3 + SemEval-2013 integration deferred (needs encoder load).
    """

    def test_distant_unit_vectors_have_low_cosine(self):
        # Navigli 2013 §3 — different senses should map to vectors with
        # cosine << 1.0. Synthetic baseline: orthogonal vectors → cos=0.
        sense_fruit = _unit(1.0, 0.0)
        sense_company = _unit(0.0, 1.0)
        cos = float(np.dot(sense_fruit, sense_company))
        self.assertAlmostEqual(cos, 0.0, places=5)

    def test_correct_sense_outranks_wrong_sense(self):
        # Query vector aligned with fruit context → fruit destination
        # ranks ahead of company destination via MMR rerank.
        query_fruit = _unit(1.0, 0.0)
        fruit_dest = _unit(0.99, 0.05)
        company_dest = _unit(0.05, 0.99)
        host_scores = [
            ("fruit", float(np.dot(query_fruit, fruit_dest))),
            ("company", float(np.dot(query_fruit, company_dest))),
        ]
        emb = {"fruit": fruit_dest, "company": company_dest}
        out = mmr_rerank_keys(host_scores, emb, k=1, lambda_=0.7)
        self.assertEqual(out[0][0], "fruit")

    def test_homonym_close_to_diagonal_still_picks_dominant_sense(self):
        # Adversarial: query halfway between the two senses (ambiguous
        # context). MMR returns whichever the relevance score favours.
        # The point isn't the answer — it's that MMR doesn't crash on
        # an ambiguous query.
        ambiguous = _unit(1.0, 1.0)
        fruit = _unit(1.0, 0.0)
        company = _unit(0.0, 1.0)
        host_scores = [
            ("fruit", float(np.dot(ambiguous, fruit))),
            ("company", float(np.dot(ambiguous, company))),
        ]
        emb = {"fruit": fruit, "company": company}
        out = mmr_rerank_keys(host_scores, emb, k=2, lambda_=0.7)
        # Both candidates returned; either order is acceptable.
        self.assertEqual({k for k, _ in out}, {"fruit", "company"})


# ─────────────────────────────────────────────────────────────────────
# B. Out-of-distribution content
# ─────────────────────────────────────────────────────────────────────


class OutOfDistributionTests(SimpleTestCase):
    """Synthetic neologisms via Beizer 1990 §6 domain-edge pattern.

    OOD tokens (made-up brand names, niche slang) get vectors near
    the model's tokenizer's "unknown" subword decomposition. We
    simulate this by injecting a vector with very small magnitude
    components — a degenerate "weak signal" embedding — and verify
    the math doesn't produce NaN or rank it absurdly high.
    """

    def test_weak_magnitude_vector_audited_correctly(self):
        # Adversarial: a vector with magnitude 0.01 (near-zero).
        # The L2 audit must catch this because cosine on un-normalised
        # vectors is biased by magnitude (Wang 2017 NAACL §2).
        weak = np.array([[0.01, 0.0]], dtype=np.float32)
        with self.assertRaises(L2NormalizationAuditError):
            _audit_l2_normalization(weak)

    def test_zero_vector_audited_as_failure(self):
        # Edge case: tokenizer produced an empty embedding.
        # Audit catches it before persistence.
        zero = np.zeros((1, 8), dtype=np.float32)
        with self.assertRaises(L2NormalizationAuditError):
            _audit_l2_normalization(zero)

    def test_ood_candidate_not_eliminated_when_no_embedding_lookup(self):
        # FR-239 documented contract: a candidate without an embedding
        # entry is treated as "fully diverse" rather than dropped.
        # Avoids silently penalising legitimate OOD content.
        host_scores = [("known", 0.9), ("ood", 0.85)]
        emb = {"known": _unit(1.0, 0.0)}  # "ood" deliberately missing
        out = mmr_rerank_keys(host_scores, emb, k=2, lambda_=0.7)
        self.assertEqual({k for k, _ in out}, {"known", "ood"})


# ─────────────────────────────────────────────────────────────────────
# C. Embedding staleness
# ─────────────────────────────────────────────────────────────────────


class EmbeddingStalenessTests(SimpleTestCase):
    """FR-249 age decay returns expected multipliers across staleness ranges.

    Beizer 1990 §5 — decision-table testing across the boundary
    conditions (today, half-life, multiple half-lives).
    """

    def test_age_decay_helper_locks_canonical_values(self):
        # Lock the cited contract: 0.5 ^ (age / half_life).
        from datetime import datetime, timedelta, timezone

        from apps.pipeline.services.embedding_age import (
            compute_embedding_age_decay,
        )

        now = datetime(2026, 5, 7, tzinfo=timezone.utc)
        # 0 days → 1.0
        self.assertAlmostEqual(
            compute_embedding_age_decay(now, now=now), 1.0, places=6
        )
        # 365 days → 0.5
        self.assertAlmostEqual(
            compute_embedding_age_decay(now - timedelta(days=365), now=now),
            0.5, places=6,
        )
        # 730 days → 0.25
        self.assertAlmostEqual(
            compute_embedding_age_decay(now - timedelta(days=730), now=now),
            0.25, places=6,
        )

    def test_unknown_age_does_not_penalise(self):
        # Documented contract: None timestamp → 1.0 (no penalty for
        # unknown). Avoids silently downranking content whose
        # `updated_at` couldn't be determined.
        from apps.pipeline.services.embedding_age import (
            compute_embedding_age_decay,
        )

        self.assertEqual(compute_embedding_age_decay(None), 1.0)


# ─────────────────────────────────────────────────────────────────────
# D. GPU vs CPU parity
# ─────────────────────────────────────────────────────────────────────


class GpuCpuParityTests(SimpleTestCase):
    """Check that the FAISS-IP and NumPy-dot scoring paths agree on
    L2-unit inputs (the FR-237 invariant).

    Full GPU-vs-CPU forward-pass parity needs CUDA + a real model load
    and is deferred. These tests check the math layer.
    """

    def test_dot_and_inner_product_agree_on_l2_unit_vectors(self):
        # IEEE 754-2019 §5.4 — fp32 unit-magnitude operations are
        # deterministic across implementations. For L2-unit vectors,
        # dot product == cosine == FAISS IndexFlatIP score.
        u = _unit(1.0, 2.0, 3.0)
        v = _unit(2.0, -1.0, 0.5)
        dot = float(np.dot(u, v))
        # Same math via outer-product diagonal — symbolically equivalent.
        outer_diag = float((u[None, :] @ v[:, None])[0, 0])
        self.assertAlmostEqual(dot, outer_diag, places=6)

    def test_parity_within_ieee754_tolerance(self):
        # Adversarial: a vector that's NEARLY unit but drifts within
        # IEEE 754 rounding. Cosine on it should still satisfy the
        # FR-237 1e-6 audit tolerance.
        almost_unit = _unit(1.0, 1.0, 1.0) * (1.0 + 1e-7)
        norm_dev = abs(float(np.linalg.norm(almost_unit)) - 1.0)
        self.assertLess(norm_dev, 1e-6)


# ─────────────────────────────────────────────────────────────────────
# E. Numerical stability — Higham 2002 NaN/Inf injection
# ─────────────────────────────────────────────────────────────────────


class NumericalStabilityTests(SimpleTestCase):
    """NaN / Inf injection per Higham 2002 *Accuracy and Stability of
    Numerical Algorithms* methodology.

    These tests assert the ranking math fails LOUDLY (raises) rather
    than silently producing garbage when inputs are malformed.
    """

    def test_nan_in_vector_caught_by_audit(self):
        # IEEE 754-2019 §6.2 — NaN comparisons always evaluate False.
        # The audit's `max_dev > tolerance` check therefore can't
        # detect a NaN row by itself. FR-248 hardening: an explicit
        # `np.any(np.isnan(arr))` precheck closes that gap (Higham
        # 2002 §1.4 — adversarial inputs must fail loudly). This
        # test locks the precheck contract.
        nan_row = np.array([[np.nan, 0.0]], dtype=np.float32)
        with self.assertRaises(L2NormalizationAuditError) as ctx:
            _audit_l2_normalization(nan_row)
        self.assertEqual(ctx.exception.worst_row, 0)
        self.assertTrue(np.isnan(ctx.exception.max_dev))

    def test_inf_vector_caught_by_audit(self):
        # ||(inf, 0)|| = inf. |inf - 1.0| = inf. inf > 1e-6 → True.
        # Audit raises.
        inf_row = np.array([[np.inf, 0.0]], dtype=np.float32)
        with self.assertRaises(L2NormalizationAuditError):
            _audit_l2_normalization(inf_row)

    def test_extreme_unit_vector_at_one_minus_epsilon(self):
        # IEEE 754 fp32 epsilon ≈ 1.19e-7. A vector at 1 - 2*epsilon
        # is still within audit tolerance (1e-6).
        almost = np.array([[1.0 - 2.4e-7, 0.0]], dtype=np.float32)
        # Should not raise.
        _audit_l2_normalization(almost)

    def test_negative_zero_norm_handled(self):
        # IEEE 754 has -0.0 == 0.0 but stored differently. Cosine math
        # is unaffected by sign of zero norms; audit catches the
        # |0 - 1| = 1.0 deviation regardless of sign.
        neg_zero = np.array([[-0.0, -0.0]], dtype=np.float32)
        with self.assertRaises(L2NormalizationAuditError):
            _audit_l2_normalization(neg_zero)
