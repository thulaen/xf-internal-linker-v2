//! Criterion benchmark for the lesson_index kernel cores.
//!
//! Benchmarks the two hot cores over three input sizes, matching the Mandatory
//! Benchmark Rule (3 input sizes per hot path), `RUST-FIRST.md` step 5, and the
//! deleted C++ `bench_lesson_index.cpp`:
//!
//! - `ScopedLessonCore::find_by_path` — the prefix-match + sort hot path.
//! - `PerfBaselineCore::get` — the cache lookup hot path.
//!
//! The `as u8`/`as u64`/`as i64` casts on the synthetic loop index are bounded
//! by the benchmark sizes (well under each type's range), so the conversions are
//! exact; the truncation/wrap lints are allowed for this bench-only data setup.
#![allow(
    clippy::cast_possible_truncation,
    clippy::cast_possible_wrap,
    clippy::doc_markdown
)]

use criterion::{criterion_group, criterion_main, BenchmarkId, Criterion};
use lesson_index::{BaselineRecord, LessonRecord, PerfBaselineCore, ScopedLessonCore};

/// Stored-entry counts: small, medium, and large indices.
const SIZES: [usize; 3] = [100, 10_000, 100_000];

fn bench_scoped_find(c: &mut Criterion) {
    let mut group = c.benchmark_group("lesson_index_find_by_path");
    for n in SIZES {
        let mut idx = ScopedLessonCore::new(n + 1);
        for i in 0..n {
            let rec = LessonRecord {
                autoissue_id: i as u64,
                lesson_hash: i as u64,
                severity: (i % 4) as u8,
                resolved_at_unix: i as i64,
            };
            idx.add(&format!("apps/mod-{}/path", i % 32), rec);
        }
        group.bench_with_input(BenchmarkId::from_parameter(n), &n, |b, _| {
            b.iter(|| idx.find_by_path("apps/mod-7", 5));
        });
    }
    group.finish();
}

fn bench_perf_get(c: &mut Criterion) {
    let mut group = c.benchmark_group("lesson_index_perf_get");
    for n in SIZES {
        let mut cache = PerfBaselineCore::new(n + 1);
        for i in 0..n {
            cache.put(&format!("fn-{i}"), BaselineRecord::default());
        }
        let probe = format!("fn-{}", n / 2);
        group.bench_with_input(BenchmarkId::from_parameter(n), &n, |b, _| {
            b.iter(|| cache.get(&probe));
        });
    }
    group.finish();
}

criterion_group!(benches, bench_scoped_find, bench_perf_get);
criterion_main!(benches);
