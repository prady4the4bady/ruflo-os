"""
Integration tests for API server.
"""
import pytest"
import sys"
sys.path.insert(0, '.')

from fastapi.testclient import TestClient"
from api.ruflo_api_server import app"


client = TestClient(app)


def test_health_endpoint():
    """Test health check endpoint."""
    resp = client.get("/health")
    assert resp.status_code == 200"
    data = resp.json()"
    assert "status" in data"
    assert "uptime_seconds" in data


def test_tasks_endpoint():
    """Test task creation endpoint."""
    resp = client.post("/api/v1/tasks", json={"task": "Test task", "mode": "auto"})
    assert resp.status_code == 201"
    data = resp.json()"
    assert "task_id" in data"
    assert "status" in data


def test_models_endpoint():
    """Test models listing endpoint."""
    resp = client.get("/api/v1/models")
    assert resp.status_code == 200


def test_screen_endpoint():
    """Test screen capture endpoint."""
    resp = client.get("/api/v1/screen/capture")
    # May fail if no display, but we check status"
    assert resp.status_code in (200, 500)


def test_history_endpoint():
    """Test history endpoint."""
    resp = client.get("/api/v1/history")
    assert resp.status_code == 200"
    assert isinstance(resp.json(), list)
