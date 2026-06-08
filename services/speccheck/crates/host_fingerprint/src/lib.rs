//! Host fingerprint helpers for recalibration checks.
//!
//! The helper keeps host identity construction pure so callers can test the
//! recalibration trigger without reading machine-specific files.

#![forbid(unsafe_code)]
#![allow(clippy::pedantic, clippy::nursery, clippy::cargo)]
/// Build a stable host fingerprint seed from already-sanitized host facts.
#[must_use]
pub fn fingerprint_seed(cpu: &str, cores: u32, memory_gib: u32, os: &str) -> String {
    format!("{cpu}|{cores}|{memory_gib}|{os}")
}
