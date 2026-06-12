import django
django.setup()
from apps.auto_issues.models import AutoIssue
from django.utils import timezone

fixes = {
    21096: 'Trap: File tune_clustering.py was deleted in previous commit. Fix shape: No code needed, marking resolved.',
    21094: 'Trap: No unit test existed for session_start_payload.py. Fix shape: Added SimpleTestCase mocking read_helper_payload to verify success and error states.',
    21092: 'Trap: No unit test existed for rotate_scope_log.py. Fix shape: Added SimpleTestCase verifying empty, missing, and successful log rotation with TemporaryDirectory.'
}

for ID, lesson in fixes.items():
    i = AutoIssue.objects.get(id=ID)
    i.lessons_learned = lesson
    i.status = 'resolved'
    i.resolved_at = timezone.now()
    i.save()
    print(f"Resolved {ID}")
