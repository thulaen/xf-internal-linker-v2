//! Criterion benchmark for the Count-Min Sketch kernel core.
//!
//! Benchmarks the plain-Rust `CountMinSketchCore` add+estimate path over three
//! input sizes (100, 10000, and 100000 updates), matching the Mandatory
//! Benchmark Rule (3 input sizes per hot path), `RUST-FIRST.md` step 5, and the
//! C++ `BM_CountMinSketchAddEstimate` benchmark it replaces (width=16384,
//! depth=5, the same three `Arg` sizes). Each timed iteration builds a fresh
//! sketch, adds `n` items drawn from a 1000-key alphabet (so collisions are
//! exercised), and estimates one key — exactly the shape of the C++ bench.

use count_min_sketch::CountMinSketchCore;
use criterion::{criterion_group, criterion_main, BenchmarkId, Criterion};

/// Table shape used by the replaced C++ benchmark.
const WIDTH: usize = 16_384;
const DEPTH: usize = 5;

/// Update counts: a small burst, a typical stream, and a large stream.
const SIZES: [usize; 3] = [100, 10_000, 100_000];

fn bench_add_estimate(c: &mut Criterion) {
    let mut group = c.benchmark_group("count_min_sketch_add_estimate");
    for n in SIZES {
        group.bench_with_input(BenchmarkId::from_parameter(n), &n, |b, &n| {
            b.iter(|| {
                let mut sketch = CountMinSketchCore::new(WIDTH, DEPTH).unwrap();
                for i in 0..n {
                    sketch.add(&format!("item-{}", i % 1000), 1);
                }
                sketch.estimate("item-17")
            });
        });
    }
    group.finish();
}

criterion_group!(benches, bench_add_estimate);
criterion_main!(benches);
