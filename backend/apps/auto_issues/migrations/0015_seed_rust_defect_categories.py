from django.db import migrations


def seed_categories(apps, schema_editor):
    category = apps.get_model("auto_issues", "AutoIssueCategory")
    rows = (
        ("runtime-pressure", "Runtime pressure", "Host CPU, memory, disk, or restart pressure found by speccheck.", 126),
        ("hardware-recalibration", "Hardware recalibration", "Host fingerprint changed and performance baselines need review.", 127),
        ("coverage-gap", "Coverage gap", "Untested lines or branches found by speccheck coverage import.", 128),
        ("mutation-survivor", "Mutation survivor", "A code mutation survived the test suite.", 129),
    )
    for key, label, description, order in rows:
        category.objects.get_or_create(
            key=key,
            defaults={
                "label": label,
                "description": description,
                "sort_order": order,
            },
        )


class Migration(migrations.Migration):
    dependencies = [
        ("auto_issues", "0014_add_sonarqube_source"),
    ]

    operations = [
        migrations.RunPython(seed_categories, migrations.RunPython.noop),
    ]
