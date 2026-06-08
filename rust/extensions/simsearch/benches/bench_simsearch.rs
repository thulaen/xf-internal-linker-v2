//! Criterion benchmark for the sentence-search kernel core.
//!
//! Benchmarks the plain-Rust `score_and_topk_core` over three input sizes,
//! matching the Mandatory Benchmark Rule (3 input sizes per hot path) and
//! `RUST-FIRST.md` Pattern step 5. Each timed iteration scores the full
//! candidate list against a fixed query and selects the top-k.

use criterion::{criterion_group, criterion_main, BenchmarkId, Criterion};
use simsearch::score_and_topk_core;

/// Three representative shapes: `(num_sentences, dim, num_candidates, top_k)`.
/// Small slate, a typical Stage-2 batch, and a large candidate pool, all at
/// embedding-like dimensions.
const SHAPES: [(usize, usize, usize, usize); 3] = [
    (64, 128, 32, 5),
    (1024, 384, 256, 10),
    (8192, 768, 2048, 20),
];

fn make_destination(dim: usize) -> Vec<f32> {
    #[allow(clippy::cast_precision_loss)]
    (0..dim).map(|d| ((d % 97) as f32) - 48.0 + 0.5).collect()
}

fn make_sentences(rows: usize, cols: usize) -> Vec<f32> {
    #[allow(clippy::cast_precision_loss)]
    (0..rows * cols)
        .map(|i| ((i % 97) as f32) - 48.0 + 0.25)
        .collect()
}

fn make_candidates(num_sentences: usize, num_candidates: usize) -> Vec<i32> {
    // Spread candidate rows across the sentence range deterministically.
    #[allow(clippy::cast_possible_truncation, clippy::cast_possible_wrap)]
    (0..num_candidates)
        .map(|i| ((i * 7) % num_sentences) as i32)
        .collect()
}

fn bench_score_and_topk(c: &mut Criterion) {
    let mut group = c.benchmark_group("score_and_topk_core");
    for (num_sentences, dim, num_candidates, top_k) in SHAPES {
        let dest = make_destination(dim);
        let sentences = make_sentences(num_sentences, dim);
        let candidates = make_candidates(num_sentences, num_candidates);
        group.bench_with_input(
            BenchmarkId::from_parameter(format!(
                "{num_sentences}x{dim}_c{num_candidates}_k{top_k}"
            )),
            &(dest, sentences, candidates),
            |b, (dest, sentences, candidates)| {
                b.iter(|| {
                    score_and_topk_core(dest, sentences, dim, num_sentences, candidates, top_k)
                });
            },
        );
    }
    group.finish();
}

criterion_group!(benches, bench_score_and_topk);
criterion_main!(benches);
