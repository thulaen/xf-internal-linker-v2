"""Query VictoriaMetrics for a handful of crucial live metrics.

This service is used by PrometheusSummaryView to show live data in the
Angular Prometheus tab. It queries the VictoriaMetrics instant-query API
(the same endpoint findbugs.py uses) — not Prometheus directly — because
VictoriaMetrics is the durable store that vmagent scrapes into.

Why VictoriaMetrics and not the backend's own registry?
- The registry only reflects the current process lifetime; VictoriaMetrics
  spans the full scrape history and can compute rates/quantiles.
- Prometheus-protocol histogram_quantile() queries require multiple scrapes
  worth of bucket data, which the live registry does not have.

If VictoriaMetrics is down the endpoint returns an explicit
"unavailable: <reason>" state for every metric instead of blanking the UI.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request

logger = logging.getLogger(__name__)

_VICTORIAMETRICS_URL = os.environ.get("VICTORIAMETRICS_URL", "http://vmsingle:8428")

# Queries used for the summary dashboard. Each entry is
# (metric_key, promql_expression, unit, description).
_SUMMARY_QUERIES: list[tuple[str, str, str, str]] = [
    (
        "request_rate_per_sec",
        'sum(rate(xf_module_request_total[5m]))',
        "req/s",
        "HTTP requests per second across all modules (5-minute window)",
    ),
    (
        "latency_p95_seconds",
        'histogram_quantile(0.95, sum(rate(xf_module_request_duration_seconds_bucket[5m])) by (le))',
        "s",
        "95th-percentile request latency in seconds (5-minute window)",
    ),
    (
        "error_rate_per_sec",
        'sum(rate(xf_module_request_total{status=~"5.."}[5m]))',
        "req/s",
        "HTTP 5xx errors per second (5-minute window)",
    ),
    (
        "ranking_latency_p95_seconds",
        'histogram_quantile(0.95, sum(rate(xf_scoring_latency_seconds_bucket[5m])) by (le))',
        "s",
        "95th-percentile ranking batch latency in seconds (5-minute window)",
    ),
    (
        "db_connections",
        'pg_stat_database_numbackends{datname!~"^template.*"}',
        "connections",
        "Active Postgres connections (sum across non-template databases)",
    ),
    (
        "embedding_queue_depth",
        'xf_queue_depth{queue="pipeline"}',
        "items",
        "Current pipeline/embedding queue depth",
    ),
]


def _instant_query(promql: str) -> float | str:
    """Run one PromQL instant query; return float or an error string."""
    params = urllib.parse.urlencode({"query": promql})
    url = f"{_VICTORIAMETRICS_URL.rstrip('/')}/api/v1/query?{params}"
    try:
        with urllib.request.urlopen(url, timeout=3.0) as response:  # nosec B310
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        return f"unavailable: {exc.reason}"
    except (TimeoutError, OSError) as exc:
        return f"unavailable: {exc}"
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        return f"parse_error: {exc}"

    result = payload.get("data", {}).get("result", [])
    if not result:
        # No time-series data yet (metric not emitted yet or stale after restart).
        return "no_data"
    value = result[0].get("value", [])
    if len(value) < 2:
        return "no_data"
    raw = value[1]
    if raw in ("NaN", "+Inf", "-Inf", "Inf"):
        return "no_data"
    try:
        return float(raw)
    except (TypeError, ValueError):
        return f"parse_error: {raw!r}"


def get_prometheus_summary() -> dict:
    """Return a dict of live metric values from VictoriaMetrics.

    Each key maps to::

        {
            "value": <float or null>,
            "unit": "<unit string>",
            "description": "<plain-English description>",
            "state": "ok" | "no_data" | "unavailable",
            "raw": "<raw string if not a float>"
        }

    The caller (PrometheusSummaryView) serialises this directly.
    """
    results: dict[str, dict] = {}
    for key, promql, unit, description in _SUMMARY_QUERIES:
        raw = _instant_query(promql)
        if isinstance(raw, float):
            entry = {
                "value": raw,
                "unit": unit,
                "description": description,
                "state": "ok",
            }
        else:
            entry = {
                "value": None,
                "unit": unit,
                "description": description,
                "state": raw.split(":")[0] if ":" in raw else raw,
                "raw": raw,
            }
        results[key] = entry
    return results
