//! Testable command dispatcher for the speccheck binary.

#![forbid(unsafe_code)]
#![allow(clippy::pedantic, clippy::nursery, clippy::cargo)]
use std::path::{Path, PathBuf};

const USAGE: &str =
    "usage: speccheck [scan|find-bugs <path>|coverage-gaps --format lcov|cobertura|cargo-mutants [--stubs-dir <dir>] <path>]";

/// Run speccheck with already-collected command-line arguments.
///
/// # Errors
///
/// Returns a plain-English error when the command is unknown, an input file
/// cannot be read, or the scanned file contains malformed records.
pub fn run(args: &[String]) -> Result<(), String> {
    if args.is_empty() {
        return Err(USAGE.to_owned());
    }
    if args.len() == 1 {
        println!("{}", speccheck_report::empty_report_json());
        return Ok(());
    }
    let command = args[1].as_str();
    match command {
        "scan" => command_path(args, command).and_then(scan),
        "find-bugs" => command_path(args, command).and_then(find_bugs),
        "coverage-gaps" => coverage_args(args),
        other => Err(format!("unknown command `{other}`")),
    }
}

fn command_path<'a>(args: &'a [String], command: &str) -> Result<&'a Path, String> {
    if args.len() == 3 {
        return Ok(Path::new(&args[2]));
    }
    Err(format!("unknown command `{command}`"))
}

fn coverage_args(args: &[String]) -> Result<(), String> {
    let Some(request) = CoverageRequest::parse(args) else {
        return Err("unknown command `coverage-gaps`".to_owned());
    };
    coverage_gaps(
        &request.format,
        &request.report_path,
        request.stubs_dir.as_deref(),
    )
}

fn scan(path: &Path) -> Result<(), String> {
    let text = std::fs::read_to_string(path)
        .map_err(|error| format!("could not read `{}`: {error}", path.display()))?;
    let source_path = path.to_string_lossy();
    let (behaviors, diagnostics) = speccheck_parser::parse_behaviors(&source_path, &text);
    if let Some(diagnostic) = diagnostics.first() {
        return Err(format!(
            "{}:{} {}",
            path.display(),
            diagnostic.line_number,
            diagnostic.message
        ));
    }
    let report = speccheck_report::behavior_report_json(&behaviors);
    println!("{report}");
    Ok(())
}

fn coverage_gaps(format: &str, path: &Path, stubs_dir: Option<&Path>) -> Result<(), String> {
    let format = CoverageFormat::parse(format)?;
    let text = std::fs::read_to_string(path)
        .map_err(|error| format!("could not read `{}`: {error}", path.display()))?;
    let gaps = match format {
        CoverageFormat::Lcov => speccheck_coverage::parse_lcov("mixed", &text),
        CoverageFormat::Cobertura => speccheck_coverage::parse_cobertura("mixed", &text),
        CoverageFormat::CargoMutants => speccheck_coverage::parse_cargo_mutants("rust", &text),
    }
    .map_err(|error| format!("could not parse `{}`: {error}", path.display()))?;
    if let Some(dir) = stubs_dir {
        write_stubs(dir, &gaps)?;
    }
    let report = speccheck_report::coverage_report_json(&gaps);
    println!("{report}");
    Ok(())
}

struct CoverageRequest {
    format: String,
    report_path: PathBuf,
    stubs_dir: Option<PathBuf>,
}

impl CoverageRequest {
    fn parse(args: &[String]) -> Option<Self> {
        if args.len() == 5 && args[2] == "--format" {
            return Some(Self {
                format: args[3].clone(),
                report_path: PathBuf::from(&args[4]),
                stubs_dir: None,
            });
        }
        if args.len() == 7 && args[2] == "--format" && args[4] == "--stubs-dir" {
            return Some(Self {
                format: args[3].clone(),
                stubs_dir: Some(PathBuf::from(&args[5])),
                report_path: PathBuf::from(&args[6]),
            });
        }
        None
    }
}

enum CoverageFormat {
    Lcov,
    Cobertura,
    CargoMutants,
}

impl CoverageFormat {
    fn parse(value: &str) -> Result<Self, String> {
        match value {
            "lcov" => Ok(Self::Lcov),
            "cobertura" => Ok(Self::Cobertura),
            "cargo-mutants" => Ok(Self::CargoMutants),
            other => Err(format!("unknown coverage format `{other}`")),
        }
    }
}

