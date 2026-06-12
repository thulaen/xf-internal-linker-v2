import json
from apps.auto_issues.models import AutoIssue

issue_ids = [21241, 21243, 21245, 21248]
issues = AutoIssue.objects.filter(id__in=issue_ids).values('id', 'title', 'description', 'lessons_learned', 'status', 'priority_score', 'source')

print("=== DETAILS FOR TARGET AUTOISSUES ===")
for issue in issues:
    print(json.dumps(issue, indent=2, default=str))
