#!/usr/bin/env python3
"""ELCV — Effective Logical Code Volume for Python source (pure standard library).

    ELCV = (LEU x SCW) + USO

  LEU  Logical Execution Units    real decision points (if / for / while / except / and|or / ternary / comprehension-if / match-case)
  USO  Unique Semantic Operations distinct units after a normalized-AST hash (duplicates collapse to one)
  SCW  Structural Complexity Weight  multiplier in [0.5, 1.0] that penalises over-complex code

Raw line counts are deliberately NOT used. Vendored / generated / test code is skipped by path
classification, never by execution. The tool is deterministic: same input -> same number.

This is the Python computor (ADR-006 / spec CORE-0001). Rust (syn) and TypeScript counters,
the Grafana dashboard, and the build-board wiring are separate follow-up slices.
"""
from __future__ import annotations

import argparse
import ast
import copy
import hashlib
import warnings
from dataclasses import dataclass, field
from pathlib import Path

# Analyzed code (not this tool) may contain unescaped regex literals; don't echo those warnings.
warnings.filterwarnings("ignore", category=SyntaxWarning)

# A "decision point" node adds one Logical Execution Unit.
DECISION_NODES = (ast.If, ast.IfExp, ast.For, ast.AsyncFor, ast.While, ast.ExceptHandler)
# A unit boundary: nested functions are counted as their own units, not the parent's.
FUNC_NODES = (ast.FunctionDef, ast.AsyncFunctionDef)
# Cyclomatic ceiling; above this SCW drops below 1.0 and the unit is flagged over_ceiling.
COMPLEXITY_CEILING = 10
# Path parts that mark vendored / generated / build / cache code -> excluded from ELCV.
SKIP_DIR_PARTS = {
    "node_modules", ".git", "target", "dist", "build", ".venv", "venv",
    "__pycache__", "migrations", "staticfiles", ".angular", "vendor",
    "vendored", "site-packages", ".mypy_cache", ".pytest_cache", ".tox",
}


@dataclass(frozen=True)
class Unit:
    """One measured unit of logic (a function/method, or a module's top level)."""

    leu: int
    cc: int
    scw: float
    uso_hash: str
    over_ceiling: bool


@dataclass
class Report:
    """Aggregated ELCV over a set of files."""

    files: int
    leu_weighted: float          # sum of (leu * scw) over every unit
    uso: int                     # count of unique normalized-AST hashes (deduplicated)
    elcv: float                  # (leu_weighted) + uso
    per_file: list = field(default_factory=list)   # [(path, file_elcv, unit_count), ...]


def _own_nodes(unit):
    """Yield AST nodes that belong to *unit*, without descending into nested functions."""
    stack = list(ast.iter_child_nodes(unit))
    while stack:
        node = stack.pop()
        yield node
        if isinstance(node, FUNC_NODES):
            continue  # nested function -> belongs to its own unit
        stack.extend(ast.iter_child_nodes(node))


def _count_leu(unit) -> int:
    """Count Logical Execution Units (decision points) owned by *unit*."""
    leu = 0
    for node in _own_nodes(unit):
        if isinstance(node, DECISION_NODES):
            leu += 1
        elif isinstance(node, ast.BoolOp):       # each extra operand is a short-circuit branch
            leu += len(node.values) - 1
        elif isinstance(node, ast.comprehension):
            leu += len(node.ifs)
        elif isinstance(node, ast.match_case):
            leu += 1
    return leu


def _local_names(unit) -> set[str]:
    """Names that are local to *unit* (its args + anything it assigns) -> safe to normalize."""
    names: set[str] = set()
    if isinstance(unit, FUNC_NODES):
        a = unit.args
        for arg in (*a.posonlyargs, *a.args, *a.kwonlyargs):
            names.add(arg.arg)
        for extra in (a.vararg, a.kwarg):
            if extra is not None:
                names.add(extra.arg)
    for node in _own_nodes(unit):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            names.add(node.id)
        elif isinstance(node, ast.arg):
            names.add(node.arg)
    return names


