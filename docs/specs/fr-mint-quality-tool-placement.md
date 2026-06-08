# FR — Dell and Mint quality-tool placement

**Status:** Draft.
**Spec ID:** fr-mint-quality-tool-placement.

[SPEC FRESHNESS: reviewed_at=2026-06-02 next_review=2026-09-02]

## Plain-English Summary

Compiled-language tools, Haskell quality checks, and profiling helpers are
heavy quality workloads that stay on Linux Mint. SonarQube and sonar-autoscan
now run on the Dell helper because Dell is the faster quality machine and has
room for the scanner index and cache. Windows keeps the live control plane:
Django, Redis, Postgres, Celery, Lua advisor runtime, hooks, sessions, provider
credentials, and AutoIssue / PaperTrail database access.

## Source-Backed Rules

- Docker contexts select which Docker daemon receives commands, so scripts that
  start Dell-owned or Mint-owned work must target that host explicitly instead
  of changing the operator's default Windows Docker context.
- Docker Compose profiles keep optional services out of the default stack until
  the matching profile is requested.
- SonarQube runs as the quality server on Dell and exposes a web API that the
  Windows backend can ingest into AutoIssues.
- Haskell quality work uses Cabal inside the Docker-managed compiled-tools
  container; host-side Haskell installs are not required.

## BDD Contract

Given the operator starts the normal Windows stack,
when Docker Compose evaluates default services,
then compiled-tools, SonarQube, and sonar-autoscan do not start on Windows.

Given the operator starts Mint quality tools,
when `scripts/start-mint-quality-tools.ps1` runs,
then Mint builds and starts compiled-tools, Pyroscope, and the multi-language
observability picker, but does not start SonarQube or sonar-autoscan.

Given the operator starts Dell Sonar tools,
when `scripts/start-dell-sonar-tools.ps1` runs,
then Dell starts SonarQube and sonar-autoscan with Dell-owned named volumes and
a synced source snapshot.

Given AutoIssue ingestion runs on Windows,
when it needs SonarQube findings,
then it verifies SonarQube through the `dell` Docker context from inside the
Dell-hosted `xf_linker_sonarqube` container.

Given sanity checks run after the move,
when `scripts/check-mint-quality-tools.ps1` runs,
then it checks compiled-tools, Haskell quality, Pyroscope status, and Mint RAM.

Given sanity checks run after the Dell move,
when `scripts/check-dell-sonar-tools.ps1` runs,
then it checks Dell SonarQube status and recent sonar-autoscan logs.

## Citations

- [SPEC CITED: feature=fr-mint-quality-tool-placement kind=technical_doc id=docker-contexts verified_at=2026-05-26] Docker Docs, "Docker contexts," https://docs.docker.com/engine/manage-resources/contexts/
- [SPEC CITED: feature=fr-mint-quality-tool-placement kind=technical_doc id=docker-compose-profiles verified_at=2026-05-26] Docker Docs, "`docker compose` CLI reference," https://docs.docker.com/reference/cli/docker/compose/
- [SPEC CITED: feature=fr-mint-quality-tool-placement kind=technical_doc id=compose-services-profiles verified_at=2026-05-26] Docker Docs, "Define services in Docker Compose," https://docs.docker.com/reference/compose-file/services/
- [SPEC CITED: feature=fr-mint-quality-tool-placement kind=technical_doc id=sonarqube-docker verified_at=2026-05-26] SonarSource Docs, "Installing SonarQube from Docker," https://docs.sonarsource.com/sonarqube-community-build/setup-and-upgrade/installing-sonarqube-from-docker/
- [SPEC CITED: feature=fr-mint-quality-tool-placement kind=technical_doc id=cabal-build verified_at=2026-05-26] Cabal documentation, "Common Architecture for Building Applications and Libraries," https://downloads.haskell.org/ghc/latest/docs/users_guide/
