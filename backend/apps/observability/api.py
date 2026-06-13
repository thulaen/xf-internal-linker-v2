from __future__ import annotations

from typing import Any

try:
    from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram
    from prometheus_client.exposition import CONTENT_TYPE_LATEST, generate_latest
except ImportError:  # pragma: no cover - exercised only before image rebuild.
    CONTENT_TYPE_LATEST = "text/plain; version=0.0.4; charset=utf-8"

    class CollectorRegistry:
        def __init__(self, auto_describe: bool = True):
            self.metrics = []

        def register(self, metric):
            self.metrics.append(metric)

    class _FallbackMetric:
        metric_type = "gauge"

        def __init__(self, name: str, documentation: str, labelnames=(), registry=None, **kwargs):
            self.name = name
            self.documentation = documentation
            self.labelnames = tuple(labelnames or ())
            self.samples: dict[tuple[str, ...], float] = {(): 0.0}
            if registry is not None:
                registry.register(self)

        @property
        def value(self):
            return self.samples.get((), 0.0)

        def inc(self, amount: float = 1.0):
            self.samples[()] = self.samples.get((), 0.0) + amount

        def set(self, value: float):
            self.samples[()] = value

        def observe(self, value: float):
            self.samples[()] = value

        def labels(self, *labelvalues, **labelkwargs):
            if labelkwargs:
                labelvalues = tuple(str(labelkwargs[name]) for name in self.labelnames)
            key = tuple(str(value) for value in labelvalues)
            self.samples.setdefault(key, 0.0)
            return _FallbackMetricChild(self, key)

    class _FallbackMetricChild:
        def __init__(self, parent: _FallbackMetric, key: tuple[str, ...]):
            self.parent = parent
            self.key = key

        def inc(self, amount: float = 1.0):
            self.parent.samples[self.key] = self.parent.samples.get(self.key, 0.0) + amount

        def set(self, value: float):
            self.parent.samples[self.key] = value

        def observe(self, value: float):
            self.parent.samples[self.key] = value

    class Counter(_FallbackMetric):
        metric_type = "counter"

    class Gauge(_FallbackMetric):
        metric_type = "gauge"

    class Histogram(_FallbackMetric):
        metric_type = "histogram"

    def generate_latest(registry: CollectorRegistry) -> bytes:
        lines: list[str] = []
        for metric in registry.metrics:
            lines.append(f"# HELP {metric.name} {metric.documentation}")
            lines.append(f"# TYPE {metric.name} {metric.metric_type}")
            for key, value in metric.samples.items():
                labels = _format_labels(metric.labelnames, key)
                lines.append(f"{metric.name}{labels} {value}")
        return ("\n".join(lines) + "\n").encode()

    def _format_labels(labelnames: tuple[str, ...], values: tuple[str, ...]) -> str:
        if not labelnames or not values:
            return ""
        joined = ",".join(
            f'{name}="{value}"'
            for name, value in zip(labelnames, values)
        )
        return "{" + joined + "}"

from apps.observability.metric_specs import RESERVED_METRICS, MetricSpec

METRICS_TOKEN_HEADER = "HTTP_X_METRICS_TOKEN"  # nosec B105
_REGISTRY = CollectorRegistry(auto_describe=True)
_METRICS: dict[str, Any] = {}


def get_registry() -> CollectorRegistry:
    return _REGISTRY


def register_metric(metric_cls, name: str, documentation: str, labelnames=(), **kwargs):
    if name in _METRICS:
        return _METRICS[name]
    metric = metric_cls(name, documentation, labelnames=labelnames, registry=_REGISTRY, **kwargs)
    _METRICS[name] = metric
    return metric


def get_metric(name: str):
    return _METRICS[name]


def reserved_metric_names() -> list[str]:
    return [spec.name for spec in RESERVED_METRICS]


def registered_metric_names() -> set[str]:
    """Metric names actually registered in the live registry.

    A name in this set is wired into the ``/metrics`` exposition that vmagent
    scrapes — i.e. genuinely present in the pipeline, as opposed to a spec-only
    name that was reserved but never registered. The gap detector treats this
    set as the source of truth for whether a reserved metric is "proven".
    """
    return set(_METRICS)


def initialise_reserved_metrics() -> None:
    for spec in RESERVED_METRICS:
        if spec.name not in _METRICS:
            _register_spec(spec)


def _register_spec(spec: MetricSpec):
    doc = f"Reserved XF metric: {spec.name}"
    cls = {"counter": Counter, "gauge": Gauge, "histogram": Histogram}[spec.kind]
    return register_metric(cls, spec.name, doc, labelnames=spec.labels)


initialise_reserved_metrics()

__all__ = [
    "CONTENT_TYPE_LATEST",
    "Counter",
    "Gauge",
    "Histogram",
    "METRICS_TOKEN_HEADER",
    "generate_latest",
    "get_metric",
    "get_registry",
    "initialise_reserved_metrics",
    "register_metric",
    "registered_metric_names",
    "reserved_metric_names",
]
