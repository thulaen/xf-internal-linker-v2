#!/usr/bin/env bash
# SLICE-09 verification: storage classes, claims, and namespace quotas.

HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=cluster_lib.sh
. "$HERE/cluster_lib.sh"
cluster_require_gitbash "$0"

STORAGE_MANIFESTS="${STORAGE_MANIFESTS:-k8s/storage/nfs-cold-provisioner.yaml k8s/storage/ssd-hot-provisioner.yaml k8s/scheduling/resource-limits.yaml k8s/obs/02-resource-limits.yaml k8s/scheduling/support-resource-limits.yaml k8s/storage/workload-pvcs.yaml}"

kubectl_mint() {
    ssh_host "$MINT_SSH" "kubectl $* --request-timeout=8s"
}

jsonpath_value() {
    local resource="$1" name="$2" namespace="$3" path="$4"
    if [ -n "$namespace" ]; then
        kubectl_mint "get '$resource' '$name' -n '$namespace' -o jsonpath='{$path}'" 2>/dev/null
    else
        kubectl_mint "get '$resource' '$name' -o jsonpath='{$path}'" 2>/dev/null
    fi
}

assert_equals() {
    local label="$1" actual="$2" expected="$3"
    actual="${actual%$'\r'}"
    expected="${expected%$'\r'}"
    [ "$actual" = "$expected" ] && pass "$label = $expected" \
        || fail "$label returned ${actual:-missing}, expected $expected"
}

assert_exists() {
    local resource="$1" name="$2" namespace="$3" label="$4"
    if [ -n "$namespace" ]; then
        kubectl_mint "get '$resource' '$name' -n '$namespace'" >/dev/null 2>&1 \
            && pass "$label exists" || fail "$label is missing"
    else
        kubectl_mint "get '$resource' '$name'" >/dev/null 2>&1 \
            && pass "$label exists" || fail "$label is missing"
    fi
}

assert_yaml_parses() {
    python -c "import pathlib, yaml; [list(yaml.safe_load_all(pathlib.Path(p).read_text())) for p in '$STORAGE_MANIFESTS'.split()]" \
        && pass "Slice 9 manifests parse as YAML" \
        || fail "Slice 9 manifests do not parse as YAML"
}

iter_manifest_objects() {
    local kinds_csv="$1"
    python -c "import pathlib, yaml
kinds=set('$kinds_csv'.split(','))
for path in '$STORAGE_MANIFESTS'.split():
    for doc in yaml.safe_load_all(pathlib.Path(path).read_text()):
        if not doc:
            continue
        items = doc.get('items', []) if doc.get('kind') == 'List' else [doc]
        for item in items:
            if item.get('kind') in kinds:
                meta=item.get('metadata', {})
                spec=item.get('spec', {})
                print(item.get('kind'), meta.get('namespace', ''), meta.get('name', ''), spec.get('storageClassName', ''), sep='\\t')"
}

assert_storage_class() {
    local name="$1" provisioner="$2" binding="$3" reclaim="$4" actual
    assert_exists storageclass "$name" "" "StorageClass $name"
    actual="$(jsonpath_value storageclass "$name" "" ".provisioner")"
    assert_equals "$name provisioner" "$actual" "$provisioner"
    actual="$(jsonpath_value storageclass "$name" "" ".volumeBindingMode")"
    assert_equals "$name volume binding" "$actual" "$binding"
    actual="$(jsonpath_value storageclass "$name" "" ".reclaimPolicy")"
    assert_equals "$name reclaim policy" "$actual" "$reclaim"
}

assert_quota_and_defaults() {
    local namespace="$1" quota="$2" defaults="$3"
    assert_exists resourcequota "$quota" "$namespace" "$namespace ResourceQuota $quota"
    assert_exists limitrange "$defaults" "$namespace" "$namespace LimitRange $defaults"
}

assert_pvc_status() {
    local namespace="$1" name="$2" expected="$3" actual
    actual="$(jsonpath_value pvc "$name" "$namespace" ".status.phase")"
    assert_equals "$namespace/$name PVC status" "$actual" "$expected"
}

