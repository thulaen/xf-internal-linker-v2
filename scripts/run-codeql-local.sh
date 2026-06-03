#!/usr/bin/env bash
set -euo pipefail

python scripts/codeql_language_inventory.py --format plain
python scripts/run_codeql.py "$@"
