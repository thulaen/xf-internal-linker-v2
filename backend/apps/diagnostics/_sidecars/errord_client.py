"""Slice 1.6 — private errord client.

Wraps the gRPC contract at services/sidecars/api/errord.proto. Operations
code calls Handle(...) when an exception bubbles up; errord matches the
exception against registered policies and returns the action to take
(SWALLOW / RETRY / ALERT / FILE_AUTOISSUE).
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

SERVICE_NAME = "errord"


@dataclass(frozen=True)
class HandleResultDTO:
    matched_policy_id: str
    action: str
    backoff_seconds: int
    explanation: str
    autoissue_severity: str


@dataclass(frozen=True)
class ErrorPolicyDTO:
    id: str
    match_class: str
    match_module: str
    action: str
    backoff_seconds: int = 0
    priority: int = 0
    enabled: bool = True
    autoissue_severity: str = ""


def _result_to_dto(proto_result, action_enum) -> HandleResultDTO:
    return HandleResultDTO(
        matched_policy_id=proto_result.matched_policy_id,
        action=action_enum.Name(proto_result.action),
        backoff_seconds=proto_result.backoff_seconds,
        explanation=proto_result.explanation,
        autoissue_severity=proto_result.autoissue_severity,
    )


def _policy_to_dto(proto_policy, action_enum) -> ErrorPolicyDTO:
    return ErrorPolicyDTO(
        id=proto_policy.id,
        match_class=proto_policy.match_class,
        match_module=proto_policy.match_module,
        action=action_enum.Name(proto_policy.action),
        backoff_seconds=proto_policy.backoff_seconds,
        priority=proto_policy.priority,
        enabled=proto_policy.enabled,
        autoissue_severity=proto_policy.autoissue_severity,
    )


class ErrordClient:
    """Sync gRPC client for the exception-policy registry."""

    def __init__(self, deadline: float = DEFAULT_CALL_DEADLINE) -> None:
        self._deadline = deadline

    def handle(
        self,
        *,
        class_name: str,
        module: str,
        message: str,
        top_frames: list[str] | None = None,
    ) -> HandleResultDTO:
        pb, grpc_mod = load_service_stubs(SERVICE_NAME)
        request = pb.HandleExceptionRequest(
            class_name=class_name,
            module=module,
            message=message,
            top_frames=list(top_frames or []),
        )
        with sidecars_channel() as channel:
            stub = grpc_mod.ErrordStub(channel)
            response = stub.Handle(request, timeout=self._deadline)
        return _result_to_dto(response, pb.HandleAction)

    def register_policy(self, policy: ErrorPolicyDTO) -> ErrorPolicyDTO:
        pb, grpc_mod = load_service_stubs(SERVICE_NAME)
        request = pb.ErrorPolicy(
            id=policy.id,
            match_class=policy.match_class,
            match_module=policy.match_module,
            action=getattr(pb.HandleAction, _normalize_action(policy.action)),
            backoff_seconds=policy.backoff_seconds,
            priority=policy.priority,
            enabled=policy.enabled,
            autoissue_severity=policy.autoissue_severity,
        )
        with sidecars_channel() as channel:
            stub = grpc_mod.ErrordStub(channel)
            response = stub.RegisterPolicy(request, timeout=self._deadline)
        return _policy_to_dto(response, pb.HandleAction)

    def list_policies(self) -> list[ErrorPolicyDTO]:
        pb, grpc_mod = load_service_stubs(SERVICE_NAME)
        with sidecars_channel() as channel:
            stub = grpc_mod.ErrordStub(channel)
            response = stub.ListPolicies(pb.Empty(), timeout=self._deadline)
        return [_policy_to_dto(p, pb.HandleAction) for p in response.items]

    def health(self) -> str:
        pb, grpc_mod = load_service_stubs(SERVICE_NAME)
        with sidecars_channel() as channel:
            stub = grpc_mod.ErrordStub(channel)
            response = stub.Health(pb.Empty(), timeout=self._deadline)
        return pb.HealthStatus.Name(response.status)


def _normalize_action(action: str) -> str:
    """Map human label ('SWALLOW', 'retry', 'ALERT', 'FILE_AUTOISSUE') → ACT_*."""
    upper = action.upper().strip()
    if upper.startswith("ACT_"):
        return upper
    return f"ACT_{upper}"
