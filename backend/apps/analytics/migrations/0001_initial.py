"""Analytics app initial migration."""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = [
        ("content", "0001_initial"),
        ("suggestions", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="SearchMetric",
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
                    "date",
                    models.DateField(
                        db_index=True,
                        help_text="The date these metrics were recorded for.",
                    ),
                ),
                (
                    "source",
                    models.CharField(
                        choices=[
                            ("gsc", "Google Search Console"),
                            ("ga4", "Google Analytics 4"),
                        ],
                        help_text="Whether data came from GSC or GA4.",
                        max_length=10,
                    ),
                ),
                (
                    "impressions",
                    models.IntegerField(default=0, help_text="Search impressions."),
                ),
                ("clicks", models.IntegerField(default=0, help_text="Search clicks.")),
                (
                    "ctr",
                    models.FloatField(default=0.0, help_text="Click-through rate."),
                ),
                (
                    "average_position",
                    models.FloatField(
                        blank=True, null=True, help_text="Average ranking position."
                    ),
                ),
                (
                    "query",
                    models.CharField(
                        blank=True, help_text="Top search query.", max_length=500
                    ),
                ),
                (
                    "page_views",
                    models.IntegerField(default=0, help_text="GA4 page views."),
                ),
                ("sessions", models.IntegerField(default=0, help_text="GA4 sessions.")),
                (
                    "avg_engagement_time",
                    models.FloatField(
                        default=0.0, help_text="GA4 average engagement time."
                    ),
                ),
                (
                    "bounce_rate",
                    models.FloatField(
                        blank=True, null=True, help_text="GA4 bounce rate."
                    ),
                ),
                (
                    "content_item",
                    models.ForeignKey(
                        help_text="The content item these metrics belong to.",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="search_metrics",
                        to="content.contentitem",
                    ),
                ),
            ],
            options={
                "verbose_name": "Search Metric",
                "verbose_name_plural": "Search Metrics",
                "unique_together": {("content_item", "date", "source", "query")},
            },
        ),
        migrations.AddIndex(
            model_name="searchmetric",
            index=models.Index(
                fields=["date", "source"], name="analytics_sm_date_source_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="searchmetric",
            index=models.Index(
                fields=["content_item", "date"], name="analytics_sm_ci_date_idx"
            ),
        ),
        migrations.CreateModel(
            name="ImpactReport",
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
                    "metric_type",
                    models.CharField(
                        choices=[
                            ("impressions", "Impressions"),
                            ("clicks", "Clicks"),
                            ("position", "Average Position"),
                            ("page_views", "Page Views"),
                            ("sessions", "Sessions"),
                            ("ctr", "Click-Through Rate"),
                        ],
                        help_text="Which metric is being compared.",
                        max_length=30,
                    ),
                ),
                (
                    "before_value",
                    models.FloatField(
                        help_text="Average metric in the 'before' window."
                    ),
                ),
                (
                    "after_value",
                    models.FloatField(
                        help_text="Average metric in the 'after' window."
                    ),
                ),
                (
                    "before_date_range",
                    models.JSONField(
                        help_text="Before window: {'start': 'YYYY-MM-DD', 'end': 'YYYY-MM-DD'}."
                    ),
                ),
                (
                    "after_date_range",
                    models.JSONField(
                        help_text="After window: {'start': 'YYYY-MM-DD', 'end': 'YYYY-MM-DD'}."
                    ),
                ),
                (
                    "delta_percent",
                    models.FloatField(
                        help_text="Percentage change. Positive = improvement."
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True, help_text="When this report was generated."
                    ),
                ),
                (
                    "suggestion",
                    models.ForeignKey(
                        help_text="The applied suggestion this report measures.",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="impact_reports",
                        to="suggestions.suggestion",
                    ),
                ),
            ],
            options={
                "verbose_name": "Impact Report",
                "verbose_name_plural": "Impact Reports",
                "ordering": ["-created_at"],
            },
        ),
    ]
