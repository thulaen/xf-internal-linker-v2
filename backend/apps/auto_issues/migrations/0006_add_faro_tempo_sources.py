"""Add ``tempo`` + ``faro`` to AutoIssue.source choices and seed
both pickers' tunable thresholds.

Tempo (added 2026-05-11) is Grafana's distributed-trace backend. The
tempo picker promotes:

  - **slow spans** — spans whose duration exceeds a threshold per
    operation+service, grouped via TraceQL `/api/search`. Works from
    day one as soon as Tempo starts receiving traces from the otel-
    collector's new ``otlp/tempo`` fan-out exporter.
  - **error spans** — spans with ``status=error`` grouped by name +
    service, threshold-gated by occurrence count.

Faro (added 2026-05-11) is Grafana's frontend RUM SDK. Its events ship
through the Alloy ``faro.receiver`` into Loki with
``{service="frontend", source="faro"}`` labels, so the faro picker
queries Loki via LogQL just like the loki picker. Two detectors:

  - **error clusters** — JS errors / exceptions normalized through the
    standard fingerprinter and gated on occurrence count.
  - **Web Vitals breaches** — LCP / INP / CLS samples over per-metric
    thresholds, grouped by route.

Per DEFAULT-ON-RULE every setting is seeded ON with a non-zero starting
value via ``get_or_create``. Tempo and Faro are both internal services
in the local docker-compose stack — no ``external-data-gated`` exemption
needed.

The ``tempo.retention_hours`` default is hardware-aware: low/medium tier
gets 72 h, high/workstation gets 168 h. Reads ``hardware_profile``
defensively so a missing import never blocks the migration.
"""

from django.db import migrations, models


# Hardware-aware defaults — picked at seed time so they match the host
# the operator runs on. Kept as small dicts so a future tier table edit
# touches one place.
_TEMPO_RETENTION_BY_TIER = {
    "low": "72",
    "medium": "72",
    "high": "168",
    "workstation": "168",
}


def _tempo_retention_hours_for_tier() -> str:
    """Return the retention default string, falling back to 72 h on error."""
    try:
        from apps.pipeline.services.hardware_profile import detect_profile

        tier = detect_profile().tier
    except Exception:  # noqa: BLE001 — defensive at migration time
        return "72"
    return _TEMPO_RETENTION_BY_TIER.get(tier, "72")


# Tempo picker tunables. Internal-only Tempo service, so DEFAULT-ON.
def _tempo_defaults() -> dict[str, dict[str, str]]:
    return {
        "tempo.query_url": {
            "value": "http://tempo:3200",
            "value_type": "string",
            "category": "observability",
            "description": (
                "Base URL of the Tempo HTTP API the tempo_picker queries. "
                "Default `http://tempo:3200` matches the docker-compose "
                "service. Override only when running Tempo on a non-default "
                "port or remote host."
            ),
        },
        "tempo.slow_span_threshold_ms": {
            "value": "1000",
            "value_type": "int",
            "category": "observability",
            "description": (
                "A span is promoted as kind='slow_span' when its duration "
                "exceeds this many milliseconds. Default 1000 ms (1 s)."
            ),
        },
        "tempo.error_span_min_count": {
            "value": "3",
            "value_type": "int",
            "category": "observability",
            "description": (
                "Minimum number of error spans (status=error) sharing a "
                "fingerprint before promoting to AutoIssue. Default 3."
            ),
        },
        "tempo.scan_window_seconds": {
            "value": "3600",
            "value_type": "int",
            "category": "observability",
            "description": (
                "Time window (seconds) the tempo_picker scans on each run. "
                "Default 3600 (1 h) — picker runs every 30 min so this "
                "gives 2x overlap and no missed spans."
            ),
        },
        "tempo.retention_hours": {
            "value": _tempo_retention_hours_for_tier(),
            "value_type": "int",
            "category": "observability",
            "description": (
                "How long Tempo keeps trace blocks before the compactor "
                "deletes them. Hardware-aware: 72 h on low/medium tier "
                "(small laptop), 168 h on high/workstation. The Tempo "
                "container reads this from the TEMPO_RETENTION_HOURS env "
                "var sourced from this setting."
            ),
        },
    }


# Faro picker tunables. Faro Web SDK ships browser RUM into Alloy then
# Loki — the picker queries Loki, but every threshold belongs to the
# faro source (and the faro picker reads them).
FARO_DEFAULTS = {
    "faro.collector_url": {
        "value": "http://localhost:12347/collect",
        "value_type": "string",
        "category": "observability",
        "description": (
            "The browser ships Faro RUM events to this URL. Default "
            "matches the Alloy faro.receiver block in config.alloy. "
            "Server-side it's reachable as http://alloy:12347/collect "
            "but the browser uses the host-exposed port."
        ),
    },
    "faro.session_sample_rate": {
        "value": "1.0",
        "value_type": "float",
        "category": "observability",
        "description": (
            "Fraction of browser sessions Faro records (0.0–1.0). Default "
            "1.0 (100 %). Drop to 0.25 on low-tier hardware to reduce "
            "Loki write volume."
        ),
    },
    "faro.error_min_count": {
        "value": "5",
        "value_type": "int",
        "category": "observability",
        "description": (
            "A normalized JS error fingerprint is promoted to AutoIssue "
            "when it occurs at least this many times in the scan window. "
            "Default 5."
        ),
    },
    "faro.web_vitals_threshold_lcp_ms": {
        "value": "2500",
        "value_type": "int",
        "category": "observability",
        "description": (
            "Largest Contentful Paint threshold in milliseconds. Sessions "
            "with LCP over this value count as a breach. Default 2500 ms "
            "matches Google's 'needs improvement' boundary."
        ),
    },
    "faro.web_vitals_threshold_inp_ms": {
        "value": "200",
        "value_type": "int",
        "category": "observability",
        "description": (
            "Interaction to Next Paint threshold in milliseconds. Default "
            "200 ms matches Google's 'needs improvement' boundary."
        ),
    },
    "faro.web_vitals_threshold_cls": {
        "value": "0.1",
        "value_type": "float",
        "category": "observability",
        "description": (
            "Cumulative Layout Shift threshold (unitless). Default 0.1 "
            "matches Google's 'needs improvement' boundary."
        ),
    },
}


def seed_faro_tempo_settings(apps, schema_editor):
    AppSetting = apps.get_model("core", "AppSetting")
    combined = {**_tempo_defaults(), **FARO_DEFAULTS}
    for key, meta in combined.items():
        AppSetting.objects.get_or_create(key=key, defaults=meta)


def unseed_faro_tempo_settings(apps, schema_editor):
    AppSetting = apps.get_model("core", "AppSetting")
    keys = list(_tempo_defaults().keys()) + list(FARO_DEFAULTS.keys())
    AppSetting.objects.filter(key__in=keys).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("auto_issues", "0005_add_loki_source_and_seed_loki_picker_settings"),
        ("core", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="autoissue",
            name="source",
            field=models.CharField(
                choices=[
                    ("glitchtip", "GlitchTip"),
                    ("pyroscope", "Pyroscope"),
                    ("tempo", "Tempo"),
                    ("loki", "Loki"),
                    ("faro", "Faro"),
                    ("agent", "Agent find"),
                ],
                db_index=True,
                max_length=16,
            ),
        ),
        migrations.RunPython(seed_faro_tempo_settings, unseed_faro_tempo_settings),
    ]
