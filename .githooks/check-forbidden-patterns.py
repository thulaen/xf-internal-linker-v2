#!/usr/bin/env python3
"""Pre-commit linter — flag forbidden patterns from PERFORMANCE-SAFE-DEFAULTS.md.

Scans staged Python files for ten high-impact forbidden patterns:

    1. ``except Exception:`` with no ``ingest_error`` call in the same block
    2. ``while True:`` with no break/timeout in the body
    3. ``.objects.all()`` immediately followed by ``for x in``
    4. ``# TODO`` / ``# FIXME`` without an ``(RPT-NNN)`` or ``(ISS-NNN)`` reference
    5. New function over 50 lines (warn)
    6. Module with no docstring (warn)
    7. Celery task with no ``@HelperConstraint`` (warn)
    8. Function with >7 args (warn)
    9. Function with >4 nesting levels (warn)
    10. Bare ``print(...)`` in backend source outside tests/migrations/management
        (block — convert to ``logger.*`` or move to a CLI-shaped location)

Conservative — false positives are easier to silence (with a
``# noqa: forbidden-pattern <id>`` comment near the violation) than false
negatives are to recover from once a bad pattern lands. Patterns 1-4 + 10 BLOCK
the commit; 5-9 emit warnings only.

Exit codes:
    0   — staged Python files are clean (or none staged)
    1   — at least one staged file violates a blocking pattern
    2   — the linter itself failed

Usage from the pre-commit shim::

    if [ -n "$STAGED_PY" ]; then
      python "$REPO_ROOT/.githooks/check-forbidden-patterns.py" $STAGED_PY
    fi

Override per-instance with ``# noqa: forbidden-pattern`` (or with a more
specific ``# noqa: forbidden-pattern silent-except`` for one rule).
"""

from __future__ import annotations

import ast
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

# Where the linter lives (repo-relative).
HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent

# Files exempt from these checks (regex match against repo-relative path).
EXEMPT_PATHS = (
    re.compile(r"/migrations/"),
    re.compile(r"/tests?/"),
    re.compile(r"_pb2\.py$"),
    re.compile(r"/vendor/"),
    re.compile(r"\.githooks/"),
)


@dataclass
class Violation:
    path: Path
    lineno: int
    rule: str
    severity: str  # "block" | "warn"
    detail: str


def staged_python_paths(args: list[str]) -> list[Path]:
    """Return staged .py paths the hook should check."""
    if args:
        return [Path(a) for a in args if a.endswith(".py")]
    out = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    return [Path(p) for p in out if p.endswith(".py")]


# Diff-awareness: per the TECH-DEBT-MANDATE "steady cumulative pressure"
# rule, the linter should only flag NEW debt — pre-existing patterns in
# touched files are everyone-else's-session-to-fix, not THIS commit's.
# Set ``--strict`` to scan whole files instead.
_DIFF_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", re.MULTILINE)


