import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("content", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="SiloGroup",
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
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True,
                        help_text="Timestamp when this record was created.",
                    ),
                ),
                (
                    "updated_at",
                    models.DateTimeField(
                        auto_now=True,
                        help_text="Timestamp when this record was last modified.",
                    ),
                ),
                (
                    "name",
                    models.CharField(
                        help_text="Human-readable silo label shown in settings and review UI.",
                        max_length=200,
                        unique=True,
                    ),
                ),
                (
                    "slug",
                    models.SlugField(
                        help_text="Stable machine-friendly identifier for this silo group.",
                        max_length=200,
                        unique=True,
                    ),
                ),
                (
                    "description",
                    models.TextField(
                        blank=True,
                        help_text="Optional notes describing what belongs in this silo.",
                    ),
                ),
                (
                    "display_order",
                    models.IntegerField(
                        default=0, help_text="Sort order for silo management screens."
                    ),
                ),
            ],
            options={
                "verbose_name": "Silo Group",
                "verbose_name_plural": "Silo Groups",
                "ordering": ["display_order", "name"],
            },
        ),
        migrations.AddIndex(
            model_name="silogroup",
            index=models.Index(
                fields=["display_order", "name"], name="content_silo_display_5ef460_idx"
            ),
        ),
        migrations.AddField(
            model_name="scopeitem",
            name="silo_group",
            field=models.ForeignKey(
                blank=True,
                help_text="Optional topical silo assignment used by the ranking pipeline.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="scope_items",
                to="content.silogroup",
            ),
        ),
        migrations.AddIndex(
            model_name="scopeitem",
            index=models.Index(
                fields=["silo_group", "is_enabled"],
                name="content_scope_silo_0f7380_idx",
            ),
        ),
    ]
