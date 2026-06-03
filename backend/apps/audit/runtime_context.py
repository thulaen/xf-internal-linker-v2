"""
Runtime context snapshot captured at error-ingestion time.

Phase GT Step 5. Every ErrorLog row saves what the runtime looked like
at the moment the error happened — embedding model / spaCy / python /
node — so the operator can correlate failures with the active runtime.

Fast path: this function runs on every error, so each check is guarded
to stay under a few ms. No network calls, no shell-outs. The health
services are heavyweight — we do NOT invoke them here, we only call the
tiny OS/library probes they are built on.
"""

from __future__ import annotations

import os
import socket
import sys
from typing import Any

from django.conf import settings


def local_node_identity() -> tuple[str, str]:
    """Return ``(node_id, node_role)`` for this runtime.

    Reads from the ``NODE_ID`` / ``NODE_ROLE`` env vars stamped by the
    slave-worker bootstrap; falls back to ``socket.gethostname()`` and
    ``"primary"`` so the result is always a usable pair of strings on
    any machine. Single source of truth for the slave-worker identity
    tuple used by runtime-context snapshots, error ingestion, and
    diagnostics node rosters.
    """
    return (
        os.environ.get("NODE_ID", socket.gethostname()),
        os.environ.get("NODE_ROLE", "primary"),
    )


def snapshot() -> dict[str, Any]:
    """
    Return a small JSON-serialisable dict describing this runtime right now.

    Safe to call from sync code paths; every call is best-effort and the
    function never raises. Keys match the frontend `RuntimeContext`
    TypeScript interface in frontend/src/app/diagnostics/diagnostics.service.ts.
    """
    node_id, node_role = local_node_identity()
    ctx: dict[str, Any] = {
        "node_id": node_id,
        "node_role": node_role,
        "node_hostname": socket.gethostname(),
        "python_version": sys.version.split()[0],
        "embedding_model": getattr(settings, "EMBEDDING_MODEL", "unknown"),
    }

    # spaCy — check package presence only, do not load a model (loading
    # would cost ~200ms per error).
    try:
        import spacy

        ctx["spacy_model"] = (
            "en_core_web_sm" if spacy.util.is_package("en_core_web_sm") else None
        )
    except Exception:  # noqa: BLE001
        ctx["spacy_model"] = None

    return ctx


__all__ = ["local_node_identity", "snapshot"]
