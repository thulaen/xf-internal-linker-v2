#!/usr/bin/env python3
"""ELCV quality gate — hard-block rules over Python source (AST + line based).

Each violation is a Finding(rule, path, line, message). `run_gate(paths)` returns all
findings; the CLI exits non-zero when any are found, so it HARD-BLOCKS commits / CI.

Scope discipline (ADR-006 + our agreement): callers pass only the files being changed,
so the gate enforces on new/changed code, not the whole legacy tree.

Inline escape (matches repo convention, never `--no-verify`): put
    # elcv: allow <RULE_ID> -- <reason>
on the offending line (or `allow all`) to suppress a specific finding with a written reason.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import elcv  # noqa: E402  (reuse the ELCV measurement helpers)

# ---- tunable thresholds -------------------------------------------------------
MAX_FUNC_LINES = 50
MAX_CYCLOMATIC = 10
MAX_COGNITIVE = 15
MAX_FILE_LINES = 1200
MAX_NESTING = 4
MAX_PARAMS = 7
MAX_BOOL_PARAMS = 3       # 3 or more boolean parameters is blocked
MAX_RETURNS = 5
MAX_LOCALS = 15
MAX_METHODS = 20
MAX_UNIT_ELCV = 40
MAX_ATTR_CHAIN = 3        # a.b.c.d (4 names / 3 dots) is the limit; deeper is blocked

NEST_NODES = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.With, ast.AsyncWith, ast.Try)
COG_NODES = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.ExceptHandler)
TERMINALS = (ast.Return, ast.Raise, ast.Break, ast.Continue)
ORM_METHODS = {"filter", "get", "all", "exclude", "count", "first", "last",
               "values", "values_list", "annotate", "aggregate", "exists"}
DUPLICATE_NAME_EXEMPTIONS = {"add_arguments"}
DANGEROUS = {"eval", "exec"}
DANGEROUS_ATTR = {("pickle", "loads"), ("pickle", "load"), ("yaml", "load"),
                  ("subprocess", "call"), ("os", "system")}
SECRET_RE = re.compile(r"(?i)(password|passwd|secret|api[_-]?key|token|access[_-]?key)\s*[:=]\s*['\"][^'\"]{6,}['\"]")
SQL_RE = re.compile(r"(?i)\.(execute|raw|executescript)\s*\(\s*(f['\"]|['\"].*%|.+\+)")
TODO_RE = re.compile(r"#.*\b(TODO|FIXME|HACK|XXX)\b")
TODO_REF_RE = re.compile(r"(paper-trail|AutoIssue)\s*#\d+")
BLANKET_RE = re.compile(r"#\s*(noqa\s*(?:$|[^:])|type:\s*ignore\s*(?:$|[^[])|pylint:\s*disable\s*=?\s*$)")
SUPPRESS_RE = re.compile(r"#\s*elcv:\s*allow\s+(\S+)\s*--\s*\S")


@dataclass(frozen=True)
class Finding:
    rule: str
    path: str
    line: int
    message: str

    @property
    def key(self) -> str:
        """A line-independent identity used for the baseline (so edits don't churn it)."""
        return _stable_key_text(f"{self.rule}|{Path(self.path).as_posix()}|{self.message}")


_COUNT_PATTERNS = (
    re.compile(r"\bfile is \d+ lines\b"),
    re.compile(r"\bis \d+ lines\b"),
    re.compile(r"\bcyclomatic complexity \d+\b"),
    re.compile(r"\bcognitive complexity \d+\b"),
    re.compile(r"\buses \d+ locals\b"),
    re.compile(r"\bhas \d+ returns\b"),
    re.compile(r"\bhas \d+ methods\b"),
    re.compile(r"\btakes \d+ parameters\b"),
)


def _stable_key_text(text: str) -> str:
    """Remove measured counts from baseline keys so legacy findings do not churn."""
    stable = text
    replacements = (
        "file is <n> lines",
        "is <n> lines",
        "cyclomatic complexity <n>",
        "cognitive complexity <n>",
        "uses <n> locals",
        "has <n> returns",
        "has <n> methods",
        "takes <n> parameters",
    )
    for pattern, replacement in zip(_COUNT_PATTERNS, replacements):
        stable = pattern.sub(replacement, stable)
    return stable


# ---- recursive structural metrics (do not descend into nested functions) ------
def _cognitive(node: ast.AST, depth: int = 0) -> int:
    score = 0
    for child in ast.iter_child_nodes(node):
        if isinstance(child, elcv.FUNC_NODES):
            continue
        nd = depth
        if isinstance(child, COG_NODES):
            score += 1 + depth
            nd = depth + 1
        elif isinstance(child, ast.BoolOp):
            score += 1
        score += _cognitive(child, nd)
    return score


def _max_nesting(node: ast.AST, depth: int = 0) -> int:
    best = depth
    for child in ast.iter_child_nodes(node):
        if isinstance(child, elcv.FUNC_NODES):
            continue
        nd = depth + 1 if isinstance(child, NEST_NODES) else depth
        best = max(best, _max_nesting(child, nd))
    return best


def _count(node: ast.AST, kind) -> int:
    return sum(1 for n in elcv._own_nodes(node) if isinstance(n, kind))


def _bool_params(func: ast.AST) -> int:
    a = func.args
    n = sum(1 for d in a.defaults if isinstance(d, ast.Constant) and isinstance(d.value, bool))
    n += sum(1 for arg in (*a.posonlyargs, *a.args, *a.kwonlyargs)
             if isinstance(arg.annotation, ast.Name) and arg.annotation.id == "bool")
    return n


def _is_stub(func: ast.AST) -> bool:
    body = [s for s in func.body if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant)
                                         and isinstance(s.value.value, str))]  # drop docstring
    if not body:
        return True
    if len(body) == 1:
        only = body[0]
        if isinstance(only, ast.Pass):
            return True
        if isinstance(only, ast.Expr) and isinstance(only.value, ast.Constant) and only.value.value is Ellipsis:
            return True
        if isinstance(only, ast.Raise) and isinstance(only.exc, (ast.Call, ast.Name)):
            name = only.exc.func.id if isinstance(only.exc, ast.Call) and isinstance(only.exc.func, ast.Name) \
                else getattr(only.exc, "id", "")
            return name == "NotImplementedError"
    return False


