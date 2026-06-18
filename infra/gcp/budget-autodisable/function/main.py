"""Simulation-first budget notification handler for slice 29."""

from __future__ import annotations

import base64
import binascii
import json
import os
from dataclasses import dataclass

_SIMULATE_ENV = "SIMULATE_DEACTIVATION"


@dataclass(frozen=True, slots=True)
class BudgetAction:
    """Plain decision returned for a budget notification."""

    should_disable_billing: bool
    simulation: bool
    reason: str


def decode_budget_message(data: str | None) -> dict[str, object]:
    """Decode a Pub/Sub budget notification payload."""
    if not data:
        return {}
    try:
        raw = base64.b64decode(data).decode("utf-8")
        payload = json.loads(raw)
    except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def decide_budget_action(payload: dict[str, object], *, simulate: bool) -> BudgetAction:
    """Return whether the budget function should disable billing."""
    cost = float(payload.get("costAmount", 0) or 0)
    budget = float(payload.get("budgetAmount", 0) or 0)
    if budget <= 0:
        return BudgetAction(False, simulate, "Budget amount was missing.")
    if cost < budget:
        return BudgetAction(False, simulate, "Budget has not been reached.")
    if simulate:
        return BudgetAction(False, True, "Simulation mode: billing would be disabled.")
    return BudgetAction(True, False, "Budget reached: billing disable requested.")


def stop_billing(event: object) -> dict[str, object]:
    """Cloud Run function entry point kept safe by simulation mode."""
    data = getattr(event, "data", {}) if event is not None else {}
    data = data if isinstance(data, dict) else {}
    message = data.get("message", {})
    message = message if isinstance(message, dict) else {}
    payload = decode_budget_message(message.get("data"))
    simulate = os.environ.get(_SIMULATE_ENV, "true").lower() != "false"
    action = decide_budget_action(payload, simulate=simulate)
    return {
        "should_disable_billing": action.should_disable_billing,
        "simulation": action.simulation,
        "reason": action.reason,
    }
