"""
Merge shard outputs for a given run_id.

Reads all per-run manifest entries from Mint, verifies every
required_for_merge=True entry has its blob present, and reports errors.

References:
  Content addressing: https://bazel.build/remote/rbe
  RFC 6234 SHA-256 (https://datatracker.ietf.org/doc/html/rfc6234)
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable


def check_manifests(
    manifest_entries: list[dict],
    blob_exists: Callable[[str], bool],
) -> list[str]:
    """Return a list of error messages for missing required blobs.

    Args:
        manifest_entries: List of manifest entry dicts (from JSONL manifest).
        blob_exists:      Callable that takes a sha256 string and returns bool.

    Returns:
        Empty list when all required blobs are present.
        One error string per missing required blob otherwise.
    """
    errors: list[str] = []
    for entry in manifest_entries:
        if not entry.get("required_for_merge", False):
            continue
        sha256 = entry.get("sha256", "")
        if not blob_exists(sha256):
            logical = entry.get("logical_path", "<unknown>")
            errors.append(
                f"Missing required blob sha256={sha256} "
                f"(logical_path={logical!r}, shard={entry.get('shard_id')!r})"
            )
    return errors


def check_failed_shards(manifest_entries: list[dict]) -> list[str]:
    """Return error messages for required failed shards missing an autoissue_id.

    A shard is a tracked failure when failed=True and required_for_merge=True.
    Each such entry must carry autoissue_id so the merge step can report it.
    """
    errors: list[str] = []
    for entry in manifest_entries:
        if not entry.get("required_for_merge", False):
            continue
        if not entry.get("failed", False):
            continue
        if not entry.get("autoissue_id"):
            shard = entry.get("shard_id", "<unknown>")
            tool = entry.get("tool", "<unknown>")
            errors.append(
                f"Failed required shard shard_id={shard!r} tool={tool!r} "
                f"has no autoissue_id — file the failure with file_test_failure "
                f"before merging"
            )
    return errors


def summarize_entries(manifest_entries: list[dict], errors: list[str]) -> dict:
    """Return small merge counts for final reporting."""
    required = [entry for entry in manifest_entries if entry.get("required_for_merge", False)]
    failed = [entry for entry in manifest_entries if entry.get("failed", False)]
    return {
        "total_entries": len(manifest_entries),
        "required_entries": len(required),
        "failed_entries": len(failed),
        "error_count": len(errors),
        "status": "failed" if errors else "passed",
    }


def render_final_report(run_id: str, manifest_entries: list[dict], errors: list[str]) -> str:
    """Render a plain-English merge report for the distributed test run."""
    summary = summarize_entries(manifest_entries, errors)
    lines = [
        f"# Distributed quality merge report {run_id}",
        "",
        f"Status: {summary['status']}",
        f"Manifest entries checked: {summary['total_entries']}",
        f"Required entries checked: {summary['required_entries']}",
        f"Failed shard entries: {summary['failed_entries']}",
        f"Merge errors: {summary['error_count']}",
    ]
    if errors:
        lines.append("")
        lines.append("## Errors")
        lines.extend(f"- {error}" for error in errors)
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: merge-shard-outputs.py <run_id> [--mint-host H] [--ssh-user U]."""
    import argparse
    from mint_blob_store import MintBlobStore

    parser = argparse.ArgumentParser(description="Merge shard outputs for a run.")
    parser.add_argument("run_id", help="Run identifier")
    parser.add_argument("--mint-host", default="mint", help="Mint SSH hostname")
    parser.add_argument("--ssh-user", default="xf", help="Mint SSH user")
    parser.add_argument("--mint-root", default="/srv/xf", help="Mint artifact root")
    parser.add_argument("--report-out", help="Write a final Markdown report to this path")
    args = parser.parse_args(argv)

    store = MintBlobStore(args.mint_host, args.ssh_user, args.mint_root)
    entries = store.read_manifest(args.run_id)

    if not entries:
        print(f"ERROR: no manifest entries found for run_id={args.run_id!r}", file=sys.stderr)
        return 1

    errors = check_manifests(entries, blob_exists=store.blob_exists)
    errors.extend(check_failed_shards(entries))
    report = render_final_report(args.run_id, entries, errors)
    if args.report_out:
        Path(args.report_out).write_text(report, encoding="utf-8")

    if errors:
        for err in errors:
            print(f"ERROR: {err}", file=sys.stderr)
        return 1

    print(f"OK: all {len(entries)} manifest entries verified for run_id={args.run_id!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