def _attr_chain_depth(node: ast.Attribute) -> int:
    depth = 0
    cur = node
    while isinstance(cur, ast.Attribute):
        depth += 1
        cur = cur.value
    return depth


# ---- per-construct checks -----------------------------------------------------
def _check_function(func: ast.AST, path: str):
    out = []
    name = func.name
    span = (func.end_lineno or func.lineno) - func.lineno + 1
    if span > MAX_FUNC_LINES:
        out.append(Finding("ELCV001-long-function", path, func.lineno,
                           f"function '{name}' is {span} lines (max {MAX_FUNC_LINES}); split it"))
    cyclo = elcv._count_leu(func) + 1
    if cyclo > MAX_CYCLOMATIC:
        out.append(Finding("ELCV003-high-complexity", path, func.lineno,
                           f"function '{name}' cyclomatic complexity {cyclo} (max {MAX_CYCLOMATIC})"))
    cog = _cognitive(func)
    if cog > MAX_COGNITIVE:
        out.append(Finding("ELCV004-high-cognitive", path, func.lineno,
                           f"function '{name}' cognitive complexity {cog} (max {MAX_COGNITIVE})"))
    if _max_nesting(func) > MAX_NESTING:
        out.append(Finding("ELCV005-deep-nesting", path, func.lineno,
                           f"function '{name}' nests deeper than {MAX_NESTING} levels"))
    nparams = len(func.args.posonlyargs) + len(func.args.args) + len(func.args.kwonlyargs)
    if nparams > MAX_PARAMS:
        out.append(Finding("ELCV006-too-many-params", path, func.lineno,
                           f"function '{name}' takes {nparams} parameters (max {MAX_PARAMS}); use an object"))
    if _bool_params(func) >= MAX_BOOL_PARAMS:
        out.append(Finding("ELCV007-boolean-trap", path, func.lineno,
                           f"function '{name}' has {MAX_BOOL_PARAMS}+ boolean parameters; split it"))
    nret = _count(func, ast.Return)
    if nret > MAX_RETURNS:
        out.append(Finding("ELCV008-too-many-returns", path, func.lineno,
                           f"function '{name}' has {nret} returns (max {MAX_RETURNS})"))
    nlocals = len(elcv._local_names(func))
    if nlocals > MAX_LOCALS:
        out.append(Finding("ELCV009-too-many-locals", path, func.lineno,
                           f"function '{name}' uses {nlocals} locals (max {MAX_LOCALS}); doing too much"))
    if _is_stub(func):
        out.append(Finding("ELCV018-placeholder-stub", path, func.lineno,
                           f"function '{name}' is an empty/placeholder stub shipped to production"))
    for d in func.args.defaults + func.args.kw_defaults:
        if isinstance(d, (ast.List, ast.Dict, ast.Set)):
            out.append(Finding("ELCV013-mutable-default", path, func.lineno,
                               f"function '{name}' has a mutable default argument"))
            break
    return out


