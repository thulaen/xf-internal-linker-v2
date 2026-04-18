"""FR-198 keyword stuffing detector."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import math
from typing import Mapping, TypeAlias

from .text_tokens import TOKEN_RE

ContentKey: TypeAlias = tuple[int, str]


@dataclass(frozen=True, slots=True)
class KeywordStuffingSettings:
    enabled: bool = True
    ranking_weight: float = 0.04
    alpha: float = 6.0
    tau: float = 0.30
    dirichlet_mu: int = 2000
    top_k_stuff_terms: int = 5
    algorithm_version: str = "fr198-v1"


@dataclass(frozen=True, slots=True)
class KeywordBaseline:
    term_counts: Mapping[str, int]
    total_terms: int
    doc_count: int
    vocab_size: int


@dataclass(frozen=True, slots=True)
class KeywordStuffingEvaluation:
    score_keyword_stuffing: float
    score_component: float
    diagnostics: dict[str, object]


def build_keyword_baseline(
    content_records: Mapping[ContentKey, object],
) -> KeywordBaseline:
    """Build the corpus baseline term distribution used by FR-198."""
    term_counts: Counter[str] = Counter()
    doc_count = 0
    total_terms = 0
    for record in content_records.values():
        terms = _document_terms(record)
        if not terms:
            continue
        doc_count += 1
        total_terms += len(terms)
        term_counts.update(terms)
    return KeywordBaseline(
        term_counts=dict(term_counts),
        total_terms=total_terms,
        doc_count=doc_count,
        vocab_size=max(len(term_counts), 1),
    )


def evaluate_keyword_stuffing(
    *,
    destination: object,
    baseline: KeywordBaseline,
    settings: KeywordStuffingSettings,
) -> KeywordStuffingEvaluation:
    """Evaluate Ntoulas-style document term divergence against the corpus."""
    terms = _document_terms(destination)
    diagnostics: dict[str, object] = {
        "stuffing_state": "neutral",
        "token_count": len(terms),
        "baseline_doc_count": baseline.doc_count,
        "baseline_vocab_size": baseline.vocab_size,
        "stuff_score": 0.0,
        "stuff_penalty": 0.0,
        "score_keyword_stuffing": 0.5,
        "top_stuff_terms": [],
        "dirichlet_mu": settings.dirichlet_mu,
        "alpha": settings.alpha,
        "tau": settings.tau,
        "algorithm_version": settings.algorithm_version,
    }

    if not settings.enabled:
        diagnostics["stuffing_state"] = "disabled"
        return KeywordStuffingEvaluation(0.5, 0.0, diagnostics)

    if baseline.doc_count < 100 or baseline.total_terms <= 0:
        diagnostics["stuffing_state"] = "no_baseline"
        return KeywordStuffingEvaluation(0.5, 0.0, diagnostics)

    if len(terms) < 30:
        diagnostics["stuffing_state"] = "text_too_short"
        return KeywordStuffingEvaluation(0.5, 0.0, diagnostics)

    tf = Counter(terms)
    vocab_size_doc = max(len(tf), 1)
    denominator = baseline.total_terms + settings.dirichlet_mu
    background_mass = settings.dirichlet_mu / max(baseline.vocab_size, 1)
    kl_sum = 0.0
    term_contributions: list[tuple[str, float]] = []

    for term, count in tf.items():
        p_d = count / len(terms)
        q_t = (baseline.term_counts.get(term, 0) + background_mass) / max(
            denominator,
            1e-9,
        )
        contribution = p_d * math.log(max(p_d / max(q_t, 1e-12), 1e-12))
        kl_sum += contribution
        term_contributions.append((term, contribution))

    if not math.isfinite(kl_sum):
        diagnostics["stuffing_state"] = "nan_clamped"
        return KeywordStuffingEvaluation(0.5, 0.0, diagnostics)

    stuff_score = kl_sum / max(math.log(max(vocab_size_doc, 2)), 1e-9)
    stuff_penalty = 1.0 / (1.0 + math.exp(-settings.alpha * (stuff_score - settings.tau)))
    score_keyword_stuffing = 0.5 - 0.5 * stuff_penalty
    score_component = min(0.0, 2.0 * (score_keyword_stuffing - 0.5))

    diagnostics.update(
        stuffing_state="single_term" if vocab_size_doc == 1 else "scored",
        stuff_score=round(stuff_score, 6),
        stuff_penalty=round(stuff_penalty, 6),
        score_keyword_stuffing=round(score_keyword_stuffing, 6),
        top_stuff_terms=[
            {"term": term, "kl_contribution": round(contribution, 6)}
            for term, contribution in sorted(
                term_contributions,
                key=lambda item: item[1],
                reverse=True,
            )[: settings.top_k_stuff_terms]
        ],
    )
    return KeywordStuffingEvaluation(
        score_keyword_stuffing=score_keyword_stuffing,
        score_component=score_component,
        diagnostics=diagnostics,
    )


def _document_terms(record: object) -> list[str]:
    title = getattr(record, "title", "") or ""
    distilled_text = getattr(record, "distilled_text", "") or ""
    text = f"{title}\n\n{distilled_text}".strip()
    return [token.lower() for token in TOKEN_RE.findall(text or "")]
