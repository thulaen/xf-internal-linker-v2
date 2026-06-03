"""Convention-named SimpleTestCase coverage for services/stack_status.py.

``build_stack_status`` reports a fixed list of twelve observability services.
The three VictoriaMetrics services are probed over HTTP; the other nine carry a
static ``state``. These tests replace every network call (``_endpoint_responds``
and the urllib path underneath it) with a stub so NO real request to the Mint
host ever leaves the process, and pin every state/string/number literal with
exact ``assertEqual`` so the diff-scoped mutation gate cannot survive a changed
operator, flipped guard, or reworded message.

No database, no Redis, no Celery, no real HTTP: SimpleTestCase only.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from apps.observability.services import stack_status


class ServiceCatalogTests(SimpleTestCase):
    def test_exactly_twelve_services_are_declared(self) -> None:
        # Exact count kills the +1/-1 mutation; the plan reserves exactly 12.
        self.assertEqual(len(stack_status.SERVICES), 12)

    def test_first_three_services_are_the_probed_victoriametrics_tier(self) -> None:
        names = [service["name"] for service in stack_status.SERVICES[:3]]
        self.assertEqual(names, ["VictoriaMetrics", "vmagent", "vmalert"])

    def test_probed_services_carry_a_health_url_and_static_services_do_not(self) -> None:
        self.assertIn("health_url", stack_status.SERVICES[0])
        # Grafana (index 3) is a static-state service with no probe.
        self.assertNotIn("health_url", stack_status.SERVICES[3])
        self.assertEqual(stack_status.SERVICES[3]["state"], "healthy")


class ServiceStateTests(SimpleTestCase):
    def test_static_service_returns_its_declared_state(self) -> None:
        service = {"name": "Grafana", "state": "healthy", "dashboard_uid": "x"}
        self.assertEqual(stack_status._service_state(service), "healthy")

    def test_static_service_without_state_returns_unknown(self) -> None:
        # Default of the second .get must be exactly "unknown".
        self.assertEqual(stack_status._service_state({"name": "X"}), "unknown")

    def test_probed_service_healthy_when_endpoint_responds_true(self) -> None:
        service = {"name": "vm", "health_url": "http://stub/health"}
        with patch.object(stack_status, "_endpoint_responds", return_value=True):
            self.assertEqual(stack_status._service_state(service), "healthy")

    def test_probed_service_degraded_when_endpoint_responds_false(self) -> None:
        # Both branches of the boolean guard are tested: True -> healthy above,
        # False -> degraded here. Negating the condition flips one of them.
        service = {"name": "vm", "health_url": "http://stub/health"}
        with patch.object(stack_status, "_endpoint_responds", return_value=False):
            self.assertEqual(stack_status._service_state(service), "degraded")


class EndpointRespondsTests(SimpleTestCase):
    """The urllib call is replaced wholesale — no socket is ever opened."""

    def _patched_urlopen(self, status: int):
        response = MagicMock()
        response.status = status
        context = MagicMock()
        context.__enter__.return_value = response
        context.__exit__.return_value = False
        return patch.object(stack_status.urllib.request, "urlopen", return_value=context)

    def test_status_200_is_treated_as_responding(self) -> None:
        with self._patched_urlopen(200):
            self.assertEqual(stack_status._endpoint_responds("http://stub"), True)

    def test_status_499_is_responding_but_500_is_not(self) -> None:
        # The comparison is ``200 <= status < 500``. 499 passes, 500 fails;
        # exact True/False on each side kills a flipped < or <=.
        with self._patched_urlopen(499):
            self.assertEqual(stack_status._endpoint_responds("http://stub"), True)
        with self._patched_urlopen(500):
            self.assertEqual(stack_status._endpoint_responds("http://stub"), False)

    def test_status_199_is_not_responding(self) -> None:
        with self._patched_urlopen(199):
            self.assertEqual(stack_status._endpoint_responds("http://stub"), False)

    def test_network_error_is_swallowed_as_not_responding(self) -> None:
        with patch.object(
            stack_status.urllib.request, "urlopen", side_effect=OSError("boom")
        ):
            self.assertEqual(stack_status._endpoint_responds("http://stub"), False)


class ExplanationAndNextActionTests(SimpleTestCase):
    def test_healthy_explanation_exact_string(self) -> None:
        service = {"name": "Grafana"}
        self.assertEqual(
            stack_status._explanation(service, "healthy"),
            "Grafana is configured in the existing stack.",
        )

    def test_degraded_explanation_exact_string(self) -> None:
        service = {"name": "Grafana"}
        self.assertEqual(
            stack_status._explanation(service, "degraded"),
            "Grafana is configured but its health endpoint is not answering yet.",
        )

    def test_healthy_next_action_exact_string(self) -> None:
        self.assertEqual(
            stack_status._next_action({"name": "X"}, "healthy"),
            "Open the linked dashboard for detail.",
        )

    def test_degraded_next_action_exact_string(self) -> None:
        self.assertEqual(
            stack_status._next_action({"name": "X"}, "degraded"),
            "Start or repair the VictoriaMetrics, vmagent, and vmalert services.",
        )


class ServicePayloadTests(SimpleTestCase):
    def _service(self) -> dict:
        return {"name": "Grafana", "state": "healthy", "dashboard_uid": "xf-system-health"}

    def test_healthy_payload_has_exact_fields(self) -> None:
        payload = stack_status._service_payload(7, self._service(), "2026-06-03T00:00:00")
        self.assertEqual(payload["id"], 7)
        self.assertEqual(payload["service_name"], "Grafana")
        self.assertEqual(payload["state"], "healthy")
        self.assertEqual(payload["last_check"], "2026-06-03T00:00:00")
        # When healthy, last_success mirrors now and last_failure is None.
        self.assertEqual(payload["last_success"], "2026-06-03T00:00:00")
        self.assertIsNone(payload["last_failure"])

    def test_healthy_metadata_open_gaps_is_zero_and_sample_recent(self) -> None:
        payload = stack_status._service_payload(1, self._service(), "now")
        self.assertEqual(payload["metadata"]["dashboard_uid"], "xf-system-health")
        self.assertEqual(payload["metadata"]["open_gaps"], 0)
        self.assertEqual(payload["metadata"]["last_sample"], "recent")

    def test_degraded_payload_flips_success_gaps_and_sample(self) -> None:
        # A probed service forced degraded: both branches of every
        # state-conditional differ from the healthy case above.
        service = {"name": "vmagent", "health_url": "http://stub", "dashboard_uid": "uid"}
        with patch.object(stack_status, "_endpoint_responds", return_value=False):
            payload = stack_status._service_payload(2, service, "now")
        self.assertEqual(payload["state"], "degraded")
        self.assertIsNone(payload["last_success"])
        self.assertEqual(payload["metadata"]["open_gaps"], 1)
        self.assertEqual(payload["metadata"]["last_sample"], "missing")


class BuildStackStatusTests(SimpleTestCase):
    def test_build_returns_twelve_payloads_with_one_based_ids(self) -> None:
        # All probes stubbed False so nothing leaves the process.
        with patch.object(stack_status, "_endpoint_responds", return_value=False), patch.object(
            stack_status.timezone, "now"
        ) as fake_now:
            fake_now.return_value.isoformat.return_value = "2026-06-03T00:00:00"
            payloads = stack_status.build_stack_status()
        self.assertEqual(len(payloads), 12)
        ids = [row["id"] for row in payloads]
        self.assertEqual(ids, list(range(1, 13)))

    def test_static_services_stay_healthy_when_probes_fail(self) -> None:
        # Grafana carries a static state, so a failed probe must not touch it.
        with patch.object(stack_status, "_endpoint_responds", return_value=False), patch.object(
            stack_status.timezone, "now"
        ) as fake_now:
            fake_now.return_value.isoformat.return_value = "now"
            payloads = stack_status.build_stack_status()
        states = {row["service_name"]: row["state"] for row in payloads}
        self.assertEqual(states["Grafana"], "healthy")
        self.assertEqual(states["VictoriaMetrics"], "degraded")
