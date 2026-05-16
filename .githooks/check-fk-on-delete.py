#!/usr/bin/env python3
"""Rule H.H22 — verify explicit on_delete on every Django ForeignKey.

File-scoped: only fires on staged backend/apps/**/models.py files.
AST-based: parses the file and asserts every `models.ForeignKey(...)`
and `models.OneToOneField(...)` call includes an `on_delete=...` keyword.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _staged_models_files() -> list[Path]:
    try:
        out = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
            cwd=str(REPO_ROOT), capture_output=True, text=True,
            timeout=10, check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
    paths: list[Path] = []
    for line in (out.stdout or "").splitlines():
        line = line.strip()
        if not line:
            continue
        if not line.endswith(".py"):
            continue
        if "/models.py" not in line and not line.endswith("/models.py"):
            continue
        if not line.startswith("backend/apps/"):
            continue
        paths.append(REPO_ROOT / line)
    return paths


def _scan(path: Path) -> list[tuple[int, str]]:
    """Return [(line_no, snippet)] of FK declarations missing on_delete."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(text, filename=str(path))
    except (OSError, SyntaxError):
        return []
    hits: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        # Match models.ForeignKey / models.OneToOneField
        name = None
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
            if func.value.id == "models" and func.attr in {"ForeignKey", "OneToOneField"}:
                name = func.attr
        if name is None:
            continue
        has_on_delete = any(
            kw.arg == "on_delete" for kw in node.keywords
        )
        if not has_on_delete:
            hits.append((node.lineno, name))
    return hits


def main() -> int:
    files = _staged_models_files()
    if not files:
        return 0
    all_hits: dict[str, list[tuple[int, str]]] = {}
    for f in files:
        hits = _scan(f)
        if hits:
            all_hits[str(f.relative_to(REPO_ROOT))] = hits
    if not all_hits:
        return 0
    sys.stderr.write(
        "FAIL check-fk-on-delete: ForeignKey / OneToOneField declared "
        "without explicit `on_delete=...` keyword.\n"
        "WHY: Rule H.H22 requires every FK to declare what happens when "
        "the referenced row is deleted (`CASCADE`, `PROTECT`, `SET_NULL`, "
        "`SET_DEFAULT`, `DO_NOTHING`). The Django default changed in 2.x "
        "and an implicit on_delete can silently cascade deletions in ways "
        "that delete operator data unexpectedly.\n"
        "UNBLOCK: For each match below, decide the right policy and add "
        "`on_delete=models.<policy>` to the FK call. Most data tables want "
        "`PROTECT` for parents you don't want auto-deleted, `CASCADE` only "
        "for true child rows, `SET_NULL` (with null=True) for soft "
        "relationships. If you genuinely believe Django's default is "
        "correct here (very rare), file:\n"
        "  docker compose exec -T backend python manage.py "
        "report_hook_false_positive --hook check-fk-on-delete "
        "--context \"<explanation>\"\n"
    )
    for path, hits in all_hits.items():
        for line_no, kind in hits:
            sys.stderr.write(f"  {path}:{line_no}: models.{kind}(...) missing on_delete\n")
    return 2


if __name__ == "__main__":
    sys.exit(main())
