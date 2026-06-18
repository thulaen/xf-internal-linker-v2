#!/usr/bin/env bash
set -euo pipefail
cd "${BUILD_WORKSPACE_DIRECTORY:-$(pwd)}"
export REPO_ROOT="${BUILD_WORKSPACE_DIRECTORY:-$(pwd)}"
export XF_BAZEL_INTERNAL=1
exec bash tools/quality/internal/run-rust-quality.sh "$@"
