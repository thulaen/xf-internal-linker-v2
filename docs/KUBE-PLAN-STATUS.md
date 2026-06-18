# KUBE PLAN Core Slice Status

Last reviewed: 2026-06-18

This file is the repo-owned status ledger for the Kubernetes migration plan.
It covers Slice 1 through Slice 30.

Live database status: the fresh MSI database backup was restored onto Dell and
the exact row-count proof passed. The stopped MSI app and worker containers were
removed after the operator approved cleanup. The MSI database container,
exporter, and database volume were removed after the rollback files were
archived on Dell. The remaining MSI local Docker containers were removed after
their cluster replacements were verified. Valkey, the Redis-compatible cache,
now runs on Dell.

| Slice | Status | Repo source of truth | Proof command |
|---|---|---|---|
| 01 network preflight | done | `docs/specs/fr-k8s-wifi-preflight.md` | `bash tools/preflight/test_lan_matrix.sh` |
| 02 Dell host prep | done | `docs/specs/fr-k8s-dell-host-prep.md` | `bash tools/preflight/test_dell_host.sh` |
| 03 Mint host prep | done | `docs/specs/fr-k8s-mint-host-prep.md` | `bash tools/preflight/test_mint_host.sh` |
| 04 time and names | done | `docs/specs/fr-k8s-time-dns.md` | `bash tools/preflight/test_cluster_time_and_names.sh` |
| 05 k3s server | done | `docs/specs/fr-k8s-k3s-server.md` | `bash tools/preflight/test_k3s_server.sh` |
| 06 k3s agent | done | `docs/specs/fr-k8s-k3s-agent.md` | `bash tools/preflight/test_k3s_agent.sh` |
| 07 network rules | done | `docs/specs/fr-k8s-net-rbac.md` | `bash tools/preflight/test_net_rbac.sh` |
| 08 NFS storage host | done | `docs/specs/fr-k8s-nfs-server.md` | `bash tools/preflight/test_nfs_server.sh` |
| 09 storage classes | done | `docs/specs/fr-k8s-storage-class.md` | `bash tools/preflight/test_storage.sh` |
| 10 node reservations | done | `docs/specs/fr-k8s-kubelet-reservations.md` | `bash tools/preflight/test_reservations.sh` |
| 11 Dell Postgres | done | `docs/specs/fr-k8s-postgres-on-dell.md` | `bash tools/preflight/test_postgres_service.sh` |
| 12 cluster Postgres Service | done | `docs/specs/fr-k8s-postgres-selectorless-service.md` | `bash tools/preflight/test_postgres_service.sh` |
| 13 database migration | done | `docs/specs/fr-k8s-db-migration.md` | `bash tools/migration/04_verify_equal.sh --source-counts /mnt/c/tmp/kube-row-counts-msi-final.txt --target-counts /mnt/c/tmp/kube-row-counts-dell-final.txt` |
| 14 PgBouncer and test DB shards | done | `docs/specs/fr-k8s-test-db-sharding.md` | `python scripts/bazel_default.py run //tools/quality:python` |
| 15 MSI kubectl console | documented replacement | `docs/specs/fr-msi-kubectl-console.md` | MSI now asks Mint to run Kubernetes commands when Windows has no `kubectl`; do not reinstall Windows `kubectl` for this slice |
| 16 Redis-compatible cache | done; Dell-backed | `docs/specs/fr-redis-in-cluster.md` | `kubectl -n xf-app exec deploy/valkey -- valkey-cli ping` |
| 17 backend deployment | done | `docs/specs/fr-backend-deployment.md` | `ssh mint-wifi "kubectl -n xf-app exec deploy/backend -- python manage.py check"` |
| 18 workers and scheduler | done | `docs/specs/fr-celery-workers-beat.md` | `ssh mint-wifi kubectl -n xf-app get deploy,pods,svc --request-timeout=10s` |
| 19 frontend | done | `docs/specs/fr-frontend-nginx-ingress.md` | `ssh mint-wifi "curl -fsS --max-time 10 http://127.0.0.1:30080/"` |
| 20 prebuilt sidecars | done | `docs/specs/fr-go-sidecars-deploy.md` | `bash tools/preflight/test_sidecar_images.sh` passes with digest-pinned images in `sidecar-images.lock.json` |
| 21 observability | done; MSI copies removed | `docs/specs/fr-observability-migration.md` | Grafana and GlitchTip NodePorts respond; Loki, Tempo, and VictoriaMetrics readiness checks pass |
| 22 registry and pre-pull | done | `docs/specs/fr-k8s-registry-mirror.md` | `bash tools/preflight/test_registry_mirror.sh --live` |
| 23 runner images | done | `docs/specs/fr-k8s-runner-images.md` | `python tools/runners/test_runner_image_refs.py` |
| 24 Bazel install and build files | done | `docs/specs/fr-k8s-bazel-install.md` | `python scripts/bazel_default.py test --cache_test_results=no //tools/quality:all`; `python scripts/bazel_default.py run //tools/quality:affected_targets` |
| 25 Bazel remote cache | done | `docs/specs/fr-k8s-bazel-remote.md` | `bash tools/preflight/test_bazel_backends.sh` |
| 26 distributed test adapters | done | `docs/specs/fr-k8s-distribute-tests.md` | `python -m pytest -q -p no:randomly tools/test/test_quality_adapters.py scripts/test_distributed_test_coordinator.py` |
| 27 coordinator and merge | done | `docs/specs/fr-k8s-coordinator.md` | `pwsh scripts/run-distributed-tests.ps1 -DryRun` |
| 28 guarded cutover | done; Dell rollback archive retained | `docs/specs/fr-k8s-cutover.md` | `bash tools/migration/05_cutover.sh --proof-file /mnt/c/tmp/kube-db-cutover-proof.json --dry-run` |
| 29 Google Cloud burst | complete; no-spend proof only | `docs/specs/fr-k8s-29-gcp-spot-mutation-burst.md` | `python scripts/gcp_burst_executor.py --project xf --region europe-west1 --dry-run`; `python scripts/distributed_test_coordinator.py --dry-run --burst gcp --full` |
| 30 embedding provider evaluation | done | `docs/specs/fr232-embedding-provider-bakeoff.md` | `python scripts/bazel_default.py run //tools/quality:provider_score_backend` |

