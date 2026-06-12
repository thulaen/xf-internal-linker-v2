import django
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
from apps.auto_issues.models import AutoIssue
from django.utils import timezone

for i in [19043, 19041, 19040]:
    issue = AutoIssue.objects.get(id=i)
    if i == 19040:
        issue.lessons_learned = 'Trap: The string literal "glitchtip" in the filteredErrors source exclusion was not covered by any test that explicitly asserted the length of the filtered list, allowing it to survive if mutated to an empty string. Fix shape: Added a test that asserts filteredErrors explicitly excludes glitchtip source errors when selectedTabIndex is not ALL_TAB_INDEX.'
    else:
        issue.lessons_learned = 'Trap: ConditionalExpression and BooleanLiteral mutations inside filteredErrors for filterAcknowledged / filterJobType were uncovered in older versions but are now fully asserted by subsequent test additions in #23110/#23107. Fix shape: Verified existing test coverage is sufficient (tests assert list length excludes based on job type and acknowledged state).'
    issue.status = 'resolved'
    issue.resolved_at = timezone.now()
    issue.save()
