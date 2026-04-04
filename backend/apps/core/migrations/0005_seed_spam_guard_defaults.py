"""Seed default AppSetting rows for the three spam-guard limits.

These are the patent-backed defaults established during the FR-016
spam-guard research (Ntoulas et al. 2006, US8380722B2, US8577893B1,
Google 2024 API leak):

* spam_guards.max_existing_links_per_host = 3
* spam_guards.max_anchor_words            = 4
* spam_guards.paragraph_window            = 3

Use update_or_create so that existing installs that have already
customised these values are not overwritten.
"""

from django.db import migrations


SPAM_GUARD_ROWS = [
    {
        "key": "spam_guards.max_existing_links_per_host",
        "value": "3",
        "value_type": "int",
        "category": "anchor",
        "description": (
            "Maximum number of existing outgoing body links a host page may already "
            "carry before the pipeline skips it entirely. Default 3 — Ntoulas et al. "
            "anchor-word fraction research (US20060184500A1) and the 2024 Google API "
            "leak (droppedLocalAnchorCount field)."
        ),
    },
    {
        "key": "spam_guards.max_anchor_words",
        "value": "4",
        "value_type": "int",
        "category": "anchor",
        "description": (
            "Maximum number of words allowed in a suggested anchor phrase. "
            "Default 4 — Google recommends 2–5 words in official link best-practices; "
            "US8380722B2 confirms anchors are 'usually short and descriptive'; "
            "empirical average of natural anchor text is ~4.85 words."
        ),
    },
    {
        "key": "spam_guards.paragraph_window",
        "value": "3",
        "value_type": "int",
        "category": "anchor",
        "description": (
            "Sentence-position window for paragraph-cluster detection. "
            "Two suggestions within this many sentence positions of each other on "
            "the same host page are treated as the same paragraph — only the "
            "higher-scoring one is kept. Default 3 — US8577893B1 (Google ±5-word "
            "context window) and Google's documented guidance against adjacent links."
        ),
    },
]


def seed_spam_guard_defaults(apps, schema_editor):
    AppSetting = apps.get_model("core", "AppSetting")
    for row in SPAM_GUARD_ROWS:
        AppSetting.objects.update_or_create(
            key=row["key"],
            defaults={
                "value": row["value"],
                "value_type": row["value_type"],
                "category": row["category"],
                "description": row["description"],
                "is_secret": False,
            },
        )


def unseed_spam_guard_defaults(apps, schema_editor):
    AppSetting = apps.get_model("core", "AppSetting")
    AppSetting.objects.filter(
        key__in=[row["key"] for row in SPAM_GUARD_ROWS]
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0004_alter_appsetting_category"),
    ]

    operations = [
        migrations.RunPython(
            seed_spam_guard_defaults,
            reverse_code=unseed_spam_guard_defaults,
        ),
    ]
