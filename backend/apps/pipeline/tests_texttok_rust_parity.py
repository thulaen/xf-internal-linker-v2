"""Parity tests: the Rust `extensions.texttok` kernel vs the Python regex oracle.

The Rust kernel (`rust/extensions/texttok`, built to `texttok.so` and staged at
`/opt/xf/compiled/active/extensions/`) is the SOLE native implementation of the
ASCII-tokenizer hot path that `apps.pipeline.services.text_tokens.tokenize_text`
calls. The C++ `texttok` kernel (`backend/extensions/texttok.cpp` + its header,
fuzz harness, and shared benchmark translation unit) was deleted when this Rust
kernel landed (RUST-FIRST.md zero-fallback / dead-code-on-replace).

The byte-parity oracle is the pure-Python reference kept in
`text_tokens.py`: ``_tokenize_text_py`` / ``tokenize_text_batch`` implement the
authoritative behaviour — ``TOKEN_RE = [A-Za-z0-9]+(?:'[A-Za-z0-9]+)?`` plus
stopword removal, lowercase, and de-duplication into a ``frozenset``. The parity
basis for this kernel is EXACT (deterministic byte scanning, no hashing, no
floats), so these tests assert exact frozenset-by-frozenset equality between the
Rust kernel and the Python reference, not an approximate tolerance.

This complements the older ``TextTokenizerExtensionTests`` in
``apps/pipeline/tests.py`` (which asserts the same equality on a fixed corpus)
by adding contraction / boundary / non-ASCII edge cases and the
return-type contract (each element is a real ``frozenset``).

Skipped (not failed) when the Rust ``.so`` is not built/staged yet, so the suite
stays green on a host that has not run the compiled-artifacts build. The
build-and-wire step (``scripts/ensure_compiled_artifacts.py``) flips this from
skipped to executed.
"""

from __future__ import annotations

import unittest

from apps.pipeline.services import text_tokens as text_tokens_service

try:
    from extensions import texttok as rust_texttok

    _HAS_TEXTTOK = hasattr(rust_texttok, "tokenize_text_batch")
except ImportError:
    _HAS_TEXTTOK = False


# A corpus that exercises every branch of the tokenizer: separators, digits,
# ASCII lowercasing, the single-apostrophe contraction rule and its boundary
# (trailing apostrophe, apostrophe at end of string, apostrophe followed by a
# non-alnum byte), non-ASCII bytes acting as separators, duplicate collapse, and
# stopword removal (including contraction stopwords like "don't").
_CORPUS = [
    "",
    "the and or but",
    "don't stop believing",
    "can't stop won't stop",
    "it's a test",
    "Hello WORLD",
    "abc123 xyz789",
    "cafe",
    "café",
    "café and tea",
    "A typical sentence for token testing.",
    "Numbers 123 456 and words",
    "Mixed CASE and Don't Repeat don't repeat",
    "one,two;three",
    "rock'n'roll",
    "URL http://example.com/path",
    "Email me@example.com now",
    "Quote 'single' and apostrophe don't",
    "Tabs\tand\nnewlines",
    "Repeat repeat REPEAT unique",
    "dogs' bones",  # trailing apostrophe must not fold
    "cat'",  # apostrophe at end of string boundary
    "a'b'c",  # only one apostrophe group per token
    "rock' n",  # apostrophe followed by space, no fold
]


@unittest.skipUnless(
    _HAS_TEXTTOK,
    "Rust extensions.texttok not built/staged yet — run "
    "scripts/ensure_compiled_artifacts.py in the compiled-tools image.",
)
class RustTextTokParityTests(unittest.TestCase):
    """Exact parity of the Rust kernel against the Python regex reference."""

    def test_batch_matches_python_reference_exactly(self) -> None:
        py_result = text_tokens_service.tokenize_text_batch(
            _CORPUS, text_tokens_service.STANDARD_ENGLISH_STOPWORDS
        )
        rust_result = rust_texttok.tokenize_text_batch(
            _CORPUS, text_tokens_service.STANDARD_ENGLISH_STOPWORDS
        )

        # Outer list length and order preserved.
        self.assertEqual(len(rust_result), len(py_result))
        for index, (rust_tokens, py_tokens) in enumerate(
            zip(rust_result, py_result, strict=True)
        ):
            with self.subTest(index=index, text=_CORPUS[index]):
                self.assertEqual(rust_tokens, py_tokens)

    def test_each_element_is_a_frozenset(self) -> None:
        # Load-bearing return-type contract: callers do frozenset set ops and
        # `tokenize_text()` indexes [0]; a plain set or list would break them.
        rust_result = rust_texttok.tokenize_text_batch(
            ["Hello world", ""], text_tokens_service.STANDARD_ENGLISH_STOPWORDS
        )
        for element in rust_result:
            self.assertIsInstance(element, frozenset)

    def test_accepts_frozenset_stopwords_iterable(self) -> None:
        # The stopword argument is a generic iterable; the real callers pass a
        # frozenset. An empty input set keeps every non-empty token.
        rust_result = rust_texttok.tokenize_text_batch(
            ["the quick brown fox"], frozenset()
        )
        self.assertEqual(
            rust_result[0], frozenset({"the", "quick", "brown", "fox"})
        )

    def test_live_tokenize_text_matches_reference(self) -> None:
        """The live ``text_tokens.tokenize_text`` (now Rust-only) == reference.

        ``tokenize_text`` is Rust-only (RUST-FIRST.md zero-fallback — the old
        ``HAS_CPP_EXT`` try/except branch was deleted with the C++ kernel). It
        must equal the Python reference for the same single text.
        """
        for text in _CORPUS:
            with self.subTest(text=text):
                live = text_tokens_service.tokenize_text(text)
                reference = text_tokens_service.tokenize_text_batch(
                    [text or ""], text_tokens_service.STANDARD_ENGLISH_STOPWORDS
                )[0]
                self.assertEqual(live, reference)


if __name__ == "__main__":
    unittest.main()
