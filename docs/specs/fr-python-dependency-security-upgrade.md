# Python Dependency Security Upgrade

[SPEC FRESHNESS: reviewed_at=2026-05-19 next_review=2026-06-19]
[SPEC CITED: feature=python-dependency-security-upgrade kind=technical_doc id=https://docs.djangoproject.com/en/5.2/releases/5.2.14/ verified_at=2026-05-20T00:59:00Z]
[SPEC CITED: feature=python-dependency-security-upgrade kind=technical_doc id=https://docs.pytest.org/en/latest/changelog.html verified_at=2026-05-20T00:59:00Z]

## Goal

Given the local pre-commit chain reports known Python package vulnerabilities, when dependency pins are changed, then the update must use versions that resolve cleanly together in Docker and keep the backend checks scoped to the changed dependency surface.

## Required Version Targets

- Django stays on the 5.2 long-term support line and moves from `5.2.13` to `5.2.14`.
- Python-Markdown moves from `3.7` to `3.8.1`.
- The Python MCP SDK moves from `1.1.2` to at least `1.23.0`.
- Memray moves from `1.14.0` to `1.19.2`.
- NLTK moves from `3.9.1` to `3.9.4`.
- Pytest moves from `8.3.4` to `9.0.3`.
- Setuptools moves from `<70` to `78.1.1`.
- Protobuf moves to a fixed line compatible with the selected gRPC tooling and OpenTelemetry pins.
- OpenTelemetry and gRPC pins move together when needed so protobuf is not forced back below the fixed version.
- Paramiko moves to a scanner-clean supported line while keeping SSH sync importable.

## Behavior

Given `backend/requirements.txt` and `backend/requirements-dev.txt` are the Docker build inputs, when the pins are updated, then a focused test must prove the old vulnerable pins are gone and the expected safe pins are present.

Given protobuf is transitive today, when protobuf is upgraded, then the requirements file must pin it directly and align `grpcio`, `grpcio-tools`, and OpenTelemetry packages so the pip resolver succeeds.

Given this is a dependency-only slice, when tests run, then they should target dependency import, resolver, Django startup, and the dependency-pin contract instead of unrelated application behavior.

## Sources

- Django 5.2.14 release notes, official Django documentation, reviewed 2026-05-19: https://docs.djangoproject.com/en/5.2/releases/5.2.14/
- pytest 9.0.3 changelog, official pytest documentation, reviewed 2026-05-19: https://docs.pytest.org/en/latest/changelog.html
- Python package index metadata for protobuf 6.33.5 and Paramiko supported releases, reviewed 2026-05-19: https://pypi.org/
- Local pre-commit safety and pip-audit output from 2026-05-19, which named the vulnerable packages and fixed versions.
