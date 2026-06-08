//! Criterion benchmark for the rare-term scoring kernel core.
//!
//! Benchmarks the plain-Rust `evaluate_rare_terms_core` over three input sizes
//! (10 / 100 / 1000 terms), mirroring the deleted C++ `BM_EvaluateRareTerms`
//! `Arg(10)/Arg(100)/Arg(1000)` and the pytest-benchmark sizes, matching the
//! Mandatory Benchmark Rule (3 input sizes) and `RUST-FIRST.md` Pattern step 5.
//! The host set is built so roughly half the terms match, exercising the
//! filter, the sort, and the top-k average.

use std::collections::HashSet;

use criterion::{criterion_group, criterion_main, BenchmarkId, Criterion};
use rareterm::evaluate_rare_terms_core;

/// Three representative term-count sizes.
const SIZES: [usize; 3] = [10, 100, 1000];

/// Build `n` terms, evidences, supporting-page counts, and a host set that
/// contains every even-indexed term (so ~half match). Evidences and page counts
/// vary so the sort does real comparisons.
fn make_inputs(n: usize) -> (Vec<String>, Vec<f64>, Vec<i64>, HashSet<String>) {
    let mut terms = Vec::with_capacity(n);
    let mut evidences = Vec::with_capacity(n);
    let mut pages = Vec::with_capacity(n);
    let mut host: HashSet<String> = HashSet::new();
    for i in 0..n {
        let term = format!("term{i}");
        if i % 2 == 0 {
            host.insert(term.clone());
        }
        // Evidence cycles through a small set of distinct finite values. The
        // modulo keeps the value in 0..17, so the `u32` conversion is exact and
        // never truncates.
        let bucket = u32::try_from(i % 17).expect("i % 17 < 17 fits u32");
        evidences.push(f64::from(bucket) / 17.0);
        pages.push(i64::try_from(i % 7).expect("i % 7 < 7 fits i64"));
        terms.push(term);
    }
    (terms, evidences, pages, host)
}

fn bench_evaluate(c: &mut Criterion) {
    let mut group = c.benchmark_group("evaluate_rare_terms_core");
    for n in SIZES {
        let (terms, evidences, pages, host) = make_inputs(n);
        group.bench_with_input(
            BenchmarkId::from_parameter(n),
            &(terms, evidences, pages, host),
            |b, (terms, evidences, pages, host)| {
                b.iter(|| {
                    evaluate_rare_terms_core(terms, evidences, pages, host, 2)
                        .expect("aligned inputs never error")
                });
            },
        );
    }
    group.finish();
}

criterion_group!(benches, bench_evaluate);
criterion_main!(benches);
