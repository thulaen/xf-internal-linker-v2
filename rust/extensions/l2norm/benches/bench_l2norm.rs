//! Criterion benchmark for the L2 normalization kernel core.
//!
//! Benchmarks the plain-Rust `normalize_l2_batch_buffer` over three input
//! sizes, matching the Mandatory Benchmark Rule (3 input sizes per hot path)
//! and `RUST-FIRST.md` Pattern step 5. The buffer is reset before each timed
//! iteration so every run normalizes the same un-normalized input rather than
//! re-normalizing an already-unit matrix.

use criterion::{criterion_group, criterion_main, BatchSize, BenchmarkId, Criterion};
use l2norm::normalize_l2_batch_buffer;

/// Three representative embedding-batch shapes: a small slate, a typical
/// embedding flush, and a large flush at the production embedding dimension.
const SHAPES: [(usize, usize); 3] = [(32, 128), (256, 768), (512, 1024)];

fn make_buffer(rows: usize, cols: usize) -> Vec<f32> {
    // Deterministic, non-degenerate values so no row hits the 1e-10 no-op
    // guard — the benchmark measures the real divide path, not the skip path.
    // The `i % 97` stays in 0..96, so the `as f32` cast is exact; the
    // precision-loss lint does not apply to this small bounded range.
    #[allow(clippy::cast_precision_loss)]
    (0..rows * cols)
        .map(|i| ((i % 97) as f32) - 48.0 + 0.5)
        .collect()
}

fn bench_normalize_batch(c: &mut Criterion) {
    let mut group = c.benchmark_group("normalize_l2_batch_buffer");
    for (rows, cols) in SHAPES {
        let seed = make_buffer(rows, cols);
        group.bench_with_input(
            BenchmarkId::from_parameter(format!("{rows}x{cols}")),
            &seed,
            |b, seed| {
                b.iter_batched_ref(
                    || seed.clone(),
                    |buf| normalize_l2_batch_buffer(buf, cols),
                    BatchSize::SmallInput,
                );
            },
        );
    }
    group.finish();
}

criterion_group!(benches, bench_normalize_batch);
criterion_main!(benches);