assert_pvc_class() {
    local namespace="$1" name="$2" expected="$3" actual
    actual="$(jsonpath_value pvc "$name" "$namespace" ".spec.storageClassName")"
    assert_equals "$namespace/$name PVC storage class" "$actual" "$expected"
}

copy_named_manifest() {
    local local_path="$1" name="$2" remote
    remote="/tmp/${name}-$$.yaml"
    transfer_with_checksum_retry "$local_path" "$MINT_SSH" "$remote" >/dev/null \
        || { fail "Could not copy $name proof manifest"; return 1; }
    printf '%s' "$remote"
}

delete_remote_manifest() {
    local remote="$1"
    [ -n "$remote" ] && ssh_host "$MINT_SSH" "rm -f '$remote'" >/dev/null 2>&1 || true
}

wait_pod_succeeded() {
    local namespace="$1" pod="$2" phase attempt
    for attempt in $(seq 1 60); do
        phase="$(jsonpath_value pod "$pod" "$namespace" ".status.phase")"
        [ "$phase" = Succeeded ] && { pass "$namespace/$pod write probe succeeded"; return; }
        [ "$phase" = Failed ] && { fail "$namespace/$pod write probe failed"; return; }
        sleep 2
    done
    fail "$namespace/$pod write probe timed out"
}

apply_probe_manifest() {
    local local_path="$1" name="$2" remote
    remote="$(copy_named_manifest "$local_path" "$name")" || return 1
    if kubectl_mint "apply -f '$remote'" >/dev/null; then
        pass "$name proof pod created"
        delete_remote_manifest "$remote"
        return 0
    fi
    fail "$name proof pod could not be created"
    delete_remote_manifest "$remote"
    return 1
}

assert_no_live_cold_pv_uses_delete() {
    local rows bad
    rows="$(kubectl_mint "get pv -o jsonpath='{range .items[?(@.spec.storageClassName==\"nfs-cold\")]}{.metadata.name}:{.spec.persistentVolumeReclaimPolicy}{\"\\n\"}{end}'")"
    bad="$(printf '%s\n' "$rows" | awk -F: '$2 != "" && $2 != "Retain" {print}')"
    [ -z "$bad" ] && pass "all live nfs-cold volumes retain data after claim delete" \
        || fail "nfs-cold volumes with unsafe reclaim policy: $bad"
}

assert_oversized_hot_pvc_is_rejected() {
    local tmp remote output status
    tmp="$(mktemp)" || { fail "Could not create quota proof manifest"; return; }
    cat > "$tmp" <<'YAML'
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: storage-quota-proof
  namespace: xf-test
spec:
  accessModes: ["ReadWriteOnce"]
  storageClassName: ssd-hot
  resources:
    requests:
      storage: 101Gi
YAML
    remote="$(copy_named_manifest "$tmp" storage-quota-proof)" || { rm -f "$tmp"; return; }
    output="$(ssh_host "$MINT_SSH" "kubectl apply --dry-run=server -f '$remote' --request-timeout=8s 2>&1")"
    status=$?
    rm -f "$tmp"
    delete_remote_manifest "$remote"
    if [ "$status" -eq 0 ]; then
        fail "xf-test accepted an oversized hot claim"
    elif printf '%s' "$output" | grep -Eqi "exceeded quota|maximum storage usage|max storage"; then
        pass "xf-test rejects oversized hot claims"
    else
        fail "xf-test oversized hot claim returned an unexpected error: $output"
    fi
}

assert_limitrange_injects_defaults() {
    local tmp remote output
    tmp="$(mktemp)" || { fail "Could not create defaults proof manifest"; return; }
    cat > "$tmp" <<'YAML'
apiVersion: v1
kind: Pod
metadata:
  name: storage-defaults-proof
  namespace: xf-test
spec:
  restartPolicy: Never
  containers:
    - name: proof
      image: busybox:1.36
      command: ["sh", "-c", "true"]
YAML
    remote="$(copy_named_manifest "$tmp" storage-defaults-proof)" || { rm -f "$tmp"; return; }
    output="$(ssh_host "$MINT_SSH" "kubectl apply --dry-run=server -f '$remote' -o jsonpath='{.spec.containers[0].resources.requests.cpu}:{.spec.containers[0].resources.requests.memory}' --request-timeout=8s")"
    rm -f "$tmp"
    delete_remote_manifest "$remote"
    assert_equals "xf-test default pod requests" "$output" "100m:128Mi"
}

