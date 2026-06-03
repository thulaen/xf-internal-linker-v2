"""
Blob garbage collection for the Mint SHA-256 artifact store.

Enumerates all blobs, compares against the set of SHA-256 values referenced
by retained manifests, and returns a list of blobs safe to delete.

Invariant: a blob referenced by ANY retained manifest entry is NEVER returned
in the delete list, regardless of age.

References:
  Content addressing: https://bazel.build/remote/rbe
  RFC 6234 SHA-256 (https://datatracker.ietf.org/doc/html/rfc6234)
"""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path, PurePosixPath

DEFAULT_RETENTION_DAYS = 14


def collect_garbage(
    all_blobs: list[str],
    retained_sha256s: set[str],
    grace_period_days: int,
) -> list[str]:
    """Return the list of blob paths that are safe to delete.

    A blob is safe to delete when ALL of these are true:
      - Its SHA-256 is NOT in retained_sha256s.
      - grace_period_days == 0  OR  the blob's age exceeds the grace period.

    In practice the caller populates retained_sha256s by reading all
    manifests for retained runs.  This function never touches the filesystem
    itself — it is a pure decision function so callers can test it without SSH.

    Args:
        all_blobs:        Absolute remote paths of every blob in the store.
        retained_sha256s: Set of SHA-256 hex strings still referenced by
                          at least one retained manifest entry.
        grace_period_days: Blobs newer than this many days are kept even
                           if unreferenced.  Pass 0 to delete immediately.

    Returns:
        List of blob paths that may be deleted.  Empty list when nothing
        qualifies for deletion.
    """
    to_delete: list[str] = []
    for blob_path in all_blobs:
        sha256 = PurePosixPath(blob_path).name
        if sha256 in retained_sha256s:
            continue
        if grace_period_days > 0:
            try:
                age_days = _blob_age_days(blob_path)
                if age_days < grace_period_days:
                    continue
            except OSError:
                # Can't stat remote path locally; skip the grace-period check
                # and let the caller decide (SSH stat would handle this).
                pass
        to_delete.append(blob_path)
    return to_delete


def _blob_age_days(blob_path: str) -> float:
    """Return approximate age in days based on local mtime (for local FS tests).

    In production the caller uses SSH to stat remote paths; this function is
    a fallback for tests that use a local temp directory as a fake blob store.
    """
    import time
    stat = os.stat(blob_path)
    return (time.time() - stat.st_mtime) / 86400


def collect_retained_sha256s(
    manifest_files: list[os.PathLike[str] | str],
    *,
    retention_days: int = DEFAULT_RETENTION_DAYS,
    now: datetime | None = None,
) -> set[str]:
    """Return SHA-256 values referenced by manifests inside retention.

    Entries without a parseable created_at are retained to avoid deleting
    evidence that may have been written by an older tool version.
    """
    cutoff = (now or datetime.now(UTC)) - timedelta(days=retention_days)
    retained: set[str] = set()
    for manifest_file in manifest_files:
        try:
            lines = Path(manifest_file).read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                created_at = _parse_created_at(entry.get("created_at"))
                if created_at is None or created_at >= cutoff:
                    retained.add(entry["sha256"])
            except (json.JSONDecodeError, KeyError):
                continue
    return retained


def _parse_created_at(raw: object) -> datetime | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        parsed = datetime.strptime(raw, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError:
        return None
    return parsed


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for SSH-callable GC on Mint."""
    import argparse
    parser = argparse.ArgumentParser(description="GC the Mint blob store.")
    parser.add_argument(
        "--blob-store-root",
        default="/srv/xf/artifacts/blob-store/sha256",
        help="Root of the blob store on Mint",
    )
    parser.add_argument(
        "--runs-root",
        default="/srv/xf/artifacts/runs",
        help="Root of the per-run manifests on Mint",
    )
    parser.add_argument(
        "--grace-period-days",
        type=int,
        default=DEFAULT_RETENTION_DAYS,
        help="Keep unreferenced blobs newer than N days (default 14)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be deleted without deleting",
    )
    args = parser.parse_args(argv)

    blob_store = Path(args.blob_store_root)
    runs_root = Path(args.runs_root)

    all_blobs = [
        str(p)
        for p in blob_store.rglob("*")
        if p.is_file()
    ]

    retained = collect_retained_sha256s(
        list(runs_root.rglob("manifest.json")),
        retention_days=args.grace_period_days,
    )

    to_delete = collect_garbage(all_blobs, retained_sha256s=retained,
                                grace_period_days=args.grace_period_days)

    freed = 0
    for path in to_delete:
        size = 0
        try:
            size = os.path.getsize(path)
        except OSError:
            pass
        if args.dry_run:
            print(f"[DRY RUN] would delete: {path}")
        else:
            try:
                os.unlink(path)
                freed += size
                print(f"deleted: {path}")
            except OSError as exc:
                print(f"ERROR deleting {path}: {exc}", file=sys.stderr)

    if args.dry_run:
        print(f"[DRY RUN] {len(to_delete)} blobs would be freed")
    else:
        print(f"GC complete: {len(to_delete)} blobs deleted, ~{freed // 1024} KB freed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
