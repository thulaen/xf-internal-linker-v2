#!/usr/bin/env python3
"""Slice 1.5 — block direct Python<->Go imports across the services tier.

Rule F-compliant (FAIL / WHY / UNBLOCK). Hard-block at commit.

What this hook enforces (per ADR 0006 § Decision point 3 and
docs/MODULAR-MONOLITH.md § Services tier rule 3):

  Python may not import or shell into Go services. Go may not embed or shell
  into Python code. The only legal channel is the RPC contract declared in
  services/<name>/api.proto or services/<name>/api.http.md.

What it flags (using AST for Python and a comment-stripped regex pass for Go,
so docstrings and comments do not trip the hook):

  Python: ctypes.CDLL(...) / ctypes.cdll.LoadLibrary(...) whose argument is a
          string literal pointing into `services/`. subprocess.run|call|Popen|
          check_output|check_call whose first arg references a `services/`
          path. os.system(...) likewise.

  Go:     exec.Command("python"|"python3"|"manage.py"|"/repo/backend/...").
          exec.CommandContext(ctx, "python"|...).

The hook's helper `scan_paths(paths)` is exposed for unit tests so the test
suite never has to write to the real git index.
"""

from __future__ import annotations

import ast
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parent.parent

# Files outside these suffixes are skipped — keeps the scan cheap.
_PY_SUFFIXES = (".py",)
_GO_SUFFIXES = (".go",)

# Subprocess functions we care about.
_SUBPROCESS_FUNCS = frozenset(
    {"run", "call", "Popen", "check_output", "check_call"}
)

# Substrings inside a string-literal argument that indicate the Python code is
# shelling into the services tier. The leading "./" form is the common one.
_SERVICES_HINTS = ("services/", "./services/")

# Comment / string stripper for Go source.
_GO_TOKEN_RE = re.compile(
    r'("(?:\\.|[^"\\\n])*")|(`[^`]*`)|(//[^\n]*)|(/\*[\s\S]*?\*/)',
)

# exec.Command / exec.CommandContext calls that name a Python entry point or
# reach into the backend Django tree. The (?:...,\s*) optional non-capturing
# group covers CommandContext's extra `ctx` first argument.
_GO_EXEC_RE = re.compile(
    r'\bexec\.(?:Command|CommandContext)\s*\('
    r'(?:[^,()]+,\s*)?'
    r'"(python|python3|manage\.py|/repo/backend/[^"]+)"'
)


@dataclass(frozen=True)
class Violation:
    path: Path
    line: int
    snippet: str
    rule: str


# ---------------------------------------------------------------------------
# Python scan
# ---------------------------------------------------------------------------


def _string_arg_contains_services(node: ast.Call) -> bool:
    """Return True if any positional or keyword arg is a string-literal that
    points into the services tier."""

    def _check_const(value: object) -> bool:
        if not isinstance(value, str):
            return False
        return any(hint in value for hint in _SERVICES_HINTS)

    for arg in node.args:
        if isinstance(arg, ast.Constant) and _check_const(arg.value):
            return True
        if isinstance(arg, (ast.List, ast.Tuple)):
            for elt in arg.elts:
                if isinstance(elt, ast.Constant) and _check_const(elt.value):
                    return True
    for kw in node.keywords:
        if kw.arg in ("args", "executable", "shell_command") and isinstance(
            kw.value, ast.Constant
        ):
            if _check_const(kw.value.value):
                return True
    return False


def _is_ctypes_load(node: ast.Call) -> bool:
    """Match `ctypes.CDLL(...)` and `ctypes.cdll.LoadLibrary(...)`."""
    f = node.func
    if isinstance(f, ast.Attribute):
        if f.attr == "CDLL" and isinstance(f.value, ast.Name) and f.value.id == "ctypes":
            return True
        if f.attr == "LoadLibrary" and isinstance(f.value, ast.Attribute):
            inner = f.value
            if (
                inner.attr == "cdll"
                and isinstance(inner.value, ast.Name)
                and inner.value.id == "ctypes"
            ):
                return True
    return False


def _is_subprocess_call(node: ast.Call) -> bool:
    """Match `subprocess.run(...)` and the other subprocess entry points."""
    f = node.func
    if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name):
        return f.value.id == "subprocess" and f.attr in _SUBPROCESS_FUNCS
    return False


def _is_os_system(node: ast.Call) -> bool:
    """Match `os.system(...)`."""
    f = node.func
    if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name):
        return f.value.id == "os" and f.attr == "system"
    return False


