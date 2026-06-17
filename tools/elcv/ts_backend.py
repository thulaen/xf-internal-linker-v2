#!/usr/bin/env python3
"""True-AST Rust + TypeScript ELCV counter via tree-sitter (optional dependency).

multilang.py uses this when `tree-sitter` and the grammars are importable; otherwise it
falls back to its keyword heuristic. Same ELCV model as the Python computor:
  LEU  = decision nodes per function (not descending into nested functions)
  USO  = structural fingerprint per function, deduped (keeps method names + operators,
         drops variable names/literals — so renamed copies collapse, distinct calls don't)
  SCW  = [0.5, 1.0] complexity weight

Install (in the quality container / CI, NOT the host):  pip install -r tools/elcv/requirements.txt
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

COMPLEXITY_CEILING = 10

_RUST_DECISIONS = {"if_expression", "while_expression", "for_expression",
                   "loop_expression", "match_arm", "try_expression"}
_RUST_FUNCS = {"function_item", "closure_expression"}
_TS_DECISIONS = {"if_statement", "for_statement", "for_in_statement", "while_statement",
                 "do_statement", "switch_case", "catch_clause", "ternary_expression"}
_TS_FUNCS = {"function_declaration", "function_expression", "arrow_function",
             "method_definition", "generator_function", "generator_function_declaration"}
_NAME_NODES = {"field_identifier", "property_identifier"}
_OP_NODES = {"binary_expression", "unary_expression", "assignment_expression",
             "augmented_assignment_expression", "compound_assignment_expr"}

def _build_languages():
    from tree_sitter import Language
    import tree_sitter_rust
    import tree_sitter_typescript
    rust = Language(tree_sitter_rust.language())
    ts = Language(tree_sitter_typescript.language_typescript())
    tsx = Language(tree_sitter_typescript.language_tsx())
    return {
        ".rs": ("rust", rust, _RUST_DECISIONS, _RUST_FUNCS),
        ".ts": ("typescript", ts, _TS_DECISIONS, _TS_FUNCS),
        ".tsx": ("typescript", tsx, _TS_DECISIONS, _TS_FUNCS),
    }


@lru_cache(maxsize=1)
def _cached_languages() -> dict:
    try:
        return _build_languages()
    except (AttributeError, ImportError, TypeError):
        return {}


def available() -> bool:
    """True if tree-sitter and both grammars import and build cleanly."""
    return bool(_cached_languages())


def _parser(language):
    from tree_sitter import Parser
    try:
        return Parser(language)
    except TypeError:           # older tree-sitter API
        parser = Parser()
        parser.language = language
        return parser


def _scw(cc: int) -> float:
    penalty = max(0, cc - COMPLEXITY_CEILING) * 0.05
    return round(max(0.5, min(1.0, 1.0 - penalty)), 4)


def _analyze(unit, decisions, funcs):
    """Return (leu, scw, fingerprint) for one function node, ignoring nested functions."""
    leu = 0
    parts: list[str] = []

    def visit(node, top):
        nonlocal leu
        if not top and node.type in funcs:
            parts.append("<unit>")          # nested function: its own unit, stub here
            return
        parts.append(node.type)
        if node.type in decisions:
            leu += 1
        if node.type in _OP_NODES:
            op = node.child_by_field_name("operator")
            if op is not None:
                text = op.text.decode("utf-8", "ignore")
                parts.append(text)          # keep operators (a+b != a-b, && adds a branch)
                if text in ("&&", "||"):
                    leu += 1
        elif node.type in _NAME_NODES:
            parts.append(node.text.decode("utf-8", "ignore"))   # keep method/property names
        for child in node.named_children:
            visit(child, False)

    visit(unit, True)
    fingerprint = hashlib.sha1("".join(parts).encode("utf-8")).hexdigest()
    return leu, _scw(leu + 1), fingerprint


def _iter_funcs(node, funcs):
    if node.type in funcs:
        yield node
    for child in node.named_children:
        yield from _iter_funcs(child, funcs)


@dataclass
class LangResult:
    language: str
    files: int
    leu_weighted: float
    uso: int

    @property
    def elcv(self) -> float:
        return round(self.leu_weighted + self.uso, 2)


@dataclass
class _LanguageTotals:
    files: dict[str, int]
    leu_weighted: dict[str, float]
    seen: dict[str, set]


def count_paths(root: Path) -> dict:
    """True-AST ELCV per language under *root* (global USO dedup, skips vendored/test paths)."""
    from elcv import should_skip
    languages = _cached_languages()
    if not languages:
        return {}
    totals = _LanguageTotals(files={}, leu_weighted={}, seen={})
    for suffix, config in languages.items():
        _count_language_paths(root, suffix, config, should_skip, totals)
    return _language_results(totals)


def _count_language_paths(root: Path, suffix: str, config: tuple, should_skip, totals) -> None:
    lang, language, decisions, funcs = config
    parser = _parser(language)
    for path in root.rglob(f"*{suffix}"):
        if should_skip(path):
            continue
        try:
            tree = parser.parse(path.read_bytes())
        except OSError:
            continue
        _add_tree_counts(lang, tree, decisions, funcs, totals)


def _add_tree_counts(lang: str, tree, decisions: set, funcs: set, totals: _LanguageTotals) -> None:
    totals.files[lang] = totals.files.get(lang, 0) + 1
    bucket = totals.seen.setdefault(lang, set())
    for fn in _iter_funcs(tree.root_node, funcs):
        leu, scw, fingerprint = _analyze(fn, decisions, funcs)
        totals.leu_weighted[lang] = totals.leu_weighted.get(lang, 0.0) + leu * scw
        bucket.add(fingerprint)


def _language_results(totals: _LanguageTotals) -> dict:
    return {
        lang: LangResult(
            lang,
            totals.files[lang],
            round(totals.leu_weighted.get(lang, 0.0), 2),
            len(totals.seen[lang]),
        )
        for lang in totals.files
    }
