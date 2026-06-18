#!/usr/bin/env bash
# Slice 22 non-destructive registry and image pre-pull proof.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=cluster_lib.sh
. "$HERE/cluster_lib.sh"

LIVE=0
PYTHON_BIN="${PYTHON_BIN:-python3}"
for arg in "$@"; do
  case "$arg" in
    --live) LIVE=1 ;;
    --help) echo "Usage: $0 [--live]"; exit 0 ;;
    *) echo "Unknown argument: $arg" >&2; exit 2 ;;
  esac
done

if [ "$LIVE" -eq 1 ]; then
  cluster_require_gitbash "$0"
fi

"$PYTHON_BIN" -c "import pathlib,yaml; reg=yaml.safe_load_all(pathlib.Path('k8s/registry/registry.yaml').read_text()); docs=[d for d in reg if d]; assert any(d.get('kind')=='Deployment' and d['metadata']['name']=='registry' for d in docs); pre=yaml.safe_load(pathlib.Path('k8s/registry/image-prepull.yaml').read_text()); assert pre['kind']=='DaemonSet'; assert pre['spec']['template']['spec']['nodeSelector']['xf.io/role']=='worker'" \
  && pass "registry and pre-pull manifests have the expected rehearsal shape" \
  || fail "registry or pre-pull manifest shape is wrong"

"$PYTHON_BIN" tools/runners/image_refs.py --format env >/dev/null \
  && pass "runner image references render from runner-images.lock.json" \
  || fail "runner image references failed to render"

if [ "$LIVE" -eq 1 ]; then
  ssh_host "$MINT_SSH" "curl -fsS --max-time 5 http://$MINT_WIRED_IP:5000/v2/" >/dev/null \
    && pass "Mint registry answers /v2/" \
    || fail "Mint registry did not answer /v2/"
fi

cluster_exit
