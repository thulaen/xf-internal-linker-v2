# Compiled-Language Rules

Compiled languages must work through Docker without manual host builds.

## Required Path

- Use the running `compiled-tools` container for compiled-language checks:
  `docker compose exec -T compiled-tools ...`.
- If the tool container is not running yet, start it with `docker compose up -d compiled-tools`.
- Use `scripts/build-native-extensions.ps1` for runtime C++ Python extensions.
- Do not require host Visual Studio, host Go, host CMake, or host compiler tools.
- Do not write build output into repo-tracked folders.

## Shared Dynamic Libraries First

- Before adding a compiled custom library, search the existing C++, Go, Python, and
  TypeScript shared modules for a reusable path.
- A dynamic library is a shared compiled file loaded at runtime. In the Linux Docker
  stack this usually means a `.so` file.
- New compiled runtime code must be built as a dynamic library unless the platform
  or toolchain cannot support it. If dynamic loading is impossible, write the reason
  in the standards marker and handoff entry before shipping the fallback.
- Reuse an existing runtime library when it already owns the job. Do not create a
  second private library just to avoid a small refactor.
- All dynamic libraries must go through the Docker-managed artifact store described
  below, so the app has one verified copy instead of duplicate binaries.

## Runtime Artifacts

- Runtime artifacts live in the Docker volume mounted at `/opt/xf/compiled`.
- The protected store is content-addressed:
  - `/opt/xf/compiled/store/<sha256>` keeps one copy of each compiled output.
  - `/opt/xf/compiled/active/` keeps the runtime files that Python or future Go services load.
  - `/opt/xf/compiled/manifest.json` maps source hash, artifact hash, language, module,
    build command, active path, and last verification time.
- Temporary build work lives under `/tmp/xf-build`.
- Backend, Celery workers, and Celery Beat must run `scripts/ensure_compiled_artifacts.py`
  before starting.
- The artifact manifest must decide whether to rebuild from source hashes.
- A missing, stale, or failed hot-path artifact is a hard failure.
- C++ runtime extensions build into `/tmp/xf-build/<build-id>` first. The script hashes the
  `.so` files, imports required modules from a staging path, and only then activates them.
- Future Go modules follow the same Docker-only path: detect `go.mod`, build runtime outputs
  in `/tmp/xf-build`, hash outputs into the shared store, and activate verified files under
  `/opt/xf/compiled/active/go`. If no Go modules exist, record `no-go-modules`; do not create
  fake artifacts.
- Keep the previous active C++ extension set for one rollback window. It must point at the
  same store files through hard links or copied files, not duplicate untracked output folders.

## Future Languages

Any new compiled language must add:

- Source file patterns.
- Runtime artifact path under `/opt/xf/compiled`.
- Temporary build path under `/tmp/xf-build`.
- Docker-only test command.
- Docker-only coverage command with the repo target.
- Docker-only mutation or fuzz command when the language supports it.
- Docker-only lint or static-analysis command.
- Docker-only benchmark command for hot paths.
- Tool-readiness check in `scripts/run-tool-readiness.sh`.
- Pre-commit or pre-push wiring so changed files in the new language are found.
- Shared Docker cache volumes for tool caches, with matching entries in
  `config/protected-data-stores.json`.

Generated binaries, coverage files, build folders, and crash reproducers must not be committed.

## Operator Commands

- `python /repo/scripts/ensure_compiled_artifacts.py --check` builds or verifies active artifacts.
- `python /repo/scripts/ensure_compiled_artifacts.py --json` prints the manifest for agents.
- `python /repo/scripts/ensure_compiled_artifacts.py --prune-stale` deletes stale store files
  after retention and removes disposable scratch folders under `/tmp/xf-build`.
- `python /repo/scripts/ensure_compiled_artifacts.py --force` rebuilds safely without deleting
  the current active artifacts until verification passes.

Cleanup must refuse `/opt/xf/compiled`, Docker volumes, PostgreSQL, Redis, media, backups,
observability data, future QuestDB, future SQLite registry data, and Apache AGE data inside
PostgreSQL.
