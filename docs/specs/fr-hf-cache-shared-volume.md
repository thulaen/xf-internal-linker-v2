# Hugging Face Cache Shared Volume

[SPEC FRESHNESS: reviewed_at=2026-05-19 next_review=2026-06-19]
[SPEC CITED: feature=hf-cache-shared-volume kind=technical_doc id=https://docs.docker.com/engine/storage/volumes/ verified_at=2026-05-19T16:52:00Z]
[SPEC CITED: feature=hf-cache-shared-volume kind=technical_doc id=https://docs.docker.com/reference/compose-file/services/#volumes verified_at=2026-05-19T16:52:00Z]
[SPEC CITED: feature=hf-cache-shared-volume kind=technical_doc id=https://huggingface.co/docs/huggingface_hub/en/guides/manage-cache verified_at=2026-05-19T16:52:00Z]

## Sources

- Docker Docs, "Volumes", https://docs.docker.com/engine/storage/volumes/
- Docker Docs, "Compose file services: volumes", https://docs.docker.com/reference/compose-file/services/#volumes
- Hugging Face Hub Docs, "Understand caching", https://huggingface.co/docs/huggingface_hub/en/guides/manage-cache

## Requirement

Given the Celery workers download Hugging Face model files during embedding and pipeline work.
When the worker containers restart or run in parallel.
Then they must share one Docker named volume at `/tmp/.cache` so the cache is stored once and survives container recreation.

## Design

- Declare one top-level Docker named volume: `hf_cache`.
- Mount `hf_cache:/tmp/.cache` into `celery-worker-default`, `celery-worker-pipeline`, and `celery-beat`.
- Do not mount the volume into `backend` in this slice.
- Add `hf_cache` to `config/protected-data-stores.json` because it stores runtime model files, not disposable tool downloads.

## Tests

- `apps/diagnostics/tests_compose_hf_cache_mounts.py` parses `docker-compose.yml` and proves the three Celery services mount `hf_cache:/tmp/.cache`.
- `apps/diagnostics/tests_protected_volumes.py` parses `config/protected-data-stores.json` and proves `hf_cache` is protected but not classified as disposable tool cache.
