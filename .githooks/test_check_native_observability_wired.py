#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

import importlib.util

hook_path = Path(__file__).resolve().parent / "check-native-observability-wired.py"
spec = importlib.util.spec_from_file_location("check_native_observability_wired", hook_path)
hook = importlib.util.module_from_spec(spec)
sys.modules["check_native_observability_wired"] = hook
spec.loader.exec_module(hook)

class TestCheckNativeObservability(unittest.TestCase):
    @patch("check_native_observability_wired.EXTENSIONS_DIR")
    def test_missing_directory_skips(self, mock_dir):
        mock_dir.exists.return_value = False
        self.assertEqual(hook.check_native_observability(), 0)

    @patch("check_native_observability_wired.EXTENSIONS_DIR")
    def test_missing_files_skips(self, mock_dir):
        mock_dir.exists.return_value = True
        mock_dir.is_dir.return_value = True
        mock_dir.rglob.return_value = []
        self.assertEqual(hook.check_native_observability(), 0)

    @patch("check_native_observability_wired.EXTENSIONS_DIR")
    def test_passing_configuration(self, mock_dir):
        mock_dir.exists.return_value = True
        mock_dir.is_dir.return_value = True
        
        mock_file = MagicMock()
        mock_file.read_text.return_value = """
        #include <perfetto.h>
        // gwp_asan enabled
        // buffer_size_kb = 4096
        // SampleRate = 5000
        // MaxSimultaneousAllocations = 16
        """
        mock_dir.rglob.side_effect = lambda ext: [mock_file] if ext == "*.cpp" else []
        
        self.assertEqual(hook.check_native_observability(), 0)

    @patch("check_native_observability_wired.EXTENSIONS_DIR")
    def test_failing_configuration(self, mock_dir):
        mock_dir.exists.return_value = True
        mock_dir.is_dir.return_value = True
        
        mock_file = MagicMock()
        mock_file.read_text.return_value = """
        #include <perfetto.h>
        // gwp_asan enabled
        // buffer_size_kb = 1024
        // SampleRate = 1000
        // MaxSimultaneousAllocations = 4
        """
        mock_dir.rglob.side_effect = lambda ext: [mock_file] if ext == "*.cpp" else []
        
        self.assertEqual(hook.check_native_observability(), 1)

if __name__ == "__main__":
    unittest.main()
