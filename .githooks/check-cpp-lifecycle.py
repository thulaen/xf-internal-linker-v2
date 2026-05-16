#!/usr/bin/env python3
"""Rule J - C++ kernel lifecycle invariant (added 2026-05-16).

A C++ kernel only exists when ALL FIVE of these are true together:

  1. `backend/extensions/<name>.cpp` exists, is non-empty, and contains
     a `PYBIND11_MODULE(<name>, ...)` block so the Python loader can
     bind it.
  2. `<name>` appears in the `EXTENSION_NAMES` set in
     `scripts/ensure_compiled_artifacts.py` so the build step knows
     to compile it.
  3. `<name>` appears in the `_NATIVE_RUNTIME_MODULES` tuple in
     `backend/apps/diagnostics/health.py` so the health check knows
     to load it.
  4. The artifact ends up in the content-addressed store and gets
     activated by ensure_compiled_artifacts.py (runtime concern).
  5. `from extensions import <name>` succeeds (runtime concern).

This hook enforces items 1-3 at commit time. Items 4-5 are
runtime-verified by the health check at boot.

When does the hook fire?

  - A staged diff TOUCHES one of:
      * `backend/extensions/<name>.cpp` (added, removed, or content
        changed from empty to non-empty)
      * the `EXTENSION_NAMES` set in `scripts/ensure_compiled_artifacts.py`
      * the `_NATIVE_RUNTIME_MODULES` tuple in
        `backend/apps/diagnostics/health.py`

What does it check?

  - Every name in the union of (changed-sources, changed-EXTENSION_NAMES,
    changed-_NATIVE_RUNTIME_MODULES) must end the commit with all THREE
    registrations present. A half-finished addition (source without
    declaration, or declaration without source) is hard-blocked.
  - 0-byte source files are hard-blocked. The slice 1.5 audit found one
    empty placeholder (`pixie_walk.cpp`); the rule applies prospectively
    so existing-state grandfather is automatic - the hook only fires on
    the names appearing in the staged diff.

Rule F-compliant: three-part FAIL with what / why / unblock.
"""
# quality-debt-ignore: reason: hook scripts share Rule-F docstring trailer + import boilerplate; refactoring further hurts readability without measurable gain

from __future__ import annotations

import re
import sys
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parent
if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))

from _hook_helpers import run_git, staged_paths  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent

EXTENSIONS_DIR = REPO_ROOT / "backend" / "extensions"
ENSURE_SCRIPT = REPO_ROOT / "scripts" / "ensure_compiled_artifacts.py"
HEALTH_FILE = REPO_ROOT / "backend" / "apps" / "diagnostics" / "health.py"

_PYBIND11_RE = re.compile(r"PYBIND11_MODULE\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*,")
_EXTENSION_NAMES_RE = re.compile(
    r"EXTENSION_NAMES\s*=\s*\{(?P<body>[^}]+)\}", re.MULTILINE | re.DOTALL
)
_NATIVE_RUNTIME_TUPLE_RE = re.compile(
    r"\(\s*\"(?P<name>[a-z_][a-z0-9_]*)\"\s*,"
)


def _git_diff_names() -> list[str]:
    """Return staged file paths via the shared helper."""
    return staged_paths(REPO_ROOT)


def _staged_text(path: Path) -> str | None:
    """Return the staged version of a tracked file (index-side), or None."""
    rel = path.relative_to(REPO_ROOT)
    text = run_git(REPO_ROOT, ["show", f":{rel.as_posix()}"])
    return text or None


def _names_in_extension_set(text: str) -> set[str]:
    """Parse EXTENSION_NAMES = { ... } and return its names."""
    match = _EXTENSION_NAMES_RE.search(text)
    if not match:
        return set()
    body = match.group("body")
    names: set[str] = set()
    for token in re.findall(r"\"([a-z_][a-z0-9_]*)\"", body):
        names.add(token)
    return names


