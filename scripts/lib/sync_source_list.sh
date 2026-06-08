#!/usr/bin/env bash
# Single source of truth for "which files get synced to a remote quality runner".
#
# It derives the file list from git, so it AUTOMATICALLY respects .gitignore:
# generated output, local DB backups (backend/backups), coverage HTML
# (backend/coverage-html), build artefacts and caches are never packed. This
# replaces the hand-maintained `tar --exclude=...` lists that drifted out of sync
# across the sync scripts (run-dell-quality-shard.sh had no backend/backups
# exclude, so it shipped ~428 MB of DB backups on every remote check).
#
# Usage: source this file from the repo root, then:
#     sync_file_list [root-prefix ...]
#   No args   -> every git-known source file in the repo.
#   With args -> only files under those top-level roots (e.g. backend services).
# Output: NUL-separated paths on stdout — pipe into `tar --null -T - -cf -`.

# Returns 0 (true) when a path is a generated/heavy directory we never sync.
# Defence-in-depth: .gitignore already drops these when untracked, but a file
# committed before being ignored is still listed by `git ls-files --cached`.
_sync_is_generated() {
  case "$1" in
    .git/* | node_modules/* | .venv/* | .mypy_cache/* | .pytest_cache/* | .ruff_cache/* | htmlcov/*) return 0 ;;
    frontend/dist/* | frontend/node_modules/*) return 0 ;;
    backend/backups/* | backend/coverage-html/* | backend/reports/* | backend/staticfiles/* | backend/media/*) return 0 ;;
    backend/extensions/build/* | backend/extensions/build_*/* | backend/extensions/build_tests/* | backend/extensions/reports/*) return 0 ;;
    rust/target/* | rust/mutants.out | rust/mutants.out/* | rust/mutants.out.old | rust/mutants.out.old/*) return 0 ;;
    services/speccheck/mutants.out | services/speccheck/mutants.out/* | services/speccheck/mutants.out.old | services/speccheck/mutants.out.old/*) return 0 ;;
  esac
  return 1
}

# Returns 0 (true) when a path is under one of the requested roots (or when no
# roots were requested, i.e. "sync everything").
_sync_in_roots() {
  local path="$1"
  shift
  [ "$#" -eq 0 ] && return 0
  local root
  for root in "$@"; do
    case "$path" in "$root"/*) return 0 ;; esac
  done
  return 1
}

sync_file_list() {
  # Use GNU sort explicitly: on Windows/git-bash a bare `sort` resolves to
  # Windows' sort.exe, which does not understand -z (NUL) and silently emits
  # nothing. /usr/bin/sort is GNU coreutils in both git-bash and the Linux
  # container. (Same Windows-shadowing guard dell-rust.sh uses for sha1sum.)
  local sort_bin=/usr/bin/sort
  [ -x "$sort_bin" ] || sort_bin=sort
  git ls-files -z --cached --modified --others --exclude-standard |
    while IFS= read -r -d '' path; do
      [ -e "$path" ] || continue
      _sync_is_generated "$path" && continue
      _sync_in_roots "$path" "$@" || continue
      printf '%s\0' "$path"
    done |
    "$sort_bin" -zu
}
