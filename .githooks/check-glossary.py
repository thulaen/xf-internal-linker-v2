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
# and obvious â€” anything genuinely new should land in the glossary itself.
ALLOWLIST: frozenset[str] = frozenset({
    # Web standards
    "CSS", "HTML", "URL", "URLs", "JSON", "HTTP", "HTTPS", "CSV", "JSX", "TSX",
    "SCSS", "DOM", "AST", "GUI", "CLI", "UI", "UX", "ID", "IDs", "SDK", "REST",
    "RPC", "JWT", "TLS", "SSL", "CRC", "MD5", "SHA", "UUID", "ISO", "RFC",
    "UTF-8", "INTERPOLATION", "ICU", "ISO-8601",
    "GMT", "UTC", "MIME", "PNG", "JPG", "JPEG", "GIF", "SVG", "PDF", "MP3",
    "MP4", "ZIP", "TAR", "GZ", "TXT", "YAML", "YML", "TOML", "INI", "IPW",
    "UUID-PK", "FOREVER",
    # Hardware / OS
    "OS", "CPU", "GPU", "RAM", "ROM", "USB", "IP", "IPv4", "IPv6", "TCP",
    "UDP", "DNS", "BIOS", "ARM", "ARM64", "AMD64", "x86", "x86_64",
    # Common backend frameworks already covered by the existing glossary
    "API", "APIs", "DRF", "ORM", "SQL", "PSQL", "ETL",
    # Common units / numeric prefixes
    "KB", "MB", "GB", "TB", "PB", "MS", "NS", "US", "ERR", "CPP",
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
    # Hex / address / register shorthand that shows up in synthetic
    # log lines (`<HEX>` placeholders inside `loki_picker._normalize_line`,
    # "Segfault at 0x... â€” RIP" test fixtures, etc). These are NOT new
    # technical concepts â€” they are well-known existing terms used as
    # markers or test scaffolding. Adding here so the glossary check
    # doesn't keep flagging legitimate test/code use.
    "HEX", "RIP",
    # Common English words / SQL constants / log levels / Django magic that
    # happen to be all-caps in our codebase or docstrings.
    "AND", "OR", "NOT", "NULL", "TRUE", "FALSE", "NONE", "DOES", "WHERE",
    "FROM", "INTO", "JOIN", "ASC", "DESC", "EXACT", "REGEX",
    "NAME", "PATH", "REGISTRY", "BACKEND", "FRONTEND",
    "PRIOR", "STATE", "NEW", "OLD",  # everyday English, all-caps in prose / fixture suffixes
    "COMMAND", "README",  # CMake keyword in add_test(...) + the README filename shorthand
    # Ruff rule-family codes used in backend/ruff.toml's ignore list — they
    # are tool-specific identifiers (documented in Ruff's rule index), not
    # new project vocabulary. Adding them here so the glossary check doesn't
    # treat them as undefined acronyms. Phase 3 of the test-hardening plan.
    "ANN", "ARG", "ASYNC", "BLE", "COM", "CPY", "DJ", "DTZ",
    "EM", "ERA", "EXE", "FBT", "FIX", "FURB", "ICN", "INP",
    "ISC", "NPY", "PERF", "PGH", "PIE", "PLC", "PLR", "PLW",
    "PTH", "PYI", "RET", "RUF", "SIM", "SLF", "TC", "TCH",
    "TRY",
    "SRCS",  # bash-array name in the cpp-clang-tidy CI step
    "MUTATION-TESTING-CPP",  # future doc filename referenced from MUTATION-TESTING.md
    "TESTING-STANDARD", "CONTRACT-TESTING",  # doc filename refs from services/go/
    "PPA",  # apt Personal Package Archive — Ubuntu standard, well-known initialism
    "DEFAULT-ON",  # the project term "default-on rule" is already glossed (lowercase form)
    "CONTEXT", "ROADMAP",  # filename refs (AI-CONTEXT.md / ROADMAP.md) — common English words
    "FLIPS", "LONG-TERM",  # English words used in milestone status (ROADMAP.md)
    "MUTATION-TESTING", "FEATURE-REQUESTS",  # filename refs (already-glossed docs)
    "NNN",  # placeholder for a numeric suffix (RPT-NNN, FR-NNN) — already explained inline
    "MULTILINE",  # Python re module flag (re.MULTILINE)
    "APPENDED",  # English past tense in management-command stdout messages
    "READ-ONLY",  # English compound term, common in docs
    "SHIPPED",  # roadmap status — English past tense
    "EXACTLY",  # English adverb used as bold emphasis in rule prose
    "CORS",     # Cross-Origin Resource Sharing — well-known web standard initialism
    "PLACEHOLDER",  # English word used in fixture schemas and templates
    "GOES",  # English verb used in rule prose ("ONLY GOES UP")
    "STAGED",  # English participle used as a CLI arg sentinel
    "DCOVERAGE",  # CMake `-DCOVERAGE=ON` flag (the `D` is CMake's define prefix)
    "GATES",  # English plural in filename refs like `docs/CI-GATES.md`
    "STREQUAL", "SOURCE",  # CMake operators / function-arg names
    "VERSION", "LANGUAGES", "CXX", "PROPERTIES", "NAME", "TARGET",  # CMake keywords
    "PRIVATE", "PUBLIC", "INTERFACE",  # CMake target_link/include scopes
    "RELEASE", "DEBUG",  # CMake build types
    "ASSERT", "EXEC", "REQUIRED", "CONFIG",  # CMake / pytest common all-caps
    "CAN", "MUST", "MAY", "SHOULD",  # RFC-2119-style English in docstrings / rules
    # More everyday English words that get capitalised mid-sentence in
    # narrative documentation (e.g. "TURN OFF", "ONE release",
    # "WHICH key" in instructional prose) and aren't technical jargon.
    "OFF", "ONE", "TURN", "OUT", "WHICH", "WHETHER", "LEGACY",
    "INSIDE", "ONLY", "BELOW", "ABOVE",
    # Status / emphasis words that show up in observability gap docs
    # and similar status-table prose ("YET to wire", "PARTIAL coverage",
    # "ALSO note", "THIS section"). All everyday English, no jargon.
    "YET", "PARTIAL", "ALSO", "THIS",
    # Everyday English words that get capitalised mid-sentence in
    # narrative prose (handoff entries, doc headings, README-style
    # bullets). Adding these stops the glossary check from flagging
    # plain English as "new technical jargon".
    "READ", "NEVER", "ALL", "SHOW", "DONE", "OPEN", "OWN",
    "RUN", "SAME", "FIRST", "YOU", "RECENT", "RESOLUTIONS",
    "YES", "DISCOVERED", "NOW", "FRESH", "CORRECT", "CONTROL",
    "CHANNEL", "WITHOUT", "PRE", "OTHER", "SINGLE", "STOP",
    "WHEN", "THINK", "CODE", "SEARCH", "BLAST", "HISTORY", "IMPORT", "SYNC",
    "RESOLVED", "WIRED", "DON", "SIGNAL", "ABSOLUTE", "SPEC",
    # SQL keywords frequently quoted in code comments / handoff prose
    # alongside the DDL allowlist above (those covered: CREATE/INSERT/
    # UPDATE/SELECT etc were missed by the earlier list).
    "SELECT", "INSERT", "UPDATE", "CREATE", "DATABASE", "OWNER",
    "CONFLICT", "ILIKE", "ORDER", "LIMIT",
    # PostgreSQL libpq environment variables â€” show up in psql wrapper
    # commands inside docker-compose healthcheck blocks.
    "PGHOST", "PGUSER", "PGPASSWORD", "PGDATABASE", "HOSTNAME",
    # Hyphenated tokens that are doc-filename references or shell /
    # Docker directives, not technical jargon.
    "OBSERVABILITY-GAPS-EXTENSION", "OBSERVABILITY-OPTIONS",
    "CPP-DAILY-ISSUE-PICKER-SPEC", "CREATE-IF-NOT-EXISTS",
    "OTLP-HTTP", "PRE-EXISTING", "CREATE-DATABASE", "CMD-SHELL",
    "SEI-2003-TR-002",
    # One-off regex character class that the glossary's `[A-Z]{3,}`
    # pattern reads as a token (see `deploy_check_picker.py` â€”
    # `[WEC]` matches Django check IDs of severity W/E/C).
    "WEC",
    # Common project shorthand / academic citation tokens that are not
    # technical jargon a non-coder would need defined.
    "TAC", "ISBN", "WSDM", "STRIDE", "IEEE", "CMU", "SEI",
    # All-caps form of "Celery" â€” the lowercase form is already in the
    # glossary, but the regex catches the uppercase variant separately.
    "CELERY",
    # Everyday English caps used in the session-start-banner script
    # ("OPEN REGISTRY FINDINGS", "TWO recent items"). Plain prose,
    # not jargon.
    "FINDINGS", "TWO",
    # Pre-commit chain infrastructure nouns (added 2026-05-22). These
    # words appear in legitimate prose inside scripts/precommit-docker.sh,
    # check-* hooks, and similar files describing the commit gate flow.
    # Without exempting them here, any edit that shifts the lines they
    # appear on trips the "new technical jargon" detector on a false
    # positive. See backend/config/tests/test_typescript_sonarqube_rules.py
    # for the parallel pattern. The terms are real English nouns / past
    # participles in this context (a "hook" is the pre-commit script, a
    # "finding" is a logged AutoIssue, "blocked" describes the commit
    # state when a hook hard-blocks).
    "HOOK", "FINDING", "BLOCKED",
    # mktemp(1) template placeholder — the X's are replaced with random
    # characters by mktemp itself ("xf-hook-output.XXXXXX"). Standard
    # POSIX shell idiom, not a new technical term.
    "XXXXXX",
    # Python module-level constants in scripts/smart_build.py + its
    # test (added 2026-05-23 as part of Phase M.1). `ROOT` is the repo
    # root Path; `REMAINDER` is argparse.REMAINDER, the standard
    # library sentinel for "consume all remaining argv". Real English
    # nouns, not new technical jargon.
    "ROOT", "REMAINDER",
    # Project-specific section labels printed by the banner script.
    # The lowercase forms (`AGENT-HANDOFF.md`, `auto_issues` app) are
    # already documented; the all-caps headings are just visual labels.
    "HANDOFF", "AGENT", "AUTO-ISSUES",
    "INFO", "WARN", "WARNING", "ERROR", "DEBUG", "TRACE", "FATAL",
    "NOTICE", "SUCCESS", "FAILED", "FAIL", "PASS", "SKIP", "SKIPPED",
    "COMPLETED", "RUNNING", "PENDING", "QUEUED", "PROCESSING", "ABORTED",
    "ATTENTION",
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
    # RFC 2119 keywords â€” common in spec / rule prose
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
    # 2026-05-09 frontend audit session. ROLLOUT and SETTINGS-SPLIT-PLAN
    # are doc-filename references; COMMANDS is a TypeScript variable name
    # (DEEP_LINK_CATALOG â†’ COMMANDS in command-palette.commands.ts).
    "ROLLOUT", "SETTINGS-SPLIT-PLAN", "COMMANDS",
    # 2026-05-09 settings-grid layout fix. DESIGN-PATTERNS is a doc
    # filename; COMP is the Angular `_ngcontent-%COMP%` placeholder
    # token in compiled CSS; MQTTUWQS is a content-hash example in
    # the handoff describing a build artefact filename.
    "DESIGN-PATTERNS", "COMP", "MQTTUWQS",
    # Standard accessibility / OS / English-emphasis tokens.
    "ARIA", "ESC", "TTL", "INPUT", "DID", "WORK",
    # ISO 4217 currency codes â€” extension of the existing USD/EUR/GBP
    # entries above. These are user-facing strings the locale service
    # passes through to `Intl.NumberFormat({style:'currency'})`.
    "JPY", "CNY", "INR", "CAD", "AUD", "BRL", "MXN", "KRW",
    # 2026-05-10 prevention-cleanup batch â€” ALL-CAPS English words that
    # appear in narrative comments + docstrings across the new files
    # (tunable_registry.py, ONGOING-CODE-QUALITY.md, self_test_smoke.py,
    # verify_unused_python.py, acknowledge_resolved_warnings.py).
    "USED", "EMPTY", "TUNABLE", "KEYSET", "ADD", "ENTRY", "HERE",
    "NEITHER", "MEDIUM", "HIGH", "LOW", "ONCE",
    # Project marker comments / placeholder shapes documented in CLAUDE.md.
    "AUTOTUNER-EXCLUDED", "DEFERRED-KNOWN", "RPT-NNN", "ISS-NNN",
    # More plain-English ALL-CAPS narrative tokens used in handoff /
    # docs prose ("MISSING test files", "WHY this matters", etc).
    "MISSING", "WHY",
    # Image / asset file format extensions accepted by site-asset upload views.
    "WEBP", "ICO", "BMP", "TIFF", "AVIF", "HEIC", "HEIF",
    # More plain-English narrative ALL-CAPS that show up in handoff /
    # docstring prose ("FILES touched", "VIEWS extracted", etc).
    "FILES", "VIEWS",
    # Common file format extensions surfaced in user-facing copy
    # (e.g. "Export to JSONL", "JSONL log file").
    "JSONL", "NDJSON", "PARQUET",
    # More plain-English narrative ALL-CAPS that show up in tests +
    # docstring prose ("STATUS column", "ROUTE prefix", etc).
    "STATUS", "ROUTE", "ROUTES", "ENDPOINT", "ENDPOINTS",
    "TOGGLED", "ANY",
    # Out-Of-Memory â€” common shorthand in operator-facing diagnostics.
    "OOM",
    # Network metrics + project shorthand surfaced in helper-node
    # heartbeat code + benchmark + ABI compatibility diagnostics.
    "RTT", "WPM", "XFIL", "ABI",
    # Web standards + crypto file format extensions surfaced in
    # connection-card UI copy (URI scheme labels, PEM-format key blobs,
    # PRIVATE KEY field labels, etc).
    "URI", "PEM", "PRIVATE", "KEY", "HEALTH",
    # Algorithm shorthand surfaced in ranking-weights tab UI labels.
    # SCC = Strongly Connected Components (graph algorithm).
    # PRF = Pseudo-Relevance Feedback (information-retrieval signal).
    "SCC", "PRF",
    # Academic conference / venue / library shorthand surfaced as
    # citation labels next to spec links in ranking-weights tab.
    # ICWSM = International Conference on Weblogs and Social Media.
    # ACL = Association for Computational Linguistics.
    # EACL = European chapter of ACL. JMLR = Journal of Machine
    # Learning Research. WMT = Workshop on Machine Translation.
    # VADER = sentiment-analysis lexicon library. YAKE = keyword
    # extraction algorithm. All third-party citations, not project jargon.
    "VADER", "ICWSM", "ACL", "YAKE", "EACL", "JMLR", "WMT",
    # More academic / venue shorthand from same citation block.
    # KDD = Knowledge Discovery and Data Mining. LTR = Learning To Rank.
    # UAI = Uncertainty in Artificial Intelligence. ICDM = International
    # Conference on Data Mining. SIAM = Society for Industrial and
    # Applied Mathematics. CACM = Communications of the ACM.
    "KDD", "LTR", "UAI", "ICDM", "SIAM", "CACM",
    # Karma helper script output headings - plain English not jargon.
    "TOTAL", "FAILURES",
    # `LogLevel.LOG` enum member from `@grafana/faro-web-sdk` (used in
    # faro-bootstrap.ts to suppress non-error console captures). The SDK
    # owns this identifier; we can't rename it.
    "LOG",
    # 2026-05-17 — slice 1.6 marker labels emitted by hook scripts and
    # management commands. These are NOT new technical concepts; they
    # are the project's own internal marker vocabulary (e.g. the
    # `[CODE REVIEW LESSON LOGGED:]` and `[TDD LESSON DEDUPED:]`
    # markers from log_code_review_lessons / log_tdd_lesson). The
    # plain-English form of each is captured in PLAIN-ENGLISH-RULE.md
    # as a one-line gloss; here we just stop the regex from treating
    # the ALL-CAPS form in docstrings + command output as new jargon.
    "LESSON", "LESSONS", "LOGGED", "DEDUPED", "FILED", "PICKED",
    "GRANDFATHERED", "READ", "BUMP", "MAPPING", "COMPLIANCE",
    "CYCLE", "STRICT", "EVIDENCE", "REFACTOR", "TRIVIAL", "CHANGE",
    "SCOPED", "COVERAGE", "SUMMARY", "BEFORE", "START", "PAPER",
    "TRAIL", "SNAPSHOTS", "SPEC", "CITED", "QUOTA", "VERIFIED",
    "DROUGHT", "DROUGHT-LOGGED", "FRESHNESS", "EXEMPTION",
    "PROFILING", "PROOF", "HOTSPOT", "OPTIMIZATION", "PERFORMANCE",
    "SELF-REVIEW", "RESULT", "STANDARDS", "READY", "GATE",
    "QUALITY", "BDD", "TDD",  # already covered but keep explicit
    "RESOLVED", "HISTORY", "CASE", "CASES", "FALSE-POSITIVE",
    "POSITIVE", "MARKER", "TASK", "NON-CODEBASE-EDIT",
    "RULE", "INTRODUCTION", "BATCH", "DRY", "SOURCE",
    "ACKNOWLEDGED", "WRITTEN", "FAILURE", "FAILURE-FINGERPRINT",
    "RETRY", "EXPECTED", "UNEXPECTED", "INSTEAD", "SWALLOW",
    "CUTOFF", "MINIMAL", "FULL", "HARD-CAPPED", "STRICT-RULE",
    "FIRST-RULE", "ALERT", "ENTRYPOINT",
    "UNBLOCK", "DRY-RUN",  # Rule F three-part FAIL keyword + --dry-run flag
    # Prototype HTML ranking signal meta-algorithm IDs (internal identifiers, not user-facing acronyms)
    "META-09", "META-12", "META-13", "META-14", "META-16", "META-23",
    "META-24", "META-26", "META-31", "META-38", "META-39",
    "DETECTION",  # Hub detection method label in Behavioral Hubs prototype page
    # Rule-file filenames (each has a plain-English description in the
    # docs/*-RULE.md file itself; the all-caps form here is just a
    # filename reference in docstrings + log lines).
    "TDD-STRICT-RULE", "TEST-CASE-FIRST-RULE",
    "PAPER-TRAIL-EVIDENCE-RULE",
    # Project shorthand for common things (slice-1.6 + Go-services tier).
    "DTO",  # Data Transfer Object — established CS term
    "CEP",  # Complex Event Processing — established CS term
    "ART",  # Adaptive Radix Tree — established CS term
    "OCR",  # Optical Character Recognition — established term
    "GOMEMLIMIT", "GOOS",  # Go env vars
    "ISBN-10", "ISBN-13", "ISBN",  # standard ISBN formats
    "PROTOC",  # protocol buffer compiler — Go-services tier
    "PHONY",  # GNU Make .PHONY target — common shell vocabulary
    "YARN",  # Node package manager — well-known
    "ANSI",  # American National Standards Institute — well-known
    "APISIX",  # Apache APISIX — vendor name
    "IEC",  # International Electrotechnical Commission — standards body
    "IGNORECASE",  # Python re module flag, like MULTILINE already in the list
    "ISO-IEEE-IETF",  # multi-org standards body shorthand
    "GLOSSARY",  # English word capitalized in section headings
    "SERVING", "UNKNOWN",  # gRPC health-check enum values
    # Commit A internal marker/file-label tokens. These are command output
    # labels and rule-file names, not new user-facing vocabulary.
    "PER-FILE-LESSON-LOOKUP-RULE", "TDD-PIPELINE-RULE",
    "PIPELINE", "METHOD", "DOTALL", "EXPORTED",
    # Plain English verbs / nouns used ALL-CAPS for emphasis in test
    # docstrings (scripts/test_machine_routing.py and similar). Not
    # technical jargon — "INJECTED" means a fake was substituted,
    # "RAISE" means the function throws an exception, "SSH" is the
    # well-known Secure Shell protocol already covered in the glossary's
    # one-liner.
    "SSH", "INJECTED", "RAISE",
    # Plain English words used ALL-CAPS in code comments and docstrings
    # (added 2026-06-01, pgexporter + machine_routing session).
    # WOULD / PASSES / UNLESS / DIRECTLY / ZERO — everyday English used
    # for emphasis in docstrings and inline comments, not new technical terms.
    # ALWAYS-ON — project compound noun for the "always-on fix quota" gate
    # (lowercase form "always-on quota" is already explained in CLAUDE.md).
    # PGEXPORTER — shorthand for the postgres_exporter monitoring sidecar;
    # the full name is used in file names (pgexporter_picker.py) so this
    # is a filename-stem reference, not a new concept requiring a glossary row.
    # NCPU — Docker Go-template field `{{.NCPU}}` (number of CPUs returned by
    # `docker info`); it is a well-known Docker API field, not project jargon.
    "WOULD", "PASSES", "UNLESS", "DIRECTLY", "ZERO",
    "ALWAYS-ON", "PGEXPORTER", "NCPU",
    # INTERVAL — plain English noun for "time between events", used as a shell
    # variable name in the sonar-autoscan loop (SONAR_AUTOSCAN_INTERVAL_SECONDS).
    # Not a new technical concept; the word "interval" is already in any dictionary.
    "INTERVAL",
})

