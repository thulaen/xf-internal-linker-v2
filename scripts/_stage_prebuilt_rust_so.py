#!/usr/bin/env python3
"""Stage a Dell-built Rust kernel `.so` into MSI's compiled-artifacts runtime.

MSI (the Windows runtime host) runs the app but never builds: its Rust/C++
build images were removed to reclaim disk. Dell builds every kernel. A kernel
ported to Rust on Dell *after* MSI lost its build image therefore never reaches
MSI's runtime store on its own — the per-boot ``ensure_compiled_artifacts``
Rust path needs ``cargo``, which MSI does not have, so it just skips. That left
``anchor_self_information`` missing on MSI and crash-looped the backend.

This stager closes that gap. Given a prebuilt cdylib (``lib<name>.so``, the
exact file ``cargo build --release`` drops in ``target/release/``), it:

  1. content-addresses the file into the store via the module's own
     ``_store_artifact`` (no hand-rolled hashing);
  2. hard-links/copies it into ``active/extensions/<name>.so`` via
     ``_link_or_copy`` so ``from extensions import <name>`` resolves to it;
  3. removes the stale ABI-tagged C++ ``<name>.cpython-*.so`` sibling so
     CPython prefers the bare Rust ``.so`` (reuses the module's
     ``_remove_superseded_cpp_artifact``);
  4. records the artifact in ``manifest["active"]["rust_extensions"]`` exactly
     like the in-container Rust build does, so the kernel SURVIVES future boots:
     ``_record_rust_extensions_state`` sees the entry, ``_rust_extensions_present``
     returns True, and the boot skips the (impossible-on-MSI) cargo rebuild
     instead of trying to recompile and crashing.

This is intentionally a runtime stager, not a builder — it never invokes cargo
and must run inside a container that has the compiled-artifacts volume mounted
at ``$XF_COMPILED_ARTIFACT_ROOT`` (default ``/opt/xf/compiled``). It is driven
by ``scripts/sync-rust-kernels-from-dell.sh`` (the permanent Dell -> MSI route)
but can also be run directly with an already-built ``.so``.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import ensure_compiled_artifacts as eca


def _upsert_rust_artifact_record(manifest: dict[str, Any], record: dict[str, Any]) -> None:
    """Add or replace the kernel's record in the rust_extensions manifest entry.

    Reuses whatever rust_extensions metadata already exists (source_hash,
    last_verified_at, etc.) and only swaps in the one artifact record for this
    kernel, so previously staged kernels keep their records and re-staging the
    same kernel replaces — never duplicates — its row.
    """
    entry = manifest["active"].get("rust_extensions")
    if not entry or entry.get("status") not in {"built", None}:
        # No usable prior entry (fresh store or a "no-rust-extensions" stub):
        # start a minimal built entry. The source_hash is left empty so the next
        # build-capable boot can recompute it; on MSI (no cargo) presence of the
        # active_path is what keeps the kernel — the hash is never recomputed.
        entry = {
            "language": "rust",
            "module": "rust/extensions",
            "source_hash": entry.get("source_hash", "") if entry else "",
            "status": "built",
            "active_path": str(eca.ACTIVE_EXTENSIONS_ROOT),
            "build_command": "cargo build --release --locked --package <name>",
            "artifacts": [],
        }
    artifacts = [a for a in entry.get("artifacts", []) if a.get("module") != record["module"]]
    artifacts.append(record)
    artifacts.sort(key=lambda a: a.get("module", ""))
    entry["artifacts"] = artifacts
    entry["last_verified_at"] = eca._now()
    manifest["active"]["rust_extensions"] = entry
    manifest["rust_extensions_path"] = str(eca.ACTIVE_EXTENSIONS_ROOT)


def stage_prebuilt_rust_so(*, name: str, so_path: Path) -> int:
    """Stage one prebuilt Rust kernel `.so` into the active runtime + manifest.

    Returns 0 on success, non-zero on a guard failure (missing input file).
    All content-addressing and active-dir linking is delegated to
    ``ensure_compiled_artifacts`` so there is a single source of truth for how
    artifacts are stored.
    """
    so_path = Path(so_path)
    if not so_path.is_file():
        print(
            f"FAIL stage_prebuilt_rust_so: source .so not found: {so_path}",
            file=sys.stderr,
            flush=True,
        )
        return 2

    eca.ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)
    eca.ACTIVE_EXTENSIONS_ROOT.mkdir(parents=True, exist_ok=True)

    with eca._FileLock(eca.ARTIFACT_ROOT / ".compile.lock"):
        manifest = eca._load_manifest()
        stored = eca._store_artifact(so_path, manifest)
        active_path = eca.ACTIVE_EXTENSIONS_ROOT / f"{name}.so"
        eca._link_or_copy(Path(stored["store_path"]), active_path)
        eca._remove_superseded_cpp_artifact(name)
        record = {
            "filename": f"{name}.so",
            "module": name,
            "active_path": str(active_path),
            "build_command": f"cargo build --release --locked --package {name} (staged prebuilt from Dell)",
            **stored,
        }
        _upsert_rust_artifact_record(manifest, record)
        eca._write_manifest(manifest)

    print(
        f"[STAGED PREBUILT RUST: name={name} so={so_path} "
        f"active={active_path} sha256={stored['sha256'][:16]}]",
        flush=True,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Stage a Dell-built Rust kernel .so into MSI's compiled-artifacts runtime."
    )
    parser.add_argument("--name", required=True, help="Kernel name, e.g. anchor_self_information")
    parser.add_argument(
        "--so",
        required=True,
        help="Path to the prebuilt lib<name>.so (cargo target/release output).",
    )
    args = parser.parse_args(argv)
    return stage_prebuilt_rust_so(name=args.name, so_path=Path(args.so))


if __name__ == "__main__":
    raise SystemExit(main())
