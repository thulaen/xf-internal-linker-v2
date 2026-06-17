#!/usr/bin/env python3
"""Rust + TypeScript logic counters for ELCV (heuristic, keyword-based).

The Python computor (elcv.py) is AST-accurate. Rust and TypeScript are counted here with a
lighter keyword heuristic after stripping comments and string/char/template literals: it
counts decision keywords (LEU) and function-like blocks (a rough unit/USO proxy). It does
NOT do cross-file dedup or complexity weighting — so treat these as an *estimate*. A full
AST counter (Rust `syn`, the TypeScript compiler API) is a follow-up slice.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
import logging
from pathlib import Path

_COMMENT = re.compile(r"//.*?$|/\*.*?\*/", re.S | re.M)
_STRINGS = [re.compile(r'"(?:\\.|[^"\\])*"'), re.compile(r"'(?:\\.|[^'\\])*'"),
            re.compile(r"`(?:\\.|[^`\\])*`")]

RUST_DECISIONS = [r"\bif\b", r"\bwhile\b", r"\bfor\b", r"\bloop\b", r"\bmatch\b",
                  r"=>", r"&&", r"\|\|", r"\?"]
RUST_UNITS = r"\bfn\b"
TS_DECISIONS = [r"\bif\b", r"\bfor\b", r"\bwhile\b", r"\bcase\b", r"\bcatch\b",
                r"&&", r"\|\|", r"(?<![?.])\?(?![?.:])"]   # ternary only, not ?. ?? ?:
TS_UNITS = r"\bfunction\b|=>"

_LANG = {
    ".rs": (RUST_DECISIONS, RUST_UNITS),
    ".ts": (TS_DECISIONS, TS_UNITS),
    ".tsx": (TS_DECISIONS, TS_UNITS),
}

logger = logging.getLogger(__name__)


@dataclass
class LangCount:
    language: str
    files: int
    elcv: float
    backend: str   # "tree-sitter" (true AST) or "heuristic" (keyword fallback)


def _strip(source: str) -> str:
    source = _COMMENT.sub(" ", source)
    for pattern in _STRINGS:
        source = pattern.sub('""', source)
    return source


def count_source(source: str, suffix: str) -> tuple[int, int]:
    """Return (leu, units) for one Rust/TS source string."""
    decisions, unit_pat = _LANG[suffix]
    text = _strip(source)
    leu = sum(len(re.findall(p, text)) for p in decisions)
    units = len(re.findall(unit_pat, text))
    return leu, units


def _keyword_counts(root: Path) -> dict:
    from elcv import should_skip  # reuse the same exclusion rules

    agg: dict[str, tuple] = {}
    for suffix in _LANG:
        for path in root.rglob(f"*{suffix}"):
            if should_skip(path):
                continue
            try:
                leu, units = count_source(path.read_text(encoding="utf-8"), suffix)
            except (UnicodeDecodeError, OSError):
                continue
            lang = "rust" if suffix == ".rs" else "typescript"
            files, total_leu, total_units = agg.get(lang, (0, 0, 0))
            agg[lang] = (files + 1, total_leu + leu, total_units + units)
    return {lang: LangCount(lang, files, float(leu + units), "heuristic")
            for lang, (files, leu, units) in agg.items()}


def count_paths(root: Path) -> dict:
    """Prefer the true-AST tree-sitter backend (ts_backend); fall back to the keyword heuristic."""
    try:
        import ts_backend
        if ts_backend.available():
            return {lang: LangCount(lang, r.files, r.elcv, "tree-sitter")
                    for lang, r in ts_backend.count_paths(root).items()}
    except (AttributeError, ImportError, OSError, TypeError) as exc:
        logger.debug("tree-sitter ELCV backend unavailable: %s", exc)
    return _keyword_counts(root)


if __name__ == "__main__":
    import sys

    for lang, c in count_paths(Path(sys.argv[1] if len(sys.argv) > 1 else ".")).items():
        print(f"{lang:<12} files={c.files:<6} ELCV={c.elcv:<10} backend={c.backend}")
