"""Slice 1.6 — private schemard client.

Wraps the gRPC contract at services/sidecars/api/schemard.proto. snapshotd
consults schemard before writing a new snapshot so an outdated reader
cannot crash on a new schema version.

Slice 1.6: thin app under apps.auto_issues. Slice 9: moves to
apps.governance._sidecars (paper-trail #571).
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

SERVICE_NAME = "schemard"


@dataclass(frozen=True)
class SchemaVersionDTO:
    subject: str
    version: int
    schema_json: str
    created_at_unix_nanos: int


@dataclass(frozen=True)
class CompatReportDTO:
    compatible: bool
    detail: str
    checked_level: str


def _version_to_dto(proto_version) -> SchemaVersionDTO:
    return SchemaVersionDTO(
        subject=proto_version.subject,
        version=proto_version.version,
        schema_json=proto_version.schema_json,
        created_at_unix_nanos=proto_version.created_at_unix_nanos,
    )


class SchemardClient:
    """Sync gRPC client for the schema registry."""

    def __init__(self, deadline: float = DEFAULT_CALL_DEADLINE) -> None:
        self._deadline = deadline

    def register(
        self,
        *,
        subject: str,
        schema_json: str,
        require_backward_compat: bool = False,
    ) -> SchemaVersionDTO:
        pb, grpc_mod = load_service_stubs(SERVICE_NAME)
        request = pb.RegisterSchemaRequest(
            subject=subject,
            schema_json=schema_json,
            require_backward_compat=require_backward_compat,
        )
        with sidecars_channel() as channel:
            stub = grpc_mod.SchemardStub(channel)
            response = stub.Register(request, timeout=self._deadline)
        return _version_to_dto(response)

    def get(self, subject: str, version: int) -> SchemaVersionDTO:
        pb, grpc_mod = load_service_stubs(SERVICE_NAME)
        with sidecars_channel() as channel:
            stub = grpc_mod.SchemardStub(channel)
            response = stub.Get(
                pb.GetSchemaRequest(subject=subject, version=version),
                timeout=self._deadline,
            )
        return _version_to_dto(response)

    def latest(self, subject: str) -> SchemaVersionDTO:
        pb, grpc_mod = load_service_stubs(SERVICE_NAME)
        with sidecars_channel() as channel:
            stub = grpc_mod.SchemardStub(channel)
            response = stub.Latest(
                pb.LatestRequest(subject=subject), timeout=self._deadline
            )
        return _version_to_dto(response)

    def check_compat(
        self,
        *,
        subject: str,
        candidate_schema_json: str,
        level: str = "COMP_BACKWARD",
    ) -> CompatReportDTO:
        pb, grpc_mod = load_service_stubs(SERVICE_NAME)
        level_enum = getattr(pb.CompatLevel, level if level.startswith("COMP_") else f"COMP_{level}")
        request = pb.CheckCompatRequest(
            subject=subject,
            candidate_schema_json=candidate_schema_json,
            level=level_enum,
        )
        with sidecars_channel() as channel:
            stub = grpc_mod.SchemardStub(channel)
            response = stub.CheckCompat(request, timeout=self._deadline)
        return CompatReportDTO(
            compatible=response.compatible,
            detail=response.detail,
            checked_level=pb.CompatLevel.Name(response.checked_level),
        )

    def health(self) -> str:
        pb, grpc_mod = load_service_stubs(SERVICE_NAME)
        with sidecars_channel() as channel:
            stub = grpc_mod.SchemardStub(channel)
            response = stub.Health(pb.Empty(), timeout=self._deadline)
        return pb.HealthStatus.Name(response.status)
