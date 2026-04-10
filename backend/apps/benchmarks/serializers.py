from rest_framework import serializers

from .models import BenchmarkResult, BenchmarkRun


class BenchmarkResultSerializer(serializers.ModelSerializer):
    class Meta:
        model = BenchmarkResult
        fields = [
            "id",
            "language",
            "extension",
            "function_name",
            "input_size",
            "mean_ns",
            "median_ns",
            "items_per_second",
            "status",
            "threshold_ns",
        ]


class BenchmarkRunSerializer(serializers.ModelSerializer):
    results = BenchmarkResultSerializer(many=True, read_only=True)

    class Meta:
        model = BenchmarkRun
        fields = [
            "id",
            "started_at",
            "finished_at",
            "trigger",
            "status",
            "summary_json",
            "results",
        ]


class BenchmarkRunListSerializer(serializers.ModelSerializer):
    result_count = serializers.IntegerField(source="results.count", read_only=True)

    class Meta:
        model = BenchmarkRun
        fields = [
            "id",
            "started_at",
            "finished_at",
            "trigger",
            "status",
            "result_count",
        ]


class BenchmarkTrendSerializer(serializers.Serializer):
    date = serializers.DateField()
    function_name = serializers.CharField()
    language = serializers.CharField()
    mean_ns = serializers.IntegerField()
    status = serializers.CharField()
