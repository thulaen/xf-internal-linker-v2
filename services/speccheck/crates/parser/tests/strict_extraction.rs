//! Strict behavior extraction tests.

use speccheck_parser::parse_behaviors;

#[test]
fn test_when_well_formed_block_then_one_behavior_is_extracted() {
    let text = "Given a spec exists\nWhen speccheck scans it\nThen one behavior is reported";

    let (behaviors, diagnostics) = parse_behaviors("docs/specs/demo.md", text);

    assert!(diagnostics.is_empty());
    assert_eq!(behaviors.len(), 1);
    assert_eq!(behaviors[0].line_number, 1);
}

#[test]
fn test_when_then_is_missing_then_diagnostic_is_reported() {
    let text = "Given a spec exists\nWhen speccheck scans it";

    let (behaviors, diagnostics) = parse_behaviors("docs/specs/demo.md", text);

    assert!(behaviors.is_empty());
    assert_eq!(diagnostics.len(), 1);
    assert_eq!(diagnostics[0].line_number, 1);
}

#[test]
fn test_when_block_has_preface_then_given_line_number_is_preserved() {
    let text =
        "# Heading\n\nGiven a spec exists\nWhen speccheck scans it\nThen one behavior is reported";

    let (behaviors, diagnostics) = parse_behaviors("docs/specs/demo.md", text);

    assert!(diagnostics.is_empty());
    assert_eq!(behaviors[0].line_number, 3);
}

#[test]
fn test_when_source_path_has_nested_area_then_target_area_uses_first_three_parts() {
    let text = "Given a spec exists\nWhen speccheck scans it\nThen one behavior is reported";

    let (behaviors, diagnostics) = parse_behaviors("docs/specs/rust/demo.md", text);

    assert!(diagnostics.is_empty());
    assert_eq!(behaviors[0].target_area, "docs/specs/rust");
}

#[test]
fn test_when_invalid_block_has_preface_then_diagnostic_line_number_is_preserved() {
    let text = "# Heading\n\nGiven a spec exists\nWhen speccheck scans it";

    let (behaviors, diagnostics) = parse_behaviors("docs/specs/demo.md", text);

    assert!(behaviors.is_empty());
    assert_eq!(diagnostics[0].line_number, 3);
}
