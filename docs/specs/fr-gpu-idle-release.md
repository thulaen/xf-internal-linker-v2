# Docker GPU Access Removal

[SPEC FRESHNESS: reviewed_at=2026-06-02 next_review=2026-09-02]

[SPEC CITED: feature=docker-gpu-access-removal kind=technical_doc id=docker-compose-devices verified_at=2026-05-26]
[SPEC CITED: feature=docker-gpu-access-removal kind=technical_doc id=docker-desktop-gpu verified_at=2026-05-26]
[SPEC CITED: feature=docker-gpu-access-removal kind=technical_doc id=docker-image-rm verified_at=2026-05-26]
[SPEC CITED: feature=docker-gpu-access-removal kind=standard id=iso-29119-3 verified_at=2026-05-26]

## Purpose

This is the first staged GPU cleanup slice. It removes project Docker access to
the laptop GPU while leaving the Windows NVIDIA driver installed. The larger
full-code GPU decommission remains separate: backend GPU code, frontend GPU UI,
old GPU specs, and FindBugs teardown all need heavier tests and data-preserving
cleanup.

## Sources Of Truth

- Docker Compose Deploy Specification, `devices`: https://docs.docker.com/reference/compose-file/deploy/#devices
- Docker Desktop GPU support: https://docs.docker.com/desktop/features/gpu/
- Docker image remove command: https://docs.docker.com/reference/cli/docker/image/rm/
- ISO/IEC/IEEE 29119-3:2021, test case documentation structure

Docker Compose grants device access per service through
`deploy.resources.reservations.devices`. If a service does not declare an NVIDIA
device reservation, Docker should not expose that GPU device to the container.
Docker Desktop's GPU support is a host feature; this project can stop using it
without uninstalling the Windows driver. Docker images can be removed safely
when no container uses them.

## Behavior

Given the production `docker-compose.yml` is parsed, when every service is
checked, then no service declares `driver: nvidia` or `capabilities: [gpu]`.

Given a stale running Celery worker was created before this cleanup, when only
`celery-worker-default` and `celery-worker-pipeline` are recreated, then
`HostConfig.DeviceRequests` is `null` for both containers.

Given a developer asks the smart-build helper for `--gpu`, `backend-gpu`,
`findbugs-gpu`, `llama-gpu`, or a CUDA build argument, when the helper runs, then
it exits with code `2` and explains that Docker GPU builds are disabled.

Given the Docker Desktop image `nvidia/cuda:12.8.0-base-ubuntu24.04` exists, when
no running or stopped container uses it, then this slice may remove only that
image. It must not run a broad Docker prune and must not delete protected
volumes.

## Requirements

### HF-1 — No Docker service requests GPU devices

Given `docker-compose.yml` is parsed; when every service's
`deploy.resources.reservations.devices` block is inspected; then the offender
list is empty for both NVIDIA driver entries and GPU capability entries.

### HF-2 — Stale worker containers are recreated narrowly

Given the current stack is running on Docker Desktop; when this slice applies
the compose change; then only `celery-worker-default` and
`celery-worker-pipeline` are recreated. The whole stack is not restarted.

### HF-3 — Smart-build rejects GPU build inputs

Given `scripts/smart_build.py` receives GPU-only inputs; when it evaluates the
request; then it fails closed before selecting a builder or running Docker.

### HF-4 — No broad disk cleanup

Given this slice is only about GPU access; when removing unused artifacts; then
only the confirmed-unused CUDA probe image may be removed. FindBugs volumes and
general Docker build cache are left for their own cleanup slices.

## Out Of Scope

- Uninstalling the Windows NVIDIA driver.
- Removing backend GPU code paths.
- Removing frontend GPU UI.
- Removing FindBugs volumes or database rows.
- Relaxing the K8S pre-flight latency target.

## Acceptance

This spec is accepted when:

- The compose audit test proves no service requests NVIDIA GPU access.
- The smart-build tests prove GPU flags, stale GPU targets, and CUDA build
  arguments are rejected.
- Live Docker verification shows `HostConfig.DeviceRequests` is `null` for
  `xf_linker_celery_worker_default` and `xf_linker_celery_worker_pipeline`.
- Docker Desktop no longer lists `nvidia/cuda:12.8.0-base-ubuntu24.04`.
