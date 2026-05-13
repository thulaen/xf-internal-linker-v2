#!/usr/bin/env python3
"""Build Docker-managed compiled artifacts when their source changes."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

try:
    import fcntl
except ImportError:  # pragma: no cover - this script is required in Linux containers.
    fcntl = None


ARTIFACT_ROOT = Path(os.environ.get("XF_COMPILED_ARTIFACT_ROOT", "/opt/xf/compiled"))
BUILD_ROOT = Path(os.environ.get("XF_COMPILED_BUILD_ROOT", "/tmp/xf-build"))
BACKEND_ROOT = Path(os.environ.get("XF_BACKEND_ROOT", "/app"))
REPO_ROOT = Path(os.environ.get("REPO_ROOT", "/repo"))
MANIFEST_PATH = ARTIFACT_ROOT / "manifest.json"
EXTENSION_NAMES = {
    "anchor_descriptiveness",
    "anchor_diversity",
    "anchor_self_information",
    "api_rate_limiter",
    "compressed_bloom",
    "count_min_sketch",
    "counting_bloom",
    "feedrerank",
    "fieldrel",
    "generic_anchor_matcher",
    "ivf_index",
    "l2norm",
    "linkparse",
    "pagerank",
    "passagesim",
    "phrasematch",
    "quantemb",
    "rareterm",
    "scoring",
    "simsearch",
    "texttok",
}


def _repo_backend_root() -> Path:
    if (BACKEND_ROOT / "extensions" / "setup.py").exists():
        return BACKEND_ROOT
    return REPO_ROOT / "backend"


def _iter_files(root: Path, patterns: tuple[str, ...]) -> list[Path]:
    files: list[Path] = []
    for pattern in patterns:
        files.extend(path for path in root.glob(pattern) if path.is_file())
    return sorted(set(files))


def _hash_files(files: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in files:
        digest.update(str(path).encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _runtime_cpp_files(extensions_root: Path) -> list[Path]:
    patterns = ("setup.py", "*.cpp", "include/*.h", "include/*.hpp")
    return _iter_files(extensions_root, patterns)


def _go_files(repo_root: Path) -> list[Path]:
    ignored_dirs = {".git", ".mypy_cache", ".pytest_cache", ".ruff_cache", "vendor"}
    ignored_dirs.update({"node_modules", "build", "build_tests", "dist", ".angular"})
    files: list[Path] = []
    for current, dirs, filenames in os.walk(repo_root):
        dirs[:] = [name for name in dirs if name not in ignored_dirs]
        current_path = Path(current)
        for filename in filenames:
            path = current_path / filename
            if filename in {"go.mod", "go.sum"} or path.suffix == ".go":
                files.append(path)
    return sorted(files)


def _load_manifest() -> dict[str, str]:
    try:
        return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _write_manifest(manifest: dict[str, str]) -> None:
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")


def _run(command: list[str], cwd: Path) -> None:
    print("+ " + " ".join(command), flush=True)
    subprocess.run(command, cwd=cwd, check=True)


def _clean_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def _build_cpp_runtime(backend_root: Path, digest: str, manifest: dict[str, str]) -> bool:
    if manifest.get("cpp_runtime_hash") == digest and _cpp_artifacts_present():
        print("Compiled C++ runtime artifacts are current.", flush=True)
        return False
    extensions_root = backend_root / "extensions"
    output_dir = ARTIFACT_ROOT / "extensions"
    build_dir = BUILD_ROOT / "cpp-runtime"
    _clean_dir(output_dir)
    _clean_dir(build_dir)
    (output_dir / "__init__.py").write_text("", encoding="utf-8")
    _run(
        [
            sys.executable,
            "setup.py",
            "build_ext",
            "--build-lib",
            str(output_dir),
            "--build-temp",
            str(build_dir / "temp"),
        ],
        cwd=extensions_root,
    )
    manifest["cpp_runtime_hash"] = digest
    manifest["cpp_runtime_path"] = str(output_dir)
    _write_manifest(manifest)
    print("Compiled C++ runtime artifacts were rebuilt.", flush=True)
    return True


def _cpp_artifacts_present() -> bool:
    output_dir = ARTIFACT_ROOT / "extensions"
    found = {path.name.split(".")[0] for path in output_dir.glob("*.so")}
    return EXTENSION_NAMES.issubset(found)


def _record_go_state(repo_root: Path, manifest: dict[str, str]) -> None:
    files = _go_files(repo_root)
    go_dir = ARTIFACT_ROOT / "go"
    go_dir.mkdir(parents=True, exist_ok=True)
    manifest["go_source_hash"] = _hash_files(files) if files else "no-go-modules"
    manifest["go_artifact_path"] = str(go_dir)
    _write_manifest(manifest)
    if files:
        print("Go source state recorded for Docker-managed checks.", flush=True)
    else:
        print("No Go modules found; Go tool state recorded.", flush=True)


def _verify_runtime_imports() -> None:
    sys.path.insert(0, str(ARTIFACT_ROOT))
    for module_name in ("extensions.scoring", "extensions.simsearch", "extensions.texttok"):
        __import__(module_name)
    print("Compiled runtime imports are ready.", flush=True)


class _FileLock:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.handle = None

    def __enter__(self) -> "_FileLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.path.open("w", encoding="utf-8")
        if fcntl is not None:
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX)
        return self

    def __exit__(self, *_exc: object) -> None:
        if self.handle is None:
            return
        if fcntl is not None:
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        self.handle.close()


def ensure_artifacts() -> int:
    backend_root = _repo_backend_root()
    extensions_root = backend_root / "extensions"
    if not (extensions_root / "setup.py").exists():
        print(f"Missing C++ setup file: {extensions_root / 'setup.py'}", file=sys.stderr)
        return 1
    ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)
    BUILD_ROOT.mkdir(parents=True, exist_ok=True)
    with _FileLock(ARTIFACT_ROOT / ".compile.lock"):
        manifest = _load_manifest()
        cpp_digest = _hash_files(_runtime_cpp_files(extensions_root))
        _build_cpp_runtime(backend_root, cpp_digest, manifest)
        _record_go_state(REPO_ROOT, _load_manifest())
        _verify_runtime_imports()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="Build if stale, then exit.")
    parser.parse_args()
    return ensure_artifacts()


if __name__ == "__main__":
    raise SystemExit(main())
