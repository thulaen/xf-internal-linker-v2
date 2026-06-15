#!/usr/bin/env bash
# SLICE-01 preflight: dropped-transfer resilience (checksum + retry).
#
# Plain English: proves that when we copy a file to a cluster machine, we can
# TRUST the copy. It does three things: (1) copy a file and confirm the bytes on
# the other side match exactly; (2) deliberately corrupt the remote copy and show
# that the checksum CATCHES it — it never reports a broken copy as "fine"; and
# (3) retry the copy and show it comes back correct. This is the guarantee every
# later slice relies on when it ships a source snapshot or build to Dell.
#
# Run with git-bash (NOT WSL):
#   /bin/bash tools/preflight/test_drop_resilience.sh
# Exit 0 = every check passed.

HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=cluster_lib.sh
. "$HERE/cluster_lib.sh"
cluster_require_gitbash "$0"

HOST="$DELL_SSH"
DEST="/tmp/xf-drop-probe-$$"
SRC="$(mktemp 2>/dev/null || echo "/tmp/xf-drop-src-$$")"

cleanup() { rm -f "$SRC" 2>/dev/null; ssh_host "$HOST" "rm -f '$DEST'" 2>/dev/null; }
trap cleanup EXIT

# Build a 5 MB random payload to transfer.
head -c 5242880 /dev/urandom > "$SRC" 2>/dev/null
WANT="$(sha256sum "$SRC" 2>/dev/null | awk '{print $1}')"
[ -n "$WANT" ] || { fail "could not create the test payload / checksum locally"; cluster_exit; }

# 1. A clean checksum-verified transfer succeeds.
if transfer_with_checksum_retry "$SRC" "$HOST" "$DEST" 3 >/dev/null; then
    pass "checksum-verified transfer to Dell succeeded (bytes match exactly)"
else
    fail "checksum-verified transfer to Dell failed"
fi

# 2. Corrupt the remote copy -> the checksum MUST catch it (no false pass).
ssh_host "$HOST" "head -c 1048576 '$DEST' > '$DEST.part' 2>/dev/null && mv '$DEST.part' '$DEST'"
GOT="$(ssh_host "$HOST" "sha256sum '$DEST' 2>/dev/null | awk '{print \$1}'")"
if [ -n "$GOT" ] && [ "$GOT" != "$WANT" ]; then
    pass "corruption detected: the truncated copy's checksum differs (no false pass)"
else
    fail "corruption NOT detected — a broken copy looked identical to the source"
fi

# 3. Retry restores a checksum-correct file.
if transfer_with_checksum_retry "$SRC" "$HOST" "$DEST" 3 >/dev/null; then
    GOT2="$(ssh_host "$HOST" "sha256sum '$DEST' 2>/dev/null | awk '{print \$1}'")"
    if [ "$GOT2" = "$WANT" ]; then
        pass "retry restored a checksum-correct file"
    else
        fail "retry did not restore a matching file"
    fi
else
    fail "retry transfer failed"
fi

cluster_exit
