//! Criterion benchmark for the compressed Bloom filter kernel core.
//!
//! Benchmarks the plain-Rust `CompressedBloomFilterCore` add+contains path over
//! three input sizes (100, 10000, and 100000 inserts), matching the Mandatory
//! Benchmark Rule (3 input sizes per hot path), `RUST-FIRST.md` step 5, and the
//! C++ `BM_CompressedBloomAddContains` benchmark it replaces (1<<20 bits,
//! 4 hashes, the same three `Arg` sizes). Each timed iteration builds a fresh
//! filter, adds `n` synthetic items `item-0`..`item-{n-1}`, and probes one key
//! — exactly the shape of the C++ bench.

use compressed_bloom::CompressedBloomFilterCore;
use criterion::{criterion_group, criterion_main, BenchmarkId, Criterion};

/// Table shape used by the replaced C++ benchmark.
const BIT_COUNT: usize = 1 << 20;
const HASHES: usize = 4;

/// Insert counts: a small burst, a typical stream, and a large stream.
const SIZES: [usize; 3] = [100, 10_000, 100_000];

fn bench_add_contains(c: &mut Criterion) {
    let mut group = c.benchmark_group("compressed_bloom_add_contains");
    for n in SIZES {
        group.bench_with_input(BenchmarkId::from_parameter(n), &n, |b, &n| {
            b.iter(|| {
                let mut filter = CompressedBloomFilterCore::new(BIT_COUNT, HASHES).unwrap();
                for i in 0..n {
                    filter.add(&format!("item-{i}"));
                }
                filter.contains("item-17")
            });
        });
    }
    group.finish();
}

criterion_group!(benches, bench_add_contains);
criterion_main!(benches);
