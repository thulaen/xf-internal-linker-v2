# Cluster IP plan (K8s migration)

[SPEC FRESHNESS: reviewed_at=2026-06-14 next_review=2026-09-14]

This is the single reference for which machine has which address, on which link, and why.
Established and proven 2026-06-14 (commit `31e82b82`); see also `docs/network/wifi-resilience-baseline.md`
and `docs/specs/fr-k8s-wifi-preflight.md`.

## Plain English

The cluster is two machines — **Mint** (control plane + storage) and **Dell** (database + all tests).
**MSI** is the remote control (it just runs `kubectl`). There are two separate networks:

- A **private wired cable** between Dell and Mint — the cluster's fast, reliable backbone. All heavy
  cluster traffic (database, tests, storage, the cluster's own control messages) runs here and never
  touches WiFi.
- The **home WiFi/router network** — used only for light things: MSI sending `kubectl` orders to Mint,
  and Dell/Mint reaching the internet (downloading images, cloud embeddings).

## Address table

| Machine | Wired cluster link (`10.10.10.0/24`) | Home WiFi/internet (`192.168.0.0/24`) | Role |
|---|---|---|---|
| **MSI** (Windows) | — (its old `10.10.10.10` cable to Mint is retired; NIC now disconnected) | WiFi `192.168.0.50` | Remote control only (`kubectl`) |
| **Mint** (`minthelper01-Lenovo-C50-30`) | wired `enp2s0 = 10.10.10.91` (static) → to Dell | WiFi `wlp1s0 = 192.168.0.91` (DHCP-reserved) | k3s server + storage + builds |
| **Dell** (OptiPlex Micro 7010) | wired `Ethernet (I219-LM) = 10.10.10.92` (static) → to Mint | WiFi `192.168.0.163` (DHCP-reserved) | k3s worker: database + all tests |
| Router/gateway | — | `192.168.0.1` | — |

Known MACs: Mint `enp2s0 = 98:ee:cb:26:46:c6`, Mint `wlp1s0 = 30:52:cb:97:c8:ab`, Dell WiFi =
`c0-a5-e8-be-d7-5f`. (Capture Dell's `I219-LM` MAC and MSI's MACs when needed for new reservations.)

## Rules every later slice honors

1. **Cluster-internal traffic → the wired link.** k3s API (6443), flannel, kubelet (10250), Postgres
   (5432), and NFS all use `10.10.10.0/24`. **k3s on both nodes must bind its node-IP to the wired NIC**
   (`--node-ip 10.10.10.91` on Mint, `--node-ip 10.10.10.92` on Dell) — set in SLICE-05/06.
2. **MSI reaches Mint over WiFi.** `kubectl` talks to Mint's k3s API at `192.168.0.91:6443`. MSI's old
   wired cable to Mint is gone.
3. **The wired cluster IPs are static** (set per-NIC: Mint `10.10.10.91`, Dell `10.10.10.92`), not
   router-managed. The **WiFi IPs are DHCP-reserved** on the router (the user reserved them 2026-06-14)
   so they survive reboots.
4. **Mint's address, as seen from MSI, is one setting** — the `MINT_OBSERVABILITY_HOST` env var
   (default `192.168.0.91`). Config and code read it instead of hardcoding an IP (commit `31e82b82`).
   Change Mint's address in one place: `MINT_OBSERVABILITY_HOST` in `.env`.
5. **Two NICs per cluster node — reserve/route carefully.** Dell and Mint are each multi-homed (wired
   cluster + WiFi internet). Cluster services bind the wired IP; internet/egress uses WiFi.

## Edge cases / notes

- Dell's WiFi was observed linking at only ~144 Mbit/s (looks like 2.4 GHz). It carries only internet
  traffic now (the cable carries cluster traffic), so this is low-impact; recheck the band if image
  pulls feel slow (`netsh wlan show interfaces` on Dell while it is still Windows).
- Mint reaches the home network over **WiFi** (`wlp1s0`), not a cable — so MSI↔Mint is wireless. That
  path is light (kubectl + reports) and covered by the WiFi-resilience safeguards.
- Dell now runs Ubuntu 26.04 (SLICE-02 done); it is the k3s worker with wired IP `10.10.10.92`. The
  Windows-era firewall rule `XF-Cluster-LAN` (allow `10.10.10.0/24`) is superseded by Ubuntu's setup.
- Cross-node name resolution + clock-sync are recorded in `docs/network/time-and-name-resolution.md`
  (SLICE-04): both nodes resolve each other by name over the wired link, both clocks are NTP-synced.
