# FR — Observability Migration into the k3s Cluster (SLICE-21)

[SPEC FRESHNESS: reviewed_at=2026-06-15 next_review=2026-09-15]

> **Status:** implemented (manifests applied + proven live on the rehearsal cluster). The one-time
> history copy and the retirement of the old Windows volumes are deferred to the final go-live
> (alongside SLICE-13). See "Out of scope / deferred" at the bottom.
>
> **Plain English first.** "Observability" is the set of tools that watch the app and tell you how it
> is doing: numbers over time (metrics), text log lines (logs), the step-by-step path of one request
> (traces), which functions burn the CPU (profiles), crash reports (error tracking), and the website
> where you look at all of it (dashboards). This document records how those tools were moved off the
> Windows Docker-compose stack and into the Kubernetes cluster, and the three big choices made along
> the way.

## Glossary (terms used below, in plain English)

- **k3s / cluster** — a small Kubernetes setup running on two machines (the Dell worker and the Mint
  helper). Kubernetes is the system that starts, restarts, and connects containers for you.
- **Namespace** — a walled-off section of the cluster. `xf-app` holds the real app; `xf-obs` holds
  the monitoring tools. Separate namespaces get separate firewall rules, separate safety caps, and
  separate identities.
- **Workload** — one running thing in the cluster (a long-running service is a *Deployment*; one that
  runs all the time, one copy per machine, is a *DaemonSet*; a one-shot setup task is a *Job*).
- **PVC (PersistentVolumeClaim)** — a request for a chunk of disk that survives a pod restart.
- **Service** — a stable in-cluster name + address for a workload (so tools find each other by name,
  not by a changing pod IP).
- **NetworkPolicy** — a firewall rule that says which pods may open a connection to which other pods.
- **NodePort** — a way to reach an in-cluster service from your own machines, on a fixed high port.
- **VictoriaMetrics (vmsingle / vmagent / vmalert)** — the metrics store, the scraper that fills it,
  and the rule-checker that watches the numbers for trouble.
- **Tempo** — the trace store. **Loki** — the log store. **Pyroscope** — the profile store.
- **OpenTelemetry Collector (otel-collector)** — the hub that receives traces/metrics/profiles from
  the app and forwards each to the right store.
- **Alloy** — the log shipper: it collects every pod's log lines and sends them to Loki.
- **Grafana** — the dashboards website. **GlitchTip** — the error-tracking website.
- **OTLP** — the standard wire format OpenTelemetry uses (ports 4317 for gRPC, 4318 for HTTP).
- **Faro** — the browser side of telemetry: the user's browser reports front-end errors to Alloy.
- **ssd-hot / nfs-cold** — the two storage tiers. `ssd-hot` is the fast SSD on Dell; `nfs-cold` is the
  shared network drive on Mint.

## Sources of truth (citations)

Every external behaviour relied on below is anchored to a primary source.

| Source | Why it is used here |
|---|---|
| Grafana — Provisioning: https://grafana.com/docs/grafana/latest/administration/provisioning/ | Grafana's data sources and dashboards are defined as files (provisioned from ConfigMaps), so they reappear automatically after a restart. |
| Grafana Loki — Storage / retention: https://grafana.com/docs/loki/latest/operations/storage/ | Loki's on-disk layout and retention behaviour for the log store. |
| Grafana Tempo — Configuration: https://grafana.com/docs/tempo/latest/configuration/ | Tempo's OTLP receiver + local storage + block-retention settings. |
| Grafana Alloy — `loki.source.kubernetes` / `discovery.kubernetes`: https://grafana.com/docs/alloy/latest/ | The Kubernetes log-discovery + log-tailing components that replace the old Docker-socket discovery. |
| OpenTelemetry Collector — Configuration: https://opentelemetry.io/docs/collector/configuration/ | Receivers, processors, exporters, and pipelines used in the collector config. |
| Kubernetes — Jobs: https://kubernetes.io/docs/concepts/workloads/controllers/job/ | The one-shot GlitchTip init + migrate Jobs, including `backoffLimit` and `ttlSecondsAfterFinished`. |
| Kubernetes — Assign Pods to Nodes (nodeSelector): https://kubernetes.io/docs/concepts/scheduling-eviction/assign-pod-node/ | Pinning pods to the Dell worker or the Mint helper by hostname. |
| Kubernetes — Services without selectors (external Endpoints): https://kubernetes.io/docs/concepts/services-networking/service/#services-without-selectors | The selectorless `postgres` Service in `xf-obs` that points at the Dell host outside the cluster. |
| Kubernetes — Network Policies: https://kubernetes.io/docs/concepts/services-networking/network-policies/ | The default-deny + additive-allow firewall model used both ways across namespaces. |
| VictoriaMetrics — single-server: https://docs.victoriametrics.com/ | The single-node metrics store, scraper, and alert evaluator. |
| GlitchTip — documentation: https://glitchtip.com/documentation | GlitchTip's database/redis/secret env-var contract and migration script. |

