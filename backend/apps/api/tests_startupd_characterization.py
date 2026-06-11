import json
import urllib.request
import urllib.error
import pytest

import os

STARTUPD_URL = os.environ.get("STARTUPD_URL", "http://startupd:8765")

def test_startupd_health():
    """Test that the /health endpoint returns 200 OK and 'ok'."""
    url = f"{STARTUPD_URL}/health"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req) as response:
        assert response.status == 200
        body = response.read().decode('utf-8')
        assert body.strip() == "ok"

def test_startupd_payload():
    """Test the /payload endpoint behavior (200, 404, or 503)."""
    url = f"{STARTUPD_URL}/payload"
    try:
        with urllib.request.urlopen(url) as response:
            assert response.status == 200
            # Should be valid JSON if it returns 200
            json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        assert e.code in [404, 503]

def test_startupd_gate_missing_type():
    """Test that /gate without 'type' returns 400 Bad Request."""
    url = f"{STARTUPD_URL}/gate"
    try:
        urllib.request.urlopen(url)
    except urllib.error.HTTPError as e:
        assert e.code == 400
    else:
        pytest.fail("Expected HTTPError 400, but request succeeded")

def test_startupd_gate_invalid_type():
    """Test that /gate with unknown 'type' returns 400 Bad Request."""
    url = f"{STARTUPD_URL}/gate?type=invalid_type_123"
    try:
        urllib.request.urlopen(url)
    except urllib.error.HTTPError as e:
        assert e.code == 400
    else:
        pytest.fail("Expected HTTPError 400, but request succeeded")

def test_startupd_gate_valid_type():
    """Test that /gate with valid 'type' behaves as specified."""
    url = f"{STARTUPD_URL}/gate?type=docs"
    try:
        with urllib.request.urlopen(url) as response:
            assert response.status == 200
            data = json.loads(response.read().decode('utf-8'))
            assert "marker_block" in data
            assert "state" in data
            assert "token" in data["state"]
    except urllib.error.HTTPError as e:
        # If django backend is unreachable or gate fails
        assert e.code in [502, 500]
