"""Benchmarks for 52-pick Parse & Embed helpers — FR-230 / G6.

Covered shipped helpers (PR-E, commit a4771e8):
- `apps.sources.normalize`            — pick #13 (NFKC)
- `apps.sources.collocations`         — pick #24 (PMI / NPMI)
- `apps.sources.passages`             — pick #25 (Callan windows)
- `apps.sources.entity_salience`      — pick #26 (Gamon heuristic)
- `apps.sources.readability`          — pick #19 (Flesch + Fog)
- `apps.sources.product_quantization` — pick #20 (FAISS PQ, skipped if
                                        faiss not installed)

Three input sizes per helper.
"""

from __future__ import annotations

import random
import string

import pytest


def _random_paragraph(rng: random.Random, words: int) -> str:
    vocab = [
        "".join(rng.choices(string.ascii_lowercase, k=rng.randint(3, 10)))
        for _ in range(2000)
    ]
    return " ".join(rng.choices(vocab, k=words))


# ── NFKC (#13) ─────────────────────────────────────────────────────


def _nfkc_batch(texts):
    from apps.sources.normalize import nfkc

    for t in texts:
        nfkc(t)


def test_bench_nfkc_small(benchmark):
    rng = random.Random(0)
    texts = [_random_paragraph(rng, 100) for _ in range(1000)]
    benchmark(_nfkc_batch, texts)


def test_bench_nfkc_medium(benchmark):
    rng = random.Random(0)
    texts = [_random_paragraph(rng, 500) for _ in range(10_000)]
    benchmark(_nfkc_batch, texts)


def test_bench_nfkc_large(benchmark):
    rng = random.Random(0)
    texts = [_random_paragraph(rng, 1000) for _ in range(100_000)]
    benchmark(_nfkc_batch, texts)


# ── PMI Collocations (#24) ────────────────────────────────────────


def _pmi_batch(n):
    from apps.sources.collocations import pmi

    for _ in range(n):
        pmi(joint_count=20, count_a=100, count_b=200, total=10_000)


def test_bench_pmi_small(benchmark):
    benchmark(_pmi_batch, 10_000)


def test_bench_pmi_medium(benchmark):
    benchmark(_pmi_batch, 10_000_000)


def test_bench_pmi_large(benchmark):
    benchmark(_pmi_batch, 100_000_000)


# ── Passage Segmentation (#25) ────────────────────────────────────


def _passages_batch(texts):
    from apps.sources.passages import segment_by_tokens

    for t in texts:
        segment_by_tokens(t, window_tokens=150, overlap_tokens=30)


def test_bench_passages_small(benchmark):
    rng = random.Random(0)
    texts = [_random_paragraph(rng, 500) for _ in range(100)]
    benchmark(_passages_batch, texts)


def test_bench_passages_medium(benchmark):
    rng = random.Random(0)
    texts = [_random_paragraph(rng, 500) for _ in range(10_000)]
    benchmark(_passages_batch, texts)


def test_bench_passages_large(benchmark):
    rng = random.Random(0)
    texts = [_random_paragraph(rng, 1000) for _ in range(100_000)]
    benchmark(_passages_batch, texts)


# ── Entity Salience (#26) — uses minimal fake doc ─────────────────


class _FakeSpan:
    def __init__(self, text, label, start, end):
        self.text = text
        self.label_ = label
        self.start_char = start
        self.end_char = end


class _FakeSent:
    def __init__(self, text, start, end):
        self.text = text
        self.start_char = start
        self.end_char = end


class _FakeDoc:
    def __init__(self, text, ents, sents):
        self.text = text
        self.ents = ents
        self.sents = sents


def _make_fake_doc(n_ents: int):
    text = " ".join([f"Sentence {i} word." for i in range(n_ents // 5 + 1)])
    ents = [
        _FakeSpan(f"E{i}", "ORG", i * 20 % len(text), i * 20 % len(text) + 5)
        for i in range(n_ents)
    ]
    # one sentence span covering the whole doc keeps the benchmark simple
    sents = [_FakeSent(text, 0, len(text))]
    return _FakeDoc(text, ents, sents)


def _rank_docs(docs):
    from apps.sources.entity_salience import rank_entities

    for doc in docs:
        rank_entities(doc)


def test_bench_entity_salience_small(benchmark):
    docs = [_make_fake_doc(10) for _ in range(100)]
    benchmark(_rank_docs, docs)


def test_bench_entity_salience_medium(benchmark):
    docs = [_make_fake_doc(30) for _ in range(10_000)]
    benchmark(_rank_docs, docs)


def test_bench_entity_salience_large(benchmark):
    docs = [_make_fake_doc(50) for _ in range(100_000)]
    benchmark(_rank_docs, docs)


# ── Readability (#19) ─────────────────────────────────────────────


def _readability_batch(texts):
    from apps.sources.readability import score

    for t in texts:
        score(t)


def test_bench_readability_small(benchmark):
    rng = random.Random(0)
    texts = [_random_paragraph(rng, 50) for _ in range(1000)]
    benchmark(_readability_batch, texts)


def test_bench_readability_medium(benchmark):
    rng = random.Random(0)
    texts = [_random_paragraph(rng, 500) for _ in range(10_000)]
    benchmark(_readability_batch, texts)


def test_bench_readability_large(benchmark):
    rng = random.Random(0)
    texts = [_random_paragraph(rng, 1000) for _ in range(1_000_000)]
    benchmark(_readability_batch, texts)


# ── Product Quantization (#20) — skipped without FAISS ───────────


def _faiss_available() -> bool:
    try:
        import faiss  # noqa: F401
        return True
    except ImportError:
        return False


@pytest.mark.skipif(not _faiss_available(), reason="faiss not installed")
def test_bench_product_quantization_small(benchmark):
    import numpy as np
    from apps.sources.product_quantization import ProductQuantizer

    rng = np.random.default_rng(0)
    train = rng.standard_normal((10_000, 1024)).astype("float32")
    pq = ProductQuantizer(dimension=1024, m_subvectors=8)
    pq.fit(train)
    encode_batch = rng.standard_normal((10_000, 1024)).astype("float32")
    benchmark(pq.encode, encode_batch)


@pytest.mark.skipif(not _faiss_available(), reason="faiss not installed")
def test_bench_product_quantization_medium(benchmark):
    import numpy as np
    from apps.sources.product_quantization import ProductQuantizer

    rng = np.random.default_rng(0)
    train = rng.standard_normal((200_000, 1024)).astype("float32")
    pq = ProductQuantizer(dimension=1024, m_subvectors=8)
    pq.fit(train)
    encode_batch = rng.standard_normal((100_000, 1024)).astype("float32")
    benchmark(pq.encode, encode_batch)


@pytest.mark.skipif(not _faiss_available(), reason="faiss not installed")
def test_bench_product_quantization_large(benchmark):
    import numpy as np
    from apps.sources.product_quantization import ProductQuantizer

    rng = np.random.default_rng(0)
    train = rng.standard_normal((200_000, 1024)).astype("float32")
    pq = ProductQuantizer(dimension=1024, m_subvectors=8)
    pq.fit(train)
    encode_batch = rng.standard_normal((1_000_000, 1024)).astype("float32")
    benchmark(pq.encode, encode_batch)
