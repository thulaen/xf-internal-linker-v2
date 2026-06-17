# FR K8s Network And RBAC

[SPEC FRESHNESS: reviewed_at=2026-06-17 next_review=2026-09-17]

## Goal

Slice 7 gives the test namespace its own Kubernetes permissions and pod traffic
rules. Kubernetes permissions are the rules that decide what an in-cluster pod
identity may do. Pod traffic rules decide what network connections pods may open.

## Current Decision

- Keep flannel on VXLAN. VXLAN is the current pod-network mode recorded in
  `docs/network/ip-plan.md`. The older KUBE PLAN text asked for `host-gw`, but
  the repo now rejects that live network restart until there is console access
  or measured need.
- Add `xf-test` namespace permissions in `k8s/network/xf-test-rbac.yaml`.
- Add `xf-test` default-deny pod traffic rules in `k8s/network/xf-test-netpol.yaml`.
- Prove the live state with `tools/preflight/test_net_rbac.sh`.

## Requirements

1. `xf-coordinator` can create and delete Jobs.
2. `xf-coordinator` can create ConfigMaps.
3. `xf-shard-runner` has no Kubernetes API permissions.
4. `xf-merge` can read Jobs but cannot delete them.
5. `xf-test` has default-deny inbound and outbound pod traffic.
6. `xf-test` allows DNS egress for name lookup.
7. Shard pods may reach Dell Postgres on `10.10.10.92:5432` and Mint NFS on
   `10.10.10.91:2049`.
8. Build-cache egress is not added until the BuildBuddy/cache service exists in
   Slice 25, so this slice does not invent a port.

## Sources

- Kubernetes RBAC documentation:
  <https://kubernetes.io/docs/reference/access-authn-authz/rbac/>
- Kubernetes NetworkPolicy documentation:
  <https://kubernetes.io/docs/concepts/services-networking/network-policies/>
- Flannel backend documentation:
  <https://github.com/flannel-io/flannel/blob/master/Documentation/backends.md>

## Behavior Proof

Given the Slice 7 manifests are applied, when `tools/preflight/test_net_rbac.sh`
runs, then it checks the intended Kubernetes permission answers and confirms the
three `xf-test` network policies exist.
