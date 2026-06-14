# WiFi-resilience baseline

[SPEC FRESHNESS: reviewed_at=2026-06-14 next_review=2026-09-14]

The standard every later slice honors so a brief WiFi drop is always caught and retried, never
silently used wrong. See `docs/network/ip-plan.md` for the addresses and `docs/specs/fr-k8s-wifi-preflight.md`
for the spec + measured proof.

## Plain English — what runs on what

After the cable was plugged (2026-06-14), the cluster has a **wired backbone** and **WiFi edges**:

- **Wired (Dell↔Mint `10.10.10.0/24`, 1 Gbps):** the heavy, correctness-critical traffic — the
  database, all tests, storage, and the cluster's own control messages. This is the steady, reliable
  path; it does not need WiFi safeguards.
- **WiFi edges (`192.168.0.0/24`):** only the light paths — MSI sending `kubectl` orders to Mint, and
  Dell/Mint reaching the internet (image pulls, cloud embeddings). These are where the safeguards below
  apply, because WiFi can briefly drop.

## The five safeguards (the standard)

1. **Checksum-verify + retry every transfer to a node.** Any file/image push to Dell or Mint is
   verified with a SHA-256 checksum and retried on mismatch, so a broken/incomplete copy is detected and
   redone, never used. (Proven by `tools/preflight/test_drop_resilience.sh`.)
2. **k3s tolerates brief WiFi blips.** The kubelet/controller node-status and node-monitor grace periods
   are set longer than a typical wireless hiccup so a brief drop on the MSI↔Mint WiFi path does not mark
   a node NotReady or evict pods. Cluster-internal node-to-node traffic is wired, so this mainly guards
   the control/API path. (Applied in SLICE-06/10.)
3. **Bazel retries + local cache fallback.** Bazel uses `--remote_timeout` + `--remote_retries`, and
   falls back to Dell's **local SSD disk cache** (`--disk_cache`) if Mint's remote cache is briefly
   unreachable. (Applied in SLICE-24/25.)
4. **Hot I/O stays on Dell's local SSD — never WiFi.** The database and all hot/temporary test scratch
   live on Dell's SSD (a local-path storage class). Only cold, durable data uses Mint's NFS, mounted
   with retry-friendly options (NFSv4.2, `async`, `nconnect`, WiFi-friendly `timeo`/`retrans`).
   (Applied in SLICE-08/09/11.)
5. **Images are pre-pulled to Dell.** A registry mirror on Mint + a pre-pull DaemonSet mean pods start
   from already-present images instead of re-downloading over WiFi at startup. (Applied in SLICE-22.)

## Why this matters

The earlier bridge work proved a large transfer can break mid-flight over WiFi (a 559 MB source push
died with a broken pipe). The wired Dell↔Mint backbone removes WiFi from the heavy path entirely; these
five safeguards make the remaining light WiFi paths self-correcting. A slice that ships a transfer,
build, or mount on a WiFi edge without checksum+retry or a local-cache fallback is incomplete.
