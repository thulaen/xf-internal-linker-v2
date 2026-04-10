"""
Shared fixtures for Python benchmarks.

These benchmarks measure hot-path performance of the C++ extensions
called from Python, and key pipeline functions.

Run with: pytest backend/benchmarks/ --benchmark-json=results/python.json
"""

import sys
from pathlib import Path

import numpy as np
import pytest

# ── Ensure extensions are importable ──────────────────────────────
# Extensions are built in backend/extensions/ via setup.py build_ext --inplace
ext_dir = Path(__file__).resolve().parent.parent / "extensions"
if str(ext_dir) not in sys.path:
    sys.path.insert(0, str(ext_dir))


@pytest.fixture
def small_embeddings():
    """100 rows x 384 dims, float32."""
    rng = np.random.default_rng(42)
    return rng.standard_normal((100, 384)).astype(np.float32)


@pytest.fixture
def medium_embeddings():
    """10,000 rows x 384 dims, float32."""
    rng = np.random.default_rng(42)
    return rng.standard_normal((10_000, 384)).astype(np.float32)


@pytest.fixture
def large_embeddings():
    """100,000 rows x 384 dims, float32."""
    rng = np.random.default_rng(42)
    return rng.standard_normal((100_000, 384)).astype(np.float32)


@pytest.fixture
def query_embedding():
    """Single 384-dim query vector, float32."""
    rng = np.random.default_rng(99)
    return rng.standard_normal(384).astype(np.float32)


@pytest.fixture
def stopwords():
    """Common English stopwords set."""
    return frozenset({
        "the", "a", "an", "is", "are", "was", "were", "be", "been",
        "being", "have", "has", "had", "do", "does", "did", "will",
        "would", "could", "should", "may", "might", "can", "shall",
        "to", "of", "in", "for", "on", "with", "at", "by", "from",
    })


@pytest.fixture
def sample_texts_small():
    """10 short texts."""
    rng = np.random.default_rng(42)
    words = ["hello", "world", "python", "benchmark", "test", "performance",
             "measure", "speed", "fast", "slow", "code", "optimize"]
    return [" ".join(rng.choice(words, size=15)) for _ in range(10)]


@pytest.fixture
def sample_texts_medium():
    """1,000 texts."""
    rng = np.random.default_rng(42)
    words = ["hello", "world", "python", "benchmark", "test", "performance",
             "measure", "speed", "fast", "slow", "code", "optimize",
             "internal", "linking", "content", "page", "url", "anchor"]
    return [" ".join(rng.choice(words, size=20)) for _ in range(1_000)]


@pytest.fixture
def sample_texts_large():
    """10,000 texts."""
    rng = np.random.default_rng(42)
    words = ["hello", "world", "python", "benchmark", "test", "performance",
             "measure", "speed", "fast", "slow", "code", "optimize",
             "internal", "linking", "content", "page", "url", "anchor"]
    return [" ".join(rng.choice(words, size=20)) for _ in range(10_000)]


@pytest.fixture
def bbcode_small():
    """~500 chars of BBCode with links."""
    return (
        '[url=https://example.com/page1]Link One[/url] some text here '
        '<a href="https://example.com/page2">Link Two</a> more text '
        'https://example.com/bare-url and some filler content to pad'
    )


@pytest.fixture
def bbcode_medium():
    """~10K chars of BBCode with links."""
    base = (
        '[url=https://example.com/page{i}]Link {i}[/url] filler text '
        '<a href="https://example.com/html{i}">Anchor {i}</a> padding '
        'https://example.com/bare{i} more text and content here. '
    )
    return "".join(base.format(i=i) for i in range(60))


@pytest.fixture
def bbcode_large():
    """~100K chars of BBCode with links."""
    base = (
        '[url=https://example.com/page{i}]Link {i}[/url] filler text '
        '<a href="https://example.com/html{i}">Anchor {i}</a> padding '
        'https://example.com/bare{i} more text and content here. '
    )
    return "".join(base.format(i=i) for i in range(600))
