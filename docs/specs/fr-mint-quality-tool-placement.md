# FR — Mint quality-tool placement

**Status:** Draft.
**Spec ID:** fr-mint-quality-tool-placement.

[SPEC FRESHNESS: reviewed_at=2026-06-02 next_review=2026-09-02]

## Plain-English Summary

Compiled-language tools, Haskell quality checks, and SonarQube are heavy quality
workloads. They should build and run on Linux Mint so Docker layers, Haskell
build output, SonarQube indexes, and scanner caches do not consume the Windows
C drive. Windows keeps the live control plane: Django, Redis, Postgres, Celery,
Lua advisor runtime, hooks, sessions, provider credentials, and AutoIssue /
PaperTrail database access.

## Source-Backed Rules

- Docker contexts select which Docker daemon receives commands, so scripts that
  start Mint-owned work must target Mint explicitly instead of changing the
  operator's default Windows Docker context.
- Docker Compose profiles keep optional services out of the default stack until
  the matching profile is requested.
- SonarQube runs as the quality server and exposes a web API that the Windows
  backend can ingest into AutoIssues.
- Haskell quality work uses Cabal inside the Docker-managed compiled-tools
  container; host-side Haskell installs are not required.

## BDD Contract

Given the operator starts the normal Windows stack,
when Docker Compose evaluates default services,
then compiled-tools, SonarQube, and sonar-autoscan do not start on Windows.

Given the operator starts Mint quality tools,
when `scripts/start-mint-quality-tools.ps1` runs,
then Mint builds and starts compiled-tools, SonarQube, and sonar-autoscan from
the Mint repo checkout.

Given AutoIssue ingestion runs on Windows,
when it needs SonarQube findings,
then it reaches SonarQube through `http://10.10.10.91:9000`.

Given sanity checks run after the move,
when `scripts/check-mint-quality-tools.ps1` runs,
then it checks compiled-tools, Haskell quality, SonarQube status, and Mint RAM.

## Citations

- [SPEC CITED: feature=fr-mint-quality-tool-placement kind=technical_doc id=docker-contexts verified_at=2026-05-26] Docker Docs, "Docker contexts," https://docs.docker.com/engine/manage-resources/contexts/
- [SPEC CITED: feature=fr-mint-quality-tool-placement kind=technical_doc id=docker-compose-profiles verified_at=2026-05-26] Docker Docs, "`docker compose` CLI reference," https://docs.docker.com/reference/cli/docker/compose/
- [SPEC CITED: feature=fr-mint-quality-tool-placement kind=technical_doc id=compose-services-profiles verified_at=2026-05-26] Docker Docs, "Define services in Docker Compose," https://docs.docker.com/reference/compose-file/services/
- [SPEC CITED: feature=fr-mint-quality-tool-placement kind=technical_doc id=sonarqube-docker verified_at=2026-05-26] SonarSource Docs, "Installing SonarQube from Docker," https://docs.sonarsource.com/sonarqube-community-build/setup-and-upgrade/installing-sonarqube-from-docker/
- [SPEC CITED: feature=fr-mint-quality-tool-placement kind=technical_doc id=cabal-build verified_at=2026-05-26] Cabal documentation, "Common Architecture for Building Applications and Libraries," https://downloads.haskell.org/ghc/latest/docs/users_guide/
