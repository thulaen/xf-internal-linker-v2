#!/usr/bin/env bash
set -euo pipefail
cd "${BUILD_WORKSPACE_DIRECTORY:-$(pwd)}"
export REPO_ROOT="${BUILD_WORKSPACE_DIRECTORY:-$(pwd)}"
export XF_BAZEL_INTERNAL=1
export XF_QUALITY_CACHE=0
export XF_PYTEST_DOCKER_CONTEXT="__local__"
exec python3 scripts/run_pytest_on_context.py \
  --targets apps/api/tests_embedding_views.py apps/pipeline/tests/test_run_embedding_provider_eval_command.py \
  --cov-targets apps.api.embedding_views,apps.pipeline.management.commands.run_embedding_provider_eval
