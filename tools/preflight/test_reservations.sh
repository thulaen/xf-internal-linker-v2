#!/usr/bin/env bash
# SLICE-10 verification: node reservations, image cleanup, and priorities.

HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=cluster_lib.sh
. "$HERE/cluster_lib.sh"
cluster_require_gitbash "$0"

MINT_CONFIG_SOURCE="${MINT_CONFIG_SOURCE:-k8s/cluster/mint-k3s-config.yaml}"
DELL_CONFIG_SOURCE="${DELL_CONFIG_SOURCE:-k8s/cluster/dell-k3s-agent-config.yaml}"
PRIORITY_SOURCE="${PRIORITY_SOURCE:-k8s/scheduling/priorityclasses.yaml}"

kubectl_mint() {
    ssh_host "$MINT_SSH" "kubectl $* --request-timeout=8s"
}

jsonpath_value() {
    local resource="$1" name="$2" path="$3"
    kubectl_mint "get '$resource' '$name' -o jsonpath='{$path}'" 2>/dev/null
}

assert_equals() {
    local label="$1" actual="$2" expected="$3"
    actual="${actual%$'\r'}"
    expected="${expected%$'\r'}"
    [ "$actual" = "$expected" ] && pass "$label = $expected" \
        || fail "$label returned ${actual:-missing}, expected $expected"
}

assert_not_equals() {
    local label="$1" left="$2" right="$3"
    left="${left%$'\r'}"
    right="${right%$'\r'}"
    [ -n "$left" ] && [ -n "$right" ] && [ "$left" != "$right" ] \
        && pass "$label differs as expected ($left vs $right)" \
        || fail "$label returned ${left:-missing} and ${right:-missing}, expected different values"
}

assert_yaml_parses() {
    python -c "import pathlib, yaml; [list(yaml.safe_load_all(pathlib.Path(p).read_text())) for p in ['$MINT_CONFIG_SOURCE', '$DELL_CONFIG_SOURCE', '$PRIORITY_SOURCE']]" \
        && pass "Slice 10 manifests parse as YAML" \
        || fail "Slice 10 manifests do not parse as YAML"
}

assert_local_config_arg() {
    local file="$1" arg="$2"
    python -c "import pathlib, yaml; args=yaml.safe_load(pathlib.Path('$file').read_text())['kubelet-arg']; assert '$arg' in args" \
        && pass "$file contains $arg" \
        || fail "$file is missing $arg"
}

assert_remote_config_arg() {
    local host="$1" label="$2" arg="$3"
    ssh_host "$host" "sudo grep -F -- '$arg' /etc/rancher/k3s/config.yaml >/dev/null" \
        && pass "$label live config contains $arg" \
        || fail "$label live config is missing $arg"
}

iter_config_args() {
    local file="$1"
    python -c "import pathlib, yaml; [print(arg) for arg in yaml.safe_load(pathlib.Path('$file').read_text())['kubelet-arg']]"
}

iter_priority_classes() {
    python -c "import pathlib, yaml
for doc in yaml.safe_load_all(pathlib.Path('$PRIORITY_SOURCE').read_text()):
    if not doc:
        continue
    name=doc['metadata']['name']
    value=doc['value']
    default=str(doc.get('globalDefault', False)).lower()
    preemption=doc.get('preemptionPolicy', 'PreemptLowerPriority')
    print(name, value, default, preemption, sep='\\t')"
}

assert_node_reserved() {
    local node="$1" cap_cpu alloc_cpu cap_mem alloc_mem ready
    ready="$(kubectl_mint "get node '$node' --no-headers" | awk '{print $2}')"
    assert_equals "$node Ready" "$ready" "Ready"
    cap_cpu="$(jsonpath_value node "$node" ".status.capacity.cpu")"
    alloc_cpu="$(jsonpath_value node "$node" ".status.allocatable.cpu")"
    cap_mem="$(jsonpath_value node "$node" ".status.capacity.memory")"
    alloc_mem="$(jsonpath_value node "$node" ".status.allocatable.memory")"
    assert_not_equals "$node allocatable CPU vs capacity CPU" "$alloc_cpu" "$cap_cpu"
    assert_not_equals "$node allocatable memory vs capacity memory" "$alloc_mem" "$cap_mem"
}

assert_priority_class() {
    local name="$1" value="$2" global="$3" preemption="$4" actual
    actual="$(jsonpath_value priorityclass "$name" ".value")"
    assert_equals "$name value" "$actual" "$value"
    actual="$(jsonpath_value priorityclass "$name" ".globalDefault")"
    [ -z "$actual" ] && actual=false
    assert_equals "$name global default" "$actual" "$global"
    actual="$(jsonpath_value priorityclass "$name" ".preemptionPolicy")"
    assert_equals "$name preemption policy" "$actual" "$preemption"
}

assert_yaml_parses

while IFS= read -r arg; do
    arg="${arg%$'\r'}"
    assert_local_config_arg "$MINT_CONFIG_SOURCE" "$arg"
    assert_remote_config_arg "$MINT_SSH" Mint "$arg"
done < <(iter_config_args "$MINT_CONFIG_SOURCE")

while IFS= read -r arg; do
    arg="${arg%$'\r'}"
    assert_local_config_arg "$DELL_CONFIG_SOURCE" "$arg"
    assert_remote_config_arg "$DELL_SSH" Dell "$arg"
done < <(iter_config_args "$DELL_CONFIG_SOURCE")

assert_node_reserved "$MINT_NODE"
assert_node_reserved "$DELL_NODE"

while IFS=$'\t' read -r name value global preemption; do
    assert_priority_class "$name" "$value" "$global" "$preemption"
done < <(iter_priority_classes)

cluster_exit
