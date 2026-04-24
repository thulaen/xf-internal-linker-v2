"""Embedding-provider exception hierarchy (plan Part 1).

These are raised by provider ``embed()`` methods. The hot loop in
``embeddings.py`` catches them to trigger graceful fallback (plan Part 8b).

Keep exceptions cheap: they carry a message plus a machine-readable ``reason``
string. No heavy payloads.
"""

from __future__ import annotations


class ProviderError(Exception):
    """Base class for all embedding-provider errors."""

    reason: str = "provider_error"

    def __init__(self, message: str = "", *, reason: str | None = None) -> None:
        super().__init__(message)
        if reason is not None:
            self.reason = reason


class AuthenticationError(ProviderError):
    """API key missing or rejected by the provider."""

    reason = "auth"


class RateLimitError(ProviderError):
    """Provider returned 429 or equivalent."""

    reason = "rate_limit"


class BudgetExceededError(ProviderError):
    """Monthly budget cap hit; abort before incurring more spend."""

    reason = "budget"


class TransientProviderError(ProviderError):
    """Timeout / 5xx. Caller may retry with backoff."""

    reason = "transient"


class InvalidInputError(ProviderError):
    """Input text too long or otherwise rejected by the provider."""

    reason = "invalid_input"


__all__ = [
    "AuthenticationError",
    "BudgetExceededError",
    "InvalidInputError",
    "ProviderError",
    "RateLimitError",
    "TransientProviderError",
]
