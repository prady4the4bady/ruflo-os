"""Tests for control plane."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from ruflo_control_plane.main import create_app
from ruflo_control_plane.orchestrator.engine import OrchestratorEngine
from ruflo_control_plane.policy.evaluator import PolicyEvaluator
from ruflo_control_plane.audit.service import AuditService


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_health(client):
    resp = await client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json()["service"] == "control-plane"


@pytest.mark.asyncio
async def test_create_task(client):
    resp = await client.post("/api/v1/tasks", json={"goal": "Open Firefox"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["goal"] == "Open Firefox"
    assert data["status"] == "awaiting_approval"


@pytest.mark.asyncio
async def test_approve_task(client):
    resp = await client.post("/api/v1/tasks", json={"goal": "Test approval"})
    task_id = resp.json()["task_id"]
    resp = await client.post(f"/api/v1/tasks/{task_id}/approve", json={"approved": True})
    assert resp.json()["status"] == "approved"


@pytest.mark.asyncio
async def test_cancel_task(client):
    resp = await client.post("/api/v1/tasks", json={"goal": "Cancel me"})
    task_id = resp.json()["task_id"]
    resp = await client.post(f"/api/v1/tasks/{task_id}/cancel")
    assert resp.json()["status"] == "cancelled"


@pytest.mark.asyncio
async def test_replay_task(client):
    resp = await client.post("/api/v1/tasks", json={"goal": "Replay me", "requires_approval": False})
    task_id = resp.json()["task_id"]
    resp = await client.post(f"/api/v1/tasks/{task_id}/replay")
    assert resp.status_code == 200
    assert resp.json()["task_id"] != task_id


# Orchestrator tests
@pytest.mark.asyncio
async def test_orchestrator_decompose():
    engine = OrchestratorEngine()
    plan = await engine.decompose("task-1", "Open Firefox and navigate to example.com")
    assert len(plan.steps) == 4
    assert plan.steps[0].agent_type == "planner"


@pytest.mark.asyncio
async def test_orchestrator_dependencies():
    engine = OrchestratorEngine()
    plan = await engine.decompose("task-2", "Test dependencies")
    ready = engine.get_ready_steps(plan.plan_id)
    assert len(ready) == 1  # Only first step has no deps


# Policy tests
def test_policy_allow_reads():
    evaluator = PolicyEvaluator()
    result = evaluator.evaluate("read_file")
    assert result.verdict.value == "allow"


def test_policy_deny_purchase():
    evaluator = PolicyEvaluator()
    result = evaluator.evaluate("browser_purchase")
    assert result.verdict.value == "deny"


def test_policy_require_approval_for_delete():
    evaluator = PolicyEvaluator()
    result = evaluator.evaluate("delete_file")
    assert result.verdict.value == "require_approval"


def test_policy_default_deny():
    evaluator = PolicyEvaluator()
    result = evaluator.evaluate("unknown_dangerous_action")
    assert result.verdict.value == "deny"


# Audit tests
def test_audit_chain():
    svc = AuditService()
    svc.log("test", "action1", "success")
    svc.log("test", "action2", "success")
    svc.log("test", "action3", "failure")
    assert svc.count == 3
    assert svc.verify_chain() is True


def test_audit_tamper_detection():
    svc = AuditService()
    svc.log("test", "action1", "success")
    svc.log("test", "action2", "success")
    # Tamper with hash
    svc._entries[0].entry_hash = "tampered"
    assert svc.verify_chain() is False
