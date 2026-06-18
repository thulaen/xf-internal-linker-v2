# FR - Frontend Nginx Rehearsal

[SPEC FRESHNESS: reviewed_at=2026-06-17 next_review=2026-09-17]

## Purpose

Slice 19 rehearses the Angular frontend served by nginx in the cluster. The repo
uses a NodePort for rehearsal instead of adding an ingress controller.

## Current Source Of Truth

- Frontend Deployment, Service, and traffic rule: `k8s/app/frontend.yaml`.

## Behavior

Given the frontend manifest is applied, when a browser reaches the NodePort, then
nginx serves the compiled frontend and forwards API traffic to the backend.

## Citations

- Kubernetes documentation - Service type NodePort: https://kubernetes.io/docs/concepts/services-networking/service/#type-nodeport
- nginx documentation - Reverse proxy: https://docs.nginx.com/nginx/admin-guide/web-server/reverse-proxy/