def _check_class(cls: ast.ClassDef, path: str):
    methods = [n for n in cls.body if isinstance(n, elcv.FUNC_NODES)]
    if len(methods) > MAX_METHODS:
        return [Finding("ELCV011-god-class", path, cls.lineno,
                        f"class '{cls.name}' has {len(methods)} methods (max {MAX_METHODS}); split by responsibility")]
    return []


def _check_import(node: ast.ImportFrom, path: str):
    out = []
    if any(a.name == "*" for a in node.names):
        out.append(Finding("ELCV012-wildcard-import", path, node.lineno,
                           f"wildcard import from '{node.module}'; import names explicitly"))
    mod = node.module or ""
    if _is_cross_module_private_import(path, mod):
        out.append(Finding("ELCV029-cross-module-private-import", path, node.lineno,
                           f"importing module internals '{mod}' instead of its public api"))
    return out


def _is_cross_module_private_import(path: str, module: str) -> bool:
    if not module.startswith("apps.") or ".api" in module or module.count(".") < 2:
        return False
    parts = module.split(".")
    imported_app = parts[1] if len(parts) > 1 else ""
    source_parts = Path(path).as_posix().split("/")
    if len(source_parts) >= 3 and source_parts[:2] == ["backend", "apps"]:
        return source_parts[2] != imported_app
    return True


def _check_call(node: ast.Call, path: str):
    f = node.func
    if isinstance(f, ast.Name) and f.id in DANGEROUS:
        return [Finding("ELCV017-dangerous-exec", path, node.lineno, f"dangerous dynamic call '{f.id}(...)'")]
    if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name):
        if (f.value.id, f.attr) in DANGEROUS_ATTR:
            return [Finding("ELCV017-dangerous-exec", path, node.lineno,
                            f"dangerous call '{f.value.id}.{f.attr}(...)'")]
    return []


def _dead_code(tree: ast.AST, path: str):
    out = []
    for node in ast.walk(tree):
        for field in ("body", "orelse", "finalbody"):
            stmts = getattr(node, field, None)
            if not isinstance(stmts, list):
                continue
            for i, stmt in enumerate(stmts[:-1]):
                if isinstance(stmt, TERMINALS):
                    nxt = stmts[i + 1]
                    out.append(Finding("ELCV015-dead-code", path, nxt.lineno,
                                       "unreachable code after return/raise/break/continue"))
                    break
    return out


