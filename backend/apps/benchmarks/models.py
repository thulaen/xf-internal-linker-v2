from django.db import models


class BenchmarkRun(models.Model):
    """A single benchmark execution covering C++ and/or Python."""

    TRIGGER_CHOICES = [
        ("scheduled", "Scheduled"),
        ("manual", "Manual"),
    ]
    STATUS_CHOICES = [
        ("running", "Running"),
        ("completed", "Completed"),
        ("failed", "Failed"),
    ]

    started_at = models.DateTimeField(auto_now_add=True, db_index=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    trigger = models.CharField(max_length=20, choices=TRIGGER_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="running")
    summary_json = models.JSONField(null=True, blank=True)
    error_message = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        return f"BenchmarkRun #{self.pk} ({self.trigger}, {self.status})"


class BenchmarkResult(models.Model):
    """A single function benchmark result within a run."""

    STATUS_CHOICES = [
        ("fast", "Fast"),
        ("ok", "OK"),
        ("slow", "Slow"),
    ]

    run = models.ForeignKey(
        BenchmarkRun, on_delete=models.CASCADE, related_name="results"
    )
    language = models.CharField(max_length=10, db_index=True)
    extension = models.CharField(max_length=100)
    function_name = models.CharField(max_length=200)
    input_size = models.CharField(max_length=20)
    mean_ns = models.BigIntegerField()
    median_ns = models.BigIntegerField()
    items_per_second = models.FloatField(default=0.0)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="ok")
    threshold_ns = models.BigIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["language", "extension", "function_name", "input_size"]

    def __str__(self):
        return (
            f"{self.language}/{self.extension}.{self.function_name} @ {self.input_size}"
        )
