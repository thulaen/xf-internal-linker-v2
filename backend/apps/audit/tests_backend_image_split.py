"""
Static checks that prove the backend Docker image is properly split
into a lean runtime stage and a separate quality stage.

Tests parse backend/Dockerfile and docker-compose.yml as text — no
Docker build required.  They run red (fail) against the current monolithic
Dockerfile and go green once the runtime/quality split is in place.

BDD:
  Given the backend Dockerfile and docker-compose.yml
  When the quality stage and runtime stage rules are applied
  Then runtime does not contain quality-only tools
  And quality stage contains all required quality tools
  And all runtime compose services use the runtime image
"""

from __future__ import annotations

import re
from pathlib import Path
from unittest import TestCase

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
DOCKERFILE = REPO_ROOT / "backend" / "Dockerfile"
COMPOSE_FILE = REPO_ROOT / "docker-compose.yml"
QUALITY_SCRIPT = REPO_ROOT / "scripts" / "run-python-quality.sh"

# Packages that belong ONLY in the quality stage, never in runtime.
QUALITY_ONLY_PACKAGES = [
    "mutmut",
    "ruff",
    "bandit",
    "pip-audit",
    "safety",
    "pylint",
    "coverage",
    "pytest",
    "hypothesis",
]

# Compose services that must use the runtime image.
RUNTIME_SERVICES = [
    "backend",
    "celery-worker-default",
    "celery-worker-pipeline",
    "celery-beat",
]

RUNTIME_IMAGE = "xf-linker-backend-runtime:latest"
QUALITY_IMAGE = "xf-linker-backend-quality:latest"


def _split_dockerfile_stages(text: str) -> dict[str, str]:
    """Return {'go-tools': '...', 'runtime': '...', 'quality': '...'} stage blocks."""
    from_pattern = re.compile(r"^FROM\s+\S+(?:\s+AS\s+(\S+))?", re.MULTILINE)
    matches = list(from_pattern.finditer(text))
    stages: dict[str, str] = {}
    for i, m in enumerate(matches):
        name = m.group(1) or f"stage_{i}"
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        stages[name] = text[m.start():end]
    return stages


class TestDockerfileHasNamedStages(TestCase):
    """The Dockerfile must declare named runtime and quality stages."""

    def setUp(self) -> None:
        self.content = DOCKERFILE.read_text(encoding="utf-8")
        self.stages = _split_dockerfile_stages(self.content)

    def test_runtime_stage_exists(self) -> None:
        self.assertIn("runtime", self.stages,
                      "Dockerfile must have 'FROM ... AS runtime' stage")

    def test_quality_stage_exists(self) -> None:
        self.assertIn("quality", self.stages,
                      "Dockerfile must have 'FROM runtime AS quality' stage")

    def test_quality_stage_extends_runtime(self) -> None:
        quality_block = self.stages.get("quality", "")
        self.assertIn("FROM runtime AS quality", quality_block,
                      "quality stage must extend runtime: 'FROM runtime AS quality'")

    def test_go_tools_stage_exists(self) -> None:
        self.assertIn("go-tools", self.stages,
                      "Dockerfile must retain 'FROM golang:... AS go-tools' stage")


class TestRuntimeStageHasNoQualityTools(TestCase):
    """Quality-only packages must not appear in the runtime stage."""

    def setUp(self) -> None:
        content = DOCKERFILE.read_text(encoding="utf-8")
        stages = _split_dockerfile_stages(content)
        self.runtime_block = stages.get("runtime", "")

    def test_quality_packages_absent_from_runtime(self) -> None:
        for pkg in QUALITY_ONLY_PACKAGES:
            with self.subTest(pkg=pkg):
                self.assertNotIn(
                    pkg,
                    self.runtime_block,
                    f"Quality-only package '{pkg}' must not be installed in the runtime stage. "
                    "Move it to the quality stage.",
                )

    def test_go_toolchain_absent_from_runtime(self) -> None:
        self.assertNotIn(
            "COPY --from=go-tools /usr/local/go",
            self.runtime_block,
            "Go toolchain must not be copied into the runtime stage — quality stage only.",
        )

    def test_go_mutesting_absent_from_runtime(self) -> None:
        self.assertNotIn(
            "go-mutesting",
            self.runtime_block,
            "go-mutesting binary must not be installed in the runtime stage.",
        )

    def test_luarocks_installs_absent_from_runtime(self) -> None:
        self.assertNotIn(
            "install busted",
            self.runtime_block,
            "luarocks quality installs (busted, luacheck, ...) must not be in the runtime stage.",
        )


