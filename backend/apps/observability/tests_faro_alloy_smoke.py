import json
import socket
import time
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from uuid import uuid4

import pytest


def _service_reachable(host: str, port: int, timeout: float = 2.0) -> bool:
    """True when a TCP connection to host:port succeeds within the timeout."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


pytestmark = pytest.mark.skipif(
    not (_service_reachable("alloy", 12347) and _service_reachable("loki", 3100)),
    reason="alloy/loki are only on the live observability stack; skipped where absent",
)


def test_faro_alloy_receiver_forwards_errors_to_loki_with_picker_labels():
    marker = f"faro-alloy-smoke-{uuid4()}"
    payload = {
        "meta": {
            "app": {
                "name": "xf-internal-linker",
                "version": "1.0.0",
                "environment": "test",
            }
        },
        "exceptions": [
            {
                "type": "Error",
                "value": marker,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        ],
    }

    request = urllib.request.Request(
        "http://alloy:12347/collect",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(request, timeout=5) as response:
        assert response.status == 202

    deadline = time.monotonic() + 10
    query = urllib.parse.urlencode(
        {"query": f'{{source="faro"}} |= "{marker}"', "limit": "5"}
    )
    url = f"http://loki:3100/loki/api/v1/query_range?{query}"

    while time.monotonic() < deadline:
        with urllib.request.urlopen(url, timeout=5) as response:
            body = json.loads(response.read().decode("utf-8"))
        result = body.get("data", {}).get("result", [])
        if _has_frontend_faro_result(result, marker):
            return
        time.sleep(1)

    raise AssertionError(f"Faro smoke marker did not reach Loki: {marker}")


def _has_frontend_faro_result(result: list[dict], marker: str) -> bool:
    for stream in result:
        labels = stream.get("stream", {})
        if labels.get("source") != "faro" or labels.get("service") != "frontend":
            continue
        for _, line in stream.get("values", []):
            if marker in line:
                return True
    return False
