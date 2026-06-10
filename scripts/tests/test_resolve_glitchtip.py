"""Tests for scripts/resolve_glitchtip.py."""

import sys
from unittest import TestCase, mock

# Setup mocks before importing to prevent hitting real Django setup or database
mock_django = mock.MagicMock()
mock_timezone = mock.MagicMock()
mock_auto_issue_model = mock.MagicMock()

# Set a predictable time
FIXED_TIME = "2026-06-10T00:00:00Z"
mock_timezone.now.return_value = FIXED_TIME

modules_to_patch = {
    "django": mock_django,
    "django.utils": mock.MagicMock(timezone=mock_timezone),
    "apps": mock.MagicMock(),
    "apps.auto_issues": mock.MagicMock(),
    "apps.auto_issues.models": mock.MagicMock(AutoIssue=mock_auto_issue_model),
}

with mock.patch.dict(sys.modules, modules_to_patch):
    import scripts.resolve_glitchtip as rg

class TestResolveGlitchtip(TestCase):
    def setUp(self) -> None:
        """Reset mocks before each test."""
        mock_auto_issue_model.objects.filter.reset_mock()
        
    def test_main_resolves_multiple_issues(self) -> None:
        """Test that multiple matching issues are correctly updated and saved."""
        issue_1 = mock.MagicMock(id=22999)
        issue_2 = mock.MagicMock(id=23000)
        
        mock_auto_issue_model.objects.filter.return_value = [issue_1, issue_2]
        
        with mock.patch.dict(sys.modules, modules_to_patch), mock.patch("builtins.print") as mock_print:
            rg.main()
            
        # Verify filtering queried the expected exact IDs
        mock_auto_issue_model.objects.filter.assert_called_once_with(id__in=[22999, 23000, 23001])
        
        # Verify updates on issue 1
        self.assertEqual(issue_1.status, "resolved")
        self.assertIn("Trap: Something was wrong with imports", issue_1.lessons_learned)
        self.assertEqual(issue_1.resolved_at, FIXED_TIME)
        issue_1.save.assert_called_once()
        
        # Verify updates on issue 2
        self.assertEqual(issue_2.status, "resolved")
        self.assertIn("Fix shape: Adjusted module path", issue_2.lessons_learned)
        self.assertEqual(issue_2.resolved_at, FIXED_TIME)
        issue_2.save.assert_called_once()
        
        # Verify standard output
        mock_print.assert_any_call("Resolved #22999")
        mock_print.assert_any_call("Resolved #23000")
        self.assertEqual(mock_print.call_count, 2)
        
    def test_main_handles_empty_queryset(self) -> None:
        """Test that the script gracefully does nothing if no issues are found."""
        mock_auto_issue_model.objects.filter.return_value = []
        
        with mock.patch.dict(sys.modules, modules_to_patch), mock.patch("builtins.print") as mock_print:
            rg.main()
            
        # Filter is still called
        mock_auto_issue_model.objects.filter.assert_called_once_with(id__in=[22999, 23000, 23001])
        
        # Nothing should be printed or saved
        mock_print.assert_not_called()