## Problem

The monitoring tools (metrics, logs, traces, profiles, error tracking, dashboards) all ran on the
Windows Docker-compose stack on the MSI machine, with Pyroscope (and the Mint copy of the log
shipper) on the Mint helper. The Kubernetes migration moves the whole system onto the two-node k3s
cluster. The monitoring tier has to move too — into its own namespace, `xf-obs` — under three hard
constraints:

1. **No lost history at go-live.** The accumulated metrics, logs, traces, profiles, and error reports
   on the old stack must survive the cutover.
2. **No disturbance to the live monitoring now.** The Windows stack keeps watching the still-live app
   during the rehearsal, so nothing about it may be stopped, blanked, or repointed while SLICE-21 is
   staged.
3. **GlitchTip stays protected.** Error tracking is ABSOLUTE-protected in `CLAUDE.md` — it must never
   be disabled, and the Docker-compose definition of it must not be edited.

## Decision (three locked-in choices)

**1. Rehearse now on fresh, empty storage; copy the old history at the final go-live.**
SLICE-21 stands up the full monitoring tier in the cluster on brand-new, empty disks and proves it
works end to end. Copying the live history *now* would only capture a stale snapshot, because the old
stack keeps recording for as long as the app still runs on MSI. So the one-time history copy is bound
to the same deliberate cutover as the live-database move (SLICE-13). Rehearse first, copy once, at the
end.

**2. Include VictoriaMetrics (vmsingle / vmagent / vmalert).** The original slice plan predates the
local VictoriaMetrics deployment. VictoriaMetrics is now the metrics store and is Grafana's default
metrics data source, so the migration carries it across as a first-class part of the tier rather than
leaving metrics behind.

**3. Drop SonarQube.** SonarQube was removed from the project on 2026-06-09, so it is not part of the
monitoring tier and is not migrated. (Older notes that mention "Sonar→Dell" describe the pre-removal
world and are superseded.)

## What was built

All manifests live under `k8s/obs/` (workloads + their config) and `k8s/network/` (the one
cross-namespace rule that lives on the app side). The tier is fourteen distinct workloads in the
`xf-obs` namespace; because the log shipper runs as a DaemonSet with one copy per node (Dell + Mint),
there are fifteen running pods in steady state — which is why the namespace caps are sized for "15
monitoring workloads."

### The workloads (file → plain-English purpose)

| File | Workload (kind) | What it does |
|---|---|---|
| `10-vmsingle.yaml` | `vmsingle` (Deployment) | The metrics store. Everything that produces numbers writes here; Grafana and the alert checker read from here. 30-day retention. |
| `11-postgres-exporter.yaml` | `postgres-exporter` (Deployment) | Reads database health numbers (connections, locks, table sizes) and publishes them on port 9187 to be scraped. |
| `12-vmagent.yaml` | `vmagent` (Deployment) | Visits each tool's metrics page every 15 seconds and writes what it finds into `vmsingle`. Scrapes 10 targets. |
| `13-vmalert.yaml` | `vmalert` (Deployment) | Runs the alert rules against the metrics every 30 seconds. No pager — `-notifier.blackhole=true`; alerts become AutoIssues separately. |
| `20-tempo.yaml` | `tempo` (Deployment) | The trace store. Holds the step-by-step path of each request so Grafana can show the whole journey by trace ID. |
| `21-loki.yaml` | `loki` (Deployment) | The log store. Holds every pod's log lines. |
| `22-otel-collector.yaml` | `otel-collector` (Deployment) | The hub. Receives traces/metrics/profiles from the app and fans them out: traces to GlitchTip **and** Tempo, profiles to Pyroscope, metrics exposed for scraping on :8889. |
| `23-alloy.yaml` | `alloy` (DaemonSet) | The log shipper. One copy per machine; each tails only its own node's pod logs and sends them to Loki. Also hosts the Faro browser-error receiver (port 12347). |
| `30-grafana.yaml` | `grafana` (Deployment) | The dashboards website. Data sources + dashboards are provisioned from files; reachable on NodePort 30030. |
| `40-pyroscope.yaml` | `pyroscope` (Deployment) | The profile store (which functions are hot). Pinned to the Mint helper. |
| `50-glitchtip-init-job.yaml` | `glitchtip-init` (Job) | One-shot: creates the `glitchtip` database if it does not already exist (safe to re-run). |
| `51-glitchtip-migrate-job.yaml` | `glitchtip-migrate` (Job) | One-shot: runs GlitchTip's shipped migration script to set up its tables. Waits for the database first. |
| `52-glitchtip.yaml` | `glitchtip` (Deployment) | The error-tracking website + API. The app reports crashes here; reachable on NodePort 30137. |
| `53-glitchtip-worker.yaml` | `glitchtip-worker` (Deployment) | GlitchTip's background worker (Celery + scheduler) that processes incoming error events. |

