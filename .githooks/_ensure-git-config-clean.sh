#!/usr/bin/env bash
# Strips [extensions] worktreeConfig = true from .git/config.
# Gemini CLI / Gemini Antigravity stop responding when this block is present.
# Claude Code's Agent(isolation: "worktree") re-adds it on every worktree op.
# Idempotent; safe to run anytime.

set -euo pipefail

GIT_DIR="$(git rev-parse --git-dir 2>/dev/null || true)"
if [ -z "${GIT_DIR}" ] || [ ! -f "${GIT_DIR}/config" ]; then
  exit 0
fi
CFG="${GIT_DIR}/config"

PY="$(command -v python3 || command -v python || true)"
if [ -n "${PY}" ]; then
  "${PY}" - "${CFG}" <<'PYEOF'
import re, sys
path = sys.argv[1]
with open(path, 'r', encoding='utf-8') as f:
    original = f.read()
content = re.sub(r'(?m)^[ \t]*worktreeConfig[ \t]*=[ \t]*true[ \t]*\r?\n', '', original)
content = re.sub(r'(?ms)^\[extensions\][ \t]*\r?\n(?=[ \t]*(\[|\Z))', '', content)
content = re.sub(r'(?s)\n{3,}', '\n\n', content)
if content != original:
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(content)
    print("ensure-git-config-clean: stripped [extensions] worktreeConfig=true from .git/config (Gemini guard).")
else:
    print("ensure-git-config-clean: .git/config already clean.")
PYEOF
  exit 0
fi

# No python available: sed fallback. Removes only the worktreeConfig line;
# an empty [extensions] header left behind is harmless for git but not for Gemini detection.
if grep -qE '^[[:space:]]*worktreeConfig[[:space:]]*=[[:space:]]*true[[:space:]]*$' "${CFG}"; then
  sed -i.bak -E '/^[[:space:]]*worktreeConfig[[:space:]]*=[[:space:]]*true[[:space:]]*$/d' "${CFG}"
  rm -f "${CFG}.bak"
  echo "ensure-git-config-clean: stripped worktreeConfig line (Gemini guard, sed fallback)."
else
  echo "ensure-git-config-clean: .git/config already clean."
fi
