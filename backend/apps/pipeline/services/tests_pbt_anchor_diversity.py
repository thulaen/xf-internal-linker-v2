"""Property-based tests for the pure anchor-text normalizer.

`normalize_anchor_text` is pure (str -> str, no I/O), so it is an ideal
property target. We assert the invariants a normalizer must hold for *every*
input rather than for a handful of examples.

Speed rules (see scripts/run-pbt.sh):
  * Construct, never filter — inputs come straight from `st.text(max_size=50)`;
    no `assume()` discards generated data.
  * Small scope — strings are capped at 50 characters.
  * Pure logic only — zero database / network / disk / clock here.
"""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from apps.pipeline.services.anchor_diversity import normalize_anchor_text

pytestmark = pytest.mark.property

# Bounded, constructed directly — no post-generation filtering.
_ANCHORS = st.text(max_size=50)


@given(raw=_ANCHORS)
def test_normalize_is_idempotent(raw: str) -> None:
    """Normalizing an already-normalized value changes nothing."""
    once = normalize_anchor_text(raw)
    assert normalize_anchor_text(once) == once


@given(raw=_ANCHORS)
def test_normalize_output_has_no_edge_whitespace(raw: str) -> None:
    """The result never has leading or trailing whitespace."""
    out = normalize_anchor_text(raw)
    assert out == out.strip()


@given(raw=_ANCHORS)
def test_normalize_output_is_lowercase(raw: str) -> None:
    """The result is always lower-cased (it feeds case-insensitive reuse checks)."""
    out = normalize_anchor_text(raw)
    assert out == out.lower()


@given(raw=_ANCHORS)
def test_normalize_collapses_internal_whitespace(raw: str) -> None:
    """Internal whitespace is collapsed — no run of two or more spaces remains."""
    out = normalize_anchor_text(raw)
    assert "  " not in out


@given(raw=_ANCHORS)
def test_normalize_never_raises(raw: str) -> None:
    """Any string input returns a string without raising."""
    assert isinstance(normalize_anchor_text(raw), str)