# Regex: 3+ consecutive uppercase letters with optional repeated hyphen-
# segments (so DEEP-LINKING-CATALOG, BGE-M3, etc. read as one token), or
# the explicit FR-NNN / RPT-NNN / ISS-NNN spec/report/issue patterns.
ACRONYM_PATTERN = re.compile(r"\b(?:[A-Z]{3,}(?:-[A-Z0-9]+)*|FR-\d{3}|RPT-\d{3}|ISS-\d{3})\b")

# Numbered identifiers (FR-250, RPT-002, ISS-031) are covered by the
# generic "FR-XXX (any 3-digit feature number)" entry already in the
# glossary â€” match each numbered hit against this pattern instead of
# requiring a per-number row.
NUMBERED_ID_PATTERN = re.compile(r"^(FR|RPT|ISS)-\d{3}$")

# Lines we never scan â€” they're not user-facing prose.
SKIP_LINE_PATTERNS = (
    re.compile(r"^\s*//"),       # JS / TS line comments
    re.compile(r"^\s*#"),         # Python / shell comments AND markdown headers (handled below)
    re.compile(r"^\s*/\*"),       # block-comment opener
    re.compile(r"^\s*\*"),        # inside block comment
    re.compile(r"^\s*<!--"),      # HTML comment opener
)

