#!/usr/bin/env python3
"""Rule L - generated stubs only move when api.proto / api.http.md moves.

The repo commits generated protobuf + grpc stubs so the build is
reproducible without re-running protoc. But it is easy to accidentally
re-run protoc with a newer plugin version and end up with a giant
unrelated diff in `_pb2.py`, `_pb2_grpc.py`, or `*.pb.go`. This hook
blocks commits where the generated stubs were touched but the source
contract (api.proto / api.http.md) was NOT.

The intent is: stubs are derived artefacts. They change WHEN AND ONLY
WHEN the contract changes. Anything else is generator-version drift.

Watched stub patterns:
  - services/<name>/api/gen/*.pb.go
  - services/<name>/api/gen/*_grpc.pb.go
  - backend/apps/<app>/_<name>_pb2/api_pb2.py
  - backend/apps/<app>/_<name>_pb2/api_pb2_grpc.py

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

_GO_STUB_RE = re.compile(
    r"^services/([a-z][a-z0-9_-]*)/api/gen/.+\.pb\.go$"
)
_PY_STUB_RE = re.compile(
    r"^backend/apps/[a-z_]+/_([a-z][a-z0-9_-]*)_pb2/.+_pb2(?:_grpc)?\.py$"
)


def _staged() -> list[str]:
    stdout = run_git(
        REPO_ROOT,
        ["diff", "--cached", "--name-only", "--diff-filter=ACM"],
    )
    return [line.strip() for line in stdout.splitlines() if line.strip()]


def _services_with_stub_diffs(paths: list[str]) -> set[str]:
    services: set[str] = set()
    for p in paths:
        m = _GO_STUB_RE.match(p)
        if m:
            services.add(m.group(1))
            continue
        m = _PY_STUB_RE.match(p)
        if m:
            services.add(m.group(1))
    return services


def _service_contract_in_diff(paths: list[str], service: str) -> bool:
    """True when a contract source for `service` is also staged.

    Single-service folders (the streamd shape) carry exactly one of:
      - services/<svc>/api.proto
      - services/<svc>/api.http.md

    Multi-service folders (the sidecars shape — 40 services in one binary)
    split the contract across `services/<svc>/api/*.proto` files (one per
    sub-service). The hook accepts EITHER shape: if any contract file for
    the service is in the diff, the regen is justified.
    """
    contract_paths = {
        f"services/{service}/api.proto",
        f"services/{service}/api.http.md",
    }
    if any(p in contract_paths for p in paths):
        return True
    # Multi-service folder: any *.proto under services/<svc>/api/ counts as
    # a contract change. Exclude the api/gen/ directory which holds derived
    # output, not source.
    multi_prefix = f"services/{service}/api/"
    gen_prefix = f"services/{service}/api/gen/"
    for p in paths:
        if p.startswith(multi_prefix) and not p.startswith(gen_prefix) and p.endswith(".proto"):
            return True
    return False


def main() -> int:
    staged = _staged()
    if not staged:
        return 0
    services = _services_with_stub_diffs(staged)
    if not services:
        return 0
    bad: list[str] = []
    for service in sorted(services):
        if not _service_contract_in_diff(staged, service):
            bad.append(service)
    if not bad:
        return 0
    sys.stderr.write(
        "FAIL check-stubs-not-regenerated: generated protobuf / gRPC "
        "stubs are staged but the source contract (api.proto / "
        "api.http.md) for the same service is NOT.\n"
        "WHY: Rule L treats generated stubs as derived artefacts. They "
        "change ONLY when the contract changes. A stub diff without a "
        "contract diff almost always means an agent accidentally re-ran "
        "protoc with a different plugin version, which pollutes git "
        "history with noise.\n"
        "UNBLOCK: Either (a) revert the stub changes (`git checkout HEAD -- "
        "<paths>`) if you did not mean to regenerate, OR (b) also stage "
        "the matching api.proto / api.http.md change that justifies the "
        "regeneration, OR (c) if the contract really did not change and "
        "you genuinely want a stub-only diff (rare; usually a generator "
        "upgrade), add the file-level waiver comment "
        "`# quality-debt-ignore: reason: <plain English>` near the top "
        "of one of the stub files and re-stage.\n"
    )
    for service in bad:
        sys.stderr.write(f"  service `{service}` - stubs changed but contract did not\n")
    return 2


if __name__ == "__main__":
    sys.exit(main())
