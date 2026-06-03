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


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: merge-shard-outputs.py <run_id> [--mint-host H] [--ssh-user U]."""
    import argparse
    from mint_blob_store import MintBlobStore

    parser = argparse.ArgumentParser(description="Merge shard outputs for a run.")
    parser.add_argument("run_id", help="Run identifier")
    parser.add_argument("--mint-host", default="mint", help="Mint SSH hostname")
    parser.add_argument("--ssh-user", default="xf", help="Mint SSH user")
    parser.add_argument("--mint-root", default="/srv/xf", help="Mint artifact root")
    args = parser.parse_args(argv)

    store = MintBlobStore(args.mint_host, args.ssh_user, args.mint_root)
    entries = store.read_manifest(args.run_id)

    if not entries:
        print(f"ERROR: no manifest entries found for run_id={args.run_id!r}", file=sys.stderr)
        return 1

    errors = check_manifests(entries, blob_exists=store.blob_exists)
    errors.extend(check_failed_shards(entries))
    if errors:
        for err in errors:
            print(f"ERROR: {err}", file=sys.stderr)
        return 1

    print(f"OK: all {len(entries)} manifest entries verified for run_id={args.run_id!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
