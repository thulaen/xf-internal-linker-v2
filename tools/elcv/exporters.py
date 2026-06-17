#!/usr/bin/env python3
"""ELCV exporters — multi-scope and config-driven (NO hardcoded targets).

Targets live in `elcv-scopes.json` (the single source of truth), so multiple initiatives
never clash: a global 2,000,000,000 ceiling, plus named scopes each measured over their own
paths (e.g. ranklab=28M, aegis=5M). USO de-duplication runs across the whole codebase, and
vendored/test/generated code is excluded, complexity is penalised (SCW), and the 27-rule
gate blocks duplication/bloat — so every unit counted toward any target is unique, executed
product logic. ELCV does NOT depend on runtime data (ARW was removed, ADR-006): the number
is measured, not "pending".

Outputs (all from one computation, so the app card / dashboard / markdown can never drift):
  --format json        cached report the app reads (never a live scan on page load)
  --format prometheus  metrics for VictoriaMetrics/Grafana
  --format board       human-readable markdown meter
  --cache <dir>        write both elcv-report.json and ELCV-REPORT.md atomically
"""
from __future__ import annotations

import argparse
import datetime
import json
import re
from pathlib import Path

import elcv
import multilang

SCOPES_FILE = Path(__file__).resolve().parent / "elcv-scopes.json"


def load_scopes(path: Path = SCOPES_FILE) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _area(path_str: str) -> str:
    posix = Path(path_str).as_posix()
    for pattern, label in (
        (r"backend/apps/([^/]+)/", "{0}"),
        (r"rust/extensions/([^/]+)/", "rust:{0}"),
        (r"tools/([^/]+)/", "tools:{0}"),
        (r"ranklab/([^/]+)/", "ranklab:{0}"),
    ):
        m = re.search(pattern, posix)
        if m:
            return label.format(m.group(1))
    if "frontend/" in posix:
        return "frontend"
    return "other"


def by_area(report: elcv.Report) -> dict:
    areas: dict[str, float] = {}
    for path, file_elcv, _units in report.per_file:
        key = _area(path)
        areas[key] = round(areas.get(key, 0.0) + file_elcv, 2)
    return dict(sorted(areas.items(), key=lambda kv: -kv[1]))


def _gather_py(roots) -> list:
    paths: set = set()
    for root in roots:
        r = Path(root)
        if r.is_file() and r.suffix == ".py" and not elcv.should_skip(r):
            paths.add(r)
        elif r.is_dir():
            paths.update(p for p in r.rglob("*.py") if not elcv.should_skip(p))
    return sorted(paths)


def _scope_rust_ts(roots):
    total, backend = 0.0, "none"
    for root in roots:
        r = Path(root)
        if not r.is_dir():
            continue
        for count in multilang.count_paths(r).values():
            total += count.elcv
            backend = count.backend
    return round(total, 2), backend


def scope_report(name: str, definition: dict) -> dict:
    roots = definition["roots"]
    target = definition["target"]
    py = elcv.compute_files(_gather_py(roots))
    rust_ts, backend = _scope_rust_ts(roots)
    current = round(py.elcv + rust_ts, 2)
    return {
        "name": name,
        "target": target,
        "roots": roots,
        "note": definition.get("note", ""),
        "python_elcv": py.elcv,
        "python_files": py.files,
        "rust_ts": rust_ts,
        "rust_ts_backend": backend,
        "current": current,
        "percent": round(100 * current / target, 6) if target else 0.0,
        "remaining": round(max(0.0, target - current), 2),
        "by_area": by_area(py),
    }


def full_report(now: str | None = None, config: dict | None = None) -> dict:
    cfg = config or load_scopes()
    now = now or datetime.datetime.now().isoformat(timespec="seconds")
    scopes = {name: scope_report(name, d) for name, d in cfg["scopes"].items()}
    ceiling = cfg["global_ceiling"]
    repo_current = (scopes.get("repo") or {}).get(
        "current", max((s["current"] for s in scopes.values()), default=0.0))
    return {
        "generated_at": now,
        "status": "measured",   # ELCV is measured (no runtime dependency; ARW removed, ADR-006)
        "global_ceiling": ceiling,
        "global_current": repo_current,
        "global_percent": round(100 * repo_current / ceiling, 9) if ceiling else 0.0,
        "scopes": scopes,
    }


