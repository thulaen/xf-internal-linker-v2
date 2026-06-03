"""Slice 1.6 — private bullboard client.

Wraps the gRPC contract at services/sidecars/api/bullboard.proto. Slice 1.6
implements Post / Recent / RegisterThreshold / ListThresholds / RemoveThreshold
/ EvaluateNow / PromoteToAutoIssue (unary). The Subscribe stream is
deferred (paper-trail #566); the Channels bridge polls Recent every 500 ms
until that lands.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from apps._sidecars_shared.channel import (
    DEFAULT_CALL_DEADLINE,
    load_service_stubs,
    sidecars_channel,
)

logger = logging.getLogger(__name__)

SERVICE_NAME = "bullboard"


@dataclass(frozen=True)
class BulletinDTO:
    id: str
    event_type: str
    severity: str
    message: str
    context_json: bytes
    posted_at_unix_nanos: int
    linked_autoissue_id: int


@dataclass(frozen=True)
class ThresholdRuleDTO:
    id: str
    event_type: str
    window: str
    count: int
    grouping_fields: list[str]
    autoissue_template: str
    enabled: bool


def _bulletin_to_dto(proto_bulletin, severity_enum) -> BulletinDTO:
    return BulletinDTO(
        id=proto_bulletin.id,
        event_type=proto_bulletin.event_type,
        severity=severity_enum.Name(proto_bulletin.severity),
        message=proto_bulletin.message,
        context_json=proto_bulletin.context_json,
        posted_at_unix_nanos=proto_bulletin.posted_at_unix_nanos,
        linked_autoissue_id=proto_bulletin.linked_autoissue_id,
    )


def _rule_to_dto(proto_rule) -> ThresholdRuleDTO:
    return ThresholdRuleDTO(
        id=proto_rule.id,
        event_type=proto_rule.event_type,
        window=proto_rule.window,
        count=proto_rule.count,
        grouping_fields=list(proto_rule.grouping_fields),
        autoissue_template=proto_rule.autoissue_template,
        enabled=proto_rule.enabled,
    )


class BullboardClient:
    """Sync gRPC client for the rolling-feed sidecar."""

    def __init__(self, deadline: float = DEFAULT_CALL_DEADLINE) -> None:
        self._deadline = deadline

    def post(
        self,
        *,
        event_type: str,
        severity: str,
        message: str,
        context_json: bytes = b"{}",
    ) -> BulletinDTO:
        pb, grpc_mod = load_service_stubs(SERVICE_NAME)
        request = pb.PostBulletinRequest(
            event_type=event_type,
            severity=getattr(pb.Severity, _normalize_severity(severity)),
            message=message,
            context_json=context_json,
        )
        with sidecars_channel() as channel:
            stub = grpc_mod.BullboardStub(channel)
            response = stub.Post(request, timeout=self._deadline)
        return _bulletin_to_dto(response, pb.Severity)

    def recent(
        self,
        *,
        event_type: str = "",
        min_severity: str = "SEV_UNKNOWN",
        limit: int = 100,
        since_unix_nanos: int = 0,
    ) -> list[BulletinDTO]:
        pb, grpc_mod = load_service_stubs(SERVICE_NAME)
        request = pb.RecentRequest(
            event_type=event_type,
            min_severity=getattr(pb.Severity, _normalize_severity(min_severity)),
            limit=limit,
            since_unix_nanos=since_unix_nanos,
        )
        with sidecars_channel() as channel:
            stub = grpc_mod.BullboardStub(channel)
            response = stub.Recent(request, timeout=self._deadline)
        return [_bulletin_to_dto(b, pb.Severity) for b in response.items]

    def register_threshold(self, rule: ThresholdRuleDTO) -> ThresholdRuleDTO:
        pb, grpc_mod = load_service_stubs(SERVICE_NAME)
        request = pb.ThresholdRule(
            id=rule.id,
            event_type=rule.event_type,
            window=rule.window,
            count=rule.count,
            grouping_fields=list(rule.grouping_fields),
            autoissue_template=rule.autoissue_template,
            enabled=rule.enabled,
        )
        with sidecars_channel() as channel:
            stub = grpc_mod.BullboardStub(channel)
            response = stub.RegisterThreshold(request, timeout=self._deadline)
        return _rule_to_dto(response)

    def list_thresholds(self) -> list[ThresholdRuleDTO]:
        pb, grpc_mod = load_service_stubs(SERVICE_NAME)
        with sidecars_channel() as channel:
            stub = grpc_mod.BullboardStub(channel)
            response = stub.ListThresholds(pb.Empty(), timeout=self._deadline)
        return [_rule_to_dto(r) for r in response.items]

    def remove_threshold(self, rule_id: str) -> bool:
        pb, grpc_mod = load_service_stubs(SERVICE_NAME)
        with sidecars_channel() as channel:
            stub = grpc_mod.BullboardStub(channel)
            response = stub.RemoveThreshold(
                pb.RemoveThresholdRequest(rule_id=rule_id), timeout=self._deadline
            )
        return response.ok

    def health(self) -> str:
        pb, grpc_mod = load_service_stubs(SERVICE_NAME)
        with sidecars_channel() as channel:
            stub = grpc_mod.BullboardStub(channel)
            response = stub.Health(pb.Empty(), timeout=self._deadline)
        return pb.HealthStatus.Name(response.status)


def _normalize_severity(severity: str) -> str:
    """Map human label ('info', 'warning', 'error', 'critical') → SEV_* enum."""
    upper = severity.upper().strip()
    if upper.startswith("SEV_"):
        return upper
    return f"SEV_{upper}"