## Closeout Notes

- Given the live database move was approved, when the fresh MSI backup was
  restored onto Dell, then exact MSI and Dell row-count files matched before the
  cluster was restarted.
- Given Slice 28 is guarded, when `scripts/remove-msi-docker.ps1` runs without
  the verified proof file and exact confirmation phrase, then it refuses to
  remove Docker from MSI.
- Given live go-live was requested, when MSI is allowed through Mint's firewall
  to Kubernetes API port 6443, then `python .githooks/check-k8s-cluster-ready.py`
  passes the node and service checks.
- Given Dell was restored from `C:\tmp\msi-xf-linker-final-cutover.dump`, when
  `tools/migration/04_verify_equal.sh` compared
  `C:\tmp\kube-row-counts-msi-final.txt` and
  `C:\tmp\kube-row-counts-dell-final.txt`, then it printed
  `[DB ROW COUNT PROOF: matched]`.
- Given the cluster app was restarted against Dell, when health and operator
  checks ran, then backend health returned `{"status": "ok", "version": "2.0.0"}`,
  the admin page redirected to login, `verify_users_present` returned
  `{"auth_user_count": 3}`, the frontend returned HTTP 200, Grafana returned
  HTTP 302 to login, and GlitchTip returned HTTP 200.
- Given the first live user-count command exposed database pool pressure, when
  PgBouncer was raised to `DEFAULT_POOL_SIZE=100` and `RESERVE_POOL_SIZE=20`,
  then the live user-count command completed instead of timing out.
