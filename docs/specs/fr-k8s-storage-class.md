# FR - Kubernetes Storage Classes, Claims, And Quotas

[SPEC FRESHNESS: reviewed=2026-06-17 next_review=2026-09-17]
[SPEC CITED: feature=fr-k8s-storage-class kind=technical_doc id=https://kubernetes.io/docs/concepts/storage/storage-classes/ verified_at=2026-06-17]
[SPEC CITED: feature=fr-k8s-storage-class kind=technical_doc id=https://kubernetes.io/docs/concepts/policy/resource-quotas/ verified_at=2026-06-17]
[SPEC CITED: feature=fr-k8s-storage-class kind=technical_doc id=https://kubernetes.io/docs/concepts/policy/limit-range/ verified_at=2026-06-17]
[SPEC CITED: feature=fr-k8s-storage-class kind=technical_doc id=https://github.com/kubernetes-sigs/nfs-subdir-external-provisioner verified_at=2026-06-17]

## Goal

Finish KUBE PLAN Slice 9 without duplicating the repo's current storage names.
The repo uses:

- `nfs-cold` for shared Mint NFS storage;
- `ssd-hot` for Dell SSD scratch storage;
- `local-path` for the Mint-hosted registry claim;
- `xf-app` instead of the older plan name `xf-prod`.

## Requirements

1. `nfs-cold` exists and uses provisioner `xf.cluster/nfs-cold`.
2. `ssd-hot` exists and uses provisioner `cluster.local/ssd-hot`.
3. The hot storage class uses `WaitForFirstConsumer`, so test scratch lands on
   Dell only when a pod asks for it.
4. Shared app claims exist for media, static files, model cache, compiled
   artifacts, and sidecar data.
5. The test namespace has one hot scratch claim.
6. App, observability, test, storage, and registry namespaces have both default
   per-object limits and whole-namespace quotas.
7. The exact NFS client mount options remain in
   `k8s/storage/nfs-cold-provisioner.yaml`; docs point there instead of copying
   the values.
8. Cold storage uses `Retain`, so deleting a cold claim releases the volume
   object instead of deleting the stored files.

## Repo Decision

The older plan requested names `xf-cold-nfs` and `xf-hot-ssd`. Those are not
added. Adding them would create duplicate storage classes for the same physical
disks. The implemented names are the existing live names, `nfs-cold` and
`ssd-hot`.

The cold class uses `reclaimPolicy: Retain`. Plain English: when a cold claim is
deleted, Kubernetes must not delete the stored files. The NFS provisioner's
`archiveOnDelete: "true"` remains as a second safety check, but it is not the
main data-loss guard.

StorageClass policy is copied onto each volume when the volume is created, so
changing the class only protects new cold volumes. The installer also patches
already-created `nfs-cold` volumes so live data gets the same `Retain` behavior.

## Behavior Proof

Given the Slice 9 manifests are applied, when
`tools/preflight/test_storage.sh` runs, then it proves:

- both storage classes exist with the expected provisioners and binding modes;
- both storage provisioner Deployments exist;
- quotas and defaults exist for app, observability, test, storage, and registry
  namespaces;
- the test namespace rejects an oversized hot-storage claim before it can land;
- the test namespace injects default pod resource requests;
- shared app NFS claims are bound;
- the test scratch claim uses `ssd-hot` and is either waiting for a first pod or
  already bound;
- existing `nfs-cold` volumes use `Retain`;
- a small write-and-delete marker succeeds on the shared cold claim and the hot
  test scratch claim.

## Operations

Run `tools/preflight/install_storage.sh` to apply storage classes, quotas, and
shared claims. Then run `tools/preflight/test_storage.sh`.

## Scope Limits

This spec does not move existing workload manifests. It does not create a second
storage class name. It does not delete any storage.
