"""Dependency security pin contract for Docker backend builds."""

from __future__ import annotations

from pathlib import Path

from django.test import SimpleTestCase


REPO_ROOT = Path(__file__).resolve().parents[2]
PROD_REQUIREMENTS = REPO_ROOT / "requirements.txt"
DEV_REQUIREMENTS = REPO_ROOT / "requirements-dev.txt"
BACKEND_DOCKERFILE = REPO_ROOT / "Dockerfile"


EXPECTED_PROD_PINS = {
    "Django==5.2.14",
    "grpcio==1.73.1",
    "grpcio-tools==1.73.1",
    "nltk==3.9.4",
    "opentelemetry-api==1.41.0",
    "opentelemetry-sdk==1.41.0",
    "opentelemetry-exporter-otlp-proto-http==1.41.0",
    "opentelemetry-instrumentation-django==0.62b0",
    "protobuf==6.33.5",
    "setuptools==78.1.1",
    "memray==1.19.2",
    "paramiko==4.0.0",
    "markdown==3.8.1",
    "mcp==1.23.0",
}

EXPECTED_DEV_PINS = {
    "pytest==9.0.3",
    "pytest-asyncio==1.3.0",
}

FORBIDDEN_REQUIREMENT_TEXT = {
    "Django==5.2.13",
    "nltk==3.9.1",
    "setuptools<70",
    "memray==1.14.0",
    "paramiko==3.5.0",
    "markdown==3.7",
    "mcp==1.1.2",
    "pytest==8.3.4",
    "pytest-asyncio==0.25.0",
}


def _requirements_lines(path: Path) -> set[str]:
    return {
        line.split("#", 1)[0].strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.split("#", 1)[0].strip()
    }


class DependencySecurityPinsTests(SimpleTestCase):
    def test_backend_requirements_use_security_upgrade_pins(self) -> None:
        prod_lines = _requirements_lines(PROD_REQUIREMENTS)
        dev_lines = _requirements_lines(DEV_REQUIREMENTS)

        self.assertTrue(EXPECTED_PROD_PINS <= prod_lines)
        self.assertTrue(EXPECTED_DEV_PINS <= dev_lines)

    def test_vulnerable_requirement_pins_are_removed(self) -> None:
        combined_text = "\n".join(
            (
                PROD_REQUIREMENTS.read_text(encoding="utf-8"),
                DEV_REQUIREMENTS.read_text(encoding="utf-8"),
                BACKEND_DOCKERFILE.read_text(encoding="utf-8"),
            )
        )

        for forbidden in FORBIDDEN_REQUIREMENT_TEXT:
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, combined_text)
