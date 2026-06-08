//! Criterion benchmark for the BM25F field-relevance kernel core.
//!
//! Benchmarks the plain-Rust `score_field_tokens_core` over three input sizes
//! (5, 20, and 100 matched tokens), mirroring the deleted C++
//! `BM_ScoreFieldTokens` (`Arg(5)`/`Arg(20)`/`Arg(100)`), the Mandatory
//! Benchmark Rule (3 input sizes per hot path), and `RUST-FIRST.md` step 5.
//! Each timed iteration scores a freshly built synthetic token field.

use criterion::{criterion_group, criterion_main, BenchmarkId, Criterion};
use fieldrel::score_field_tokens_core;

/// Matched-token counts matching the replaced C++ benchmark's `Arg` sizes.
const SIZES: [usize; 3] = [5, 20, 100];

fn bench_score_field_tokens(c: &mut Criterion) {
    let mut group = c.benchmark_group("fieldrel_score_field_tokens");
    for n in SIZES {
        let tokens: Vec<String> = (0..n).map(|i| format!("token-{i}")).collect();
        let host_tfs: Vec<i32> = (0..n).map(|i| i32::try_from(i % 4 + 1).unwrap()).collect();
        let field_tfs: Vec<i32> = (0..n).map(|i| i32::try_from(i % 7 + 1).unwrap()).collect();
        let presence: Vec<i32> = (0..n).map(|i| i32::try_from(i % 6 + 1).unwrap()).collect();
        group.bench_with_input(BenchmarkId::from_parameter(n), &n, |b, _| {
            b.iter(|| {
                score_field_tokens_core(
                    &tokens, &host_tfs, &field_tfs, &presence, 120, 100.0, 0.75, 6, 1.2, 5,
                )
                .unwrap()
            });
        });
    }
    group.finish();
}

criterion_group!(benches, bench_score_field_tokens);
criterion_main!(benches);
