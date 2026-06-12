"""Pure parser for Rust compiler warnings and errors (no DB, no network).

Turns rustc/clippy stderr text into CompilerWarning rows. The ingest layer
turns those into deduped Rust compiler AutoIssues. Every line is first stripped
of ANSI colour codes and trailing whitespace so coloured logs parse like plain
logs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace

SUPPORTED_LANGUAGES = ("rust",)


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

_LOCATION = (
    r"(?P<file>(?:[A-Za-z]:)?[^:\n]+?):(?P<line>\d+)(?::(?P<col>\d+))?"
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
    "rust": _parse_rust,
}
