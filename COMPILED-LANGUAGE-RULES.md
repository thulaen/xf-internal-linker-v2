# Compiled-Language Rules

Compiled languages must work through Docker without manual host builds.

## Required Path

- Use `docker compose run --rm compiled-tools ...` for compiled-language checks.
- Use `scripts/build-native-extensions.ps1` for runtime C++ Python extensions.
- Do not require host Visual Studio, host Go, host CMake, or host compiler tools.
- Do not write build output into repo-tracked folders.

## Runtime Artifacts

- Runtime artifacts live in the Docker volume mounted at `/opt/xf/compiled`.
- Temporary build work lives under `/tmp/xf-build`.
- Backend, Celery workers, and Celery Beat must run `scripts/ensure_compiled_artifacts.py`
  before starting.
- The artifact manifest must decide whether to rebuild from source hashes.
- A missing, stale, or failed hot-path artifact is a hard failure.

## Future Languages

Any new compiled language must add:

- Source file patterns.
- Runtime artifact path under `/opt/xf/compiled`.
- Temporary build path under `/tmp/xf-build`.
- Docker-only test command.
- Docker-only coverage command with the repo target.
- Docker-only mutation or fuzz command when the language supports it.

Generated binaries, coverage files, build folders, and crash reproducers must not be committed.
