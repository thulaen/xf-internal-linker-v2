#!/usr/bin/env bash
set -euo pipefail
cd "${BUILD_WORKSPACE_DIRECTORY:-$(pwd)}"
export REPO_ROOT="${BUILD_WORKSPACE_DIRECTORY:-$(pwd)}"
exec python3 scripts/distributed_test_coordinator.py --dry-run --run-id bazel-default
