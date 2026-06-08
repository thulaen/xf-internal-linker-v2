#!/usr/bin/env python3
"""Rule J - C++ kernel lifecycle invariant (full-tree mode, 2026-05-16).

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

Full-tree mode (changed 2026-05-16):

  Earlier versions of this hook only fired on names appearing in
  the staged diff. That meant a half-registered kernel could sit
  forever as long as no one touched it. The hook now scans the
  WHOLE TREE on every commit. The cost is a handful of file reads
  (under 50 ms); the benefit is that the three-way invariant is
  always true after every commit, not just for the names you
  touched.

  Three states must all be empty after a commit:
    - declared without source
    - source without EXTENSION_NAMES
    - source without _NATIVE_RUNTIME_MODULES
  Plus: zero-byte .cpp files are a hard block, and any PYBIND11_MODULE
  name that disagrees with the filename stem is a hard block.

Rule F-compliant: three-part FAIL with what / why / unblock.
"""
# quality-debt-ignore: reason: hook scripts share Rule-F docstring trailer + import boilerplate; refactoring further hurts readability without measurable gain

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parent
if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))

REPO_ROOT = Path(__file__).resolve().parent.parent

EXTENSIONS_DIR = REPO_ROOT / "backend" / "extensions"
RUST_EXTENSIONS_DIR = REPO_ROOT / "rust" / "extensions"
ENSURE_SCRIPT = REPO_ROOT / "scripts" / "ensure_compiled_artifacts.py"
HEALTH_FILE = REPO_ROOT / "backend" / "apps" / "diagnostics" / "health.py"

_PYBIND11_RE = re.compile(r"PYBIND11_MODULE\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*,")
# The leading `\b(?<!_)` anchors on a real word start so the C++
# `EXTENSION_NAMES` regex does NOT also match `RUST_EXTENSION_NAMES`
# (which contains `EXTENSION_NAMES` as a suffix and is defined first in the
# file). Without it `re.search` would grab the Rust set as the C++ set.
_EXTENSION_NAMES_RE = re.compile(
    r"(?<![A-Za-z0-9_])EXTENSION_NAMES\s*=\s*\{(?P<body>[^}]+)\}",
    re.MULTILINE | re.DOTALL,
)
_RUST_EXTENSION_NAMES_RE = re.compile(
    r"(?<![A-Za-z0-9_])RUST_EXTENSION_NAMES\s*=\s*\{(?P<body>[^}]+)\}",
    re.MULTILINE | re.DOTALL,
)
# A PyO3 module is declared as `#[pymodule]` immediately above `fn <name>(`.
# The module function name must equal the kernel name so the built `<name>.so`
# imports as `extensions.<name>`.
_PYMODULE_RE = re.compile(
    r"#\[pymodule\]\s*(?:pub\s+)?fn\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(",
    re.MULTILINE | re.DOTALL,
)


def _names_in_extension_set(text: str) -> set[str]:
    """Parse EXTENSION_NAMES = { ... } and return its names."""
    match = _EXTENSION_NAMES_RE.search(text)
    if not match:
        return set()
    body = match.group("body")
    return set(re.findall(r"\"([a-z_][a-z0-9_]*)\"", body))


def _names_in_rust_extension_set(text: str) -> set[str]:
    """Parse RUST_EXTENSION_NAMES = { ... } and return its names.

    These are kernels ported from C++ to Rust (PyO3 + maturin). Each is built
    from ``rust/extensions/<name>`` and stages into the same
    ``active/extensions/`` directory as the C++ ``.so`` files, so the import
    name (``extensions.<name>``) is unchanged. For the lifecycle invariant a
    Rust kernel's source-of-record is its crate, NOT a ``backend/extensions``
    ``.cpp`` file.
    """
    match = _RUST_EXTENSION_NAMES_RE.search(text)
    if not match:
        return set()
    body = match.group("body")
    return set(re.findall(r"\"([a-z_][a-z0-9_]*)\"", body))


