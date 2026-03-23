"""Suggestions app initial migration."""

import uuid
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("content", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="ScopePreset",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, help_text="Timestamp when this record was created.")),
                ("updated_at", models.DateTimeField(auto_now=True, help_text="Timestamp when this record was last modified.")),
                ("name", models.CharField(help_text="Friendly name for this preset.", max_length=200, unique=True)),
                ("scope_mode", models.CharField(help_text="How the scope is applied: 'all', 'include', or 'exclude'.", max_length=50)),
                ("enabled_ids", models.JSONField(default=list, help_text="List of ScopeItem PKs.")),
            ],
            options={"verbose_name": "Scope Preset", "verbose_name_plural": "Scope Presets", "ordering": ["name"]},
        ),

        migrations.CreateModel(
            name="PipelineRun",
            fields=[
                ("run_id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False, help_text="Unique identifier for this pipeline run.")),
                ("created_at", models.DateTimeField(auto_now_add=True, help_text="Timestamp when this record was created.")),
                ("updated_at", models.DateTimeField(auto_now=True, help_text="Timestamp when this record was last modified.")),
                ("rerun_mode", models.CharField(choices=[("skip_pending", "Skip Pending"), ("supersede_pending", "Supersede Pending"), ("full_regenerate", "Full Regenerate")], default="skip_pending", help_text="Controls how this run handles existing suggestions.", max_length=30)),
                ("host_scope", models.JSONField(default=dict, help_text="Scope config for host content.")),
                ("destination_scope", models.JSONField(default=dict, help_text="Scope config for destination content.")),
                ("run_state", models.CharField(choices=[("queued", "Queued"), ("running", "Running"), ("completed", "Completed"), ("failed", "Failed"), ("cancelled", "Cancelled")], db_index=True, default="queued", help_text="Current execution state.", max_length=20)),
                ("suggestions_created", models.IntegerField(default=0, help_text="Number of new suggestions generated.")),
                ("destinations_processed", models.IntegerField(default=0, help_text="Number of destinations processed.")),
                ("destinations_skipped", models.IntegerField(default=0, help_text="Number of destinations skipped.")),
                ("duration_seconds", models.FloatField(blank=True, null=True, help_text="Wall-clock seconds to complete.")),
                ("error_message", models.TextField(blank=True, help_text="Error details if run_state is 'failed'.")),
                ("config_snapshot", models.JSONField(default=dict, help_text="Frozen ML weights at run start.")),
                ("celery_task_id", models.CharField(blank=True, help_text="Celery task ID for WebSocket progress.", max_length=255)),
            ],
            options={"verbose_name": "Pipeline Run", "verbose_name_plural": "Pipeline Runs", "ordering": ["-created_at"]},
        ),

        migrations.CreateModel(
            name="Suggestion",
            fields=[
                ("suggestion_id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False, help_text="Unique identifier for this suggestion.")),
                ("created_at", models.DateTimeField(auto_now_add=True, help_text="Timestamp when this record was created.")),
                ("updated_at", models.DateTimeField(auto_now=True, help_text="Timestamp when this record was last modified.")),
                ("destination_title", models.CharField(blank=True, help_text="Denormalized destination title.", max_length=500)),
                ("host_sentence_text", models.TextField(blank=True, help_text="Denormalized sentence text.")),
                ("score_semantic", models.FloatField(default=0.0, help_text="Cosine similarity score.")),
                ("score_keyword", models.FloatField(default=0.0, help_text="Keyword overlap score.")),
                ("score_node_affinity", models.FloatField(default=0.0, help_text="Node affinity bonus.")),
                ("score_quality", models.FloatField(default=0.0, help_text="Host thread quality score.")),
                ("score_pagerank", models.FloatField(default=0.0, help_text="PageRank of destination.")),
                ("score_velocity", models.FloatField(default=0.0, help_text="Velocity/recency bonus.")),
                ("score_final", models.FloatField(db_index=True, default=0.0, help_text="Weighted composite score.")),
                ("anchor_phrase", models.CharField(blank=True, help_text="Clickable link text.", max_length=500)),
                ("anchor_start", models.IntegerField(blank=True, null=True, help_text="Anchor start offset.")),
                ("anchor_end", models.IntegerField(blank=True, null=True, help_text="Anchor end offset.")),
                ("anchor_confidence", models.CharField(choices=[("strong", "Strong"), ("weak", "Weak"), ("none", "None")], default="none", help_text="Anchor extraction confidence.", max_length=20)),
                ("anchor_edited", models.CharField(blank=True, help_text="Reviewer-edited anchor.", max_length=500)),
                ("repeated_anchor", models.BooleanField(default=False, help_text="True if anchor is already used for this destination.")),
                ("status", models.CharField(choices=[("pending", "Pending Review"), ("approved", "Approved"), ("rejected", "Rejected"), ("applied", "Applied"), ("verified", "Verified"), ("stale", "Stale"), ("superseded", "Superseded")], db_index=True, default="pending", help_text="Current review status.", max_length=20)),
                ("rejection_reason", models.CharField(blank=True, choices=[("", "— No reason —"), ("irrelevant", "Irrelevant"), ("low_quality", "Low quality"), ("already_linked", "Already linked"), ("bad_anchor", "Bad anchor"), ("wrong_context", "Wrong context"), ("duplicate", "Duplicate"), ("other", "Other")], help_text="Why rejected.", max_length=100)),
                ("reviewer_notes", models.TextField(blank=True, help_text="Reviewer free-text notes.")),
                ("reviewed_at", models.DateTimeField(blank=True, null=True, help_text="When reviewed.")),
                ("is_applied", models.BooleanField(default=False, help_text="True when manually applied on the live forum.")),
                ("applied_at", models.DateTimeField(blank=True, null=True, help_text="When marked as applied.")),
                ("verified_at", models.DateTimeField(blank=True, null=True, help_text="When verified as live.")),
                ("stale_reason", models.CharField(blank=True, help_text="Why this went stale.", max_length=200)),
                ("superseded_at", models.DateTimeField(blank=True, null=True, help_text="When superseded.")),
                ("destination", models.ForeignKey(help_text="The content item being linked to.", on_delete=django.db.models.deletion.CASCADE, related_name="destination_suggestions", to="content.contentitem")),
                ("host", models.ForeignKey(help_text="The content item whose post will contain the link.", on_delete=django.db.models.deletion.CASCADE, related_name="host_suggestions", to="content.contentitem")),
                ("host_sentence", models.ForeignKey(help_text="The specific sentence where the link is inserted.", on_delete=django.db.models.deletion.CASCADE, related_name="suggestions", to="content.sentence")),
                ("pipeline_run", models.ForeignKey(blank=True, help_text="The pipeline run that generated this.", null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="suggestions", to="suggestions.pipelinerun")),
                ("superseded_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="supersedes", to="suggestions.suggestion", help_text="The newer suggestion that replaced this one.")),
            ],
            options={"verbose_name": "Suggestion", "verbose_name_plural": "Suggestions", "ordering": ["-created_at"]},
        ),
        migrations.AddIndex(model_name="suggestion", index=models.Index(fields=["status", "-score_final"], name="sugg_status_score_idx")),
        migrations.AddIndex(model_name="suggestion", index=models.Index(fields=["destination", "status"], name="sugg_dest_status_idx")),
        migrations.AddIndex(model_name="suggestion", index=models.Index(fields=["host", "status"], name="sugg_host_status_idx")),
        migrations.AddIndex(model_name="suggestion", index=models.Index(fields=["is_applied"], name="sugg_applied_idx")),

        migrations.CreateModel(
            name="PipelineDiagnostic",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("skip_reason", models.CharField(choices=[("already_has_pending", "Already has pending"), ("no_host_sentences", "No host sentences"), ("score_too_low", "Score too low"), ("no_embedding", "No embedding"), ("max_links_reached", "Max links reached"), ("anchor_banned", "Anchor banned"), ("short_post", "Post too short"), ("other", "Other")], db_index=True, help_text="Why no suggestion was created.", max_length=100)),
                ("detail", models.JSONField(default=dict, help_text="Extra diagnostic data.")),
                ("created_at", models.DateTimeField(auto_now_add=True, help_text="When this diagnostic was created.")),
                ("destination", models.ForeignKey(help_text="The destination that was skipped.", on_delete=django.db.models.deletion.CASCADE, related_name="pipeline_diagnostics", to="content.contentitem")),
                ("pipeline_run", models.ForeignKey(help_text="The pipeline run this diagnostic belongs to.", on_delete=django.db.models.deletion.CASCADE, related_name="diagnostics", to="suggestions.pipelinerun")),
            ],
            options={"verbose_name": "Pipeline Diagnostic", "verbose_name_plural": "Pipeline Diagnostics"},
        ),
        migrations.AddIndex(model_name="pipelinediagnostic", index=models.Index(fields=["pipeline_run", "skip_reason"], name="diag_run_reason_idx")),
    ]
