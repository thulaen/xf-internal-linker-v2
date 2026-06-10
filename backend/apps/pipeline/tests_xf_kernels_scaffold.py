"""Scaffold proof for the Rust + PyO3 + maturin build path.

This test proves the end-to-end Rust extension build path works: a Rust
crate (``rust/xf_kernels``) compiled by maturin into a native Python
extension module that Python can ``import`` and call. It does NOT test a
real ported kernel yet -- only that the build path is alive.

``xf_kernels`` is built inside the compiled-tools Docker container (the one
image that has both a Rust toolchain and Python headers). When this test
runs in an environment where that wheel has been installed, the import
succeeds and the two trivial functions return correct values. When the
wheel is not installed (for example the runtime ``backend`` image, which has
no Rust toolchain and never builds extensions), the test skips with a clear
message rather than failing -- the same skip-if-absent discipline the C++
kernel tests use for ``extensions.*`` modules.

Functions proved:
- ``xf_kernels.version()`` returns a non-empty string (the crate version).
- ``xf_kernels.l2_norm([3.0, 4.0])`` returns ``5.0`` -- the Euclidean
  (L2) norm sqrt(3**2 + 4**2) = sqrt(25) = 5.0, a hand-verifiable value.
"""

from __future__ import annotations

import importlib
import math

from django.test import SimpleTestCase

try:  # pragma: no cover - import guard mirrors the C++ kernel test pattern
    xf_kernels = importlib.import_module("xf_kernels")
    HAS_XF_KERNELS = True
    XF_KERNELS_IMPORT_ERROR = ""
except ImportError as exc:  # pragma: no cover - exercised only when absent
    xf_kernels = None
    HAS_XF_KERNELS = False
    XF_KERNELS_IMPORT_ERROR = str(exc)


class XfKernelsScaffoldTests(SimpleTestCase):
    """Prove the Rust/PyO3/maturin extension imports and computes correctly."""

    def setUp(self) -> None:
        if not HAS_XF_KERNELS:
            self.skipTest(
                "xf_kernels native module not installed in this Python "
                "environment; build it with maturin inside the compiled-tools "
                f"container. Import error: {XF_KERNELS_IMPORT_ERROR}"
            )

    def test_version_returns_non_empty_string(self) -> None:
        result = xf_kernels.version()
        self.assertIsInstance(result, str)
        self.assertNotEqual(result.strip(), "")

    def test_l2_norm_of_3_4_is_5(self) -> None:
        # sqrt(3**2 + 4**2) = sqrt(9 + 16) = sqrt(25) = 5.0
        self.assertEqual(xf_kernels.l2_norm([3.0, 4.0]), 5.0)

    def test_l2_norm_of_empty_list_is_zero(self) -> None:
        self.assertEqual(xf_kernels.l2_norm([]), 0.0)

    def test_l2_norm_matches_math_hypot_for_three_values(self) -> None:
        values = [1.5, 2.0, 2.5]
        expected = math.sqrt(sum(v * v for v in values))
        self.assertAlmostEqual(xf_kernels.l2_norm(values), expected, places=6)
