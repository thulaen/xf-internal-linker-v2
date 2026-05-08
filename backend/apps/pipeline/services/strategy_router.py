"""Pick Strategy A (Claude Code) vs Strategy B (pure Python) at run time.

KISS detection logic:
    1. If env var `MONTHLY_STRATEGY` is set, return that verbatim.
    2. Else, ping `claude -p ping` with a 5s timeout.
       - exit 0 in 5s → "claude_code"
       - timeout / non-zero / not on PATH → "python"
    3. Cache the result for `_CACHE_TTL_SECONDS` to avoid re-pinging on every
       call inside the same process.

The Python fallback (Strategy B) is always available; the router only picks
between "fast LLM-narrated picks" and "deterministic-template picks". Both
write the same report file path and flag the same DB rows.
"""

from __future__ import annotations

import logging
import os
import subprocess
import time
from typing import Literal

logger = logging.getLogger(__name__)

Strategy = Literal["claude_code", "python"]

_CACHE: dict[str, tuple[float, Strategy]] = {}
_CACHE_TTL_SECONDS = 60.0


def pick_strategy(*, override: str | None = None) -> Strategy:
    """Return the active strategy. Cached for 60s."""
    if override is None:
        override = os.environ.get("MONTHLY_STRATEGY", "").strip().lower() or None
    if override == "python":
        return "python"
    if override == "claude_code":
        return "claude_code"
    if override == "auto":
        override = None
    cached = _CACHE.get("active")
    if cached and (time.time() - cached[0]) < _CACHE_TTL_SECONDS:
        return cached[1]
    chosen: Strategy = "python"
    try:
        result = subprocess.run(
            ["claude", "-p", "ping"],
            timeout=5,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            chosen = "claude_code"
            logger.debug("strategy_router: chose claude_code (ping ok)")
        else:
            logger.debug(
                "strategy_router: chose python (claude returned exit %d)",
                result.returncode,
            )
    except FileNotFoundError:
        logger.debug("strategy_router: chose python (claude not on PATH)")
    except subprocess.TimeoutExpired:
        logger.debug("strategy_router: chose python (claude ping timed out)")
    except Exception:  # noqa: BLE001  # justification: any exception → fallback to deterministic Python; surface in debug log
        logger.exception("strategy_router: unexpected error during detect; falling back to python")
    _CACHE["active"] = (time.time(), chosen)
    return chosen


def reset_cache() -> None:
    """Clear the module-level cache (used by tests)."""
    _CACHE.clear()
