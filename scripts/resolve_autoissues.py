import os
import sys
import django
from django.utils import timezone

sys.path.append('backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
django.setup()

from apps.auto_issues.models import AutoIssue

issue_ids = [21419, 21416, 21413, 21410, 21407, 21405]
issues = AutoIssue.objects.filter(id__in=issue_ids)

for issue in issues:
    issue.status = 'resolved'
    issue.resolved_at = timezone.now()
    if 'agent_progress' in issue.title:
        issue.lessons_learned = "Trap: agent_progress was missing unit tests for progress reporter.\nFix shape: Add unit tests with pytest covering edge cases like empty state and parsing."
    elif 'agent_guard_daemon' in issue.title:
        issue.lessons_learned = "Trap: watchdog requires proper mocking in tests to avoid host-dependent behavior.\nFix shape: Mock watchdog and django imports to test watchdog event handlers."
    elif 'agent_guard.py' in issue.title:
        issue.lessons_learned = "Trap: Missing unit tests for agent_guard.\nFix shape: Unit tests were already added in a previous session or by a previous agent."
    elif '_rules_sync_helpers.py' in issue.title:
        issue.lessons_learned = "Trap: Unicode characters (emdash) require correct matching in parsed lines.\nFix shape: Added tests that use correct unicode emdash."
    elif 'attrouted_client' in issue.title:
        issue.lessons_learned = "Trap: gRPC client requires sidecars_channel and load_service_stubs mocking.\nFix shape: Patched sidecars_channel context manager and load_service_stubs."
    elif '__init__.py' in issue.title:
        issue.lessons_learned = "Trap: Autoissue raised for an empty init file.\nFix shape: Verified it contains only docstrings; no functional test needed."
    else:
        issue.lessons_learned = "Trap: Missing test case.\nFix shape: Added missing test coverage."
    
    issue.save()
    print(f"Resolved {issue.id}: {issue.title}")
