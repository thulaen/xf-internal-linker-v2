#!/usr/bin/env python3
"""Build, dedupe, verify, and prune Docker-managed compiled artifacts."""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import fcntl
except ImportError:  # pragma: no cover - this script is required in Linux containers.
    fcntl = None


ARTIFACT_ROOT = Path(os.environ.get("XF_COMPILED_ARTIFACT_ROOT", "/opt/xf/compiled"))
BUILD_ROOT = Path(os.environ.get("XF_COMPILED_BUILD_ROOT", "/tmp/xf-build"))
BACKEND_ROOT = Path(os.environ.get("XF_BACKEND_ROOT", "/app"))
REPO_ROOT = Path(os.environ.get("REPO_ROOT", "/repo"))
MANIFEST_PATH = ARTIFACT_ROOT / "manifest.json"
STORE_ROOT = ARTIFACT_ROOT / "store"
ACTIVE_ROOT = ARTIFACT_ROOT / "active"
ACTIVE_EXTENSIONS_ROOT = ACTIVE_ROOT / "extensions"
ACTIVE_GO_ROOT = ACTIVE_ROOT / "go"
ACTIVE_SPECCHECK_PATH = ACTIVE_ROOT / "speccheck"
ROLLBACK_ROOT = ARTIFACT_ROOT / "rollback"
# Rust hot-path kernels (PyO3 + maturin) ship one cdylib per kernel under
# `rust/extensions/<name>` and stage into the SAME `active/extensions/`
# directory as the C++ `.so` files, so `from extensions import <name>`
# resolves to the Rust build. The Rust `.so` is staged AFTER the C++ build so
# a ported kernel (e.g. `l2norm`) overwrites the C++ `.so` of the same name.
RUST_EXTENSIONS_DIRNAME = "extensions"
RUST_EXTENSION_NAMES = {
    # ranking_decision_engine: Rust authority crate for bounded ranking decisions
    # (ranking governance/scoring; §G). Crate at rust/extensions/ranking_decision_engine,
    # exports rank_candidates / validate_profile / explain. There is NO C++ source — it is a
    # Rust-only kernel; registered here so the Rule J three-way lifecycle guard stays consistent.
    "ranking_decision_engine",
    "l2norm",
    "count_min_sketch",
    "counting_bloom",
    "compressed_bloom",
    # NOTE: `passagesim` was ported from C++ to Rust (crate at
    # rust/extensions/passagesim — FR-053 passage-level MaxSim kernel behind the
    # passage_relevance ranking signal; exports maxsim). It is built by the Rust
    # path, not the C++ build, so it lives here and was removed from the C++
    # EXTENSION_NAMES set below. The C++ source, header, fuzz harness,
    # GoogleTest unit test, and dedicated benchmark were deleted in the same
    # slice per RUST-FIRST.md dead-code-on-replace; the runtime imports the Rust
    # `.so` of the same name.
    "passagesim",
    # NOTE: `quantemb` was ported from C++ to Rust (crate at
    # rust/extensions/quantemb — OPQ encoder + trainer; exports opq_encode /
    # opq_train). It is built by the Rust path, not the C++ build, so it lives
    # here and was removed from the C++ EXTENSION_NAMES set below. The C++
    # source, header, fuzz harness, GoogleTest unit test, and dedicated
    # benchmark were deleted in the same slice per RUST-FIRST.md
    # dead-code-on-replace; the runtime imports the Rust `.so` of the same name.
    "quantemb",
    # NOTE: `simsearch` was ported from C++ to Rust (crate at
    # rust/extensions/simsearch — bounded top-k dot-product sentence-search
    # kernel behind the semantic_similarity ranking signal / META-07). It is
    # built by the Rust path, not the C++ build, so it lives here and was
    # removed from the C++ EXTENSION_NAMES set below and the legacy bare-import
    # smoke list. The C++ source, header, fuzz harness, GoogleTest unit test,
    # dedicated benchmark, and edge-test were deleted in the same slice per
    # RUST-FIRST.md dead-code-on-replace; the runtime imports the Rust `.so` of
    # the same name.
    "simsearch",
    # NOTE: `ivf_index` was ported from C++ to Rust (crate at
    # rust/extensions/ivf_index — Inverted File + OPQ asymmetric-distance vector
    # search; exports ivf_search and adc_score_destination). It is built by the
    # Rust path, not the C++ build, so it lives here and was removed from the
    # C++ EXTENSION_NAMES set below. The C++ source, header, fuzz harness,
    # GoogleTest unit test, and dedicated benchmark were deleted in the same
    # slice per RUST-FIRST.md dead-code-on-replace; the runtime imports the Rust
    # `.so` of the same name.
    "ivf_index",
    # NOTE: `anchor_self_information` was ported from C++ to Rust (crate at
    # rust/extensions/anchor_self_information). It is built by the Rust path,
    # not the C++ build, so it lives here and was removed from the C++
    # EXTENSION_NAMES set below, following the count_min_sketch/counting_bloom
    # precedent. The C++ source, fuzz harness, and stale shared benchmark were
    # deleted in the same slice per RUST-FIRST.md dead-code-on-replace; the
    # runtime imports the Rust `.so` of the same name.
    "anchor_self_information",
    # NOTE: `generic_anchor_matcher` was ported from C++ to Rust (crate at
    # rust/extensions/generic_anchor_matcher — Aho-Corasick multi-pattern
    # matcher). It is built by the Rust path, not the C++ build, so it lives
    # here and was removed from the C++ EXTENSION_NAMES set below. The C++
    # source and fuzz harness were deleted in the same slice per RUST-FIRST.md
    # dead-code-on-replace; the runtime imports the Rust `.so` of the same name.
    "generic_anchor_matcher",
    # NOTE: `texttok` was ported from C++ to Rust (crate at
    # rust/extensions/texttok — deterministic ASCII word tokenizer feeding the
    # keyword_jaccard ranking signal). It is built by the Rust path, not the C++
    # build, so it lives here and was removed from the C++ EXTENSION_NAMES set
    # below. The C++ source, header, fuzz harness, and shared benchmark
    # translation unit were deleted in the same slice per RUST-FIRST.md
    # dead-code-on-replace; the runtime imports the Rust `.so` of the same name.
    "texttok",
    # NOTE: `phrasematch` was ported from C++ to Rust (crate at
    # rust/extensions/phrasematch — longest-contiguous-overlap phrase matcher
    # for FR-008). It is built by the Rust path, not the C++ build, so it lives
    # here and was removed from the C++ EXTENSION_NAMES set below. The C++
    # source, header, and fuzz harness were deleted in the same slice per
    # RUST-FIRST.md dead-code-on-replace; the runtime imports the Rust `.so` of
    # the same name.
    "phrasematch",
    # NOTE: `rareterm` was ported from C++ to Rust (crate at
    # rust/extensions/rareterm — FR-010 rare-term-propagation scorer). It is
    # built by the Rust path, not the C++ build, so it lives here and was
    # removed from the C++ EXTENSION_NAMES set below. The C++ source, header,
    # fuzz harness, and dedicated benchmark were deleted in the same slice per
    # RUST-FIRST.md dead-code-on-replace; the runtime imports the Rust `.so` of
    # the same name.
    "rareterm",
    # NOTE: `linkparse` was ported from C++ to Rust (crate at
    # rust/extensions/linkparse — deterministic BBCode/HTML/bare-URL link
    # parser feeding the link-graph edge extractor). It is built by the Rust
    # path, not the C++ build, so it lives here and was removed from the C++
    # EXTENSION_NAMES set below. The C++ source, header, fuzz harness, and
    # orphan benchmark were deleted in the same slice per RUST-FIRST.md
    # dead-code-on-replace; the runtime imports the Rust `.so` of the same name.
    "linkparse",
    # NOTE: `anchor_descriptiveness` was ported from C++ to Rust (crate at
    # rust/extensions/anchor_descriptiveness — Damerau-Levenshtein edit distance
    # + char-trigram Jaccard feeding the anchor-genericness ranking signal). It
    # is built by the Rust path, not the C++ build, so it lives here and was
    # removed from the C++ EXTENSION_NAMES set below. The C++ source and fuzz
    # harness were deleted, and the shared bench_anchor_garbage.cpp had its
    # anchor_descriptiveness pieces removed, in the same slice per RUST-FIRST.md
    # dead-code-on-replace; the runtime imports the Rust `.so` of the same name.
    "anchor_descriptiveness",
    # NOTE: `anchor_diversity` was ported from C++ to Rust (crate at
    # rust/extensions/anchor_diversity — FR-045 exact-match reuse guard, the
    # batched arithmetic inner loop feeding the score_anchor_diversity ranking
    # signal). It is built by the Rust path, not the C++ build, so it lives here
    # and was removed from the C++ EXTENSION_NAMES set below. The C++ source,
    # header, fuzz harness, and dedicated benchmark were deleted in the same
    # slice per RUST-FIRST.md dead-code-on-replace; the runtime imports the Rust
    # `.so` of the same name.
    "anchor_diversity",
    # NOTE: `api_rate_limiter` was ported from C++ to Rust (crate at
    # rust/extensions/api_rate_limiter — FR-250 token-bucket rate limiter for
    # GSC/GA4/Matomo/XF/WP). It is built by the Rust path, not the C++ build, so
    # it lives here and was removed from the C++ EXTENSION_NAMES set below. The
    # C++ source, single-file fuzz harness, and single-file benchmark were
    # deleted in the same slice per RUST-FIRST.md dead-code-on-replace; the
    # runtime imports the Rust `.so` of the same name.
    "api_rate_limiter",
    # NOTE: `fieldrel` was ported from C++ to Rust (crate at
    # rust/extensions/fieldrel — FR-011 BM25F field-aware relevance scorer). It
    # is built by the Rust path, not the C++ build, so it lives here and was
    # removed from the C++ EXTENSION_NAMES set below. The C++ source, dedicated
    # header, fuzz harness, and dedicated benchmark were deleted in the same
    # slice per RUST-FIRST.md dead-code-on-replace; the runtime imports the Rust
    # `.so` of the same name.
    "fieldrel",
    # NOTE: `feedrerank` was ported from C++ to Rust (crate at
    # rust/extensions/feedrerank — FR-013 explore/exploit rerank + FR-015 MMR
    # diversity). It is built by the Rust path, not the C++ build, so it lives
    # here and was removed from the C++ EXTENSION_NAMES set below. The C++
    # source, dedicated header, fuzz harness, and orphan benchmark were deleted
    # in the same slice per RUST-FIRST.md dead-code-on-replace; the runtime
    # imports the Rust `.so` of the same name.
    "feedrerank",
    # NOTE: `pagerank` was ported from C++ to Rust (crate at
    # rust/extensions/pagerank — weighted PageRank / personalized PageRank /
    # HITS power-iteration steps). It is built by the Rust path, not the C++
    # build, so it lives here and was removed from the C++ EXTENSION_NAMES set
    # below. The C++ source, dedicated header, and fuzz harness were deleted in
    # the same slice per RUST-FIRST.md dead-code-on-replace; the runtime imports
    # the Rust `.so` of the same name.
    "pagerank",
    # NOTE: `lesson_index` was ported from C++ to Rust (crate at
    # rust/extensions/lesson_index — three-sub-index in-process cache:
    # ScopedLessonIndex, PerfBaselineCache, CitationCache). It is built by the
    # Rust path, not the C++ build, so it lives here and was removed from the C++
    # EXTENSION_NAMES set below. The C++ source, header, fuzz harness, benchmark,
    # and unit-test translation unit were deleted in the same slice per
    # RUST-FIRST.md dead-code-on-replace; the runtime imports the Rust `.so` of
    # the same name.
    "lesson_index",
    # NOTE: `papertrail_dedup` was ported from C++ to Rust (crate at
    # rust/extensions/papertrail_dedup — MinHash + LSH near-duplicate index for
    # the paper-trail dedup gate and the rust_defect AutoIssue importer). It is
    # built by the Rust path, not the C++ build, so it lives here and was removed
    # from the C++ EXTENSION_NAMES set below. The C++ source, header, fuzz
    # harness, dedicated benchmark, and unit-test translation unit were deleted in
    # the same slice per RUST-FIRST.md dead-code-on-replace; the runtime imports
    # the Rust `.so` of the same name. The Rust port reproduces the C++ hash math
    # and binary snapshot layout exactly so an existing /app/data/papertrail.idx
    # reloads transparently.
    "papertrail_dedup",
    # NOTE: `scoring` was ported from C++ to Rust (crate at
    # rust/extensions/scoring — the ranker's final composite-score hot path
    # `out[i] = silo[i] + dot(component_scores[i], weights)`). It is built by the
    # Rust path, not the C++ build, so it lives here and was removed from the C++
    # EXTENSION_NAMES set below. The C++ source, dedicated header, fuzz harness,
    # dedicated benchmark, edge-test translation unit, and GoogleTest
    # registration were deleted in the same slice per RUST-FIRST.md
    # dead-code-on-replace; the runtime imports the Rust `.so` of the same name.
    "scoring",
    "advanced_graph_signals",
}
RUST_EXTENSION_EXPECTED_ATTRS = {
    "ranking_decision_engine": "rank_candidates",
    "anchor_descriptiveness": "damerau_levenshtein",
    "anchor_diversity": "evaluate_batch",
    "anchor_self_information": "bigram_entropy",
    "api_rate_limiter": "RateLimiterRegistry",
    "feedrerank": "calculate_mmr_scores_batch",
    "fieldrel": "score_field_tokens",
    "lesson_index": "memory_cap_bytes",
    "papertrail_dedup": "DedupIndex",
    "pagerank": "pagerank_step",
    "compressed_bloom": "CompressedBloomFilter",
    "count_min_sketch": "CountMinSketch",
    "counting_bloom": "CountingBloomFilter",
    "generic_anchor_matcher": "build_automaton",
    "ivf_index": "ivf_search",
    "l2norm": "normalize_l2_batch",
    "linkparse": "find_urls",
    "passagesim": "maxsim",
    "quantemb": "opq_encode",
    "phrasematch": "longest_contiguous_overlap",
    "rareterm": "evaluate_rare_terms",
    "scoring": "calculate_composite_scores_full_batch",
    "simsearch": "score_and_topk",
    "texttok": "tokenize_text_batch",
    "advanced_graph_signals": "evaluate_batch",
}
MANIFEST_SCHEMA_VERSION = 2
STORE_RETENTION_DAYS = 7
COMPILED_BUILD_TIMEOUT_SECONDS = int(
    os.environ.get("XF_COMPILED_BUILD_TIMEOUT_SECONDS", "1800")
)
COMPILED_IMPORT_TIMEOUT_SECONDS = int(
    os.environ.get("XF_COMPILED_IMPORT_TIMEOUT_SECONDS", "60")
)
# EXTENSION_NAMES is the C++ pybind11 build set. ALL C++ kernels were migrated to Rust
# (see RUST_EXTENSION_NAMES above), so it is now empty — and it MUST be an explicit
# `set()`: an empty `{}` literal is a DICT, which broke the boot-time `EXTENSION_NAMES -
# found` set difference (TypeError: dict - set). Historical per-kernel notes follow.
EXTENSION_NAMES: set[str] = set()
# NOTE: `anchor_descriptiveness` was ported from C++ to Rust (see
    # RUST_EXTENSION_NAMES above). It is built by the Rust path, not the C++
    # build, so it is no longer in this C++ EXTENSION_NAMES set. The C++ source
    # and fuzz harness were deleted and the shared bench_anchor_garbage.cpp had
    # its pieces removed in the same slice per RUST-FIRST.md dead-code-on-replace.
    # NOTE: `anchor_diversity` was ported from C++ to Rust (see
    # RUST_EXTENSION_NAMES above). It is built by the Rust path, not the C++
    # build, so it is no longer in this C++ EXTENSION_NAMES set. The C++ source,
    # header, fuzz harness, and dedicated benchmark were deleted in the same
    # slice per RUST-FIRST.md dead-code-on-replace.
    # NOTE: `anchor_self_information` was ported from C++ to Rust (see
    # RUST_EXTENSION_NAMES above). It is built by the Rust path, not the C++
    # build, so it is no longer in this C++ EXTENSION_NAMES set. The C++
    # source, fuzz harness, and stale shared benchmark were deleted in the same
    # slice per RUST-FIRST.md dead-code-on-replace.
    # NOTE: `api_rate_limiter` was ported from C++ to Rust (see
    # RUST_EXTENSION_NAMES above). It is built by the Rust path, not the C++
    # build, so it is no longer in this C++ EXTENSION_NAMES set. The C++ source,
    # single-file fuzz harness, and single-file benchmark were deleted in the
    # same slice per RUST-FIRST.md dead-code-on-replace.
    # NOTE: `compressed_bloom` was ported from C++ to Rust (see
    # RUST_EXTENSION_NAMES above). It is built by the Rust path, not the C++
    # build, so it is no longer in this C++ EXTENSION_NAMES set. The C++ source
    # was deleted in the same change per RUST-FIRST.md dead-code-on-replace.
    # NOTE: `count_min_sketch` was ported from C++ to Rust (see
    # RUST_EXTENSION_NAMES above). It is built by the Rust path, not the C++
    # build, so it is no longer in this C++ EXTENSION_NAMES set. The C++
    # source was deleted in the same change per RUST-FIRST.md
    # dead-code-on-replace.
    # NOTE: `counting_bloom` was likewise ported from C++ to Rust (see
    # RUST_EXTENSION_NAMES above). It is built by the Rust path, not the C++
    # build, so it is no longer in this C++ EXTENSION_NAMES set.
    # NOTE: `feedrerank` was ported from C++ to Rust (see RUST_EXTENSION_NAMES
    # above). It is built by the Rust path, not the C++ build, so it is no
    # longer in this C++ EXTENSION_NAMES set. The C++ source, dedicated header,
    # fuzz harness, and orphan benchmark were deleted in the same slice per
    # RUST-FIRST.md dead-code-on-replace.
    # NOTE: `fieldrel` was ported from C++ to Rust (see RUST_EXTENSION_NAMES
    # above). It is built by the Rust path, not the C++ build, so it is no
    # longer in this C++ EXTENSION_NAMES set. The C++ source, dedicated header,
    # fuzz harness, and dedicated benchmark were deleted in the same slice per
    # RUST-FIRST.md dead-code-on-replace.
    # NOTE: `generic_anchor_matcher` was ported from C++ to Rust (see
    # RUST_EXTENSION_NAMES above). It is built by the Rust path, not the C++
    # build, so it is no longer in this C++ EXTENSION_NAMES set. The C++ source
    # and fuzz harness were deleted in the same change per RUST-FIRST.md
    # dead-code-on-replace.
    # NOTE: `ivf_index` was ported from C++ to Rust (see RUST_EXTENSION_NAMES
    # above). It is built by the Rust path, not the C++ build, so it is no
    # longer in this C++ EXTENSION_NAMES set. The C++ source, header, fuzz
    # harness, GoogleTest unit test, and dedicated benchmark were deleted in the
    # same slice per RUST-FIRST.md dead-code-on-replace.
    # NOTE: `l2norm` was ported from C++ to Rust (see RUST_EXTENSION_NAMES
    # below). It is built by the Rust path, not the C++ build, so it is no
    # longer in this C++ EXTENSION_NAMES set. The C++ source/header were
    # deleted in the same change per RUST-FIRST.md dead-code-on-replace.
    # NOTE: `lesson_index` was ported from C++ to Rust (see RUST_EXTENSION_NAMES
    # above). It is built by the Rust path, not the C++ build, so it is no longer
    # in this C++ EXTENSION_NAMES set. The C++ source, header, fuzz harness,
    # benchmark, and unit-test translation unit were deleted in the same slice
    # per RUST-FIRST.md dead-code-on-replace.
    # NOTE: `linkparse` was ported from C++ to Rust (see RUST_EXTENSION_NAMES
    # above). It is built by the Rust path, not the C++ build, so it is no
    # longer in this C++ EXTENSION_NAMES set. The C++ source, header, fuzz
    # harness, and orphan benchmark were deleted in the same slice per
    # RUST-FIRST.md dead-code-on-replace.
    # NOTE: `pagerank` was ported from C++ to Rust (see RUST_EXTENSION_NAMES
    # above). It is built by the Rust path, not the C++ build, so it is no
    # longer in this C++ EXTENSION_NAMES set. The C++ source, dedicated header,
    # and fuzz harness were deleted in the same slice per RUST-FIRST.md
    # dead-code-on-replace.
    # NOTE: `papertrail_dedup` was ported from C++ to Rust (see
    # RUST_EXTENSION_NAMES above). It is built by the Rust path, not the C++
    # build, so it is no longer in this C++ EXTENSION_NAMES set. The C++ source,
    # header, fuzz harness, dedicated benchmark, and unit-test translation unit
    # were deleted in the same slice per RUST-FIRST.md dead-code-on-replace.
    # NOTE: `passagesim` was ported from C++ to Rust (see RUST_EXTENSION_NAMES
    # above). It is built by the Rust path, not the C++ build, so it is no
    # longer in this C++ EXTENSION_NAMES set. The C++ source, header, fuzz
    # harness, GoogleTest unit test, and dedicated benchmark were deleted in the
    # same slice per RUST-FIRST.md dead-code-on-replace.
    # NOTE: `phrasematch` was ported from C++ to Rust (see RUST_EXTENSION_NAMES
    # above). It is built by the Rust path, not the C++ build, so it is no
    # longer in this C++ EXTENSION_NAMES set. The C++ source, header, and fuzz
    # harness were deleted in the same change per RUST-FIRST.md
    # dead-code-on-replace.
    # NOTE: `quantemb` was ported from C++ to Rust (see RUST_EXTENSION_NAMES
    # above). It is built by the Rust path, not the C++ build, so it is no
    # longer in this C++ EXTENSION_NAMES set. The C++ source, header, fuzz
    # harness, GoogleTest unit test, and dedicated benchmark were deleted in the
    # same slice per RUST-FIRST.md dead-code-on-replace.
    # NOTE: `rareterm` was ported from C++ to Rust (see RUST_EXTENSION_NAMES
    # above). It is built by the Rust path, not the C++ build, so it is no
    # longer in this C++ EXTENSION_NAMES set. The C++ source, header, fuzz
    # harness, and dedicated benchmark were deleted in the same change per
    # RUST-FIRST.md dead-code-on-replace.
    # NOTE: `scoring` was ported from C++ to Rust (see RUST_EXTENSION_NAMES
    # above). It is built by the Rust path, not the C++ build, so it is no
    # longer in this C++ EXTENSION_NAMES set. The C++ source, dedicated header,
    # fuzz harness, dedicated benchmark, edge-test translation unit, and
    # GoogleTest registration were deleted in the same slice per RUST-FIRST.md
    # dead-code-on-replace.
    # NOTE: `simsearch` was ported from C++ to Rust (see RUST_EXTENSION_NAMES
    # above). It is built by the Rust path, not the C++ build, so it is no
    # longer in this C++ EXTENSION_NAMES set. The C++ source, dedicated header,
    # fuzz harness, GoogleTest unit test, dedicated benchmark, and edge-test
    # were deleted in the same slice per RUST-FIRST.md dead-code-on-replace.
    # NOTE: `texttok` was ported from C++ to Rust (see RUST_EXTENSION_NAMES
    # above). It is built by the Rust path, not the C++ build, so it is no
    # longer in this C++ EXTENSION_NAMES set. The C++ source, header, fuzz
    # harness, and shared benchmark translation unit were deleted in the same
    # change per RUST-FIRST.md dead-code-on-replace.
