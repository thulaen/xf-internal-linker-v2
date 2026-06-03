"""Slice 1.6 — private attrouted client.

Wraps the gRPC contract at services/sidecars/api/attrouted.proto. Routes
work units to Celery queues or handlers based on declarative rules;
supports Replay to re-evaluate a past decision against the current rule set.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Mapping

from apps._sidecars_shared.channel import (
    DEFAULT_CALL_DEADLINE,
    load_service_stubs,
    sidecars_channel,
)

logger = logging.getLogger(__name__)

SERVICE_NAME = "attrouted"


@dataclass(frozen=True)
class RouteDecisionDTO:
    matched_rule_id: str
    target: str
    explanation: str


@dataclass(frozen=True)
class RouteRuleDTO:
    id: str
    source: str
    match_attributes: dict[str, str] = field(default_factory=dict)
    target: str = ""
    priority: int = 0
    enabled: bool = True


@dataclass(frozen=True)
class ReplayReportDTO:
    unit_id: str
    then_decision: RouteDecisionDTO
    now_decision: RouteDecisionDTO
    diff_explanation: str


def _decision_to_dto(proto_decision) -> RouteDecisionDTO:
    return RouteDecisionDTO(
        matched_rule_id=proto_decision.matched_rule_id,
        target=proto_decision.target,
        explanation=proto_decision.explanation,
    )


def _rule_to_dto(proto_rule) -> RouteRuleDTO:
    return RouteRuleDTO(
        id=proto_rule.id,
        source=proto_rule.source,
        match_attributes=dict(proto_rule.match_attributes),
        target=proto_rule.target,
        priority=proto_rule.priority,
        enabled=proto_rule.enabled,
    )


class AttroutedClient:
    """Sync gRPC client for attribute-based work routing."""

    def __init__(self, deadline: float = DEFAULT_CALL_DEADLINE) -> None:
        self._deadline = deadline

    def route(
        self,
        *,
        source: str,
        attributes: Mapping[str, str],
        unit_id: str = "",
    ) -> RouteDecisionDTO:
        pb, grpc_mod = load_service_stubs(SERVICE_NAME)
        request = pb.RouteRequest(
            source=source,
            attributes=dict(attributes),
            unit_id=unit_id,
        )
        with sidecars_channel() as channel:
            stub = grpc_mod.AttroutedStub(channel)
            response = stub.Route(request, timeout=self._deadline)
        return _decision_to_dto(response)

    def register_rule(self, rule: RouteRuleDTO) -> RouteRuleDTO:
        pb, grpc_mod = load_service_stubs(SERVICE_NAME)
        request = pb.RouteRule(
            id=rule.id,
            source=rule.source,
            match_attributes=dict(rule.match_attributes),
            target=rule.target,
            priority=rule.priority,
            enabled=rule.enabled,
        )
        with sidecars_channel() as channel:
            stub = grpc_mod.AttroutedStub(channel)
            response = stub.RegisterRule(request, timeout=self._deadline)
        return _rule_to_dto(response)

    def list_rules(self) -> list[RouteRuleDTO]:
        pb, grpc_mod = load_service_stubs(SERVICE_NAME)
        with sidecars_channel() as channel:
            stub = grpc_mod.AttroutedStub(channel)
            response = stub.ListRules(pb.Empty(), timeout=self._deadline)
        return [_rule_to_dto(r) for r in response.items]

    def remove_rule(self, rule_id: str) -> bool:
        pb, grpc_mod = load_service_stubs(SERVICE_NAME)
        with sidecars_channel() as channel:
            stub = grpc_mod.AttroutedStub(channel)
            response = stub.RemoveRule(
                pb.RemoveRuleRequest(rule_id=rule_id), timeout=self._deadline
            )
        return response.ok

    def replay(self, unit_id: str) -> ReplayReportDTO:
        pb, grpc_mod = load_service_stubs(SERVICE_NAME)
        with sidecars_channel() as channel:
            stub = grpc_mod.AttroutedStub(channel)
            response = stub.Replay(
                pb.ReplayRequest(unit_id=unit_id), timeout=self._deadline
            )
        return ReplayReportDTO(
            unit_id=response.unit_id,
            then_decision=_decision_to_dto(response.then_decision),
            now_decision=_decision_to_dto(response.now_decision),
            diff_explanation=response.diff_explanation,
        )

    def health(self) -> str:
        pb, grpc_mod = load_service_stubs(SERVICE_NAME)
        with sidecars_channel() as channel:
            stub = grpc_mod.AttroutedStub(channel)
            response = stub.Health(pb.Empty(), timeout=self._deadline)
        return pb.HealthStatus.Name(response.status)