def _scan_python(path: Path, source: str) -> list[Violation]:
    """Return every cross-language-import violation in a Python source string."""
    violations: list[Violation] = []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return violations
    lines = source.splitlines()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        snippet = ""
        line_no = getattr(node, "lineno", 0)
        if 0 < line_no <= len(lines):
            snippet = lines[line_no - 1].strip()[:160]
        if _is_ctypes_load(node) and _string_arg_contains_services(node):
            violations.append(
                Violation(path, line_no, snippet, "ctypes.CDLL into services/")
            )
        elif _is_subprocess_call(node) and _string_arg_contains_services(node):
            violations.append(
                Violation(path, line_no, snippet, "subprocess into services/")
            )
        elif _is_os_system(node) and _string_arg_contains_services(node):
            violations.append(
                Violation(path, line_no, snippet, "os.system into services/")
            )
    return violations


# ---------------------------------------------------------------------------
# Go scan
# ---------------------------------------------------------------------------


def _strip_go_noncode(source: str) -> str:
    """Remove `// ...` line comments and `/* ... */` block comments while
    preserving double-quoted and backtick-quoted string literals so we never
    flag matches that sit inside a comment or doc-string-style header."""

    def _repl(match: re.Match[str]) -> str:
        # Group 1 = "..." string. Group 2 = `...` raw string. Both kept.
        if match.group(1) is not None or match.group(2) is not None:
            return match.group(0)
        # Group 3 / 4 = line / block comment. Replace with whitespace of the
        # same length so line numbers are preserved.
        text = match.group(0)
        return "".join("\n" if ch == "\n" else " " for ch in text)

    return _GO_TOKEN_RE.sub(_repl, source)


def _scan_go(path: Path, source: str) -> list[Violation]:
    """Return every exec.Command-into-Python violation in a Go source string."""
    violations: list[Violation] = []
    cleaned = _strip_go_noncode(source)
    lines = cleaned.splitlines()
    for line_no, line in enumerate(lines, start=1):
        match = _GO_EXEC_RE.search(line)
        if match:
            violations.append(
                Violation(
                    path,
                    line_no,
                    line.strip()[:160],
                    f"exec.Command(\"{match.group(1)}\", ...)",
                )
            )
    return violations


# ---------------------------------------------------------------------------
# Public API used by the test suite and main()
# ---------------------------------------------------------------------------


def scan_paths(paths: Iterable[Path]) -> list[Violation]:
    """Scan an iterable of file paths and return the violations found.

    The function is the testable seam — tests pass synthetic file paths in a
    tempdir; main() passes the real staged-file list from git.
    """
    violations: list[Violation] = []
    for path in paths:
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        try:
            source = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if suffix in _PY_SUFFIXES:
            violations.extend(_scan_python(path, source))
        elif suffix in _GO_SUFFIXES:
            violations.extend(_scan_go(path, source))
    return violations


def _staged_files() -> list[Path]:
    """Return staged Python and Go files via git diff."""
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
    paths: list[Path] = []
    for line in (result.stdout or "").splitlines():
        line = line.strip()
        if not line:
            continue
        suffix = Path(line).suffix.lower()
        if suffix not in (*_PY_SUFFIXES, *_GO_SUFFIXES):
            continue
        paths.append(REPO_ROOT / line)
    return paths


def _format_failure(violations: list[Violation]) -> str:
    """Build the Rule-F three-part FAIL message."""
    body = [
        "FAIL check-no-cross-language-import: staged code crosses the "
        "Python <-> Go services tier boundary directly.",
        "WHY: ADR 0006 Decision point 3 and docs/MODULAR-MONOLITH.md "
        "Services tier rule 3 state Python and Go talk only through "
        "services/<name>/api.proto or services/<name>/api.http.md. Direct "
        "ctypes / cgo / subprocess crosses the boundary and re-couples the "
        "build, which is exactly what the modular-monolith refactor is "
        "removing.",
        "UNBLOCK: Remove the direct call and route through the owning Django "
        "module's api.py over the RPC contract. For streamd specifically, "
        "use apps.realtime._streamd_client (private; do not import outside "
        "apps.realtime/). For Go services calling Python, expose the "
        "Python-owned data through that Django module's api.py and call "
        "the gRPC service instead of shelling out to python3 / manage.py.",
    ]
    text = "\n".join(body) + "\n"
    for v in violations:
        rel = v.path
        if rel.is_absolute():
            try:
                rel = rel.relative_to(REPO_ROOT)
            except ValueError:
                # Path lives outside REPO_ROOT (test fixtures); print as-is.
                pass
        text += f"  {rel}:{v.line}: [{v.rule}] {v.snippet}\n"
    text += (
        "\nIf you believe this is a false positive, file the report first "
        "with:\n  docker compose exec -T backend python manage.py "
        "report_hook_false_positive --hook check-no-cross-language-import "
        "--context \"<plain-English explanation>\"\n"
    )
    return text


def main() -> int:
    files = _staged_files()
    if not files:
        return 0
    violations = scan_paths(files)
    if not violations:
        return 0
    sys.stderr.write(_format_failure(violations))
    return 2


if __name__ == "__main__":
    sys.exit(main())
