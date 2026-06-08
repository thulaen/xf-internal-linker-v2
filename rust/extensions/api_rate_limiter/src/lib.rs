//! FR-250 token-bucket rate limiter hot-path kernel, ported from the C++
//! `api_rate_limiter` kernel (`backend/extensions/api_rate_limiter.cpp`) to Rust
//! and exposed to Python as the native module `extensions.api_rate_limiter` via
//! `PyO3`.
//!
//! A token bucket (Turner 1986, "New directions in communications", IEEE
//! Communications) holds `tokens` that refill continuously at `rate_per_sec`,
//! capped at `capacity` (the burst size). `try_acquire` removes `cost` tokens
//! when enough are available; `wait_seconds` reports the wait otherwise. An
//! optional per-bucket daily call quota (`daily_quota`, `-1` = disabled) is an
//! integer counter decremented once per successful `try_acquire`; it resets at
//! the next UTC midnight.
//!
//! ## Parity basis (port note)
//!
//! Parity is the BEHAVIOURAL CONTRACT, not byte equality. Outputs depend on a
//! monotonic clock and wall-clock-to-midnight arithmetic, so token counts and
//! `wait_seconds` are inherently time-dependent and non-reproducible across
//! runs. No production caller reads exact float token values — all use goes
//! through the `rate_limited(name)` context manager in
//! `backend/apps/sources/api_rate_limiter.py`, which only branches on the
//! `try_acquire` bool and a `wait_seconds` sleep. So this port reproduces the
//! token-bucket math and the exception/return-type contract; the existing
//! parity tests in `backend/apps/sources/test_api_rate_limiter.py` are the
//! acceptance gate.
//!
//! ## Clock model (port note)
//!
//! The C++ kernel used `steady_clock` (monotonic) for refill and computed the
//! UTC-midnight threshold by offsetting `now_mono` by the wall-clock
//! seconds-until-midnight, because the monotonic and system clocks are
//! independent. This port does the same: refill uses [`std::time::Instant`]
//! (monotonic) and the daily-reset instant is `now_instant + seconds_until_utc_midnight`.
//! Seconds-into-the-UTC-day come from the UNIX epoch, which is aligned to UTC
//! midnight, so `epoch_secs.rem_euclid(86_400)` is the seconds-into-day with no
//! timezone library needed.

use std::collections::HashMap;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

use pyo3::exceptions::{PyKeyError, PyValueError};
use pyo3::prelude::*;

/// Seconds in one day. The daily quota resets at the next UTC midnight.
const SECONDS_PER_DAY: u64 = 86_400;

/// Seconds remaining until the next UTC midnight, measured from the system
/// wall clock.
///
/// The UNIX epoch (1970-01-01T00:00:00Z) falls exactly on a UTC midnight, so
/// `epoch_secs % 86_400` is the number of seconds elapsed since the most recent
/// UTC midnight, and `86_400 - that` is the seconds until the next one. This
/// avoids pulling in a calendar/timezone crate. A clock set before the epoch
/// (`SystemTime` earlier than `UNIX_EPOCH`) is treated as a full day remaining,
/// which is a safe over-estimate that only delays a reset.
fn seconds_until_utc_midnight() -> u64 {
    let epoch_secs = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_or(0, |d| d.as_secs());
    let secs_today = epoch_secs % SECONDS_PER_DAY;
    SECONDS_PER_DAY - secs_today
}

/// One named token bucket. All state is plain values; the registry owns
/// synchronisation, so this struct itself needs no lock (mirroring the C++
/// `Bucket` fields without the per-bucket mutex — the Rust core takes a single
/// `&mut self` lock at the registry level).
struct Bucket {
    /// Current available tokens.
    tokens: f64,
    /// Monotonic instant of the last refill.
    last_refill: Instant,
    /// Maximum tokens (burst ceiling).
    capacity: f64,
    /// Refill rate in tokens per second.
    rate_per_sec: f64,
    /// Remaining daily quota; `-1` means disabled and is never decremented.
    daily_remaining: i64,
    /// Initial quota value, restored at each daily reset.
    daily_quota: i64,
    /// Monotonic instant at which the daily counter next resets.
    daily_reset: Instant,
}

impl Bucket {
    /// Build a fresh bucket whose tokens start full, anchored at `now`.
    fn new(now: Instant, capacity: f64, rate_per_sec: f64, daily_quota: i64) -> Self {
        Self {
            tokens: capacity,
            last_refill: now,
            capacity,
            rate_per_sec,
            daily_remaining: daily_quota,
            daily_quota,
            daily_reset: now + Duration::from_secs(seconds_until_utc_midnight()),
        }
    }

