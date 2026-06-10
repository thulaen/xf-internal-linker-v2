//! Criterion benchmark for the IVF + OPQ ADC kernel core.
//!
//! Benchmarks the plain-Rust `adc_score_destination_core` (the per-destination
//! hot path that the production caller `passage_relevance.score()` invokes)
//! over three input sizes, matching the Mandatory Benchmark Rule (3 input sizes
//! per hot path) and `RUST-FIRST.md` step 5. Each size varies the passage count
//! at the production OPQ geometry (dim 1024, m 8, k 256).

use criterion::{criterion_group, criterion_main, BenchmarkId, Criterion};
use ivf_index::adc_score_destination_core;

/// Production OPQ geometry: 1024-dim embeddings, 8 sub-quantisers, 256 codes.
const DIM: usize = 1024;
const M: usize = 8;
const K: usize = 256;

/// Three representative per-destination passage counts: a tiny destination, a
/// typical one, and a large one.
const PASSAGE_COUNTS: [usize; 3] = [8, 64, 256];

fn make_query() -> Vec<f32> {
    // Deterministic non-degenerate values; the small bounded range keeps the
    // `as f32` cast exact, so the precision-loss lint does not apply.
    #[allow(clippy::cast_precision_loss)]
    (0..DIM).map(|i| ((i % 97) as f32) - 48.0).collect()
}

fn make_rotation() -> Vec<f32> {
    // Identity rotation: a real OPQ rotation is dense, but identity keeps the
    // benchmark focused on the ADC scan (the production hot path), and the LUT
    // build runs the full dim*dim rotation loop regardless of the values.
    let mut r = vec![0.0_f32; DIM * DIM];
    for d in 0..DIM {
        r[d * DIM + d] = 1.0;
    }
    r
}

fn make_codebooks() -> Vec<f32> {
    let sub_dim = DIM / M;
    #[allow(clippy::cast_precision_loss)]
    (0..M * K * sub_dim)
        .map(|i| ((i % 101) as f32) - 50.0)
        .collect()
}

#[allow(clippy::cast_possible_truncation)]
fn make_codes(n_passages: usize) -> Vec<u8> {
    (0..n_passages * M).map(|i| (i % K) as u8).collect()
}

fn bench_adc_score(c: &mut Criterion) {
    let query = make_query();
    let rotation = make_rotation();
    let codebooks = make_codebooks();
    let mut group = c.benchmark_group("adc_score_destination_core");
    for n_passages in PASSAGE_COUNTS {
        let codes = make_codes(n_passages);
        group.bench_with_input(
            BenchmarkId::from_parameter(n_passages),
            &n_passages,
            |b, &n_passages| {
                b.iter(|| {
                    adc_score_destination_core(
                        &query, &codes, &rotation, &codebooks, DIM, n_passages, M, K,
                    )
                });
            },
        );
    }
    group.finish();
}

criterion_group!(benches, bench_adc_score);
criterion_main!(benches);
