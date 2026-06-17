#!/usr/bin/env bash
# SLICE-12 verification: selectorless Postgres Services and EndpointSlices.

HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=cluster_lib.sh
. "$HERE/cluster_lib.sh"
cluster_require_gitbash "$0"

POSTGRES_SERVICE_MANIFEST="${POSTGRES_SERVICE_MANIFEST:-k8s/database/postgres-external-service.yaml}"

kubectl_mint() {
    ssh_host "$MINT_SSH" "kubectl $* --request-timeout=8s"
}

jsonpath_value() {
    local resource="$1" name="$2" namespace="$3" path="$4"
    kubectl_mint "get '$resource' '$name' -n '$namespace' -o jsonpath='{$path}'" 2>/dev/null
}

assert_equals() {
    local label="$1" actual="$2" expected="$3"
    [ "$actual" = "$expected" ] && pass "$label = $expected" \
        || fail "$label returned ${actual:-missing}, expected $expected"
}

assert_empty() {
    local label="$1" actual="$2"
    [ -z "$actual" ] && pass "$label is empty" \
        || fail "$label returned $actual, expected empty"
}

assert_manifest_shape() {
    python -c "import pathlib, yaml; data=yaml.safe_load(pathlib.Path('$POSTGRES_SERVICE_MANIFEST').read_text()); assert data['kind'] == 'List'; assert all(item.get('kind') != 'Endpoints' for item in data['items']); ips = {addr for item in data['items'] if item.get('kind') == 'EndpointSlice' for ep in item.get('endpoints', []) for addr in ep.get('addresses', [])}; assert ips == {'$DELL_WIRED_IP'}" \
        && pass "$POSTGRES_SERVICE_MANIFEST is a List with EndpointSlices only" \
        || fail "$POSTGRES_SERVICE_MANIFEST has the wrong selectorless-service shape"
}

assert_service() {
    local namespace="$1" selector service_type service_port
    kubectl_mint "get service '$POSTGRES_SERVICE_NAME' -n '$namespace'" >/dev/null 2>&1 \
        || { fail "$namespace/$POSTGRES_SERVICE_NAME Service is missing"; return; }
    service_type="$(jsonpath_value service "$POSTGRES_SERVICE_NAME" "$namespace" ".spec.type")"
    service_port="$(jsonpath_value service "$POSTGRES_SERVICE_NAME" "$namespace" ".spec.ports[0].port")"
    selector="$(jsonpath_value service "$POSTGRES_SERVICE_NAME" "$namespace" ".spec.selector")"
    assert_equals "$namespace/$POSTGRES_SERVICE_NAME Service type" "$service_type" "ClusterIP"
    assert_equals "$namespace/$POSTGRES_SERVICE_NAME Service port" "$service_port" "$POSTGRES_SERVICE_PORT"
    assert_empty "$namespace/$POSTGRES_SERVICE_NAME Service selector" "$selector"
}

assert_endpointslice() {
    local namespace="$1" found ip port service_label
    found="$(kubectl_mint "get endpointslice '$POSTGRES_ENDPOINTSLICE_NAME' -n '$namespace' -o name" 2>/dev/null)"
    assert_equals "$namespace EndpointSlice object" "$found" "endpointslice.discovery.k8s.io/$POSTGRES_ENDPOINTSLICE_NAME"
    service_label="$(jsonpath_value endpointslice "$POSTGRES_ENDPOINTSLICE_NAME" "$namespace" ".metadata.labels.kubernetes\\.io/service-name")"
    ip="$(jsonpath_value endpointslice "$POSTGRES_ENDPOINTSLICE_NAME" "$namespace" ".endpoints[0].addresses[0]")"
    port="$(jsonpath_value endpointslice "$POSTGRES_ENDPOINTSLICE_NAME" "$namespace" ".ports[0].port")"
    assert_equals "$namespace EndpointSlice service label" "$service_label" "$POSTGRES_SERVICE_NAME"
    assert_equals "$namespace EndpointSlice address" "$ip" "$DELL_WIRED_IP"
    assert_equals "$namespace EndpointSlice port" "$port" "$POSTGRES_SERVICE_PORT"
}

assert_no_legacy_endpoints() {
    local namespace="$1"
    kubectl_mint "get endpoints '$POSTGRES_SERVICE_NAME' -n '$namespace'" >/dev/null 2>&1 \
        && fail "$namespace still has legacy Endpoints for $POSTGRES_SERVICE_NAME" \
        || pass "$namespace has no legacy Endpoints for $POSTGRES_SERVICE_NAME"
}

assert_manifest_shape
for namespace in $POSTGRES_SERVICE_NAMESPACE_LIST; do
    assert_service "$namespace"
    assert_endpointslice "$namespace"
    assert_no_legacy_endpoints "$namespace"
done

cluster_exit
