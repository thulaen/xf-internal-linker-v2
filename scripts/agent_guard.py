#!/usr/bin/env python3
import os
import sys
import time
import ast
import hashlib
from collections import defaultdict

# Django setup for AutoIssue creation
try:
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../backend')))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")
    import django
    django.setup()
    from apps.auto_issues.models import AutoIssue
    DJANGO_AVAILABLE = True
except Exception as e:
    DJANGO_AVAILABLE = False
    print(f"Warning: Django unavailable ({e}). AutoIssues will not be saved to DB.")

# --- CONFIG ---
WATCH_DIRS = ['backend', 'frontend', 'scripts']
FILE_EXTS = ('.py', '.ts', '.sh')
MAX_LINES = 50
MAX_COMPLEXITY = 10
WINDOW_SIZE = 6

DRY_INDEX = defaultdict(set)

def normalize_line(line):
    s = line.strip()
    if not s or s.startswith('#') or s.startswith('//'):
        return None
    return s

def process_file_for_dry_index(path):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except Exception:
        return
    valid_hashes = [hash(normalize_line(l)) for l in lines if normalize_line(l)]
    for i in range(len(valid_hashes) - WINDOW_SIZE + 1):
        w_hash = hash(tuple(valid_hashes[i:i+WINDOW_SIZE]))
        DRY_INDEX[w_hash].add(path)

def build_dry_index(exclude_files):
    DRY_INDEX.clear()
    exclude_set = set(os.path.abspath(f) for f in exclude_files)
    for watch_dir in WATCH_DIRS:
        if not os.path.exists(watch_dir):
            continue
        for root, _, files in os.walk(watch_dir):
            for file in files:
                if file.endswith(FILE_EXTS):
                    path = os.path.join(root, file)
                    if os.path.abspath(path) not in exclude_set:
                        process_file_for_dry_index(path)

def get_last_test_mod_time():
    last_mod = 0
    for watch_dir in WATCH_DIRS:
        if not os.path.exists(watch_dir):
            continue
        for root, _, files in os.walk(watch_dir):
            for file in files:
                if 'test' in file.lower() and file.endswith(FILE_EXTS):
                    try:
                        st = os.stat(os.path.join(root, file))
                        if st.st_mtime > last_mod:
                            last_mod = st.st_mtime
                    except Exception:
                        pass
    return last_mod

class ComplexityVisitor(ast.NodeVisitor):
    def __init__(self):
        self.violations = []
        
    def visit_FunctionDef(self, node):
        lines = node.end_lineno - node.lineno
        if lines >= MAX_LINES:
            self.violations.append(f"Function '{node.name}' is {lines} lines (max {MAX_LINES})")
            
        branches = sum(1 for _ in ast.walk(node) if isinstance(_, (ast.If, ast.For, ast.While, ast.Try, ast.With, ast.ExceptHandler, ast.BoolOp)))
        complexity = branches + 1
        if complexity > MAX_COMPLEXITY:
            self.violations.append(f"Function '{node.name}' has complexity {complexity} (max {MAX_COMPLEXITY})")
            
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node):
        self.visit_FunctionDef(node)

def report_violation(filepath, rule, problem, suggested_fix):
    msg = f"\n> [!CAUTION]\n> **Agent Guard Checker Warning:** `{filepath}`\n> **Rule:** {rule}\n> **Problem:** {problem}\n> **Suggested Fix:** {suggested_fix}\n"
    print(msg)
    
    if DJANGO_AVAILABLE:
        canonical = f"agent_guard:{rule.lower()}:{filepath}"
        try:
            issue, created = AutoIssue.objects.update_or_create(
                canonical_fingerprint=canonical,
                defaults={
                    "source": "agent",
                    "external_id": hashlib.sha1(canonical.encode()).hexdigest(),
                    "status": "open",
                    "priority_score": 100,
                    "issue_title": f"Agent Guard: {rule} violation in {filepath}",
                    "issue_body": f"Problem: {problem}\nSuggested Fix: {suggested_fix}"
                }
            )
            if not created:
                issue.occurrence_count += 1
                issue.save(update_fields=['occurrence_count'])
        except Exception as e:
            print(f"Failed to write AutoIssue: {e}")

def check_tdd(rel_filepath, last_test_mod_time):
    if time.time() - last_test_mod_time > 300: # 5 mins
        report_violation(
            rel_filepath, 
            "TDD", 
            "Modified a production file without modifying a test file in the last 5 minutes.",
            "Write or update a test file alongside your changes."
        )
        return True
    return False

def check_kiss(filepath, rel_filepath, content):
    if not filepath.endswith('.py'):
        return False
    try:
        tree = ast.parse(content)
        visitor = ComplexityVisitor()
        visitor.visit(tree)
        if visitor.violations:
            report_violation(
                rel_filepath,
                "KISS",
                "; ".join(visitor.violations),
                f"Refactor to keep functions under {MAX_LINES} lines and {MAX_COMPLEXITY} complexity."
            )
            return True
    except SyntaxError:
        pass
    return False

def check_dry(rel_filepath, lines):
    valid_hashes = [hash(normalize_line(l)) for l in lines if normalize_line(l)]
    for i in range(len(valid_hashes) - WINDOW_SIZE + 1):
        w_hash = hash(tuple(valid_hashes[i:i+WINDOW_SIZE]))
        if w_hash in DRY_INDEX:
            other_files = list(DRY_INDEX[w_hash])
            if other_files:
                report_violation(
                    rel_filepath,
                    "DRY",
                    f"Duplicate {WINDOW_SIZE}-line block found in {other_files[0]}.",
                    "Refactor the duplicated logic into a shared helper."
                )
                return True
    return False

def process_file_checks(filepath, last_test_mod_time):
    if not os.path.exists(filepath) or not filepath.endswith(FILE_EXTS):
        return False
        
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    rel_filepath = os.path.relpath(filepath, start=repo_root)
    
    if 'test' in os.path.basename(filepath).lower():
        return False

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
            lines = content.splitlines()
    except Exception:
        return False

    v_tdd = check_tdd(rel_filepath, last_test_mod_time)
    v_kiss = check_kiss(filepath, rel_filepath, content)
    v_dry = check_dry(rel_filepath, lines)
    return v_tdd or v_kiss or v_dry

def main():
    files_to_check = sys.argv[1:]
    if not files_to_check:
        print("Usage: agent_guard.py <file1> <file2> ...")
        sys.exit(0)
        
    build_dry_index(exclude_files=files_to_check)
    last_test_mod_time = get_last_test_mod_time()
    
    for filepath in files_to_check:
        if os.path.exists(filepath) and filepath.endswith(FILE_EXTS):
            if 'test' in os.path.basename(filepath).lower():
                last_test_mod_time = time.time()
                break
                
    violations_found = False
    for filepath in files_to_check:
        if process_file_checks(filepath, last_test_mod_time):
            violations_found = True
                    
    if violations_found:
        sys.exit(1)

if __name__ == "__main__":
    main()
