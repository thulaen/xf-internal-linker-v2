"""Tests for the shared sidecar protobuf loading contract."""

from __future__ import annotations

from django.test import SimpleTestCase

from apps._sidecars_shared.channel import StubsMissingError, load_service_stubs


class SidecarGeneratedStubContractTests(SimpleTestCase):
    def test_foundation_services_expose_shared_and_service_messages(self) -> None:
        services = {
            "attrouted": ("RouteRequest", "AttroutedStub"),
            "bullboard": ("PostBulletinRequest", "BullboardStub"),
            "coordd": ("EphemeralRequest", "CoorddStub"),
            "errord": ("ErrorPolicy", "ErrordStub"),
            "schemard": ("RegisterSchemaRequest", "SchemardStub"),
            "snapshotd": ("CreateSnapshotRequest", "SnapshotdStub"),
        }

        for service_name, (message_name, stub_name) in services.items():
            with self.subTest(service=service_name):
                pb, grpc_module = load_service_stubs(service_name)

                self.assertEqual(pb.Empty().SerializeToString(), b"")
                self.assertTrue(hasattr(pb, message_name))
                self.assertTrue(hasattr(grpc_module, stub_name))

    def test_missing_service_names_raise_plain_regeneration_guidance(self) -> None:
        with self.assertRaises(StubsMissingError) as caught:
            load_service_stubs("missingd")

        message = str(caught.exception)
        self.assertIn("sidecars protobuf stubs for 'missingd' are missing", message)
        self.assertIn("grpc_tools.protoc", message)
        self.assertIn("services/sidecars/api/missingd.proto", message)
