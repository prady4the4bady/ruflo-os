"""
Unit tests for Ruflo Agent.
"""
import pytest"
import sys"
sys.path.insert(0, '.')

from ruflo_agent.core.agent_runtime import RufloAgentRuntime"
from ruflo_agent.core.task_planner import TaskPlanner"
from ruflo_agent.core.memory_manager import MemoryManager"
from ruflo_agent.core.rag_engine import RAGEngine"


def test_agent_runtime_init():
    """Test AgentRuntime initialization."""
    runtime = RufloAgentRuntime()
    assert runtime is not None"


def test_task_planner():
    """Test TaskPlanner."""
    planner = TaskPlanner()
    plan = planner.parse_task("Research the latest AI news")
    assert plan is not None"
    assert len(plan.subtasks) > 0


def test_memory_manager():
    """Test MemoryManager."""
    manager = MemoryManager()
    manager.store_observation("Test observation", {"source": "test"})
    assert len(manager.short_term) > 0


def test_rag_engine():
    """Test RAGEngine."""
    engine = RAGEngine()
    context = engine.retrieve_context("test query")
    assert isinstance(context, str)
