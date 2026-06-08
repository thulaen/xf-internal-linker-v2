import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "xf_internal_linker.settings")
django.setup()

from apps.auto_issues.models import AutoIssue

sources = [
    "agent", "glitchtip", "pyroscope", "tempo",
    "loki", "faro", "mutation", "fuzz", "contract", "gh_ci"
]

subagent_tasks = [[] for _ in range(8)]
task_idx = 0
picked_ids = []

for source in sources:
    issues = list(AutoIssue.objects.filter(status="open", source=source).order_by("-priority_score")[:3])
    for issue in issues:
        subagent_tasks[task_idx % 8].append(f"#{issue.id} [{issue.source}] {issue.title} - {issue.description}")
        picked_ids.append(f"#{issue.id}")
        task_idx += 1

print("Picked IDs:", ", ".join(picked_ids))
print("-" * 40)
for i, tasks in enumerate(subagent_tasks):
    print(f"Subagent {i+1} Tasks:")
    for task in tasks:
        print(f"  {task}")
