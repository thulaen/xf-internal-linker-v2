#!/usr/bin/env bash
# Generate local secret placeholders for the Bazel remote-cache smoke path.
set -euo pipefail

namespace="${1:-xf-build}"
cat <<YAML
apiVersion: v1
kind: Secret
metadata:
  name: bazel-remote-auth
  namespace: ${namespace}
type: Opaque
stringData:
  htpasswd: disabled-for-homelab-smoke
YAML
