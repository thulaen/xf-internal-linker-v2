#!/usr/bin/env python3
"""Rule H.H4 — block mutable default arguments in Python (`def f(x=[])`).

File-scoped: only fires when staged Python files exist.
Checks the staged Python files directly so the hook works on MSI without
local Docker or a local ruff install.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

_MUTABLE_CALLS = {"dict", "list", "set", "defaultdict"}


@dataclass(frozen=True)
class MutableDefaultFinding:
    path: str
    line: int
    column: int
    label: str


def _staged_py_files() -> list[str]:
    try:
        out = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
            cwd=str(REPO_ROOT), capture_output=True, text=True,
            timeout=10, check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
    return [
        line.strip() for line in (out.stdout or "").splitlines()
        if line.strip().endswith(".py")
        and line.strip().startswith(("backend/", "scripts/"))
    ]


def _find_mutable_defaults(path: str, source: str) -> list[MutableDefaultFinding]:
    tree = ast.parse(source, filename=path)
    lines = source.splitlines()
    findings: list[MutableDefaultFinding] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda):
            continue
        for default in _function_defaults(node):
            label = _mutable_default_label(default)
            if label and not _has_noqa_b006(lines, default.lineno):
                findings.append(
                    MutableDefaultFinding(path, default.lineno, default.col_offset + 1, label)
                )
    return findings


def _function_defaults(
    node: ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda,
) -> list[ast.expr]:
    defaults = list(node.args.defaults)
    defaults.extend(default for default in node.args.kw_defaults if default is not None)
    return defaults


def _mutable_default_label(node: ast.expr) -> str:
    if isinstance(node, ast.List):
        return "list literal []"
    if isinstance(node, ast.Dict):
        return "dict literal {}"
    if isinstance(node, ast.Set):
        return "set literal"
    if isinstance(node, ast.Call) and _call_name(node.func) in _MUTABLE_CALLS:
        return f"{_call_name(node.func)}() call"
    return ""


def _call_name(func: ast.expr) -> str:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def _has_noqa_b006(lines: list[str], line_number: int) -> bool:
    if line_number < 1 or line_number > len(lines):
        return False
    line = lines[line_number - 1]
    waiver_marker = "# " + "noqa"
    return waiver_marker in line and "B006" in line


def _scan_files(files: list[str]) -> tuple[list[MutableDefaultFinding], list[str]]:
    findings: list[MutableDefaultFinding] = []
    parse_errors: list[str] = []
    for file_name in files:
        path = REPO_ROOT / file_name
        try:
            source = path.read_text(encoding="utf-8")
            findings.extend(_find_mutable_defaults(file_name, source))
        except (OSError, UnicodeDecodeError, SyntaxError) as exc:
            parse_errors.append(f"{file_name}: {exc}")
    return findings, parse_errors


def main() -> int:
    files = _staged_py_files()
    if not files:
        return 0
    findings, parse_errors = _scan_files(files)
    if parse_errors:
        sys.stderr.write(
            "FAIL check-mutable-defaults: a staged Python file could not be parsed.\n"
            "WHY: The mutable-default check must read the Python syntax before "
            "it can prove defaults are safe.\n"
            "UNBLOCK: fix the syntax or encoding error below, then re-run.\n\n"
            + "\n".join(parse_errors)
            + "\n"
        )
        return 2
    if not findings:
        return 0
    details = "\n".join(
        f"  {finding.path}:{finding.line}:{finding.column} {finding.label}"
        for finding in findings
    )
    sys.stderr.write(
        "FAIL check-mutable-defaults: mutable default arguments were found "
        "on staged Python files.\n"
        "WHY: Rule H.H4 forbids `def f(x=[])` / `def f(x={})` — Python "
        "evaluates the default ONCE and shares it across every call, which "
        "is almost always a subtle bug. Use `None` and assign inside:\n"
        "  def f(x=None):\n"
        "      x = x or []\n"
        "UNBLOCK: Apply the None-sentinel fix above, OR if this is a "
        "deliberate intent (rare), add `# noqa: B006` with a short justifier "
        "comment, OR file:\n"
        "  python scripts/backend_manage.py "
        "report_hook_false_positive --hook check-mutable-defaults "
        "--context \"<explanation>\"\n"
        f"\nMatches:\n{details}\n"
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
