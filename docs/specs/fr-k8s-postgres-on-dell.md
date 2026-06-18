# FR - Dell Postgres Rehearsal

[SPEC FRESHNESS: reviewed_at=2026-06-17 next_review=2026-09-17]

## Purpose

Slice 11 proves the database endpoint on Dell before the live database is moved.
The rehearsal checks that later Kubernetes Services can point to Dell without
changing production data.

## Current Source Of Truth

- Cluster Service pointer: `k8s/database/postgres-external-service.yaml`.
- Install or reapply helper: `tools/preflight/install_postgres_service.sh`.
- Proof helper: `tools/preflight/test_postgres_service.sh`.

## Behavior

Given Dell is reachable on the private wired address, when the proof script runs,
then each namespace has a selectorless `postgres` Service and an EndpointSlice
that points to `10.10.10.92:5432`.

## Rehearsal Boundary

This pass does not stop the current MSI database, change application settings, or
restore live data. The database move is owned by Slice 13 and remains blocked
until explicit go-live.

## Citations

- PostgreSQL documentation - Server setup and configuration: https://www.postgresql.org/docs/current/runtime-config.html
- Kubernetes documentation - Services without selectors: https://kubernetes.io/docs/concepts/services-networking/service/#services-without-selectors
- Kubernetes documentation - EndpointSlices: https://kubernetes.io/docs/concepts/services-networking/endpoint-slices/
