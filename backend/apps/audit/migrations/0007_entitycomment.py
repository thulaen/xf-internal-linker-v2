# Phase DC / Gaps 128 + 129 — EntityComment table with @mention cache.

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("audit", "0006_entityversion"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="EntityComment",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("target_type", models.CharField(db_index=True, max_length=60)),
                ("target_id", models.CharField(db_index=True, max_length=100)),
                ("body", models.TextField()),
                ("mentions", models.JSONField(blank=True, default=list)),
                ("resolved", models.BooleanField(db_index=True, default=False)),
                (
                    "author",
                    models.ForeignKey(
                        null=True,
                        on_delete=models.deletion.SET_NULL,
                        related_name="entity_comments",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "parent",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=models.deletion.CASCADE,
                        related_name="replies",
                        to="audit.entitycomment",
                    ),
                ),
            ],
            options={
                "verbose_name": "Entity Comment",
                "verbose_name_plural": "Entity Comments",
                "ordering": ["created_at"],
                "indexes": [
                    models.Index(
                        fields=["target_type", "target_id", "created_at"],
                        name="audit_ec_target_idx",
                    ),
                    models.Index(
                        fields=["resolved", "-created_at"],
                        name="audit_ec_resolved_idx",
                    ),
                ],
            },
        ),
    ]
