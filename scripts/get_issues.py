#!/usr/bin/env python
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.config.settings')
import django
django.setup()
from apps.auto_issues.models import AutoIssue

for issue_id in [22844, 23023, 23024]:
    try:
        issue = AutoIssue.objects.get(id=issue_id)
        print(f'Issue #{issue_id}:')
        print(f'  Source: {issue.source}')
        print(f'  Category: {issue.category}')
        print(f'  Title: {issue.title}')
        # List all field names
        for field in issue._meta.get_fields():
            if not field.name.startswith('_'):
                try:
                    val = getattr(issue, field.name)
                    if isinstance(val, str) and len(val) > 300:
                        print(f'  {field.name}: {val[:300]}...')
                    elif val and not callable(val):
                        print(f'  {field.name}: {val}')
                except:
                    pass
        print()
    except AutoIssue.DoesNotExist:
        print(f'Issue #{issue_id}: NOT FOUND')
