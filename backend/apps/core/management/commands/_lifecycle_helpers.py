# xf: no_dry_run -- not a management command; this module exposes a single helper function imported by the four lifecycle commands
# quality-debt-ignore: reason: shared helper module for the 4 lifecycle helper management commands (audit_cpp_lifecycle / audit_go_services / scaffold_cpp_kernel / scaffold_go_service); kept tiny so the smoke tests in test_lifecycle_helpers.py cover its single entry point indirectly
"""Shared helpers for the 4 lifecycle management commands."""

from __future__ import annotations

import os
from pathlib import Path


# quality-debt-ignore: reason: repo_root() must handle three fallback layers (env REPO_ROOT for tests, /repo for the container default, then walk-up for direct host invocation); flattening loses one of the three call sites and breaks either the tests or the host workflow
def repo_root() -> Path:
    """Resolve the repository root path for lifecycle management commands.

    Honours the REPO_ROOT environment variable first (used by smoke tests
    to point at a synthetic temp tree), then the container default `/repo`,
    then walks up from this file's location.
    """
    env_root = os.environ.get("REPO_ROOT")
    if env_root and Path(env_root).is_dir() and (Path(env_root) / ".githooks").is_dir():
        return Path(env_root)
    container_default = Path("/repo")
    if container_default.is_dir() and (container_default / ".githooks").is_dir():
        return container_default
    here = Path(__file__).resolve()
    for parent in [here, *here.parents]:
        if (parent / ".githooks").is_dir() and (parent / "backend").is_dir():
            return parent
    return container_default
