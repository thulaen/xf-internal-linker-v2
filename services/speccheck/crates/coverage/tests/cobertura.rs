//! Cobertura XML parser tests for cross-language coverage gaps.

use speccheck_coverage::{parse_cobertura, Gap};

#[test]
fn parse_cobertura_clusters_uncovered_lines_and_branches() {
    let report = r#"
<coverage>
  <packages>
    <package>
      <classes>
        <class filename="apps/foo.py">
          <lines>
            <line number="10" hits="1"/>
            <line number="11" hits="0"/>
            <line number="12" hits="0"/>
            <line number="14" hits="0"/>
            <line number="20" hits="3" branch="true" condition-coverage="50% (1/2)"/>
            <line number="21" hits="3" branch="true" condition-coverage="0% (0/2)"/>
          </lines>
        </class>
      </classes>
    </package>
  </packages>
</coverage>
"#;

    let gaps = parse_cobertura("python", report).expect("Cobertura should parse");

    assert_eq!(
        gaps,
        vec![
            Gap {
                language: "python".to_string(),
                file: "apps/foo.py".to_string(),
                line_start: 11,
                line_end: 12,
                kind: "uncovered_line".to_string(),
            },
            Gap {
                language: "python".to_string(),
                file: "apps/foo.py".to_string(),
                line_start: 14,
                line_end: 14,
                kind: "uncovered_line".to_string(),
            },
            Gap {
                language: "python".to_string(),
                file: "apps/foo.py".to_string(),
                line_start: 20,
                line_end: 21,
                kind: "uncovered_branch".to_string(),
            },
        ],
    );
}

#[test]
fn parse_cobertura_ignores_fully_covered_branch_lines() {
    let gaps = parse_cobertura(
        "python",
        r#"
<class filename="apps/foo.py">
  <line number="20" hits="3" branch="true" condition-coverage="100% (2/2)"/>
</class>
"#,
    )
    .expect("fully covered branch should parse");

    assert!(gaps.is_empty());
}

#[test]
fn parse_cobertura_rejects_missing_filename() {
    let err = parse_cobertura(
        "python",
        r#"<class name="Foo"><lines><line number="1" hits="0"/></lines></class>"#,
    )
    .expect_err("missing filename should fail");

    assert!(err.to_string().contains("filename"));
}

#[test]
fn parse_cobertura_rejects_bad_line_number() {
    let err = parse_cobertura(
        "python",
        r#"<class filename="apps/foo.py"><line number="nope" hits="0"/></class>"#,
    )
    .expect_err("bad line number should fail");

    assert!(err.to_string().contains("line number"));
}

#[test]
fn parse_cobertura_rejects_missing_line_number() {
    let err = parse_cobertura(
        "python",
        r#"<class filename="apps/foo.py"><line hits="0"/></class>"#,
    )
    .expect_err("missing line number should fail");

    assert!(err.to_string().contains("line number"));
}

#[test]
fn parse_cobertura_rejects_unclosed_line_number_attribute() {
    let err = parse_cobertura(
        "python",
        r#"<class filename="apps/foo.py"><line number="7 hits=0/></class>"#,
    )
    .expect_err("unclosed line number attribute should fail");

    assert!(err.to_string().contains("line number"));
}

#[test]
fn parse_cobertura_rejects_line_outside_class() {
    let err = parse_cobertura("python", r#"<line number="1" hits="0"/>"#)
        .expect_err("line outside class should fail");

    assert!(err.to_string().contains("before class filename"));
}