def added_line_ranges(path: Path) -> list[tuple[int, int]] | None:
    """Return the (start_line, end_line) ranges this commit ADDS to *path*.

    Returns None if the file is brand-new (CASE: every line is "added";
    we lint the whole file). Returns [] for binary files / git failure
    (caller skips diff-awareness).
    """
    try:
        # Show the unified diff of this file in the staged set.
        result = subprocess.run(
            ["git", "diff", "--cached", "--unified=0", "--", str(path)],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError:
        return []
    diff = result.stdout
    # Brand-new files have a "new file mode" header — lint the whole file.
    if "new file mode" in diff.split("\n", 5)[0:5][0]:
        return None
    if "new file mode" in diff[:2000]:
        return None
    ranges: list[tuple[int, int]] = []
    for match in _DIFF_HUNK_RE.finditer(diff):
        start = int(match.group(1))
        count = int(match.group(2)) if match.group(2) is not None else 1
        if count == 0:
            continue
        ranges.append((start, start + count - 1))
    return ranges


def line_in_ranges(lineno: int, ranges: list[tuple[int, int]] | None) -> bool:
    """True if ``lineno`` is in one of the diff-added ranges (or full-file scan)."""
    if ranges is None:
        return True
    for start, end in ranges:
        if start <= lineno <= end:
            return True
    return False


def is_exempt(path: Path) -> bool:
    posix = str(path).replace("\\", "/")
    return any(p.search(posix) for p in EXEMPT_PATHS)


# ── Per-rule scanners ─────────────────────────────────────────────


_NOQA_LINE_RE = re.compile(r"#\s*noqa:\s*forbidden-pattern\b", re.IGNORECASE)

# Sites that already carry the standard ruff broad-except suppression
# (`# noqa: BLE001`) have been intentionally accepted by review and the
# author has decided the silent fallback is correct. Treat that as
# equivalent to the project-specific ``# noqa: forbidden-pattern silent-except``
# so the linter doesn't double-flag well-curated code.
_BLE001_NOQA_RE = re.compile(r"#\s*noqa:\s*BLE001\b", re.IGNORECASE)


def _has_noqa(source_lines: list[str], lineno: int, window: int = 1) -> bool:
    """True if any line within ``window`` of ``lineno`` carries the noqa marker."""
    lo = max(0, lineno - 1 - window)
    hi = min(len(source_lines), lineno + window)
    for line in source_lines[lo:hi]:
        if _NOQA_LINE_RE.search(line):
            return True
    return False


def _has_ble001_noqa(source_lines: list[str], lineno: int, window: int = 1) -> bool:
    """True if any line within ``window`` carries the ruff BLE001 suppression."""
    lo = max(0, lineno - 1 - window)
    hi = min(len(source_lines), lineno + window)
    for line in source_lines[lo:hi]:
        if _BLE001_NOQA_RE.search(line):
            return True
    return False


def scan_silent_except(tree: ast.Module, source_lines: list[str], path: Path) -> list[Violation]:
    """Rule 1: except Exception: block with no ingest_error call."""
    out: list[Violation] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler):
            continue
        # Match except Exception: and except (Exception, ...)
        is_broad = False
        if node.type is None:
            is_broad = True
        elif isinstance(node.type, ast.Name) and node.type.id == "Exception":
            is_broad = True
        elif isinstance(node.type, ast.Tuple):
            for elt in node.type.elts:
                if isinstance(elt, ast.Name) and elt.id == "Exception":
                    is_broad = True
                    break
        if not is_broad:
            continue
        if _has_noqa(source_lines, node.lineno, window=2):
            continue
        # The standard ruff `# noqa: BLE001` suppression at the same line
        # also counts as an intentional acceptance — see _BLE001_NOQA_RE.
        if _has_ble001_noqa(source_lines, node.lineno, window=2):
            continue
        # Check whether the body calls ingest_error / re-raises / logs.
        # ``logger.debug`` is acceptable too — it lands in container
        # logs which are searchable; "silent" means NO logging at all.
        body_src = "\n".join(
            source_lines[node.lineno - 1 : (node.end_lineno or node.lineno)]
        )
        if (
            "ingest_error" in body_src
            or "raise" in body_src
            or "logger.exception" in body_src
            or "logger.warning" in body_src
            or "logger.error" in body_src
            or "logger.info" in body_src
            or "logger.debug" in body_src
        ):
            continue
        out.append(
            Violation(
                path=path,
                lineno=node.lineno,
                rule="silent-except",
                severity="block",
                detail=(
                    "broad except with no ingest_error / logger.exception / re-raise. "
                    "Wrap with apps.audit.error_ingest.ingest_error() so the failure "
                    "is visible on /error-log."
                ),
            )
        )
    return out


def scan_unbounded_while(tree: ast.Module, source_lines: list[str], path: Path) -> list[Violation]:
    """Rule 2: while True: with no break / timeout / return in the body."""
    out: list[Violation] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.While):
            continue
        # ``while True``
        is_true = (
            (isinstance(node.test, ast.Constant) and node.test.value is True)
            or (isinstance(node.test, ast.Name) and node.test.id == "True")
        )
        if not is_true:
            continue
        if _has_noqa(source_lines, node.lineno, window=2):
            continue
        body_walk = list(ast.walk(ast.Module(body=node.body, type_ignores=[])))
        has_exit = any(
            isinstance(n, (ast.Break, ast.Return, ast.Raise)) for n in body_walk
        )
        # A timeout sleep loop usually has time.monotonic() compare in the body.
        if has_exit:
            continue
        out.append(
            Violation(
                path=path,
                lineno=node.lineno,
                rule="unbounded-loop",
                severity="block",
                detail="while True with no break / return / raise. Add a break-condition or timeout.",
            )
        )
    return out


_OBJECTS_ALL_FOR_RE = re.compile(
    r"\.objects\.all\s*\(\s*\)\s*(?:\n\s*)?(?:\.[a-z_]+\([^)]*\)\s*)*[\)\.]?\s*\n?\s*for\s+\w+\s+in",
    re.MULTILINE,
)


