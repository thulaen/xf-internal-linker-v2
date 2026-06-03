import os
import sys
import time
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import agent_guard

@pytest.fixture
def mock_checker():
    with patch('agent_guard.report_violation') as mock_report, \
         patch('agent_guard.AutoIssue', MagicMock()) as mock_autoissue:
        agent_guard.DRY_INDEX.clear()
        yield mock_report

def test_tdd_guard_violation(mock_checker, tmp_path):
    mock_report = mock_checker
    
    prod_file = tmp_path / "main.py"
    prod_file.write_text("def my_func():\n    pass")
    
    with patch('agent_guard.get_last_test_mod_time', return_value=time.time() - 600):
        with patch('sys.argv', ['agent_guard.py', str(prod_file)]):
            with patch('agent_guard.build_dry_index'):
                with pytest.raises(SystemExit) as excinfo:
                    agent_guard.main()
                assert excinfo.value.code == 1
        
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(agent_guard.__file__)))
    rel_prod = os.path.relpath(str(prod_file), start=repo_root)
    
    mock_report.assert_called_with(
        rel_prod,
        "TDD",
        "Modified a production file without modifying a test file in the last 5 minutes.",
        "Write or update a test file alongside your changes."
    )

def test_tdd_guard_allowed(mock_checker, tmp_path):
    mock_report = mock_checker
    
    prod_file = tmp_path / "main.py"
    prod_file.write_text("def my_func():\n    pass")
    
    with patch('agent_guard.get_last_test_mod_time', return_value=time.time() - 60):
        with patch('sys.argv', ['agent_guard.py', str(prod_file)]):
            with patch('agent_guard.build_dry_index'):
                agent_guard.main()
        
    mock_report.assert_not_called()

def test_kiss_guard_complexity_violation(mock_checker, tmp_path):
    mock_report = mock_checker
    
    prod_file = tmp_path / "main.py"
    complex_code = """
def complex_func():
    if 1:
        if 2:
            if 3:
                if 4:
                    if 5:
                        if 6:
                            if 7:
                                if 8:
                                    if 9:
                                        if 10:
                                            pass
"""
    prod_file.write_text(complex_code)
    
    with patch('agent_guard.get_last_test_mod_time', return_value=time.time()):
        with patch('sys.argv', ['agent_guard.py', str(prod_file)]):
            with patch('agent_guard.build_dry_index'):
                with pytest.raises(SystemExit) as excinfo:
                    agent_guard.main()
                assert excinfo.value.code == 1
        
    mock_report.assert_called_once()
    assert mock_report.call_args[0][1] == "KISS"
    assert "complexity" in mock_report.call_args[0][2]

def test_dry_guard_violation(mock_checker, tmp_path):
    mock_report = mock_checker
    
    lines = ["print(1)", "print(2)", "print(3)", "print(4)", "print(5)", "print(6)"]
    w_hash = hash(tuple([hash(agent_guard.normalize_line(l)) for l in lines]))
    agent_guard.DRY_INDEX[w_hash].add("backend/other_file.py")
    
    prod_file = tmp_path / "main.py"
    prod_file.write_text("\n".join(lines))
    
    with patch('agent_guard.get_last_test_mod_time', return_value=time.time()):
        with patch('sys.argv', ['agent_guard.py', str(prod_file)]):
            with patch('agent_guard.build_dry_index'):
                with pytest.raises(SystemExit) as excinfo:
                    agent_guard.main()
                assert excinfo.value.code == 1
        
    mock_report.assert_called_once()
    assert mock_report.call_args[0][1] == "DRY"
    assert "Duplicate 6-line block" in mock_report.call_args[0][2]

def test_no_edits_made(mock_checker, tmp_path):
    # Ensure it doesn't try to git checkout
    mock_report = mock_checker
    
    prod_file = tmp_path / "main.py"
    prod_file.write_text("def my_func():\n    pass")
    
    with patch('agent_guard.get_last_test_mod_time', return_value=time.time() - 600):
        with patch('sys.argv', ['agent_guard.py', str(prod_file)]):
            with patch('subprocess.run') as mock_run:
                with patch('agent_guard.build_dry_index'):
                    with pytest.raises(SystemExit):
                        agent_guard.main()
                    mock_run.assert_not_called()
