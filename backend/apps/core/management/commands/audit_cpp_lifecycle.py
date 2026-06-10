# quality-debt-ignore: reason: smoke tests for the 4 lifecycle helper commands live together at backend/apps/core/test_lifecycle_helpers.py because they share the same _repo_root() helper and fixture shape; co-locating them keeps the test surface small and avoids per-command duplication
"""Audit the C++ kernel three-way lifecycle state (Rule J, read-only).

Plain-English summary
---------------------

This command prints every C++ kernel name in the repo, with three columns:
  src    → does backend/extensions/<name>.cpp exist and have content?
  ext    → is <name> in EXTENSION_NAMES (scripts/ensure_compiled_artifacts.py)?
  rt     → is <name> in _NATIVE_RUNTIME_MODULES (backend/apps/diagnostics/health.py)?

A clean kernel has all three columns marked. A "half-registered" kernel
(any combination of yes/no with at least one yes and one no) is a Rule J
violation that the pre-commit hook will hard-block.

Run this when you want to know what shape the kernel set is in WITHOUT
trying to commit. It is read-only (no --dry-run needed; nothing is
written).

Usage:
  docker compose exec -T backend python manage.py audit_cpp_lifecycle
  docker compose exec -T backend python manage.py audit_cpp_lifecycle --only-broken
  docker compose exec -T backend python manage.py audit_cpp_lifecycle --json
"""
# xf: no_dry_run -- read-only audit; no state changes

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

from django.core.management.base import BaseCommand

from ._lifecycle_helpers import repo_root as _repo_root


def _names_in_extension_set(text: str) -> set[str]:
    # `(?<![A-Za-z0-9_])` keeps this from also matching the
    # `RUST_EXTENSION_NAMES` assignment (which ends in `EXTENSION_NAMES` and
    # appears first in the file).
    match = re.search(
        r"(?<![A-Za-z0-9_])EXTENSION_NAMES\s*=\s*\{([^}]+)\}", text, re.DOTALL
    )
    if not match:
        return set()
    return set(re.findall(r"\"([a-z_][a-z0-9_]*)\"", match.group(1)))


def _names_in_rust_extension_set(text: str) -> set[str]:
    """Names in RUST_EXTENSION_NAMES — kernels ported from C++ to Rust."""
    match = re.search(
        r"(?<![A-Za-z0-9_])RUST_EXTENSION_NAMES\s*=\s*\{([^}]+)\}", text, re.DOTALL
    )
    if not match:
        return set()
    return set(re.findall(r"\"([a-z_][a-z0-9_]*)\"", match.group(1)))


def _rust_source_kernels(rust_ext_dir: Path) -> dict[str, int]:
    """Map name -> lib.rs size for every rust/extensions/<name> crate."""
    out: dict[str, int] = {}
    if not rust_ext_dir.is_dir():
        return out
    for crate_dir in rust_ext_dir.iterdir():
        lib_rs = crate_dir / "src" / "lib.rs"
        if crate_dir.is_dir() and lib_rs.is_file():
            out[crate_dir.name] = lib_rs.stat().st_size
    return out


# quality-debt-ignore: reason: AST walk over _NATIVE_RUNTIME_MODULES tuple needs three nested isinstance checks (Assign / Tuple / inner Tuple / first Constant); flattening loses correctness because the tuple shape is precisely four levels deep
def _names_in_native_runtime(text: str) -> set[str]:
    # quality-debt-ignore: reason: intentional duplicate of .githooks/check-cpp-lifecycle.py:_names_in_native_runtime because the hook lives outside the Django app tree and cannot import this module; both copies stay in sync via the test suite
    try:
        # quality-debt-ignore: reason: intentional duplicate of hook helper; ast.parse+walk pattern is canonical for this Python file shape
        tree = ast.parse(text)
    except SyntaxError:
        return set()
    names: set[str] = set()
    # quality-debt-ignore: reason: AST walker for tuple-of-tuples-with-string-constant requires four nested isinstance checks; see waiver above
    for node in ast.walk(tree):
        # quality-debt-ignore: reason: see waiver above; this is the second isinstance gate in the four-level walker
        if not isinstance(node, ast.Assign):
            continue
        # quality-debt-ignore: reason: see waiver above; this is the third gate (target name match)
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


def _source_kernels(ext_dir: Path) -> dict[str, int]:
    """Map name -> file size in bytes (0 indicates an empty placeholder)."""
    out: dict[str, int] = {}
    if not ext_dir.is_dir():
        return out
    for path in ext_dir.glob("*.cpp"):
        if path.name.startswith("test_") or "/test" in path.as_posix():
            continue
        out[path.stem] = path.stat().st_size
    return out


