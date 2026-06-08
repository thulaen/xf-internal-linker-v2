//! Criterion benchmark for the passage-level `MaxSim` kernel core.
//!
//! Benchmarks the plain-Rust `max_sim_slice` over three passage counts at the
//! production embedding dimension (BGE-M3, dim=1024), matching the Mandatory
//! Benchmark Rule (3 input sizes per hot path) and `RUST-FIRST.md` step 5, and
//! mirroring the shapes of the deleted `bench_passagesim.cpp`.

use criterion::{criterion_group, criterion_main, BenchmarkId, Criterion};
use passagesim::max_sim_slice;

/// Production embedding dimension (BGE-M3).
const DIM: usize = 1024;

/// Three representative passage counts: a short document, a typical document,
/// and a long document at the FR-053 passage cap.
const PASSAGE_COUNTS: [usize; 3] = [10, 100, 200];

fn make_query(dim: usize) -> Vec<f32> {
    // Deterministic non-degenerate query. The `i % 97` stays in 0..96 so the
    // `as f32` cast is exact; the precision-loss lint does not apply.
    #[allow(clippy::cast_precision_loss)]
    (0..dim).map(|i| ((i % 97) as f32) - 48.0 + 0.5).collect()
}

fn make_matrix(num_passages: usize, dim: usize) -> Vec<f32> {
    // Deterministic non-degenerate matrix; the bounded `i % 89` keeps the cast
    // exact and avoids every row being identical.
    #[allow(clippy::cast_precision_loss)]
    (0..num_passages * dim)
        .map(|i| ((i % 89) as f32) - 44.0 + 0.25)
        .collect()
}

fn bench_max_sim(c: &mut Criterion) {
    let mut group = c.benchmark_group("max_sim_slice");
    let query = make_query(DIM);
    for num_passages in PASSAGE_COUNTS {
        let matrix = make_matrix(num_passages, DIM);
        group.bench_with_input(
            BenchmarkId::from_parameter(format!("{num_passages}x{DIM}")),
            &matrix,
            |b, matrix| {
                b.iter(|| max_sim_slice(&query, matrix, num_passages, DIM));
            },
        );
    }
    group.finish();
}

criterion_group!(benches, bench_max_sim);
criterion_main!(benches);