    /// Reset this bucket to its initial config in place, anchored at `now`.
    fn reset(&mut self, now: Instant) {
        self.tokens = self.capacity;
        self.last_refill = now;
        self.daily_remaining = self.daily_quota;
        self.daily_reset = now + Duration::from_secs(seconds_until_utc_midnight());
    }

    /// Advance `tokens` for the time elapsed since `last_refill` and roll the
    /// daily counter over if its reset instant has passed.
    ///
    /// Refill is `min(capacity, tokens + elapsed_seconds * rate_per_sec)` using
    /// the monotonic clock, so tokens never exceed `capacity` and grow linearly
    /// with elapsed time (Turner 1986).
    fn refill(&mut self, now: Instant) {
        if now >= self.daily_reset {
            self.daily_remaining = self.daily_quota;
            self.daily_reset = now + Duration::from_secs(seconds_until_utc_midnight());
        }
        if now <= self.last_refill {
            return;
        }
        let elapsed_s = (now - self.last_refill).as_secs_f64();
        let refill = elapsed_s * self.rate_per_sec;
        self.tokens = self.capacity.min(self.tokens + refill);
        self.last_refill = now;
    }
}

/// Plain-Rust token-bucket registry core (no `PyO3`). Holds a `name -> Bucket`
/// map. All logic lives here so it is unit-testable with `cargo test` without
/// crossing the Python boundary.
#[derive(Default)]
pub struct RateLimiterRegistryCore {
    buckets: HashMap<String, Bucket>,
}

/// Error returned by the core, mapped to a Python exception by the wrapper.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RateLimiterError {
    /// A positivity guard failed (`ValueError` in Python).
    BadValue(&'static str),
    /// The named bucket was never registered (`KeyError` in Python).
    NotRegistered,
}

impl RateLimiterRegistryCore {
    /// Build an empty registry.
    #[must_use]
    pub fn new() -> Self {
        Self::default()
    }

    /// Register or REPLACE a bucket. Replacing resets tokens to `capacity`
    /// (not carried over) and re-anchors the refill and daily-reset clocks.
    ///
    /// # Errors
    ///
    /// Returns [`RateLimiterError::BadValue`] when `capacity <= 0.0` or
    /// `rate_per_sec <= 0.0`.
    pub fn register_bucket(
        &mut self,
        name: &str,
        capacity: f64,
        rate_per_sec: f64,
        daily_quota: i64,
    ) -> Result<(), RateLimiterError> {
        if capacity <= 0.0 || rate_per_sec <= 0.0 {
            return Err(RateLimiterError::BadValue(
                "capacity and rate must be positive",
            ));
        }
        let now = Instant::now();
        self.buckets.insert(
            name.to_owned(),
            Bucket::new(now, capacity, rate_per_sec, daily_quota),
        );
        Ok(())
    }

    /// Mutable lookup that errors (never auto-creates) for an unknown name,
    /// matching the C++ `locate` which throws `std::out_of_range`.
    fn locate_mut(&mut self, name: &str) -> Result<&mut Bucket, RateLimiterError> {
        self.buckets
            .get_mut(name)
            .ok_or(RateLimiterError::NotRegistered)
    }

    /// Remove `cost` tokens immediately if available. Returns `true` on success.
    ///
    /// Refills first, then: if the daily quota is exhausted (`== 0`) returns
    /// `false`; if `tokens < cost` returns `false`; else decrements tokens by
    /// `cost`, decrements `daily_remaining` when it is `> 0`, and returns `true`.
    ///
    /// # Errors
    ///
    /// [`RateLimiterError::BadValue`] when `cost <= 0.0`;
    /// [`RateLimiterError::NotRegistered`] when `name` is unknown.
    pub fn try_acquire(&mut self, name: &str, cost: f64) -> Result<bool, RateLimiterError> {
        if cost <= 0.0 {
            return Err(RateLimiterError::BadValue("cost must be > 0"));
        }
        let bucket = self.locate_mut(name)?;
        bucket.refill(Instant::now());
        if bucket.daily_remaining == 0 {
            return Ok(false);
        }
        if bucket.tokens < cost {
            return Ok(false);
        }
        bucket.tokens -= cost;
        if bucket.daily_remaining > 0 {
            bucket.daily_remaining -= 1;
        }
        Ok(true)
    }

