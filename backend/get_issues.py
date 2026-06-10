import os
import sys
import django

sys.path.append('backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from apps.auto_issues.models import AutoIssue

issue_ids = [21419, 21416, 21413, 21410, 21407, 21405]
issues = AutoIssue.objects.filter(id__in=issue_ids)
for issue in issues:
    print(f"ID: {issue.id}")
    print(f"Title: {issue.title}")
    print(f"Source: {issue.source}")
    print(f"Description: {issue.description}")
    print("-" * 40)
