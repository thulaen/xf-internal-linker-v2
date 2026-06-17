#!/usr/bin/env bash
# SLICE-06 installer note for Dell k3s agent.
#
# Plain English: the live Dell agent is already joined. This script reapplies
# the repo-owned priority classes and labels Dell through kubectl on Mint.

HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=host_prep_lib.sh
. "$HERE/host_prep_lib.sh"
cluster_require_gitbash "$0"

PRIORITY_SOURCE="${PRIORITY_SOURCE:-k8s/scheduling/priorityclasses.yaml}"

[ -f "$PRIORITY_SOURCE" ] || { fail "Missing $PRIORITY_SOURCE"; cluster_exit; }
scp -q -o BatchMode=yes -o ConnectTimeout="$SSH_TIMEOUT" "$PRIORITY_SOURCE" "$MINT_SSH:/tmp/priorityclasses.yaml" \
    || { fail "Could not copy priority classes"; cluster_exit; }
ssh_host "$MINT_SSH" "kubectl apply -f /tmp/priorityclasses.yaml --request-timeout=20s" >/dev/null \
    || { fail "Could not apply priority classes"; cluster_exit; }
ssh_host "$MINT_SSH" "kubectl label node '$DELL_NODE' xf.io/role=worker xf.io/can-test=true xf.io/disk=ssd --overwrite --request-timeout=20s" >/dev/null \
    || { fail "Could not label Dell"; cluster_exit; }

printf 'Dell agent labels and priority classes reapplied. Re-run tools/preflight/test_k3s_agent.sh.\n'
