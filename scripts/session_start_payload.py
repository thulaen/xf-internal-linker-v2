"""Session-start gate: calls Django's /api/session-gate/ and prints the marker block.

Run at the start of every agent session:

    python scripts/session_start_payload.py --session-type reconciliation \\
        --area backend/apps/auto_issues --area backend/apps/observability

History note (2026-06-11): this script used to call the Go "startupd"
daemon on port 8765, which itself only proxied Django's
/api/session-gate/ endpoint and wrapped the response. The Go tier was
removed (ADR 0007 — Python + Rust only), so the script now calls Django
directly through nginx on port 80. This script:
  1. Calls GET /api/session-gate/ with the session type and area params.
     Exits with a plain-English fix message if the stack is down.
  2. Assembles the marker block from the returned markers.
  3. Writes audit/session_gate_state.json (gitignored) — the
     check-autoissue-quota hook reads session_type from it.
  4. Prints the marker block to stdout ready to paste into AGENT-HANDOFF.md.
"""

from __future__ import annotations

import json
import os
import sys
from argparse import ArgumentParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE_URL = "http://localhost"
GATE_PATH = "/api/session-gate/"
_STATE_PATH = ROOT / "audit" / "session_gate_state.json"
_VALID_SESSION_TYPES = ("docs", "infrastructure", "reconciliation", "feature")

# Canonical marker order — matches the hook chain's expected sequence
# (sticky → registry → paper trail → snapshots → lessons → TDD preflight).
_MARKER_ORDER = (
    "sticky",
    "registry",
    "paper_trail",
    "snapshots",
    "lessons",
    "tdd_preflight",
)

_DOWN_MSG = (
    "FAIL: the backend is not responding at {url}.\n"
    "The session gate cannot run without it.\n\n"
    "FIX:  docker compose up -d backend nginx\n"
    "      Wait until: docker compose ps backend  shows  (healthy)\n"
    "      Then re-run: python scripts/session_start_payload.py\n\n"
    "No session work may begin until the backend is healthy."
)


def main() -> int:
    _prefer_utf8_stdout()
    args = _parse_args()
    base_url = (
        args.base_url or os.environ.get("SESSION_GATE_URL", DEFAULT_BASE_URL)
    ).rstrip("/")
    data = _call_gate(base_url, args.session_type, args.area, timeout=args.timeout)
    _write_gate_state(build_gate_state(args.session_type, data))
    print(build_marker_block(data.get("markers") or {}))
    return 0


def build_marker_block(markers: dict) -> str:
    """Join the per-marker strings into the canonical paste-ready block.

    Known markers come first in protocol order; unknown keys the backend
    may add later are appended rather than dropped. Empty strings are
    skipped.
    """
    ordered = [markers[key] for key in _MARKER_ORDER if markers.get(key)]
    extras = [
        value
        for key, value in markers.items()
        if key not in _MARKER_ORDER and value
    ]
    return "\n".join(ordered + extras)


def build_gate_state(session_type: str, data: dict) -> dict:
    """State written to audit/session_gate_state.json.

    ``session_type`` is required by .githooks/check-autoissue-quota.py;
    ``total_open_count`` is informational.
    """
    return {
        "session_type": session_type,
        "total_open_count": int(data.get("total_open_count") or 0),
    }


def _parse_args():
    parser = ArgumentParser(
        description="Run the session-start gate against Django's /api/session-gate/."
    )
    parser.add_argument(
        "--session-type",
        choices=_VALID_SESSION_TYPES,
        default="feature",
        help="Session type: docs / infrastructure / reconciliation / feature.",
    )
    parser.add_argument(
        "--area",
        action="append",
        default=[],
        metavar="PATH",
        help="Repo-relative path for lesson lookup. Repeat for multiple areas.",
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help=(
            f"Backend base URL (default {DEFAULT_BASE_URL} — nginx on port 80 — "
            "or $SESSION_GATE_URL)."
        ),
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=float(os.environ.get("XF_GATE_TIMEOUT", "30")),
        help="HTTP timeout in seconds (default 30).",
    )
    return parser.parse_args()


def _call_gate(
    base_url: str, session_type: str, areas: list[str], *, timeout: float
) -> dict:
    params: list[tuple[str, str]] = [("type", session_type)]
    for area in areas:
        params.append(("area", area))
    url = f"{base_url}{GATE_PATH}?{urlencode(params)}"
    try:
        with urlopen(url, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        sys.exit(_DOWN_MSG.format(url=f"{base_url}{GATE_PATH}") + f"\n\nDetail: {exc}")
    except json.JSONDecodeError as exc:
        sys.exit(f"FAIL: session gate returned invalid JSON: {exc}")


def _write_gate_state(state: dict) -> None:
    _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _STATE_PATH.write_text(
        json.dumps(state, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _prefer_utf8_stdout() -> None:
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is not None:
        reconfigure(encoding="utf-8", errors="replace")


if __name__ == "__main__":
    raise SystemExit(main())