PROTECTED_NAMES = {
    "compiled_artifacts",
    "pgdata",
    "redis-data",
    "media_files",
    "staticfiles",
    "frontend_dist",
    "pyroscope_data",
    "loki_data",
    "alloy_data",
    "tempo_data",
    "grafana_data",
    "questdb_data",
    "sqlite_registry_data",
}


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _repo_backend_root() -> Path:
    if (BACKEND_ROOT / "extensions" / "setup.py").exists():
        return BACKEND_ROOT
    return REPO_ROOT / "backend"


def _iter_files(root: Path, patterns: tuple[str, ...]) -> list[Path]:
    files: list[Path] = []
    for pattern in patterns:
        files.extend(path for path in root.glob(pattern) if path.is_file())
    return sorted(set(files))


def _hash_files(files: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in files:
        digest.update(str(path).encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _runtime_cpp_files(extensions_root: Path) -> list[Path]:
    patterns = ("setup.py", "*.cpp", "include/*.h", "include/*.hpp")
    return _iter_files(extensions_root, patterns)


def _go_module_roots(repo_root: Path) -> list[Path]:
    ignored = _ignored_walk_dirs()
    roots: list[Path] = []
    for current, dirs, filenames in os.walk(repo_root):
        dirs[:] = [name for name in dirs if name not in ignored]
        if "go.mod" in filenames:
            roots.append(Path(current))
            dirs[:] = []
    return sorted(roots)


def _go_files(repo_root: Path) -> list[Path]:
    return _go_files_in_modules(_go_module_roots(repo_root))


def _go_files_in_modules(modules: list[Path]) -> list[Path]:
    ignored = _ignored_walk_dirs()
    files: list[Path] = []
    for module_root in modules:
        for current, dirs, filenames in os.walk(module_root):
            dirs[:] = [name for name in dirs if name not in ignored]
            current_path = Path(current)
            for filename in filenames:
                path = current_path / filename
                if filename in {"go.mod", "go.sum"} or path.suffix == ".go":
                    files.append(path)
    return sorted(files)


def _rust_extensions_workspace(repo_root: Path) -> Path:
    """Cargo workspace root for the PyO3 kernel crates (`rust/`)."""
    return repo_root / "rust"


def _rust_extension_files(workspace: Path) -> list[Path]:
    """Hash inputs for the Rust kernel build: every `.rs`, `Cargo.toml`, `Cargo.lock`.

    Walks the whole `rust/` workspace (scaffold + every `extensions/<name>`
    crate) minus build output. The digest gates the rebuild exactly like the
    C++ and speccheck source hashes: unchanged source -> no recompile.
    """
    if not (workspace / "Cargo.toml").exists():
        return []
    ignored = _ignored_walk_dirs() | {"target", "mutants.out", "mutants.out.old"}
    files: list[Path] = []
    for current, dirs, filenames in os.walk(workspace):
        dirs[:] = [name for name in dirs if name not in ignored]
        current_path = Path(current)
        for filename in filenames:
            path = current_path / filename
            if filename in {"Cargo.toml", "Cargo.lock"} or path.suffix == ".rs":
                files.append(path)
    return sorted(files)


def _rust_speccheck_root(repo_root: Path) -> Path:
    return repo_root / "services" / "speccheck"


def _rust_speccheck_files(workspace: Path) -> list[Path]:
    if not (workspace / "Cargo.toml").exists():
        return []
    ignored = _ignored_walk_dirs() | {"target", "mutants.out", "mutants.out.old"}
    files: list[Path] = []
    for current, dirs, filenames in os.walk(workspace):
        dirs[:] = [name for name in dirs if name not in ignored]
        current_path = Path(current)
        for filename in filenames:
            path = current_path / filename
            if filename in {"Cargo.toml", "Cargo.lock"} or path.suffix == ".rs":
                files.append(path)
    return sorted(files)


def _ignored_walk_dirs() -> set[str]:
    return {
        ".angular",
        ".cache",
        ".git",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".stryker-tmp",
        ".venv",
        "__pycache__",
        "backups",
        "build",
        "build_tests",
        "coverage",
        "dist",
        "htmlcov",
        "Inspiration-Temp",
        "media",
        "node_modules",
        "reports",
        "test-results",
        "vendor",
        "venv",
    }


def _load_manifest() -> dict[str, Any]:
    try:
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        manifest = {}
    return _normalize_manifest(manifest)


def _normalize_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    manifest.setdefault("schema_version", MANIFEST_SCHEMA_VERSION)
    manifest.setdefault("active", {})
    manifest.setdefault("store", {})
    manifest.setdefault("history", [])
    return manifest


def _write_manifest(manifest: dict[str, Any]) -> None:
    manifest["schema_version"] = MANIFEST_SCHEMA_VERSION
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")


def _run(command: list[str], cwd: Path) -> None:
    print("+ " + " ".join(command), flush=True)
    subprocess.run(command, cwd=cwd, timeout=COMPILED_BUILD_TIMEOUT_SECONDS, check=True)


def _run_capture(command: list[str], cwd: Path) -> str:
    print("+ " + " ".join(command), flush=True)
    result = subprocess.run(
        command,
        cwd=cwd,
        check=True,
        text=True,
        capture_output=True,
        timeout=COMPILED_BUILD_TIMEOUT_SECONDS,
    )
    return result.stdout.strip()


def _clean_dir(path: Path) -> None:
    _refuse_protected_path(path)
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def _refuse_protected_path(path: Path) -> None:
    resolved = path.resolve()
    protected_roots = [ARTIFACT_ROOT.resolve(), REPO_ROOT.resolve(), _repo_backend_root().resolve()]
    if resolved in protected_roots:
        raise ValueError(f"Refusing to delete protected path: {resolved}")
    if resolved.name in PROTECTED_NAMES:
        raise ValueError(f"Refusing to delete protected data store: {resolved.name}")


def _store_artifact(path: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    sha = _file_sha256(path)
    STORE_ROOT.mkdir(parents=True, exist_ok=True)
    store_path = STORE_ROOT / sha
    if not store_path.exists():
        shutil.copy2(path, store_path)
    stat = path.stat()
    manifest["store"][sha] = {
        "sha256": sha,
        "bytes": stat.st_size,
        "store_path": str(store_path),
        "created_at": manifest["store"].get(sha, {}).get("created_at", _now()),
        "last_used_at": _now(),
    }
    return {"sha256": sha, "bytes": stat.st_size, "store_path": str(store_path)}


def _link_or_copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() or destination.is_symlink():
        destination.unlink()
    try:
        os.link(source, destination)
    except OSError:
        shutil.copy2(source, destination)


def _artifact_records(build_output: Path, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for artifact in sorted(build_output.glob("*.so")):
        stored = _store_artifact(artifact, manifest)
        records.append(
            {
                "filename": artifact.name,
                "module": artifact.name.split(".")[0],
                **stored,
            }
        )
    return records


def _stage_artifacts(records: list[dict[str, Any]], stage_dir: Path) -> None:
    _clean_dir(stage_dir)
    (stage_dir / "extensions" / "__init__.py").parent.mkdir(parents=True, exist_ok=True)
    (stage_dir / "extensions" / "__init__.py").write_text("", encoding="utf-8")
    for record in records:
        _link_or_copy(Path(record["store_path"]), stage_dir / "extensions" / record["filename"])


def _carry_forward_rust_kernels_into_stage(stage_dir: Path) -> None:
    """Copy the already-active bare Rust kernel `.so` into the C++ stage dir.

    A kernel ported from C++ to Rust (``RUST_EXTENSION_NAMES``) is built by the
    Rust path, never the C++ build, so the freshly-built C++ stage dir does not
    contain its ``.so``. Two problems follow if we activate that stage dir as-is:

    1. ``_verify_runtime_imports(stage_dir)`` imports every Rust kernel and
       crashes with ``ModuleNotFoundError`` because they are absent from the
       C++-only stage — exactly the boot crash-loop this guards against.
    2. The activation move (``shutil.move`` of ``stage_dir/extensions`` over the
       active dir) would otherwise drop the Rust kernels out of the active dir
       until the later Rust path re-stages them — which never happens on a
       runtime host without ``cargo``.

    Copying the live active Rust ``.so`` into the stage dir before activation
    fixes both: the stage becomes the full runtime picture, the probe passes,
    and the move preserves the Rust kernels. Missing kernels are skipped (the
    Rust path handles a genuine absence); a non-existent active dir is a no-op.
    """
    staged_extensions = stage_dir / "extensions"
    if not staged_extensions.is_dir() or not ACTIVE_EXTENSIONS_ROOT.is_dir():
        return
    for name in sorted(RUST_EXTENSION_NAMES):
        source = ACTIVE_EXTENSIONS_ROOT / f"{name}.so"
        if not source.is_file():
            continue
        _link_or_copy(source, staged_extensions / f"{name}.so")


def _activate_staged_runtime(stage_dir: Path) -> None:
    ACTIVE_ROOT.mkdir(parents=True, exist_ok=True)
    if ACTIVE_EXTENSIONS_ROOT.exists():
        try:
            _activate_via_rollback_move(stage_dir)
        except PermissionError as exc:
            # 2026-05-23 — Phase K.5 fallback: the rollback-move dance
            # fails when ACTIVE_EXTENSIONS_ROOT (or any file inside it)
            # was created by a different user (typically root from a
            # previous container-run-as-root build).  The cure used to
            # be a privileged `chown` outside the script; that broke
            # automation under a non-root agent.  We now fall back to a
            # per-file atomic replacement that only needs write access
            # to the files we own and the parent dir, never permission
            # to unlink the directory itself.
            print(
                "ensure_compiled_artifacts: rollback-move blocked by "
                f"PermissionError ({exc}); falling back to per-file "
                "atomic replacement so the build can complete without "
                "shared-infrastructure root permissions.",
                flush=True,
            )
            _activate_via_file_replacement(stage_dir)
    else:
        try:
            shutil.move(str(stage_dir / "extensions"), ACTIVE_EXTENSIONS_ROOT)
            _ensure_legacy_extension_link()
        finally:
            shutil.rmtree(stage_dir, ignore_errors=True)
    _prune_rollback_sets(keep=1)


def _activate_via_rollback_move(stage_dir: Path) -> None:
    """Original full-dir rollback-then-replace activation path."""
    ROLLBACK_ROOT.mkdir(parents=True, exist_ok=True)
    previous = ROLLBACK_ROOT / f"extensions-{int(time.time())}"
    shutil.move(str(ACTIVE_EXTENSIONS_ROOT), previous)
    try:
        shutil.move(str(stage_dir / "extensions"), ACTIVE_EXTENSIONS_ROOT)
        _ensure_legacy_extension_link()
    except Exception:
        if previous.exists() and not ACTIVE_EXTENSIONS_ROOT.exists():
            shutil.move(str(previous), ACTIVE_EXTENSIONS_ROOT)
        raise
    finally:
        shutil.rmtree(stage_dir, ignore_errors=True)


def _activate_via_file_replacement(stage_dir: Path) -> None:
    """Per-file atomic replacement fallback when the directory move fails.

    Writes each file from ``stage_dir/extensions/`` into the existing
    ``ACTIVE_EXTENSIONS_ROOT`` via an ``os.replace`` rename of a
    sibling temp file.  Atomic per file.  Leaves the directory itself
    untouched, so the only permissions needed are write access to the
    individual files we own and write access to the parent directory
    (both held by the build user once the artifact is appuser-owned).
    """
    staged_extensions = stage_dir / "extensions"
    if not staged_extensions.is_dir():
        raise RuntimeError(
            f"stage directory {stage_dir} has no extensions subtree to activate"
        )
    ACTIVE_EXTENSIONS_ROOT.mkdir(parents=True, exist_ok=True)
    try:
        replaced: list[str] = []
        for source in staged_extensions.iterdir():
            if not source.is_file():
                continue
            target = ACTIVE_EXTENSIONS_ROOT / source.name
            temp = ACTIVE_EXTENSIONS_ROOT / f".activate-{source.name}.{int(time.time())}"
            shutil.copy2(source, temp)
            try:
                os.replace(temp, target)
            except OSError:
                # Cleanup the temp file before re-raising so the active
                # dir is not left littered with .activate-* fragments.
                with contextlib.suppress(OSError):
                    temp.unlink()
                raise
            replaced.append(source.name)
        _ensure_legacy_extension_link()
        print(
            "ensure_compiled_artifacts: per-file replacement updated "
            f"{len(replaced)} extension(s) in {ACTIVE_EXTENSIONS_ROOT} "
            "without touching directory ownership.",
            flush=True,
        )
    finally:
        shutil.rmtree(stage_dir, ignore_errors=True)


def _build_cpp_runtime(
    backend_root: Path,
    digest: str,
    manifest: dict[str, Any],
    *,
    force: bool = False,
) -> bool:
    cpp_entry = manifest["active"].get("cpp_runtime", {})
    if not force and cpp_entry.get("source_hash") == digest and _cpp_artifacts_present():
        print("Compiled C++ runtime artifacts are current.", flush=True)
        return False
    build_id = f"cpp-runtime-{digest[:12]}-{int(time.time())}"
    extensions_root = backend_root / "extensions"
    build_dir = BUILD_ROOT / build_id
    build_output = build_dir / "out"
    _clean_dir(build_dir)
    _run(_cpp_build_command(build_output, build_dir), cwd=extensions_root)
    records = _artifact_records(build_output, manifest)
    _validate_cpp_artifact_set(records)
    stage_dir = ACTIVE_ROOT / f".stage-{build_id}"
    _stage_artifacts(records, stage_dir)
    _carry_forward_rust_kernels_into_stage(stage_dir)
    _activate_staged_runtime(stage_dir)
    manifest["active"]["cpp_runtime"] = _cpp_manifest_entry(digest, records)
    manifest["cpp_runtime_hash"] = digest
    manifest["cpp_runtime_path"] = str(ACTIVE_EXTENSIONS_ROOT)
    _write_manifest(manifest)
    print("Compiled C++ runtime artifacts were rebuilt and deduped.", flush=True)
    return True


def _cpp_build_command(build_output: Path, build_dir: Path) -> list[str]:
    return [
        sys.executable,
        "setup.py",
        "build_ext",
        "--build-lib",
        str(build_output),
        "--build-temp",
        str(build_dir / "temp"),
    ]


def _cpp_manifest_entry(source_hash: str, records: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "language": "cpp",
        "module": "extensions",
        "source_hash": source_hash,
        "active_path": str(ACTIVE_EXTENSIONS_ROOT),
        "build_command": "python setup.py build_ext",
        "last_verified_at": _now(),
        "artifacts": records,
    }


def _validate_cpp_artifact_set(records: list[dict[str, Any]]) -> None:
    found = {record["module"] for record in records}
    missing = sorted(EXTENSION_NAMES - found)
    if missing:
        raise RuntimeError(f"C++ build did not produce required extensions: {', '.join(missing)}")


def _cpp_artifacts_present() -> bool:
    if not ACTIVE_EXTENSIONS_ROOT.exists():
        return False
    found = {path.name.split(".")[0] for path in ACTIVE_EXTENSIONS_ROOT.glob("*.so")}
    return EXTENSION_NAMES.issubset(found)


def _record_go_state(repo_root: Path, manifest: dict[str, Any]) -> None:
    modules = _go_module_roots(repo_root)
    if not modules:
        _record_no_go_modules(manifest, "no-go-modules")
        return
    files = _go_files_in_modules(modules)
    source_hash = _hash_files(files)
    go_entry = manifest["active"].get("go_runtime", {})
    if go_entry.get("source_hash") == source_hash and _go_artifacts_present(go_entry):
        print("Go runtime artifact state is current.", flush=True)
        return
    # The backend runtime container has no Go toolchain and never executes the
    # Go binaries — streamd / startupd / sidecars run as their own containers
    # and talk to the backend over gRPC/Unix sockets, so the backend does NOT
    # load /opt/xf/compiled/go artifacts at runtime. When `go` is absent here,
    # skip the rebuild unconditionally (warn only) so a Go-source change — e.g.
    # adding a new sidecar service — can never crash the backend boot. The Go
    # artifacts are (re)built in the compiled-tools container, which has Go.
    if shutil.which("go") is None:
        print(
            "Go is not installed in this container and the backend does not run "
            "Go binaries — skipping Go runtime build (build it in compiled-tools).",
            flush=True,
        )
        return
    records = _build_go_modules(modules, manifest)
    manifest["active"]["go_runtime"] = _go_manifest_entry(source_hash, records)
    manifest["go_source_hash"] = source_hash
    manifest["go_artifact_path"] = str(ACTIVE_GO_ROOT)
    _write_manifest(manifest)
    print("Go runtime artifact state is recorded and deduped.", flush=True)


def _record_rust_speccheck_state(
    repo_root: Path,
    manifest: dict[str, Any],
    *,
    force: bool = False,
) -> None:
    workspace = _rust_speccheck_root(repo_root)
    files = _rust_speccheck_files(workspace)
    if not files:
        _record_no_rust_speccheck(manifest, "no-rust-speccheck")
        return
    source_hash = _hash_files(files)
    rust_entry = manifest["active"].get("rust_speccheck", {})
    if not force and rust_entry.get("source_hash") == source_hash and _rust_speccheck_present(rust_entry):
        print("Rust speccheck binary is current.", flush=True)
        return
    if shutil.which("cargo") is None:
        if _rust_speccheck_present(rust_entry):
            print("Rust speccheck binary is active; Cargo is not installed in this container.", flush=True)
            return
        raise RuntimeError(
            "Rust speccheck build requires the Docker-managed compiled-tools container with cargo."
        )
    record = _build_rust_speccheck(workspace, source_hash, manifest)
    manifest["active"]["rust_speccheck"] = _rust_speccheck_manifest_entry(source_hash, record)
    manifest["rust_speccheck_hash"] = source_hash
    manifest["rust_speccheck_path"] = str(ACTIVE_SPECCHECK_PATH)
    _write_manifest(manifest)
    print("Rust speccheck binary was rebuilt and deduped.", flush=True)


def _record_no_rust_speccheck(manifest: dict[str, Any], source_hash: str) -> None:
    manifest["active"]["rust_speccheck"] = {
        "language": "rust",
        "source_hash": source_hash,
        "status": "no-rust-speccheck",
        "last_verified_at": _now(),
    }
    manifest["rust_speccheck_path"] = str(ACTIVE_SPECCHECK_PATH)
    _write_manifest(manifest)
    print("No Rust speccheck workspace found; no fake Rust artifact was created.", flush=True)


def _rust_speccheck_present(entry: dict[str, Any]) -> bool:
    active_path = entry.get("active_path") or str(ACTIVE_SPECCHECK_PATH)
    return Path(active_path).exists()


def _build_rust_speccheck(
    workspace: Path,
    source_hash: str,
    manifest: dict[str, Any],
) -> dict[str, Any]:
    build_id = f"rust-speccheck-{source_hash[:12]}-{int(time.time())}"
    build_dir = BUILD_ROOT / build_id
    target_dir = build_dir / "target"
    _clean_dir(build_dir)
    _run(
        [
            "cargo",
            "build",
            "--release",
            "--locked",
            "--bin",
            "speccheck",
            "--target-dir",
            str(target_dir),
        ],
        cwd=workspace,
    )
    binary = target_dir / "release" / "speccheck"
    if not binary.exists():
        raise RuntimeError(f"Rust build did not produce speccheck binary: {binary}")
    stored = _store_artifact(binary, manifest)
    _link_or_copy(Path(stored["store_path"]), ACTIVE_SPECCHECK_PATH)
    ACTIVE_SPECCHECK_PATH.chmod(0o755)
    _run([str(ACTIVE_SPECCHECK_PATH)], cwd=workspace)
    return {
        "filename": "speccheck",
        "module": "speccheck",
        "active_path": str(ACTIVE_SPECCHECK_PATH),
        **stored,
    }


def _rust_speccheck_manifest_entry(source_hash: str, record: dict[str, Any]) -> dict[str, Any]:
    return {
        "language": "rust",
        "module": "services/speccheck",
        "source_hash": source_hash,
        "status": "built",
        "active_path": str(ACTIVE_SPECCHECK_PATH),
        "build_command": "cargo build --release --locked --bin speccheck",
        "last_verified_at": _now(),
        "artifacts": [record],
    }


def _record_rust_extensions_state(
    repo_root: Path,
    manifest: dict[str, Any],
    *,
    force: bool = False,
) -> None:
    """Build the Rust PyO3 kernels and stage each `<name>.so` into active/extensions.

    Mirrors ``_build_cpp_runtime`` for Rust: hash-gated, content-addressed
    store, atomic-ish stage into the SAME ``active/extensions/`` directory the
    C++ build populated. A ported kernel (e.g. ``l2norm``) overwrites the C++
    ``.so`` of the same name, so ``from extensions import l2norm`` resolves to
    the Rust build. Skips cleanly when the workspace or Cargo are absent so a
    runtime container without the Rust toolchain (the backend image) never
    crashes — the kernels are (re)built in the compiled-tools image.
    """
    workspace = _rust_extensions_workspace(repo_root)
    files = _rust_extension_files(workspace)
    if not files or not RUST_EXTENSION_NAMES:
        _record_no_rust_extensions(manifest, "no-rust-extensions")
        return
    source_hash = _hash_files(files)
    rust_entry = manifest["active"].get("rust_extensions", {})
    if (
        not force
        and rust_entry.get("source_hash") == source_hash
        and _rust_extensions_present(rust_entry)
    ):
        print("Rust extension kernels are current.", flush=True)
        return
    if shutil.which("cargo") is None:
        if _rust_extensions_present(rust_entry):
            print(
                "Rust extension kernels are active; Cargo is not installed in this container.",
                flush=True,
            )
            return
        raise RuntimeError(
            "Rust extension build requires the Docker-managed compiled-tools container with cargo."
        )
    records = _build_rust_extensions(workspace, manifest)
    manifest["active"]["rust_extensions"] = _rust_extensions_manifest_entry(
        source_hash, records
    )
    manifest["rust_extensions_hash"] = source_hash
    manifest["rust_extensions_path"] = str(ACTIVE_EXTENSIONS_ROOT)
    _write_manifest(manifest)
    print("Rust extension kernels were rebuilt and deduped.", flush=True)


def _record_no_rust_extensions(manifest: dict[str, Any], source_hash: str) -> None:
    manifest["active"]["rust_extensions"] = {
        "language": "rust",
        "source_hash": source_hash,
        "status": "no-rust-extensions",
        "last_verified_at": _now(),
    }
    manifest["rust_extensions_path"] = str(ACTIVE_EXTENSIONS_ROOT)
    _write_manifest(manifest)
    print("No Rust extension crates found; no fake Rust artifact was created.", flush=True)


def _rust_extensions_present(entry: dict[str, Any]) -> bool:
    if entry.get("status") == "no-rust-extensions":
        return True
    artifacts = entry.get("artifacts", [])
    if not artifacts:
        return False
    return all(
        artifact.get("active_path") and Path(artifact["active_path"]).exists()
        for artifact in artifacts
    )


def _build_rust_extensions(
    workspace: Path,
    manifest: dict[str, Any],
) -> list[dict[str, Any]]:
    """Compile every Rust kernel crate and stage `<name>.so` into active/extensions.

    Uses ``cargo build --release -p <name>`` (one package per kernel) so the
    workspace's scaffold crate is not force-built. The cdylib output is
    ``target/release/lib<name>.so``; it is content-addressed into the store and
    linked into ``active/extensions/<name>.so`` so the import name matches.
    """
    ACTIVE_EXTENSIONS_ROOT.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    for name in sorted(RUST_EXTENSION_NAMES):
        records.append(_build_one_rust_extension(workspace, name, manifest))
    _verify_runtime_imports()
    return records


def _build_one_rust_extension(
    workspace: Path,
    name: str,
    manifest: dict[str, Any],
) -> dict[str, Any]:
    """Build a single Rust kernel crate and stage its `.so` as `<name>.so`."""
    build_id = f"rust-extension-{name}-{int(time.time())}"
    build_dir = BUILD_ROOT / build_id
    target_dir = build_dir / "target"
    _clean_dir(build_dir)
    _run(
        [
            "cargo",
            "build",
            "--release",
            "--locked",
            "--package",
            name,
            "--target-dir",
            str(target_dir),
        ],
        cwd=workspace,
    )
    cdylib = target_dir / "release" / f"lib{name}.so"
    if not cdylib.exists():
        raise RuntimeError(f"Rust build did not produce {cdylib}")
    stored = _store_artifact(cdylib, manifest)
    active_path = ACTIVE_EXTENSIONS_ROOT / f"{name}.so"
    _link_or_copy(Path(stored["store_path"]), active_path)
    _remove_superseded_cpp_artifact(name)
    shutil.rmtree(build_dir, ignore_errors=True)
    return {
        "filename": f"{name}.so",
        "module": name,
        "active_path": str(active_path),
        "build_command": f"cargo build --release --locked --package {name}",
        **stored,
    }


def _remove_superseded_cpp_artifact(name: str) -> None:
    """Delete the ABI-tagged C++ `.so` so Python imports the bare Rust `<name>.so`.

    The C++ build stages `<name>.cpython-312-x86_64-linux-gnu.so` (a
    platform-specific extension suffix). CPython prefers that suffix over a
    bare `<name>.so`, so without this purge `from extensions import <name>`
    would resolve to the C++ build even though the Rust `<name>.so` sits beside
    it. Removing the ABI-tagged sibling makes the Rust build authoritative for
    this kernel while leaving every other C++ kernel untouched.
    """
    for sibling in ACTIVE_EXTENSIONS_ROOT.glob(f"{name}.*.so"):
        if sibling.name == f"{name}.so":
            continue
        try:
            sibling.unlink()
            print(
                f"Removed superseded C++ artifact {sibling.name}; "
                f"Rust {name}.so is now the import target.",
                flush=True,
            )
        except OSError as exc:
            print(
                f"Could not remove superseded C++ artifact {sibling.name}: {exc}",
                file=sys.stderr,
                flush=True,
            )


def _rust_extensions_manifest_entry(
    source_hash: str,
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "language": "rust",
        "module": "rust/extensions",
        "source_hash": source_hash,
        "status": "built" if records else "no-extensions",
        "active_path": str(ACTIVE_EXTENSIONS_ROOT),
        "build_command": "cargo build --release --locked --package <name>",
        "last_verified_at": _now(),
        "artifacts": records,
    }


def _record_no_go_modules(manifest: dict[str, Any], source_hash: str) -> None:
    manifest["active"]["go_runtime"] = {
        "language": "go",
        "source_hash": source_hash,
        "status": "no-go-modules",
        "modules": [],
        "last_verified_at": _now(),
    }
    manifest["go_source_hash"] = source_hash
    manifest["go_artifact_path"] = str(ACTIVE_GO_ROOT)
    _write_manifest(manifest)
    print("No Go modules found; no fake Go artifacts were created.", flush=True)


def _go_artifacts_present(entry: dict[str, Any]) -> bool:
    if entry.get("status") == "no-go-modules":
        return True
    artifacts = entry.get("artifacts", [])
    if not artifacts and entry.get("status") == "built":
        return False
    return all(
        artifact.get("active_path") and Path(artifact["active_path"]).exists()
        for artifact in artifacts
    )


def _build_go_modules(modules: list[Path], manifest: dict[str, Any]) -> list[dict[str, Any]]:
    _clean_dir(ACTIVE_GO_ROOT)
    records: list[dict[str, Any]] = []
    for module_root in modules:
        records.extend(_build_go_module(module_root, manifest))
    return records


def _build_go_module(module_root: Path, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    # `-buildvcs=false` keeps the call working inside containers where the
    # /repo bind-mount has a .git folder whose ownership does not match the
    # current uid (Go's default VCS stamping shells `git status` and treats
    # the resulting "dubious ownership" exit-128 as fatal). The artifact
    # store is content-addressed off the source hash, not VCS metadata, so
    # disabling VCS stamping does not change reproducibility.
    package_lines = _run_capture(
        ["go", "list", "-buildvcs=false", "-f",
         "{{if eq .Name \"main\"}}{{.ImportPath}}{{end}}", "./..."],
        cwd=module_root,
    ).splitlines()
    main_packages = [line for line in package_lines if line.strip()]
    records: list[dict[str, Any]] = []
    for import_path in main_packages:
        output_name = import_path.replace("/", "_").replace("\\", "_")
        scratch_output = BUILD_ROOT / "go-runtime" / output_name
        _run(
            ["go", "build", "-buildvcs=false", "-o", str(scratch_output), import_path],
            cwd=module_root,
        )
        stored = _store_artifact(scratch_output, manifest)
        active_path = ACTIVE_GO_ROOT / output_name
        _link_or_copy(Path(stored["store_path"]), active_path)
        records.append(_go_artifact_record(module_root, import_path, active_path, stored))
    return records


def _go_artifact_record(
    module_root: Path,
    import_path: str,
    active_path: Path,
    stored: dict[str, Any],
) -> dict[str, Any]:
    return {
        "language": "go",
        "module": str(module_root.relative_to(REPO_ROOT)) if module_root.is_relative_to(REPO_ROOT) else str(module_root),
        "import_path": import_path,
        "active_path": str(active_path),
        "build_command": f"go build -o {active_path.name} {import_path}",
        **stored,
    }


def _go_manifest_entry(source_hash: str, records: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "language": "go",
        "source_hash": source_hash,
        "status": "built" if records else "no-main-packages",
        "active_path": str(ACTIVE_GO_ROOT),
        "last_verified_at": _now(),
        "artifacts": records,
    }


def _verify_runtime_imports(active_root: Path = ACTIVE_ROOT) -> None:
    pythonpath = os.pathsep.join([str(active_root), str(BACKEND_ROOT), os.environ.get("PYTHONPATH", "")])
    env = {**os.environ, "PYTHONPATH": pythonpath}
    code = _runtime_import_probe_code()
    subprocess.run(
        [sys.executable, "-c", code],
        check=True,
        env=env,
        timeout=COMPILED_IMPORT_TIMEOUT_SECONDS,
    )
    print("Compiled runtime imports are ready.", flush=True)


def _runtime_import_probe_code() -> str:
    """Return Python code that imports required native modules and public names."""
    # `texttok`, `scoring`, and `simsearch` were ported to Rust, so they are now
    # imported and attribute-checked by the rust path below
    # (RUST_EXTENSION_NAMES) rather than as a bare legacy C++ import here. No
    # bare-import-only C++ kernels remain.
    legacy_modules: tuple[str, ...] = ()
    rust_checks = {
        name: RUST_EXTENSION_EXPECTED_ATTRS[name]
        for name in sorted(RUST_EXTENSION_NAMES)
    }
    rust_imports = [
        f"{name} = importlib.import_module('extensions.{name}')"
        for name in rust_checks
    ]
    return "\n".join(
        [
            "import importlib",
            *(f"importlib.import_module('extensions.{name}')" for name in legacy_modules),
            *rust_imports,
            "expected = " + repr(rust_checks),
            "for name, attr in expected.items():",
            "    module = globals()[name]",
            "    if not hasattr(module, attr):",
            "        raise RuntimeError(f'extensions.{name} missing {attr}')",
        ]
    )


def _ensure_legacy_extension_link() -> None:
    legacy = ARTIFACT_ROOT / "extensions"
    if legacy == ACTIVE_EXTENSIONS_ROOT:
        return
    if legacy.exists() or legacy.is_symlink():
        if legacy.is_symlink() or legacy.is_file():
            legacy.unlink()
        else:
            shutil.rmtree(legacy)
    try:
        legacy.symlink_to(ACTIVE_EXTENSIONS_ROOT, target_is_directory=True)
    except OSError:
        shutil.copytree(ACTIVE_EXTENSIONS_ROOT, legacy)


def _prune_rollback_sets(*, keep: int) -> None:
    if not ROLLBACK_ROOT.exists():
        return
    entries = sorted((path for path in ROLLBACK_ROOT.iterdir() if path.is_dir()), reverse=True)
    for old_entry in entries[keep:]:
        shutil.rmtree(old_entry)


def prune_stale(*, retention_days: int = STORE_RETENTION_DAYS, dry_run: bool = False) -> dict[str, Any]:
    manifest = _load_manifest()
    referenced = _referenced_store_hashes(manifest)
    cutoff = time.time() - retention_days * 24 * 60 * 60
    deleted_store = _prune_store_files(referenced, cutoff, dry_run=dry_run)
    deleted_scratch = _prune_scratch_dirs(dry_run=dry_run)
    if not dry_run:
        _write_manifest(manifest)
    return {"store_files": deleted_store, "scratch_dirs": deleted_scratch, "dry_run": dry_run}


def _referenced_store_hashes(manifest: dict[str, Any]) -> set[str]:
    referenced: set[str] = set()
    for section in manifest.get("active", {}).values():
        for artifact in section.get("artifacts", []):
            if artifact.get("sha256"):
                referenced.add(artifact["sha256"])
    return referenced


def _prune_store_files(referenced: set[str], cutoff: float, *, dry_run: bool) -> list[str]:
    deleted: list[str] = []
    if not STORE_ROOT.exists():
        return deleted
    for store_file in STORE_ROOT.iterdir():
        if store_file.name in referenced or store_file.stat().st_mtime > cutoff:
            continue
        deleted.append(str(store_file))
        if not dry_run:
            store_file.unlink()
    return deleted


def _prune_scratch_dirs(*, dry_run: bool) -> list[str]:
    _validate_scratch_root(BUILD_ROOT)
    deleted: list[str] = []
    if not BUILD_ROOT.exists():
        return deleted
    for child in BUILD_ROOT.iterdir():
        if not child.is_dir():
            continue
        deleted.append(str(child))
        if not dry_run:
            shutil.rmtree(child)
    return deleted


def _validate_scratch_root(root: Path) -> None:
    resolved = root.resolve()
    if str(resolved) in {"/", "\\"} or resolved.name in PROTECTED_NAMES:
        raise ValueError(f"Refusing to prune protected path: {resolved}")
    if ARTIFACT_ROOT.resolve() in resolved.parents or resolved == ARTIFACT_ROOT.resolve():
        raise ValueError(f"Refusing to prune compiled artifact storage: {resolved}")


def manifest_status() -> dict[str, Any]:
    manifest = _load_manifest()
    return {
        "artifact_root": str(ARTIFACT_ROOT),
        "build_root": str(BUILD_ROOT),
        "active_cpp_artifacts_present": _cpp_artifacts_present(),
        "active_speccheck_present": ACTIVE_SPECCHECK_PATH.exists(),
        "manifest": manifest,
    }


class _FileLock:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.handle = None

    def __enter__(self) -> "_FileLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.path.open("w", encoding="utf-8")
        if fcntl is not None:
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX)
        return self

    def __exit__(self, *_exc: object) -> None:
        if self.handle is None:
            return
        if fcntl is not None:
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        self.handle.close()


def ensure_artifacts(*, force: bool = False) -> int:
    backend_root = _repo_backend_root()
    extensions_root = backend_root / "extensions"
    if not (extensions_root / "setup.py").exists():
        print(f"Missing C++ setup file: {extensions_root / 'setup.py'}", file=sys.stderr)
        return 1
    ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)
    BUILD_ROOT.mkdir(parents=True, exist_ok=True)
    with _FileLock(ARTIFACT_ROOT / ".compile.lock"):
        manifest = _load_manifest()
        cpp_digest = _hash_files(_runtime_cpp_files(extensions_root))
        _build_cpp_runtime(backend_root, cpp_digest, manifest, force=force)
        # Stage Rust kernels AFTER the C++ build so a ported kernel (e.g.
        # l2norm) overwrites the C++ `.so` of the same name in the active
        # extensions dir, making `from extensions import l2norm` resolve to Rust.
        manifest = _load_manifest()
        _record_rust_extensions_state(REPO_ROOT, manifest, force=force)
        manifest = _load_manifest()
        _record_go_state(REPO_ROOT, manifest)
        manifest = _load_manifest()
        _record_rust_speccheck_state(REPO_ROOT, manifest, force=force)
        _verify_runtime_imports()
    return 0


def check_artifacts() -> int:
    missing: list[str] = []
    if not _cpp_artifacts_present():
        missing.append("compiled C++ extension runtime")
    if not ACTIVE_SPECCHECK_PATH.exists():
        missing.append("Rust speccheck binary")
    if missing:
        print(
            "Missing Docker-managed compiled artifact(s): " + ", ".join(missing),
            file=sys.stderr,
            flush=True,
        )
        print(
            "Run the compiled-tools service to build them before starting app containers.",
            file=sys.stderr,
            flush=True,
        )
        return 1
    _verify_runtime_imports()
    print("Docker-managed compiled artifacts are ready.", flush=True)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="Verify active artifacts, then exit.")
    parser.add_argument("--json", action="store_true", help="Print manifest status as JSON.")
    parser.add_argument("--prune-stale", action="store_true", help="Delete stale store and scratch files.")
    parser.add_argument("--dry-run", action="store_true", help="Show prune results without deleting.")
    parser.add_argument("--force", action="store_true", help="Rebuild runtime artifacts safely.")
    parser.add_argument("--retention-days", type=int, default=STORE_RETENTION_DAYS)
    args = parser.parse_args()
    if args.json:
        print(json.dumps(manifest_status(), indent=2, sort_keys=True))
        return 0
    if args.prune_stale:
        result = prune_stale(retention_days=args.retention_days, dry_run=args.dry_run)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    if args.check:
        return check_artifacts()
    return ensure_artifacts(force=args.force)


if __name__ == "__main__":
    raise SystemExit(main())