Supporting config (ConfigMaps, applied with the workloads): `cm-grafana-dashboards.yaml`
(12 dashboards — `xf-app-health`, `xf-import`, `xf-indexing`, `xf-embeddings`, `xf-scoring`,
`xf-suggestions`, `xf-cleaning`, `xf-crawlers`, `xf-review`, `xf-sentence-split`, `traces-overview`,
`xf-system-health`), `cm-loki-config.yaml`, `cm-pyroscope-config.yaml`, and `cm-vmalert-rules.yaml`.
Where a tool's config was unchanged from Docker-compose, it was carried over verbatim; where it
referenced a Docker hostname or a LAN-IP indirection (the old `MINT_OBSERVABILITY_HOST` trick), the
reference was replaced with a cluster Service name (kube-DNS) or a node pin.

### Namespace governance (`00`–`05`)

- **`00-namespace.yaml`** — creates the `xf-obs` namespace. Kubernetes auto-labels it
  `kubernetes.io/metadata.name: xf-obs`, which the cross-namespace firewall rules match on.
- **`01-rbac.yaml`** — the namespace's default identity has its control-plane token turned **off**
  (`automountServiceAccountToken: false`), the same defence-in-depth posture as the app namespace.
  The one exception is Alloy, which genuinely needs to ask the Kubernetes API "which pods run on my
  machine?"; it gets its own ServiceAccount with a **read-only** ClusterRole over pods, pod logs,
  nodes, and namespaces — nothing else, no write, no exec.
- **`02-resource-limits.yaml`** — a `LimitRange` (sensible per-container defaults + a 2Gi memory and
  50Gi disk ceiling per item) and a `ResourceQuota` (a whole-namespace ceiling: 8 CPU / 6Gi requested
  memory / 120Gi total disk, with per-tier disk caps of 55Gi on `ssd-hot` and 60Gi on `nfs-cold`).
  These are runaway-prevention ceilings, not tight packing.
- **`05-priorityclass.yaml`** — a dedicated `xf-obs` PriorityClass at value **5000**, which sits
  **below** the app (`xf-app` = 10000) and **above** throwaway test jobs (`xf-test` = 100). Meaning:
  under memory pressure on Dell, test jobs are evicted first, then monitoring, and the app is
  protected. `preemptionPolicy: Never` means a monitoring pod never shoves a running pod aside to get
  scheduled.

### Network policies (`03-netpol.yaml` + `k8s/network/xf-app-allow-obs-ingress.yaml`)

Default-deny-ingress on `xf-obs`, then exactly the needed allows (NetworkPolicies are additive
allow-lists, so each rule only widens, never narrows):

- **Inside `xf-obs`** — monitoring pods may talk to each other; the wired cluster backbone
  (`10.10.10.0/24`) may reach in (node health probes + NodePort access from your machines); the app
  namespace may push telemetry on ports **4317/4318** (OTLP to the collector) and **12347** (Faro
  browser events to Alloy); and the two dashboards (Grafana 3000, GlitchTip 8000) accept NodePort
  traffic from anywhere.
