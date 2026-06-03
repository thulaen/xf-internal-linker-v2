#!/usr/bin/env python
"""Check shared sections in the four agent rule files."""

from __future__ import annotations

import argparse
import sys

from _rules_sync_helpers import (
    apply_shared_sections,
    diff_shared_sections,
    load_manifest,
    read_agent_files,
)


def check() -> int:
    errors = diff_shared_sections(load_manifest())
    for error in errors:
        print(f"FAIL check-agent-rules-sync: {error}", file=sys.stderr)
    return 1 if errors else 0


def verify_plan_rules() -> int:
    manifest = load_manifest()
    files = read_agent_files(manifest)
    missing: list[str] = []
    for path, text in files.items():
        for required in manifest["plan_40_41_42_required"]:
            if required not in text:
                missing.append(f"{path}: {required}")
    for item in missing:
        print(f"FAIL verify-plan-40-41-42: missing {item}", file=sys.stderr)
    return 1 if missing else 0


def verify_forbidden_phrases() -> int:
    manifest = load_manifest()
    files = read_agent_files(manifest)
    expected = set(manifest["forbidden_phrases"])
    failures: list[str] = []
    for path, text in files.items():
        present = {phrase for phrase in expected if phrase in text}
        if present != expected:
            missing = sorted(expected - present)
            failures.append(f"{path}: missing {', '.join(missing)}")
    for failure in failures:
        print(f"FAIL verify-forbidden-phrases: {failure}", file=sys.stderr)
    return 1 if failures else 0


def apply_from(source_file: str) -> int:
    errors = apply_shared_sections(load_manifest(), source_file)
    for error in errors:
        print(f"FAIL apply-agent-rules-sync: {error}", file=sys.stderr)
    return 1 if errors else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--apply", metavar="SOURCE_FILE")
    parser.add_argument("--verify-plan-40-41-42", action="store_true")
    parser.add_argument("--verify-forbidden-phrases", action="store_true")
    args = parser.parse_args(argv)
    if args.check:
        return check()
    if args.apply:
        return apply_from(args.apply)
    if args.verify_plan_40_41_42:
        return verify_plan_rules()
    if args.verify_forbidden_phrases:
        return verify_forbidden_phrases()
    parser.error(
        "choose --check, --apply, --verify-plan-40-41-42, "
        "or --verify-forbidden-phrases"
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
