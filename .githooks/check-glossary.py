#!/usr/bin/env python3
"""
Pre-commit glossary check.

Reads the staged diff, scans every added line for new technical terms
(acronyms, project shorthand like FR-XXX / RPT-XXX / ISS-XXX, etc.), and
fails the commit if any of them are not present in the markdown table in
`PLAIN-ENGLISH-RULE.md` AND not in the false-positive allowlist below.

Goal: keep the plain-English glossary in step with the code, per the
PARAMOUNT rule in `CLAUDE.md` and `GLOSSARY-RULE.md`.

Override per-instance: add the term to the allowlist below if it really is
a false-positive (e.g. a one-off variable name in a generated file). For
genuine new vocabulary, add a row to `PLAIN-ENGLISH-RULE.md` instead.

Run manually:
    python .githooks/check-glossary.py <files...>

Run via the hook:
    automatic on every commit
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
GLOSSARY_PATH = REPO_ROOT / "PLAIN-ENGLISH-RULE.md"

# Common false-positives that never need a glossary entry. Keep this short
# and obvious — anything genuinely new should land in the glossary itself.
ALLOWLIST: frozenset[str] = frozenset({
    # Web standards
    "CSS", "HTML", "URL", "URLs", "JSON", "HTTP", "HTTPS", "CSV", "JSX", "TSX",
    "SCSS", "DOM", "AST", "GUI", "CLI", "UI", "UX", "ID", "IDs", "SDK", "REST",
    "RPC", "JWT", "TLS", "SSL", "CRC", "MD5", "SHA", "UUID", "ISO", "RFC",
    "GMT", "UTC", "MIME", "PNG", "JPG", "JPEG", "GIF", "SVG", "PDF", "MP3",
    "MP4", "ZIP", "TAR", "GZ", "TXT", "YAML", "YML", "TOML", "INI",
    # Hardware / OS
    "OS", "CPU", "GPU", "RAM", "ROM", "USB", "IP", "IPv4", "IPv6", "TCP",
    "UDP", "DNS", "BIOS", "ARM", "ARM64", "AMD64", "x86", "x86_64",
    # Common backend frameworks already covered by the existing glossary
    "API", "APIs", "DRF", "ORM", "SQL", "PSQL", "ETL",
    # Common units / numeric prefixes
    "KB", "MB", "GB", "TB", "PB", "MS", "NS", "US",
    # English words that happen to be uppercase
    "OK", "USA", "UK", "EU", "USD", "EUR", "GBP",
    # Project-specific paths / files (rarely meaningful as terms)
    "TODO", "FIXME", "XXX", "NB", "NOTE", "HACK", "BUG", "DEPRECATED",
    # HTTP methods
    "GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD",
    # File markers from CI / build output that may appear in diffs
    "BEGIN", "END", "EOF", "EOL", "BOM",
    # Common abbreviations the user-facing glossary already implies
    "VS", "AKA", "FAQ", "ETA", "DPI", "LCP", "FCP", "CLS", "TTFB",
    # Math / stats common shorthand
    "MIN", "MAX", "AVG", "SUM", "STD", "P50", "P95", "P99",
    # Common English words / SQL constants / log levels / Django magic that
    # happen to be all-caps in our codebase or docstrings.
    "AND", "OR", "NOT", "NULL", "TRUE", "FALSE", "NONE", "DOES", "WHERE",
    "FROM", "INTO", "JOIN", "ASC", "DESC", "EXACT", "REGEX",
    "NAME", "PATH", "REGISTRY", "BACKEND", "FRONTEND",
    "PRIOR", "STATE", "NEW", "OLD",  # everyday English, all-caps in prose / fixture suffixes
    # More everyday English words that get capitalised mid-sentence in
    # narrative documentation (e.g. "TURN OFF", "ONE release",
    # "WHICH key" in instructional prose) and aren't technical jargon.
    "OFF", "ONE", "TURN", "OUT", "WHICH", "WHETHER", "LEGACY",
    "INFO", "WARN", "WARNING", "ERROR", "DEBUG", "TRACE", "FATAL",
    "NOTICE", "SUCCESS", "FAILED", "FAIL", "PASS", "SKIP", "SKIPPED",
    "COMPLETED", "RUNNING", "PENDING", "QUEUED", "PROCESSING", "ABORTED",
    "BENCHMARK", "BENCH",
    # PowerShell built-in variables / common shell vars
    "LASTEXITCODE", "PSScriptRoot", "PSCommandPath", "ErrorActionPreference",
    "PWD", "OLDPWD", "HOME", "TMPDIR",
    # Date-format placeholders
    "YYYY-MM", "YYYY-MM-DD", "MM-DD", "HH-MM",
    # Project section / doc-file headings used in upper-case prose
    "PARAMOUNT", "CLAUDE", "AGENTS", "CODEX", "GEMINI", "RULE", "GUIDE",
    "BEFORE", "AFTER", "CRITICAL", "MANDATORY", "PROHIBITED",
    # Template placeholders that look like all-caps tokens
    "MONTH", "YEAR", "DAY", "DATE", "TIME", "USER", "EMAIL",
    # Universal placeholder words used in tests / examples
    "FOO", "BAR", "BAZ", "QUX", "SAMPLE", "EXAMPLE", "TEST",
    # Marketing / SEO abbreviations that appear in user-facing copy
    "SEO", "CRM", "CTR", "CTA", "ROI", "KPI", "B2B", "B2C",
    # RFC 2119 keywords — common in spec / rule prose
    "MUST", "SHOULD", "MAY", "MUST-NOT", "SHOULD-NOT", "REQUIRED",
    "RECOMMENDED", "OPTIONAL",
    # Project-specific compound nouns that read more naturally hyphenated
    "BEAT-ENTRY", "TASK-NAME", "TASK-ID", "RUN-ID", "BATCH-LABEL",
    # POSIX errno codes and OS / process identifiers
    "EADDRINUSE", "EAGAIN", "EBADF", "EBUSY", "ECONNRESET", "EEXIST",
    "EINTR", "EINVAL", "EIO", "ENOENT", "ENOMEM", "ENOSPC", "EPERM",
    "EPIPE", "ETIMEDOUT", "EXDEV", "EOL", "EOF", "PID", "PPID", "TTY",
    # Web servers and well-known system services people mention by acronym
    "IIS", "NGINX", "APACHE",
    # Vendor / product proper nouns that show up in all-caps string lookups
    "OPENAI", "GEMINI", "ANTHROPIC", "GOOGLE", "AWS", "GCP", "AZURE",
    # PostgreSQL / SQL DDL keywords commonly typed in upper-case in code
    "REFRESH", "MATERIALIZED", "VIEW", "CONCURRENTLY", "TABLE", "INDEX",
    "CONSTRAINT", "UNIQUE", "PRIMARY", "FOREIGN", "REFERENCES", "CASCADE",
    "RESTRICT", "DEFAULT", "CHECK", "TRIGGER", "FUNCTION", "PROCEDURE",
    "GRANT", "REVOKE", "COMMIT", "ROLLBACK", "SAVEPOINT", "VACUUM",
    "ANALYZE", "EXPLAIN", "TRUNCATE", "ALTER", "DROP", "RENAME", "RETURNS",
    # Status / state enum values (uppercase in code AND docstrings)
    "PAUSED", "WORKING", "IDLE", "DEGRADED", "RUNNING", "STOPPED",
    "STARTING", "STOPPING", "PENDING", "PROPOSED", "APPROVED", "REJECTED",
    "APPLIED", "VERIFIED", "STALE", "SUPERSEDED", "ACTIVE", "INACTIVE",
    "DESTRUCTIVE", "DUPLICATES", "BODYKEY", "META", "SIGNALS",
    "GROUP", "FETCHED", "FAISS-GPU",
    # spaCy part-of-speech tags (Universal Dependencies set)
    "ADJ", "ADP", "ADV", "AUX", "CCONJ", "DET", "INTJ", "NOUN", "NUM",
    "PART", "PRON", "PROPN", "PUNCT", "SCONJ", "SYM", "VERB",
    # Project shorthand / algorithm acronyms already used widely
    "ACI", "BPR", "ELO", "EMA", "HPO", "HITS", "IPS", "KCIB", "KMIG",
    "MMR", "PPR", "PMI", "RRF", "SHAP", "SPRT", "TAPB", "DARB", "BERP",
    "HGTE", "RSQVA",
    # Common dev-environment + design-pattern terms
    "KISS", "DRY", "YAGNI", "LOC", "TDD", "BDD", "MVC", "MVP", "MVVM",
    # Short shorthand (already cited in glossary one-liners)
    "LLM", "LLMs", "GSC", "GA4", "MCP", "FR", "RPT", "ISS",
    # Doc/spec filenames that show up in `path/to/X-RULE.md`-style refs
    "PLAIN-ENGLISH", "GLOSSARY-RULE", "CPP-FIRST", "CPP-RULES",
    "MCP-SETUP", "FRONTEND-RULES", "PYTHON-RULES",
    "PERFORMANCE-SAFE-DEFAULTS", "TECH-DEBT-MANDATE", "CITATION-RULE",
    "DEEP-LINKING-CATALOG", "PLAIN-ENGLISH-HELPER-RULE",
    "HARDWARE-PROFILES", "DISK-PRESSURE-RULES", "NO-DUPLICATES",
    "AGENT-HANDOFF", "AI-CONTEXT", "REPORT-REGISTRY",
    "BUSINESS-LOGIC-CHECKLIST", "RANKING-GATES",
    "THINK-BEFORE-YOU-CODE", "PERFORMANCE",
    # Newly-added rule files (2026-05-09 default-on session). Each has a
    # full plain-English explanation in PLAIN-ENGLISH-RULE.md's glossary
    # row; the all-caps form is just a doc-filename reference.
    "DEFAULT-ON-RULE", "PLAIN-ENGLISH-RULE", "RECOMMENDED-PRESET",
    # Magic comment marker used by .githooks/check-default-on-rule.py
    # to suppress the autotuner-classification check on a per-migration
    # basis (e.g. `# AUTOTUNER: not-tunable - <reason>`).
    "AUTOTUNER",
})

# Regex: 3+ consecutive uppercase letters with optional repeated hyphen-
# segments (so DEEP-LINKING-CATALOG, BGE-M3, etc. read as one token), or
# the explicit FR-NNN / RPT-NNN / ISS-NNN spec/report/issue patterns.
ACRONYM_PATTERN = re.compile(r"\b(?:[A-Z]{3,}(?:-[A-Z0-9]+)*|FR-\d{3}|RPT-\d{3}|ISS-\d{3})\b")

# Numbered identifiers (FR-250, RPT-002, ISS-031) are covered by the
# generic "FR-XXX (any 3-digit feature number)" entry already in the
# glossary — match each numbered hit against this pattern instead of
# requiring a per-number row.
NUMBERED_ID_PATTERN = re.compile(r"^(FR|RPT|ISS)-\d{3}$")

# Lines we never scan — they're not user-facing prose.
SKIP_LINE_PATTERNS = (
    re.compile(r"^\s*//"),       # JS / TS line comments
    re.compile(r"^\s*#"),         # Python / shell comments AND markdown headers (handled below)
    re.compile(r"^\s*/\*"),       # block-comment opener
    re.compile(r"^\s*\*"),        # inside block comment
    re.compile(r"^\s*<!--"),      # HTML comment opener
)

# File extensions / paths we never scan — generated / binary / test snapshots.
SKIP_FILE_PATTERNS = (
    re.compile(r"\.lock$"),
    re.compile(r"\.min\.(js|css)$"),
    re.compile(r"package-lock\.json$"),
    re.compile(r"poetry\.lock$"),
    re.compile(r"requirements.*\.txt$"),  # version pins; not prose
    re.compile(r"^backend/.*/migrations/"),
    re.compile(r"^docs/specs/"),  # specs have their own citation rule
    re.compile(r"^docs/reports/"),  # report registry handles its own jargon
    re.compile(r"^GLOSSARY-RULE\.md$"),  # the rule doc itself uses acronyms as examples
    re.compile(r"^PLAIN-ENGLISH-RULE\.md$"),  # the glossary itself
    re.compile(r"\.cpp$"),  # C++ source files have their own header
    re.compile(r"\.h$"),
    re.compile(r"\.svg$"),
    re.compile(r"\.png$"),
    re.compile(r"\.jpg$"),
    re.compile(r"\.pdf$"),
    re.compile(r"^\.githooks/"),  # hook scripts themselves contain regex literals
    re.compile(r"^\.git/"),
    re.compile(r"frontend/dist/"),
    re.compile(r"frontend/coverage/"),
    re.compile(r"node_modules/"),
)


def load_glossary_terms() -> set[str]:
    """Parse PLAIN-ENGLISH-RULE.md and return every term mentioned in the table.

    The table is loose markdown with a "| plain-English | technical |" shape.
    We split each cell by `/` to handle "MCP / Model Context Protocol" as
    two terms, then add the trimmed phrase plus every acronym-style token
    inside it. This catches everything from single acronyms (`MCP`) to
    two-word phrases (`Claude Code`) to longer phrases (`Model Context
    Protocol`) without trying to be clever about capitalisation rules.
    """
    if not GLOSSARY_PATH.exists():
        return set()
    content = GLOSSARY_PATH.read_text(encoding="utf-8")
    terms: set[str] = set()
    for line in content.splitlines():
        if "|" not in line:
            continue
        # Markdown table separator rows look like `| --- | --- |` — skip.
        if set(line.replace("|", "").strip()) <= {"-", " ", ":"}:
            continue
        for cell in line.split("|"):
            cell = cell.strip()
            if not cell:
                continue
            # Split on slash so "MCP / Model Context Protocol" becomes two
            # terms; also split on commas for cells like "FR-XXX, ISS-XXX".
            for chunk in re.split(r"\s*[/,]\s*", cell):
                chunk = chunk.strip()
                if not chunk:
                    continue
                terms.add(chunk)
                # Also add embedded acronyms so a chunk like
                # "WordPress JSON API" registers `JSON` and `API` too.
                for match in ACRONYM_PATTERN.findall(chunk):
                    terms.add(match)
    return terms


def get_staged_added_lines(paths: list[str]) -> list[tuple[str, int, str]]:
    """Return [(file, line_number_in_new_file, line_text), ...] for added lines."""
    if not paths:
        return []
    cmd = ["git", "diff", "--cached", "--unified=0", "--no-color", "--"] + paths
    try:
        out = subprocess.check_output(cmd, encoding="utf-8", errors="replace")
    except subprocess.CalledProcessError:
        return []
    results: list[tuple[str, int, str]] = []
    current_file: str | None = None
    current_line = 0
    for line in out.splitlines():
        if line.startswith("+++ b/"):
            current_file = line[6:]
            current_line = 0
            continue
        if line.startswith("@@"):
            # @@ -old,+new @@ — capture the new-file start line
            match = re.search(r"\+(\d+)", line)
            if match:
                current_line = int(match.group(1)) - 1
            continue
        if line.startswith("+") and not line.startswith("+++"):
            current_line += 1
            if current_file:
                results.append((current_file, current_line, line[1:]))
        elif not line.startswith("-") and not line.startswith("\\"):
            current_line += 1
    return results


def should_skip_file(path: str) -> bool:
    return any(pattern.search(path) for pattern in SKIP_FILE_PATTERNS)


def should_skip_line(line: str) -> bool:
    return any(pattern.match(line) for pattern in SKIP_LINE_PATTERNS)


def find_violations(
    added_lines: list[tuple[str, int, str]],
    glossary: set[str],
) -> list[tuple[str, str, int]]:
    """Return [(term, file, line), ...] for terms that need a glossary entry."""
    violations: list[tuple[str, str, int]] = []
    seen_locations: set[tuple[str, str]] = set()  # dedupe (term, file)
    for file, line_no, text in added_lines:
        if should_skip_file(file):
            continue
        if should_skip_line(text):
            continue
        for match in ACRONYM_PATTERN.findall(text):
            if match in ALLOWLIST or match in glossary:
                continue
            # FR-NNN / RPT-NNN / ISS-NNN are covered by the generic
            # "FR-XXX (any 3-digit feature number)" glossary entry; we
            # don't require a per-number row for every numbered identifier.
            if NUMBERED_ID_PATTERN.match(match):
                continue
            key = (match, file)
            if key in seen_locations:
                continue
            seen_locations.add(key)
            violations.append((match, file, line_no))
    return violations


def main(argv: list[str]) -> int:
    paths = argv[1:]
    if not paths:
        # Hook called with no args — pull staged paths ourselves.
        try:
            out = subprocess.check_output(
                ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
                encoding="utf-8",
            )
            paths = [line.strip() for line in out.splitlines() if line.strip()]
        except subprocess.CalledProcessError:
            return 0
    glossary = load_glossary_terms()
    added = get_staged_added_lines(paths)
    violations = find_violations(added, glossary)
    if not violations:
        return 0
    print("\nFAIL check-glossary: new technical terms found without a plain-English glossary entry.\n")
    for term, file, line_no in violations:
        print(f"  {term} — {file}:{line_no}")
    print(
        "\nTo fix: add a row to the table in `PLAIN-ENGLISH-RULE.md` describing"
        "\neach term in plain English. Format: | <plain-English substitute> | <term> |"
        "\n"
        "\nIf the term is genuinely a false-positive (a one-off variable name,"
        "\na hash, etc.), add it to the ALLOWLIST in `.githooks/check-glossary.py`."
        "\n"
        "\nSee `GLOSSARY-RULE.md` for the full policy."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