- Given full MSI database cleanup was approved, when the rollback files were
  archived to `/var/backups/xf-linker/cutover-2026-06-17/` on Dell and hashes
  matched, then `xf_linker_postgres`, `xf_linker_postgres_exporter`, and
  `xf-internal-linker-v2_pgdata` were removed from MSI.
- Given MSI still had old local support containers, when Dell-backed cluster
  replacements were verified, then the remaining MSI containers were removed and
  `docker ps -a` no longer listed project containers on MSI.
- Given MSI previously ran Redis locally, when Valkey was pinned to Dell and
  rolled out, then `kubectl -n xf-app exec deploy/valkey -- valkey-cli ping`
  returned `PONG` and the live app stayed healthy.
- Given Mint remains the Kubernetes control-plane helper, when this status was
  updated, then Mint still intentionally ran the control-plane services,
  registry, Pyroscope, and its node-local Alloy collector. Those are not MSI
  leftovers.
- Given older slice drafts mention `k8s/base`, when repo files already exist in
  `k8s/storage`, `k8s/network`, `k8s/database`, `k8s/app`, `k8s/registry`, and
  `k8s/obs`, then the existing repo paths remain the source of truth.
- Given Slice 30 evaluates providers, when a provider loses two significant
  paired tests, then it is skipped until the operator unbans it.
- Given MSI is now meant to work without local Docker, when hooks or startup
  scripts need Django, then they call `scripts/backend_manage.py`, which runs
  `python manage.py` inside the Kubernetes backend pod by default.
- Given the Dell helper may still run Docker, when MSI needs a Dell Docker
  command, then the new `scripts/dell_docker.py` helper builds an
  `ssh dell docker ...` command instead of requiring MSI's Docker command.
- Given normal repo work must stay Docker-free on MSI, when pre-commit runs,
  then `.githooks/check-msi-docker-free.py` scans the active hook and startup
  path and refuses local Docker Compose, Docker Desktop, local `docker ps`,
  local `docker stats`, and local `docker system prune` dependencies.
- Given observability moved into Kubernetes, when
  `.githooks/check-observability-stack.py` runs, then it checks pods in the
  `xf-obs` namespace instead of checking local Compose containers.
- Given MSI no longer has a Windows `kubectl` command, when backend and
  observability checks need Kubernetes, then they fall back to
  `ssh mint-wifi kubectl ...` and still avoid MSI Docker.
- Given full MSI Docker removal was approved, when the proof gate passed, then
  Docker Desktop was removed, Docker's WSL distributions were removed, the
  user-level Docker shims were removed, PowerShell startup references were
  removed, and `Get-Command docker` returned nothing.
- Given the full repo Docker-free guard was rerun after cleanup, when
  `python .githooks/check-msi-docker-free.py` completed, then it printed
  `[MSI DOCKER-FREE: passed]`.
- Given proof was refreshed on 2026-06-18, when
  `bash tools/preflight/test_postgres_service.sh` ran, then Dell Postgres
  EndpointSlices passed in `xf-app`, `xf-obs`, and `xf-test`, all pointing to
  `10.10.10.92:5432`.
- Given the live app was checked on 2026-06-18, when
  `ssh mint-wifi kubectl -n xf-app get deploy,pods,svc --request-timeout=10s`
  ran, then backend was `2/2`, workers and scheduler were `1/1`, frontend was
  `1/1`, and all listed pods were Running.
- Given the frontend and backend were checked on 2026-06-18, when Mint ran
  `curl -fsS --max-time 10 http://127.0.0.1:30080/` and
  `kubectl -n xf-app exec deploy/backend -- python manage.py check`, then the
  frontend returned an 8,863-byte page and Django reported no issues.
- Given the registry mirror was checked on 2026-06-18, when
  `bash tools/preflight/test_registry_mirror.sh --live` ran, then the registry
  manifest shape passed, runner image references rendered, and Mint registry
  answered `/v2/`.
