# GO-LIVE-ONLY: the `wait-for-history` initContainer

SLICE-21 observability migration — go-live history copy, part 3 of 3.

## What this is, in plain English

When we move monitoring into the cluster **for real** (go-live), we first copy
the old history off the Windows machine and unpack it into each tool's cluster
disk:

1. `scripts/obs-history-copy.ps1` packs each Docker volume into a fingerprinted
   tarball and stages it on the Mint NFS folder.
2. `k8s/obs/history-copy/restore-job.yaml` re-checks the fingerprint inside the
   cluster, unpacks it into the tool's disk, and writes a small marker file
   `.copy-complete` at the root of that disk.

This document is the **third** piece: a tiny "wait" step (a Kubernetes
*initContainer* — a helper container that must finish before the real tool
container starts) that you add to each stateful monitoring tool **at go-live
only**. It makes the tool **refuse to start serving until the history is in
place**. Without it, a tool could boot on an empty disk and start writing fresh
data *before* the restore Job finished — which would mix new data into a
half-restored disk, or make the tool think it has no history.

## Why the rehearsal manifests deliberately leave this OUT

The rehearsal is meant to prove the manifests boot correctly on **empty**
storage, fast, with nothing to restore. So the rehearsal manifests in
`k8s/obs/` **intentionally omit** this initContainer — rehearsal pods should
start instantly on empty disks.

This `wait-for-history` step is **patched in only at go-live**, *after* the
restore Job for that tool has finished and written its `.copy-complete` marker.

## The marker path per tool

The initContainer waits for `.copy-complete` at the **root of the same disk the
tool mounts** (the restore Job writes the marker there). So the path the
initContainer checks is the tool's own mount path plus `/.copy-complete`:

| Tool      | PVC              | Tool mount path     | Marker the init waits for      |
|-----------|------------------|---------------------|--------------------------------|
| vmsingle  | `vmsingle-data`  | `/storage`          | `/storage/.copy-complete`      |
| loki      | `loki-data`      | `/loki`             | `/loki/.copy-complete`         |
| tempo     | `tempo-data`     | `/var/tempo`        | `/var/tempo/.copy-complete`    |
| grafana   | `grafana-data`   | `/var/lib/grafana`  | `/var/lib/grafana/.copy-complete` |
| pyroscope | `pyroscope-data` | `/data`             | `/data/.copy-complete`         |

> alloy is **not** in this table — it uses `emptyDir` in the cluster and its
> data is reconstructable, so there is nothing to wait for. GlitchTip is also
> **not** here — it has no file disk; its history rides the SLICE-13 Postgres
> dump/restore, not a volume copy.

## The snippet to add (go-live only)

At go-live, add an `initContainers:` block to the tool's Deployment pod spec.
It mounts the **same** PVC the tool already mounts (so it can see the marker),
and busy-waits until `.copy-complete` exists. Keep it bounded so a stuck restore
fails loudly instead of hanging forever.

The example below is for **vmsingle** (mount `/storage`). For every other tool,
change only:

- the `volumeMounts.mountPath` and the path inside the loop to the tool's mount
  path (`/loki`, `/var/tempo`, `/var/lib/grafana`, `/data`), and
- the `volumeMounts.name` to whatever the tool's storage volume is named in its
  own manifest (in the current manifests it is `storage` for vmsingle, loki,
  tempo, pyroscope, and `data` for grafana).

```yaml
# Add this UNDER spec.template.spec, as a sibling of `containers:`.
# GO-LIVE ONLY — do NOT add this to the rehearsal manifests.
      initContainers:
        - name: wait-for-history
          image: alpine:3.20
          imagePullPolicy: IfNotPresent
          # Refuse to start the tool until the restore Job's marker exists.
          # Bounded wait (~10 min) so a failed/forgotten restore fails loudly
          # instead of hanging the pod forever.
          command: ["sh", "-eu", "-c"]
          args:
            - |
              MARKER="/storage/.copy-complete"   # <-- tool mount path + /.copy-complete
              echo "waiting for monitoring-history restore marker: $MARKER"
              i=0
              while [ ! -f "$MARKER" ]; do
                i=$((i + 1))
                if [ "$i" -gt 120 ]; then
                  echo "FAIL: $MARKER not found after ~10 minutes." >&2
                  echo "      Did the obs-history-restore Job for this volume run and finish?" >&2
                  exit 1
                fi
                sleep 5
              done
              echo "history marker present — letting the tool start:"
              cat "$MARKER"
          volumeMounts:
            - name: storage            # <-- the tool's storage volume name
              mountPath: /storage      # <-- the tool's mount path
```

### Grafana note

Grafana's storage volume is named `data` (not `storage`) and mounts at
`/var/lib/grafana`, so its snippet uses:

```yaml
              MARKER="/var/lib/grafana/.copy-complete"
          volumeMounts:
            - name: data
              mountPath: /var/lib/grafana
```

## Go-live order (so the pieces line up)

1. Stop the live app writing to the old Windows volumes.
2. Run `scripts/obs-history-copy.ps1` on the Windows (MSI) host — stages + verifies.
3. Apply `k8s/obs/history-copy/restore-job.yaml` once per volume — extracts +
   writes each `.copy-complete` marker.
4. Patch this `wait-for-history` initContainer into each tool's Deployment, then
   roll the tools. They now start only after their history is in place.

Steps 2–4 are **go-live only**. None of them run during a rehearsal.
