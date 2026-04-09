"""Audit app initial migration."""

from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = []

    operations = [
        migrations.CreateModel(
            name="AuditEntry",
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
                    "action",
                    models.CharField(
                        choices=[
                            ("approve", "Approved suggestion"),
                            ("reject", "Rejected suggestion"),
                            ("apply", "Marked as applied"),
                            ("verify", "Verified live link"),
                            ("edit_anchor", "Edited anchor text"),
                            ("mark_stale", "Marked as stale"),
                            ("supersede", "Superseded"),
                            ("note", "Note added"),
                            ("setting_change", "Setting changed"),
                            ("plugin_toggle", "Plugin enabled/disabled"),
                            ("pipeline_start", "Pipeline run started"),
                            ("pipeline_complete", "Pipeline run completed"),
                            ("sync_start", "Sync started"),
                            ("sync_complete", "Sync completed"),
                        ],
                        db_index=True,
                        help_text="What type of action was taken.",
                        max_length=30,
                    ),
                ),
                (
                    "target_type",
                    models.CharField(
                        help_text="The model/entity type affected.", max_length=50
                    ),
                ),
                (
                    "target_id",
                    models.CharField(
                        help_text="The primary key of the affected record.",
                        max_length=100,
                    ),
                ),
                (
                    "detail",
                    models.JSONField(
                        default=dict,
                        help_text="Extra context: previous value, new value, reason.",
                    ),
                ),
                (
                    "ip_address",
                    models.GenericIPAddressField(
                        blank=True,
                        null=True,
                        help_text="IP address of the user who took this action.",
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True,
                        db_index=True,
                        help_text="When this action was recorded.",
                    ),
                ),
            ],
            options={
                "verbose_name": "Audit Entry",
                "verbose_name_plural": "Audit Trail",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="auditentry",
            index=models.Index(
                fields=["target_type", "target_id"], name="audit_target_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="auditentry",
            index=models.Index(
                fields=["action", "created_at"], name="audit_action_date_idx"
            ),
        ),
        migrations.CreateModel(
            name="ReviewerScorecard",
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
                    "period_start",
                    models.DateField(help_text="Start date of the reporting period."),
                ),
                (
                    "period_end",
                    models.DateField(help_text="End date of the reporting period."),
                ),
                (
                    "total_reviewed",
                    models.IntegerField(
                        default=0, help_text="Total suggestions reviewed."
                    ),
                ),
                (
                    "approved_count",
                    models.IntegerField(default=0, help_text="Number approved."),
                ),
                (
                    "rejected_count",
                    models.IntegerField(default=0, help_text="Number rejected."),
                ),
                (
                    "approval_rate",
                    models.FloatField(
                        default=0.0, help_text="Approval rate percentage."
                    ),
                ),
                (
                    "verified_rate",
                    models.FloatField(
                        default=0.0, help_text="Verified rate percentage."
                    ),
                ),
                (
                    "stale_rate",
                    models.FloatField(default=0.0, help_text="Stale rate percentage."),
                ),
                (
                    "avg_review_time_seconds",
                    models.FloatField(
                        blank=True, null=True, help_text="Average seconds per review."
                    ),
                ),
                (
                    "top_rejection_reasons",
                    models.JSONField(
                        default=list, help_text="Top rejection reason codes."
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True,
                        help_text="When this scorecard was generated.",
                    ),
                ),
            ],
            options={
                "verbose_name": "Reviewer Scorecard",
                "verbose_name_plural": "Reviewer Scorecards",
                "ordering": ["-period_end"],
            },
        ),
        migrations.CreateModel(
            name="ErrorLog",
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
                    "job_type",
                    models.CharField(
                        db_index=True,
                        help_text="Type of job that failed.",
                        max_length=50,
                    ),
                ),
                (
                    "step",
                    models.CharField(
                        help_text="The step where the error occurred.", max_length=100
                    ),
                ),
                (
                    "error_message",
                    models.TextField(help_text="Human-readable error message."),
                ),
                (
                    "raw_exception",
                    models.TextField(blank=True, help_text="Full Python traceback."),
                ),
                (
                    "why",
                    models.TextField(
                        blank=True, help_text="Plain-English explanation of the cause."
                    ),
                ),
                (
                    "acknowledged",
                    models.BooleanField(
                        db_index=True,
                        default=False,
                        help_text="True once reviewed and dismissed.",
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True,
                        db_index=True,
                        help_text="When this error was recorded.",
                    ),
                ),
            ],
            options={
                "verbose_name": "Error Log Entry",
                "verbose_name_plural": "Error Log",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="errorlog",
            index=models.Index(
                fields=["acknowledged", "created_at"], name="errorlog_ack_date_idx"
            ),
        ),
    ]
