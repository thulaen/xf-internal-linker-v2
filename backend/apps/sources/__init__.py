"""Source layer — shared helpers for pulling content from XenForo, WordPress, and JSONL uploads.

This module collects six small, orthogonal helpers that every outbound
integration needs:

- :mod:`token_bucket` — per-host paced request admission (Turner 1986).
- :mod:`backoff` — exponential backoff with AWS-full-jitter retry
  (Metcalfe & Boggs 1976; Brooker 2015).
- :mod:`circuit_breaker` — thin re-export of the mature breaker in
  ``apps.pipeline.services.circuit_breaker`` so outbound callers have a
  single dotted path without duplicating logic (Nygard 2007).
- :mod:`bloom_filter` — pre-fetch ID dedup (Bloom 1970).
- :mod:`hyperloglog` — near-constant-memory unique-cardinality sketch
  (Flajolet, Fusy, Gandouet, Meunier 2007).
- :mod:`conditional_get` — HTTP ``If-None-Match`` + ``If-Modified-Since``
  wrapper (RFC 7232).

Every helper is pure Python and dependency-free (no new pip packages
added). They all fit in <= 128 MB RAM + <= 256 MB disk and none
duplicates existing code (PR-C duplication audit).
"""
