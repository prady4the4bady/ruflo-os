"""Tests for runtime — sandbox, brokers, NemoClaw bridge."""

import pytest
from ruflo_runtime.sandbox.manager import SandboxManager, SandboxState
from ruflo_runtime.sandbox.policy import PolicyTemplate
from ruflo_runtime.brokers.file_broker import FileBroker
from ruflo_runtime.brokers.secret_broker import SecretBroker
from ruflo_runtime.brokers.network_broker import NetworkBroker, NetworkRule
from ruflo_runtime.nemoclaw.bridge import LocalNemoClawBridge, InferenceRequest


# ── Sandbox tests ──

@pytest.mark.asyncio
async def test_sandbox_create_and_destroy():
    mgr = SandboxManager()
    sb = await mgr.create("task-1", template="default")
    assert sb.state == SandboxState.READY
    assert sb.user == "ruflo-worker"
    await mgr.destroy(sb.sandbox_id)
    assert sb.state == SandboxState.TERMINATED


@pytest.mark.asyncio
async def test_sandbox_execute():
    mgr = SandboxManager()
    sb = await mgr.create("task-2")
    result = await mgr.execute(sb.sandbox_id, "echo hello")
    assert result["exit_code"] == 0


def test_policy_templates():
    templates = PolicyTemplate.list_templates()
    assert "default" in templates
    assert "restricted" in templates
    assert "coding" in templates
    p = PolicyTemplate.get("restricted")
    assert p.network_allowed is False
    assert p.process_max_memory_mb == 512


def test_policy_template_copy():
    p1 = PolicyTemplate.get("default")
    p2 = PolicyTemplate.get("default")
    p1.network_allowed = False
    assert p2.network_allowed is True  # Should not be affected


# ── File broker tests ──

def test_file_broker_issue_handle():
    broker = FileBroker()
    handle = broker.issue_handle("/tmp/test.txt", "task-1", "read")
    assert handle.handle_id
    assert handle.display_name == "test.txt"
    assert handle.permissions == "read"


def test_file_broker_deny_sensitive():
    broker = FileBroker()
    with pytest.raises(PermissionError):
        broker.issue_handle("/etc/shadow", "task-1", "read")


def test_file_broker_deny_ssh():
    broker = FileBroker()
    with pytest.raises(PermissionError):
        broker.issue_handle("/home/user/.ssh/id_rsa", "task-1", "read")


def test_file_broker_revoke():
    broker = FileBroker()
    handle = broker.issue_handle("/tmp/test.txt", "task-1", "read")
    broker.revoke(handle.handle_id)
    with pytest.raises(PermissionError):
        import asyncio
        asyncio.get_event_loop().run_until_complete(broker.read(handle.handle_id))


# ── Secret broker tests ──

def test_secret_broker_no_raw_access():
    broker = SecretBroker()
    broker.register_secret("smtp_password", "s3cret123")
    handle = broker.issue_handle("smtp_password", "task-1", "send_email_via_work")
    # Agent only sees handle_id and scoped_action, NOT the raw secret
    assert "s3cret" not in handle.handle_id
    assert handle.scoped_action == "send_email_via_work"


def test_secret_broker_use_limit():
    broker = SecretBroker()
    broker.register_secret("api_key", "key123")
    handle = broker.issue_handle("api_key", "task-1", "call_api", max_uses=1)
    import asyncio
    asyncio.get_event_loop().run_until_complete(broker.use_secret(handle.handle_id))
    with pytest.raises(PermissionError):
        asyncio.get_event_loop().run_until_complete(broker.use_secret(handle.handle_id))


# ── Network broker tests ──

def test_network_broker_default_deny():
    broker = NetworkBroker()
    assert broker.check("example.com", 443) is False


def test_network_broker_allow_rule():
    broker = NetworkBroker(default_rules=[
        NetworkRule(host_pattern="*.github.com", ports=[443]),
    ])
    assert broker.check("api.github.com", 443) is True
    assert broker.check("evil.com", 443) is False


def test_network_broker_always_deny_metadata():
    broker = NetworkBroker(default_rules=[
        NetworkRule(host_pattern="*", ports=[80, 443]),
    ])
    assert broker.check("169.254.169.254", 80) is False


# ── NemoClaw bridge tests ──

@pytest.mark.asyncio
async def test_nemoclaw_bridge_infer():
    bridge = LocalNemoClawBridge()
    result = await bridge.infer(InferenceRequest(model="test", prompt="hello", task_id="t-1"))
    assert result.routed_to == "local"


@pytest.mark.asyncio
async def test_nemoclaw_bridge_health():
    bridge = LocalNemoClawBridge()
    assert await bridge.health_check() is True
