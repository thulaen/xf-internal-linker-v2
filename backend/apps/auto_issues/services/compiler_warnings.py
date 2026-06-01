"""Pure parser for compiler / linter warnings and errors (no DB, no network).

Turns one tool's stderr text into CompilerWarning rows. The ingest layer
(compiler_ingest.py) turns those into deduped SOURCE_COMPILER AutoIssues.
Regex shapes per language were designed by the Phase B research fan-out and
are documented in docs/specs/fr-compiler-warning-autoissues.md.

Supported languages (one combined "fix 10" quota): cpp (clang/gcc/cppcheck),
go (go vet / golangci-lint), rust (cargo / clippy arrow-location), haskell
(GHC / hlint).

Each language has a small named parser (`_parse_cpp`, `_parse_go`,
`_parse_rust`, `_parse_haskell`). Every line is first stripped of ANSI colour
codes and a trailing carriage return so coloured / Windows-CRLF logs parse the
same as plain POSIX logs. File paths may be POSIX (`a/b.cpp`) or Windows
(`C:\\src\\b.cpp`, `src\\b.cpp`); the path group stops only at the
`:<line>:<col>:` location marker, never at a Windows drive-letter colon.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace

SUPPORTED_LANGUAGES = ("cpp", "go", "rust", "haskell")


@dataclass(frozen=True)
class CompilerWarning:
    language: str
    file: str
    line: int
    col: int | None
    code: str
    message: str
    severity: str  # "warning" or "error"


# Matches a leading ANSI colour/SGR escape sequence anywhere in the line.
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")

# A file path followed by ":line[:col]". The path may contain a single
# leading drive letter (`C:`) and Windows back-slashes. We anchor the path on
# the LAST ":line:col" location marker by requiring the line/col groups to be
# digits, so a Windows `C:\...` drive colon is never mistaken for the marker.
_LOCATION = (
    r"(?P<file>(?:[A-Za-z]:)?[^:\n]+?):(?P<line>\d+)(?::(?P<col>\d+))?"
)

# clang / gcc / cppcheck / clang-tidy: <file>:<line>[:<col>]: warning|error: msg [-Wcode]
_CPP_RE = re.compile(
    rf"^{_LOCATION}:\s*"
    r"(?P<severity>warning|error):\s*(?P<message>.*?)"
    r"(?:\s*\[(?P<code>-W[A-Za-z0-9\-]+)\])?$",
    re.IGNORECASE,
)

# go vet:        <file>:<line>:<col>: message
# golangci-lint: <file>:<line>:<col>: message (linter)
# Some golangci-lint configs print the linter in [brackets] instead of
# (parens); both trailing forms are accepted as the dedup `code`.
_GO_RE = re.compile(
    rf"^{_LOCATION}:\s+"
    r"(?P<message>.*?)"
    r"(?:\s+[\(\[](?P<code>[A-Za-z0-9_\-]+)[\)\]])?$"
)

# rust / clippy machine-parseable location line: "  --> <file>:<line>:<col>"
_RUST_ARROW_RE = re.compile(
    rf"^\s*-->\s+{_LOCATION}\s*$"
)
# The diagnostic header that precedes the arrow line:
# "warning: unused variable: `x`" / "error[E0277]: ..." / "warning: ... `#[warn(clippy::foo)]`"
_RUST_HEADER_RE = re.compile(
    r"^(?P<severity>warning|error)(?:\[(?P<code>[A-Za-z0-9]+)\])?:\s*(?P<message>.+?)\s*$",
    re.IGNORECASE,
)
# A clippy lint name that sometimes appears in a later "= note:" line.
_RUST_LINT_NOTE_RE = re.compile(r"#\[(?:warn|deny|allow)\((?P<code>[A-Za-z0-9_:]+)\)\]")

# Two real GHC layouts plus hlint, all single-header-line:
#   GHC 9.x:  <file>:<line>:<col>: warning: [-Wflag]      (message on later lines)
#   GHC/older:<file>:<line>:<col>: warning: message [-Wflag]
#   hlint:    <file>:<line>:<col>: Warning: message       (capital W, no flag)
# The `-Wflag` may sit right after the severity OR at the end of the message;
# both positions are captured into one `code` group. re.IGNORECASE covers
# hlint's capitalised "Warning:".
_HASKELL_RE = re.compile(
    rf"^{_LOCATION}:\s+"
    r"(?P<severity>warning|error):\s*"
    r"(?:\[(?P<code>-W[^\]]+)\]\s*)?"
    r"(?P<message>.*?)"
    r"(?:\s*\[(?P<code2>-W[^\]]+)\])?\s*$",
    re.IGNORECASE,
)


def parse_warnings(text: str, language: str) -> list[CompilerWarning]:
    """Parse every warning/error line of `text` for `language`."""
    parser = _PARSERS.get(language)
    if parser is None:
        return []
    lines = [_clean(raw) for raw in text.splitlines()]
    return parser(lines)


def _clean(raw: str) -> str:
    """Strip ANSI colour codes and trailing whitespace/carriage returns."""
    return _ANSI_RE.sub("", raw).rstrip()


def _warning_from(match: re.Match, language: str, default_severity: str) -> CompilerWarning:
    groups = match.groupdict()
    raw_col = groups.get("col")
    code = (groups.get("code") or groups.get("code2") or "").strip()
    return CompilerWarning(
        language=language,
        file=groups["file"].strip(),
        line=int(groups["line"]),
        col=int(raw_col) if raw_col else None,
        code=code,
        message=(groups.get("message") or "").strip(),
        severity=(groups.get("severity") or default_severity).lower(),
    )


def _parse_cpp(lines: list[str]) -> list[CompilerWarning]:
    out: list[CompilerWarning] = []
    for line in lines:
        match = _CPP_RE.match(line)
        if match is not None:
            out.append(_warning_from(match, "cpp", "warning"))
    return out


def _parse_go(lines: list[str]) -> list[CompilerWarning]:
    out: list[CompilerWarning] = []
    for line in lines:
        match = _GO_RE.match(line)
        if match is None or not (match.group("message") or "").strip():
            continue
        out.append(_warning_from(match, "go", "warning"))
    return out


def _parse_haskell(lines: list[str]) -> list[CompilerWarning]:
    out: list[CompilerWarning] = []
    for line in lines:
        match = _HASKELL_RE.match(line)
        if match is not None:
            out.append(_warning_from(match, "haskell", "warning"))
    return out


def _parse_rust(lines: list[str]) -> list[CompilerWarning]:
    """Pair each diagnostic header with the next `-->` location line.

    Rust/clippy diagnostics span multiple lines: a header (`warning: msg`),
    then an indented `--> file:line:col` location, then a later
    `= note: \\`#[warn(clippy::foo)]\\`` that names the lint. We carry the most
    recent header forward, resolve its location at the arrow line, then
    backfill the clippy lint name onto the most recent warning when its note
    line appears.
    """
    out: list[CompilerWarning] = []
    pending: re.Match | None = None
    for line in lines:
        header = _RUST_HEADER_RE.match(line)
        if header is not None and "-->" not in line:
            pending = header
            continue
        arrow = _RUST_ARROW_RE.match(line)
        if arrow is not None:
            out.append(_build_rust_warning(pending, arrow))
            pending = None
            continue
        _maybe_attach_lint_note(out, line)
    return out


def _maybe_attach_lint_note(out: list[CompilerWarning], line: str) -> None:
    """Backfill a clippy lint name onto the most recent codeless warning."""
    if not out or out[-1].code:
        return
    note = _RUST_LINT_NOTE_RE.search(line)
    if note is not None:
        out[-1] = replace(out[-1], code=note.group("code"))


def _build_rust_warning(header: re.Match | None, arrow: re.Match) -> CompilerWarning:
    severity = (header.group("severity").lower() if header else "warning")
    message = (header.group("message").strip() if header else "")
    code = (header.group("code") or "").strip() if header else ""
    return CompilerWarning(
        language="rust",
        file=arrow.group("file").strip(),
        line=int(arrow.group("line")),
        col=int(arrow.group("col")) if arrow.group("col") else None,
        code=code,
        message=message,
        severity=severity,
    )


_PARSERS = {
    "cpp": _parse_cpp,
    "go": _parse_go,
    "rust": _parse_rust,
    "haskell": _parse_haskell,
}
