"""Embedding provider abstraction (plan Part 1).

Resolves the active provider from ``AppSetting("embedding.provider")`` at call
time, returning a cached provider instance. All providers implement the
``EmbeddingProvider`` Protocol in ``base.py`` so the hot loop in
``embeddings.py`` stays provider-agnostic: it calls ``provider.embed(batch)``
and receives an ``EmbedResult`` regardless of backend.

Supported providers:
    local   -> LocalBGEProvider    (sentence-transformers, GPU/CPU)
    openai  -> OpenAIProvider      (text-embedding-3-small/large via API)
    gemini  -> GeminiProvider      (text-embedding-004 via google-genai)
"""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

from .base import EmbedResult, EmbeddingProvider
from .errors import (
    AuthenticationError,
    BudgetExceededError,
    ProviderError,
    RateLimitError,
)

if TYPE_CHECKING:  # pragma: no cover - import cost at runtime avoided
    pass

logger = logging.getLogger(__name__)

_provider_cache: dict[str, EmbeddingProvider] = {}
_cache_lock = threading.Lock()


def _read_provider_name() -> str:
    """Resolve the active provider name from AppSetting; default ``local``."""
    try:
        from apps.core.models import AppSetting

        setting = AppSetting.objects.filter(key="embedding.provider").first()
        if setting and setting.value:
            return str(setting.value).strip().lower()
    except Exception:
        logger.debug(
            "AppSetting unavailable; using default provider 'local'", exc_info=True
        )
    return "local"


def get_provider(force_refresh: bool = False) -> EmbeddingProvider:
    """Return the active embedding provider, cached per (provider, signature).

    Thread-safe. Callers should call this once per batch, not once per item —
    the lookup is cheap but cache miss involves model / client instantiation.
    """
    name = _read_provider_name()
    if force_refresh:
        with _cache_lock:
            _provider_cache.pop(name, None)
    cached = _provider_cache.get(name)
    if cached is not None:
        return cached
    with _cache_lock:
        cached = _provider_cache.get(name)
        if cached is not None:
            return cached
        provider = _instantiate(name)
        _provider_cache[name] = provider
        return provider


def _instantiate(name: str) -> EmbeddingProvider:
    if name == "openai":
        from .openai_provider import OpenAIProvider

        return OpenAIProvider()
    if name == "gemini":
        from .gemini_provider import GeminiProvider

        return GeminiProvider()
    # default + unknown names fall back to local so a typo does not cost money
    if name != "local":
        logger.warning("Unknown embedding.provider=%r; falling back to local", name)
    from .local_bge import LocalBGEProvider

    return LocalBGEProvider()


def clear_cache() -> None:
    """Drop all cached providers (useful on AppSetting change or tests)."""
    with _cache_lock:
        _provider_cache.clear()


__all__ = [
    "AuthenticationError",
    "BudgetExceededError",
    "EmbedResult",
    "EmbeddingProvider",
    "ProviderError",
    "RateLimitError",
    "clear_cache",
    "get_provider",
]
