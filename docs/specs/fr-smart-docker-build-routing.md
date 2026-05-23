# Smart Docker Build Routing

[SPEC FRESHNESS: reviewed_at=2026-05-23 next_review=2026-08-23]

[SPEC CITED: feature=smart-docker-build-routing kind=technical_doc id=docker-buildx-builders verified_at=2026-05-23]
[SPEC CITED: feature=smart-docker-build-routing kind=technical_doc id=docker-compose-build-cli verified_at=2026-05-23]
[SPEC CITED: feature=smart-docker-build-routing kind=technical_doc id=docker-desktop-gpu-wsl2 verified_at=2026-05-23]
[SPEC CITED: feature=smart-docker-build-routing kind=technical_doc id=docker-buildkit-cdi verified_at=2026-05-23]

## Purpose

Docker builds must not silently fill the Windows drive. General builds use the Mint helper builder. GPU builds use the local Windows/WSL builder because GPU runtime access must be proven on the machine that owns the GPU. Docker Build Cloud is not used by default because it can create paid usage.

## Sources Of Truth

- Docker Buildx builders: https://docs.docker.com/build/builders/
- Docker Compose build command: https://docs.docker.com/reference/cli/docker/compose/build/
- Docker Desktop GPU support on Windows with WSL2: https://docs.docker.com/desktop/features/gpu/
- Docker BuildKit Container Device Interface for GPU-aware builders: https://docs.docker.com/build/building/cdi/

## Behavior

Given a build target is not marked as GPU-only, when the smart build helper runs, then it selects the `mint` builder before running `docker compose build`.

Given a build target is marked as GPU-only, when the smart build helper runs, then it selects the local `desktop-linux` builder and checks local GPU access before running the build.

Given the Mint builder is unavailable for a non-GPU build, when the smart build helper runs, then it fails with a plain-English message and does not fall back to Windows or Docker Build Cloud.

Given a future agent reads the build rules, when they look for the old timed auto-switcher, then the docs point to the repo-owned smart build helper instead of `auto-select-builder.ps1`.

## Routing Defaults

- General builder: `mint`
- GPU builder: `desktop-linux`
- Fallback policy: fail closed
- Docker Build Cloud: disabled by default

## Verification

The regression tests exercise routing without running a real build. The live build command is still a normal Docker command, but the builder choice happens first and is visible in the helper output.

## Global Docker context stays `desktop-linux` (Phase H)

`scripts/smart_build.py` uses `docker --context <builder>` per call. This routes a single docker invocation to the named engine without mutating global `docker context use` state. The global Docker context stays whatever it was before the helper ran.

The intended global context is `desktop-linux`. WSL2 on Windows exposes the local NVIDIA GPU through the Docker Desktop Linux engine; switching the global context to `mint` would hide the GPU from any non-helper command that runs against the default context.

To keep the global context stable across PowerShell sessions, add the following to the user's PowerShell `$PROFILE` (both `Microsoft.PowerShell_profile.ps1` and `profile.ps1` under `OneDrive\Documents\PowerShell\`):

```powershell
$env:DOCKER_CONTEXT = 'desktop-linux'
```

The `DOCKER_CONTEXT` environment variable takes precedence over the `currentContext` field in `~/.docker/config.json` per the Docker CLI documentation. Every new PowerShell session then forces `desktop-linux` as the engine even if something earlier flipped the persistent default.

`.env.example` carries the same `DOCKER_CONTEXT=desktop-linux` line so an operator who imports it gets the right default in shells that read `.env`.

## Agents-must-use-smart_build rule (Phase M.1)

Every agent (Claude, Codex, Gemini, Antigravity, and every future agent) MUST invoke `scripts/build-smart.ps1` (PowerShell) or `python scripts/smart_build.py` (Python) rather than running `docker compose build` / `docker buildx build` / `docker build` directly. The rule is mirrored in `CLAUDE.md` / `AGENTS.md` / `CODEX.md` / `GEMINI.md` under the "Pattern B Build Routing" section. Running plain `docker compose build` bypasses the routing and risks building heavy images on the Windows local disk.
