#!/usr/bin/env bash
# Static smoke checks for the Slice 25 Bazel backend manifests.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
test -f "$ROOT/k8s/bazel/bazel-remote.yaml"
test -f "$ROOT/k8s/bazel/buildbuddy-values.yaml"
grep -q "bazel-remote" "$ROOT/.bazelrc"
grep -q "xf.io/role: control-storage" "$ROOT/k8s/bazel/bazel-remote.yaml"
echo "[BAZEL BACKENDS: static proof passed]"
