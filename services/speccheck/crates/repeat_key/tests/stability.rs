//! Repeat-key stability tests.

use speccheck_parser::Behavior;
use speccheck_repeat_key::repeat_key;

#[test]
fn test_when_whitespace_changes_then_repeat_key_stays_stable() {
    let left = behavior("Given  value", "When value", "Then value");
    let right = behavior("Given value", "When   value", "Then value");

    assert_eq!(repeat_key(&left), repeat_key(&right));
}

#[test]
fn test_when_repeat_key_is_built_then_sha256_hex_is_used() {
    let key = repeat_key(&behavior("Given value", "When value", "Then value"));

    assert_eq!(key.0.len(), 64);
    assert!(key.0.chars().all(|character| character.is_ascii_hexdigit()));
}

#[test]
fn test_when_meaningful_text_changes_then_repeat_key_changes() {
    let left = behavior("Given value one", "When value", "Then value");
    let right = behavior("Given value two", "When value", "Then value");

    assert_ne!(repeat_key(&left), repeat_key(&right));
}

fn behavior(given: &str, when: &str, then: &str) -> Behavior {
    Behavior {
        source_path: "docs/spec.md".into(),
        line_number: 1,
        given: given.into(),
        when: when.into(),
        then: then.into(),
        target_area: "docs".into(),
    }
}
