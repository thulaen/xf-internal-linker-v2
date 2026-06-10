"""Shared loader for the Rust hot-path kernels (RUST-FIRST.md, zero fallback).

Many backend hot paths are owned by a Rust kernel built with PyO3 + maturin and
imported as ``extensions.<name>``. The policy in ``RUST-FIRST.md`` is
zero-fallback: there is no Python copy of the hot path, so a missing or broken
kernel must fail **loudly** at the point of use, never silently drop to a slower
Python implementation.

Before this module, that "import the kernel or raise a loud error" logic was
copy-pasted into each caller (``embeddings.py``, ``anchor_garbage_signals.py``,
…). This module is the single place that owns it, so every caller raises the
same actionable error pointing at the Docker-managed rebuild.

Usage::

    from apps.pipeline.services.rust_kernels import load_kernel

    l2norm = load_kernel("extensions.l2norm", "normalize_l2_batch")
    l2norm.normalize_l2_batch(buffer)

If the kernel module cannot be imported, or it imports but is missing the named
public attribute, ``load_kernel`` raises :class:`KernelUnavailableError` (a
:class:`RuntimeError` subclass, so existing ``except RuntimeError`` call sites
keep working).
"""

from __future__ import annotations

import importlib
from types import ModuleType

_REBUILD_HINT = (
    "There is no Python fallback (RUST-FIRST.md zero-fallback). Rebuild the "
    "Rust kernel in the Docker-managed compiled-tools image via "
    "scripts/ensure_compiled_artifacts.py, then restart the backend."
)


class KernelUnavailableError(RuntimeError):
    """Raised when a required Rust kernel is missing or incomplete.

    Subclasses :class:`RuntimeError` so call sites that already catch
    ``RuntimeError`` (the pre-refactor contract) continue to work unchanged.
    """


def load_kernel(module_name: str, attr_name: str) -> ModuleType:
    """Import the Rust kernel ``module_name`` and verify it exposes ``attr_name``.

    Returns the imported module on success. Raises
    :class:`KernelUnavailableError` — loudly, with a rebuild hint — when the
    module cannot be imported or is missing the required public attribute.

    Args:
        module_name: The dotted import path of the kernel, e.g.
            ``"extensions.l2norm"``.
        attr_name: A public attribute the caller depends on (a function or a
            class). Verifying it here turns a half-built or stale ``.so`` into a
            clear error at load time instead of a confusing ``AttributeError``
            deep in the hot path.
    """
    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:
        raise KernelUnavailableError(
            f"Rust kernel '{module_name}' is not loaded. {_REBUILD_HINT} "
            f"Original import error: {exc}"
        ) from exc

    if not hasattr(module, attr_name):
        raise KernelUnavailableError(
            f"Rust kernel '{module_name}' imported but is missing the required "
            f"attribute '{attr_name}' — the built .so is stale or incomplete. "
            f"{_REBUILD_HINT}"
        )

    return module
