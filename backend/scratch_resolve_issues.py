import django
django.setup()
from apps.auto_issues.models import AutoIssue
from django.utils import timezone

issues_to_resolve = [23044, 1838, 22510]

lessons = {
    23044: "Trap: `RuntimeWarning` from database access during `AppConfig.ready()` causes high error rates in logs for `agent-guard`, triggering Loki bursts. Fix shape: Wrapped `Plugin.objects.filter()` in `loader.py` with `warnings.catch_warnings()` to explicitly suppress the `RuntimeWarning` when we deliberately query enabled plugins at startup.",
    1838: "Trap: Grafana complains loudly about missing `plugins` and `alerting` directories in `./grafana/provisioning`, emitting WARN/ERROR logs that trigger Loki burst alerts. Fix shape: Created the missing directories with `.gitkeep` files to satisfy Grafana and silence the warnings.",
    22510: "Trap: `celery-beat` logs were flooded with `RuntimeWarning: Accessing the database during app initialization is discouraged`, causing Loki bursts. The warning happens because `load_enabled_plugins()` queries the DB in `ready()`. Fix shape: Suppressed the `RuntimeWarning` specifically around the plugin query in `loader.py` using `warnings.filterwarnings`."
}

for issue_id in issues_to_resolve:
    i = AutoIssue.objects.get(id=issue_id)
    i.lessons_learned = lessons[issue_id]
    i.status = 'resolved'
    i.resolved_at = timezone.now()
    i.save()
    print(f"Resolved AutoIssue #{issue_id}")
