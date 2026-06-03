from apps.auto_issues.models import AutoIssue
from django.utils import timezone

issues = {
    2025: "Trap: C++ module exported function with incorrect name vs Python wrapper expectation. Fix shape: Renamed m.def() in scoring.cpp to match Python caller.",
    1437: "Trap: Celery task expected a zero-argument function that was deferred but not stubbed. Fix shape: Added a stub function that logs the deferral.",
    2024: "Trap: Exponential backoff raised exceptions as ERROR, filling GlitchTip logs. Fix shape: Downgraded logger.error to logger.warning.",
    2023: "Trap: API connection errors caused Celery task crash. Fix shape: Caught RequestException explicitly in tasks_link_health to publish graceful failure.",
    1337: "Trap: connection.close() called unconditionally inside task loops, crashing in atomic test blocks. Fix shape: Wrapped in if not connection.in_atomic_block globally.",
    1339: "Trap: connection.close() called unconditionally inside task loops, crashing in atomic test blocks. Fix shape: Wrapped in if not connection.in_atomic_block globally.",
}

qs = AutoIssue.objects.filter(id__in=issues.keys())
count = 0
for i in qs:
    i.status = 'resolved'
    i.resolved_at = timezone.now()
    i.lessons_learned = issues[i.id]
    i.save()
    count += 1
print(f"Resolved {count} issues.")
