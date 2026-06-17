# FR K8s NFS Server

[SPEC FRESHNESS: reviewed_at=2026-06-16 next_review=2026-09-16]

## Goal

Mint provides one cold-storage Network File System export for data that must be
shared across the two-node cluster. The current live root is `/srv/nfs/cluster`,
and the repo must not create a second persistent export tree under
`/srv/xf/nfs-exports`.

## Current Decision

- Keep the live export root at `/srv/nfs/cluster` because it already contains
  Kubernetes-created persistent-volume data.
- Restrict access to the wired cluster network `10.10.10.0/24`.
- Use one reviewed exports template:
  `tools/preflight/etc-exports.template`.
- Keep client mount options in the Kubernetes StorageClass manifest:
  `k8s/storage/nfs-cold-provisioner.yaml`. The markdown note points there
  instead of repeating the exact values.
- Check the host with `tools/preflight/test_nfs_server.sh`.

## Why This Differs From The Older Slice Text

The KUBE PLAN Slice 8 draft expected `/srv/xf/nfs-exports`. Live cluster storage
was already using `/srv/nfs/cluster`, and that path contains real volume data.
Moving the root without a migration plan would risk data loss and would leave two
storage roots behind. This spec chooses the existing root and removes the repo's
expectation that host prep should create a duplicate export directory.

## Requirements

1. Mint has `nfs-kernel-server` installed.
2. `nfs-server` is active and enabled.
3. `/srv/nfs/cluster` exists.
4. `/srv/nfs/cluster` is exported only to `10.10.10.0/24`.
5. The export includes `rw`, `sync`, `no_subtree_check`, and `no_root_squash`.
6. Mint firewall allows `10.10.10.0/24` to reach `2049/tcp`.
7. The repo has exactly one documented NFS export root for cluster cold storage.

## Sources

- RFC 7530, Network File System Version 4 Protocol:
  <https://datatracker.ietf.org/doc/html/rfc7530>
- Linux `exports(5)` manual:
  <https://man7.org/linux/man-pages/man5/exports.5.html>
- Kubernetes StorageClass documentation:
  <https://kubernetes.io/docs/concepts/storage/storage-classes/>
- NFS subdir external provisioner:
  <https://github.com/kubernetes-sigs/nfs-subdir-external-provisioner>

## Behavior Proof

Given Mint is the storage host, when `tools/preflight/test_nfs_server.sh` runs,
then it proves the NFS package, service state, export root, export options, and
firewall rule.

Given a future installer run is needed, when `tools/preflight/install_nfs_server.sh`
runs, then it writes the reviewed exports template and re-exports the single live
root instead of creating a second storage root.

## Review Notes

- No live data is moved by these repo files.
- The empty `/srv/xf/nfs-exports` folder should be removed only after explicit
  user approval, because deleting host folders is a persistent machine change.
- If later testing proves `async` is needed, update `tools/preflight/etc-exports.template`
  and run the same NFS proof script. Do not add a second exports template.
