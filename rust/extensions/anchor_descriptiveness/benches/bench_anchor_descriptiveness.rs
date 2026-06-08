//! Criterion benchmark for the anchor-descriptiveness kernel cores.
//!
//! Benchmarks the plain-Rust `damerau_levenshtein_core` and
//! `char_trigram_jaccard_core` over three input sizes (20, 60, 180 bytes),
//! matching the Mandatory Benchmark Rule (3 input sizes per hot path),
//! `RUST-FIRST.md` step 5, and the replaced C++ `BM_DamerauLevenshtein` /
//! `BM_CharTrigramJaccard` benchmarks (the same `Arg(20)/Arg(60)/Arg(180)`
//! sizes). Each timed iteration compares two near-identical strings (one
//! transposed character) so the DP and the trigram-overlap paths are exercised.

use anchor_descriptiveness::{char_trigram_jaccard_core, damerau_levenshtein_core};
use criterion::{criterion_group, criterion_main, BenchmarkId, Criterion};

/// Anchor-text lengths: short, medium, and long.
const SIZES: [usize; 3] = [20, 60, 180];

/// Build a deterministic byte string of length `n` plus a near-duplicate with
/// one adjacent transposition near the middle, so both kernels do real work.
fn pair(n: usize) -> (Vec<u8>, Vec<u8>) {
    let base: Vec<u8> = (0..n)
        .map(|i| b'a' + u8::try_from(i % 26).unwrap())
        .collect();
    let mut other = base.clone();
    if n >= 2 {
        let mid = n / 2;
        other.swap(mid - 1, mid);
    }
    (base, other)
}

fn bench_damerau(c: &mut Criterion) {
    let mut group = c.benchmark_group("anchor_descriptiveness_damerau");
    for n in SIZES {
        let (a, b) = pair(n);
        group.bench_with_input(BenchmarkId::from_parameter(n), &(a, b), |bn, (a, b)| {
            bn.iter(|| damerau_levenshtein_core(a, b));
        });
    }
    group.finish();
}

fn bench_jaccard(c: &mut Criterion) {
    let mut group = c.benchmark_group("anchor_descriptiveness_jaccard");
    for n in SIZES {
        let (a, b) = pair(n);
        group.bench_with_input(BenchmarkId::from_parameter(n), &(a, b), |bn, (a, b)| {
            bn.iter(|| char_trigram_jaccard_core(a, b));
        });
    }
    group.finish();
}

criterion_group!(benches, bench_damerau, bench_jaccard);
criterion_main!(benches);
