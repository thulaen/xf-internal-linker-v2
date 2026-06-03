"""Enforce explicit local scope caps for quality tools."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Mapping, Sequence


class ScopeCapExceeded(ValueError):
    """Raised when a local quality-tool scope is larger than its cap."""

    def __init__(self, tool: str, count: int, cap: int) -> None:
        self.tool = tool
        self.count = count
        self.cap = cap
        super().__init__(format_failure(tool, count, cap))


def ci_full_tree_opted_in(env: Mapping[str, str] | None = None) -> bool:
    """Return whether remote quality explicitly asked for full-tree scope."""
    values = env or os.environ
    return values.get("XF_QUALITY_ENV") == "ci" and values.get("XF_SCOPE_FULL_TREE") == "1"


def format_failure(tool: str, count: int, cap: int) -> str:
    """Return the operator-facing scope-cap failure text."""
    return (
        f"FAIL scope cap: {tool} targets={count} cap={cap}.\n"
        "UNBLOCK: narrow the commit, increase cap with documented reason, "
        "or move whole-tree run to CI (XF_QUALITY_ENV=ci)."
    )


def enforce_cap(
    scope: Sequence[str],
    max_files: int,
    tool: str,
    *,
    env: Mapping[str, str] | None = None,
) -> list[str]:
    """Return scope when it is within cap, or raise a clear refusal."""
    clean_scope = [item for item in scope if item]
    if ci_full_tree_opted_in(env):
        return clean_scope
    if len(clean_scope) > max_files:
        raise ScopeCapExceeded(tool, len(clean_scope), max_files)
    return clean_scope


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse the small shell-facing command line."""
    parser = argparse.ArgumentParser()
    parser.add_argument("tool")
    parser.add_argument("max_files", type=int)
    parser.add_argument("scope", nargs="*")
    parser.add_argument("--stdin", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Shell entry point. Return 2 when the local cap refuses a run."""
    args = parse_args(argv)
    scope = list(args.scope)
    if args.stdin:
        scope.extend(sys.stdin.read().split())
    try:
        enforce_cap(scope, args.max_files, args.tool)
    except ScopeCapExceeded as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