- **On the `xf-app` side** (`xf-app-allow-obs-ingress.yaml`, kept in its own file so SLICE-21 does not
  edit the app's baseline policy) — the monitoring namespace may reach **two** app ports: the
  backend's `/metrics/` on **8000** (for `vmagent`) and the cache (Valkey/redis) on **6379** (for
  GlitchTip, which uses redis database 4).

## Storage placement

Each store sits on the tier that matches how it is written, and pods are pinned so the data and the
process stay close.

| Workload | Disk | Tier | Why |
|---|---|---|---|
| `vmsingle` | 30Gi | `ssd-hot` (Dell) | Metrics are written continuously and must be fast. |
| `tempo` | 15Gi | `ssd-hot` (Dell) | Traces are bursty and write-heavy. |
| `grafana` | 2Gi | `ssd-hot` (Dell) | Grafana's small SQLite database needs reliable file locking; SQLite over NFS is known to misbehave, so it is deliberately **not** on the NFS share. |
| `loki` | 20Gi | `nfs-cold` (Mint) | Logs are large but written at a moderate rate; durability matters more than raw speed. |
| `pyroscope` | 15Gi | `nfs-cold` (Mint) | Profiles live with Pyroscope on Mint, so the pod and its data are co-located (no cross-node I/O). |
| `alloy` | `emptyDir` (no PVC) | — | Alloy keeps only short-lived positions/buffers; nothing to persist. |

**Node pins:** Pyroscope and the Mint copy of the Alloy DaemonSet run on the **Mint** helper
(`minthelper01-lenovo-c50-30`); everything else runs on **Dell**
(`dell-ubuntu-01-optiplex-micro-7010`). Alloy, being a DaemonSet, also runs a copy on Mint via
control-plane tolerations so Mint's own pod logs are collected.

## Cross-namespace wiring

The app and the monitoring tier live in different namespaces, so every connection between them is
explicit:

- **App → collector.** The app (in `xf-app`) sends OpenTelemetry to the `otel-collector` in `xf-obs`.
  Allowed by the `allow-xf-app-telemetry` ingress rule on `xf-obs` ports **4317/4318** (and **12347**
  for Faro browser errors to Alloy).
- **Monitoring → app.** `vmagent` scrapes the backend's `/metrics/` on **8000**, and GlitchTip uses
  the cache on **6379** (redis database 4). Both are allowed by `allow-obs-ingress` on the `xf-app`
  side.
- **Monitoring → database.** The database lives directly on the Dell host, outside Kubernetes. The
  `xf-obs` namespace gets its **own** selectorless `postgres` Service whose manual Endpoints point at
  Dell over the private cable (`10.10.10.92:5432`). `postgres-exporter` and GlitchTip reach the
  database through that name, independent of the app namespace's copy. (No port-5432 rule is needed on
  the app side, because the database is not an app pod.)
- **Secrets are namespace-scoped.** A Kubernetes Secret only exists inside one namespace, so the
  `postgres-credentials` Secret is synced into `xf-obs` for the database-using tools. GlitchTip also
  reads a `glitchtip-secrets` Secret (its `SECRET_KEY`) and the collector reads a `glitchtip-dsn`
  Secret (the error-reporting address); Grafana reads a `grafana-admin` Secret (admin login). These
  Secrets are created on the cluster, not committed in plaintext.

## The hardest translation (Alloy)

On the Windows stack, Alloy found containers through the Docker socket. **k3s has no Docker socket**
(it uses containerd, and there is no host socket to mount). The fix: Alloy became a **DaemonSet** (one
copy per machine) that asks the Kubernetes API instead. Its config uses `discovery.kubernetes` with a
field selector on `spec.nodeName == $NODE_NAME` (the node name comes from the downward API), so each
copy only handles its own node's pods; `discovery.relabel` maps Kubernetes metadata into readable Loki
labels (namespace, pod, container, service, node); and `loki.source.kubernetes` streams each pod's
logs via the API to Loki. The **Faro** browser-RUM receiver (port 12347) is kept unchanged, so
front-end errors from the user's browser still flow in.

## GlitchTip (ABSOLUTE-protected)

GlitchTip is protected by an ABSOLUTE rule in `CLAUDE.md` — never disable it, never blank its
connection settings. The migration honours that in Kubernetes terms:

