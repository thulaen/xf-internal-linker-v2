# NFS Client Mount Option Source

The exact client mount options live in one place:

`k8s/storage/nfs-cold-provisioner.yaml`

Plain English: the Kubernetes StorageClass is the source of truth because it is
the object that actually gives the options to newly created NFS-backed volumes.
This note explains the intent without repeating the values.

- Use modern Network File System support already enabled on Mint.
- Wait and retry if Mint briefly drops, rather than returning a partial write.
- Avoid needless read-time timestamp writes.
- Use parallel network connections and large transfer chunks for throughput.
- Keep retry timing explicit.

Server-side export settings live in `tools/preflight/etc-exports.template`.
Do not create a second export root under `/srv/xf/nfs-exports`; that would split
persistent storage and make later cleanup risky.
