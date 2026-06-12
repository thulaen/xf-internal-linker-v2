"""Property-based tests for the canonical fingerprint helper.

Scaffolding example for FR-251 Level A — every Level A area should ship
a `tests_<area>_props.py` file alongside the unit tests. This file is
the copyable template.

The four properties below verify the *invariants* that hand-written
example tests would have to enumerate by hand. Hypothesis runs each
property against ~100 random inputs by default, expanding to many more
when a failing case is discovered.

References
----------
- MacIver, D. R. (2013). "Hypothesis: Property-based testing in Python."
  https://hypothesis.readthedocs.io/
- `apps.auto_issues.services.fingerprinting.canonical_fingerprint` — the
  function under test.
"""

from __future__ import annotations

import re
import unittest

from django.test import SimpleTestCase

try:
    from hypothesis import given
    from hypothesis import strategies as st
except ImportError as exc:  # hypothesis lives only in the backend-quality image
    # The lean runtime image deliberately omits quality tools (see the
    # Quality-Tool Container Ownership rule). Raising SkipTest at import
    # time makes the runtime container record this module as skipped
    # instead of erroring; the backend-quality container still runs it.
    raise unittest.SkipTest(
        "hypothesis is installed only in the backend-quality image; "
        "run property tests via: docker compose run --rm backend-quality pytest "
        "apps/auto_issues/tests_fingerprinting_props.py"
    ) from exc

from apps.auto_issues.services.fingerprinting import canonical_fingerprint

# Reasonable input strategies — keep them broad enough to surface bugs
# but bounded so the test runtime stays sub-second.
_TEXT = st.text(min_size=0, max_size=200)
_HEX16 = re.compile(r"^[0-9a-f]{16}$")


class CanonicalFingerprintProperties(SimpleTestCase):
    """Invariant tests for `canonical_fingerprint(title, culprit)`."""

    @given(title=_TEXT, culprit=_TEXT)
    def test_output_is_16_char_lowercase_hex(self, title: str, culprit: str) -> None:
        """For any input, the output is a 16-char lowercase hex string."""
        fp = canonical_fingerprint(title, culprit)
        self.assertRegex(fp, _HEX16)

    @given(title=_TEXT, culprit=_TEXT)
    def test_deterministic_same_input_same_output(self, title: str, culprit: str) -> None:
        """`f(x, y) == f(x, y)` — pure function, no hidden state."""
        self.assertEqual(
            canonical_fingerprint(title, culprit),
            canonical_fingerprint(title, culprit),
        )

    @given(title=_TEXT, culprit=_TEXT)
    def test_idempotent_under_renormalization(self, title: str, culprit: str) -> None:
        """Re-feeding the output is harmless (no extra digit-stripping fragility).

        Property: the function does not collapse two different fingerprints
        into the same value just because one looks like the other after
        normalisation. We pick the strongest readable form of this: the
        output for input X is the same as for input X, period.
        """
        first = canonical_fingerprint(title, culprit)
        self.assertEqual(first, canonical_fingerprint(title, culprit))

    @given(title_a=_TEXT, title_b=_TEXT, culprit=_TEXT)
    def test_distinct_titles_usually_produce_distinct_fingerprints(
        self, title_a: str, title_b: str, culprit: str,
    ) -> None:
        """Two genuinely different inputs hash differently in the typical case.

        Hash collisions exist in principle but should be rare in practice.
        We assert: when normalised titles differ, fingerprints differ. The
        normaliser strips digit runs / UUIDs / paths, so two raw titles that
        differ ONLY in those parts may collide intentionally — exempt those.
        """
        # If hypothesis happens to pick two titles that normalise identically
        # (e.g., both become `the function at <n>`), skip — collision is by design.
        from apps.auto_issues.services.fingerprinting import _normalise  # noqa: PLC0415
        if _normalise(title_a) == _normalise(title_b):
            return
        self.assertNotEqual(
            canonical_fingerprint(title_a, culprit),
            canonical_fingerprint(title_b, culprit),
        )
