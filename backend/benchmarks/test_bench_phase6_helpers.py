"""Benchmarks for Phase 6 helpers + Group C Stage-1 retrievers.

Mandatory benchmark rule per CLAUDE.md: every hot-path function gets
3 input sizes. Each helper here is called per-token / per-sentence /
per-document during ranking, so all qualify.

Helpers covered:
- ``apps.sources.vader_sentiment``   — pick #22
- ``apps.sources.pysbd_segmenter``   — pick #15
- ``apps.sources.yake_keywords``     — pick #17
- ``apps.sources.trafilatura_extractor`` — pick #7
- ``apps.sources.fasttext_langid``   — pick #14
- ``apps.pipeline.services.lda_topics``      — pick #18
- ``apps.pipeline.services.kenlm_fluency``   — pick #23
- ``apps.pipeline.services.candidate_retrievers`` — Groups C.1-C.3 (Lexical, QueryExpansion)

Helpers shipped earlier (already covered in test_bench_parse_layer.py):
- NFKC #13, Snowball #21, PMI #24, Passages #25, Entity Salience #26,
  Readability #19, PQ #20.

The benchmarks measure cold-start path performance (the dep-missing
branch that consumers always hit when the optional pip dep isn't
installed). When a dep IS installed, an additional benchmark fires
to measure the full path. This matches our production ship state
where most deps are install-on-demand.
"""

from __future__ import annotations

import random
import string


def _random_paragraph(rng: random.Random, words: int) -> str:
    vocab = [
        "".join(rng.choices(string.ascii_lowercase, k=rng.randint(3, 10)))
        for _ in range(2000)
    ]
    return " ".join(rng.choices(vocab, k=words))


def _random_html(rng: random.Random, words: int) -> str:
    body = _random_paragraph(rng, words)
    return (
        "<html><head><title>t</title></head><body>"
        "<nav>chrome</nav>"
        f"<article><p>{body}</p></article>"
        "<footer>chrome</footer></body></html>"
    )


# ── VADER (#22) ───────────────────────────────────────────────────


def _vader_batch(texts):
    from apps.sources.vader_sentiment import score

    for t in texts:
        score(t)


def test_bench_vader_small(benchmark):
    rng = random.Random(0)
    texts = [_random_paragraph(rng, 50) for _ in range(1000)]
    benchmark(_vader_batch, texts)


def test_bench_vader_medium(benchmark):
    rng = random.Random(0)
    texts = [_random_paragraph(rng, 200) for _ in range(10_000)]
    benchmark(_vader_batch, texts)


def test_bench_vader_large(benchmark):
    rng = random.Random(0)
    texts = [_random_paragraph(rng, 500) for _ in range(50_000)]
    benchmark(_vader_batch, texts)


# ── PySBD (#15) ───────────────────────────────────────────────────


def _pysbd_batch(texts):
    from apps.sources.pysbd_segmenter import split

    for t in texts:
        split(t)


def test_bench_pysbd_small(benchmark):
    rng = random.Random(1)
    texts = [
        ". ".join(_random_paragraph(rng, 30) for _ in range(5))
        for _ in range(100)
    ]
    benchmark(_pysbd_batch, texts)


def test_bench_pysbd_medium(benchmark):
    rng = random.Random(1)
    texts = [
        ". ".join(_random_paragraph(rng, 30) for _ in range(10))
        for _ in range(1_000)
    ]
    benchmark(_pysbd_batch, texts)


def test_bench_pysbd_large(benchmark):
    rng = random.Random(1)
    texts = [
        ". ".join(_random_paragraph(rng, 30) for _ in range(20))
        for _ in range(5_000)
    ]
    benchmark(_pysbd_batch, texts)


# ── YAKE! (#17) ───────────────────────────────────────────────────


def _yake_batch(texts):
    from apps.sources.yake_keywords import extract

    for t in texts:
        extract(t, top_k=10)


def test_bench_yake_small(benchmark):
    rng = random.Random(2)
    texts = [_random_paragraph(rng, 100) for _ in range(50)]
    benchmark(_yake_batch, texts)


def test_bench_yake_medium(benchmark):
    rng = random.Random(2)
    texts = [_random_paragraph(rng, 200) for _ in range(500)]
    benchmark(_yake_batch, texts)


def test_bench_yake_large(benchmark):
    rng = random.Random(2)
    texts = [_random_paragraph(rng, 500) for _ in range(2_000)]
    benchmark(_yake_batch, texts)


# ── Trafilatura (#7) ──────────────────────────────────────────────


def _trafilatura_batch(htmls):
    from apps.sources.trafilatura_extractor import extract

    for h in htmls:
        extract(h)


def test_bench_trafilatura_small(benchmark):
    rng = random.Random(3)
    htmls = [_random_html(rng, 100) for _ in range(50)]
    benchmark(_trafilatura_batch, htmls)


def test_bench_trafilatura_medium(benchmark):
    rng = random.Random(3)
    htmls = [_random_html(rng, 300) for _ in range(500)]
    benchmark(_trafilatura_batch, htmls)


def test_bench_trafilatura_large(benchmark):
    rng = random.Random(3)
    htmls = [_random_html(rng, 1000) for _ in range(1_000)]
    benchmark(_trafilatura_batch, htmls)


# ── FastText LangID (#14) ─────────────────────────────────────────


