//! Criterion benchmark for the Aho-Corasick generic-anchor matcher core.
//!
//! Benchmarks the plain-Rust `AutomatonCore` over three input sizes for each of
//! the two hot paths, matching the Mandatory Benchmark Rule (3 input sizes per
//! hot path), `RUST-FIRST.md` step 5, and the removed C++ `BM_GenericAnchorBuild`
//! (50/500/5000 phrases) and `BM_GenericAnchorFindAll` (200/2000/20000-byte
//! corpus) benchmarks it replaces.

use std::fmt::Write as _;

use criterion::{criterion_group, criterion_main, BenchmarkId, Criterion};
use generic_anchor_matcher::AutomatonCore;

/// Phrase-count sizes for the build benchmark (mirrors the C++ Arg(50/500/5000)).
const BUILD_SIZES: [usize; 3] = [50, 500, 5000];

/// Corpus byte-length sizes for the `find_all` benchmark
/// (mirrors the C++ Arg(200/2000/20000)).
const FIND_SIZES: [usize; 3] = [200, 2000, 20_000];

/// Build a deterministic lexicon of `n` distinct short phrases.
fn make_phrases(n: usize) -> Vec<String> {
    (0..n).map(|i| format!("anchor-phrase-{i}")).collect()
}

/// Build a deterministic corpus of `n` bytes that contains many lexicon hits.
fn make_corpus(n: usize) -> String {
    let mut s = String::with_capacity(n + 32);
    let mut i = 0usize;
    while s.len() < n {
        // `write!` into the String avoids the extra `format!` allocation.
        let _ = write!(s, "anchor-phrase-{} filler ", i % 1000);
        i += 1;
    }
    s.truncate(n);
    s
}

fn bench_build(c: &mut Criterion) {
    let mut group = c.benchmark_group("generic_anchor_matcher_build");
    for n in BUILD_SIZES {
        let phrases = make_phrases(n);
        group.bench_with_input(BenchmarkId::from_parameter(n), &phrases, |b, phrases| {
            // `build` consumes its Vec, so clone the fixed input per iteration.
            b.iter(|| AutomatonCore::build(phrases.clone()));
        });
    }
    group.finish();
}

fn bench_find_all(c: &mut Criterion) {
    let mut group = c.benchmark_group("generic_anchor_matcher_find_all");
    let aut = AutomatonCore::build(make_phrases(500));
    for n in FIND_SIZES {
        let corpus = make_corpus(n);
        group.bench_with_input(BenchmarkId::from_parameter(n), &corpus, |b, corpus| {
            b.iter(|| aut.find_all(corpus));
        });
    }
    group.finish();
}

criterion_group!(benches, bench_build, bench_find_all);
criterion_main!(benches);
