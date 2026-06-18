# FR - Backend Deployment Rehearsal

[SPEC FRESHNESS: reviewed_at=2026-06-17 next_review=2026-09-17]

## Purpose

Slice 17 rehearses the Django backend Deployment in the cluster. The backend is
scheduled on Dell, reads secrets from Kubernetes, and talks to the database
through PgBouncer.

## Current Source Of Truth

- Backend Deployment and Service: `k8s/app/backend.yaml`.
- Migration Job: `k8s/app/backend-migrate-job.yaml`.
- Shared settings: `k8s/app/xf-app-config.yaml`.

## Behavior

Given the manifests are applied in rehearsal, when the backend pod starts, then
it serves HTTP on port 8000 and reports readiness through `/api/system/health/`.

## Citations

- Kubernetes documentation - Deployments: https://kubernetes.io/docs/concepts/workloads/controllers/deployment/
- Kubernetes documentation - Probes: https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/
