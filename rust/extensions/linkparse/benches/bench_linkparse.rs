//! Criterion benchmark for the linkparse kernel core.
//!
//! Benchmarks the plain-Rust `find_urls_core` parse path over three input sizes
//! (10, 100, and 1000 links), matching the Mandatory Benchmark Rule (3 input
//! sizes per hot path), `RUST-FIRST.md` step 5, and the C++ `bench_linkparse`
//! benchmark it replaces. Each timed iteration parses a synthetic forum body
//! built from `n` mixed `BBCode` / HTML / bare links so all three passes and the
//! overlap-suppression logic are exercised.

use std::fmt::Write as _;

use criterion::{criterion_group, criterion_main, BenchmarkId, Criterion};
use linkparse::find_urls_core;

/// Link counts: a small post, a medium thread, and a large dump.
const SIZES: [usize; 3] = [10, 100, 1000];

/// Build a synthetic body with `n` links, cycling through the three extraction
/// methods so every pass and the overlap rule are exercised.
fn build_body(n: usize) -> String {
    let mut body = String::new();
    for i in 0..n {
        // `write!` to a String never fails; the unwrap documents that.
        match i % 3 {
            0 => write!(
                body,
                "[url=https://example.com/threads/topic.{i}]Anchor {i}[/url] "
            )
            .unwrap(),
            1 => write!(
                body,
                "<a href=\"https://example.com/resources/tool.{i}\">Tool {i}</a> "
            )
            .unwrap(),
            _ => write!(body, "see https://example.com/posts/p{i} here ").unwrap(),
        }
    }
    body
}

fn bench_find_urls(c: &mut Criterion) {
    let mut group = c.benchmark_group("linkparse_find_urls");
    for n in SIZES {
        let body = build_body(n);
        group.bench_with_input(BenchmarkId::from_parameter(n), &body, |b, body| {
            b.iter(|| find_urls_core(body));
        });
    }
    group.finish();
}

criterion_group!(benches, bench_find_urls);
criterion_main!(benches);
