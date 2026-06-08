# api_rate_limiter

FR-250 token-bucket rate limiter hot-path kernel, ported from C++ to Rust and
exposed to Python as `extensions.api_rate_limiter` via [PyO3](https://pyo3.rs) +
[maturin](https://www.maturin.rs). It throttles outbound analytics API calls
(Google Search Console, GA4, Matomo, XenForo, WordPress) so the app never trips
a provider rate limit.

The algorithm is a classic token bucket (Turner 1986, "New directions in
communications", IEEE Communications): each named bucket holds `tokens` that
refill continuously at `rate_per_sec`, capped at `capacity` (the burst size).
`try_acquire` removes tokens if enough are available; `wait_seconds` reports how
long to wait otherwise. An optional per-bucket daily call quota resets at the
next UTC midnight.

The crate ships as `api_rate_limiter.so` (the `cdylib`) and is imported from
Python as `extensions.api_rate_limiter`. The plain-Rust core
(`RateLimiterRegistryCore`) is also exposed as an `rlib` so `cargo test` and the
Criterion benchmark can exercise it without crossing the Python boundary.

Part of the Python → Rust hot-path migration. See
`docs/PYTHON-RUST-MIGRATION-PLAN.md` and `RUST-FIRST.md`.