def scan_unbounded_iteration(source: str, source_lines: list[str], path: Path) -> list[Violation]:
    """Rule 3: ``for x in Model.objects.all():`` (potentially unbounded)."""
    out: list[Violation] = []
    for match in _OBJECTS_ALL_FOR_RE.finditer(source):
        lineno = source[: match.start()].count("\n") + 1
        if _has_noqa(source_lines, lineno, window=1):
            continue
        out.append(
            Violation(
                path=path,
                lineno=lineno,
                rule="unbounded-iter",
                severity="block",
                detail=(
                    ".objects.all() followed by `for x in` — use "
                    ".iterator(chunk_size=N) or an explicit slice to bound memory."
                ),
            )
        )
    return out


_TODO_RE = re.compile(r"#\s*(TODO|FIXME)\b(?!\((?:RPT|ISS)-\d+)", re.IGNORECASE)


def scan_unscoped_todo(source: str, source_lines: list[str], path: Path) -> list[Violation]:
    """Rule 4: ``# TODO`` / ``# FIXME`` without a ``(RPT-NNN)`` or ``(ISS-NNN)`` reference.

    Both prefixes are accepted because the project tracks two surfaces:
    Registry reports (RPT) and per-issue rows (ISS / AutoIssue). A scoped
    TODO must point at one or the other.
    """
    out: list[Violation] = []
    for match in _TODO_RE.finditer(source):
        lineno = source[: match.start()].count("\n") + 1
        if _has_noqa(source_lines, lineno, window=1):
            continue
        out.append(
            Violation(
                path=path,
                lineno=lineno,
                rule="unscoped-todo",
                severity="block",
                detail=(
                    "# TODO/FIXME without an (RPT-NNN) or (ISS-NNN) reference. "
                    "Either resolve, or tag with a tracking entry: "
                    "# TODO(RPT-042): ... or # TODO(ISS-103): ..."
                ),
            )
        )
    return out


# Rule 10 — committed `print(...)` calls in backend source. Allowed in
# tests, migrations, and management commands (which are CLI-facing). The
# rest of the backend uses `logger.*`. The check is AST-based to avoid
# false positives on docstrings / comments containing the word "print".
_PRINT_ALLOWED_PATH_RE = re.compile(
    r"/(tests?|migrations|management/commands)/", re.IGNORECASE
)
# Files named tests.py / tests_*.py / test_*.py at any depth — also exempt.
# Without this carve-out, a print() inside `apps/foo/tests.py` (legacy
# single-file layout) would block the commit even though Django treats
# the file as test-only.
_PRINT_ALLOWED_FILENAME_RE = re.compile(
    r"/(tests?\.py|tests?_[^/]+\.py|test_[^/]+\.py)$", re.IGNORECASE
)
_PRINT_ALLOWED_FILE_RE = re.compile(r"^backend/scripts/", re.IGNORECASE)


def scan_committed_prints(
    tree: ast.Module, source_lines: list[str], path: Path
) -> list[Violation]:
    """Rule 10: bare `print(...)` calls left in committed backend source.

    Skipped for tests, migrations, management/commands, and ``backend/scripts/``
    (CLI-facing files where stdout IS the output channel). Honors the
    ``# noqa: forbidden-pattern print-statement`` per-line override and a
    file-wide ``# print-allowed: <reason>`` top-of-file comment for the
    rare debug helper that genuinely belongs on stdout.
    """
    out: list[Violation] = []
    posix = str(path).replace("\\", "/")
    if not posix.startswith("backend/apps/") and not posix.startswith("backend/config/"):
        return out
    if (
        _PRINT_ALLOWED_PATH_RE.search(posix)
        or _PRINT_ALLOWED_FILENAME_RE.search(posix)
        or _PRINT_ALLOWED_FILE_RE.search(posix)
    ):
        return out
    # File-wide opt-out via top-of-file comment.
    head = "\n".join(source_lines[:5]).lower()
    if "# print-allowed:" in head:
        return out

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        is_print = (
            isinstance(func, ast.Name) and func.id == "print"
        ) or (
            isinstance(func, ast.Attribute) and func.attr == "print"
            and isinstance(func.value, ast.Name) and func.value.id == "builtins"
        )
        if not is_print:
            continue
        if _has_noqa(source_lines, node.lineno, window=1):
            continue
        out.append(
            Violation(
                path=path,
                lineno=node.lineno,
                rule="print-statement",
                severity="block",
                detail=(
                    "bare print() in backend source — convert to logger.* "
                    "(info / debug / warning / error). For genuine stdout output "
                    "(e.g. management commands) move the file under "
                    "management/commands/ or add a top-of-file "
                    "`# print-allowed: <reason>` comment."
                ),
            )
        )
    return out