    /// Seconds until `cost` tokens can be acquired. `0.0` means available now.
    ///
    /// Refills first. If the daily quota is exhausted, returns seconds until the
    /// daily reset. Else if enough tokens exist returns `0.0`, otherwise returns
    /// `(cost - tokens) / rate_per_sec`.
    ///
    /// # Errors
    ///
    /// [`RateLimiterError::BadValue`] when `cost <= 0.0`;
    /// [`RateLimiterError::NotRegistered`] when `name` is unknown.
    pub fn wait_seconds(&mut self, name: &str, cost: f64) -> Result<f64, RateLimiterError> {
        if cost <= 0.0 {
            return Err(RateLimiterError::BadValue("cost must be > 0"));
        }
        let now = Instant::now();
        let bucket = self.locate_mut(name)?;
        bucket.refill(now);
        if bucket.daily_remaining == 0 {
            let until = if bucket.daily_reset > now {
                (bucket.daily_reset - now).as_secs_f64()
            } else {
                0.0
            };
            return Ok(until);
        }
        if bucket.tokens >= cost {
            return Ok(0.0);
        }
        Ok((cost - bucket.tokens) / bucket.rate_per_sec)
    }

    /// Refill and return the current token count.
    ///
    /// # Errors
    ///
    /// [`RateLimiterError::NotRegistered`] when `name` is unknown.
    pub fn available(&mut self, name: &str) -> Result<f64, RateLimiterError> {
        let bucket = self.locate_mut(name)?;
        bucket.refill(Instant::now());
        Ok(bucket.tokens)
    }

    /// Refill (which performs the daily rollover) and return the remaining
    /// daily quota (`-1` when disabled).
    ///
    /// # Errors
    ///
    /// [`RateLimiterError::NotRegistered`] when `name` is unknown.
    pub fn daily_remaining(&mut self, name: &str) -> Result<i64, RateLimiterError> {
        let bucket = self.locate_mut(name)?;
        bucket.refill(Instant::now());
        Ok(bucket.daily_remaining)
    }

    /// Test-only: reset every registered bucket to its initial config in place.
    /// Does NOT forget buckets.
    pub fn reset_all(&mut self) {
        let now = Instant::now();
        for bucket in self.buckets.values_mut() {
            bucket.reset(now);
        }
    }
}

/// Python-facing token-bucket registry. Thin wrapper around
/// [`RateLimiterRegistryCore`] that adapts the Python boundary (exception types,
/// default args, GIL release) to the pure-Rust core.
///
/// The class name `RateLimiterRegistry` is load-bearing:
/// `backend/apps/diagnostics/health.py` expects it as the module attribute, and
/// `backend/apps/sources/api_rate_limiter.py` imports it directly.
#[pyclass]
pub struct RateLimiterRegistry {
    core: RateLimiterRegistryCore,
}

/// Map a core error to the Python exception the parity tests expect.
///
/// `BadValue` → `ValueError` (test line 78 catches `(ValueError, RuntimeError)`);
/// `NotRegistered` → `KeyError` (test line 82 catches `(KeyError, RuntimeError,
/// IndexError)`, and `KeyError` is closest to the Python fallback adapter).
fn to_py_err(err: RateLimiterError) -> PyErr {
    match err {
        RateLimiterError::BadValue(msg) => PyValueError::new_err(msg),
        RateLimiterError::NotRegistered => PyKeyError::new_err("bucket not registered"),
    }
}

#[pymethods]
impl RateLimiterRegistry {
    /// `RateLimiterRegistry()` — no args. State is an internal name→bucket map.
    #[new]
    fn new() -> Self {
        Self {
            core: RateLimiterRegistryCore::new(),
        }
    }

    /// `register_bucket(name, capacity, rate_per_sec, daily_quota=-1) -> None`.
    ///
    /// Raises `ValueError("capacity and rate must be positive")` for a
    /// non-positive `capacity` or `rate_per_sec`.
    #[pyo3(signature = (name, capacity, rate_per_sec, daily_quota=-1))]
    fn register_bucket(
        &mut self,
        py: Python<'_>,
        name: &str,
        capacity: f64,
        rate_per_sec: f64,
        daily_quota: i64,
    ) -> PyResult<()> {
        py.detach(|| {
            self.core
                .register_bucket(name, capacity, rate_per_sec, daily_quota)
        })
        .map_err(to_py_err)
    }

    /// `try_acquire(name, cost=1.0) -> bool`.
    #[pyo3(signature = (name, cost=1.0))]
    fn try_acquire(&mut self, py: Python<'_>, name: &str, cost: f64) -> PyResult<bool> {
        py.detach(|| self.core.try_acquire(name, cost))
            .map_err(to_py_err)
    }

