import unittest
from unittest.mock import patch, MagicMock

from apps.sources._sidecars.attrouted_client import (
    AttroutedClient,
    RouteRuleDTO,
    RouteDecisionDTO,
    ReplayReportDTO,
    _decision_to_dto,
    _rule_to_dto,
)

class TestAttroutedClient(unittest.TestCase):
    def setUp(self):
        self.client = AttroutedClient()
        self.mock_pb = MagicMock()
        self.mock_grpc = MagicMock()
        self.mock_stub = MagicMock()
        self.mock_grpc.AttroutedStub.return_value = self.mock_stub

        # Mock sidecars_channel context manager
        self.mock_channel = MagicMock()
        self.mock_cm = MagicMock()
        self.mock_cm.__enter__.return_value = self.mock_channel

    @patch('apps.sources._sidecars.attrouted_client.load_service_stubs')
    @patch('apps.sources._sidecars.attrouted_client.sidecars_channel')
    def test_route(self, mock_channel, mock_load_stubs):
        mock_load_stubs.return_value = (self.mock_pb, self.mock_grpc)
        mock_channel.return_value = self.mock_cm

        mock_resp = MagicMock()
        mock_resp.matched_rule_id = "r1"
        mock_resp.target = "t1"
        mock_resp.explanation = "exp"
        self.mock_stub.Route.return_value = mock_resp

        decision = self.client.route(source="src", attributes={"k": "v"}, unit_id="u1")
        self.assertEqual(decision.matched_rule_id, "r1")
        self.assertEqual(decision.target, "t1")
        
        self.mock_stub.Route.assert_called_once()

    @patch('apps.sources._sidecars.attrouted_client.load_service_stubs')
    @patch('apps.sources._sidecars.attrouted_client.sidecars_channel')
    def test_register_rule(self, mock_channel, mock_load_stubs):
        mock_load_stubs.return_value = (self.mock_pb, self.mock_grpc)
        mock_channel.return_value = self.mock_cm

        mock_resp = MagicMock()
        mock_resp.id = "r1"
        mock_resp.source = "src"
        mock_resp.match_attributes = {"k": "v"}
        mock_resp.target = "t1"
        mock_resp.priority = 1
        mock_resp.enabled = True
        self.mock_stub.RegisterRule.return_value = mock_resp

        rule = RouteRuleDTO(id="r1", source="src")
        registered = self.client.register_rule(rule)
        self.assertEqual(registered.id, "r1")
        
        self.mock_stub.RegisterRule.assert_called_once()

    @patch('apps.sources._sidecars.attrouted_client.load_service_stubs')
    @patch('apps.sources._sidecars.attrouted_client.sidecars_channel')
    def test_health(self, mock_channel, mock_load_stubs):
        mock_load_stubs.return_value = (self.mock_pb, self.mock_grpc)
        mock_channel.return_value = self.mock_cm

        mock_resp = MagicMock()
        mock_resp.status = 1
        self.mock_pb.HealthStatus.Name.return_value = "OK"
        self.mock_stub.Health.return_value = mock_resp

        status = self.client.health()
        self.assertEqual(status, "OK")
