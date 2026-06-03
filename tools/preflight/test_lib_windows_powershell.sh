#!/usr/bin/env bash
# Focused regression test for the WSL Windows PowerShell fallback.
set -euo pipefail

tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT

cat >"$tmp_dir/direct-powershell.exe" <<'SH'
#!/bin/sh
exit 126
SH

cat >"$tmp_dir/fake-init" <<'SH'
#!/bin/sh
"$@"
SH

cat >"$tmp_dir/fallback-powershell.exe" <<'SH'
#!/bin/sh
case "$*" in
    *"Write-Output fallback-ok"*) printf 'fallback-ok\r\n' ;;
esac
SH

chmod +x "$tmp_dir/direct-powershell.exe" "$tmp_dir/fake-init" "$tmp_dir/fallback-powershell.exe"

source tools/preflight/lib.sh

result="$(
    PATH="$tmp_dir" \
    WINDOWS_POWERSHELL_DIRECT="direct-powershell.exe" \
    WINDOWS_POWERSHELL_EXE="$tmp_dir/fallback-powershell.exe" \
    WSL_INIT_EXE="$tmp_dir/fake-init" \
    windows_powershell "Write-Output fallback-ok" | /usr/bin/tr -d "\r"
)"

[[ "$result" == "fallback-ok" ]]