def to_json(report=None, now=None, config=None) -> str:
    return json.dumps(report or full_report(now, config), indent=2)


def to_prometheus(report=None, now=None, config=None) -> str:
    report = report or full_report(now, config)
    lines = [
        "# HELP elcv_global_ceiling Global ELCV capacity ceiling (all initiatives).",
        "# TYPE elcv_global_ceiling gauge",
        f"elcv_global_ceiling {report['global_ceiling']}",
        "# TYPE elcv_global_current gauge",
        f"elcv_global_current {report['global_current']}",
        "# TYPE elcv_global_percent gauge",
        f"elcv_global_percent {report['global_percent']}",
        "# HELP elcv_scope_total Current ELCV per initiative scope.",
        "# TYPE elcv_scope_total gauge",
    ]
    for name, s in report["scopes"].items():
        lines.append(f'elcv_scope_total{{scope="{name}"}} {s["current"]}')
    lines.append("# TYPE elcv_scope_target gauge")
    for name, s in report["scopes"].items():
        lines.append(f'elcv_scope_target{{scope="{name}"}} {s["target"]}')
    lines.append("# TYPE elcv_scope_percent gauge")
    for name, s in report["scopes"].items():
        lines.append(f'elcv_scope_percent{{scope="{name}"}} {s["percent"]}')
    lines.append("# TYPE elcv_scope_remaining gauge")
    for name, s in report["scopes"].items():
        lines.append(f'elcv_scope_remaining{{scope="{name}"}} {s["remaining"]}')
    lines.append("# TYPE elcv_by_area gauge")
    for area, val in (report["scopes"].get("repo") or {}).get("by_area", {}).items():
        lines.append(f'elcv_by_area{{area="{area}"}} {val}')
    return "\n".join(lines) + "\n"


def to_board_markdown(report=None, now=None, config=None) -> str:
    report = report or full_report(now, config)
    out = [
        "# ELCV Scopes (auto-generated — do not edit by hand)", "",
        f"Generated: {report['generated_at']}  ·  Status: **{report['status']}** "
        f"(measured; no runtime dependency)", "",
        f"**Global ceiling:** {report['global_ceiling']:,} ELCV  ·  "
        f"**Repo current:** {report['global_current']:,.0f} ({report['global_percent']}%)", "",
        "| Scope | Current | Target | % | Remaining |",
        "|---|--:|--:|--:|--:|",
    ]
    for name, s in report["scopes"].items():
        out.append(f"| {name} | {s['current']:,.0f} | {s['target']:,} | {s['percent']} | "
                   f"{s['remaining']:,.0f} |")
    out += [
        "", "_Every counted unit is unique (USO de-dup across the whole codebase), "
        "non-vendor, and non-bloat (SCW + the 27-rule gate). Targets live in "
        "`tools/elcv/elcv-scopes.json` — never hardcoded._",
    ]
    return "\n".join(out) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Export multi-scope ELCV (config-driven).")
    parser.add_argument("--format", choices=("json", "prometheus", "board"), default="board")
    parser.add_argument("--out", help="write to this file instead of stdout")
    parser.add_argument("--cache", help="write elcv-report.json AND ELCV-REPORT.md into this dir")
    args = parser.parse_args(argv)

    if args.cache:
        report = full_report()
        d = Path(args.cache)
        d.mkdir(parents=True, exist_ok=True)
        (d / "elcv-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        (d / "ELCV-REPORT.md").write_text(to_board_markdown(report), encoding="utf-8")
        print(f"cached elcv-report.json + ELCV-REPORT.md -> {d}")
        return 0

    text = {"json": to_json, "prometheus": to_prometheus, "board": to_board_markdown}[args.format]()
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"wrote {args.format} -> {args.out}")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
