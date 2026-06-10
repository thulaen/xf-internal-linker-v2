#!/usr/bin/env python3
"""Unit tests for agent_guard_daemon.py."""
import unittest
from unittest.mock import patch, MagicMock
import os
import sys

# Mock watchdog and agent_guard before importing
sys.modules['watchdog'] = MagicMock()
sys.modules['watchdog.events'] = MagicMock()
sys.modules['watchdog.events'].FileSystemEventHandler = object
sys.modules['watchdog.observers'] = MagicMock()

# Mock django to prevent DB connection attempt during agent_guard import
sys.modules['django'] = MagicMock()
sys.modules['apps'] = MagicMock()
sys.modules['apps.auto_issues'] = MagicMock()
sys.modules['apps.auto_issues.models'] = MagicMock()

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import agent_guard_daemon

class TestGuardEventHandler(unittest.TestCase):
    def setUp(self):
        self.handler = agent_guard_daemon.GuardEventHandler(debounce_seconds=1.0)
        
    @patch('agent_guard.FILE_EXTS', ('.py',))
    def test_should_check_wrong_extension(self):
        self.assertFalse(self.handler.should_check("some_file.txt", now=10.0))

    @patch('agent_guard.FILE_EXTS', ('.py',))
    def test_should_check_debouncing_behavior(self):
        # Current logic:
        # if now - last_seen > debounce: return False
        
        # Test 1: path not seen (0.0) -> diff is 10.0 > 1.0 -> False
        self.assertFalse(self.handler.should_check("test.py", now=10.0))
        
        # Manually set last_seen so diff <= debounce
        self.handler._last_seen["test.py"] = 10.0
        self.assertTrue(self.handler.should_check("test.py", now=10.5))
        # It should update _last_seen
        self.assertEqual(self.handler._last_seen["test.py"], 10.5)

    @patch('agent_guard_daemon.GuardEventHandler.should_check')
    @patch('agent_guard.build_dry_index')
    @patch('agent_guard.get_last_test_mod_time')
    @patch('agent_guard.process_file_checks')
    def test_handle(self, mock_process, mock_get_time, mock_build, mock_should_check):
        mock_should_check.return_value = False
        self.handler.handle("test.py")
        mock_build.assert_not_called()
        
        mock_should_check.return_value = True
        mock_get_time.return_value = 12345
        self.handler.handle("test.py")
        mock_build.assert_called_once_with(exclude_files=["test.py"])
        mock_process.assert_called_once_with("test.py", 12345)

    @patch('agent_guard_daemon.GuardEventHandler.handle')
    def test_on_events(self, mock_handle):
        class Event:
            def __init__(self, src_path, is_directory):
                self.src_path = src_path
                self.is_directory = is_directory
                
        self.handler.on_modified(Event("test.py", True))
        mock_handle.assert_not_called()
        
        self.handler.on_modified(Event("test.py", False))
        mock_handle.assert_called_with("test.py")
        
        mock_handle.reset_mock()
        self.handler.on_created(Event("test.py", False))
        mock_handle.assert_called_with("test.py")

    @patch('os.path.isdir')
    @patch('agent_guard.WATCH_DIRS', ['valid_dir', 'invalid_dir'])
    def test_watched_dirs(self, mock_isdir):
        mock_isdir.side_effect = lambda d: d == 'valid_dir'
        dirs = agent_guard_daemon.watched_dirs()
        self.assertEqual(dirs, ['valid_dir'])

if __name__ == '__main__':
    unittest.main()
