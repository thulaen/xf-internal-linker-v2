# FR-K8s-k3s-server - Mint lightweight cluster control plane

[SPEC FRESHNESS: reviewed_at=2026-06-16 next_review=2026-09-16]

## Purpose

Record and verify the live Mint k3s server setup without duplicating the repo's existing k3s
configuration. k3s means the small Kubernetes service this project uses for the two-machine cluster.

## Current source of truth

- Live host file: `/etc/rancher/k3s/config.yaml` on Mint.
- Repo copy: `k8s/cluster/mint-k3s-config.yaml`.
- Verification script: `tools/preflight/test_k3s_server.sh`.
- MSI check: `tools/preflight/test_k3s_from_msi.ps1`.

The original plan expected `k8s/base/node-config/kubelet-flags-mint.env`. That file is not created
because it would duplicate `k8s/cluster/mint-k3s-config.yaml`, which is already the repo-owned copy
of the live Mint k3s config.

## Behavior

Given Mint is the k3s server, When `tools/preflight/test_k3s_server.sh` runs, Then it checks that k3s
is active, Traefik and ServiceLB are disabled, SQLite state exists, etcd is absent, Mint is Ready, and
allocatable memory is lower than capacity.

Given MSI has a working kubeconfig, When `tools/preflight/test_k3s_from_msi.ps1` runs, Then Windows
`kubectl` reads the cluster and sees at least one Ready node.

## Current live status

Verified from Mint on 2026-06-16:

- k3s service is active.
- `/var/lib/rancher/k3s/server/db/state.db` exists.
- `/var/lib/rancher/k3s/server/db/etcd` is absent.
- Mint and Dell both report Ready from Mint-side `kubectl`.

The MSI-side `kubectl` check requires Mint's firewall to allow MSI's reserved IP
`192.168.0.50/32` to `6443/tcp`, because MSI reaches the control plane over the home network,
not the private Dell-to-Mint cable. The API is not opened to the whole home subnet.

## Citations

- k3s documentation, "Configuration with install script", official server flag behavior:
  <https://docs.k3s.io/installation/configuration>
- k3s documentation, "Server CLI", official `--disable`, `--tls-san`, and `--node-ip` flags:
  <https://docs.k3s.io/cli/server>
- Kubernetes documentation, "Reserve Compute Resources for System Daemons", official reserved-resource
  behavior: <https://kubernetes.io/docs/tasks/administer-cluster/reserve-compute-resources/>
- Ongaro and Ousterhout 2014, "In Search of an Understandable Consensus Algorithm", Raft paper:
  <https://raft.github.io/raft.pdf>
