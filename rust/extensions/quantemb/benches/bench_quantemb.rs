//! Criterion benchmark for the OPQ encode kernel core.
//!
//! Benchmarks the plain-Rust `opq_encode_core` over three input sizes (vector
//! counts) at a representative dim/m/k, matching the Mandatory Benchmark Rule
//! (3 input sizes per hot path) and `RUST-FIRST.md` step 5, and mirroring the
//! shapes of the deleted `bench_quantemb.cpp`.

use criterion::{criterion_group, criterion_main, BenchmarkId, Criterion};
use quantemb::{opq_encode_core, opq_train_core};

/// Representative OPQ shape: dim 128 split into m=8 subquantisers of `sub_dim`
/// 16, k=16 centroids each.
const DIM: usize = 128;
const M: usize = 8;
const K: usize = 16;

/// Three representative encode batch sizes.
const VECTOR_COUNTS: [usize; 3] = [64, 256, 1024];

fn make_vectors(num_vectors: usize, dim: usize) -> Vec<f32> {
    // Deterministic non-degenerate values; the bounded `i % 97` keeps the
    // `as f32` cast exact and the vectors distinct.
    #[allow(clippy::cast_precision_loss)]
    (0..num_vectors * dim)
        .map(|i| ((i % 97) as f32) - 48.0 + 0.5)
        .collect()
}

fn bench_opq_encode(c: &mut Criterion) {
    let mut group = c.benchmark_group("opq_encode_core");
    // Train one codebook set up front (training is not the benchmarked path).
    let train_vectors = make_vectors(256, DIM);
    let (rotation, codebooks) = opq_train_core(&train_vectors, 256, DIM, M, K, 5);

    for num_vectors in VECTOR_COUNTS {
        let vectors = make_vectors(num_vectors, DIM);
        group.bench_with_input(
            BenchmarkId::from_parameter(format!("{num_vectors}x{DIM}")),
            &vectors,
            |b, vectors| {
                b.iter(|| opq_encode_core(vectors, num_vectors, DIM, &rotation, &codebooks, M, K));
            },
        );
    }
    group.finish();
}

criterion_group!(benches, bench_opq_encode);
criterion_main!(benches);
