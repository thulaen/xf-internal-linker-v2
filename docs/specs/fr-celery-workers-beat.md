# FR - Worker And Scheduler Rehearsal

[SPEC FRESHNESS: reviewed_at=2026-06-17 next_review=2026-09-17]

## Purpose

Slice 18 rehearses the background workers and scheduler in the cluster. The
workers run on Dell, use bounded memory, and read the same settings as the
backend.

## Current Source Of Truth

- Worker and scheduler manifests: `k8s/app/celery.yaml`.
- Job queue manifest: `k8s/broker/rabbitmq.yaml`.

## Behavior

Given the manifests are applied, when workers start, then general jobs use the
default queue, pipeline jobs use the pipeline and embeddings queues, and the
scheduler runs as a single pod.

## Citations

- Celery documentation - Workers: https://docs.celeryq.dev/en/stable/userguide/workers.html
- Kubernetes documentation - Resource management for Pods and containers: https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/
