# FR - Kubernetes Node Reservations And Image Cleanup

[SPEC FRESHNESS: reviewed=2026-06-17 next_review=2026-09-17]
[SPEC CITED: feature=fr-k8s-kubelet-reservations kind=technical_doc id=https://kubernetes.io/docs/tasks/administer-cluster/reserve-compute-resources/ verified_at=2026-06-17]
[SPEC CITED: feature=fr-k8s-kubelet-reservations kind=technical_doc id=https://kubernetes.io/docs/concepts/scheduling-eviction/node-pressure-eviction/ verified_at=2026-06-17]
[SPEC CITED: feature=fr-k8s-kubelet-reservations kind=technical_doc id=https://kubernetes.io/docs/concepts/architecture/garbage-collection/ verified_at=2026-06-17]
[SPEC CITED: feature=fr-k8s-kubelet-reservations kind=technical_doc id=https://kubernetes.io/docs/concepts/scheduling-eviction/pod-priority-preemption/ verified_at=2026-06-17]

## Goal

Finish KUBE PLAN Slice 10 by reserving node resources on both machines and by
making low-priority test work the default for unnamed pods.

## Requirements

1. Mint keeps `500m` CPU and `1Gi` memory out of normal pod scheduling.
2. Dell keeps `1` CPU and `2Gi` memory out of normal pod scheduling.
3. Both nodes have hard and soft eviction settings for memory and local disk.
4. Mint has image cleanup thresholds of `80` percent high and `60` percent low,
   plus a two-hour minimum image age.
5. Existing priority class names are reused: `xf-infra`, `xf-app`, `xf-obs`,
   and `xf-test`.
6. `xf-test` is the global default priority class and uses
   `preemptionPolicy: Never`, so an unnamed workload is least protected and does
   not push out a running workload.

## Repo Decision

The older plan requested new names `xf-system-critical`, `xf-storage-db`, and
`xf-shard`. Those are not added because the repo already uses `xf-infra`,
`xf-app`, `xf-obs`, and `xf-test` in live manifests. Adding new names would
create duplicate priority meanings and would not update existing workloads.

The source files are:

- `k8s/cluster/mint-k3s-config.yaml`;
- `k8s/cluster/dell-k3s-agent-config.yaml`;
- `k8s/scheduling/priorityclasses.yaml`.

## Behavior Proof

Given the Slice 10 configs are applied, when
`tools/preflight/test_reservations.sh` runs, then it proves:

- local config files parse;
- local config files contain the required reservation and cleanup arguments;
- the live Mint and Dell config files contain the expected arguments;
- both nodes are Ready;
- both nodes have allocatable CPU and memory below capacity;
- priority classes have the expected values, default status, and preemption
  policy.

## Operations

Run `tools/preflight/apply_kubelet_flags.sh` to copy the config files, restart
k3s on Mint, restart the k3s agent on Dell, and apply priority classes. Then run
`tools/preflight/test_reservations.sh`.

## Scope Limits

This spec does not run a deliberate memory-pressure test. It does not change the
external Dell Postgres process. It only changes what Kubernetes is allowed to
schedule on each node.