clear_test_scratch_wrong_node() {
    local phase selected
    phase="$(jsonpath_value pvc test-scratch xf-test ".status.phase")"
    selected="$(jsonpath_value pvc test-scratch xf-test ".metadata.annotations.volume\\.kubernetes\\.io/selected-node")"
    if [ "$phase" = Pending ] && [ -n "$selected" ] && [ "$selected" != "$DELL_NODE" ]; then
        kubectl_mint "annotate pvc test-scratch -n xf-test volume.kubernetes.io/selected-node-" >/dev/null \
            && pass "xf-test/test-scratch stale selected node cleared" \
            || fail "xf-test/test-scratch stale selected node could not be cleared"
    fi
}

run_storage_probe() {
    local namespace="$1" pod="$2" claim="$3" mode="$4" tmp
    tmp="$(mktemp)" || { fail "Could not create $pod proof manifest"; return; }
    cat > "$tmp" <<YAML
apiVersion: v1
kind: Pod
metadata:
  name: $pod
  namespace: $namespace
spec:
  restartPolicy: Never
  nodeSelector:
    kubernetes.io/hostname: $DELL_NODE
  containers:
    - name: proof
      image: busybox:1.36
      command:
        - sh
        - -c
        - "mkdir -p /mnt/probe/.storage-proof && echo $mode > /mnt/probe/.storage-proof/marker && test -s /mnt/probe/.storage-proof/marker && rm -f /mnt/probe/.storage-proof/marker"
      volumeMounts:
        - name: probe-storage
          mountPath: /mnt/probe
  volumes:
    - name: probe-storage
      persistentVolumeClaim:
        claimName: $claim
YAML
    apply_probe_manifest "$tmp" "$pod" || { rm -f "$tmp"; return; }
    rm -f "$tmp"
    wait_pod_succeeded "$namespace" "$pod"
}

cleanup_probe_pods() {
    kubectl_mint "delete pod storage-probe-cold -n xf-app --ignore-not-found=true" >/dev/null 2>&1 || true
    kubectl_mint "delete pod storage-probe-hot -n xf-test --ignore-not-found=true" >/dev/null 2>&1 || true
}

trap cleanup_probe_pods EXIT

assert_yaml_parses
assert_storage_class nfs-cold xf.cluster/nfs-cold Immediate Retain
assert_storage_class ssd-hot cluster.local/ssd-hot WaitForFirstConsumer Delete
assert_no_live_cold_pv_uses_delete
assert_oversized_hot_pvc_is_rejected
assert_limitrange_injects_defaults

assert_exists deployment nfs-client-provisioner xf-storage "NFS provisioner Deployment"
assert_exists deployment ssd-hot-provisioner xf-storage "SSD hot provisioner Deployment"

while IFS=$'\t' read -r kind namespace name _; do
    [ "$kind" = ResourceQuota ] && assert_exists resourcequota "$name" "$namespace" "$namespace ResourceQuota $name"
    [ "$kind" = LimitRange ] && assert_exists limitrange "$name" "$namespace" "$namespace LimitRange $name"
done < <(iter_manifest_objects ResourceQuota,LimitRange)

while IFS=$'\t' read -r _ namespace name storage_class; do
    storage_class="${storage_class%$'\r'}"
    assert_pvc_class "$namespace" "$name" "$storage_class"
    if [ "$storage_class" = nfs-cold ]; then
        assert_pvc_status "$namespace" "$name" Bound
    else
        pvc_status="$(jsonpath_value pvc "$name" "$namespace" ".status.phase")"
        case "$pvc_status" in
            Pending|Bound) pass "$namespace/$name PVC status is $pvc_status" ;;
            *) fail "$namespace/$name PVC status returned ${pvc_status:-missing}, expected Pending or Bound" ;;
        esac
    fi
done < <(iter_manifest_objects PersistentVolumeClaim)

cleanup_probe_pods
run_storage_probe xf-app storage-probe-cold media-files cold
clear_test_scratch_wrong_node
run_storage_probe xf-test storage-probe-hot test-scratch hot

cluster_exit
