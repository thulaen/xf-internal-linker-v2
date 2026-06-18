#!/usr/bin/env bash
set -euo pipefail
cd "${BUILD_WORKSPACE_DIRECTORY:-$(pwd)}"

bash scripts/run-python-mutation.sh "$@"
bash scripts/run-python-repo-mutation.sh "$@"
bash scripts/run-rust-mutation.sh "$@"
bash scripts/run-angular-mutation.sh "$@"