def scan_missing_helper_constraint(tree: ast.Module, path: Path) -> list[Violation]:
    """Rule 7 (warn): ``@shared_task`` without an adjacent ``@HelperConstraint``.

    Phase 4.9 — every NEW Celery task should declare its resource
    constraints so the helper-PC routing engine can pick the right node.
    Warns on staged-line additions only (diff-aware mode); does not block.

    The check looks at decorator names directly. ``@shared_task(...)`` /
    ``@app.task(...)`` / ``@celery.task(...)`` all qualify. The check
    is satisfied if ANY decorator on the same function is named
    ``HelperConstraint`` (the class-style decorator from
    ``apps.core.helpers``).
    """
    out: list[Violation] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not node.decorator_list:
            continue

        is_celery_task = False
        has_helper_constraint = False
        for dec in node.decorator_list:
            name = _decorator_name(dec)
            if name in {"shared_task", "task"}:
                is_celery_task = True
            elif name == "HelperConstraint":
                has_helper_constraint = True

        if not is_celery_task or has_helper_constraint:
            continue

        out.append(
            Violation(
                path=path,
                lineno=node.lineno,
                rule="missing-helper-constraint",
                severity="warn",
                detail=(
                    f"Celery task `{node.name}` has no @HelperConstraint annotation. "
                    f"Add one from apps.core.helpers so the routing engine can pick "
                    f"main vs helper PC. Example: "
                    f"@HelperConstraint(cpu_intensive=True, gpu_required=False, "
                    f"storage_writes_to='postgres_main', ram_peak_mb=512)"
                ),
            )
        )
    return out


def _decorator_name(dec: ast.expr) -> str:
    """Return the bare name of a decorator (e.g. 'shared_task' from
    ``@shared_task(name=...)`` or ``@celery.shared_task``)."""
    if isinstance(dec, ast.Call):
        return _decorator_name(dec.func)
    if isinstance(dec, ast.Attribute):
        return dec.attr
    if isinstance(dec, ast.Name):
        return dec.id
    return ""


def scan_long_functions(
    tree: ast.Module, source_lines: list[str], path: Path, max_lines: int = 50,
) -> list[Violation]:
    """Rule 5 (warn): function over 50 lines encourages splitting.

    Honors `# noqa: forbidden-pattern` (or `# noqa: forbidden-pattern long-function`)
    on the def line — useful for pure-data spec tables that are naturally a
    single list literal.
    """
    out: list[Violation] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.end_lineno is None:
            continue
        line_count = node.end_lineno - node.lineno + 1
        if line_count <= max_lines:
            continue
        if _has_noqa(source_lines, node.lineno, window=1):
            continue
        out.append(
            Violation(
                path=path,
                lineno=node.lineno,
                rule="long-function",
                severity="warn",
                detail=(
                    f"function `{node.name}` is {line_count} lines (limit {max_lines}). "
                    f"Consider extracting helpers."
                ),
            )
        )
    return out


def scan_missing_docstring(tree: ast.Module, path: Path) -> list[Violation]:
    """Rule 6 (warn): module with no docstring."""
    if ast.get_docstring(tree):
        return []
    return [
        Violation(
            path=path,
            lineno=1,
            rule="no-docstring",
            severity="warn",
            detail="module has no docstring. Add a one-line summary at the top.",
        )
    ]


def scan_too_many_args(
    tree: ast.Module, source_lines: list[str], path: Path, max_args: int = 7,
) -> list[Violation]:
    """Rule 8 (warn): function with >7 positional + keyword-only args.

    Per ``THINK-BEFORE-YOU-CODE.md``: signatures over 7 args become
    hard to call correctly; group related args into a dataclass /
    TypedDict / kwargs dict.

    ``self`` / ``cls`` / `*args` / `**kwargs` don't count toward the
    cap (those are framework-mandated, not operator design choices).

    Honors `# noqa: forbidden-pattern` (or `# noqa: forbidden-pattern too-many-args`)
    on the def line — useful when a helper has 8+ kwargs by design and a
    dataclass would hurt more than help.
    """
    out: list[Violation] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        args = node.args
        # Count: positional + keyword-only. Exclude self/cls.
        positional = [
            a for a in args.args if a.arg not in ("self", "cls")
        ]
        kw_only = list(args.kwonlyargs)
        total = len(positional) + len(kw_only)
        if total <= max_args:
            continue
        if _has_noqa(source_lines, node.lineno, window=1):
            continue
        out.append(
            Violation(
                path=path,
                lineno=node.lineno,
                rule="too-many-args",
                severity="warn",
                detail=(
                    f"function `{node.name}` has {total} args (limit {max_args}). "
                    f"Group related args into a dataclass / TypedDict / kwargs dict."
                ),
            )
        )
    return out


