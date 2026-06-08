#!/usr/bin/env python3
"""Pre-commit guard: the backend is Python + Rust ONLY.

C, C++, Go, Haskell, Lua, and Java are removed languages (see
``docs/adr/0007-python-rust-two-language.md`` and
``docs/PYTHON-RUST-MIGRATION-PLAN.md``). This hook hard-blocks any staged file
that ADDS or MODIFIES a removed-language source. It is the backstop that makes
the policy stick: no matter which old plan an agent follows, a commit that
reintroduces one of these languages is refused.

What is NOT blocked:
  * Rust (``.rs``, ``Cargo.toml``, ``Cargo.lock``) and Python — the two kept
    languages.
  * DELETING a removed-language file — the migration removes them. The staged
    set is filtered to Added/Copied/Modified (``--diff-filter=ACM``), so a
    deletion never reaches this guard.

Run manually:
    python .githooks/check-removed-languages.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Source extensions of the removed languages -> human label.
_BLOCKED_EXT: dict[str, str] = {
    ".cpp": "C/C++", ".cc": "C/C++", ".cxx": "C/C++", ".c": "C/C++", ".cu": "C/C++",
    ".hpp": "C/C++", ".hh": "C/C++", ".hxx": "C/C++", ".h": "C/C++",
    ".go": "Go", ".proto": "Go",
    ".hs": "Haskell", ".lhs": "Haskell", ".cabal": "Haskell",
    ".lua": "Lua",
    ".java": "Java",
}
# Exact filenames of removed-language build/manifest files -> label.
_BLOCKED_NAME: dict[str, str] = {
    "go.mod": "Go", "go.sum": "Go",
}


def removed_language(path: str) -> str | None:
    """Return the removed-language label for *path*, or None if it is allowed.

    Pure + path-only so it is unit-testable without git. Rust and Python paths
    return None (allowed).
    """
    norm = path.replace("\\", "/")
    name = norm.rsplit("/", 1)[-1]
    if name in _BLOCKED_NAME:
        return _BLOCKED_NAME[name]
    dot = name.rfind(".")
    if dot == -1:
        return None
    return _BLOCKED_EXT.get(name[dot:].lower())


def classify_staged(paths: list[str]) -> list[tuple[str, str]]:
    """Return [(path, language)] for every removed-language file in *paths*."""
    out: list[tuple[str, str]] = []
    for path in paths:
        lang = removed_language(path)
        if lang is not None:
            out.append((path, lang))
    return out


def _staged_files() -> list[str]:
    try:
        out = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
            cwd=str(REPO_ROOT), capture_output=True, text=True,
            encoding="utf-8", errors="replace", check=False,
        )
    except (FileNotFoundError, OSError):
        return []
    return [ln.strip() for ln in (out.stdout or "").splitlines() if ln.strip()]


def main() -> int:
    violations = classify_staged(_staged_files())
    if not violations:
        return 0
    listed = "\n".join(f"  {path}  ({lang})" for path, lang in violations)
    sys.stderr.write(
        "FAIL check-removed-languages: a staged file adds/modifies a removed "
        "language.\n"
        "WHY: this backend is Python + Rust ONLY. C/C++, Go, Haskell, Lua, and "
        "Java were removed (hot paths are Rust via PyO3; everything else is "
        "Python). An old plan may still describe these languages — do not build "
        "from it. See docs/adr/0007-python-rust-two-language.md and "
        "docs/PYTHON-RUST-MIGRATION-PLAN.md.\n"
        "REMOVED-LANGUAGE FILES:\n" + listed + "\n"
        "UNBLOCK: implement the change in Python (or Rust for a proven hot "
        "path) instead. To remove one of these files, DELETE it (deletions are "
        "allowed); do not add or modify it.\n"
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
