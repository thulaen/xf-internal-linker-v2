"""Mapping from MegaLinter linter identifiers to AutoIssue category and severity.

Each entry: linter_id → (category_key, severity, create_autoissue).
category_key must be a valid key from categories.DEFAULT_CATEGORIES.
Linters not in this table get create_autoissue=True with UNKNOWN_* defaults.
"""

from __future__ import annotations

# (category_key, severity, create_autoissue)
LINTER_MAP: dict[str, tuple[str, str, bool]] = {
    # Secrets scanning — immediate critical risk
    "REPOSITORY_GITLEAKS":   ("security", "critical", True),
    "REPOSITORY_SECRETLINT": ("security", "critical", True),
    "REPOSITORY_TRUFFLEHOG": ("security", "critical", True),
    "REPOSITORY_KINGFISHER": ("security", "critical", True),

    # Vulnerability scanning (CVE databases)
    "REPOSITORY_GRYPE":      ("security", "high", True),
    "REPOSITORY_TRIVY":      ("security", "high", True),
    "OSV_SCANNER":           ("security", "high", True),

    # Static security analysis
    "REPOSITORY_SEMGREP":    ("security", "high", True),
    "REPOSITORY_DEVSKIM":    ("security", "high", True),
    "PYTHON_BANDIT":         ("security", "high", False),  # own quality script

    # IaC security
    "REPOSITORY_CHECKOV":    ("security", "high", True),
    "TERRAFORM_CHECKOV":     ("security", "high", True),
    "YAML_KICS":             ("security", "medium", True),

    # CI workflow correctness
    "ACTION_ACTIONLINT":     ("correctness", "medium", True),
    "ACTION_ZIZMOR":         ("security", "high", True),

    # Shell / Docker / config correctness
    "SHELL_SHELLCHECK":      ("correctness", "medium", True),
    "DOCKERFILE_HADOLINT":   ("correctness", "medium", True),
    "YAML_YAMLLINT":         ("correctness", "medium", True),
    "JSON_JSONLINT":         ("correctness", "low", True),

    # Formatting tools — do not create AutoIssues (noise without value)
    "SHELL_SHFMT":           ("readability", "low", False),
    "TOML_TAPLO":            ("readability", "low", False),
    "MARKDOWN_MARKDOWNLINT": ("readability", "low", False),
    "SPELL_CSPELL":          ("readability", "low", False),
    "REPOSITORY_JSCPD":      ("readability", "low", False),

    # Already covered by dedicated quality scripts — skip to avoid duplicates
    "PYTHON_RUFF":           ("correctness", "medium", False),
    "PYTHON_PYLINT":         ("correctness", "medium", False),
    "GO_GOLANGCI_LINT":      ("correctness", "medium", False),
    "RUST_CLIPPY":           ("correctness", "medium", False),
    "RUST_RUSTFMT":          ("readability", "low", False),
    "CPP_CLANGTIDY":         ("correctness", "medium", False),
    "CPP_CPPCHECK":          ("correctness", "medium", False),
    "TYPESCRIPT_ES":         ("correctness", "medium", False),
}

# Defaults for linters not in LINTER_MAP
UNKNOWN_CATEGORY = "correctness"
UNKNOWN_SEVERITY = "medium"
UNKNOWN_ENABLED = True


def lookup(linter_id: str) -> tuple[str, str, bool]:
    """Return (category_key, severity, create_autoissue) for a linter identifier."""
    return LINTER_MAP.get(linter_id, (UNKNOWN_CATEGORY, UNKNOWN_SEVERITY, UNKNOWN_ENABLED))
