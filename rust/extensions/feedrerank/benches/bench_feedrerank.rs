//! Criterion benchmark for the feedrerank kernel cores.
//!
//! Benchmarks both pure-Rust cores (`rerank_factors_core` and
//! `mmr_scores_core`) over three input sizes, matching the Mandatory Benchmark
//! Rule (3 input sizes per hot path), `RUST-FIRST.md` step 5, and the deleted
//! C++ `bench_feedrerank.cpp`. The MMR bench uses a 384-wide embedding to match
//! the production embedding width.
//!
//! The `(i % N) as f64` synthetic-data casts are bounded by small moduli (< 13)
//! so the usize → f64 conversion is exact; the precision-loss lint is allowed
//! for this benchmark-only data generation.
#![allow(clippy::cast_precision_loss)]

use criterion::{criterion_group, criterion_main, BenchmarkId, Criterion};
use feedrerank::{mmr_scores_core, rerank_factors_core};

/// Candidate counts: a small slate, a typical page, and a large batch.
const SIZES: [usize; 3] = [16, 256, 4096];
/// Production embedding width.
const WIDTH: usize = 384;
/// Already-selected embeddings the MMR bench compares against.
const SELECTED: usize = 8;

fn bench_rerank(c: &mut Criterion) {
    let mut group = c.benchmark_group("feedrerank_rerank_factors");
    for n in SIZES {
        let successes: Vec<i32> = (0..n).map(|i| i32::try_from(i % 10).unwrap()).collect();
        let totals: Vec<i32> = (0..n).map(|i| i32::try_from(i % 20 + 1).unwrap()).collect();
        let oc: Vec<f64> = (0..n).map(|i| (i % 11) as f64 / 10.0).collect();
        group.bench_with_input(BenchmarkId::from_parameter(n), &n, |b, _| {
            b.iter(|| rerank_factors_core(&successes, &totals, &oc, 10_000, 1.0, 1.0, 0.3, 0.2));
        });
    }
    group.finish();
}

fn bench_mmr(c: &mut Criterion) {
    let mut group = c.benchmark_group("feedrerank_mmr_scores");
    for n in SIZES {
        let relevance: Vec<f64> = (0..n).map(|i| (i % 7) as f64 / 7.0).collect();
        let candidate: Vec<f64> = (0..n * WIDTH).map(|i| (i % 13) as f64 / 13.0).collect();
        let selected: Vec<f64> = (0..SELECTED * WIDTH)
            .map(|i| (i % 5) as f64 / 5.0)
            .collect();
        group.bench_with_input(BenchmarkId::from_parameter(n), &n, |b, _| {
            b.iter(|| mmr_scores_core(&relevance, &candidate, &selected, n, SELECTED, WIDTH, 0.7));
        });
    }
    group.finish();
}

criterion_group!(benches, bench_rerank, bench_mmr);
criterion_main!(benches);
