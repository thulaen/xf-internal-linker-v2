# FR - Kubernetes Postgres Service For Dell

[SPEC FRESHNESS: reviewed=2026-06-17 next_review=2026-09-17]
[SPEC CITED: feature=fr-k8s-postgres-selectorless-service kind=technical_doc id=https://kubernetes.io/docs/concepts/services-networking/service/#services-without-selectors verified_at=2026-06-17]
[SPEC CITED: feature=fr-k8s-postgres-selectorless-service kind=technical_doc id=https://kubernetes.io/docs/concepts/services-networking/endpoint-slices/ verified_at=2026-06-17]
[SPEC CITED: feature=fr-k8s-postgres-selectorless-service kind=technical_doc id=https://kubernetes.io/docs/concepts/services-networking/dns-pod-service/ verified_at=2026-06-17]

## Goal

Give app, observability, and test pods a stable Kubernetes name for the Postgres
database that runs directly on Dell. The database is not a pod, so the Service is
selectorless: it has no pod selector. A hand-written EndpointSlice points that
Service at Dell's private cable address, `10.10.10.92:5432`.

## Current Repo Decision

The older KUBE PLAN used the name `dell-postgres` and mentioned `xf-prod`. The
repo already uses `postgres` as the app setting value and uses `xf-app` instead
of `xf-prod`. The implemented Service therefore stays named `postgres` in
`xf-app`, `xf-obs`, and `xf-test`.

The values live in `k8s/database/postgres-external-service.yaml` as one YAML
`List`. The Dell address, Service name, port name, and port number are defined
once with YAML anchors and reused for each namespace. The old observability-only
copy is intentionally removed so there is not a second source for the same route.

## Requirements

1. Each namespace in `POSTGRES_SERVICE_NAMESPACE_LIST` has a Service named
   `postgres`.
2. Each Service is `ClusterIP`, has no selector, and exposes named port
   `postgres` on `5432`.
3. Each namespace has one hand-written EndpointSlice named `postgres-external`.
4. Each EndpointSlice has label `kubernetes.io/service-name=postgres`.
5. Each EndpointSlice points only at Dell's private IP, `10.10.10.92`, port
   `5432`.
6. No `ExternalName` Service is used for this database route.
7. Legacy `Endpoints` objects named `postgres` are removed after the
   EndpointSlices exist, so live routing has one source.

## Behavior Proof

Given the consolidated manifest is applied, when
`tools/preflight/test_postgres_service.sh` runs, then it proves:

- the manifest parses as one Kubernetes `List`;
- the manifest uses EndpointSlice objects, not legacy Endpoints objects;
- every listed namespace has a selectorless `postgres` Service;
- every listed namespace has the expected EndpointSlice;
- the EndpointSlice address and port match Dell Postgres;
- no old live Endpoints object remains.

## Operations

Run `tools/preflight/install_postgres_service.sh` to apply the manifest to Mint.
The script copies the manifest with checksum verification, applies it with
`kubectl`, then deletes old live `postgres` Endpoints objects in the namespaces
from `POSTGRES_SERVICE_NAMESPACE_LIST`.

Run `tools/preflight/test_postgres_service.sh` after the installer. A failure
means pods may not route to Dell Postgres by the stable Service name.

## Scope Limits

This spec does not provision Postgres on Dell. It does not migrate data. It does
not configure PgBouncer. Those are separate KUBE PLAN slices.
