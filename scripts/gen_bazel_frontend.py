#!/usr/bin/env python3
"""Check the hand-written frontend BUILD file used by KUBE PLAN Slice 24."""

from __future__ import annotations

import argparse
from pathlib import Path


REQUIRED_SNIPPETS = ("npm_link_all_packages", "runner_toolbox", "package-lock.json")


def missing_snippets(content: str) -> list[str]:
    """Return required frontend BUILD snippets that are absent."""
    return [snippet for snippet in REQUIRED_SNIPPETS if snippet not in content]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(argv)
    target = args.root / "frontend" / "BUILD.bazel"
    missing = missing_snippets(target.read_text(encoding="utf-8") if target.exists() else "")
    for snippet in missing:
        print(f"missing frontend BUILD snippet: {snippet}")
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
