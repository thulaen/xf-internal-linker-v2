//! Criterion benchmark for the token-bucket rate limiter kernel core.
//!
//! Benchmarks the plain-Rust `RateLimiterRegistryCore` register + `try_acquire`
//! path over three input sizes (100, 10000, and 100000 acquire attempts),
//! matching the Mandatory Benchmark Rule (3 input sizes per hot path),
//! `RUST-FIRST.md` step 5, and the C++ `bench_api_rate_limiter.cpp` it replaces.
//! Each timed iteration registers one bucket and runs `n` `try_acquire` calls.

use api_rate_limiter::RateLimiterRegistryCore;
use criterion::{criterion_group, criterion_main, BenchmarkId, Criterion};

/// Acquire counts: a small burst, a typical stream, and a large stream.
const SIZES: [usize; 3] = [100, 10_000, 100_000];

fn bench_try_acquire(c: &mut Criterion) {
    let mut group = c.benchmark_group("api_rate_limiter_try_acquire");
    for n in SIZES {
        group.bench_with_input(BenchmarkId::from_parameter(n), &n, |b, &n| {
            b.iter(|| {
                let mut reg = RateLimiterRegistryCore::new();
                // Large capacity + fast rate so most acquires succeed and the
                // refill math runs on every call (the hot path).
                reg.register_bucket("api", 1_000_000.0, 1_000_000.0, -1)
                    .unwrap();
                let mut ok = 0_u64;
                for _ in 0..n {
                    if reg.try_acquire("api", 1.0).unwrap_or(false) {
                        ok += 1;
                    }
                }
                ok
            });
        });
    }
    group.finish();
}

criterion_group!(benches, bench_try_acquire);
criterion_main!(benches);