fn write_stubs(dir: &Path, gaps: &[speccheck_coverage::Gap]) -> Result<(), String> {
    std::fs::create_dir_all(dir).map_err(|error| {
        format!(
            "could not create stubs directory `{}`: {error}",
            dir.display()
        )
    })?;
    for gap in gaps {
        let path = dir.join(stub_filename(gap));
        std::fs::write(&path, stub_body(gap))
            .map_err(|error| format!("could not write stub `{}`: {error}", path.display()))?;
    }
    Ok(())
}

fn stub_filename(gap: &speccheck_coverage::Gap) -> String {
    let source = Path::new(&gap.file);
    let extension = source
        .extension()
        .and_then(|value| value.to_str())
        .unwrap_or("txt");
    let without_extension = source.with_extension("");
    let stem = without_extension
        .to_string_lossy()
        .replace(['/', '\\', '.', '-'], "_")
        .trim_matches('_')
        .to_owned();
    format!("{stem}_{}.{}", gap.line_start, extension)
}

fn stub_body(gap: &speccheck_coverage::Gap) -> String {
    format!(
        "# AUTO-GENERATED-STUB\n\
         # Given coverage is missing for {}:{}\n\
         # When the affected behavior is exercised\n\
         # Then this gap should be covered by a real assertion\n\n\
         def test_when_{}_line_{}_then_gap_is_covered():\n\
         \x20   raise AssertionError(\"Fill in the behavior and assertion for {}:{}\")\n",
        gap.file,
        gap.line_start,
        function_hint(&gap.file),
        gap.line_start,
        gap.file,
        gap.line_start,
    )
}

fn function_hint(file: &str) -> String {
    file.rsplit(['/', '\\'])
        .next()
        .unwrap_or("coverage_gap")
        .split('.')
        .next()
        .unwrap_or("coverage_gap")
        .replace('-', "_")
}

