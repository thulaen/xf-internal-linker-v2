"""
Hard CI gate that fails if backend domain code (modules that run in the
non-GPU containers) imports `torch.cuda` or calls `.cuda()` on tensors.

Background: `docs/specs/fr-gpu-idle-release.md` §HF-5 / HF-6 declares that
the `backend` HTTP container and the `celery-worker-default` Celery worker
must not exercise any GPU code path. The compose-level audit
(`tests_compose_gpu_discipline.py`) makes the GPU unreachable from those
containers, but a developer could still write a `torch.cuda` import that
would either crash at runtime in the non-GPU container OR silently fall back
to CPU and hide the architectural violation. This audit catches the import at
review time so the fix is a local edit, not a Sentry alert.

The audit scans backend domain modules that are loaded inside the `backend`
HTTP container or are routed to the Celery `default` queue. It does NOT scan
`apps/pipeline/` because that module is the legitimate home of GPU code and
runs only inside `celery-worker-pipeline`.

The test uses Python's `ast` module — no actual imports happen, so missing
runtime deps don't affect the result. Runs as `SimpleTestCase` in <500 ms.
"""

from __future__ import annotations

import ast
from pathlib import Path

from django.test import SimpleTestCase

from apps.audit.tests_glitchtip_compose_integrity import REPO_ROOT


# Backend domain code that loads in non-GPU containers. The pipeline module
# is intentionally excluded — it is the GPU code path's home.
NON_GPU_BACKEND_DOMAINS = (
    "backend/apps/api",
    "backend/apps/audit",
    "backend/apps/auto_issues",
    "backend/apps/core",
    "backend/apps/health",
    "backend/apps/observability",
    "backend/apps/paper_trail",
    "backend/apps/realtime",
)


_FORBIDDEN_IMPORT_PREFIXES = ("torch.cuda",)
_FORBIDDEN_CALL_NAMES = frozenset({"cuda"})
_FORBIDDEN_KEYWORD_VALUES = frozenset({"cuda"})


def _scan_python_file(path: Path) -> list[str]:
    """Return a list of human-readable violations found in this file.

    Each violation is a string like
    `apps/foo/bar.py:42 imports torch.cuda` — useful for the assertion
    message so the failing line number is named.
    """
    source = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return []

    violations: list[str] = []
    relative = path.relative_to(REPO_ROOT)

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith(_FORBIDDEN_IMPORT_PREFIXES):
                    violations.append(
                        f"{relative}:{node.lineno} imports `{alias.name}` "
                        f"— GPU code is forbidden in non-GPU backend domain code."
                    )
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module.startswith(_FORBIDDEN_IMPORT_PREFIXES):
                violations.append(
                    f"{relative}:{node.lineno} imports from `{module}` "
                    f"— GPU code is forbidden in non-GPU backend domain code."
                )
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute) and node.func.attr in _FORBIDDEN_CALL_NAMES:
                violations.append(
                    f"{relative}:{node.lineno} calls `.{node.func.attr}()` "
                    f"— `.cuda()` is forbidden in non-GPU backend domain code."
                )
            for keyword in node.keywords:
                if keyword.arg == "device" and isinstance(keyword.value, ast.Constant):
                    if str(keyword.value.value).lower() in _FORBIDDEN_KEYWORD_VALUES:
                        violations.append(
                            f"{relative}:{node.lineno} passes `device='cuda'` "
                            f"— GPU device pinning is forbidden in non-GPU backend domain code."
                        )

    return violations


class GpuUsagePerServiceTests(SimpleTestCase):
    """Per fr-gpu-idle-release.md §HF-5 / HF-6: no GPU code in non-GPU domains."""

    def test_given_backend_domains_when_walked_then_no_torch_cuda_imports_or_calls(self):
        """HF-5 / HF-6: every Python file in the non-GPU domain list must be GPU-free."""
        violations: list[str] = []
        for domain in NON_GPU_BACKEND_DOMAINS:
            root = REPO_ROOT / domain
            if not root.exists():
                continue
            for path in root.rglob("*.py"):
                # Skip generated stubs and migrations — the audit targets
                # human-authored domain code, not auto-generated artifacts.
                if "/migrations/" in str(path).replace("\\", "/"):
                    continue
                if path.name.endswith("_pb2.py") or path.name.endswith("_pb2_grpc.py"):
                    continue
                violations.extend(_scan_python_file(path))

        self.assertEqual(
            violations,
            [],
            msg=(
                "GPU code path detected in non-GPU backend domain modules. Per "
                "docs/specs/fr-gpu-idle-release.md §HF-5 and §HF-6, these "
                "imports/calls must move to `backend/apps/pipeline/` (the only "
                "module that loads inside celery-worker-pipeline):\n  - "
                + "\n  - ".join(violations)
            ),
        )
