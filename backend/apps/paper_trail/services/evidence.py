"""Paper Trail Evidence Rule helpers (added 2026-05-17).

Module-level validators used by both `manage.py defer_work` (at filing) and
`manage.py verify_paper_trail_evidence` (at commit-time hook re-check) to
keep the validation contract in one place.

Spec: docs/PAPER-TRAIL-EVIDENCE-RULE.md
"""

from __future__ import annotations

import re

# ── Citation regex set (inclusive mode per user decision 2026-05-17) ───
# Order does not matter — first match wins via validate_citation().
_CITATION_REGEXES: tuple[tuple[str, "re.Pattern[str]"], ...] = (
    ("doi", re.compile(r"^(doi:)?10\.\d{4,9}/[-._;()/:A-Za-z0-9]+$", re.IGNORECASE)),
    ("arxiv_new", re.compile(r"^arxiv:\d{4}\.\d{4,5}(v\d+)?$", re.IGNORECASE)),
    ("arxiv_old", re.compile(r"^arxiv:[a-z\-]+/\d{7}(v\d+)?$", re.IGNORECASE)),
    ("patent", re.compile(r"^(US|EP|WO|JP|CN|KR)\d{6,12}([A-Z]\d?)?$", re.IGNORECASE)),
    ("standard", re.compile(r"^(ISO|IEC|IEEE|ANSI)[/\s-]*\d+(-\d+)*(:\d{4})?$", re.IGNORECASE)),
    ("rfc", re.compile(r"^rfc\s*\d+$", re.IGNORECASE)),
    ("isbn", re.compile(r"^(?:isbn[:\s]*)?(?:978|979)[-\s]?\d[-\s]?\d{1,5}[-\s]?\d{1,7}[-\s]?[\dX]$", re.IGNORECASE)),
    ("w3c", re.compile(r"^https?://(www\.)?w3\.org/(TR|Recommendation)/", re.IGNORECASE)),
)

# Hosts whose docs count as a "stable URL from an official source" per the
# user's inclusive citation decision. New hosts land via PR + paired test
# case row per docs/PAPER-TRAIL-EVIDENCE-RULE.md § "Official vendor docs".
_VENDOR_ALLOWLIST: tuple[str, ...] = (
    "apache.org",
    "parquet.apache.org",
    "iceberg.apache.org",
    "arrow.apache.org",
    "datatracker.ietf.org",
    "tools.ietf.org",
    "grpc.io",
    "protobuf.dev",
    "kernel.org",
    "python.org",
    "docs.python.org",
    "golang.org",
    "go.dev",
    "pkg.go.dev",
    "pypi.org",
    "cve.org",
    "mitre.org",
    "owasp.org",
    "nvd.nist.gov",
    "docker.com",
    "docs.docker.com",
    "kubernetes.io",
    "wordnet.princeton.edu",
)

# The 10 required BDD section names a test_case AutoIssue's
# `lessons_learned` MUST contain to be considered "full" per this rule.
# Names match the labels produced by `log_test_case._format_lessons()`.
REQUIRED_BDD_FIELDS: tuple[str, ...] = (
    "Given",
    "When",
    "Then",
    "Edge cases",
    "Failure cases",
    "Security",
    "Usability",
    "Scalability",
    "Maintainability",
    "Regression risks",
)


def validate_citation(raw: str) -> tuple[bool, str]:
    """Validate one citation string against the inclusive citation set.

    Returns (ok, kind). `kind` is the matched type name (`"doi"`,
    `"arxiv_new"`, `"patent"`, `"standard"`, `"rfc"`, `"isbn"`, `"w3c"`,
    `"vendor_url"`) or `"unknown"` on failure.
    """
    s = (raw or "").strip()
    if not s or len(s) > 4096:
        return False, "unknown"
    for kind, regex in _CITATION_REGEXES:
        if regex.match(s):
            return True, kind
    for host in _VENDOR_ALLOWLIST:
        if re.match(
            rf"^https?://(www\.)?{re.escape(host)}/",
            s,
            re.IGNORECASE,
        ):
            return True, "vendor_url"
    return False, "unknown"


def validate_test_case_completeness(autoissue) -> list[str]:
    """Return the list of REQUIRED_BDD_FIELDS missing from an AutoIssue.

    The check is case-insensitive and accepts both `Field: value` and
    `Field <value>` forms so an agent writing free-prose contracts can
    still pass as long as every field name is present.

    An empty return list means the row is "full" per this rule.
    """
    text = (autoissue.lessons_learned or "") if autoissue is not None else ""
    if not text:
        return list(REQUIRED_BDD_FIELDS)
    missing: list[str] = []
    for field in REQUIRED_BDD_FIELDS:
        # Spaces in the field name match any whitespace at the lookup site.
        pattern = re.escape(field).replace(r"\ ", r"\s+")
        if not re.search(rf"\b{pattern}\b", text, re.IGNORECASE):
            missing.append(field)
    return missing
