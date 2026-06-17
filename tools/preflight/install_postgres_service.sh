#!/usr/bin/env bash
# SLICE-12 installer: apply selectorless Postgres Services and EndpointSlices.

HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=cluster_lib.sh
. "$HERE/cluster_lib.sh"
cluster_require_gitbash "$0"

POSTGRES_SERVICE_MANIFEST="${POSTGRES_SERVICE_MANIFEST:-k8s/database/postgres-external-service.yaml}"

[ -f "$POSTGRES_SERVICE_MANIFEST" ] || { fail "Missing $POSTGRES_SERVICE_MANIFEST"; cluster_exit; }

remote="/tmp/$(basename "$POSTGRES_SERVICE_MANIFEST")"
transfer_with_checksum_retry "$POSTGRES_SERVICE_MANIFEST" "$MINT_SSH" "$remote" >/dev/null \
    || { fail "Could not copy $POSTGRES_SERVICE_MANIFEST"; cluster_exit; }

ssh_host "$MINT_SSH" "kubectl apply -f '$remote' --request-timeout=20s" >/dev/null \
    || { fail "Could not apply $POSTGRES_SERVICE_MANIFEST"; cluster_exit; }

for namespace in $POSTGRES_SERVICE_NAMESPACE_LIST; do
    ssh_host "$MINT_SSH" \
        "kubectl delete endpoints '$POSTGRES_SERVICE_NAME' -n '$namespace' --ignore-not-found --request-timeout=20s" \
        >/dev/null || { fail "Could not delete legacy Endpoints in $namespace"; cluster_exit; }
done

printf 'Postgres Services and EndpointSlices applied. Re-run tools/preflight/test_postgres_service.sh.\n'
