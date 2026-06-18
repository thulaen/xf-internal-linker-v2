#!/usr/bin/env bash
set -euo pipefail
cd "${BUILD_WORKSPACE_DIRECTORY:-$(pwd)}"
export REPO_ROOT="${BUILD_WORKSPACE_DIRECTORY:-$(pwd)}"
export XF_BAZEL_INTERNAL=1
export QUALITY_EVIDENCE_SKIP_IMPORT="${QUALITY_EVIDENCE_SKIP_IMPORT:-1}"
export XF_LINT_DOCKER_CONTEXT="${XF_LINT_DOCKER_CONTEXT:-__local__}"
export XF_PYTEST_DOCKER_CONTEXT="${XF_PYTEST_DOCKER_CONTEXT:-__local__}"
exec bash tools/quality/internal/run-python-quality.sh "$@"