def _names_in_native_runtime(text: str) -> set[str]:
    """Parse _NATIVE_RUNTIME_MODULES tuple and return the leading names.

    The shape is `("name", "expected_attr", "label", critical),` so we
    grab every leading string in a parenthesised group. False positives
    on unrelated tuples are tolerable because the cross-checks below
    only flag names that ALSO appear in one of the three sources.
    """
    block_match = re.search(
        r"_NATIVE_RUNTIME_MODULES\s*=\s*\((?P<body>.+?)^\)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    if not block_match:
        return set()
    body = block_match.group("body")
    return set(_NATIVE_RUNTIME_TUPLE_RE.findall(body))


def _names_with_source() -> dict[str, Path]:
    """Map module name -> .cpp path for every non-test extensions source."""
    sources: dict[str, Path] = {}
    if not EXTENSIONS_DIR.is_dir():
        return sources
    for path in EXTENSIONS_DIR.glob("*.cpp"):
        if path.name.startswith("test_") or "/test" in path.as_posix():
            continue
        sources[path.stem] = path
    return sources


def _changed_kernel_names(diff: list[str]) -> set[str]:
    """Names of kernels mentioned by the staged diff."""
    touched: set[str] = set()
    for path in diff:
        if path.startswith("backend/extensions/") and path.endswith(".cpp"):
            stem = Path(path).stem
            if not stem.startswith("test_") and "/test" not in path:
                touched.add(stem)
    if any(p == "scripts/ensure_compiled_artifacts.py" for p in diff):
        text = ENSURE_SCRIPT.read_text(encoding="utf-8", errors="replace")
        touched.update(_names_in_extension_set(text))
    if any(p == "backend/apps/diagnostics/health.py" for p in diff):
        text = HEALTH_FILE.read_text(encoding="utf-8", errors="replace")
        touched.update(_names_in_native_runtime(text))
    return touched


# quality-debt-ignore: reason: lifecycle check needs the 4 sequential file probes (source / EXTENSION_NAMES / _NATIVE_RUNTIME_MODULES / PYBIND11_MODULE) co-located so the failure message names every missing piece at once; splitting would make the user-facing error worse
def _check_kernel(name: str) -> list[str]:
    """Return list of failure messages for one kernel name."""
    failures: list[str] = []
    source = EXTENSIONS_DIR / f"{name}.cpp"
    source_exists = source.is_file() and source.stat().st_size > 0
    if source.is_file() and source.stat().st_size == 0:
        # quality-debt-ignore: reason: three failures.append(...) calls are intentional - each one names a distinct lifecycle gap (empty source, half-registration, pybind name mismatch) and the caller wants them all listed
        failures.append(
            f"  {name}: source is 0 bytes ({source.relative_to(REPO_ROOT)}). "
            "An empty .cpp file builds nothing - either implement it or "
            "remove the file."
        )
    if not source.is_file():
        # The name was declared somewhere but there is no .cpp.
        # Fall through; the union check below will flag this via the
        # EXTENSION_NAMES / _NATIVE_RUNTIME_MODULES path.
        source_exists = False
    ensure_text = ENSURE_SCRIPT.read_text(encoding="utf-8", errors="replace")
    in_extension_names = name in _names_in_extension_set(ensure_text)
    health_text = HEALTH_FILE.read_text(encoding="utf-8", errors="replace")
    in_native_runtime = name in _names_in_native_runtime(health_text)

    present_count = sum([source_exists, in_extension_names, in_native_runtime])
    if 0 < present_count < 3:
        missing = []
        if not source_exists:
            missing.append("backend/extensions/{0}.cpp (non-empty)".format(name))
        if not in_extension_names:
            missing.append(
                "EXTENSION_NAMES in scripts/ensure_compiled_artifacts.py"
            )
        if not in_native_runtime:
            missing.append(
                "_NATIVE_RUNTIME_MODULES in backend/apps/diagnostics/health.py"
            )
        failures.append(
            f"  {name}: half-registered ({present_count}/3 places present). "
            f"Missing: {', '.join(missing)}."
        )
    if source_exists:
        body = source.read_text(encoding="utf-8", errors="replace")
        pybind_match = _PYBIND11_RE.search(body)
        if pybind_match is None:
            failures.append(
                f"  {name}: source exists but has no PYBIND11_MODULE block. "
                "Add `PYBIND11_MODULE({0}, m) {{ ... }}` so Python can bind it.".format(name)
            )
        elif pybind_match.group(1) != name:
            failures.append(
                f"  {name}: PYBIND11_MODULE declares "
                f"`{pybind_match.group(1)}` but the file is `{name}.cpp`. "
                "The module name must match the filename stem."
            )
    return failures


def main() -> int:
    diff = _git_diff_names()
    if not diff:
        return 0
    touched = _changed_kernel_names(diff)
    if not touched:
        return 0
    all_failures: list[str] = []
    for name in sorted(touched):
        all_failures.extend(_check_kernel(name))
    if not all_failures:
        return 0
    sys.stderr.write(
        "FAIL check-cpp-lifecycle: C++ kernel lifecycle invariant broken.\n"
        "WHY: Rule J requires every kernel to be registered in ALL THREE "
        "places together (source file, EXTENSION_NAMES, _NATIVE_RUNTIME_MODULES) "
        "or in NONE of them. Half-registered kernels confuse the build pipeline "
        "and surface as 'missing C++ kernels' in the GUI forever.\n"
        "UNBLOCK: For each kernel below, either complete the three registrations "
        "OR remove the partial one. Empty .cpp placeholders are not allowed - "
        "implement the body or delete the file.\n"
    )
    for line in all_failures:
        sys.stderr.write(line + "\n")
    sys.stderr.write(
        "\nReference: see CLAUDE.md `Rule J - C++ kernel lifecycle` for the "
        "full five-step lifecycle.\n"
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
