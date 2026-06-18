# FR - MSI Kubernetes Console

[SPEC FRESHNESS: reviewed_at=2026-06-17 next_review=2026-09-17]

## Purpose

Slice 15 makes MSI a control computer only. It keeps `kubectl` and the kubeconfig
file on MSI while Docker stays installed until the final guarded cutover.

## Current Source Of Truth

- Installer: `k8s/console/install-kubectl-msi.ps1`.
- Kubeconfig copier: `k8s/console/place-kubeconfig.ps1`.
- Version lock: `k8s/console/kubectl-version.lock`.
- Verification: `k8s/console/verify-console.ps1`.

## Behavior

Given the k3s server is running on Mint, when `verify-console.ps1` runs on MSI,
then it checks that `kubectl` exists, the kubeconfig exists, and the cluster has
the expected Mint and Dell nodes.

## Citations

- Kubernetes documentation - Install kubectl on Windows: https://kubernetes.io/docs/tasks/tools/install-kubectl-windows/
- Kubernetes documentation - Organizing cluster access using kubeconfig files: https://kubernetes.io/docs/concepts/configuration/organize-cluster-access-kubeconfig/
