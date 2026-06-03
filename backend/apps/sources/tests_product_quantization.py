"""Convention-named discovery shim for apps/sources/product_quantization.py.

The mutation gate only discovers a file named ``tests_<stem>.py`` in the same
directory as ``<stem>.py``. The proven coverage for ``product_quantization.py``
lives in the suite-level ``tests.py`` next to this file under the class
``ProductQuantizationTests``. Rather than duplicate the asserted behaviour
(which would drift), this shim re-exports that test class under the discoverable
name so the same assertions run when the gate collects
``tests_product_quantization.py``.

The re-exported class is a ``SimpleTestCase`` that constructs ``ProductQuantizer``
objects and validates parameter checks, byte sizing, and (when FAISS is
importable) a round-trip — no database, no network, so this is hang-safe for the
mutation gate.
"""

from __future__ import annotations

from apps.sources.tests import ProductQuantizationTests  # noqa: F401

__all__ = ["ProductQuantizationTests"]