fn find_bugs(path: &Path) -> Result<(), String> {
    let text = std::fs::read_to_string(path)
        .map_err(|error| format!("could not read `{}`: {error}", path.display()))?;
    let source_path = path.to_string_lossy();
    let findings = speccheck_detectors::find_bugs_in_source(&source_path, &text);
    let report = speccheck_report::bug_report_json(&findings);
    println!("{report}");
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::run;

    #[test]
    fn test_when_args_are_empty_then_usage_is_returned() {
        let result = run(&[]);

        assert_eq!(
            result.expect_err("empty args should fail"),
            "usage: speccheck [scan|find-bugs <path>|coverage-gaps --format lcov|cobertura|cargo-mutants [--stubs-dir <dir>] <path>]"
        );
    }

    #[test]
    fn test_when_only_binary_arg_is_given_then_empty_report_is_returned() {
        let args = vec!["speccheck".to_owned()];

        assert!(run(&args).is_ok());
    }

    #[test]
    fn test_when_unknown_command_is_used_then_plain_english_error_is_returned() {
        let args = vec!["speccheck".to_owned(), "unknown".to_owned()];

        let error = run(&args).expect_err("unknown command should fail");

        assert_eq!(error, "unknown command `unknown`");
    }

    #[test]
    fn test_when_three_arg_command_is_unknown_then_plain_english_error_is_returned() {
        let args = vec![
            "speccheck".to_owned(),
            "lint".to_owned(),
            "source.py".to_owned(),
        ];

        let error = run(&args).expect_err("unknown three-arg command should fail");

        assert_eq!(error, "unknown command `lint`");
    }

    #[test]
    fn test_when_scan_arg_is_valid_then_report_is_returned() {
        let fixture =
            std::env::temp_dir().join(format!("speccheck-lib-scan-{}.md", std::process::id()));
        std::fs::write(
            &fixture,
            "Given a spec exists\nWhen speccheck scans it\nThen JSON includes it",
        )
        .expect("fixture should be writable");
        let args = vec![
            "speccheck".to_owned(),
            "scan".to_owned(),
            fixture.to_string_lossy().into_owned(),
        ];

        let result = run(&args);

        let _ = std::fs::remove_file(&fixture);
        assert!(result.is_ok());
    }

    #[test]
    fn test_when_find_bugs_arg_is_valid_then_report_is_returned() {
        let fixture =
            std::env::temp_dir().join(format!("speccheck-lib-find-bugs-{}.py", std::process::id()));
        std::fs::write(
            &fixture,
            "def view(request):\n    return pickle.loads(request.body)\n",
        )
        .expect("fixture should be writable");
        let args = vec![
            "speccheck".to_owned(),
            "find-bugs".to_owned(),
            fixture.to_string_lossy().into_owned(),
        ];

        let result = run(&args);

        let _ = std::fs::remove_file(&fixture);
        assert!(result.is_ok());
    }

    #[test]
    fn test_when_coverage_gaps_arg_is_valid_then_report_is_returned() {
        let fixture =
            std::env::temp_dir().join(format!("speccheck-lib-lcov-{}.info", std::process::id()));
        std::fs::write(&fixture, "SF:apps/foo.py\nDA:11,0\nend_of_record\n")
            .expect("fixture should be writable");
        let args = vec![
            "speccheck".to_owned(),
            "coverage-gaps".to_owned(),
            "--format".to_owned(),
            "lcov".to_owned(),
            fixture.to_string_lossy().into_owned(),
        ];

        let result = run(&args);

        let _ = std::fs::remove_file(&fixture);
        assert!(result.is_ok());
    }

    #[test]
    fn test_when_scan_file_is_missing_then_read_error_is_returned() {
        let args = vec![
            "speccheck".to_owned(),
            "scan".to_owned(),
            "missing-file.md".to_owned(),
        ];

        let error = run(&args).expect_err("missing scan file should fail");

        assert!(error.contains("could not read `missing-file.md`"));
    }

    #[test]
    fn test_when_scan_file_has_diagnostic_then_diagnostic_is_returned() {
        let fixture =
            std::env::temp_dir().join(format!("speccheck-lib-invalid-{}.md", std::process::id()));
        std::fs::write(&fixture, "# Heading\n\nGiven a spec\nWhen it runs")
            .expect("fixture should be writable");
        let args = vec![
            "speccheck".to_owned(),
            "scan".to_owned(),
            fixture.to_string_lossy().into_owned(),
        ];

        let error = run(&args).expect_err("invalid scan file should fail");

        let _ = std::fs::remove_file(&fixture);
        assert!(error.contains(":3 Given must be followed by exactly one When and one Then line."));
    }

    #[test]
    fn test_when_find_bugs_file_is_missing_then_read_error_is_returned() {
        let args = vec![
            "speccheck".to_owned(),
            "find-bugs".to_owned(),
            "missing-source.py".to_owned(),
        ];

        let error = run(&args).expect_err("missing find-bugs file should fail");

        assert!(error.contains("could not read `missing-source.py`"));
    }

    #[test]
    fn test_when_coverage_format_is_unknown_then_error_is_returned() {
        let args = vec![
            "speccheck".to_owned(),
            "coverage-gaps".to_owned(),
            "--format".to_owned(),
            "mystery".to_owned(),
            "coverage.out".to_owned(),
        ];

        let error = run(&args).expect_err("unknown format should fail");

        assert_eq!(error, "unknown coverage format `mystery`");
    }

    #[test]
    fn test_when_coverage_gaps_flag_is_wrong_then_command_is_rejected() {
        let args = vec![
            "speccheck".to_owned(),
            "coverage-gaps".to_owned(),
            "--type".to_owned(),
            "lcov".to_owned(),
            "coverage.info".to_owned(),
        ];

        let error = run(&args).expect_err("wrong coverage flag should fail");

        assert_eq!(error, "unknown command `coverage-gaps`");
    }

    #[test]
    fn test_when_coverage_gaps_is_missing_path_then_command_is_rejected() {
        let args = vec![
            "speccheck".to_owned(),
            "coverage-gaps".to_owned(),
            "--format".to_owned(),
            "lcov".to_owned(),
        ];

        let error = run(&args).expect_err("missing coverage path should fail");

        assert_eq!(error, "unknown command `coverage-gaps`");
    }

    #[test]
    fn test_when_stub_dir_has_missing_format_flag_then_command_is_rejected() {
        let args = vec![
            "speccheck".to_owned(),
            "coverage-gaps".to_owned(),
            "--stubs-dir".to_owned(),
            "tests/suggestions".to_owned(),
            "--format".to_owned(),
            "lcov".to_owned(),
            "coverage.info".to_owned(),
        ];

        let error = run(&args).expect_err("misordered stub args should fail");

        assert_eq!(error, "unknown command `coverage-gaps`");
    }

    #[test]
    fn test_when_stub_dir_flag_is_wrong_then_command_is_rejected() {
        let args = vec![
            "speccheck".to_owned(),
            "coverage-gaps".to_owned(),
            "--format".to_owned(),
            "lcov".to_owned(),
            "--output-dir".to_owned(),
            "tests/suggestions".to_owned(),
            "coverage.info".to_owned(),
        ];

        let error = run(&args).expect_err("wrong stub-dir flag should fail");

        assert_eq!(error, "unknown command `coverage-gaps`");
    }

    #[test]
    fn test_when_stub_source_has_no_extension_then_txt_stub_is_written() {
        let fixture =
            std::env::temp_dir().join(format!("speccheck-lib-stub-{}.info", std::process::id()));
        let stub_dir =
            std::env::temp_dir().join(format!("speccheck-lib-stubs-{}", std::process::id()));
        std::fs::write(&fixture, "SF:apps/foo/Makefile\nDA:7,0\nend_of_record\n")
            .expect("fixture should be writable");
        let args = vec![
            "speccheck".to_owned(),
            "coverage-gaps".to_owned(),
            "--format".to_owned(),
            "lcov".to_owned(),
            "--stubs-dir".to_owned(),
            stub_dir.to_string_lossy().into_owned(),
            fixture.to_string_lossy().into_owned(),
        ];

        let result = run(&args);

        let stub_path = stub_dir.join("apps_foo_Makefile_7.txt");
        let _ = std::fs::remove_file(&fixture);
        let _ = std::fs::remove_file(&stub_path);
        let _ = std::fs::remove_dir(&stub_dir);
        assert!(result.is_ok());
    }

    #[test]
    fn test_when_stub_dir_is_a_file_then_plain_error_is_returned() {
        let fixture = std::env::temp_dir().join(format!(
            "speccheck-lib-stub-file-{}.info",
            std::process::id()
        ));
        let stub_dir =
            std::env::temp_dir().join(format!("speccheck-lib-stub-file-{}", std::process::id()));
        std::fs::write(&fixture, "SF:apps/foo.py\nDA:7,0\nend_of_record\n")
            .expect("fixture should be writable");
        std::fs::write(&stub_dir, "not a directory").expect("stub path should be writable");
        let args = vec![
            "speccheck".to_owned(),
            "coverage-gaps".to_owned(),
            "--format".to_owned(),
            "lcov".to_owned(),
            "--stubs-dir".to_owned(),
            stub_dir.to_string_lossy().into_owned(),
            fixture.to_string_lossy().into_owned(),
        ];

        let error = run(&args).expect_err("file stubs-dir should fail");

        let _ = std::fs::remove_file(&fixture);
        let _ = std::fs::remove_file(&stub_dir);
        assert!(error.contains("could not create stubs directory"));
    }

    #[test]
    fn test_when_stub_target_is_a_directory_then_plain_error_is_returned() {
        let fixture = std::env::temp_dir().join(format!(
            "speccheck-lib-stub-write-{}.info",
            std::process::id()
        ));
        let stub_dir =
            std::env::temp_dir().join(format!("speccheck-lib-stub-write-{}", std::process::id()));
        let blocked_path = stub_dir.join("apps_foo_7.py");
        std::fs::write(&fixture, "SF:apps/foo.py\nDA:7,0\nend_of_record\n")
            .expect("fixture should be writable");
        std::fs::create_dir_all(&blocked_path).expect("blocked stub path should be a directory");
        let args = vec![
            "speccheck".to_owned(),
            "coverage-gaps".to_owned(),
            "--format".to_owned(),
            "lcov".to_owned(),
            "--stubs-dir".to_owned(),
            stub_dir.to_string_lossy().into_owned(),
            fixture.to_string_lossy().into_owned(),
        ];

        let error = run(&args).expect_err("directory stub target should fail");

        let _ = std::fs::remove_file(&fixture);
        let _ = std::fs::remove_dir(&blocked_path);
        let _ = std::fs::remove_dir(&stub_dir);
        assert!(error.contains("could not write stub"));
    }

    #[test]
    fn test_when_five_arg_command_is_not_coverage_gaps_then_command_is_rejected() {
        let args = vec![
            "speccheck".to_owned(),
            "scan".to_owned(),
            "--format".to_owned(),
            "lcov".to_owned(),
            "coverage.info".to_owned(),
        ];

        let error = run(&args).expect_err("wrong command shape should fail");

        assert_eq!(error, "unknown command `scan`");
    }

    #[test]
    fn test_when_coverage_file_is_missing_then_read_error_is_returned() {
        let args = vec![
            "speccheck".to_owned(),
            "coverage-gaps".to_owned(),
            "--format".to_owned(),
            "lcov".to_owned(),
            "missing-coverage.info".to_owned(),
        ];

        let error = run(&args).expect_err("missing coverage file should fail");

        assert!(error.contains("could not read `missing-coverage.info`"));
    }
}