class TestQualityStageHasRequiredTools(TestCase):
    """The quality stage must install all required quality tools."""

    def setUp(self) -> None:
        content = DOCKERFILE.read_text(encoding="utf-8")
        stages = _split_dockerfile_stages(content)
        self.quality_block = stages.get("quality", "")

    def test_quality_packages_present(self) -> None:
        for pkg in QUALITY_ONLY_PACKAGES:
            with self.subTest(pkg=pkg):
                self.assertIn(
                    pkg,
                    self.quality_block,
                    f"Quality package '{pkg}' must be installed in the quality stage.",
                )

    def test_go_toolchain_present_in_quality(self) -> None:
        self.assertIn(
            "COPY --from=go-tools /usr/local/go",
            self.quality_block,
            "Go toolchain must be copied into the quality stage.",
        )

    def test_go_mutesting_present_in_quality(self) -> None:
        self.assertIn(
            "go-mutesting",
            self.quality_block,
            "go-mutesting binary must be present in the quality stage.",
        )

    def test_luarocks_installs_present_in_quality(self) -> None:
        self.assertIn(
            "install busted",
            self.quality_block,
            "Lua quality tools (busted, luacheck, ...) must be installed in the quality stage.",
        )

    def test_quality_stage_switches_back_to_appuser(self) -> None:
        self.assertIn(
            "USER appuser",
            self.quality_block,
            "quality stage must end with USER appuser (security: no root at runtime).",
        )


class TestComposeServicesUseRuntimeImage(TestCase):
    """Runtime compose services must reference xf-linker-backend-runtime:latest."""

    def setUp(self) -> None:
        self.compose = yaml.safe_load(COMPOSE_FILE.read_text(encoding="utf-8"))
        self.services = self.compose.get("services", {})

    def test_runtime_services_use_runtime_image(self) -> None:
        for svc in RUNTIME_SERVICES:
            with self.subTest(service=svc):
                image = self.services.get(svc, {}).get("image", "")
                self.assertEqual(
                    image,
                    RUNTIME_IMAGE,
                    f"Service '{svc}' must use '{RUNTIME_IMAGE}', found '{image}'.",
                )

    def test_backend_build_target_is_runtime(self) -> None:
        build = self.services.get("backend", {}).get("build", {})
        target = build.get("target", "")
        self.assertEqual(
            target,
            "runtime",
            f"backend build.target must be 'runtime', found '{target}'.",
        )

    def test_backend_quality_service_exists(self) -> None:
        self.assertIn(
            "backend-quality",
            self.services,
            "docker-compose.yml must have a 'backend-quality' service for quality runs.",
        )

    def test_backend_quality_has_profile(self) -> None:
        svc = self.services.get("backend-quality", {})
        profiles = svc.get("profiles", [])
        self.assertIn(
            "quality",
            profiles,
            "backend-quality service must have profiles: [quality].",
        )

    def test_backend_quality_uses_quality_image(self) -> None:
        image = self.services.get("backend-quality", {}).get("image", "")
        self.assertEqual(
            image,
            QUALITY_IMAGE,
            f"backend-quality must use '{QUALITY_IMAGE}', found '{image}'.",
        )


class TestQualityScriptUsesQualityService(TestCase):
    """run-python-quality.sh must invoke the backend-quality service, not backend."""

    def setUp(self) -> None:
        self.script = QUALITY_SCRIPT.read_text(encoding="utf-8")

    def test_quality_script_references_backend_quality(self) -> None:
        self.assertIn(
            "backend-quality",
            self.script,
            "run-python-quality.sh must invoke the 'backend-quality' service "
            "(which has quality tools) not the 'backend' runtime service.",
        )

    def test_quality_script_does_not_run_bare_backend_service(self) -> None:
        # Look for 'docker compose run ... backend ' (with trailing space/newline)
        # as the service argument — not as part of 'backend-quality'.
        bare_backend = re.search(
            r"docker compose\s.*?\bbackend\s",
            self.script,
            re.DOTALL,
        )
        if bare_backend:
            matched = bare_backend.group(0)
            self.assertNotIn(
                "backend ",
                matched.replace("backend-quality", "").replace("backend-quality", ""),
                "run-python-quality.sh must not invoke the bare 'backend' service "
                "for quality runs; use 'backend-quality' instead.",
            )
