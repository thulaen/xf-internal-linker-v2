"""Central C++ extension loader with ErrorLog integration.

Every C++ extension import in the pipeline should go through this module.
If an extension fails to load, this logs the failure to ErrorLog (visible in
the dashboard) and to the health system, rather than silently falling back.

Usage:
    from apps.pipeline.services.ext_loader import load_extension

    scoring_ext = load_extension("scoring", "calculate_composite_scores_full_batch")
    if scoring_ext is not None:
        scoring_ext.calculate_composite_scores_full_batch(...)
"""

from __future__ import annotations

import importlib
import logging
import traceback
from typing import Any

from django.conf import settings

logger = logging.getLogger(__name__)


def load_extension(
    module_name: str,
    expected_attr: str | None = None,
    *,
    critical: bool = False,
) -> Any | None:
    """Import a C++ pybind11 extension and log failures to ErrorLog.

    Args:
        module_name: Name of the extension (e.g. "scoring", "simsearch").
        expected_attr: If set, verify this callable exists on the module.
        critical: If True and USE_NATIVE_EXTENSIONS is True, raise instead
                  of returning None.

    Returns:
        The imported module, or None if import failed and critical=False.

    Raises:
        RuntimeError: If critical=True, USE_NATIVE_EXTENSIONS=True, and
                      the extension could not be loaded.
    """
    dotted = f"extensions.{module_name}"
    use_native = getattr(settings, "USE_NATIVE_EXTENSIONS", True)

    try:
        module = importlib.import_module(dotted)
    except ImportError as exc:
        msg = (
            f"C++ extension '{module_name}' failed to import: {exc}. "
            f"Run: cd backend/extensions && pip install -e ."
        )
        logger.warning(msg)
        _log_to_errorlog(module_name, "import", msg, exc)

        if use_native and critical:
            raise RuntimeError(msg) from exc
        return None

    if expected_attr and not hasattr(module, expected_attr):
        msg = (
            f"C++ extension '{module_name}' loaded but missing "
            f"expected callable '{expected_attr}'."
        )
        logger.warning(msg)
        _log_to_errorlog(module_name, "missing_attr", msg)

        if use_native and critical:
            raise RuntimeError(msg)
        return None

    return module


def _log_to_errorlog(
    module_name: str,
    step: str,
    message: str,
    exc: BaseException | None = None,
) -> None:
    """Write a C++ extension failure to the ErrorLog table.

    This makes extension failures visible in the dashboard Error Log tab,
    alongside job failures from Celery tasks.
    """
    try:
        from apps.audit.models import ErrorLog

        ErrorLog.objects.create(
            job_type="cpp_extension",
            step=f"{step}_{module_name}",
            error_message=message,
            raw_exception=traceback.format_exc() if exc else "",
            why=(
                f"The compiled C++ extension '{module_name}' could not be loaded. "
                f"This means the affected pipeline stage is either using a slow Python "
                f"fallback (50-100x slower) or is disabled entirely. "
                f"To fix: rebuild extensions with 'cd backend/extensions && pip install -e .'"
            ),
        )
    except Exception:
        # ErrorLog itself may not be available during early startup or tests.
        pass