    /// `wait_seconds(name, cost=1.0) -> float`.
    #[pyo3(signature = (name, cost=1.0))]
    fn wait_seconds(&mut self, py: Python<'_>, name: &str, cost: f64) -> PyResult<f64> {
        py.detach(|| self.core.wait_seconds(name, cost))
            .map_err(to_py_err)
    }

    /// `available(name) -> float` — current tokens after a refill.
    fn available(&mut self, py: Python<'_>, name: &str) -> PyResult<f64> {
        py.detach(|| self.core.available(name)).map_err(to_py_err)
    }

    /// `daily_remaining(name) -> int` — remaining quota (`-1` = disabled).
    fn daily_remaining(&mut self, py: Python<'_>, name: &str) -> PyResult<i64> {
        py.detach(|| self.core.daily_remaining(name))
            .map_err(to_py_err)
    }

    /// `reset_all() -> None` — reset every bucket in place (test-only).
    fn reset_all(&mut self, py: Python<'_>) {
        py.detach(|| self.core.reset_all());
    }
}

/// The Python module definition. The module name (`api_rate_limiter`) MUST
/// match the `[lib] name` in `Cargo.toml` so the built artifact imports as
/// `extensions.api_rate_limiter`. Registering `RateLimiterRegistry` keeps the
/// health probe's expected attribute present and NOTHING else is added, per the
/// port spec.
#[pymodule]
fn api_rate_limiter(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<RateLimiterRegistry>()?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::{RateLimiterError, RateLimiterRegistryCore};

    fn registry_with(name: &str, capacity: f64, rate: f64, quota: i64) -> RateLimiterRegistryCore {
        let mut reg = RateLimiterRegistryCore::new();
        reg.register_bucket(name, capacity, rate, quota).unwrap();
        reg
    }

    #[test]
    fn register_rejects_non_positive_capacity() {
        // Pins the `capacity <= 0.0` half of the `||` guard. Kills a
        // `<= -> <` boundary mutant (0.0 must be rejected) and the `|| -> &&`
        // mutant (zero capacity alone errors despite a positive rate).
        let mut reg = RateLimiterRegistryCore::new();
        assert_eq!(
            reg.register_bucket("b", 0.0, 5.0, -1),
            Err(RateLimiterError::BadValue(
                "capacity and rate must be positive"
            ))
        );
    }

    #[test]
    fn register_rejects_non_positive_rate() {
        // The other half of the `||` guard: zero rate alone errors despite a
        // positive capacity.
        let mut reg = RateLimiterRegistryCore::new();
        assert_eq!(
            reg.register_bucket("b", 5.0, 0.0, -1),
            Err(RateLimiterError::BadValue(
                "capacity and rate must be positive"
            ))
        );
    }

    #[test]
    fn register_accepts_minimum_positive_config() {
        let mut reg = RateLimiterRegistryCore::new();
        assert!(reg.register_bucket("b", 1.0, 1.0, -1).is_ok());
    }

    #[test]
    fn unknown_name_is_not_registered_error() {
        let mut reg = RateLimiterRegistryCore::new();
        assert_eq!(
            reg.available("missing"),
            Err(RateLimiterError::NotRegistered)
        );
        assert_eq!(
            reg.try_acquire("missing", 1.0),
            Err(RateLimiterError::NotRegistered)
        );
        assert_eq!(
            reg.wait_seconds("missing", 1.0),
            Err(RateLimiterError::NotRegistered)
        );
        assert_eq!(
            reg.daily_remaining("missing"),
            Err(RateLimiterError::NotRegistered)
        );
    }

    #[test]
    fn try_acquire_rejects_non_positive_cost() {
        let mut reg = registry_with("b", 10.0, 5.0, -1);
        assert_eq!(
            reg.try_acquire("b", 0.0),
            Err(RateLimiterError::BadValue("cost must be > 0"))
        );
        assert_eq!(
            reg.wait_seconds("b", -1.0),
            Err(RateLimiterError::BadValue("cost must be > 0"))
        );
    }

    #[test]
    fn fresh_bucket_starts_full() {
        let mut reg = registry_with("b", 10.0, 5.0, -1);
        // A just-registered bucket holds `capacity` tokens.
        assert!((reg.available("b").unwrap() - 10.0).abs() < 1e-6);
    }

    #[test]
    fn try_acquire_decrements_tokens_by_cost() {
        let mut reg = registry_with("b", 10.0, 0.000_001, -1);
        assert!(reg.try_acquire("b", 3.0).unwrap());
        // Rate is tiny, so refill over the test's microseconds is negligible:
        // tokens dropped from 10 to ~7. Assert close to 7, never 10 or 4.
        let left = reg.available("b").unwrap();
        assert!(left < 7.5 && left > 6.5, "expected ~7 tokens, got {left}");
    }

    #[test]
    fn try_acquire_fails_when_insufficient_tokens() {
        let mut reg = registry_with("b", 2.0, 0.000_001, -1);
        // Cost exceeds capacity and the rate is too slow to ever help quickly.
        assert!(!reg.try_acquire("b", 5.0).unwrap());
    }

    #[test]
    fn wait_seconds_zero_when_acquirable_now() {
        let mut reg = registry_with("b", 10.0, 5.0, -1);
        // Exactly 0.0 means available now; abs() guards the f64 strict-compare
        // lint while still pinning the value to zero.
        assert!(reg.wait_seconds("b", 5.0).unwrap().abs() < 1e-12);
    }

    #[test]
    fn wait_seconds_is_deficit_over_rate() {
        // Capacity 5, rate 2/s, drain all 5, ask for 5 more: deficit ~5,
        // wait ~5/2 = 2.5s. Use a slow rate so refill during the test is small.
        let mut reg = registry_with("b", 5.0, 2.0, -1);
        assert!(reg.try_acquire("b", 5.0).unwrap());
        let wait = reg.wait_seconds("b", 5.0).unwrap();
        // deficit/rate with a tiny refill correction: close to 2.5s.
        assert!(wait > 2.0 && wait < 2.6, "expected ~2.5s, got {wait}");
    }

    #[test]
    fn refill_caps_at_capacity() {
        // Even after a long conceptual wait, tokens never exceed capacity.
        // We can't sleep deterministically, but a fresh full bucket already
        // sits at capacity and another refill must not push it above.
        let mut reg = registry_with("b", 4.0, 1000.0, -1);
        let t = reg.available("b").unwrap();
        assert!(t <= 4.0 + 1e-9, "tokens {t} exceeded capacity 4.0");
    }

    #[test]
    fn daily_quota_disabled_is_minus_one_and_never_decrements() {
        let mut reg = registry_with("b", 10.0, 5.0, -1);
        assert_eq!(reg.daily_remaining("b").unwrap(), -1);
        assert!(reg.try_acquire("b", 1.0).unwrap());
        // Disabled quota stays -1 after a successful acquire.
        assert_eq!(reg.daily_remaining("b").unwrap(), -1);
    }

    #[test]
    fn daily_quota_decrements_on_success_and_exhausts() {
        let mut reg = registry_with("b", 100.0, 0.000_001, 2);
        assert_eq!(reg.daily_remaining("b").unwrap(), 2);
        assert!(reg.try_acquire("b", 1.0).unwrap());
        assert_eq!(reg.daily_remaining("b").unwrap(), 1);
        assert!(reg.try_acquire("b", 1.0).unwrap());
        assert_eq!(reg.daily_remaining("b").unwrap(), 0);
        // Quota exhausted: further acquires fail even though tokens remain.
        assert!(!reg.try_acquire("b", 1.0).unwrap());
    }

    #[test]
    fn wait_seconds_reports_daily_reset_when_quota_blocks() {
        let mut reg = registry_with("b", 100.0, 0.000_001, 1);
        assert!(reg.try_acquire("b", 1.0).unwrap());
        // Quota now 0; wait_seconds returns time until next UTC midnight (>0,
        // <= one day in seconds), not a token deficit.
        let wait = reg.wait_seconds("b", 1.0).unwrap();
        assert!(
            wait > 0.0 && wait <= 86_400.0,
            "expected seconds-until-midnight, got {wait}"
        );
    }

    #[test]
    fn reset_all_restores_tokens_and_keeps_buckets() {
        let mut reg = registry_with("b", 10.0, 0.000_001, 3);
        assert!(reg.try_acquire("b", 4.0).unwrap());
        assert_eq!(reg.daily_remaining("b").unwrap(), 2);
        reg.reset_all();
        // Tokens back to capacity, quota restored, bucket still present.
        assert!((reg.available("b").unwrap() - 10.0).abs() < 0.1);
        assert_eq!(reg.daily_remaining("b").unwrap(), 3);
    }

    #[test]
    fn register_replace_resets_tokens_not_carried_over() {
        let mut reg = registry_with("b", 10.0, 0.000_001, -1);
        assert!(reg.try_acquire("b", 8.0).unwrap());
        // Re-register: tokens reset to the new capacity, not the drained 2.
        reg.register_bucket("b", 6.0, 1.0, -1).unwrap();
        let t = reg.available("b").unwrap();
        assert!(
            (t - 6.0).abs() < 0.1,
            "replace should reset tokens to 6, got {t}"
        );
    }
}
