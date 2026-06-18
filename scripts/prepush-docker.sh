#!/usr/bin/env bash
# Push-time mutation gate — Bazel is the public entry point.
set -euo pipefail
repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

exec python scripts/bazel_default.py run //tools/quality:mutation -- "$@"
