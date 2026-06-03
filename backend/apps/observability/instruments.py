from __future__ import annotations

from contextlib import contextmanager
import logging
import time
from collections.abc import Iterator
from typing import Any

from apps.observability.api import get_metric

logger = logging.getLogger(__name__)


def safe_inc(metric: Any, amount: float = 1.0, **labels: str) -> None:
    _call_metric(metric, "inc", amount, labels)


def safe_set(metric: Any, value: float, **labels: str) -> None:
    _call_metric(metric, "set", value, labels)


def safe_observe(metric: Any, value: float, **labels: str) -> None:
    _call_metric(metric, "observe", value, labels)


def observe_import_posts(source: str, *, count: int = 1) -> None:
    safe_inc(get_metric("xf_import_posts_total"), count, source=source)


def observe_import_failure(source: str, reason: str) -> None:
    safe_inc(get_metric("xf_import_failures_total"), source=source, reason=reason)


def observe_webhook_event(source: str, event_type: str) -> None:
    safe_inc(get_metric("xf_import_webhook_events_total"), source=source, event_type=event_type)


def observe_cleaning_result(raw_text: str, cleaned_text: str) -> None:
    safe_inc(get_metric("xf_cleaning_documents_total"))
    safe_observe(get_metric("xf_cleaning_text_length_chars"), len(raw_text or ""), phase="before")
    safe_observe(get_metric("xf_cleaning_text_length_chars"), len(cleaned_text or ""), phase="after")


def observe_cleaning_failure(reason: str) -> None:
    safe_inc(get_metric("xf_cleaning_failures_total"), reason=reason)


def observe_sentence_split(total_sentences: int, bad_sentences: int = 0) -> None:
    safe_observe(get_metric("xf_sentence_split_sentences_per_doc"), max(total_sentences, 0))
    ratio = 0.0 if total_sentences <= 0 else min(max(bad_sentences / total_sentences, 0.0), 1.0)
    safe_set(get_metric("xf_sentence_split_bad_sentence_ratio"), ratio)


@contextmanager
def observe_duration(metric_name: str, **labels: str) -> Iterator[None]:
    started = time.perf_counter()
    try:
        yield
    finally:
        safe_observe(get_metric(metric_name), time.perf_counter() - started, **labels)


def _call_metric(metric: Any, method: str, value: float | int, labels: dict[str, str]) -> None:
    try:
        target = metric.labels(**labels) if labels else metric
        getattr(target, method)(value)
    except Exception:
        logger.debug("observability metric emission failed", exc_info=True)
