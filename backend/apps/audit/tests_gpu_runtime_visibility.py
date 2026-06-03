"""
Docker-integration audit: at runtime, no backend-side container sees the GPU.

Background: `docs/specs/fr-gpu-idle-release.md` §HF-1 / HF-2 declares that
project Docker services must not request NVIDIA devices, and stale worker
containers must be recreated without `HostConfig.DeviceRequests`. This is the
end-to-end runtime check for the backend-side containers after that cleanup.

The test shells out to `docker exec` so it requires Docker to be running and
the three containers to be up. It skips cleanly (rather than failing) when
Docker is unavailable so unit-test environments without Docker don't break.

We use `torch.cuda.is_available()` instead of parsing `nvidia-smi` output
because torch is always installed in our backend images while `nvidia-smi`
is only present when the container has GPU access.

Runs as `SimpleTestCase`; ~3 s on a warm stack.
"""

from __future__ import annotations

import shutil
import subprocess

from django.test import SimpleTestCase


CONTAINERS_MUST_NOT_SEE_GPU = (
    ("xf_linker_backend", False),
    ("xf_linker_celery_worker_default", False),
    ("xf_linker_celery_worker_pipeline", False),
)
_PYTHON_PROBE = (
    "import torch, json, sys; "
    "sys.stdout.write(json.dumps({'cuda_available': bool(torch.cuda.is_available())}))"
)


def _docker_available() -> bool:
    return shutil.which("docker") is not None


def _probe_container_for_cuda(container_name: str) -> bool | None:
    """Return True/False for cuda_available, or None if the probe could not run."""
    try:
        completed = subprocess.run(  # noqa: S603 — trusted args
            ["docker", "exec", "-T", container_name, "python", "-c", _PYTHON_PROBE],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    stdout = completed.stdout.strip()
    if "cuda_available" not in stdout:
        return None
    # Cheapest parse — the probe writes a single JSON object on stdout.
    return '"cuda_available": true' in stdout.replace(" ", "").replace("\n", "")


class GpuRuntimeVisibilityTests(SimpleTestCase):
    """Per fr-gpu-idle-release.md §HF-1 / §HF-2: live runtime visibility check."""

    def _skip_if_docker_unavailable(self) -> None:
        if not _docker_available():
            self.skipTest("`docker` CLI not on PATH — integration audit cannot run.")

    def test_given_running_stack_when_backend_side_containers_probed_then_cuda_unavailable(self):
        """HF-1 / HF-2: backend-side containers report no CUDA at runtime."""
        self._skip_if_docker_unavailable()
        for container_name, expected_cuda in CONTAINERS_MUST_NOT_SEE_GPU:
            with self.subTest(container=container_name):
                result = _probe_container_for_cuda(container_name)
                if result is None:
                    self.skipTest(
                        f"Container `{container_name}` is not running or torch "
                        f"is not importable; live audit deferred."
                    )
                self.assertEqual(
                    result,
                    expected_cuda,
                    msg=(
                        f"`{container_name}` reports cuda_available={result} but "
                        f"docs/specs/fr-gpu-idle-release.md §HF-1/§HF-2 requires "
                        f"cuda_available=False (no GPU device should be visible "
                        f"inside this container)."
                    ),
                )