- **Four workloads, all present:** the `glitchtip-init` Job (idempotent CREATE-DATABASE — checks
  `WHERE datname='glitchtip'` first), the `glitchtip-migrate` Job (runs `./bin/run-migrate.sh` behind
  a wait-for-db init container that enforces the init → migrate order, since Jobs cannot "wait for the
  other Job"), the `glitchtip` web Deployment, and the `glitchtip-worker` Deployment.
- **Connection settings never blanked:** `DATABASE_URL` and `REDIS_URL` carry non-empty literals;
  `SECRET_KEY` is sourced from a Secret, never an empty value.
- **The collector keeps GlitchTip first:** in the otel-collector traces pipeline, the `sentry`
  (GlitchTip) exporter is listed **first**, ahead of Tempo, so errors always reach GlitchTip.
- **`docker-compose.yml` is NOT edited.** The migration adds Kubernetes manifests only, so the
  existing compose-integrity guard (`apps.audit.tests_glitchtip_compose_integrity`) stays green.
- **A new cluster guard:** `backend/apps/audit/tests_glitchtip_k8s_integrity.py` is the cluster twin
  of the compose guard. It is a plain `SimpleTestCase` (no Kubernetes, no database — it reads the YAML
  files) that fails if any of these regress: all four GlitchTip workloads present; init creates the DB
  idempotently; migrate runs the shipped script behind a wait-for-db init container; connection env is
  never blanked and `SECRET_KEY` comes from a Secret; the collector keeps `sentry` first in the traces
  pipeline + enables the profiles feature gate + exports profiles to Pyroscope; Pyroscope stays pinned
  to Mint; and the cross-namespace telemetry/cache/metrics ports (4317/4318, 6379/8000) are not
  severed.

## History copy (designed for go-live)

The one-time history copy is **designed and described here**, to be executed at the final go-live
(with SLICE-13), not during the rehearsal — copying live data now would only produce a stale snapshot
(see Decision #1). The mechanism mirrors the proven WiFi-resilience baseline
(`docs/network/wifi-resilience-baseline.md`): a copy script (`scripts/obs-history-copy.ps1`) streams
each old volume's contents to the matching cluster PVC, and a restore Job
(`k8s/obs/history-copy/restore-job.yaml`) lands the data inside the cluster; a **wait-for-marker**
initContainer holds each store's pod until its restore has finished, so a store never starts on
half-copied data. Every transfer is **checksum-verified (SHA-256) and retried**, because the copy may
cross WiFi — a broken or incomplete transfer is detected and re-sent, never silently used.

> Status note: these history-copy artifacts (`scripts/obs-history-copy.ps1`,
> `k8s/obs/history-copy/restore-job.yaml`, `k8s/obs/history-copy/_initcontainer-snippet.md`) are
> **authored now** but are intentionally **not run** during the SLICE-21 rehearsal — they live in the
> `history-copy/` subfolder so the rehearsal's `kubectl apply -f k8s/obs/` (non-recursive) never picks
> them up. They execute once, at the final go-live.

## Verification (proven live on the rehearsal cluster)

The tier was applied to fresh, empty storage and proven end to end:

- **Metrics:** all **10 of 10** scrape targets reported up in `vmagent` (backend, otel-collector,
  postgres-exporter, vmsingle, vmagent, vmalert, loki, tempo, pyroscope, alloy).
- **Traces:** a test trace flowed **backend → otel-collector → Tempo** and was queryable by trace ID.
- **Logs:** Loki ingested logs from **all namespaces** (app + monitoring), labelled by
  namespace/pod/container/node.
- **Dashboards:** Grafana's data sources **VictoriaMetrics + Loki** reported healthy, and all **12
  dashboards** loaded from the provisioned ConfigMap.
- **External reach:** Grafana on **NodePort 30030** and GlitchTip on **NodePort 30137** were both
  reachable from the MSI machine.

## Out of scope / deferred

- **Run the history copy + retire the old Windows volumes** — deferred to the final go-live (with
  SLICE-13). The rehearsal runs on fresh, empty storage on purpose.
- **Create GlitchTip's real project + DSN** — a one-time step in the GlitchTip UI on the fresh cluster
  instance; the `glitchtip-dsn` Secret is wired in but the live DSN/project are set at go-live.
- **The test-pipeline slices (23–27)** — building the in-cluster test/quality pipeline is separate
  work and not part of moving the monitoring tier.
- **Final cutover (SLICE-13 live-database move + SLICE-28 remove Docker from MSI)** — the two
  deliberate go-live checkpoints, each paused for the user.
