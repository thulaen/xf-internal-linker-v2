"""
Windows storage guard utilities.

Provides:
  validate_safe_delete_path(path) — raise ValueError if path is not under
      C:\\xf\\ or %TEMP%, preventing accidental deletion of source files.

  check_storage_caps(caps, get_used_bytes) — return a list of warning strings
      for any root that exceeds its declared byte cap.  Never raises.

Called by upload-artifacts-to-mint.ps1 and check-windows-storage.ps1 via
  python scripts/windows_storage.py --validate-path <path>
  python scripts/windows_storage.py --check-caps
"""

from __future__ import annotations

import os
import sys
from typing import Callable

# Safe deletion roots on Windows.  Any path must start with one of these
# (case-insensitive) to be accepted by validate_safe_delete_path.  Separators
# are normalised to a forward slash before matching so the guard behaves the
# same whether it runs on Windows (os.sep == "\\") or inside a Linux quality
# container (os.sep == "/").
_SAFE_ROOTS: list[str] = [
    "c:/xf/",
]


def _normalise_sep(path: str) -> str:
    """Lower-case and convert every backslash to a forward slash."""
    return path.lower().replace("\\", "/")

# Per-root storage caps in bytes (used by check-windows-storage.ps1).
DEFAULT_CAPS: dict[str, int] = {
    r"C:\xf\pgdata":            20 * 1024 ** 3,   # 20 GB
    r"C:\xf\frontend-runtime":   5 * 1024 ** 3,   #  5 GB
    r"C:\xf\bazel-output-base":  5 * 1024 ** 3,   #  5 GB
    r"C:\xf\temp-runs":          2 * 1024 ** 3,   #  2 GB
    r"C:\xf\tool-cache":        15 * 1024 ** 3,   # 15 GB
}


def validate_safe_delete_path(path: str) -> None:
    """Raise ValueError if *path* is not under a safe deletion root.

    Safe roots:
      - C:\\xf\\   (all Windows working state)
      - %TEMP%     (environment variable, typically C:\\Users\\...\\AppData\\Local\\Temp)

    This guard stops upload-artifacts-to-mint.ps1 from accidentally
    deleting source files when it prunes local shard outputs after upload.

    Raises:
        ValueError: If *path* does not start with a safe root.
    """
    path_normalised = _normalise_sep(path).rstrip("/")

    safe_roots = list(_SAFE_ROOTS)
    temp = os.environ.get("TEMP", "")
    if temp:
        safe_roots.append(_normalise_sep(temp) + "/")

    for root in safe_roots:
        if path_normalised.startswith(_normalise_sep(root)):
            return

    raise ValueError(
        f"Refusing to delete path outside safe roots (C:\\xf\\ or %TEMP%): {path}. "
        "Safe roots: " + ", ".join(safe_roots)
    )


def _default_get_used_bytes(path: str) -> int:
    """Return total bytes used under *path* (local filesystem walk)."""
    total = 0
    try:
        for dirpath, _dirs, files in os.walk(path):
            for fname in files:
                try:
                    total += os.path.getsize(os.path.join(dirpath, fname))
                except OSError:
                    pass
    except OSError:
        pass
    return total


def check_storage_caps(
    caps: dict[str, int],
    *,
    get_used_bytes: Callable[[str], int] | None = None,
) -> list[str]:
    """Return a list of warning strings for roots that exceed their byte cap.

    This function never raises — cap violations are warnings only.

    Args:
        caps:           Dict mapping root path → cap in bytes.
        get_used_bytes: Injectable callable for testing.  Defaults to a
                        recursive os.walk total.

    Returns:
        List of human-readable warning strings (empty if all roots are
        within cap).
    """
    if get_used_bytes is None:
        get_used_bytes = _default_get_used_bytes

    warnings: list[str] = []
    for root, cap_bytes in caps.items():
        used = get_used_bytes(root)
        if used > cap_bytes:
            used_gb = used / 1024 ** 3
            cap_gb = cap_bytes / 1024 ** 3
            warnings.append(
                f"WARNING: {root} used {used_gb:.2f} GB, cap is {cap_gb:.2f} GB "
                f"(over by {(used - cap_bytes) / 1024**3:.2f} GB)"
            )
    return warnings


def main(argv: list[str] | None = None) -> int:
    """CLI entry for PowerShell callers."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Windows storage guard and cap checker."
    )
    parser.add_argument(
        "--validate-path",
        metavar="PATH",
        help="Validate that PATH is under a safe deletion root.",
    )
    parser.add_argument(
        "--check-caps",
        action="store_true",
        help="Check all default roots against their caps and print warnings.",
    )
    args = parser.parse_args(argv)

    if args.validate_path:
        try:
            validate_safe_delete_path(args.validate_path)
            print(f"OK: {args.validate_path!r} is under a safe deletion root")
        except ValueError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1

    if args.check_caps:
        warnings = check_storage_caps(DEFAULT_CAPS)
        if warnings:
            for w in warnings:
                print(w)
        else:
            print("OK: all storage roots are within cap")

    return 0


if __name__ == "__main__":
    sys.exit(main())
