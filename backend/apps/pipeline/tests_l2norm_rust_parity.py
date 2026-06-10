"""Parity tests: the Rust `extensions.l2norm` kernel vs a NumPy reference oracle.

The Rust kernel (`rust/extensions/l2norm`, built to `l2norm.so` and staged at
`/opt/xf/compiled/active/extensions/`) is the SOLE implementation of the L2
normalization hot path that `apps.pipeline.services.embeddings._l2_normalize`
calls. The C++ `l2norm` kernel and the old pure-NumPy fallback were both deleted
when this Rust kernel landed (RUST-FIRST.md zero-fallback / dead-code-on-
replace). These tests prove the Rust output matches an independent NumPy
reference on random float32 matrices, within single-precision tolerance.

Two checks:

1. ``_numpy_l2_reference`` mirrors the Rust kernel semantics exactly: each row
   is normalized to unit L2 norm in place, and a row whose norm is ``<= 1e-10``
   is left unchanged (the kernel's no-op guard). The Rust kernel must match it.
2. The live ``embeddings._l2_normalize`` entry point (now Rust-only) must also
   match that reference on non-degenerate rows (norm well above the guard) —
   the regime the embedding pipeline actually runs in. This proves the
   production call site, not just the kernel.

Source for the semantics: the FR-237 L2-norm audit notes in
``apps/pipeline/services/embeddings.py`` (the C++ kernel that previously held
this logic, ``backend/extensions/l2norm.cpp``, was deleted in the Rust port).

Skipped (not failed) when the Rust `.so` is not built/staged yet, so the suite
stays green on a host that has not run the compiled-artifacts build. The
build-and-wire step (``scripts/ensure_compiled_artifacts.py``) is what flips
this from skipped to executed.
"""

from __future__ import annotations

import unittest

import numpy as np

try:
    from extensions import l2norm as rust_l2norm

    _HAS_L2NORM = hasattr(rust_l2norm, "normalize_l2_batch") and hasattr(
        rust_l2norm, "normalize_l2"
    )
except ImportError:
    _HAS_L2NORM = False

_MIN_NORM = 1e-10
_F32_TOL = 1e-5


def _numpy_l2_reference(arr: np.ndarray) -> np.ndarray:
    """Row-wise unit-L2 reference matching the C++/Rust kernel semantics.

    Rows whose L2 norm is ``<= 1e-10`` are passed through unchanged; every
    other row is divided by its norm. Operates on a float32 copy and returns
    float32, so the comparison is single-precision against single-precision.
    """
    out = arr.astype(np.float32, copy=True)
    norms = np.linalg.norm(out, axis=1)
    for row_index, norm in enumerate(norms):
        if norm > _MIN_NORM:
            out[row_index] = out[row_index] / np.float32(norm)
    return out


@unittest.skipUnless(
    _HAS_L2NORM,
    "Rust extensions.l2norm not built/staged yet — run "
    "scripts/ensure_compiled_artifacts.py in the compiled-tools image.",
)
class RustL2NormParityTests(unittest.TestCase):
    """Random-matrix parity of the Rust kernel against the NumPy reference."""

    def test_random_batches_match_numpy_reference(self) -> None:
        rng = np.random.default_rng(20260606)
        for rows, cols in [(1, 1), (3, 4), (17, 1024), (64, 128), (256, 1536)]:
            with self.subTest(rows=rows, cols=cols):
                base = rng.standard_normal((rows, cols)).astype(np.float32)
                expected = _numpy_l2_reference(base)

                actual = np.ascontiguousarray(base, dtype=np.float32)
                rust_l2norm.normalize_l2_batch(actual)

                np.testing.assert_allclose(
                    actual, expected, rtol=0, atol=_F32_TOL
                )
                # Each non-degenerate row is unit-norm after normalization.
                norms = np.linalg.norm(actual, axis=1)
                np.testing.assert_allclose(
                    norms, np.ones(rows, dtype=np.float32), rtol=0, atol=_F32_TOL
                )

    def test_subthreshold_row_left_unchanged(self) -> None:
        # Row 0 is below the 1e-10 guard (must be untouched); row 1 is normal.
        arr = np.array(
            [[1e-12, 1e-12, 1e-12], [3.0, 4.0, 0.0]], dtype=np.float32
        )
        original_row0 = arr[0].copy()
        rust_l2norm.normalize_l2_batch(arr)

        np.testing.assert_array_equal(arr[0], original_row0)
        np.testing.assert_allclose(
            arr[1], np.array([0.6, 0.8, 0.0], dtype=np.float32), atol=_F32_TOL
        )

    def test_live_l2_normalize_matches_numpy_reference(self) -> None:
        """The live ``embeddings._l2_normalize`` == the NumPy reference oracle.

        ``_l2_normalize`` is now Rust-only (RUST-FIRST.md zero-fallback — the
        old ``HAS_CPP_EXT`` flag and NumPy fallback branch were deleted with the
        C++ kernel). On rows whose norm is well above the ``1e-10`` guard — the
        regime the embedding pipeline runs in, since real embedding vectors are
        never near-zero — the Rust-backed entry point and the independent NumPy
        reference are numerically identical. This is the parity that matters at
        runtime, proven through the production call site rather than the kernel
        directly.
        """
        from apps.pipeline.services import embeddings as embeddings_module

        rng = np.random.default_rng(424242)
        base = rng.standard_normal((48, 256)).astype(np.float32)
        expected = _numpy_l2_reference(base)

        live_out = embeddings_module._l2_normalize(base.copy())

        np.testing.assert_allclose(live_out, expected, rtol=0, atol=_F32_TOL)

    def test_normalize_l2_1d_in_place(self) -> None:
        vec = np.array([3.0, 4.0], dtype=np.float32)
        rust_l2norm.normalize_l2(vec)
        np.testing.assert_allclose(
            vec, np.array([0.6, 0.8], dtype=np.float32), atol=_F32_TOL
        )

    def test_non_2d_input_raises_value_error(self) -> None:
        one_d = np.array([1.0, 2.0, 3.0], dtype=np.float32)
        with self.assertRaises(ValueError):
            rust_l2norm.normalize_l2_batch(one_d)


if __name__ == "__main__":
    unittest.main()
