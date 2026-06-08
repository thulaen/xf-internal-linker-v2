//! Criterion benchmark for the longest-contiguous-overlap kernel core.
//!
//! Benchmarks the plain-Rust `longest_contiguous_overlap_core` over three input
//! sizes, matching the Mandatory Benchmark Rule (3 input sizes per hot path)
//! and `RUST-FIRST.md` Pattern step 5. Each input is a pair of token lists that
//! share a contiguous run in the middle, so the inner extend-loop does real
//! work rather than bailing on the first token.

use criterion::{criterion_group, criterion_main, BenchmarkId, Criterion};
use phrasematch::longest_contiguous_overlap_core;

/// Three representative token-list lengths: a short anchor phrase, a typical
/// sentence span, and an over-long span at the upper end of what the caller
/// ever passes. The kernel is `O(n*m*min(n,m))` so even the large case is tiny.
const SIZES: [usize; 3] = [8, 24, 48];

/// Build two `len`-token lists that share a contiguous run of `len / 2` tokens
/// starting a quarter of the way in, with distinct surrounding tokens so the
/// match is exactly the shared middle run.
fn make_pair(len: usize) -> (Vec<String>, Vec<String>) {
    let run_start = len / 4;
    let run_len = len / 2;
    let mut left = Vec::with_capacity(len);
    let mut right = Vec::with_capacity(len);
    for i in 0..len {
        if i >= run_start && i < run_start + run_len {
            // Shared run: identical tokens in both lists at the same offset.
            left.push(format!("shared{i}"));
            right.push(format!("shared{i}"));
        } else {
            // Distinct surrounding tokens so they never match.
            left.push(format!("l{i}"));
            right.push(format!("r{i}"));
        }
    }
    (left, right)
}

fn bench_overlap(c: &mut Criterion) {
    let mut group = c.benchmark_group("longest_contiguous_overlap_core");
    for len in SIZES {
        let (left, right) = make_pair(len);
        group.bench_with_input(
            BenchmarkId::from_parameter(format!("{len}x{len}")),
            &(left, right),
            |b, (left, right)| {
                b.iter(|| longest_contiguous_overlap_core(left, right));
            },
        );
    }
    group.finish();
}

criterion_group!(benches, bench_overlap);
criterion_main!(benches);
