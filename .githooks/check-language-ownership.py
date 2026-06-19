#!/usr/bin/env python3
"""Block code written in the wrong language — hard block.

The repo is Python + Rust ONLY for the backend, plus Angular for the frontend.
Each kind of work has an owning language:

  * Rust  — production correctness and hot paths. This includes domain invariants,
            ranking validity, governance decisions, never-zero weights,
            movement budgets, score validation, search execution, reranking,
            normalization, missing-value policy, score breakdown validation,
            helper workers, optional GPU dispatch, artifact validation, and
            performance-sensitive compute.
  * Python — Django, orchestration, module APIs, models, migrations, admin/operator
             workflows, management commands, schedules, analytics ingestion,
             report generation, approved offline ML, GUI backend endpoints, and
             MCP registration.
  * TypeScript/Angular — browser UI, interaction state, visual workflows.

This gate catches the most common ownership violations as an IMPLEMENTATION.
It is deliberately conservative so it does not block legitimate orchestration code.

The helper ``scan_paths(paths)`` is exposed so tests never touch the git index.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# (Violation regex, Allowed-import regex, Error message)
_RUST_OWNED_PATTERNS = [
    (
        re.compile(r"min_?hash|simhash|lsh_bands|shingle_hash|jaccard_bands", re.I),
        re.compile(r"papertrail_dedup|import\s+\w*dedup\w*", re.I),
        "MinHash/LSH reimplementation in Python. Hot-path dedup belongs in the Rust papertrail_dedup extension",
    ),
    (
        re.compile(r"ranking_validity|score_validation|score_breakdown|normalize_score|movement_budget|never_zero_weight", re.I),
        re.compile(r"import\s+\w*(scoring|ranking_decision_engine|feedrerank)", re.I),
        "Ranking validity or scoring logic in Python. Rust owns ranking validity, never-zero weights, movement budgets, and score validation",
    ),
    (
        re.compile(r"bloom_filter|count_min_sketch|frequency_sketch", re.I),
        re.compile(r"import\s+\w*(compressed_bloom|counting_bloom|count_min_sketch)", re.I),
        "Bloom filter or sketch in Python. Probabilistic data structures belong in Rust extensions",
    ),
    (
        re.compile(r"page_?rank|hits_algorithm|graph_walk", re.I),
        re.compile(r"import\s+\w*(pagerank|advanced_graph_signals)", re.I),
        "PageRank or graph walk in Python. Graph iteration belongs in Rust extensions",
    ),
    (
        re.compile(r"ivf_index|vector_search|l2_?norm", re.I),
        re.compile(r"import\s+\w*(ivf_index|l2norm|simsearch)", re.I),
        "Vector search or math loops in Python. Vector computation belongs in Rust extensions",
    ),
]


def _is_test_or_generated(path: str) -> bool:
    return bool(
        re.search(r"(^|/)(tests?/|test_|tests_)|_test\.py$|/api/gen/|"
                  r"_pb2|/migrations/", path)
    )


def _is_python_routing_config(path: str) -> bool:
    return path.endswith("/urls.py")


def _scan_python(path: str, text: str) -> list[str]:
    out: list[str] = []
    for violation_re, import_re, message in _RUST_OWNED_PATTERNS:
        if violation_re.search(text) and not import_re.search(text):
            out.append(f"{path}: looks like {message}; call the Rust extension instead.")
    return out


def scan_paths(paths: list[str]) -> list[str]:
    violations: list[str] = []
    for path in paths:
        norm = path.replace("\\", "/")
        if _is_test_or_generated(norm):
            continue
        if _is_python_routing_config(norm):
            continue
        full = REPO_ROOT / norm
        try:
            text = full.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if norm.endswith(".py") and norm.startswith("backend/"):
            violations.extend(_scan_python(norm, text))
    return violations


def _staged_files() -> list[str]:
    try:
        out = subprocess.check_output(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
            cwd=REPO_ROOT, text=True, encoding="utf-8", errors="replace",
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []
    return [
        line.strip() for line in out.splitlines()
        if line.strip().endswith(".py")
    ]


def _fail(violations: list[str]) -> int:
    sys.stderr.write(
        "\nFAIL check-language-ownership: code is written in the wrong language.\n"
        "WHY: the backend is Python + Rust only, and Rust owns production correctness "
        "and hot paths (ranking validity, movement budgets, score validation, vector search, etc.). "
        "The flagged Python code crosses that boundary.\n"
        "UNBLOCK: move the logic into the corresponding Rust extension and call it "
        "from Python, or — if this is a false positive — file it via "
        "`manage.py report_hook_false_positive --hook check-language-ownership`.\n\n"
        + "\n".join(f"  {v}" for v in violations) + "\n"
    )
    return 1


def main() -> int:
    violations = scan_paths(_staged_files())
    if violations:
        return _fail(violations)
    return 0


if __name__ == "__main__":
    sys.exit(main())
