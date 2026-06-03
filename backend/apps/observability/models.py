from __future__ import annotations

from django.db import models


class MetricCardinalityBudget(models.Model):
    metric_name = models.CharField(max_length=160, unique=True)
    max_series = models.PositiveIntegerField(default=1000)
    current_series_estimated = models.PositiveIntegerField(default=0)
    exceeded_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["metric_name"]