- Given slices 24 through 27 were completed on 2026-06-18, when the focused
  Python tests ran with the local random-seed plugin disabled, then 52 script
  and tooling tests passed.
- Given slice 30 was completed on 2026-06-18, when Dell-backed backend tests
  and targeted frontend tests ran, then 30 backend tests and 6 frontend tests
  passed. The backend coverage report was 80% across the checked provider
  evaluation files.
- Given the follow-up Bazel default conversion ran on 2026-06-18, when
  `python scripts/bazel_default.py test --cache_test_results=no
  //tools/quality:all` ran from MSI, then the source synced to Dell, Dell Bazel
  executed the default quality suite, and all 10 Bazel quality tests passed.
- Given old language quality entry points could conflict with Bazel, when the
  Bazel-only cleanup ran, then the old public language quality scripts were
  deleted and Bazel became the only public quality entry point.
- Given provider-score backend coverage was below target, when the branch tests
  were added and Dell pytest reran, then 38 backend tests passed and coverage
  rose to 97% across the checked provider-score backend files.
- Given the host-side random-order test run previously hit a NumPy seed error,
  when pytest config was changed to keep random order but stop per-test seed
  resets, then the same focused host-side suite passed with `pytest-randomly`
  enabled.
- Given the live resolved-issue lookup was failing with `PermissionError:
  /audit`, when the audit path resolver was changed and Dell-backed tests ran,
  then the resolver now chooses `XF_AUDIT_DIR`, a writable repo `audit` folder,
  or `/tmp/xf-linker-audit`, and the focused backend coverage was 91%.
- Given Kubernetes management commands should not write to `/audit`, when
  `scripts/backend_manage.py` builds a Kubernetes command, then it injects
  `XF_AUDIT_DIR=/tmp/xf-linker-audit` unless the caller already set
  `XF_AUDIT_DIR`.
- Given Bazel is the required quality entry point, when
  `python scripts/bazel_default.py test --cache_test_results=no
  //tools/quality:all` ran from MSI, then Dell Bazel executed 10 quality tests
  and all 10 passed.
- Given the scoped Bazel targets were refreshed on 2026-06-18, when
  `python scripts/bazel_default.py run //tools/quality:python`,
  `//tools/quality:frontend`, `//tools/quality:rust`,
  `//tools/quality:provider_score_backend`, and
  `//tools/quality:distributed_dry_run` ran, then Python quality passed on
  Dell, frontend lint/style/tests passed with 138 Vitest tests, Rust correctly
  skipped because no Rust files changed, provider-score backend coverage was
  97%, and the distributed dry-run placed all shard groups on Dell.
- Given Bazel was running quality targets on Dell, when frontend and Rust
  targets needed Docker, then the private Bazel runner bodies used Dell's local
  Docker engine directly and still blocked local Docker on MSI.
- Given Angular 22 no longer accepts the retired frontend test flag shape, when
  the frontend quality runner was updated, then it used `--watch=false`,
  `--coverage=true`, and repeated `--include=<spec>` flags, and the Bazel
  frontend target passed.
- Given old public language runners could conflict with Bazel, when public
  hooks, GitHub Actions workflows, `scripts/verify.ps1`, and active docs were
  updated, then they call `scripts/bazel_default.py`, and
  `.githooks/check-bazel-public-entrypoints.py` passed.
- Given live Kubernetes still ran the old `xf-linker-backend:v6` image, when
  the fixed backend was rebuilt as `10.10.10.91:5000/xf-linker-backend:v7`,
  pushed to the Mint registry, and rolled out to backend plus Celery
  deployments on 2026-06-18, then
  `python scripts/backend_manage.py search_resolved_issues --area
  backend/apps/auto_issues --force` passed. The live pod has no `/audit`
  path, and it writes lookup proof to `/tmp/xf-linker-audit`.
