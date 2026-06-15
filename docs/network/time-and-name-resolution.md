# Cluster time-sync + cross-node name resolution (SLICE-04)

[SPEC FRESHNESS: reviewed_at=2026-06-15 next_review=2026-09-15]

Establishes two host-level facts every later slice relies on: the cluster machines'
clocks agree with real time, and each machine can find the other by name (not just by
number) over the private wired cable. See `docs/network/ip-plan.md` for the addresses.

## Plain English

Two small things keep a multi-machine cluster honest:

1. **The clocks must agree.** If Mint and Dell disagree on the time, security tokens,
   TLS certificates, log timelines, and scheduled jobs all misbehave. Both machines run
   `chrony` (a service that keeps the clock matched to internet time). Both already report
   "synchronized" and sit **well under a thousandth of a second** off true time — so the
   clocks agree. Nothing was changed here; the operating-system default already does it.
2. **Each machine must find the other by name.** Cluster code is easier to read and debug
   when you can say "mint" or "dell" instead of memorising `10.10.10.91` / `10.10.10.92`.
   We added one line to each machine's address book (`/etc/hosts`) mapping the other
   machine's **wired** address to its name. They now resolve each other over the cable.

## What is configured

### Clock sync (already satisfied by the OS)

Both nodes run `chrony`, `systemd` reports `NTPSynchronized=yes`, and each is sub-millisecond
from true time (Mint via HEAnet `ntp1-cwt.heanet.ie`, Dell via Canonical `ntp-nts-2.ps5`).
They sync **independently to internet time servers** rather than peering with each other —
this is deliberate: each clock tracks true UTC directly, so there is no single machine whose
failure desynchronises the cluster. We did **not** alter the working time-sync.

### Name resolution (added 2026-06-15)

One guarded line per machine, over the wired backbone (`10.10.10.0/24`):

- On **Dell** `/etc/hosts`: `10.10.10.91 minthelper01-Lenovo-C50-30 minthelper01-lenovo-c50-30 mint`
- On **Mint** `/etc/hosts`: `10.10.10.92 dell-ubuntu-01-OptiPlex-Micro-7010 dell-ubuntu-01-optiplex-micro-7010 dell`

Each line carries the full hostname, the lowercase Kubernetes node name (so it matches
`kubectl get nodes`), and a short alias. The entries are guarded by a
`# xf-cluster SLICE-04` marker comment so re-applying them cannot create duplicates.
Both point at the **wired** IP, so name-based traffic uses the cable, not WiFi.

## Verification

`tools/preflight/test_cluster_time_and_names.sh` re-proves all of this from MSI. It logs in
to both machines (read-only) and checks: each clock is NTP-synchronised and within tolerance;
Dell resolves the Mint node name to `10.10.10.91`; Mint resolves the Dell node name to
`10.10.10.92`; and each reaches a real cluster port on the other **by name** (Dell → Mint
k3s API `:6443`, Mint → Dell Postgres `:5432`).

Run it with git-bash (the script refuses to run under WSL, whose `ssh` cannot see the Windows
host aliases and would silently return nothing):

```bash
/bin/bash tools/preflight/test_cluster_time_and_names.sh
```

Result 2026-06-15: all six checks PASS (Mint offset 9.7e-05 s, Dell offset 8.3e-05 s).

## Citations

- Clock synchronisation protocol: D. Mills et al., **RFC 5905 — Network Time Protocol Version 4**
  (2010), <https://www.rfc-editor.org/rfc/rfc5905>. `chrony` is an NTPv4 implementation:
  <https://chrony-project.org/documentation.html>.
- Static name→address mapping precedes DNS via the hosts file, specified by POSIX
  (`/etc/hosts`, gethostbyname resolution order via `nsswitch.conf`):
  <https://man7.org/linux/man-pages/man5/hosts.5.html>.
- Kubernetes requires node clocks to be synchronised (certificate validity, token expiry,
  lease/heartbeat timing): <https://kubernetes.io/docs/setup/best-practices/certificates/>.
