"""Helpers for detecting when sync database work is unsafe."""

from __future__ import annotations

import asyncio


def in_async_context() -> bool:
    """Return True when the current thread is running an async event loop."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return False
    return True
