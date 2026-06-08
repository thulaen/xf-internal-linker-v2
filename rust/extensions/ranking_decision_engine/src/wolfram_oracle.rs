//! Test-only notes for the future Wolfram offline oracle harness.
//!
//! Wolfram Engine is intentionally not linked into live scoring. Future tests
//! may call wolframscript or WSTP to generate compressed expected-value
//! fixtures, then stream those fixtures into Rust property checks.

pub const ORACLE_ROLE: &str = "offline-test-only";
