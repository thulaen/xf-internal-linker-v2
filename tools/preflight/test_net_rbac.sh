#!/usr/bin/env bash
# SLICE-07 verification: xf-test permissions and network policies.

HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=cluster_lib.sh
. "$HERE/cluster_lib.sh"
cluster_require_gitbash "$0"

RBAC_MANIFEST="${RBAC_MANIFEST:-k8s/network/xf-test-rbac.yaml}"
NETPOL_MANIFEST="${NETPOL_MANIFEST:-k8s/network/xf-test-netpol.yaml}"

kubectl_mint() {
    ssh_host "$MINT_SSH" "kubectl $* --request-timeout=8s"
}

assert_yaml_parses() {
    local manifest="$1"
    python -c "import pathlib, yaml; list(yaml.safe_load_all(pathlib.Path('$manifest').read_text()))" \
        && pass "$manifest parses as YAML" \
        || fail "$manifest does not parse as YAML"
}

assert_can_i() {
    local account="$1" verb="$2" resource="$3" expected="$4" result
    result="$(kubectl_mint "auth can-i '$verb' '$resource' --as='system:serviceaccount:xf-test:$account' -n xf-test" 2>/dev/null)"
    [ "$result" = "$expected" ] && pass "$account can-i $verb $resource = $expected" \
        || fail "$account can-i $verb $resource returned ${result:-missing}, expected $expected"
}

assert_network_policy() {
    local name="$1"
    kubectl_mint "get networkpolicy '$name' -n xf-test" >/dev/null 2>&1 \
        && pass "NetworkPolicy $name exists in xf-test" \
        || fail "NetworkPolicy $name is missing in xf-test"
}

assert_vxlan_decision_visible() {
    ssh_host "$MINT_SSH" "ip link show flannel.1 >/dev/null 2>&1" \
        && pass "Mint shows the accepted VXLAN flannel interface" \
        || fail "Mint does not show flannel.1 VXLAN interface"
}

assert_yaml_parses "$RBAC_MANIFEST"
assert_yaml_parses "$NETPOL_MANIFEST"
assert_vxlan_decision_visible
assert_can_i xf-coordinator create jobs yes
assert_can_i xf-coordinator delete jobs yes
assert_can_i xf-coordinator create configmaps yes
assert_can_i xf-shard-runner list pods no
assert_can_i xf-merge get jobs yes
assert_can_i xf-merge delete jobs no
assert_network_policy default-deny-all
assert_network_policy allow-dns-egress
assert_network_policy allow-shard-host-egress

cluster_exit
