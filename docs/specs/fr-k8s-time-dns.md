# FR - Kubernetes Time And Name Checks

[SPEC FRESHNESS: reviewed_at=2026-06-17 next_review=2026-09-17]

## Purpose

Slice 4 proves the two cluster nodes agree on time and can resolve the stable
names used by later scripts. It uses the existing proof script instead of adding
duplicate host files.

## Current Source Of Truth

- Human-readable network names: `docs/network/time-and-name-resolution.md`.
- Repeatable proof: `tools/preflight/test_cluster_time_and_names.sh`.
- Shared node defaults: `tools/preflight/cluster_lib.sh`.

## Behavior

Given Mint and Dell are online, when the proof script runs from Git Bash, then
both nodes report close clock time, the expected node names resolve, and the
script exits non-zero if either host is missing.

## Rehearsal Boundary

This slice only checks time and names. It does not install k3s, change router
settings, or write machine network files.

## Citations

- RFC 5905 - Network Time Protocol Version 4: https://www.rfc-editor.org/rfc/rfc5905
- Kubernetes documentation - DNS for Services and Pods: https://kubernetes.io/docs/concepts/services-networking/dns-pod-service/
