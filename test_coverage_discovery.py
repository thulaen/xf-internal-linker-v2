"""Temporary test to diagnose coverage discovery."""
import sys
sys.path.insert(0, '.githooks')
from pathlib import Path
import re
import subprocess

REPO_ROOT = Path('.').resolve()

def _staged_files():
    out = subprocess.check_output(
        ['git', 'diff', '--cached', '--name-only', '--diff-filter=ACM'],
        cwd=str(REPO_ROOT), text=True, encoding='utf-8', errors='replace'
    )
    return [line.strip().replace('\\', '/') for line in out.splitlines() if line.strip()]

def _is_test_py(p):
    return p.endswith('.py') and bool(re.search(r'(^|/)(test_|tests_)|/tests/', p))

def _app_root(rel):
    parts = Path(rel).parts
    if len(parts) >= 3 and parts[:2] == ('backend', 'apps'):
        return '/'.join(parts[:3])
    if len(parts) >= 2 and parts[0] == 'backend' and parts[1] == 'config':
        return 'backend/config'
    return None

def _test_paths_for(rel):
    path = Path(rel)
    stem = path.stem
    found = []
    cur = path.parent
    while True:
        for cand in (
            cur / f'tests_{stem}.py',
            cur / 'tests' / f'test_{stem}.py',
            cur / f'test_{stem}.py',
        ):
            posix = cand.as_posix()
            if (REPO_ROOT / cand).is_file() and posix not in found:
                found.append(posix)
        parts = cur.parts
        if len(parts) <= 3 or parts[:2] != ('backend', 'apps'):
            break
        cur = cur.parent
    app = _app_root(rel)
    if app:
        for t in _staged_files():
            if _is_test_py(t) and t.startswith(app + '/') and t not in found:
                found.append(t)
    return found

rel1 = 'backend/apps/auto_issues/management/commands/pick_pgexporter_findings.py'
rel2 = 'backend/apps/auto_issues/services/pgexporter_picker.py'
print('pick_pgexporter_findings:', _test_paths_for(rel1))
print('pgexporter_picker:', _test_paths_for(rel2))
