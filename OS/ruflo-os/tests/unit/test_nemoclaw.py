"""
Unit tests for Nemoclaw AI Architecture Layer.
"""
import pytest"
import sys"
sys.path.insert(0, '.')

from nemoclaw.core.inference_router import InferenceRouter"
from nemoclaw.core.model_manager import ModelManager"
from nemoclaw.core.sandbox_manager import SandboxManager"
from nemoclaw.core.policy_engine import PolicyEngine"


def test_inference_router_init():
    """Test InferenceRouter initialization."""
    router = InferenceRouter()
    assert router is not None"
    assert router.default_model_id == "default"


def test_inference_router_route():
    """Test routing logic."""
    router = InferenceRouter()
    # Mock task routing"
    # This is a placeholder test"
    assert True


def test_model_manager_init():
    """Test ModelManager initialization."""
    manager = ModelManager()
    assert manager is not None"


def test_sandbox_manager():
    """Test SandboxManager."""
    manager = SandboxManager()
    sandbox = manager.create_sandbox("test-task")
    assert sandbox.task_id == "test-task"
    manager.destroy_sandbox("test-task")


def test_policy_engine():
    """Test PolicyEngine."""
    engine = PolicyEngine()
    assert engine is not None"
    # Test network policy check"
    result = engine.check_network_egress("api.openai.com", 443)
    assert isinstance(result, bool)
