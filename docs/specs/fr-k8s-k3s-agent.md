# FR-K8s-k3s-agent - Dell worker placement and priorities

[SPEC FRESHNESS: reviewed_at=2026-06-16 next_review=2026-09-16]

## Purpose

Record and verify the live Dell k3s worker setup without adding duplicate scheduling manifests.
Dell is the worker node that runs the database, app pods, and all test-capable workloads.

## Current source of truth

- Priority classes: `k8s/scheduling/priorityclasses.yaml`.
- Verification script: `tools/preflight/test_k3s_agent.sh`.
- Reapply script: `tools/preflight/install_k3s_agent.sh`.

The original plan expected `k8s/base/node-config/priorityclasses.yaml`, `labels.yaml`, and
`taints.yaml`. The priority file is not duplicated because `k8s/scheduling/priorityclasses.yaml`
already owns the live priority classes. A Dell taint is intentionally not used in the current
two-node topology because Dell is the only workload node; tainting it away from non-test pods would
break the app.

## Behavior

Given Dell has joined the cluster, When `tools/preflight/test_k3s_agent.sh` runs, Then it checks Dell
is Ready, Dell has `xf.io/role=worker`, `xf.io/can-test=true`, and `xf.io/disk=ssd`, exactly one node
is test-capable, no Dell taint exists in this topology, and the priority classes exist.

## Current live status

Verified from Mint on 2026-06-16:

- Dell is Ready.
- Dell labels are `worker`, `true`, and `ssd`.
- Mint labels are `control-storage`, `false`, and `hdd`.
- `xf-infra`, `xf-app`, `xf-test`, and `xf-obs` priority classes exist.
- Dell has no taints by design for the current two-node topology.

## Citations

- k3s documentation, "Agent CLI", official worker-node join behavior:
  <https://docs.k3s.io/cli/agent>
- Kubernetes documentation, "Assign Pods to Nodes", official node-label and node-selector behavior:
  <https://kubernetes.io/docs/concepts/scheduling-eviction/assign-pod-node/>
- Kubernetes documentation, "Taints and Tolerations", official taint behavior and why it is not used
  for Dell in this two-node topology:
  <https://kubernetes.io/docs/concepts/scheduling-eviction/taint-and-toleration/>
- Kubernetes documentation, "Pod Priority and Preemption", official PriorityClass behavior:
  <https://kubernetes.io/docs/concepts/scheduling-eviction/pod-priority-preemption/>
