"""
Core app initial migration — creates the AppSetting table.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="AppSetting",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, help_text="Timestamp when this record was created.")),
                ("updated_at", models.DateTimeField(auto_now=True, help_text="Timestamp when this record was last modified.")),
                ("key", models.CharField(help_text="Unique setting key, e.g. 'pipeline.max_links_per_host'.", max_length=200, unique=True)),
                ("value", models.TextField(help_text="Stored value (always text; cast using value_type).")),
                ("value_type", models.CharField(choices=[("str", "Text"), ("int", "Integer"), ("float", "Decimal"), ("bool", "True / False"), ("json", "JSON")], default="str", help_text="Data type of the value — used to cast when reading.", max_length=20)),
                ("category", models.CharField(choices=[("general", "General"), ("ml", "ML / AI"), ("sync", "Sync"), ("performance", "Performance"), ("api", "API Keys"), ("anchor", "Anchor Policy")], db_index=True, default="general", help_text="Grouping shown in the admin sidebar.", max_length=50)),
                ("description", models.CharField(help_text="Human-readable description of what this setting controls.", max_length=500)),
                ("is_secret", models.BooleanField(default=False, help_text="If True, the value is masked in the admin UI (e.g. API keys).")),
            ],
            options={
                "verbose_name": "App Setting",
                "verbose_name_plural": "App Settings",
                "ordering": ["category", "key"],
            },
        ),
    ]
