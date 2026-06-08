//! Criterion benchmark for the anchor self-information kernel core.
//!
//! Benchmarks the plain-Rust `bigram_entropy_bytes` path over three input
//! sizes (20, 120, and 800 bytes), matching the Mandatory Benchmark Rule (3
//! input sizes per hot path), `RUST-FIRST.md` step 5, and the C++
//! `BM_BigramEntropy` benchmark it replaces
//! (`BENCHMARK(BM_BigramEntropy)->Arg(20)->Arg(120)->Arg(800)`). Each timed
//! iteration computes the byte-bigram entropy of a pseudo-text string of the
//! given length — exactly the shape of the C++ bench.

use anchor_self_information::bigram_entropy_bytes;
use criterion::{criterion_group, criterion_main, BenchmarkId, Criterion};

/// Input lengths in bytes: a short anchor, a sentence, and a long anchor —
/// the same three `Arg` sizes the replaced C++ benchmark used.
const SIZES: [usize; 3] = [20, 120, 800];

/// Build a deterministic pseudo-text of `len` bytes with a realistic spread of
/// repeated bigrams (a 26-letter cycle, so the bigram distribution is varied
/// but not uniform — close to natural-language anchor text).
fn make_text(len: usize) -> Vec<u8> {
    (0..len)
        .map(|i| b'a' + u8::try_from(i % 26).unwrap())
        .collect()
}

fn bench_bigram_entropy(c: &mut Criterion) {
    let mut group = c.benchmark_group("anchor_self_information_bigram_entropy");
    for len in SIZES {
        let text = make_text(len);
        group.bench_with_input(BenchmarkId::from_parameter(len), &text, |b, text| {
            b.iter(|| bigram_entropy_bytes(text));
        });
    }
    group.finish();
}

criterion_group!(benches, bench_bigram_entropy);
criterion_main!(benches);
