//! Criterion benchmark for the paper-trail `MinHash` + LSH dedup core.
//!
//! Benchmarks the plain-Rust `DedupIndexCore` build + `find_similar` path over
//! three index sizes (1K, 10K, 100K entries), matching the Mandatory Benchmark
//! Rule (3 input sizes per hot path), `RUST-FIRST.md` step 5, and the C++
//! `bench_papertrail_dedup.cpp` it replaces. Each timed iteration builds an
//! index of `n` distinct abstracts, then runs one `find_similar` query — the
//! shape that drives the paper-trail dedup gate.

use criterion::{criterion_group, criterion_main, BenchmarkId, Criterion};
use papertrail_dedup::DedupIndexCore;

/// Index sizes: small, medium, and the 100K capacity cap.
const SIZES: [usize; 3] = [1_000, 10_000, 100_000];

fn build_index(n: usize) -> DedupIndexCore {
    let mut idx = DedupIndexCore::new(100_000, 42).unwrap();
    for i in 0..n {
        idx.add_entry(
            i as u64,
            &format!("paper-trail abstract number {i} with enough text to shingle properly"),
        );
    }
    idx
}

fn bench_find_similar(c: &mut Criterion) {
    let mut group = c.benchmark_group("papertrail_dedup_find_similar");
    for n in SIZES {
        let idx = build_index(n);
        let query = format!(
            "paper-trail abstract number {} with enough text to shingle properly",
            n / 2
        );
        group.bench_with_input(BenchmarkId::from_parameter(n), &n, |b, _| {
            b.iter(|| idx.find_similar(&query, 0.85));
        });
    }
    group.finish();
}

criterion_group!(benches, bench_find_similar);
criterion_main!(benches);
