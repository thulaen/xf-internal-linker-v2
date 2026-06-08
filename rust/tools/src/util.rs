//! Small shared helpers used by more than one subcommand (DRY).

use std::path::Path;

use crate::output::ExitCode;

/// A subcommand error carrying a message and the exit code to use.
///
/// Pure logic returns `Result<ToolReport, ToolError>`; `main` prints the
/// message to stderr and exits with `code`.
#[derive(Debug)]
pub struct ToolError {
    /// Human-readable, plain-English explanation of what went wrong.
    pub message: String,
    /// Exit code (`Error` for usage/IO problems).
    pub code: ExitCode,
}

impl ToolError {
    /// A usage / IO / parse error (exit code 2).
    #[must_use]
    pub fn usage(message: impl Into<String>) -> Self {
        Self {
            message: message.into(),
            code: ExitCode::Error,
        }
    }
}

impl std::fmt::Display for ToolError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}", self.message)
    }
}

impl std::error::Error for ToolError {}

/// Read a file to a string, turning IO failure into a plain-English [`ToolError`].
pub fn read_file(path: &Path) -> Result<String, ToolError> {
    std::fs::read_to_string(path)
        .map_err(|e| ToolError::usage(format!("cannot read '{}': {e}", path.display())))
}

/// Parse JSON text into a `serde_json::Value`, mapping failure to a [`ToolError`].
pub fn parse_json(text: &str, what: &str) -> Result<serde_json::Value, ToolError> {
    serde_json::from_str(text)
        .map_err(|e| ToolError::usage(format!("'{what}' is not valid JSON: {e}")))
}

/// Read and parse a JSON file in one step.
pub fn read_json(path: &Path) -> Result<serde_json::Value, ToolError> {
    let text = read_file(path)?;
    parse_json(&text, &path.display().to_string())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parse_json_rejects_garbage() {
        let err = parse_json("{not json", "x").unwrap_err();
        assert_eq!(err.code, ExitCode::Error);
        assert!(err.message.contains("not valid JSON"));
    }

    #[test]
    fn parse_json_accepts_object() {
        let v = parse_json("{\"a\":1}", "x").unwrap();
        assert_eq!(v["a"], 1);
    }

    #[test]
    fn read_file_missing_is_usage_error() {
        let err = read_file(Path::new("/no/such/file/xftool-test")).unwrap_err();
        assert_eq!(err.code, ExitCode::Error);
        assert!(err.message.contains("cannot read"));
    }
}
