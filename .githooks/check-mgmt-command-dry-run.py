#!/usr/bin/env python3
"""Rule H.H25 — Django management commands must support `--dry-run`.

File-scoped: only fires on staged backend/apps/**/management/commands/*.py
files (excluding __init__.py). AST-based.

A command must either:
  - Define a `--dry-run` argument in `add_arguments`, OR
  - Carry the marker comment `# xf: no_dry_run -- <reason>`

Read-only commands (print_*, search_*, verify_*) are exempt by name
prefix because they never mutate state.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

_READ_ONLY_PREFIXES = (
    "print_", "search_", "verify_", "show_", "list_",
)


def _staged_commands() -> list[Path]:
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
        if not line.startswith("backend/apps/"):
            continue
        if "/management/commands/" not in line:
            continue
        if not line.endswith(".py"):
            continue
        if line.endswith("/__init__.py"):
            continue
        name = Path(line).stem
        if any(name.startswith(p) for p in _READ_ONLY_PREFIXES):
            continue
        paths.append(REPO_ROOT / line)
    return paths


def _has_dry_run(path: Path) -> bool:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return True  # don't block on read error
    if "# xf: no_dry_run" in text:
        return True
    try:
        tree = ast.parse(text, filename=str(path))
    except SyntaxError:
        return True
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            # parser.add_argument("--dry-run", ...)
            if (
                isinstance(node.func, ast.Attribute)
                and node.func.attr == "add_argument"
            ):
                for arg in node.args:
                    if isinstance(arg, ast.Constant) and arg.value == "--dry-run":
                        return True
    return False


def main() -> int:
    files = _staged_commands()
    if not files:
        return 0
    missing = [f for f in files if not _has_dry_run(f)]
    if not missing:
        return 0
    sys.stderr.write(
        "FAIL check-mgmt-command-dry-run: management command(s) missing "
        "`--dry-run` flag.\n"
        "WHY: Rule H.H25 requires every Django management command that "
        "mutates state to support `--dry-run` so operators can preview "
        "what the command would do before letting it actually run. This "
        "prevents accidental data loss during maintenance jobs.\n"
        "UNBLOCK: In each command's `add_arguments(self, parser)`, add:\n"
        "  parser.add_argument(\"--dry-run\", action=\"store_true\",\n"
        "      help=\"Show what would change without applying.\")\n"
        "Then guard mutating calls with `if not opts['dry_run']:`. If the "
        "command is genuinely read-only or dry-run makes no sense, add the "
        "marker comment `# xf: no_dry_run -- <one-line reason>` at the top "
        "of the file. If you believe this hook fired in error, file:\n"
        "  docker compose exec -T backend python manage.py "
        "report_hook_false_positive --hook check-mgmt-command-dry-run "
        "--context \"<explanation>\"\n"
    )
    for f in missing:
        sys.stderr.write(f"  missing --dry-run: {f.relative_to(REPO_ROOT)}\n")
    return 2


if __name__ == "__main__":
    sys.exit(main())
