#!/usr/bin/env python3
"""Unit tests for _rules_sync_helpers.py."""
import unittest
from unittest.mock import patch, MagicMock
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _rules_sync_helpers

class TestRulesSyncHelpers(unittest.TestCase):
    def test_clean_yaml_value(self):
        self.assertEqual(_rules_sync_helpers._clean_yaml_value('"hello"'), 'hello')
        self.assertEqual(_rules_sync_helpers._clean_yaml_value('world'), 'world')

    def test_normalize_text(self):
        self.assertEqual(_rules_sync_helpers.normalize_text("abc\r\ndef  "), "abc\ndef\n")

    def test_extract_section(self):
        text = "some text\n**ABSOLUTE — Test**\nline 1\nline 2\n**PARAMOUNT — Next**\nend"
        extracted = _rules_sync_helpers.extract_section(text, "ABSOLUTE — Test**")
        self.assertEqual(extracted, "**ABSOLUTE — Test**\nline 1\nline 2\n")

    def test_replace_section(self):
        text = "some text\n**ABSOLUTE — Test**\nline 1\nline 2\n**PARAMOUNT — Next**\nend"
        replacement = "**ABSOLUTE — Test**\nnew line 1\n"
        replaced = _rules_sync_helpers.replace_section(text, "ABSOLUTE — Test**", replacement)
        expected = "some text\n**ABSOLUTE — Test**\nnew line 1\n**PARAMOUNT — Next**\nend\n"
        self.assertEqual(replaced, expected)

    def test_replace_section_append(self):
        text = "some text\n"
        replacement = "**ABSOLUTE — New**\nline\n"
        replaced = _rules_sync_helpers.replace_section(text, "ABSOLUTE — New**", replacement)
        expected = "some text\n\n**ABSOLUTE — New**\nline\n"
        self.assertEqual(replaced, expected)

if __name__ == '__main__':
    unittest.main()
