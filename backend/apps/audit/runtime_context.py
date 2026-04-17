"""
Runtime context snapshot captured at error-ingestion time.

Phase GT Step 5. Every ErrorLog row saves what the runtime looked like
at the moment the error happened — GPU / CUDA / embedding model / spaCy /
python / node — so the operator can correlate "this error only happens
on CPU fallback" or "only on slave-01". Reuses the detectors in
apps.health.services (no duplicate GPU / spaCy code).

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


def snapshot() -> dict[str, Any]:
    """
    Return a small JSON-serialisable dict describing this runtime right now.

    Safe to call from sync code paths; every call is best-effort and the
    function never raises. Keys match the frontend `RuntimeContext`
    TypeScript interface in frontend/src/app/diagnostics/diagnostics.service.ts.
    """
    ctx: dict[str, Any] = {
        "node_id": os.environ.get("NODE_ID", socket.gethostname()),
        "node_role": os.environ.get("NODE_ROLE", "primary"),
        "node_hostname": socket.gethostname(),
        "python_version": sys.version.split()[0],
        "embedding_model": getattr(settings, "EMBEDDING_MODEL", "unknown"),
    }

    # GPU — lightweight torch-only probe. No pynvml calls (those can block
    # waiting for the driver) and no NVIDIA-SMI subprocess spawn.
    try:  # noqa: SIM105 — explicit imports for readability
        import torch

        gpu_available = bool(torch.cuda.is_available())
        ctx["gpu_available"] = gpu_available
        ctx["cuda_version"] = torch.version.cuda if gpu_available else None
        ctx["gpu_name"] = torch.cuda.get_device_name(0) if gpu_available else None
    except Exception:  # noqa: BLE001 — probe must never fail the caller
        ctx["gpu_available"] = False
        ctx["cuda_version"] = None
        ctx["gpu_name"] = None

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


__all__ = ["snapshot"]
