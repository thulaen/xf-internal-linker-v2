#!/usr/bin/env bash
set -euo pipefail
export PATH="/usr/bin:/bin:${PATH:-}"
export MSYS_NO_PATHCONV=1
export MSYS2_ARG_CONV_EXCL="*"

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

. scripts/quality-evidence-lib.sh
evidence_file="$(quality_evidence_path tool-readiness)"
evidence_container="$(quality_evidence_container_path tool-readiness)"
quality_evidence_init "$evidence_file"
trap 'quality_evidence_finalize "$?" "$evidence_file" "$evidence_container"' EXIT
force_build=0
if [[ "${1:-}" == "--build" ]]; then
  force_build=1
fi

record_readiness() {
  local status="$1"
  local tool="$2"
  local command="$3"
  local summary="$4"
  quality_evidence_write \
    --out "$evidence_file" \
    --check-type tool_readiness \
    --status "$status" \
    --tool-name "$tool" \
    --command "$command" \
    --summary "$summary" \
    --failure-fingerprint "tool-readiness:${tool}:${status}"
}

ensure_image() {
  local service="$1"
  local image="$2"
  if [[ "$force_build" -eq 0 ]] && docker image inspect "$image" >/dev/null 2>&1; then
    record_readiness passed "${service}-image" "docker image inspect ${image}" "Docker image is already present."
    return 0
  fi
  set +e
  docker compose build "$service"
  local status=$?
  set -e
  if [[ "$status" -eq 0 ]]; then
    record_readiness passed "${service}-build" "docker compose build ${service}" "Docker image built successfully."
  else
    record_readiness failed "${service}-build" "docker compose build ${service}" "Docker image build failed."
    exit "$status"
  fi
}

wait_for_service() {
  local service="$1"
  local label="$2"
  for _ in $(seq 1 45); do
    local container_id
    container_id="$(docker compose ps -q "$service" 2>/dev/null || true)"
    if [[ -n "$container_id" ]]; then
      local status
      status="$(docker inspect -f '{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{end}}' "$container_id" 2>/dev/null || true)"
      if [[ "$status" == "running healthy" || "$status" == "running " ]]; then
        record_readiness passed "${label}-container" "docker compose ps ${service}" "Container is running."
        return 0
      fi
    fi
    sleep 2
  done
  record_readiness failed "${label}-container" "docker compose ps ${service}" "Container did not become healthy."
  return 1
}

ensure_volume() {
  local volume="$1"
  set +e
  docker volume inspect "${repo_root##*/}_${volume}" >/dev/null 2>&1
  local namespaced_status=$?
  docker volume inspect "$volume" >/dev/null 2>&1
  local direct_status=$?
  set -e
  if [[ "$namespaced_status" -eq 0 || "$direct_status" -eq 0 ]]; then
    record_readiness passed "${volume}-volume" "docker volume inspect ${volume}" "Shared tool cache volume is present."
    return 0
  fi
  record_readiness failed "${volume}-volume" "docker volume inspect ${volume}" "Shared tool cache volume is missing."
  return 1
}

ensure_image backend xf-linker-backend:latest
ensure_image compiled-tools xf-linker-compiled-tools:latest
ensure_image frontend-mutation-tools xf-linker-frontend-mutation-tools:latest

set +e
docker compose up -d --no-deps compiled-tools frontend-mutation-tools
autostart_status=$?
set -e
if [[ "$autostart_status" -eq 0 ]]; then
  record_readiness passed docker-tools-autostart "docker compose up -d --no-deps compiled-tools frontend-mutation-tools" "Docker-managed quality tool containers started."
else
  record_readiness failed docker-tools-autostart "docker compose up -d --no-deps compiled-tools frontend-mutation-tools" "Docker-managed quality tool containers could not start."
  exit "$autostart_status"
fi

wait_for_service compiled-tools compiled-tools
wait_for_service frontend-mutation-tools frontend-tools
ensure_volume compiled_tool_cache
ensure_volume frontend_tool_cache
ensure_volume go_tool_mod_cache

set +e
docker compose exec -T compiled-tools bash -lc '
  mutmut --version
  mull-runner-19 --version
  go version
  command -v go-mutesting >/dev/null
  golangci-lint --version
  gosec -version
  cmake --version
  clang++-19 --version
  clang-format-19 --version
  clang-tidy-19 --version
  llvm-cov-19 --version
  llvm-profdata-19 --version
  cppcheck --version
  include-what-you-use --version
  infer --version
  semgrep --version
'
compiled_status=$?
set -e
if [[ "$compiled_status" -eq 0 ]]; then
  record_readiness passed compiled-tools "docker compose exec compiled-tools tool version checks" "Compiled-language quality tools are installed in the running container."
else
  record_readiness failed compiled-tools "docker compose exec compiled-tools tool version checks" "A compiled-language quality tool is missing or broken."
  exit "$compiled_status"
fi

set +e
docker compose exec -T frontend-mutation-tools sh -lc '
  node --version
  npm --version
  npx eslint --version
  npx stylelint --version
  npx stryker --version
  npm audit --version
'
frontend_status=$?
set -e
if [[ "$frontend_status" -eq 0 ]]; then
  record_readiness passed frontend-tools "docker compose exec frontend-mutation-tools tool version checks" "Frontend quality tools are installed in the running container."
else
  record_readiness failed frontend-tools "docker compose exec frontend-mutation-tools tool version checks" "A frontend quality tool is missing or broken."
  exit "$frontend_status"
fi

set +e
docker compose run --rm -T --no-deps backend sh -lc '
  ruff --version
  pylint --version
  bandit --version
  pip-audit --version
  safety --version
  coverage --version
  mutmut --version
'
backend_status=$?
set -e
if [[ "$backend_status" -eq 0 ]]; then
  record_readiness passed backend-tools "docker compose run --rm backend tool version checks" "Backend quality tools are installed."
else
  record_readiness failed backend-tools "docker compose run --rm backend tool version checks" "A backend quality tool is missing or broken."
  exit "$backend_status"
fi

echo "All required Docker-managed quality tools are installed."
