//! Criterion benchmark for the anchor-diversity kernel core.
//!
//! Benchmarks the plain-Rust `evaluate_anchor_diversity_core` over three input
//! sizes (100, 1000, 5000 candidates), matching the Mandatory Benchmark Rule
//! (3 input sizes per hot path) and `RUST-FIRST.md` step 5. Each timed
//! iteration scores a batch whose rows cover the neutral, share-penalty, and
//! count-penalty branches so the full straight-line arithmetic is exercised.

use anchor_diversity::evaluate_anchor_diversity_core;
use criterion::{criterion_group, criterion_main, BenchmarkId, Criterion};

/// Candidate-batch sizes: a small slate, a typical batch, and a large flush.
const SIZES: [usize; 3] = [100, 1000, 5000];

/// FR-045 default settings.
const MIN_HISTORY: i32 = 5;
const MAX_SHARE: f64 = 0.3;
const MAX_COUNT: i32 = 3;

/// Build two parallel int32 columns whose rows cycle through every state
/// branch so the benchmark does representative work.
fn columns(n: usize) -> (Vec<i32>, Vec<i32>) {
    let mut active = Vec::with_capacity(n);
    let mut before = Vec::with_capacity(n);
    for i in 0..n {
        match i % 4 {
            0 => {
                active.push(1);
                before.push(0);
            } // neutral_no_history
            1 => {
                active.push(10);
                before.push(0);
            } // neutral_below_threshold
            2 => {
                active.push(5);
                before.push(1);
            } // penalized_exact_share
            _ => {
                active.push(20);
                before.push(3);
            } // blocked_exact_count
        }
    }
    (active, before)
}

fn bench_evaluate(c: &mut Criterion) {
    let mut group = c.benchmark_group("anchor_diversity_evaluate");
    for n in SIZES {
        let (active, before) = columns(n);
        group.bench_with_input(
            BenchmarkId::from_parameter(n),
            &(active, before),
            |b, (active, before)| {
                b.iter(|| {
                    evaluate_anchor_diversity_core(
                        active,
                        before,
                        MIN_HISTORY,
                        MAX_SHARE,
                        MAX_COUNT,
                        true,
                    )
                });
            },
        );
    }
    group.finish();
}

criterion_group!(benches, bench_evaluate);
criterion_main!(benches);
