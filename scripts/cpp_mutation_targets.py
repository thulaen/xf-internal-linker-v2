"""K1: changed C++ files → Mull GTest binaries.

`scripts/run-cpp-mutation.sh` previously ran all 9 GTest binaries even
when no C++ file changed. This script reads
`backend/extensions/CMakeLists.txt`, builds a binary → source-set
map by parsing every `add_executable(...)` call, then emits ONLY the
binaries whose source set intersects the changed C++ files in the
staged diff.

Fallbacks (intentionally conservative — run more rather than less when
impact is unclear):

  * Header change (`*.h`) → run all binaries (header usage is implicit).
  * `backend/extensions/include/*` change → run all binaries.
  * CMakeLists.txt itself changed → run all binaries (target list may
    have shifted).
  * Parse failure → run all binaries.

Usage:
    python scripts/cpp_mutation_targets.py
    # outputs one binary name per line, e.g.:
    #   test_scoring
    #   test_passagesim

The shell consumer:
    targets=()
    while IFS= read -r line; do
      [ -n "$line" ] && targets+=("$line")
    done < <(python scripts/cpp_mutation_targets.py)
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CMAKE_FILE = REPO_ROOT / "backend" / "extensions" / "CMakeLists.txt"
EXT_DIR = REPO_ROOT / "backend" / "extensions"

# Match: add_executable(<name> <file1> <file2> ...)
# Permissive — accepts whitespace + parenthesised positional sources.
_ADD_EXEC_RE = re.compile(
    r"add_executable\s*\(\s*(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s+(?P<sources>[^)]+?)\)",
    re.MULTILINE,
)

# `set(XF_GTEST_TARGETS test_a test_b ...)` — the canonical list.
_TARGETS_LIST_RE = re.compile(
    r"set\s*\(\s*XF_GTEST_TARGETS\s+(?P<targets>[^)]+?)\)",
    re.MULTILINE,
)

# Header path tokens — if any changed file matches, run all.
_HEADER_BROADCAST = (".h", ".hpp", ".hxx")

_HEADER_BROADCAST_PREFIX = "backend/extensions/include/"


def _parse_cmake(text: str) -> tuple[dict[str, set[str]], list[str]]:
    """Return (binary -> set-of-source-files, GTest-target-order)."""
    bin_map: dict[str, set[str]] = {}
    for m in _ADD_EXEC_RE.finditer(text):
        name = m.group("name").strip()
        raw_sources = m.group("sources")
        # Sources may be space- or newline-separated. Filter out empty.
        sources = [s.strip() for s in re.split(r"\s+", raw_sources) if s.strip()]
        bin_map[name] = set(sources)
    # The XF_GTEST_TARGETS list controls which binaries Mull runs against.
    order: list[str] = []
    target_list_match = _TARGETS_LIST_RE.search(text)
    if target_list_match:
        raw = target_list_match.group("targets")
        order = [t.strip() for t in re.split(r"\s+", raw) if t.strip()]
    return bin_map, order


def _changed_cpp_files() -> list[str]:
    """Return staged C++/header files under backend/extensions/."""
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
    files = []
    for line in (result.stdout or "").splitlines():
        path = line.strip().replace("\\", "/")
        if not path:
            continue
        if path.startswith("backend/extensions/") and path.endswith(
            (".cpp", ".h", ".hpp", ".hxx")
        ):
            files.append(path)
    return files


def _should_broadcast(changed: list[str]) -> bool:
    """If any changed file forces running ALL binaries, return True."""
    for f in changed:
        if f.endswith(_HEADER_BROADCAST):
            return True
        if f.startswith(_HEADER_BROADCAST_PREFIX):
            return True
    # CMakeLists itself changed → broadcast.
    return False


def _normalise_source(name: str) -> str:
    """`tests/test_simsearch.cpp` and `simsearch.cpp` are kept as-is.

    The change-detection compares against either form because changed
    files are under `backend/extensions/`. We compare basename + the
    relative path segment.
    """
    return name.replace("\\", "/")


def _binaries_for_changed(
    bin_map: dict[str, set[str]],
    order: list[str],
    changed: list[str],
) -> list[str]:
    """Return the subset of binaries whose sources include a changed file."""
    # Strip the leading "backend/extensions/" so we can compare to
    # the relative paths from CMakeLists.
    changed_rel = {
        f[len("backend/extensions/") :] for f in changed
        if f.startswith("backend/extensions/")
    }
    hits: list[str] = []
    for binary in order:
        sources = bin_map.get(binary, set())
        # Match by exact relative path OR by basename for robustness.
        for src in sources:
            src_norm = _normalise_source(src)
            if src_norm in changed_rel:
                hits.append(binary)
                break
            # basename match (e.g. CMake declares `simsearch.cpp` and the
            # change is `backend/extensions/simsearch.cpp`).
            if any(c == src_norm or c.endswith("/" + src_norm) for c in changed_rel):
                hits.append(binary)
                break
    return hits


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--all", action="store_true",
        help="Print every binary regardless of staged changes (for dry-run).",
    )
    opts = parser.parse_args()

    if not CMAKE_FILE.is_file():
        # No CMakeLists → can't classify. Fall back: print nothing so
        # the caller's all-binaries default kicks in.
        print("# CMakeLists.txt missing; caller falls back to all-binaries", file=sys.stderr)
        return 0

    try:
        text = CMAKE_FILE.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        print(f"# CMakeLists.txt unreadable: {exc}", file=sys.stderr)
        return 0

    bin_map, order = _parse_cmake(text)
    if not order:
        # No XF_GTEST_TARGETS list — print every binary we found.
        order = sorted(bin_map.keys())

    if opts.all:
        for binary in order:
            print(binary)
        return 0

    changed = _changed_cpp_files()
    # CMakeLists itself in the staged diff → broadcast.
    if any(c.endswith("CMakeLists.txt") for c in changed) or _should_broadcast(changed):
        for binary in order:
            print(binary)
        return 0

    # No C++ changes at all → print nothing; caller skips mutation.
    if not changed:
        return 0

    hits = _binaries_for_changed(bin_map, order, changed)
    if not hits:
        # Changed C++ files belong to no specific binary (e.g. a
        # standalone helper). Broadcast — safer to run more.
        print("# no binary matched changed C++ files; broadcasting", file=sys.stderr)
        for binary in order:
            print(binary)
        return 0

    for binary in hits:
        print(binary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
