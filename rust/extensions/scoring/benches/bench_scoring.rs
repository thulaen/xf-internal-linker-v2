//! Criterion benchmark for the composite-scoring kernel core.
//!
//! Benchmarks the plain-Rust `score_full_batch_core` over three input sizes,
//! matching the Mandatory Benchmark Rule (3 input sizes per hot path),
//! `RUST-FIRST.md` step 5, and the deleted C++ `BM_ScoreFullBatch`
//! `Arg(100)/Arg(10000)/Arg(100000)`. Each timed iteration scores every row of
//! a synthetic component matrix (8 components per row), exercising the per-row
//! silo seed plus the dot-product inner loop.
//!
//! The `i % 97` synthetic values stay in `0..96`, so the `as f32` casts are
//! exact for these bounded inputs.
#![allow(clippy::cast_precision_loss)]

use criterion::{criterion_group, criterion_main, BenchmarkId, Criterion};
use scoring::score_full_batch_core;

/// Row counts mirroring the deleted C++ benchmark args.
const ROW_COUNTS: [usize; 3] = [100, 10_000, 100_000];
/// Components per row (matches the typical per-signal component vector width).
const NUM_COMPONENTS: usize = 8;

fn make_components(rows: usize) -> Vec<f32> {
    (0..rows * NUM_COMPONENTS)
        .map(|i| ((i % 97) as f32).mul_add(0.01, -0.48))
        .collect()
}

fn bench_score(c: &mut Criterion) {
    let weights: Vec<f32> = (0..NUM_COMPONENTS)
        .map(|j| (j as f32).mul_add(0.1, 0.05))
        .collect();
    let mut group = c.benchmark_group("score_full_batch_core");
    for rows in ROW_COUNTS {
        let comp = make_components(rows);
        let silo: Vec<f32> = (0..rows).map(|i| (i % 13) as f32 * 0.001).collect();
        group.bench_with_input(BenchmarkId::from_parameter(rows), &rows, |b, &rows| {
            b.iter(|| score_full_batch_core(&comp, rows, NUM_COMPONENTS, &weights, &silo));
        });
    }
    group.finish();
}

criterion_group!(benches, bench_score);
criterion_main!(benches);