# quality-debt-ignore: reason: AST walk over _NATIVE_RUNTIME_MODULES tuple needs four nested isinstance checks (Assign / Tuple / inner Tuple / first Constant); the tuple shape is precisely four levels deep and flattening loses correctness
def _names_in_native_runtime(text: str) -> set[str]:
    """Parse _NATIVE_RUNTIME_MODULES via AST so multi-line tuples are caught."""
    # quality-debt-ignore: reason: this AST walker is the canonical implementation; the audit_cpp_lifecycle.py command intentionally re-implements the same walker because hooks (.githooks/) live outside the Django app tree and cannot import from backend/apps/core/management/commands/_lifecycle_helpers.py; both copies stay in sync via the test suite
    try:
        # quality-debt-ignore: reason: intentional duplicate of audit_cpp_lifecycle.py helper; ast.parse+walk pattern is canonical for this Python file shape
        tree = ast.parse(text)
    except SyntaxError:
        return set()
    names: set[str] = set()
    # quality-debt-ignore: reason: AST walker for tuple-of-tuples-with-string-constant requires four nested isinstance checks; see waiver above
    for node in ast.walk(tree):
        # quality-debt-ignore: reason: see waiver above; first isinstance gate in the four-level walker
        if not isinstance(node, ast.Assign):
            continue
        # quality-debt-ignore: reason: see waiver above; second gate (target name match)
        if not any(isinstance(t, ast.Name) and t.id == "_NATIVE_RUNTIME_MODULES" for t in node.targets):
            continue
        if not isinstance(node.value, ast.Tuple):
            continue
        # quality-debt-ignore: reason: see waiver above; the four-level isinstance check on Tuple.elts[0] is the shape of _NATIVE_RUNTIME_MODULES
        for elt in node.value.elts:
            # quality-debt-ignore: reason: see waiver above; inner Tuple shape check
            if not isinstance(elt, ast.Tuple) or not elt.elts:
                continue
            first = elt.elts[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                names.add(first.value)
    return names


def _source_kernels() -> dict[str, Path]:
    """Map module name -> .cpp path for every non-test extensions source."""
    sources: dict[str, Path] = {}
    if not EXTENSIONS_DIR.is_dir():
        return sources
    for path in EXTENSIONS_DIR.glob("*.cpp"):
        if path.name.startswith("test_") or "/test" in path.as_posix():
            continue
        sources[path.stem] = path
    return sources


def _rust_source_kernels() -> dict[str, Path]:
    """Map module name -> lib.rs path for every Rust kernel crate.

    A Rust kernel lives at ``rust/extensions/<name>/src/lib.rs``. This is the
    source-of-record for a kernel that was ported off C++ — the equivalent of a
    ``backend/extensions/<name>.cpp`` for the C++ kernels.
    """
    sources: dict[str, Path] = {}
    if not RUST_EXTENSIONS_DIR.is_dir():
        return sources
    for crate_dir in RUST_EXTENSIONS_DIR.iterdir():
        lib_rs = crate_dir / "src" / "lib.rs"
        if crate_dir.is_dir() and lib_rs.is_file():
            sources[crate_dir.name] = lib_rs
    return sources


def _check_pymodule_block(name: str, source_path: Path) -> str | None:
    """Return a failure message (or None) for the `#[pymodule]` of a Rust kernel.

    Mirrors ``_check_pybind_block`` for C++: the PyO3 module function name must
    match the crate (and import) name so the built ``<name>.so`` imports as
    ``extensions.<name>``.
    """
    body = source_path.read_text(encoding="utf-8", errors="replace")
    match = _PYMODULE_RE.search(body)
    if match is None:
        return (
            f"  {name}: Rust crate exists but has no `#[pymodule]` function. "
            f"Add `#[pymodule] fn {name}(m: &Bound<'_, PyModule>) ...` so Python "
            "can import it."
        )
    if match.group(1) != name:
        return (
            f"  {name}: `#[pymodule]` declares `{match.group(1)}` but the crate "
            f"is `rust/extensions/{name}`. The module function name must match "
            "the crate (and import) name."
        )
    return None


def _check_pybind_block(name: str, source_path: Path) -> str | None:
    """Return failure message (or None) for the PYBIND11 block of `name`."""
    body = source_path.read_text(encoding="utf-8", errors="replace")
    match = _PYBIND11_RE.search(body)
    if match is None:
        return (
            f"  {name}: source exists but has no PYBIND11_MODULE block. "
            f"Add `PYBIND11_MODULE({name}, m) {{ ... }}` so Python can bind it."
        )
    if match.group(1) != name:
        return (
            f"  {name}: PYBIND11_MODULE declares "
            f"`{match.group(1)}` but the file is `{name}.cpp`. "
            "The module name must match the filename stem."
        )
    return None


# quality-debt-ignore: reason: _collect_failures walks three sets in lockstep and emits a per-kernel message naming the missing 0-3 places plus 0-byte and pybind-mismatch checks; splitting hurts the failure-message readability that the FAIL block presents to operators
def _collect_failures(
    sources: dict[str, Path],
    ext_names: set[str],
    runtime_names: set[str],
    rust_names: set[str],
) -> list[str]:
    """Build the C++ lifecycle failures in repo-wide order.

    ``rust_names`` are the kernels backed by a Rust crate. Their
    ``_NATIVE_RUNTIME_MODULES`` entry is satisfied by the Rust source, NOT a
    C++ ``.cpp`` + ``EXTENSION_NAMES`` pair, so they are excluded from the C++
    runtime universe here and validated by ``_collect_rust_failures`` instead.
    A name that is wrongly registered as BOTH C++ and Rust is caught up front
    by ``_collect_cross_language_failures``.
    """
    failures: list[str] = []
    src_set = set(sources)
    # A Rust-backed runtime kernel must not be treated as a half-registered C++
    # kernel just because it has no `.cpp` / no EXTENSION_NAMES entry.
    cpp_runtime_names = runtime_names - rust_names
    universe = sorted(src_set | ext_names | cpp_runtime_names)

    for name in universe:
        in_src = name in src_set
        in_ext = name in ext_names
        in_runtime = name in cpp_runtime_names
        present = sum([in_src, in_ext, in_runtime])
        if present == 0 or present == 3:
            continue
        missing: list[str] = []
        if not in_src:
            missing.append(f"backend/extensions/{name}.cpp (non-empty)")
        if not in_ext:
            missing.append("EXTENSION_NAMES in scripts/ensure_compiled_artifacts.py")
        if not in_runtime:
            missing.append(
                "_NATIVE_RUNTIME_MODULES in backend/apps/diagnostics/health.py"
            )
        failures.append(
            f"  {name}: half-registered ({present}/3 places present). "
            f"Missing: {', '.join(missing)}."
        )

    for name, path in sorted(sources.items()):
        if path.stat().st_size == 0:
            failures.append(
                f"  {name}: source is 0 bytes ({path.relative_to(REPO_ROOT)}). "
                "An empty .cpp file builds nothing - either implement it or "
                "remove the file."
            )
            continue
        pybind_failure = _check_pybind_block(name, path)
        if pybind_failure is not None:
            failures.append(pybind_failure)

    return failures


def _collect_rust_failures(
    rust_sources: dict[str, Path],
    rust_names: set[str],
    runtime_names: set[str],
) -> list[str]:
    """Build the Rust kernel lifecycle failures in repo-wide order.

    A Rust kernel exists only when ALL THREE are present together:
      1. ``rust/extensions/<name>/src/lib.rs`` with a matching ``#[pymodule]``,
      2. ``<name>`` in ``RUST_EXTENSION_NAMES`` in
         ``scripts/ensure_compiled_artifacts.py``,
      3. ``<name>`` in ``_NATIVE_RUNTIME_MODULES`` in
         ``backend/apps/diagnostics/health.py``.
    Same strict three-way invariant as the C++ side, with the Rust crate as the
    source-of-record instead of a ``.cpp`` file.
    """
    failures: list[str] = []
    src_set = set(rust_sources)
    # Every crate under rust/extensions/ is a kernel crate (the `xf_kernels`
    # scaffold lives at rust/xf_kernels, outside this dir, so it is never seen
    # here). A crate present in only one of the three places is half-registered,
    # exactly like a bare C++ `.cpp`.
    universe = sorted(src_set | rust_names | (runtime_names & (src_set | rust_names)))

    for name in universe:
        in_src = name in src_set
        in_names = name in rust_names
        in_runtime = name in runtime_names
        present = sum([in_src, in_names, in_runtime])
        if present == 0 or present == 3:
            continue
        missing: list[str] = []
        if not in_src:
            missing.append(f"rust/extensions/{name}/src/lib.rs (with #[pymodule])")
        if not in_names:
            missing.append(
                "RUST_EXTENSION_NAMES in scripts/ensure_compiled_artifacts.py"
            )
        if not in_runtime:
            missing.append(
                "_NATIVE_RUNTIME_MODULES in backend/apps/diagnostics/health.py"
            )
        failures.append(
            f"  {name}: Rust kernel half-registered ({present}/3 places present). "
            f"Missing: {', '.join(missing)}."
        )

    for name, path in sorted(rust_sources.items()):
        if path.stat().st_size == 0:
            failures.append(
                f"  {name}: Rust source is 0 bytes ({path.relative_to(REPO_ROOT)}). "
                "An empty lib.rs builds nothing - either implement it or remove "
                "the crate."
            )
            continue
        pymodule_failure = _check_pymodule_block(name, path)
        if pymodule_failure is not None:
            failures.append(pymodule_failure)

    return failures


def _collect_cross_language_failures(
    cpp_sources: dict[str, Path],
    ext_names: set[str],
    rust_sources: dict[str, Path],
    rust_names: set[str],
) -> list[str]:
    """Block a kernel that is registered as BOTH C++ and Rust (half-deleted port).

    When a kernel is ported off C++ to Rust the C++ source, header, and
    ``EXTENSION_NAMES`` entry are deleted in the SAME change (RUST-FIRST.md
    zero-fallback / dead-code-on-replace). A name that still appears on both
    sides means the C++ side was not fully retired.
    """
    failures: list[str] = []
    cpp_side = set(cpp_sources) | ext_names
    rust_side = set(rust_sources) | rust_names
    for name in sorted(cpp_side & rust_side):
        wheres: list[str] = []
        if name in cpp_sources:
            wheres.append(f"backend/extensions/{name}.cpp")
        if name in ext_names:
            wheres.append("EXTENSION_NAMES")
        failures.append(
            f"  {name}: registered as BOTH a Rust kernel and a C++ kernel. "
            f"The C++ side is not fully retired (still in: {', '.join(wheres)}). "
            "Delete the C++ source/header and the EXTENSION_NAMES entry in the "
            "same change that lands the Rust port."
        )
    return failures


def main() -> int:
    if not EXTENSIONS_DIR.is_dir() or not ENSURE_SCRIPT.is_file() or not HEALTH_FILE.is_file():
        # Nothing to enforce when the project skeleton is missing (fresh clone, partial checkout).
        return 0

    sources = _source_kernels()
    rust_sources = _rust_source_kernels()
    ensure_text = ENSURE_SCRIPT.read_text(encoding="utf-8", errors="replace")
    health_text = HEALTH_FILE.read_text(encoding="utf-8", errors="replace")
    ext_names = _names_in_extension_set(ensure_text)
    rust_names = _names_in_rust_extension_set(ensure_text)
    runtime_names = _names_in_native_runtime(health_text)

    failures = (
        _collect_cross_language_failures(sources, ext_names, rust_sources, rust_names)
        + _collect_failures(sources, ext_names, runtime_names, rust_names)
        + _collect_rust_failures(rust_sources, rust_names, runtime_names)
    )
    # Dedup zero-byte messages (which may surface twice — once via half-registered, once via direct scan).
    seen: set[str] = set()
    failures_unique: list[str] = []
    for line in failures:
        if line in seen:
            continue
        seen.add(line)
        failures_unique.append(line)

    if not failures_unique:
        return 0

    sys.stderr.write(
        "FAIL check-cpp-lifecycle: native kernel lifecycle invariant broken (full-tree scan).\n"
        "WHY: Rule J requires every kernel to be registered in ALL THREE "
        "places together or in NONE of them. A C++ kernel needs its "
        "backend/extensions/<name>.cpp source + EXTENSION_NAMES + "
        "_NATIVE_RUNTIME_MODULES. A kernel ported to Rust (RUST-FIRST.md) needs "
        "its rust/extensions/<name>/src/lib.rs crate + RUST_EXTENSION_NAMES + "
        "_NATIVE_RUNTIME_MODULES instead, and must NOT keep a C++ twin. The hook "
        "scans the entire tree on every commit, not just staged changes, so "
        "half-registered or half-ported kernels cannot accumulate as legacy "
        "debt. Empty .cpp / lib.rs placeholders are also blocked - they build "
        "nothing and confuse the GUI 'missing kernels' panel forever.\n"
        "UNBLOCK: For each kernel below, either (a) complete the three "
        "registrations for its language, OR (b) remove the partial one. When a "
        "kernel is ported off C++ to Rust, delete the C++ .cpp/header and the "
        "EXTENSION_NAMES entry in the SAME change. If you want to park "
        "a kernel's name for later implementation, move its line to "
        "docs/CPP-ROADMAP.md - that file does not trip the hook because the "
        "name is not present in any of the lifecycle places.\n"
    )
    for line in failures_unique:
        sys.stderr.write(line + "\n")
    sys.stderr.write(
        "\nReference: see CLAUDE.md `Rule J - C++ kernel lifecycle` for the "
        "full five-step lifecycle and docs/CPP-ROADMAP.md for parked names.\n"
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
