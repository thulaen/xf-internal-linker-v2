# FR - Redis-Compatible Cache In Cluster

[SPEC FRESHNESS: reviewed_at=2026-06-17 next_review=2026-09-17]

## Purpose

Slice 16 provides a Redis-compatible cache inside the cluster. The repo uses
Valkey because it speaks the same protocol and keeps the existing `redis` service
name for the app.

## Current Source Of Truth

- Manifest: `k8s/cache/valkey.yaml`.
- Service name: `redis` in namespace `xf-app`.

## Behavior

Given the manifest is applied, when pods use `redis://redis:6379`, then the
request reaches the Valkey pod and cache data remains disposable.

## Citations

- Valkey documentation: https://valkey.io/
- Kubernetes documentation - Services: https://kubernetes.io/docs/concepts/services-networking/service/
