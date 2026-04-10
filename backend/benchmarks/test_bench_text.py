"""Benchmarks for text processing C++ extensions (texttok, phrasematch, fieldrel, rareterm)."""

import numpy as np


def _import_texttok():
    import texttok
    return texttok


def _import_phrasematch():
    import phrasematch
    return phrasematch


def _import_fieldrel():
    import fieldrel
    return fieldrel


def _import_rareterm():
    import rareterm
    return rareterm


# ── Tokenization ────────────────────────────────────────────────


def test_bench_tokenize_small(benchmark, sample_texts_small, stopwords):
    texttok = _import_texttok()
    benchmark(texttok.tokenize_text_batch, sample_texts_small, stopwords)


def test_bench_tokenize_medium(benchmark, sample_texts_medium, stopwords):
    texttok = _import_texttok()
    benchmark(texttok.tokenize_text_batch, sample_texts_medium, stopwords)


def test_bench_tokenize_large(benchmark, sample_texts_large, stopwords):
    texttok = _import_texttok()
    benchmark(texttok.tokenize_text_batch, sample_texts_large, stopwords)


# ── Phrase Matching ─────────────────────────────────────────────


def test_bench_phrasematch_small(benchmark):
    phrasematch = _import_phrasematch()
    left = ["hello", "world", "test", "python", "benchmark"]
    right = ["hello", "world", "fast", "code", "test"]
    benchmark(phrasematch.longest_contiguous_overlap, left, right)


def test_bench_phrasematch_medium(benchmark):
    phrasematch = _import_phrasematch()
    rng = np.random.default_rng(42)
    words = ["alpha", "beta", "gamma", "delta", "epsilon", "zeta",
             "eta", "theta", "iota", "kappa", "lambda", "mu",
             "nu", "xi", "omicron", "pi", "rho", "sigma", "tau", "upsilon"]
    left = list(rng.choice(words, size=20))
    right = list(rng.choice(words, size=20))
    benchmark(phrasematch.longest_contiguous_overlap, left, right)


def test_bench_phrasematch_large(benchmark):
    phrasematch = _import_phrasematch()
    rng = np.random.default_rng(42)
    words = ["alpha", "beta", "gamma", "delta", "epsilon", "zeta",
             "eta", "theta", "iota", "kappa", "lambda", "mu",
             "nu", "xi", "omicron", "pi", "rho", "sigma", "tau", "upsilon"]
    left = list(rng.choice(words, size=100))
    right = list(rng.choice(words, size=100))
    benchmark(phrasematch.longest_contiguous_overlap, left, right)


# ── Field Relevance ─────────────────────────────────────────────


def test_bench_fieldrel_small(benchmark):
    fieldrel = _import_fieldrel()
    n = 5
    tokens = [f"token{i}" for i in range(n)]
    benchmark(fieldrel.score_field_tokens,
              tokens, [2] * n, [1] * n, [50] * n,
              100, 80.0, 0.75, 500, 1.5, 10)


def test_bench_fieldrel_medium(benchmark):
    fieldrel = _import_fieldrel()
    n = 20
    tokens = [f"token{i}" for i in range(n)]
    benchmark(fieldrel.score_field_tokens,
              tokens, [2] * n, [1] * n, [50] * n,
              100, 80.0, 0.75, 500, 1.5, 10)


def test_bench_fieldrel_large(benchmark):
    fieldrel = _import_fieldrel()
    n = 100
    tokens = [f"token{i}" for i in range(n)]
    benchmark(fieldrel.score_field_tokens,
              tokens, [2] * n, [1] * n, [50] * n,
              100, 80.0, 0.75, 500, 1.5, 10)


# ── Rare Terms ──────────────────────────────────────────────────


def test_bench_rareterm_small(benchmark):
    rareterm = _import_rareterm()
    terms = [f"term{i}" for i in range(10)]
    evidences = [0.5] * 10
    pages = [3] * 10
    host = frozenset(terms[:5] + [f"extra{i}" for i in range(45)])
    benchmark(rareterm.evaluate_rare_terms,
              terms, evidences, pages, host, 10)


def test_bench_rareterm_medium(benchmark):
    rareterm = _import_rareterm()
    terms = [f"term{i}" for i in range(100)]
    evidences = [0.5] * 100
    pages = [3] * 100
    host = frozenset(terms[:50] + [f"extra{i}" for i in range(450)])
    benchmark(rareterm.evaluate_rare_terms,
              terms, evidences, pages, host, 10)


def test_bench_rareterm_large(benchmark):
    rareterm = _import_rareterm()
    terms = [f"term{i}" for i in range(1000)]
    evidences = [0.5] * 1000
    pages = [3] * 1000
    host = frozenset(terms[:500] + [f"extra{i}" for i in range(4500)])
    benchmark(rareterm.evaluate_rare_terms,
              terms, evidences, pages, host, 10)