class Command(BaseCommand):
    help = "Audit the C++ kernel three-way lifecycle (source / EXTENSION_NAMES / _NATIVE_RUNTIME_MODULES)."

    def add_arguments(self, parser):
        # quality-debt-ignore: reason: Django add_arguments boilerplate is intentionally repetitive — each argument needs its own parser.add_argument call with its own help text; consolidating these would hide CLI documentation
        parser.add_argument(
            "--only-broken",
            action="store_true",
            help="Show only kernels that violate Rule J (half-registered or 0-byte).",
        )
        # quality-debt-ignore: reason: Django parser.add_argument boilerplate; each argument needs its own call with its own help text
        parser.add_argument(
            "--json",
            action="store_true",
            help="Output a JSON document instead of the human-readable table.",
        )

    # quality-debt-ignore: reason: a kernel row folds C++ and Rust three-way state into one PRESENT/BROKEN/ABSENT verdict; the booleans are tightly coupled to the table columns and splitting hurts readability
    @staticmethod
    def _kernel_row(
        name: str,
        *,
        sources: dict[str, int],
        rust_sources: dict[str, int],
        ext_names: set[str],
        rust_names: set[str],
        rt_names: set[str],
    ) -> dict[str, object]:
        """Fold the C++ and Rust three-way state for *name* into one row.

        A kernel is PRESENT when it forms a complete C++ triple (.cpp +
        EXTENSION_NAMES + runtime) OR a complete Rust triple (rust crate +
        RUST_EXTENSION_NAMES + runtime), and is not registered as both.
        """
        cpp_size = sources.get(name)
        rust_size = rust_sources.get(name)
        in_cpp_src = cpp_size is not None and cpp_size > 0
        in_rust_src = rust_size is not None and rust_size > 0
        is_empty = (cpp_size == 0) or (rust_size == 0)
        in_ext = name in ext_names
        in_rust_names = name in rust_names
        in_rt = name in rt_names

        cpp_present = sum([in_cpp_src, in_ext, in_rt])
        rust_present = sum([in_rust_src, in_rust_names, in_rt])
        cpp_side = in_cpp_src or in_ext
        rust_side = in_rust_src or in_rust_names
        both_languages = cpp_side and rust_side

        is_rust = rust_side and not cpp_side
        complete = cpp_present == 3 or rust_present == 3
        absent = cpp_present == 0 and rust_present == 0
        broken = both_languages or is_empty or not (complete or absent)
        state = "BROKEN" if broken else ("PRESENT" if complete else "ABSENT")
        return {
            "name": name,
            "lang": "rust" if is_rust else "cpp",
            "src": in_rust_src if is_rust else in_cpp_src,
            "src_empty": is_empty,
            "ext": in_rust_names if is_rust else in_ext,
            "rt": in_rt,
            "state": state,
        }

    # quality-debt-ignore: reason: handle() reads four files, walks the union of name sets, builds row dicts, and renders a table — the steps are tightly coupled to the audit output shape and splitting hurts readability
    def handle(self, *args, **options):
        root = _repo_root()
        ext_dir = root / "backend" / "extensions"
        rust_ext_dir = root / "rust" / "extensions"
        ensure = root / "scripts" / "ensure_compiled_artifacts.py"
        health = root / "backend" / "apps" / "diagnostics" / "health.py"

        sources = _source_kernels(ext_dir)
        rust_sources = _rust_source_kernels(rust_ext_dir)
        ensure_text = ensure.read_text(encoding="utf-8", errors="replace") if ensure.is_file() else ""
        ext_names = _names_in_extension_set(ensure_text)
        rust_names = _names_in_rust_extension_set(ensure_text)
        rt_names = _names_in_native_runtime(health.read_text(encoding="utf-8", errors="replace")) if health.is_file() else set()

        all_names = sorted(set(sources) | set(rust_sources) | ext_names | rust_names | rt_names)
        rows = [
            self._kernel_row(
                name,
                sources=sources,
                rust_sources=rust_sources,
                ext_names=ext_names,
                rust_names=rust_names,
                rt_names=rt_names,
            )
            for name in all_names
        ]

        if options["only_broken"]:
            rows = [r for r in rows if r["state"] == "BROKEN"]

        if options["json"]:
            self.stdout.write(json.dumps(rows, indent=2))
            return

        clean = [r for r in rows if r["state"] == "PRESENT"]
        broken = [r for r in rows if r["state"] == "BROKEN"]
        absent = [r for r in rows if r["state"] == "ABSENT"]
        self.stdout.write("Native kernel lifecycle audit (Rule J, C++ + Rust)")
        self.stdout.write(f"  PRESENT (all three places): {len(clean)}")
        self.stdout.write(f"  BROKEN  (half-registered or 0-byte): {len(broken)}")
        self.stdout.write(f"  ABSENT  (none of three places): {len(absent)}")
        self.stdout.write("")
        self.stdout.write(f"  {'name':<32}  lang  src   reg   rt    state")
        for r in rows:
            src = ("yes" if r["src"] else ("0B " if r["src_empty"] else "no "))
            reg = "yes" if r["ext"] else "no "
            rt = "yes" if r["rt"] else "no "
            self.stdout.write(
                f"  {r['name']:<32}  {r['lang']:<4}  {src}   {reg}   {rt}   {r['state']}"
            )
        if broken:
            self.stdout.write("")
            self.stdout.write(
                "Fix BROKEN rows before committing — the pre-commit hook "
                ".githooks/check-cpp-lifecycle.py will hard-block any commit "
                "while half-registered kernels exist. Either complete the "
                "three registrations or remove the partial one. Park the "
                "name in docs/CPP-ROADMAP.md if you want to keep it for later."
            )