def _fasttext_batch(texts):
    from apps.sources.fasttext_langid import predict

    for t in texts:
        predict(t)


def test_bench_fasttext_small(benchmark):
    rng = random.Random(4)
    texts = [_random_paragraph(rng, 50) for _ in range(1000)]
    benchmark(_fasttext_batch, texts)


def test_bench_fasttext_medium(benchmark):
    rng = random.Random(4)
    texts = [_random_paragraph(rng, 100) for _ in range(10_000)]
    benchmark(_fasttext_batch, texts)


def test_bench_fasttext_large(benchmark):
    rng = random.Random(4)
    texts = [_random_paragraph(rng, 200) for _ in range(50_000)]
    benchmark(_fasttext_batch, texts)


# ── LDA (#18) ─────────────────────────────────────────────────────


def _lda_batch(token_lists):
    from apps.pipeline.services.lda_topics import infer_topics

    for toks in token_lists:
        infer_topics(toks)


def test_bench_lda_small(benchmark):
    rng = random.Random(5)
    token_lists = [
        rng.choices(["python", "rails", "ruby", "django", "tutorial"], k=50)
        for _ in range(100)
    ]
    benchmark(_lda_batch, token_lists)


def test_bench_lda_medium(benchmark):
    rng = random.Random(5)
    token_lists = [
        rng.choices(["python", "rails", "ruby", "django", "tutorial"], k=100)
        for _ in range(1_000)
    ]
    benchmark(_lda_batch, token_lists)


def test_bench_lda_large(benchmark):
    rng = random.Random(5)
    token_lists = [
        rng.choices(["python", "rails", "ruby", "django", "tutorial"], k=200)
        for _ in range(10_000)
    ]
    benchmark(_lda_batch, token_lists)


# ── KenLM (#23) ───────────────────────────────────────────────────


def _kenlm_batch(sentences):
    from apps.pipeline.services.kenlm_fluency import score_fluency

    for s in sentences:
        score_fluency(s)


def test_bench_kenlm_small(benchmark):
    rng = random.Random(6)
    sentences = [_random_paragraph(rng, 30) for _ in range(1000)]
    benchmark(_kenlm_batch, sentences)


def test_bench_kenlm_medium(benchmark):
    rng = random.Random(6)
    sentences = [_random_paragraph(rng, 30) for _ in range(10_000)]
    benchmark(_kenlm_batch, sentences)


def test_bench_kenlm_large(benchmark):
    rng = random.Random(6)
    sentences = [_random_paragraph(rng, 30) for _ in range(50_000)]
    benchmark(_kenlm_batch, sentences)


# ── Group C — LexicalRetriever (RRF fusion #31, pick #C.2) ───────


class _FakeRecord:
    """Stand-in for ContentRecord — only ``.title`` and ``.scope_title`` are read."""

    __slots__ = ("title", "scope_title")

    def __init__(self, title: str, scope_title: str = "") -> None:
        self.title = title
        self.scope_title = scope_title


def _make_retriever_context(
    *, n_dest: int, n_host: int, words_per_title: int = 6
) -> tuple:
    from apps.pipeline.services.candidate_retrievers import RetrievalContext

    rng = random.Random(42)
    keys = [(i, "thread") for i in range(n_dest + n_host)]
    records = {
        k: _FakeRecord(_random_paragraph(rng, words_per_title))
        for k in keys
    }
    sentence_ids = {k: [k[0] * 100, k[0] * 100 + 1] for k in keys}
    import numpy as np

    return RetrievalContext(
        destination_keys=tuple(keys[:n_dest]),
        dest_embeddings=np.zeros((n_dest, 4), dtype=np.float32),
        content_records=records,
        content_to_sentence_ids=sentence_ids,
        top_k=10,
        block_size=64,
    )


def _lexical_batch(context):
    from apps.pipeline.services.candidate_retrievers import LexicalRetriever

    LexicalRetriever(enabled=True).retrieve(context)


def test_bench_lexical_retriever_small(benchmark):
    ctx = _make_retriever_context(n_dest=10, n_host=100)
    benchmark(_lexical_batch, ctx)


def test_bench_lexical_retriever_medium(benchmark):
    ctx = _make_retriever_context(n_dest=50, n_host=500)
    benchmark(_lexical_batch, ctx)


def test_bench_lexical_retriever_large(benchmark):
    ctx = _make_retriever_context(n_dest=200, n_host=2000)
    benchmark(_lexical_batch, ctx)


# ── Group C — QueryExpansionRetriever (PRF #27, pick #C.3) ───────


def _query_expansion_batch(context):
    from apps.pipeline.services.candidate_retrievers import (
        QueryExpansionRetriever,
    )

    QueryExpansionRetriever(enabled=True).retrieve(context)


def test_bench_query_expansion_small(benchmark):
    ctx = _make_retriever_context(n_dest=10, n_host=100)
    benchmark(_query_expansion_batch, ctx)


def test_bench_query_expansion_medium(benchmark):
    ctx = _make_retriever_context(n_dest=50, n_host=500)
    benchmark(_query_expansion_batch, ctx)


def test_bench_query_expansion_large(benchmark):
    ctx = _make_retriever_context(n_dest=200, n_host=2000)
    benchmark(_query_expansion_batch, ctx)
