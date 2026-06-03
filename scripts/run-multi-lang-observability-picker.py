"""Mint runner for multi-language observability AutoIssue findings."""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from apps.auto_issues.services.multi_lang_picker import (  # noqa: E402
    find_multi_lang_observability_issues,
    normalize_gwp_asan_crash,
    normalize_perfetto_trace,
    normalize_prometheus_series,
    pprof_collector_gap_findings,
    pprof_cpu_sample_rate_for_language,
    send_findings_to_windows_backend,
)


PROMETHEUS_QUERIES = (
    ("go_goroutines", "go"),
    ("profiler_cpu_pct", "go"),
    ("haskell_gc_cpu_pct", "haskell"),
    ("haskell_mut_cpu_pct", "haskell"),
)


def main() -> int:
    interval = int(os.environ.get("MULTI_LANG_OBSERVABILITY_PICKER_INTERVAL_SECONDS", "300"))
    windows_url = os.environ.get("WINDOWS_AUTOISSUE_BASE_URL", "http://10.10.10.10:8000")
    token = os.environ.get("AUTOISSUE_INGEST_TOKEN", "")
    if not token:
        print("[multi-lang-picker] AUTOISSUE_INGEST_TOKEN is missing; not starting", flush=True)
        return 2
    _log_sampling_rates()
    while True:
        findings = collect_findings()
        if findings:
            result = send_findings_to_windows_backend(
                findings,
                base_url=windows_url,
                token=token,
            )
            print(f"[multi-lang-picker] sent={len(findings)} result={result}", flush=True)
        else:
            print("[multi-lang-picker] sent=0", flush=True)
        time.sleep(interval)


def collect_findings() -> list:
    findings = pprof_collector_gap_findings()
    for payload in _prometheus_payloads():
        findings.extend(find_multi_lang_observability_issues(payload))
    for payload in _perfetto_payloads():
        findings.extend(find_multi_lang_observability_issues(payload))
    for payload in _gwp_asan_payloads():
        findings.extend(find_multi_lang_observability_issues(payload))
    return findings


def _log_sampling_rates() -> None:
    compiled_rate = pprof_cpu_sample_rate_for_language("go")
    python_rate = pprof_cpu_sample_rate_for_language("python")
    print(
        "[multi-lang-picker] pprof_cpu_sample_rate_hz "
        f"compiled={compiled_rate} python={python_rate}",
        flush=True,
    )


def _prometheus_payloads() -> list[dict[str, Any]]:
    prometheus_url = os.environ.get("PROMETHEUS_BASE_URL", "http://10.10.10.10:8428")
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for query, language in PROMETHEUS_QUERIES:
        for item in _query_prometheus(prometheus_url, query):
            metric = dict(item.get("metric") or {})
            metric.setdefault("__name__", query)
            service = str(
                metric.get("service")
                or metric.get("job")
                or metric.get("container")
                or "unknown-service"
            )
            item = {**item, "metric": metric}
            grouped.setdefault((service, language), []).append(item)
    return [
        normalize_prometheus_series(series, service=service, language=language)
        for (service, language), series in grouped.items()
    ]


def _query_prometheus(base_url: str, query: str) -> list[dict[str, Any]]:
    url = f"{base_url.rstrip('/')}/api/v1/query?{urllib.parse.urlencode({'query': query})}"
    try:
        with urllib.request.urlopen(url, timeout=5) as response:  # noqa: S310
            body = json.loads(response.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001 - one telemetry source must not stop the loop.
        print(f"[multi-lang-picker] prometheus query failed query={query} error={exc}", flush=True)
        return []
    return list(((body.get("data") or {}).get("result")) or [])


def _perfetto_payloads() -> list[dict[str, Any]]:
    root = Path(os.environ.get("PERFETTO_INPUT_DIR", "/repo/observability/perfetto"))
    payloads = []
    for path in _json_files(root):
        rows = _load_json(path)
        if isinstance(rows, dict):
            rows = rows.get("threads", [])
        if isinstance(rows, list):
            payloads.append(normalize_perfetto_trace(rows, service=_service_from_path(path)))
    return payloads


def _gwp_asan_payloads() -> list[dict[str, Any]]:
    root = Path(os.environ.get("GWP_ASAN_INPUT_DIR", "/repo/observability/gwp-asan"))
    payloads = []
    for path in _json_files(root):
        crash = _load_json(path)
        if isinstance(crash, dict):
            payloads.append(normalize_gwp_asan_crash(crash, service=_service_from_path(path)))
    return payloads


def _json_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted(root.glob("*.json"))


def _load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[multi-lang-picker] skipped bad json path={path} error={exc}", flush=True)
        return None


def _service_from_path(path: Path) -> str:
    return path.stem.split(".", 1)[0] or "unknown-service"


if __name__ == "__main__":
    raise SystemExit(main())
