# Multi-Language Observability Picker

[SPEC FRESHNESS: reviewed_at=2026-06-02 next_review=2026-09-02]

## Sources

- Google pprof `profile.proto`: https://github.com/google/pprof/blob/main/proto/profile.proto
- Prometheus querying basics: https://prometheus.io/docs/prometheus/latest/querying/basics/
- Perfetto Trace Processor: https://perfetto.dev/docs/analysis/trace-processor
- LLVM GWP-ASan: https://llvm.org/docs/GwpAsan.html

## Behaviour

Given Mint receives pprof, Prometheus, Perfetto, or GWP-ASan telemetry,
When a language-specific threshold is exceeded,
Then the picker emits one normalized finding that the Windows backend can file
through the existing AutoIssue dedup writer.

Given the profiler process itself uses CPU,
When its total CPU use reaches `5.0%` or higher,
Then the picker emits a medium-severity profiler-overhead finding.

Given a telemetry value is below `1%`,
When it is not the profiler-overhead budget,
Then the picker treats the value as noise and emits no finding.

Given pprof CPU profiles are collected for Haskell, C, C++, Rust, or Go,
When the profiler is configured,
Then the CPU sampling rate is `500` samples per second.

Given pprof CPU profiles are collected for Python,
When the profiler is configured,
Then the CPU sampling rate is `250` samples per second.

## Thresholds

| Signal | Threshold | Result |
|---|---:|---|
| Python flat CPU | `>=5%` | High-overhead finding with C++/Rust extension advice |
| Python memory allocation share | `>=20%` | High-overhead finding |
| Go goroutines | `>10000` | Goroutine leak / allocation overhead finding |
| Go `runtime.mallocgc` flat CPU | `>10%` | Goroutine leak / allocation overhead finding |
| Haskell GC to mutation CPU ratio | `>15%` | Medium space-leak warning |
| Rust mutex contention | `>10%` | Lock-contention finding |
| Rust `core::ptr::drop_in_place` flat CPU | `>5%` | Expensive-drop finding |
| C/C++ Perfetto off-CPU I/O wait or context switch | `>25%` | Context-switch / I/O wait finding |
| C/C++ GWP-ASan memory safety error | any supported crash | Critical memory-safety finding |
| Profiler self CPU | `>=5.0%` | Medium profiler-overhead finding |

## pprof Sampling Rates

| Language | CPU profile samples per second |
|---|---:|
| Haskell | `500` |
| C | `500` |
| C++ | `500` |
| Rust | `500` |
| Go | `500` |
| Python | `250` |

## Ownership

The Mint service collects and normalizes telemetry. The Windows backend remains
the AutoIssue database writer. This preserves local-control-plane ownership for
AutoIssue and Paper Trail database access while keeping heavy profiling work off
the Windows C drive.

[SPEC CITED: feature=fr-multi-lang-observability-picker kind=technical_doc id=https://github.com/google/pprof/blob/main/proto/profile.proto verified_at=2026-06-02]