def _structural(tree: ast.AST, path: str):
    out = []
    for node in ast.walk(tree):
        if isinstance(node, elcv.FUNC_NODES):
            out += _check_function(node, path)
        elif isinstance(node, ast.ClassDef):
            out += _check_class(node, path)
        elif isinstance(node, ast.ImportFrom):
            out += _check_import(node, path)
        elif isinstance(node, ast.Call):
            out += _check_call(node, path)
        elif isinstance(node, ast.Global):
            out.append(Finding("ELCV021-mutable-global", path, node.lineno,
                               f"mutable global state via 'global {', '.join(node.names)}'"))
        elif isinstance(node, ast.IfExp) and _has_nested_ifexp(node):
            out.append(Finding("ELCV019-nested-ternary", path, node.lineno,
                               "nested ternary; use plain if/else"))
        elif isinstance(node, ast.Attribute) and _attr_chain_depth(node) > MAX_ATTR_CHAIN:
            out.append(Finding("ELCV020-train-wreck", path, node.lineno,
                               f"attribute chain deeper than {MAX_ATTR_CHAIN} (Law of Demeter)"))
        elif isinstance(node, ast.While) and _is_true(node.test) and not _has_break(node):
            out.append(Finding("ELCV016-unbounded-loop", path, node.lineno,
                               "`while True` with no break/return; bound the loop"))
        elif isinstance(node, ast.ExceptHandler) and _is_silent(node):
            out.append(Finding("ELCV014-silent-except", path, node.lineno,
                               "bare/broad except that swallows errors silently"))
        elif isinstance(node, ast.Assert):
            out.append(Finding("ELCV025-assert-in-prod", path, node.lineno,
                               "assert used in production code (stripped under -O); raise explicitly"))
    out += _dead_code(tree, path)
    out += _n_plus_one(tree, path)
    return out


def _has_nested_ifexp(node: ast.IfExp) -> bool:
    return any(isinstance(c, ast.IfExp) for c in (node.body, node.orelse))


def _is_true(test) -> bool:
    return isinstance(test, ast.Constant) and test.value is True


def _has_break(loop) -> bool:
    for n in ast.walk(loop):
        if isinstance(n, ast.Break):
            return True
        if isinstance(n, (ast.Return,)):
            return True
    return False


def _is_silent(handler: ast.ExceptHandler) -> bool:
    broad = handler.type is None or (isinstance(handler.type, ast.Name)
                                     and handler.type.id in {"Exception", "BaseException"})
    body = handler.body
    only_pass = len(body) == 1 and isinstance(body[0], ast.Pass)
    return broad and only_pass


def _n_plus_one(tree: ast.AST, path: str):
    out = []
    for loop in ast.walk(tree):
        if not isinstance(loop, (ast.For, ast.AsyncFor, ast.While)):
            continue
        for n in ast.walk(loop):
            if _looks_like_orm_loop_query(n):
                out.append(Finding("ELCV026-n-plus-one", path, n.lineno,
                                   f"query '.{n.func.attr}(...)' inside a loop (N+1); batch it"))
                break
    return out


def _looks_like_orm_loop_query(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
        return False
    if node.func.attr not in ORM_METHODS:
        return False
    names = _attribute_names(node.func.value)
    if "objects" in names:
        return True
    if names:
        root = names[0].lower()
        return root.endswith(("queryset", "_queryset", "qs", "_qs"))
    return False


def _attribute_names(node: ast.AST) -> list[str]:
    names: list[str] = []
    current = node
    while isinstance(current, ast.Attribute):
        names.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        names.append(current.id)
    names.reverse()
    return names


# ---- line-based checks --------------------------------------------------------
def _line_checks(lines, path: str):
    out = []
    if len(lines) > MAX_FILE_LINES:
        out.append(Finding("ELCV002-oversized-file", path, len(lines),
                           f"file is {len(lines)} lines (max {MAX_FILE_LINES}); refactor/split"))
    for i, text in enumerate(lines, start=1):
        if TODO_RE.search(text) and not TODO_REF_RE.search(text):
            out.append(Finding("ELCV023-orphan-todo", path, i,
                               "TODO/FIXME/HACK without a (paper-trail #N) or (AutoIssue #N) reference"))
        if BLANKET_RE.search(text):
            out.append(Finding("ELCV024-blanket-suppression", path, i,
                               "blanket noqa/type-ignore/pylint-disable without a specific code"))
        if SECRET_RE.search(text):
            out.append(Finding("ELCV027-hardcoded-secret", path, i, "possible hardcoded secret/credential"))
        if SQL_RE.search(text):
            out.append(Finding("ELCV028-sql-injection", path, i,
                               "SQL built by string concatenation/f-string; use parameters"))
    return out


def _apply_suppression(findings, lines):
    kept = []
    for f in findings:
        line = lines[f.line - 1] if 0 < f.line <= len(lines) else ""
        m = SUPPRESS_RE.search(line)
        if m and (m.group(1) == "all" or f.rule.startswith(m.group(1))):
            continue
        kept.append(f)
    return kept


def _function_units(tree: ast.AST):
    """Yield (uso_hash, lineno, name) for every function/method in *tree*."""
    for node in ast.walk(tree):
        if isinstance(node, elcv.FUNC_NODES):
            yield elcv._uso_hash(node), node.lineno, node.name


def gate_source(source: str, path: str, uso_index=None):
    lines = source.splitlines()
    findings = _line_checks(lines, path)
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        findings.append(Finding("ELCV000-syntax-error", path, exc.lineno or 0, f"syntax error: {exc.msg}"))
        return _apply_suppression(findings, lines)
    findings += _structural(tree, path)
    if uso_index:
        here = Path(path).as_posix()
        for h, lineno, name in _function_units(tree):
            loc = uso_index.get(h)
            if loc and loc.split("::", 1)[0] != here and name not in DUPLICATE_NAME_EXEMPTIONS:
                findings.append(Finding("ELCV031-cross-file-duplicate", path, lineno,
                                        f"function '{name}' duplicates existing logic at {loc}; reuse it"))
    return _apply_suppression(findings, lines)


def build_uso_index(paths) -> dict:
    """Map each function's normalized hash -> 'relpath::name::line' (first occurrence wins)."""
    index: dict = {}
    for p in paths:
        path = Path(p)
        if elcv.should_skip(path) or path.suffix != ".py":
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError, OSError):
            continue
        for h, lineno, name in _function_units(tree):
            index.setdefault(h, f"{path.as_posix()}::{name}::{lineno}")
    return index


