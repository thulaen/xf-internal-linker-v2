#!/bin/bash
# Push the current working-tree source snapshot to the Dell mutation runner.
#
# Scoped mutation must run against the EXACT staged source. This tars the
# backend tree + the hook helpers and extracts them on the Dell over SSH, so
# the Dell's checkout matches this machine before each remote mutation run.
# mutmut mutates the Dell's copy IN PLACE; that copy is disposable and is
# re-synced every run, so no snapshot/restore is needed on the Dell side.
set -euo pipefail

DELL_HOST="${DELL_HOST:-dell}"
DELL_REPO="${DELL_REPO_PATH:-C:\\Users\\PC\\xf-internal-linker-v2}"

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

# Single source of truth: scripts/_sync_tar_excludes.py (shared with the Python
# sharders; MUST stay byte-identical — the Dell side re-hashes the same bytes, so
# a drifted list fails the manifest). Read the --exclude args from that one list.
mapfile -t _tar_excludes < <(python3 "${repo_root}/scripts/_sync_tar_excludes.py")
tar -cf - "${_tar_excludes[@]}" \
  backend .githooks \
  | ssh -o BatchMode=yes "$DELL_HOST" "cd ${DELL_REPO} && tar -xf -"
