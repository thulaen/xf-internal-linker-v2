from setuptools import setup
from pybind11.setup_helpers import Pybind11Extension, build_ext
import sys

# NOTE: the `l2norm` kernel was ported to Rust (rust/extensions/l2norm,
# built via PyO3 + maturin) and is no longer built here. Per RUST-FIRST.md
# the C++ source, header, bench, and fuzz harness were deleted in the same
# change that proved the Rust kernel, so there is exactly one implementation.
ext_modules = [
    # NOTE: `scoring` was ported from C++ to Rust (rust/extensions/scoring,
    # built via PyO3 + maturin) and is no longer built here. Per RUST-FIRST.md
    # the C++ source, dedicated header, bench, edge test, and fuzz harness were
    # deleted in the same change that proved the Rust kernel, so there is
    # exactly one implementation.
    # NOTE: `texttok` was ported from C++ to Rust (rust/extensions/texttok,
    # built via PyO3 + maturin) and is no longer built here. Per RUST-FIRST.md
    # the C++ source, header, bench, and fuzz harness were deleted in the same
    # change that proved the Rust kernel, so there is exactly one
    # implementation.
    # NOTE: `simsearch` was ported from C++ to Rust (rust/extensions/simsearch,
    # built via PyO3 + maturin) and is no longer built here. Per RUST-FIRST.md
    # the C++ source, dedicated header, fuzz harness, GoogleTest unit test,
    # dedicated benchmark, and edge-test were deleted in the same change that
    # proved the Rust kernel, so there is exactly one implementation.
    # NOTE: `pagerank` was ported from C++ to Rust (rust/extensions/pagerank,
    # built via PyO3 + maturin) and is no longer built here. Per RUST-FIRST.md
    # the C++ source, dedicated header, and fuzz harness were deleted in the same
    # change that proved the Rust kernel, so there is exactly one implementation.
    # NOTE: `phrasematch` was ported from C++ to Rust (rust/extensions/phrasematch,
    # built via PyO3 + maturin) and is no longer built here. Per RUST-FIRST.md
    # the C++ source, header, and fuzz harness were deleted in the same change
    # that proved the Rust kernel, so there is exactly one implementation.
    # NOTE: `fieldrel` was ported from C++ to Rust (rust/extensions/fieldrel,
    # built via PyO3 + maturin) and is no longer built here. Per RUST-FIRST.md
    # the C++ source, dedicated header, fuzz harness, and dedicated benchmark
    # were deleted in the same change that proved the Rust kernel, so there is
    # exactly one implementation.
    # NOTE: `rareterm` was ported from C++ to Rust (rust/extensions/rareterm,
    # built via PyO3 + maturin) and is no longer built here. Per RUST-FIRST.md
    # the C++ source, header, bench, and fuzz harness were deleted in the same
    # change that proved the Rust kernel, so there is exactly one
    # implementation.
    # NOTE: `linkparse` was ported from C++ to Rust (rust/extensions/linkparse,
    # built via PyO3 + maturin) and is no longer built here. Per RUST-FIRST.md
    # the C++ source, header, fuzz harness, and orphan benchmark were deleted in
    # the same change that proved the Rust kernel, so there is exactly one
    # implementation.
    # NOTE: `feedrerank` was ported from C++ to Rust (rust/extensions/feedrerank,
    # built via PyO3 + maturin) and is no longer built here. Per RUST-FIRST.md
    # the C++ source, dedicated header, fuzz harness, and orphan benchmark were
    # deleted in the same change that proved the Rust kernel, so there is exactly
    # one implementation.
    # NOTE: `anchor_diversity` was ported from C++ to Rust
    # (rust/extensions/anchor_diversity, built via PyO3 + maturin) and is no
    # longer built here. Per RUST-FIRST.md the C++ source, header, fuzz harness,
    # and dedicated benchmark were deleted in the same change that proved the
    # Rust kernel, so there is exactly one implementation.
    # ── Anti-garbage anchor signals (3 algos, plan PR-Anchor) ─────
    # Each sits in its own extension per the one-kernel-per-.cpp
    # pattern. All three are tiny — well under the 64 MB RAM /
    # 64 MB disk caps the plan called for.
    # NOTE: `generic_anchor_matcher` was ported from C++ to Rust
    # (rust/extensions/generic_anchor_matcher). It is built by the Rust path, so
    # its Pybind11Extension build entry was removed here per RUST-FIRST.md
    # dead-code-on-replace. The C++ source and fuzz harness were deleted in the
    # same slice.
    # NOTE: `anchor_descriptiveness` was ported from C++ to Rust
    # (rust/extensions/anchor_descriptiveness). It is built by the Rust path, so
    # its Pybind11Extension build entry was removed here per RUST-FIRST.md
    # dead-code-on-replace. The C++ source and fuzz harness were deleted and the
    # shared bench_anchor_garbage.cpp had its pieces removed in the same slice.
    # NOTE: `anchor_self_information` was ported from C++ to Rust
    # (rust/extensions/anchor_self_information). It is built by the Rust path,
    # so its Pybind11Extension build entry was removed here per RUST-FIRST.md
    # dead-code-on-replace. The C++ source, fuzz harness, and shared benchmark
    # translation unit were deleted in the same slice.
    # NOTE: pixie_walk.cpp is an empty 0-byte stub left from phase-0
    # scaffolding (FR-021). The C++ Pixie-style random walk over the
    # Article-Entity bipartite graph was never written. Its caller in
    # apps/pipeline/services/candidate_retrievers.py wraps the import in
    # try/except ImportError and gracefully degrades — PixieRetriever
    # silently returns no candidates, which is the same behaviour every
    # contributor has lived with since the project was created. Skipping
    # the build here so the link step doesn't fail on the missing
    # PyInit_pixie_walk symbol. Re-enable when a real implementation lands.
    # Pybind11Extension(
    #     "pixie_walk",
    #     ["pixie_walk.cpp"],
    #     extra_compile_args=["-O3", "-std=c++17", "-march=native"]
    #     if sys.platform != "win32"
    #     else ["/O2", "/std:c++17", "/arch:AVX2"],
    # ),
    # NOTE: `quantemb` was ported from C++ to Rust (rust/extensions/quantemb —
    # OPQ encoder + trainer). It is built by the Rust path, so its
    # Pybind11Extension build entry and C++ source/header/fuzz/test/bench were
    # deleted here per RUST-FIRST.md dead-code-on-replace.
    # NOTE: `passagesim` was ported from C++ to Rust (rust/extensions/passagesim
    # — FR-053 passage-level MaxSim kernel). It is built by the Rust path, so its
    # Pybind11Extension build entry and C++ source/header/fuzz/test/bench were
    # deleted here per RUST-FIRST.md dead-code-on-replace.
    # NOTE: `ivf_index` was ported from C++ to Rust
    # (rust/extensions/ivf_index). It is built by the Rust path, so its
    # Pybind11Extension build entry and C++ source/header/fuzz/test/bench were
    # deleted here per RUST-FIRST.md dead-code-on-replace.
    # NOTE: `counting_bloom` was ported from C++ to Rust
    # (rust/extensions/counting_bloom). It is built by the Rust path, so its
    # Pybind11Extension build entry and C++ source were deleted here per
    # RUST-FIRST.md dead-code-on-replace.
    # NOTE: `compressed_bloom` was ported from C++ to Rust
    # (rust/extensions/compressed_bloom). It is built by the Rust path, so its
    # Pybind11Extension build entry and C++ source were deleted here per
    # RUST-FIRST.md dead-code-on-replace.
    # NOTE: `count_min_sketch` was ported from C++ to Rust
    # (rust/extensions/count_min_sketch). It is built by the Rust path, so its
    # Pybind11Extension build entry and C++ source were deleted here per
    # RUST-FIRST.md dead-code-on-replace.
    # NOTE: `api_rate_limiter` was ported from C++ to Rust
    # (rust/extensions/api_rate_limiter — FR-250 outbound rate limiter for GSC,
    # GA4, Matomo, XenForo, WordPress). It is built by the Rust path, so its
    # Pybind11Extension build entry and C++ source were deleted here per
    # RUST-FIRST.md dead-code-on-replace.
    # NOTE: `papertrail_dedup` was ported from C++ to Rust
    # (rust/extensions/papertrail_dedup — MinHash + LSH near-duplicate index;
    # sources of truth Broder 1997, Indyk-Motwani 1998, MMDS Ch.3). It is built
    # by the Rust path, so its Pybind11Extension build entry, C++ source, header,
    # fuzz harness, benchmark, and unit-test translation unit were deleted here
    # per RUST-FIRST.md dead-code-on-replace.
    # NOTE: `lesson_index` was ported from C++ to Rust
    # (rust/extensions/lesson_index — three-sub-index in-process cache:
    # ScopedLessonIndex, PerfBaselineCache, CitationCache; CRC-32C snapshots per
    # RFC 3309). It is built by the Rust path, so its Pybind11Extension build
    # entry, C++ source, header, fuzz harness, benchmark, and unit-test
    # translation unit were deleted here per RUST-FIRST.md dead-code-on-replace.
]


setup(
    name="xf_linker_extensions",
    version="0.1.0",
    ext_modules=ext_modules,
    cmdclass={"build_ext": build_ext},
)
