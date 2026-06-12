from apps.auto_issues.models import AutoIssue
from django.utils import timezone

issue_ids = [21251, 21254, 21257, 21260, 21263, 21266]
issues = AutoIssue.objects.filter(id__in=issue_ids)

for issue in issues:
    if "Trap:" not in (issue.lessons_learned or ""):
        if issue.id == 21251:
            trap = "Trap: PeHelperDirective lacked component integration tests with Given/When/Then behavior."
            fix_shape = "Fix shape: Added integration test suite to pe-helper.directive.spec.ts proving matTooltip and data-pe-helper bindings with BDD naming."
        elif issue.id == 21254:
            trap = "Trap: GscInsightCardComponent tests did not use standard Given/When/Then behavior wording."
            fix_shape = "Fix shape: Refactored test descriptions in gsc-insight-card.component.spec.ts to follow BDD Given/When/Then standard."
        elif issue.id == 21257:
            trap = "Trap: GscKpiComponent tests lacked strict BDD naming conventions."
            fix_shape = "Fix shape: Updated gsc-kpi.component.spec.ts descriptions to Given/When/Then formats reflecting actual behavior."
        elif issue.id == 21260:
            trap = "Trap: GscMetricTilesComponent specs were written imperatively rather than behaviorally."
            fix_shape = "Fix shape: Applied Given/When/Then conventions to all spec descriptions in gsc-metric-tiles.component.spec.ts."
        elif issue.id == 21263:
            trap = "Trap: GscSummaryCardComponent tests missed BDD Given/When/Then standards."
            fix_shape = "Fix shape: Rewrote test suite descriptions in gsc-summary-card.component.spec.ts to use clear BDD structure."
        elif issue.id == 21266:
            trap = "Trap: SpikeInsightCardComponent testing lacked BDD formatting for its spec titles."
            fix_shape = "Fix shape: Converted spike-insight-card.component.spec.ts descriptions to Given/When/Then to align with test-case specs."
        else:
            trap = "Trap: Tests missing BDD conventions."
            fix_shape = "Fix shape: Updated tests to Given/When/Then."
            
        original_lesson = issue.lessons_learned or ""
        issue.lessons_learned = f"{trap} {fix_shape}\n\n{original_lesson}".strip()
    
    issue.status = 'resolved'
    issue.resolved_at = timezone.now()
    issue.save()

print("Resolved AutoIssues 21251, 21254, 21257, 21260, 21263, 21266 successfully.")