def scan_deep_nesting(
    tree: ast.Module, source_lines: list[str], path: Path, max_depth: int = 4,
) -> list[Violation]:
    """Rule 9 (warn): function body with >4 levels of if/for/with/try.

    Per ``THINK-BEFORE-YOU-CODE.md``: deep nesting becomes hard to
    follow; early-return + extract helper. The depth counter only
    increments on the 4 nesting-introducing statements; expression-
    level depth (list comprehensions, ternaries) doesn't count.

    Honors `# noqa: forbidden-pattern` (or `# noqa: forbidden-pattern deep-nesting`)
    on the def line.
    """
    out: list[Violation] = []
    nesting_types = (ast.If, ast.For, ast.While, ast.With, ast.AsyncFor, ast.AsyncWith, ast.Try)

    def _max_depth(node: ast.AST, current: int = 0) -> int:
        """Recurse the AST counting nesting-introducing nodes."""
        depth = current
        for child in ast.iter_child_nodes(node):
            child_depth = current
            if isinstance(child, nesting_types):
                child_depth = current + 1
            sub = _max_depth(child, child_depth)
            if sub > depth:
                depth = sub
        return depth

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        depth = _max_depth(node)
        if depth <= max_depth:
            continue
        if _has_noqa(source_lines, node.lineno, window=1):
            continue
        out.append(
            Violation(
                path=path,
                lineno=node.lineno,
                rule="deep-nesting",
                severity="warn",
                detail=(
                    f"function `{node.name}` has {depth} nesting levels (limit {max_depth}). "
                    f"Use early-return + extract helper to flatten."
                ),
            )
        )
    return out


# ── Top-level lint loop ────────────────────────────────────────────


def lint_file(path: Path, *, strict: bool = False) -> list[Violation]:
    if is_exempt(path):
        return []
    if not path.exists():
        return []
    source = path.read_text(encoding="utf-8", errors="replace")
    source_lines = source.splitlines()
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        return [
            Violation(
                path=path,
                lineno=getattr(exc, "lineno", 1) or 1,
                rule="syntax",
                severity="block",
                detail=f"syntax error: {exc.msg}",
            )
        ]

    violations: list[Violation] = []
    violations.extend(scan_silent_except(tree, source_lines, path))
    violations.extend(scan_unbounded_while(tree, source_lines, path))
    violations.extend(scan_unbounded_iteration(source, source_lines, path))
    violations.extend(scan_unscoped_todo(source, source_lines, path))
    violations.extend(scan_long_functions(tree, source_lines, path))
    violations.extend(scan_missing_docstring(tree, path))
    violations.extend(scan_missing_helper_constraint(tree, path))
    violations.extend(scan_too_many_args(tree, source_lines, path))
    violations.extend(scan_deep_nesting(tree, source_lines, path))
    violations.extend(scan_committed_prints(tree, source_lines, path))

    # Diff-awareness: drop pre-existing violations unless --strict.
    if strict:
        return violations
    ranges = added_line_ranges(path)
    return [v for v in violations if line_in_ranges(v.lineno, ranges)]


def main(argv: list[str]) -> int:
    strict = "--strict" in argv
    args = [a for a in argv[1:] if a != "--strict"]
    paths = staged_python_paths(args)
    if not paths:
        return 0

    blocking: list[Violation] = []
    warnings: list[Violation] = []
    for path in paths:
        for v in lint_file(path, strict=strict):
            (blocking if v.severity == "block" else warnings).append(v)

    if warnings:
        print("\n[forbidden-patterns] WARNINGS (commit allowed):\n")
        for v in warnings:
            print(f"  {v.path}:{v.lineno}: [{v.rule}] {v.detail}")

    if not blocking:
        return 0

    print("\n[forbidden-patterns] BLOCKING violations:\n")
    for v in blocking:
        print(f"  {v.path}:{v.lineno}: [{v.rule}] {v.detail}")
    print(
        "\nFix each violation per PERFORMANCE-SAFE-DEFAULTS.md, OR add\n"
        "  # noqa: forbidden-pattern <rule>  # justification: ...\n"
        "near the line if the pattern is genuinely intentional.\n"
    )
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
