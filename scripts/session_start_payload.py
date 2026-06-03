"""Session-start gate: calls startupd /gate and prints the marker block.

Run at the start of every agent session:

    python scripts/session_start_payload.py --session-type reconciliation \\
        --area backend/apps/auto_issues --area backend/apps/observability

startupd calls Django's /api/session-gate/, assembles the seven-marker
block, signs it with an HMAC token, and returns JSON.  This script:
  1. Checks startupd /health — exits immediately with a plain-English
     fix message if startupd is down.  There is NO fallback to slow
     Docker commands.
  2. Calls GET /gate with the session type and area params.
  3. Writes audit/session_gate_state.json (gitignored).
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
DEFAULT_BASE_URL = "http://127.0.0.1:8765"
_STATE_PATH = ROOT / "audit" / "session_gate_state.json"
_VALID_SESSION_TYPES = ("docs", "infrastructure", "reconciliation", "feature")
_DOWN_MSG = (
    "FAIL: startupd is not responding at {url}/health.\n"
    "The session gate cannot run without it.\n\n"
    "FIX:  docker compose up -d startupd\n"
    "      Wait until: docker compose ps startupd  shows  (healthy)\n"
    "      Then re-run: python scripts/session_start_payload.py\n\n"
    "No session work may begin until startupd is healthy."
)


def main() -> int:
    _prefer_utf8_stdout()
    args = _parse_args()
    base_url = (args.base_url or os.environ.get("STARTUPD_URL", DEFAULT_BASE_URL)).rstrip("/")
    _check_health(base_url, timeout=min(args.timeout, 2.0))
    data = _call_gate(base_url, args.session_type, args.area, timeout=args.timeout)
    _write_gate_state(data["state"])
    print(data["marker_block"])
    return 0


def _parse_args():
    parser = ArgumentParser(description="Run the session-start gate via startupd.")
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
        help=f"startupd base URL (default {DEFAULT_BASE_URL} or $STARTUPD_URL).",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=float(os.environ.get("XF_GATE_TIMEOUT", "10")),
        help="HTTP timeout in seconds (default 10).",
    )
    return parser.parse_args()


def _check_health(base_url: str, *, timeout: float) -> None:
    try:
        urlopen(f"{base_url}/health", timeout=timeout)
    except (HTTPError, URLError, TimeoutError, OSError):
        sys.exit(_DOWN_MSG.format(url=base_url))


def _call_gate(
    base_url: str, session_type: str, areas: list[str], *, timeout: float
) -> dict:
    params: list[tuple[str, str]] = [("type", session_type)]
    for area in areas:
        params.append(("area", area))
    url = f"{base_url}/gate?{urlencode(params)}"
    try:
        with urlopen(url, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        sys.exit(f"FAIL: session gate request failed: {exc}")


def _write_gate_state(state: dict) -> None:
    _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _STATE_PATH.write_text(
        json.dumps(state, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def read_payload(url: str, *, timeout_seconds: float) -> dict:
    """Backward-compat shim: reads /payload directly. New code uses /gate."""
    try:
        with urlopen(url, timeout=timeout_seconds) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(exc) from exc


def _prefer_utf8_stdout() -> None:
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is not None:
        reconfigure(encoding="utf-8", errors="replace")


if __name__ == "__main__":
    raise SystemExit(main())
