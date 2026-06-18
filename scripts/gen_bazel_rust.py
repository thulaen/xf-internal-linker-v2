#!/usr/bin/env python3
"""Generate the minimal Rust BUILD marker used by KUBE PLAN Slice 24."""

from __future__ import annotations

import argparse
from pathlib import Path

from lib.bazel_gen import render_exports_files, write_if_changed


def build_content(root: Path) -> str:
    """Return the deterministic rust BUILD.bazel content."""
    exports = ["Cargo.toml", "Cargo.lock"]
    existing = [path for path in exports if (root / "rust" / path).exists()]
    return render_exports_files(existing)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Do not write; fail if stale.")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(argv)
    target = args.root / "rust" / "BUILD.bazel"
    content = build_content(args.root)
    if args.check:
        return 0 if target.exists() and target.read_text(encoding="utf-8") == content else 1
    write_if_changed(target, content)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