def run_gate(paths, uso_index=None):
    findings = []
    for p in paths:
        path = Path(p)
        if elcv.should_skip(path) or path.suffix != ".py":
            continue
        try:
            findings += gate_source(path.read_text(encoding="utf-8"), str(path), uso_index)
        except (UnicodeDecodeError, OSError):
            continue
    return findings


def filter_baseline(findings, baseline):
    """Drop findings whose key is grandfathered in *baseline* (a set of keys)."""
    stable_baseline = {_stable_key_text(item) for item in baseline}
    return [f for f in findings if f.key not in stable_baseline]


def _expand(paths):
    targets = []
    for raw in paths:
        root = Path(raw)
        targets += [root] if root.is_file() else sorted(root.rglob("*.py"))
    return targets


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="ELCV hard-block quality gate.")
    parser.add_argument("paths", nargs="+", help="files or directories to gate")
    parser.add_argument("--baseline", help="JSON of grandfathered finding keys; only NEW findings block")
    parser.add_argument("--write-baseline", help="write current findings as a baseline here, then exit 0")
    parser.add_argument("--uso-index", help="JSON USO index for cross-file duplicate detection")
    parser.add_argument("--write-uso-index", help="build a USO index from the paths, write here, exit 0")
    args = parser.parse_args(argv)
    targets = _expand(args.paths)

    if args.write_uso_index:
        index = build_uso_index(targets)
        Path(args.write_uso_index).write_text(json.dumps(index), encoding="utf-8")
        print(f"wrote USO index ({len(index)} functions) -> {args.write_uso_index}")
        return 0

    uso_index = json.loads(Path(args.uso_index).read_text(encoding="utf-8")) if args.uso_index else None
    findings = run_gate(targets, uso_index)

    if args.write_baseline:
        Path(args.write_baseline).write_text(json.dumps([f.key for f in findings]), encoding="utf-8")
        print(f"wrote baseline ({len(findings)} grandfathered) -> {args.write_baseline}")
        return 0

    if args.baseline:
        findings = filter_baseline(findings, set(json.loads(Path(args.baseline).read_text(encoding="utf-8"))))

    for f in sorted(findings, key=lambda x: (x.path, x.line)):
        print(f"BLOCK {f.rule}  {f.path}:{f.line}  {f.message}")
    if findings:
        print(f"\nELCV gate: {len(findings)} violation(s); commit BLOCKED. "
              f"Fix them, or add `# elcv: allow <RULE> -- <reason>` on the line.")
        return 1
    print("ELCV gate: clean.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
