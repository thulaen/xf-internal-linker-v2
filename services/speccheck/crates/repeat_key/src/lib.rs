//! Stable repeat-key generation for parsed behavior blocks.
//!
//! Keys use SHA-256 over normalized behavior fields so repeated imports dedupe
//! the same behavior across line-ending and whitespace changes.

#![forbid(unsafe_code)]
#![allow(clippy::pedantic, clippy::nursery, clippy::cargo)]
use sha2::{Digest, Sha256};
use speccheck_parser::Behavior;

/// A deterministic repeat key for one behavior.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RepeatKey(pub String);

/// Build a deterministic key from normalized behavior text.
///
/// # Examples
///
/// ```
/// use speccheck_parser::Behavior;
/// let b = Behavior {
///     source_path: "docs/spec.md".into(),
///     line_number: 1,
///     given: "a spec".into(),
///     when: "it runs".into(),
///     then: "it passes".into(),
///     target_area: "docs".into(),
/// };
/// assert_eq!(speccheck_repeat_key::repeat_key(&b).0.len(), 64);
/// ```
#[must_use]
pub fn repeat_key(behavior: &Behavior) -> RepeatKey {
    let stable = format!(
        "{}\n{}\n{}\n{}\n{}",
        normalize(&behavior.source_path),
        normalize(&behavior.given),
        normalize(&behavior.when),
        normalize(&behavior.then),
        normalize(&behavior.target_area),
    );
    let digest = Sha256::digest(stable.as_bytes());
    RepeatKey(format!("{digest:x}"))
}

fn normalize(value: &str) -> String {
    value.split_whitespace().collect::<Vec<_>>().join(" ")
}
