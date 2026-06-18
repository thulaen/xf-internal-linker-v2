#!/usr/bin/env bash
# Guarded live database cutover helper. Dry-run by default.
set -euo pipefail

PROOF_FILE=""
EXECUTE=0
CONFIRM_PHRASE=""
EXPECTED_PHRASE="CUT OVER DATABASE AFTER VERIFIED REHEARSAL"
PYTHON_BIN="${PYTHON_BIN:-python3}"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --proof-file) PROOF_FILE="${2:-}"; shift 2 ;;
    --confirm-phrase) CONFIRM_PHRASE="${2:-}"; shift 2 ;;
    --dry-run) EXECUTE=0; shift ;;
    --execute) EXECUTE=1; shift ;;
    --help)
      echo "Usage: $0 --proof-file <json> [--execute --confirm-phrase \"$EXPECTED_PHRASE\"]"
      exit 0
      ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done

[ -n "$PROOF_FILE" ] || { echo "--proof-file is required." >&2; exit 2; }
[ -f "$PROOF_FILE" ] || { echo "Proof file not found: $PROOF_FILE" >&2; exit 2; }

"$PYTHON_BIN" -c "import json,sys; p=json.load(open(sys.argv[1], encoding='utf-8')); missing=[k for k in ('backup','restore','row_counts','rollback') if not p.get(k,{}).get('verified')]; print('Missing proof: '+', '.join(missing) if missing else '[DB CUTOVER PROOF: ready]'); sys.exit(2 if missing else 0)" "$PROOF_FILE"

if [ "$EXECUTE" -ne 1 ]; then
  echo "[DB CUTOVER: dry-run]"
  echo "Would repoint app secrets and restart app pods after verified rehearsal."
  exit 0
fi

[ "$CONFIRM_PHRASE" = "$EXPECTED_PHRASE" ] || {
  echo "Cutover refused because the confirmation phrase did not match." >&2
  exit 2
}

echo "[DB CUTOVER: execute requested]"
echo "This script intentionally leaves the live repoint command for the go-live session."
exit 2
