import os
import subprocess
import json
import tempfile

def run_speccheck(*args):
    """Run speccheck via the compiled binary and return the result."""
    bin_path = "/opt/xf/compiled/active/speccheck"
    cmd = [bin_path] + list(args)
    return subprocess.run(cmd, capture_output=True, text=True)

def test_speccheck_no_args():
    res = run_speccheck()
    assert res.returncode == 0
    data = json.loads(res.stdout)
    assert "parsed_behaviors" in data
    assert data["parsed_behaviors"] == []

def test_speccheck_scan_valid():
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
        f.write("Given a test spec\nWhen it runs\nThen it passes\n")
        f.close()
        try:
            res = run_speccheck("scan", f.name)
            assert res.returncode == 0
            data = json.loads(res.stdout)
            assert "parsed_behaviors" in data
            assert len(data["parsed_behaviors"]) > 0
        finally:
            os.remove(f.name)

def test_speccheck_scan_invalid():
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
        f.write("Given a test spec\nWhen it runs with no then\n")
        f.close()
        try:
            res = run_speccheck("scan", f.name)
            assert res.returncode != 0
            assert "FAIL speccheck" in res.stderr
        finally:
            os.remove(f.name)

def test_speccheck_find_bugs():
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write("def view(request):\n    return pickle.loads(request.body)\n")
        f.close()
        try:
            res = run_speccheck("find-bugs", f.name)
            assert res.returncode == 0
            data = json.loads(res.stdout)
            assert "bug_candidates" in data
        finally:
            os.remove(f.name)

def test_speccheck_coverage_gaps_unknown_format():
    res = run_speccheck("coverage-gaps", "--format", "unknown", "cov.info")
    assert res.returncode != 0
    assert "FAIL speccheck: unknown coverage format `unknown`" in res.stderr

