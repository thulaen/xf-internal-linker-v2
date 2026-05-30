"""Regression guard: every C++ extension registered in setup.py must have its source on disk.

A pybind11 kernel registered in ``backend/extensions/setup.py`` whose ``.cpp`` source is
missing makes the build step fail to produce that module, which crash-loops the backend
at import time. This is exactly the ``bench_helpers`` incident (2026-05): a kernel was
registered with no source file and every container restart died building it.

This test parses ``setup.py`` statically with ``ast`` (no build, no Docker, no import of
setup.py) and asserts every ``Pybind11Extension(name, [sources...])`` points at files that
exist. It runs in a plain ``SimpleTestCase``-style pytest with no database.
"""

from __future__ import annotations

import ast
from pathlib import Path

EXT_DIR = Path(__file__).resolve().parents[1]  # backend/extensions
SETUP_PY = EXT_DIR / "setup.py"


def _registered_sources() -> list[tuple[str, str]]:
    """Return ``(module_name, source_path)`` pairs from every ``Pybind11Extension`` call."""
    tree = ast.parse(SETUP_PY.read_text(encoding="utf-8"))
    pairs: list[tuple[str, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
        if name != "Pybind11Extension" or len(node.args) < 2:
            continue
        module, sources = node.args[0], node.args[1]
        if not isinstance(module, ast.Constant) or not isinstance(sources, ast.List):
            continue
        for src in sources.elts:
            if isinstance(src, ast.Constant) and isinstance(src.value, str):
                pairs.append((module.value, src.value))
    return pairs


def test_setup_py_registers_at_least_one_extension() -> None:
    assert _registered_sources(), "setup.py registered no Pybind11Extension sources to check"


def test_every_registered_extension_source_exists() -> None:
    missing = [
        (module, src)
        for module, src in _registered_sources()
        if not (EXT_DIR / src).is_file()
    ]
    assert not missing, (
        "setup.py registers C++ extensions whose source files are missing: "
        + ", ".join(f"{module} -> {src}" for module, src in missing)
        + ". A registered kernel with no source crash-loops the backend at build time "
        "(the bench_helpers incident). Remove the dead registration or add the source."
    )
