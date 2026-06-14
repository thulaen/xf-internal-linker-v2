# FR-K8s-WiFi-Preflight — cluster network foundation (wired backbone + WiFi edges)

[SPEC FRESHNESS: reviewed_at=2026-06-14 next_review=2026-09-14]

## Purpose

Prove the cluster network before any k3s install: every machine reaches every other, the addresses are
fixed, and the resilience safeguards are written down. Originally a "Dell-on-WiFi" preflight; the user
then plugged a direct Dell↔Mint ethernet cable, so the foundation is now a **wired backbone + WiFi
edges** (see `docs/network/ip-plan.md`, `docs/network/wifi-resilience-baseline.md`).

## ADR (Architecture Decision Record)

- **Context:** Dell lives in the bedroom and could not be cabled to the house network; WiFi can drop
  mid-transfer. The user instead ran a direct cable between **Dell and Mint** (Mint has the only spare
  arrangement), giving the two cluster nodes a private wired link and retiring MSI's old cable to Mint.
- **Decision:** Cluster-internal traffic runs over the wired `10.10.10.0/24` link (Mint `.91`, Dell
  `.92`); MSI drives the cluster over WiFi; Dell/Mint use WiFi only for internet. The WiFi edges are
  made reliable in software (the five safeguards). Mint's address, as seen from MSI, is the single env
  var `MINT_OBSERVABILITY_HOST`.
- **Alternatives considered:** (1) Dell on WiFi only — rejected: the heavy path would cross a flaky
  link. (2) Wire Dell to the router — impossible (bedroom). (3) WSL2 on Dell so it stays Windows —
  weak for the wired backbone (the cable lands on Windows, not the Linux that runs k3s); revisited at
  SLICE-02 (current direction: native Ubuntu so k3s binds the wired NIC directly).
- **Consequences:** The cluster's heavy traffic never touches WiFi. MSI↔Mint and node↔internet are
  wireless and rely on the safeguards. Every later slice honors the baseline.

## Measured reachability matrix (2026-06-14)

| From → To | Result | Notes |
|---|---|---|
| **Dell ↔ Mint (wired `10.10.10.92`/`.91`)** | **0% loss, ~1.0–1.5 ms** | 1 Gbps link; Mint→Dell 1.495 ms avg, Dell→Mint <1 ms. The backbone. |
| MSI → Dell (WiFi `192.168.0.163`) | reachable (TCP) | ICMP varies by Dell's Windows firewall profile; TCP/SSH open. |
| MSI → Mint (WiFi `192.168.0.91`) | 0% loss, <1 ms | kubectl + Docker-over-TLS path. |
| MSI → router (`192.168.0.1`) | 0% loss | — |

The wired link throughput (`iperf3`, expect ≈ 1 Gbit) is measured in SLICE-02 once Dell runs Linux and
`iperf3` is available on both ends; the 1 Gbps negotiated link speed + sub-2 ms latency already prove a
healthy gigabit cable.

## Source-backed rules (citations)

- **RFC 792** — ICMP Echo (ping) is the standard reachability probe: https://www.rfc-editor.org/rfc/rfc792
- **RFC 2131** — DHCP and its reservation (static binding) mechanism: https://www.rfc-editor.org/rfc/rfc2131
- **RFC 6234** — SHA-2, the checksum that detects a broken/incomplete transfer so it is retried, never
  silently used: https://www.rfc-editor.org/rfc/rfc6234
- **RFC 7530** — NFSv4 `timeo`/`retrans`/`soft` semantics so a brief WiFi drop on an NFS read retries
  instead of hanging: https://www.rfc-editor.org/rfc/rfc7530
- **Kubernetes — Nodes** — node status, monitor grace, and eviction settings tuned so a brief WiFi blip
  does not evict a node: https://kubernetes.io/docs/concepts/architecture/nodes/
- **iperf3 (ESnet)** — the standard achievable-throughput measurement tool: https://software.es.net/iperf/

## BDD scenarios

- **Scenario 1 — wired backbone is healthy.** Given the Dell↔Mint cable is plugged and both NICs hold
  their `10.10.10.x` static IPs, When `tools/preflight/test_lan_matrix.sh` pings the pair, Then loss is
  0% and round-trip is under 2 ms (a wired link).
- **Scenario 2 — every directed pair is reachable.** Given all three machines are up, When the matrix
  probes each directed pair, Then each is reachable (ICMP where the host firewall allows it, TCP
  otherwise) and the result is recorded.
- **Scenario 3 — a dropped transfer is caught, not silently passed.** Given a payload is sent to Dell
  and the link is interrupted mid-transfer, When `tools/preflight/test_drop_resilience.sh` runs, Then
  the SHA-256 checksum detects the broken copy and the retry produces a correct, checksum-matched file
  (or fails loudly) — never a false pass.
- **Scenario 4 — safeguards baseline exists.** Given the slice is done, When a later slice author opens
  `docs/network/wifi-resilience-baseline.md`, Then it lists the five safeguards as the standard.
- **Scenario 5 — addresses survive a reboot.** Given the static wired IPs and DHCP-reserved WiFi IPs,
  When each machine reboots, Then it returns to the same address.

## Test entry points (implemented in SLICE-02)

The reachability matrix above was captured by hand on 2026-06-14 (commands in the AGENT-HANDOFF entry).
The repeatable scripts land in **SLICE-02**, once Dell runs Linux. Drafting them in this slice surfaced
two things to settle first, both clean on a Linux Dell with stable addressing:

1. **Dell's Windows firewall now drops ICMP** — `ping` to Dell fails even though TCP/SSH works, so
   reachability checks must probe a **TCP port** (e.g. 22), not only `ping`.
2. **From MSI the Mint SSH target must be Mint's WiFi** (`192.168.0.91` / the `mint-wifi` alias) — the
   old cable IP `10.10.10.91` is no longer reachable from MSI now that the cable moved to Dell↔Mint.

- `tools/preflight/test_lan_matrix.sh` — ping/TCP reachability matrix + `iperf3` Dell↔Mint throughput.
- `tools/preflight/test_drop_resilience.sh` — checksum-verified, retried transfer to a cluster node.
- Shared probes extend `tools/preflight/lib.sh`.

## Out of scope

- Installing k3s, Docker, or any cluster software (SLICE-02/05/06).
- Time-sync and name resolution (SLICE-04).
- NFS, Postgres, app pods (later phases) — though those slices MUST honor this baseline.

[SPEC CITED: feature=fr-k8s-wifi-preflight kind=rfc id=https://www.rfc-editor.org/rfc/rfc6234 verified_at=2026-06-14]
