"""Slice 1.6 — shared helpers for sidecar Python clients.

Each owning Django module has its own private `_sidecars/` package
(apps.auto_issues._sidecars, apps.ops_feed._sidecars, etc.) holding the
typed clients for the sidecar services it consumes. The clients re-use the
helpers in this package so the socket path, channel options, and lazy
stub loading live in exactly one place.

NOT a Django app — pure-Python helpers. Importable without AppConfig.
"""
