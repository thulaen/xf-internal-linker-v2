# Go Stream Broker Spec

[SPEC CITED: feature=go-streamd-broker kind=academic_paper id=10.14778/2536222.2536229 verified_at=2026-05-16]
[SPEC CITED: feature=go-streamd-broker kind=academic_paper id=10.1145/502034.502057 verified_at=2026-05-16]
[SPEC CITED: feature=go-streamd-broker kind=patent id=US10042713B2 verified_at=2026-05-16]
[SPEC FRESHNESS: reviewed_at=2026-05-16 next_review=2026-06-16]

## Summary

`streamd` is the Go service that owns high-volume event intake for this project.
Go is the preferred path for the stream layer. Python remains the safe fallback
for Django business rules, final suggestion scoring, embeddings, and the review
workflow.

The first slice replaces Python webhook-event dedupe and event brokering. Later
slices move live browser streams, job progress streams, operations feed streams,
link-health probes, and lightweight analytics rollups into the same Go service.

## Sources Of Truth

| Design choice | Source |
|---|---|
| Event-time stream processing, replay, persistent per-key state, and checkpoints | Akidau et al. 2013, *MillWheel: Fault-Tolerant Stream Processing at Internet Scale*, DOI (permanent paper identifier) `10.14778/2536222.2536229`, verified against Google Research and DBLP. |
| Watermarks and late-event handling | Akidau et al. 2015, *The Dataflow Model*, Proceedings of the VLDB Endowment, DOI `10.14778/2824032.2824076`, verified against the VLDB record. |
| Bounded stages connected by explicit queues | Welsh, Culler, and Brewer 2001, *SEDA: An Architecture for Well-Conditioned, Scalable Internet Services*, proceedings DOI `10.1145/502034.502057`, verified against DBLP. |
| Append-only durable log with later compaction | O'Neil et al. 1996, *The Log-Structured Merge-Tree*, DOI `10.1007/s002360050048`, verified against Springer-indexed records. |
| Adaptive checkpoint policy | Patent `US10042713B2`, *Adaptive incremental checkpointing for data stream processing applications*. |
| Dynamically scheduled checkpoints | Patent `US10623281B1`, *Dynamically scheduled checkpoints in distributed data streaming system*. |
| Offset-based watermarks | Patent `US12061651B1`, *Offset-based watermarks for data stream processing*. |
| Window and trigger semantics | Patent `US10732928B1`, *Data flow windowing and triggering*. |
| Transactional streaming writes | Patent `US11573876B2`, *Scalable exactly-once data processing using transactional streaming writes*. |
| Idempotent stream processing | Patent `US20200220910A1`, *Idempotent processing of data streams*. |
| Two-phase commit state transitions | Patent `US10296371B2`, *Passive two-phase commit system for high-performance distributed transaction execution*. |
| Current 512 MB Go-service memory cap | Repo operator requirement plus `HARDWARE-PROFILES.md` and `DISK-PRESSURE-RULES.md`. |
| Docker-only Go build and checks | `COMPILED-LANGUAGE-RULES.md`, `scripts/run-go-quality.sh`, and `scripts/check_go_tools.py`. |

Academic papers are the default source for this slice because they describe
stream-processing behavior, queue bounds, and durable-log design directly.
Patent references are used as design references only. Do not copy patent claim
language into code comments, docs, API names, or user-facing text.

Reference links:

- MillWheel: https://research.google/pubs/pub41378/
- MillWheel DBLP record: https://dblp.uni-trier.de/rec/journals/pvldb/AkidauBBCHLMMNW13.html
- Dataflow paper: https://www.vldb.org/pvldb/vol8/p1792-Akidau.pdf
- SEDA DBLP record: https://dblp.org/rec/conf/sosp/WelshCB01
- LSM-tree record: https://cir.nii.ac.jp/crid/1361418519657211264
- US10042713B2: https://patents.google.com/patent/US10042713B2/en
- US10623281B1: https://patents.google.com/patent/US10623281B1/en
- US12061651B1: https://patents.google.com/patent/US12061651B1/en
- US10732928B1: https://patents.google.com/patent/US10732928B1/en
- US11573876B2: https://patents.google.com/patent/US11573876B2/en
- US20200220910A1: https://patents.google.com/patent/US20200220910A1/en
- US10296371B2: https://patents.google.com/patent/US10296371B2/en

## Scope

Go owns:

- Webhook intake, secret checks, dedupe keys, and event publication.
- Message topics, ordered offsets, acknowledgement tracking, and replay.
- Bounded in-memory buffers and later capped disk segments.
- Browser-facing live event streams after the cutover.

Python keeps:

- Django database ownership.
- Import and embedding business rules.
- Final ranking formulas and diagnostics.
- Operator review and approval workflow.

## Shadow Runtime Scope

The stream engine layer is enabled by default in shadow mode. In shadow mode,
Go computes the result first, Python remains the comparison and fallback path,
and a feature cannot become live-default until parity, speed, memory, and review
checks all pass.

This layer adds the 40 non-overlapping features above the broker:

- Job graph runner, stable job step IDs, operator plugin registry, and operator
  lifecycle hooks.
- Automatic checkpoints, manual savepoints, savepoint restore validation, and
  snapshot catalog.
- State schema versions, per-key state, time-to-live cleanup, compaction, size
  accounting, disk spill, memory budget manager, in-memory backend, and
  file-backed backend.
- Timer wheel, delayed timers, watermarks, late-event quarantine, tumbling
  windows, sliding windows, session windows, window finalization, count
  triggers, and time triggers.
- Side outputs, dead-letter handling, poison-event isolation, schema registry,
  schema compatibility checks, exactly-once output mode, at-least-once output
  mode, transactional commits, two-phase commits, pause/resume, per-operator
  metrics, and admin inspection API.

The broker's dedupe, secret checks, publish path, topics, offsets, replay,
acknowledgements, and bounded topic buffers remain separate and are not
reimplemented here.

## Defaults

| Default | Value | Reason |
|---|---:|---|
| Docker hard memory cap | 512 MB | User requirement. |
| Go soft memory limit | 384 MB | Leaves room below the Docker cap for runtime overhead. |
| First-slice topic buffer | 1-8 events in tests | Keeps tests small while proving bounded behavior. Production value lands with measured load tests. |
| Minimum Go speedup | 5x faster than Python | User requirement; enforced by a Go test that compares Go dedupe against a Python baseline. |
| Go coverage target | 95% | `docs/CODE-COVERAGE-RULES.md` Go-module rule. |

## Non-Overlap

This is not a new ranking signal. It does not change score math.
Live analytics-based scoring updates only move existing analytics inputs faster.
Any future score formula needs its own ranking spec, sources, defaults, diagnostics,
and benchmark plan.

## Test Plan

- Write failing Go tests before implementation.
- Run `go test ./...` inside Docker.
- Run `go test -race -shuffle=on -count=1 ./...` inside Docker.
- Run the repo Go quality command through `scripts/run-go-quality.sh`.
- Keep the speed test blocking until Go dedupe is at least 5x faster than the
  Python baseline.
- Add integration tests before any Python route is removed or bypassed.

## Rollout

1. Add Go broker core with tests and benchmark guard.
2. Add HTTP endpoints behind an off-by-default internal route.
3. Switch webhook ingress to Go as the default path after tests pass.
4. Keep Python fallback for one release window.
5. Remove replaced Python code only after replay, dedupe, and UI checks pass.
