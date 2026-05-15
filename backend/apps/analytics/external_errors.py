"""Helpers for classifying expected analytics provider failures."""

from __future__ import annotations


def is_google_api_client_error(exc: Exception) -> bool:
    """Return True for Google API client errors caused by provider responses."""
    try:
        from googleapiclient.errors import HttpError
    except ImportError:
        return False
    return isinstance(exc, HttpError)
