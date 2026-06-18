#!/usr/bin/env bash
set -euo pipefail
cd "${BUILD_WORKSPACE_DIRECTORY:-$(pwd)}"

python3 scripts/gen_bazel_python.py --check
python3 scripts/gen_bazel_rust.py --check
python3 scripts/gen_bazel_frontend.py
