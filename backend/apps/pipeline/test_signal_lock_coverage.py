"""
Phase SEQ — CI coverage test for ``with_signal_lock()``.

Every Celery ``@shared_task`` that computes a ranking signal MUST wear
the ``with_signal_lock()`` decorator so that signal computations are
serialised on a single Redis namespace. Without this gate, someone
adding a new ``compute_signal_*`` task for meta-algorithms (FR-099…FR-224)
could accidentally let it run in parallel with other signals, saturating
GPU/CPU and tanking pipeline throughput.

Approach
--------
We don't bootstrap Django or Celery in this test — we walk the source
tree with ``ast`` and inspect decorator names directly. This keeps the
test cheap (runs in milliseconds) and lets it live in CI even when the
full app is unavailable.

A task qualifies if ANY of:
  * its ``def`` name matches the regex ``compute_signal_.*``
  * its ``@shared_task(name=...)`` keyword ends in ``compute_signal_*``
    (so tasks whose function body has a terser name but whose public
    Celery name is ``suggestions.compute_signal_authority`` are caught)

Each qualifying function must ALSO carry ``@with_signal_lock()`` or an
equivalent call to ``with_signal_lock``. Violators are reported with
file + line so the fix is one ``git blame`` away.

This test passes vacuously today (no ``compute_signal_*`` tasks exist
yet). It turns into a hard CI failure the moment someone adds one
without the decorator — exactly the guardrail the approved plan called
for.
"""

from __future__ import annotations

import ast
import pathlib
import re


# Anchor to the repo root so local runs and CI runs behave the same.
_THIS_FILE = pathlib.Path(__file__).resolve()
_REPO_ROOT = _THIS_FILE.parents[3]  # .../backend/apps/pipeline/ -> repo root
_APPS_ROOT = _REPO_ROOT / "backend" / "apps"

_SIGNAL_NAME_RE = re.compile(r"compute_signal_[A-Za-z0-9_]+")


def _iter_python_files(root: pathlib.Path):
    for path in root.rglob("*.py"):
        # Skip migrations + the test itself + generated __pycache__.
        if "migrations" in path.parts:
            continue
        if "__pycache__" in path.parts:
            continue
        if path.name.startswith("test_"):
            continue
        yield path


def _qualifies_as_signal_task(func: ast.FunctionDef) -> bool:
    """Return True if this function looks like a ranking-signal compute task."""
    if _SIGNAL_NAME_RE.fullmatch(func.name):
        return True
    # Look for @shared_task(name="...compute_signal_...")
    for dec in func.decorator_list:
        if not isinstance(dec, ast.Call):
            continue
        # Covers `@shared_task(...)` and `@celery_app.task(...)`
        dec_name = _dotted_name(dec.func)
        if not dec_name.endswith("shared_task") and not dec_name.endswith(".task"):
            continue
        for kw in dec.keywords:
            if kw.arg != "name":
                continue
            if isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                if _SIGNAL_NAME_RE.search(kw.value.value):
                    return True
    return False


def _has_signal_lock(func: ast.FunctionDef) -> bool:
    """Return True if the function carries ``@with_signal_lock()`` (or equiv)."""
    for dec in func.decorator_list:
        # Bare decorator usage `@with_signal_lock` — still counts, even
        # though the canonical form is `@with_signal_lock()`.
        name = _dotted_name(dec.func if isinstance(dec, ast.Call) else dec)
        if name.endswith("with_signal_lock"):
            return True
    return False


def _dotted_name(node: ast.AST) -> str:
    """Render ``a.b.c`` from an ast.Attribute/ast.Name chain."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{_dotted_name(node.value)}.{node.attr}"
    return ""


def test_every_signal_compute_task_uses_with_signal_lock():
    """Every ``compute_signal_*`` task must wear ``@with_signal_lock()``.

    Vacuously passes while no such tasks exist. Fails loudly the moment
    one lands without the decorator.
    """
    violations: list[str] = []
    for path in _iter_python_files(_APPS_ROOT):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError:
            # Non-fatal — some generated fixtures may be invalid Python.
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if not _qualifies_as_signal_task(node):
                continue
            if _has_signal_lock(node):
                continue
            violations.append(
                f"{path.relative_to(_REPO_ROOT)}:{node.lineno} — "
                f"`{node.name}` is a ranking-signal compute task but "
                f"is missing `@with_signal_lock()`."
            )

    assert not violations, (
        "Phase SEQ violation — the following ranking-signal compute tasks "
        "must declare `@with_signal_lock()` (see apps/pipeline/decorators.py). "
        "Running signals in parallel will saturate GPU/CPU and drag the "
        "whole pipeline.\n\n"
        + "\n".join("  - " + v for v in violations)
    )


def test_coverage_scanner_detects_missing_decorator_when_planted():
    """Self-check: the scanner must catch a violation when we plant one.

    Rationale: if the scanner ever silently degrades to "zero matches",
    the guardrail becomes useless. We plant a decoy source string,
    parse it through the same AST helpers, and assert a violation is
    reported.
    """
    decoy = (
        "from celery import shared_task\n"
        "@shared_task(bind=True, name='suggestions.compute_signal_decoy')\n"
        "def compute_signal_decoy(self):\n"
        "    return 0\n"
    )
    tree = ast.parse(decoy)
    funcs = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
    assert len(funcs) == 1
    f = funcs[0]
    assert _qualifies_as_signal_task(f), "Scanner failed to classify decoy as a signal task."
    assert not _has_signal_lock(f), "Scanner wrongly reports the decoy has a lock."


def test_coverage_scanner_accepts_properly_decorated_task():
    """Self-check: a correctly-decorated task must pass the scanner."""
    good = (
        "from celery import shared_task\n"
        "from apps.pipeline.decorators import with_signal_lock\n"
        "@shared_task(bind=True, name='suggestions.compute_signal_good')\n"
        "@with_signal_lock()\n"
        "def compute_signal_good(self):\n"
        "    return 1\n"
    )
    tree = ast.parse(good)
    funcs = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
    assert len(funcs) == 1
    f = funcs[0]
    assert _qualifies_as_signal_task(f)
    assert _has_signal_lock(f), "Scanner missed a valid @with_signal_lock decorator."
