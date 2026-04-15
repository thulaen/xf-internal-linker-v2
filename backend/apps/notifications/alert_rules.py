"""
Named operator-alert rules (plan item 10).

Central place to emit the four "system decided something on your behalf" alerts
from plan `.claude/plans/mossy-gliding-deer.md`:

  (a) Performance mode reverted automatically    -> Celery-beat auto-revert (items 12-14)
  (b) Helper node went offline                    -> heartbeat expiry (future)
  (c) Checkpoint retention hit the 2 GB cap       -> checkpoint pruner (item 19)
  (d) GPU fell back to CPU                        -> runtime switcher / CUDA warmup (items 15, 23)

All four flow through the existing ``emit_operator_alert`` in ``services.py`` so
frontend dedupe, cooldown, WebSocket fan-out, and the alert detail route keep
working untouched.  Each rule has a stable ``dedupe_key`` so repeated firings
inside the cooldown window increment ``occurrence_count`` instead of spamming
new rows.
"""

from __future__ import annotations

import logging
from typing import Optional

from .models import OperatorAlert
from .services import emit_operator_alert

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# (a) Performance mode reverted automatically
# --------------------------------------------------------------------------- #


def alert_performance_mode_reverted(
    *,
    from_mode: str,
    to_mode: str,
    reason: str,
) -> Optional[OperatorAlert]:
    """Fired when the Celery-beat auto-revert task changes the performance mode.

    ``reason`` should be a short human phrase such as "tonight's window ended"
    or "activity detected after Until-I-come-back was set".
    """
    try:
        return emit_operator_alert(
            event_type="system.perf_mode_reverted",
            severity=OperatorAlert.SEVERITY_WARNING,
            title=f"Performance mode reverted to {to_mode.title()}",
            message=(
                f"The system automatically switched from {from_mode.title()} "
                f"to {to_mode.title()} because {reason}."
            ),
            source_area=OperatorAlert.AREA_SYSTEM,
            dedupe_key=f"perf_mode_reverted:{from_mode}:{to_mode}",
            related_route="/dashboard",
            payload={"from_mode": from_mode, "to_mode": to_mode, "reason": reason},
            cooldown_seconds=900,  # 15 min
        )
    except Exception:
        logger.warning("Failed to emit perf-mode-reverted alert", exc_info=True)
        return None


# --------------------------------------------------------------------------- #
# (b) Helper node went offline
# --------------------------------------------------------------------------- #


def alert_helper_node_offline(
    *,
    helper_id: str,
    helper_name: str,
    last_seen_seconds_ago: int,
) -> Optional[OperatorAlert]:
    """Fired when a HelperNode heartbeat is past its expiry window."""
    try:
        return emit_operator_alert(
            event_type="system.helper_offline",
            severity=OperatorAlert.SEVERITY_WARNING,
            title=f"Helper node offline: {helper_name}",
            message=(
                f"Helper node '{helper_name}' has not checked in for "
                f"{last_seen_seconds_ago} seconds. Work it owned has been "
                f"marked resumable and will be retried on another worker."
            ),
            source_area=OperatorAlert.AREA_SYSTEM,
            dedupe_key=f"helper_offline:{helper_id}",
            related_route="/settings",  # future: /settings#helpers
            related_object_type="HelperNode",
            related_object_id=str(helper_id),
            payload={
                "helper_id": str(helper_id),
                "helper_name": helper_name,
                "last_seen_seconds_ago": last_seen_seconds_ago,
            },
            cooldown_seconds=1800,  # 30 min — per-helper
        )
    except Exception:
        logger.warning("Failed to emit helper-offline alert", exc_info=True)
        return None


# --------------------------------------------------------------------------- #
# (c) Checkpoint retention hit the 2 GB cap
# --------------------------------------------------------------------------- #


def alert_checkpoint_cap_hit(
    *,
    used_mb: int,
    cap_mb: int,
    pruned_mb: int,
) -> Optional[OperatorAlert]:
    """Fired when the checkpoint pruner removes data because the cap was hit.

    A cooldown of 6 hours keeps this from spamming on disks that linger near
    the cap.
    """
    try:
        return emit_operator_alert(
            event_type="system.checkpoint_cap_hit",
            severity=OperatorAlert.SEVERITY_INFO,
            title="Checkpoint storage cap reached",
            message=(
                f"Checkpoint scratch grew to {used_mb} MB, past the {cap_mb} MB "
                f"cap. Pruned {pruned_mb} MB of oldest completed checkpoints first."
            ),
            source_area=OperatorAlert.AREA_SYSTEM,
            dedupe_key="checkpoint_cap_hit",
            related_route="/health",  # future: /health#disk
            payload={"used_mb": used_mb, "cap_mb": cap_mb, "pruned_mb": pruned_mb},
            cooldown_seconds=21600,  # 6 hours
        )
    except Exception:
        logger.warning("Failed to emit checkpoint-cap-hit alert", exc_info=True)
        return None


# --------------------------------------------------------------------------- #
# (d) GPU fell back to CPU
# --------------------------------------------------------------------------- #


def alert_gpu_fallback_to_cpu(
    *,
    reason: str,
    vram_required_mb: int | None = None,
) -> Optional[OperatorAlert]:
    """Fired when High Performance mode was requested but the system dropped to CPU.

    Reasons observed in the wild:
      - "CUDA not available" (driver / hardware issue)
      - "torch not installed" (container / dep issue)
      - "GPU temperature at ceiling" (thermal guard — see PERFORMANCE.md §6)
      - "VRAM exhausted"
    """
    try:
        return emit_operator_alert(
            event_type="system.gpu_fallback",
            severity=OperatorAlert.SEVERITY_WARNING,
            title="GPU unavailable - fell back to CPU",
            message=(
                f"High Performance mode asked for GPU but the system dropped to CPU. "
                f"Reason: {reason}. Jobs will still run, just slower."
            ),
            source_area=OperatorAlert.AREA_SYSTEM,
            dedupe_key=f"gpu_fallback:{reason}",
            related_route="/health",  # future: /health#runtime
            payload={"reason": reason, "vram_required_mb": vram_required_mb},
            cooldown_seconds=3600,  # 1 hour
        )
    except Exception:
        logger.warning("Failed to emit gpu-fallback alert", exc_info=True)
        return None
