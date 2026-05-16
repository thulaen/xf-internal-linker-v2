# OpenTelemetry Profiles to Pyroscope Spec

[SPEC CITED: feature=opentelemetry-profiles-pyroscope kind=technical_doc id=https://opentelemetry.io/blog/2024/state-profiling/ verified_at=2026-05-16]
[SPEC CITED: feature=opentelemetry-profiles-pyroscope kind=technical_doc id=https://grafana.com/docs/pyroscope/latest/configure-client/opentelemetry/ebpf-profiler/ verified_at=2026-05-16]
[SPEC CITED: feature=opentelemetry-profiles-pyroscope kind=academic_paper id=10.1109/MM.2010.68 verified_at=2026-05-16]
[SPEC FRESHNESS: reviewed_at=2026-05-16 next_review=2026-06-16]

## Goal

Connect OpenTelemetry Profiles to Pyroscope so agents can inspect real profile data before they change production source.

OpenTelemetry Profiles means sampled stack data that shows where code spends time or memory. Pyroscope is the local service that stores and queries that data. OTLP means the OpenTelemetry transfer format used between the app, collector, and storage service.

## Sources Of Truth

| Area | Source | Design decision |
|---|---|---|
| Collector profile support | OpenTelemetry State of Profiling, 2024 | Use OpenTelemetry Collector version `0.112.0` or newer and enable `service.profilesSupport`. |
| Pyroscope profile ingest | Grafana Pyroscope OpenTelemetry profiling documentation | Export profiles to `pyroscope:4040` over OTLP gRPC with insecure TLS inside the Docker network. |
| Continuous profiling value | Ren et al., Google-Wide Profiling, IEEE Micro 2010, DOI `10.1109/MM.2010.68` | Keep profiling always available for low-overhead performance investigation. |

## Required Config

- `docker-compose.yml` must run `otel/opentelemetry-collector-contrib:0.112.0` or newer enough to support profiles and the existing GlitchTip exporter settings.
- `docker-compose.yml` must pass `--feature-gates=service.profilesSupport` to the collector.
- `docker-compose.yml` must run `grafana/pyroscope:1.18.1` or newer enough to receive OTLP profiles.
- `otelcol-config.yaml` must define an `otlp/pyroscope` exporter with `endpoint: pyroscope:4040`.
- `otelcol-config.yaml` must define a `profiles` pipeline that receives `otlp` and exports `otlp/pyroscope`.

## Agent Rule

Any future speed, profiling, or native-rewrite task must add or cite a spec before implementation. The spec must use at least one patent, academic paper, or official technical document. TDD is required: agents must add or update the focused test before or alongside the code, then run it until it passes.

The handoff marker is:

`[PERFORMANCE SPEC: sources=<ids> source_types=<patent|academic_paper|technical_doc> tdd=yes tests=<commands>]`

## Tests

- `backend/apps/audit/tests_glitchtip_compose_integrity.py` checks the Docker and collector profile wiring.
- `backend/apps/auto_issues/tests_inspect_profiles_command.py` checks that the profile inspector accepts only config with a profile pipeline, compatible versions, and the profile feature flag.
- `.githooks/test_check_profiling_proof.py` checks that profiling and speed work needs a source-backed spec marker.
