#!/usr/bin/env python3
"""Pre-commit guard: dead code is deleted in the SAME step that replaces it.

``docs/PYTHON-RUST-MIGRATION-PLAN.md`` § "Dead-code handling" requires that
when a commit deletes a module — a Python fallback after a Rust port, a
removed-language source, or an orphan — no surviving staged file may still
``import`` the deleted module. A leftover reference is a dangling import: the
module is gone, so the code crashes at runtime the next time that line runs.

This guard reads the modules a commit deletes (staged ``D`` entries under the
scanned source roots, mapped to dotted module names) and scans every other
staged file's text. If any surviving file still references a deleted module,
the commit is hard-blocked.

The pure core ``dangling_references`` takes the deleted dotted names and the
staged files' text directly, so it is unit-tested with no git involved.

Run manually:
    python .githooks/check-dead-code-on-replace.py
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Source roots whose deletions map to dotted Python module names.
_PY_ROOTS = ("backend/",)


def _module_name_for(path: str) -> str:
    """Map a repo-relative ``.py`` path to its dotted module name.

    ``backend/apps/pipeline/services/ranker_fallback.py`` ->
    ``backend.apps.pipeline.services.ranker_fallback``. ``__init__.py`` maps to
    its package. Returns ``""`` for non-Python paths.
    """
    p = path.replace("\\", "/")
    if not p.endswith(".py"):
        return ""
    stem = p[: -len(".py")]
    if stem.endswith("/__init__"):
        stem = stem[: -len("/__init__")]
    return stem.replace("/", ".")


def _reference_patterns(name: str) -> tuple[re.Pattern[str], ...]:
    """Patterns that match a surviving ``import``/``from`` reference to *name*.

    A reference is the deleted dotted name itself OR any of its parent packages
    re-pointing at the deleted leaf is intentionally NOT matched — only the
    exact deleted module (and deeper) counts, so deleting a leaf never falsely
    flags an unrelated sibling.
    """
    esc = re.escape(name)
    # `from <name> import ...` / `from <name>.sub import ...`
    from_re = re.compile(rf"^\s*from\s+{esc}(?:\.[A-Za-z0-9_.]+)?\s+import\b", re.M)
    # `import <name>` / `import <name> as x` / `import <name>.sub`
    import_re = re.compile(rf"^\s*import\s+{esc}(?:\.[A-Za-z0-9_]+)*(?:\s+as\s+\w+)?\s*$", re.M)
    return (from_re, import_re)


def dangling_references(deleted_modules: list[str], files: dict[str, str]) -> list[str]:
    """Return staged files that still import a deleted module.

    Pure and git-free. *deleted_modules* are dotted names the commit removes
    (e.g. ``"backend.apps.pipeline.services.ranker_fallback"``). *files* maps a
    repo-relative path to its staged text. A file is flagged when its text
    contains an ``import <name>`` or ``from <name>`` reference to any deleted
    module. An empty *deleted_modules* set yields ``[]``.
    """
    if not deleted_modules:
        return []
    patterns = [(name, _reference_patterns(name)) for name in deleted_modules if name]
    flagged: list[str] = []
    for path, text in files.items():
        for _name, pats in patterns:
            if any(pat.search(text) for pat in pats):
                flagged.append(path)
                break
    return flagged


def _git(args: list[str]) -> str:
    try:
        out = subprocess.run(
            ["git", *args], cwd=str(REPO_ROOT), capture_output=True, text=True,
            encoding="utf-8", errors="replace", check=False,
        )
    except (FileNotFoundError, OSError):
        return ""
    return out.stdout or ""


def _deleted_modules() -> list[str]:
    names: list[str] = []
    out = _git(["diff", "--cached", "--name-only", "--diff-filter=D"])
    for raw in out.splitlines():
        path = raw.strip()
        if not path:
            continue
        if not any(path.replace("\\", "/").startswith(root) for root in _PY_ROOTS):
            continue
        mod = _module_name_for(path)
        if mod:
            names.append(mod)
    return names


def _surviving_files() -> dict[str, str]:
    files: dict[str, str] = {}
    out = _git(["diff", "--cached", "--name-only", "--diff-filter=ACM"])
    for raw in out.splitlines():
        path = raw.strip()
        if not path or not path.replace("\\", "/").endswith(".py"):
            continue
        files[path] = _git(["show", f":{path}"])
    return files


def main() -> int:
    deleted = _deleted_modules()
    flagged = dangling_references(deleted, _surviving_files())
    if not flagged:
        return 0
    sys.stderr.write(
        "FAIL check-dead-code-on-replace: a staged file still imports a module "
        "this commit deletes.\n"
        "WHY: docs/PYTHON-RUST-MIGRATION-PLAN.md § \"Dead-code handling\" "
        "requires dead code to be removed in the SAME step that replaces it. A "
        "surviving `import`/`from` to a deleted module is a dangling import that "
        "crashes at runtime once that line runs.\n"
        "DELETED MODULES:\n  " + "\n  ".join(deleted) + "\n"
        "STILL REFERENCED IN:\n  " + "\n  ".join(flagged) + "\n"
        "UNBLOCK: in the same commit, delete or re-point every listed reference "
        "to the replacement module, then re-run the verification sweep (ruff "
        "F401, vulture, and a grep for the deleted name returning zero callers).\n"
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