class _Normalizer(ast.NodeTransformer):
    """Strip local-name and literal-value noise so identical logic hashes identically.

    Kept (so genuinely different logic stays distinct): attribute/method names, free
    (non-local) names like called functions and builtins, operators, control structure.
    Normalized: the unit's own name, argument names, local variable names, literal values
    (to their type). Nested functions are replaced by a stub (they are their own units).
    """

    def __init__(self, local_names: set[str], top):
        self._locals = local_names
        self._top = top

    @staticmethod
    def _stub():
        return ast.Expr(value=ast.Constant(value="<nested-unit>"))

    def visit_FunctionDef(self, node):
        if node is not self._top:
            return self._stub()
        node.name = "_f"
        self.generic_visit(node)
        return node

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_arg(self, node):
        node.arg = "_a"
        node.annotation = None
        return node

    def visit_Name(self, node):
        if node.id in self._locals:
            node.id = "_n"
        return node

    def visit_Constant(self, node):
        node.value = type(node.value).__name__
        return node


def _uso_hash(unit) -> str:
    """A normalized-AST fingerprint of *unit* for cross-module duplicate detection."""
    clone = copy.deepcopy(unit)
    _Normalizer(_local_names(unit), clone).visit(clone)
    dump = ast.dump(clone, annotate_fields=False)
    return hashlib.sha1(dump.encode("utf-8")).hexdigest()


def _scw(cc: int) -> float:
    """Structural Complexity Weight in [0.5, 1.0]; >ceiling is discounted, never rewarded."""
    penalty = max(0, cc - COMPLEXITY_CEILING) * 0.05
    return round(max(0.5, min(1.0, 1.0 - penalty)), 4)


def _measure(node) -> Unit:
    leu = _count_leu(node)
    cc = leu + 1
    return Unit(leu=leu, cc=cc, scw=_scw(cc), uso_hash=_uso_hash(node),
                over_ceiling=cc > COMPLEXITY_CEILING)


def units_of_source(source: str) -> list[Unit]:
    """Parse Python *source* and return a Unit per function/method plus one module unit."""
    tree = ast.parse(source)
    nodes = [tree, *(n for n in ast.walk(tree) if isinstance(n, FUNC_NODES))]
    return [_measure(n) for n in nodes]


def should_skip(path: Path) -> bool:
    """True when *path* is vendored / generated / build / cache / test code (excluded)."""
    parts = {part.lower() for part in path.parts}
    if parts & SKIP_DIR_PARTS or "tests" in parts:
        return True
    name = path.name.lower()
    if name in {"conftest.py", "tests.py"}:
        return True
    return (name.startswith(("test_", "tests_"))
            or name.endswith(("_test.py", "_tests.py")))


def compute_files(paths) -> Report:
    """Compute aggregated ELCV over an iterable of Python file *paths* (global USO dedup)."""
    seen: set[str] = set()
    leu_weighted = 0.0
    files = 0
    per_file: list = []
    for path in paths:
        try:
            units = units_of_source(Path(path).read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError, ValueError):
            continue
        files += 1
        file_first = sum(u.leu * u.scw for u in units)
        leu_weighted += file_first
        fresh = sum(1 for u in units if not (u.uso_hash in seen or seen.add(u.uso_hash)))
        per_file.append((str(path), round(file_first + fresh, 2), len(units)))
    uso = len(seen)
    return Report(files=files, leu_weighted=round(leu_weighted, 2), uso=uso,
                  elcv=round(leu_weighted + uso, 2), per_file=per_file)


def compute_path(root: Path) -> Report:
    """Compute ELCV for a single .py file or a directory tree (skipping excluded paths)."""
    if root.is_file():
        return compute_files([root])
    paths = sorted(p for p in root.rglob("*.py") if not should_skip(p))
    return compute_files(paths)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Compute ELCV for Python source.")
    parser.add_argument("path", help="a .py file or a directory to scan")
    parser.add_argument("--top", type=int, default=10, help="show the top-N files by ELCV")
    args = parser.parse_args(argv)
    report = compute_path(Path(args.path))
    print(f"Files scanned : {report.files}")
    print(f"LEU x SCW     : {report.leu_weighted}")
    print(f"USO (unique)  : {report.uso}")
    print(f"ELCV          : {report.elcv}")
    if args.top and report.per_file:
        print(f"\nTop {args.top} files by ELCV:")
        for path, elcv, n in sorted(report.per_file, key=lambda row: -row[1])[: args.top]:
            print(f"  {elcv:>10}  ({n} units)  {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
