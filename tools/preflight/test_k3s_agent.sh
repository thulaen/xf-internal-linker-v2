#!/usr/bin/env bash
# SLICE-06 verification: Dell k3s worker placement.
#
# Plain English: checks that Dell is the test-capable worker and that the
# scheduling priority classes already used by the live topology exist.

HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=host_prep_lib.sh
. "$HERE/host_prep_lib.sh"
cluster_require_gitbash "$0"

kubectl_mint() {
    ssh_host "$MINT_SSH" "kubectl $* --request-timeout=8s"
}

assert_dell_ready() {
    local ready
    ready="$(kubectl_mint "get node '$DELL_NODE' --no-headers" 2>/dev/null | awk '{print $2}')"
    [ "$ready" = "Ready" ] && pass "Dell node is Ready" || fail "Dell node is ${ready:-missing}"
}

assert_dell_labels() {
    local labels
    labels="$(kubectl_mint "get node '$DELL_NODE' -o jsonpath='{.metadata.labels.xf\\.io/role} {.metadata.labels.xf\\.io/can-test} {.metadata.labels.xf\\.io/disk}'" 2>/dev/null)"
    [ "$labels" = "worker true ssd" ] && pass "Dell has worker/test/SSD labels" \
        || fail "Dell labels are '${labels:-missing}', expected 'worker true ssd'"
}

assert_only_dell_can_test() {
    local nodes
    nodes="$(kubectl_mint "get nodes -l xf.io/can-test=true --no-headers" 2>/dev/null | awk '{print $1}')"
    [ "$nodes" = "$DELL_NODE" ] && pass "Only Dell is labelled can-test=true" \
        || fail "can-test=true nodes are '${nodes:-none}'"
}

assert_no_dell_taint_for_current_topology() {
    local taints
    taints="$(kubectl_mint "get node '$DELL_NODE' -o jsonpath='{.spec.taints}'" 2>/dev/null)"
    [ -z "$taints" ] && pass "Dell has no test taint in the current two-node topology" \
        || fail "Dell has unexpected taints: $taints"
}

assert_priority_classes() {
    local name
    for name in xf-infra xf-app xf-test; do
        kubectl_mint "get priorityclass '$name'" >/dev/null 2>&1 \
            && pass "PriorityClass $name exists" \
            || fail "PriorityClass $name is missing"
    done
}

assert_dell_ready
assert_dell_labels
assert_only_dell_can_test
assert_no_dell_taint_for_current_topology
assert_priority_classes

cluster_exit
