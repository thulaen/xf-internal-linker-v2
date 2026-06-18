"""Tests for the no-spend Google Cloud budget action helper."""

from __future__ import annotations

import base64
import importlib.util
import json
import sys
import unittest
from pathlib import Path

_FUNCTION_PATH = Path("infra/gcp/budget-autodisable/function/main.py")


def _load_module():
    spec = importlib.util.spec_from_file_location("gcp_budget_autodisable", _FUNCTION_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load budget function module.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class GcpBudgetAutoDisableTests(unittest.TestCase):
    def test_when_budget_reached_in_simulation_then_billing_is_not_disabled(self) -> None:
        module = _load_module()

        action = module.decide_budget_action({"costAmount": 20, "budgetAmount": 20}, simulate=True)

        self.assertFalse(action.should_disable_billing)
        self.assertTrue(action.simulation)

    def test_when_budget_reached_live_then_action_requests_disable(self) -> None:
        module = _load_module()

        action = module.decide_budget_action({"costAmount": 21, "budgetAmount": 20}, simulate=False)

        self.assertTrue(action.should_disable_billing)
        self.assertFalse(action.simulation)

    def test_when_pubsub_payload_is_encoded_then_decoder_returns_budget_message(self) -> None:
        module = _load_module()
        payload = {"costAmount": 3, "budgetAmount": 20}
        encoded = base64.b64encode(json.dumps(payload).encode("utf-8")).decode("ascii")

        decoded = module.decode_budget_message(encoded)

        self.assertEqual(decoded, payload)

    def test_when_pubsub_payload_is_invalid_then_decoder_returns_empty_message(self) -> None:
        module = _load_module()

        decoded = module.decode_budget_message("not-base64")

        self.assertEqual(decoded, {})

    def test_when_event_shape_is_invalid_then_stop_billing_stays_simulated(self) -> None:
        module = _load_module()
        event = type("Event", (), {"data": "bad"})()

        result = module.stop_billing(event)

        self.assertFalse(result["should_disable_billing"])
        self.assertTrue(result["simulation"])


if __name__ == "__main__":
    unittest.main()
