# MSI Docker Removal And Dell/Mint Cutover

[SPEC FRESHNESS: reviewed_at=2026-06-12 next_review=2026-07-12]

## Source Types

- technical_doc: PostgreSQL documentation for `pg_dump`, `pg_restore`, and dump verification.
- technical_doc: Kubernetes documentation for persistent volumes, jobs, and `kubectl`.
- technical_doc: Docker documentation for Docker Desktop, images, volumes, contexts, and uninstall behavior.
- technical_doc: Bazel remote caching documentation and BuildBuddy remote cache documentation.

## Behavior

Given MSI still has Docker volumes and images, when the cutover starts, then the repo-owned helper must classify every named volume and image before a destructive step is allowed.

Given a volume contains PostgreSQL, media, or observability history, when the inventory is classified, then the helper must mark it `must-copy` and name the destination class.

Given a volume only contains build output, tool cache, package cache, or static output, when the inventory is classified, then the helper may mark it `discard`.

Given a Docker image can be rebuilt from the repo or pulled from a registry, when the inventory is classified, then the helper must mark it `rebuild-on-dell-or-mint` or `pull-by-digest` instead of exporting it from MSI.

Given an image or volume is unknown, when the inventory is classified, then the helper must mark it `manual-review`.

Given the proof file does not show verified database, media, observability, GlitchTip, remote checks, rollback data, and manual review, when MSI Docker removal is requested, then the removal helper must refuse to run.

Given the proof file is complete and the operator gives the exact confirmation phrase, when MSI Docker removal is run with the execution flag, then the helper may remove Docker Desktop, Docker WSL data, and user Docker contexts from MSI.

## Design

MSI becomes a pure development computer. Pure development means it keeps the local Git repo, editor, SSH, and `kubectl`, which is the Kubernetes command-line tool. It does not keep Docker Desktop, local Docker images, local Docker volumes, or local build cache.

Dell is authoritative for fast work: app hot data, PostgreSQL, tests, mutation testing, and hot observability data. Mint is authoritative for slow storage: source snapshots, BuildBuddy cache, registry mirror, cold observability archives, merged reports, and long-retention artifacts.

The current scripts are transition wrappers. They should keep routing work away from MSI while Bazel and Kubernetes take over. Bazel is the build system that chooses exact affected targets. BuildBuddy is the remote cache and build result service. Kubernetes is the cluster runtime that runs the app and helper jobs.

The final MSI Docker removal step is intentionally separate from inventory and proof generation. The helper has a dry-run default, a proof-file check, and an exact confirmation phrase because it can delete local container data.

## Test Plan

- `python -m pytest -q scripts/test_msi_docker_cutover.py`
- `python -m py_compile scripts/msi_docker_cutover.py scripts/test_msi_docker_cutover.py`

