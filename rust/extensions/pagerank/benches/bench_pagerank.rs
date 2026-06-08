//! Criterion benchmark for the pagerank kernel cores.
//!
//! Benchmarks all three pure-Rust cores (`pagerank_step_core`,
//! `personalized_pagerank_step_core`, `hits_step_core`) over three graph sizes,
//! matching the Mandatory Benchmark Rule (3 input sizes per hot path),
//! `RUST-FIRST.md` step 5, and the shared C++ graph benchmark. Each timed
//! iteration runs ONE power-iteration step over a synthetic ring graph where
//! every node points at the next, so `indptr`/`indices`/`data` are dense and
//! the sparse matrix-vector inner loop is exercised on every row.
//!
//! The `as f64`/`as i32` synthetic-graph casts are bounded by the node count,
//! which stays well under 2^52, so the conversions are exact for these sizes.
#![allow(
    clippy::cast_precision_loss,
    clippy::cast_possible_truncation,
    clippy::cast_possible_wrap
)]

use criterion::{criterion_group, criterion_main, BenchmarkId, Criterion};
use pagerank::{hits_step_core, pagerank_step_core, personalized_pagerank_step_core};

/// Node counts: small, medium, and large graphs.
const SIZES: [usize; 3] = [64, 1024, 16_384];

/// Build a ring graph CSR: target `v` has the single source `(v + n - 1) % n`.
fn ring_csr(n: usize) -> (Vec<i32>, Vec<i32>, Vec<f64>) {
    let indptr: Vec<i32> = (0..=n).map(|i| i as i32).collect();
    let indices: Vec<i32> = (0..n).map(|v| ((v + n - 1) % n) as i32).collect();
    let data = vec![1.0_f64; n];
    (indptr, indices, data)
}

fn bench_pagerank(c: &mut Criterion) {
    let mut group = c.benchmark_group("pagerank_step");
    for n in SIZES {
        let (indptr, indices, data) = ring_csr(n);
        let ranks = vec![1.0 / n as f64; n];
        let dangling = vec![false; n];
        group.bench_with_input(BenchmarkId::from_parameter(n), &n, |b, _| {
            b.iter(|| pagerank_step_core(&indptr, &indices, &data, &ranks, &dangling, 0.15, n));
        });
    }
    group.finish();
}

fn bench_personalized(c: &mut Criterion) {
    let mut group = c.benchmark_group("personalized_pagerank_step");
    for n in SIZES {
        let (indptr, indices, data) = ring_csr(n);
        let ranks = vec![1.0 / n as f64; n];
        let dangling = vec![false; n];
        let seed = vec![1.0 / n as f64; n];
        group.bench_with_input(BenchmarkId::from_parameter(n), &n, |b, _| {
            b.iter(|| {
                personalized_pagerank_step_core(
                    &indptr, &indices, &data, &ranks, &dangling, &seed, 0.15, n,
                )
            });
        });
    }
    group.finish();
}

fn bench_hits(c: &mut Criterion) {
    let mut group = c.benchmark_group("hits_step");
    for n in SIZES {
        let (indptr, indices, data) = ring_csr(n);
        let authority = vec![1.0_f64; n];
        let hub = vec![1.0_f64; n];
        group.bench_with_input(BenchmarkId::from_parameter(n), &n, |b, _| {
            b.iter(|| hits_step_core(&indptr, &indices, &data, &authority, &hub, n));
        });
    }
    group.finish();
}

criterion_group!(benches, bench_pagerank, bench_personalized, bench_hits);
criterion_main!(benches);
