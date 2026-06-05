"""Slice 1.5 — layer-fence test for the Go services tier.

This is the architecture-level regression test that runs in pytest. It is
NOT a pre-commit hook — the on-commit equivalent is
.githooks/check-go-service-contract.py. The two checks share the constants
module so they cannot drift.

Enforces three rules for `services/<name>/`:

  1. Every services/<name>/ folder publishes a binary entry point at
     services/<name>/cmd/<name>/main.go.
  2. Every services/<name>/ folder publishes a contract file: ONE of
     api.proto or api.http.md.
  3. The services tier contains only Go-side artefacts: *.go files, go.mod,
     go.sum, contract files, docs, build files. Specific exemptions:
       - *_baseline.py / parity_*.py — Python parity baselines for cross-
         language equivalence tests (e.g.
         services/streamd/internal/state/python_state_baseline.py).
       - *_test.* — test fixtures of any extension are tolerated.

Rule 3 is the "no stray code" guard — Python source under services/ that is
not a parity baseline or a test fixture is forbidden because it re-imports
the build coupling the modular-monolith refactor is removing.

The test is skipped before Half B (streamd binary + contract) lands so the
suite stays green while slice 1.5 is in progress. Once streamd has its
artefacts the skip lifts automatically.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from unittest import TestCase, skipUnless

# Hookable into the shared constants module without making this a package.
HOOKS_DIR = Path(__file__).resolve().parent
if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))

from _modular_monolith_constants import (  # noqa: E402
    GO_BINARY_ENTRY_TEMPLATE,
    GO_CONTRACT_FILES,
    SERVICES_DIR,
    go_service_folders,
)


def _load_contract_hook():
    """Load check-go-service-contract.py so the test reuses the hook's own
    multi-service detection. Sharing the live helper is what keeps the test
    and the on-commit hook from drifting (see the module docstring)."""
    spec = importlib.util.spec_from_file_location(
        "check_go_service_contract", HOOKS_DIR / "check-go-service-contract.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # @dataclass needs the module registered
    spec.loader.exec_module(module)
    return module


_CONTRACT_HOOK = _load_contract_hook()


def _has_contract(folder: Path) -> bool:
    """A service publishes its RPC contract either as a single top-level
    api.proto / api.http.md OR — for a multi-service folder (slice 1.6
    sidecars shape) — as services.manifest.yaml plus api/*.proto. This mirrors
    check-go-service-contract.py exactly."""
    if any((folder / cf).is_file() for cf in GO_CONTRACT_FILES):
        return True
    return _CONTRACT_HOOK._is_multi_service_folder(folder)


_ALLOWED_NON_GO_EXTENSIONS = {
    ".md",
    ".proto",
    ".avsc",  # Avro schema definitions — a contract artefact like .proto.
    ".yml",
    ".yaml",
    ".toml",
    ".conf",
    ".json",
    ".mod",
    ".sum",
    ".dockerignore",
    ".gitignore",
    ".golangci",
    ".staticcheck",
}

_ALLOWED_BASENAMES = {
    "Dockerfile",
    "Makefile",
    "go.mod",
    "go.sum",
    "api.proto",
    "api.http.md",
    "README.md",
    "LICENSE",
    ".golangci.yml",
    "staticcheck.conf",
}

# Untracked output files left over from go-mutesting / coverage runs.
_TOLERATED_ARTEFACTS = {
    "report.json",  # go-mutesting output, untracked
    "cover.out",
    "bench.txt",
    "PROMOTION-AUDIT.md",  # short-lived; auto-deleted at end of slice
}


def _git_ignored(paths: list[Path]) -> set[Path]:
    """Return the subset of `paths` that git itself ignores.

    Build outputs and protoc/buf intermediates (compiled binaries, *.tmp
    files) are gitignored debris, not tracked source the layer-fence rule
    governs. One batched `git check-ignore` keeps this cheap.
    """
    if not paths:
        return set()
    repo_root = SERVICES_DIR.parent
    try:
        result = subprocess.run(
            # `-c safe.directory=*` keeps this working when the repo is owned
            # by a different uid than the (container) user running the tests.
            ["git", "-c", "safe.directory=*", "-C", str(repo_root),
             "check-ignore", "--stdin"],
            input="\n".join(str(p) for p in paths),
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return set()
    ignored = {line.strip() for line in result.stdout.splitlines() if line.strip()}
    return {p for p in paths if str(p) in ignored}


def _is_test_fixture(path: Path) -> bool:
    name = path.name
    return (
        name.startswith("test_")
        or name.endswith("_test.go")
        or name.endswith("_test.py")
        or "/test/" in path.as_posix()
        or "/tests/" in path.as_posix()
    )


def _is_parity_baseline(path: Path) -> bool:
    name = path.name
    return (
        path.suffix == ".py"
        and (
            name.endswith("_baseline.py")
            or name.startswith("parity_")
            or "/parity/" in path.as_posix()
        )
    )


def _service_artefacts_ready(folder: Path) -> bool:
    """Return True if a service folder has both a binary and a contract."""
    binary = folder / GO_BINARY_ENTRY_TEMPLATE.format(name=folder.name)
    contract_ok = any((folder / cf).is_file() for cf in GO_CONTRACT_FILES)
    return binary.is_file() and contract_ok


def _streamd_ready() -> bool:
    streamd = SERVICES_DIR / "streamd"
    return streamd.is_dir() and _service_artefacts_ready(streamd)


class GoServicesLayerTests(TestCase):
    """Architecture regression for the services tier."""

    @skipUnless(_streamd_ready(), "depends on slice 1.5 Half B — streamd binary + contract not yet present")
    def test_when_services_folder_present_then_every_service_has_binary(self) -> None:
        for folder in go_service_folders():
            binary = folder / GO_BINARY_ENTRY_TEMPLATE.format(name=folder.name)
            self.assertTrue(
                binary.is_file(),
                f"services/{folder.name}/ must publish {binary.relative_to(SERVICES_DIR.parent)} — "
                f"library-only Go modules under services/ are forbidden",
            )

    @skipUnless(_streamd_ready(), "depends on slice 1.5 Half B — streamd binary + contract not yet present")
    def test_when_services_folder_present_then_every_service_has_contract(
        self,
    ) -> None:
        for folder in go_service_folders():
            self.assertTrue(
                _has_contract(folder),
                f"services/{folder.name}/ must publish ONE of {list(GO_CONTRACT_FILES)} — "
                f"or, for a multi-service folder, services.manifest.yaml + api/*.proto — "
                f"the contract is the public RPC surface",
            )

    def test_services_tier_contains_only_allowed_non_go_files(self) -> None:
        if not SERVICES_DIR.is_dir():
            self.skipTest("no services/ folder yet — nothing to check")
        candidates: list[Path] = []
        for folder in go_service_folders():
            for current, dirs, filenames in os.walk(folder):
                # Skip vendored / build outputs that are not tracked.
                dirs[:] = [d for d in dirs if d not in {"vendor", ".git", "build", "build_tests", "dist"}]
                for name in filenames:
                    full = Path(current) / name
                    if full.suffix == ".go":
                        continue
                    if name in _ALLOWED_BASENAMES:
                        continue
                    if name in _TOLERATED_ARTEFACTS:
                        continue
                    if full.suffix in _ALLOWED_NON_GO_EXTENSIONS:
                        continue
                    if _is_test_fixture(full):
                        continue
                    if _is_parity_baseline(full):
                        continue
                    candidates.append(full)
        # Drop gitignored build/temp debris (compiled binaries, *.tmp protoc
        # intermediates) — those are not tracked source the rule governs.
        ignored = _git_ignored(candidates)
        offenders = [
            str(p.relative_to(SERVICES_DIR.parent)) for p in candidates if p not in ignored
        ]
        self.assertEqual(
            offenders,
            [],
            "services/ may only contain Go source, contract files, docs, "
            "build files, test fixtures, and parity baselines; got: "
            + ", ".join(offenders[:10])
            + ("..." if len(offenders) > 10 else ""),
        )


if __name__ == "__main__":
    import unittest

    unittest.main()