# File extensions / paths we never scan â€” generated / binary / test snapshots.
SKIP_FILE_PATTERNS = (
    re.compile(r"\.lock$"),
    re.compile(r"\.min\.(js|css)$"),
    re.compile(r"package-lock\.json$"),
    re.compile(r"poetry\.lock$"),
    re.compile(r"requirements.*\.txt$"),  # version pins; not prose
    re.compile(r"^backend/.*/migrations/"),
    re.compile(r"^docs/specs/"),  # specs have their own citation rule
    re.compile(r"^docs/reports/"),  # report registry handles its own jargon
    re.compile(r"^audit/.*\.jsonl$"),  # generated audit evidence, not prose
    re.compile(r"^docs/CPP-ROADMAP\.md$"),  # parked-kernel namespace: OPT-XX / META-XX / FR-XX IDs are kernel codenames, not new acronyms for the glossary; each parked tuple links back to a spec entry where the real citation lives
    re.compile(r"^GLOSSARY-RULE\.md$"),  # the rule doc itself uses acronyms as examples
    re.compile(r"^PLAIN-ENGLISH-RULE\.md$"),  # the glossary itself
    re.compile(r"^AGENT-HANDOFF\.md$"),  # session-log artifact, not user-facing prose; bundle content hashes (e.g. main-LKCJGWJN.js) and ALL-CAPS narrative emphasis would otherwise force per-session allowlist churn
    re.compile(r"^frontend/signal-control-light-prototype\.html$"),  # single-file HTML prototype with mock UI text, hex color codes, and music domain terms (VST/DAW/MIDI) that are not new technical acronyms requiring glossary entries
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
    # 2026-05-17 — paper-trail #586 quick win: skip auto-generated proto
    # stubs. Their vocabulary (DESCRIPTOR, UNIMPLEMENTED, DTO, SERVING,
    # etc.) is the tool's responsibility, not the agent's; flagging 100+
    # terms per sidecar package drowns out real new vocabulary.
    re.compile(r"(^|/)_sidecars_pb/"),
    re.compile(r"_pb2\.py$"),
    re.compile(r"_pb2_grpc\.py$"),
    re.compile(r"(^|/)api/gen/"),
    re.compile(r"\.pb\.go$"),
    re.compile(r"_grpc\.pb\.go$"),
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
        # Markdown table separator rows look like `| --- | --- |` â€” skip.
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
            # @@ -old,+new @@ â€” capture the new-file start line
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
        # Hook called with no args â€” pull staged paths ourselves.
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
        print(f"  {term} â€” {file}:{line_no}")
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
