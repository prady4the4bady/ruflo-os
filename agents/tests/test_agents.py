"""Tests for agents."""

import pytest
from ruflo_agents.base import AgentContext
from ruflo_agents.gui_operator.agent import GuiOperatorAgent
from ruflo_agents.browser.agent import BrowserAgent
from ruflo_agents.coding.agent import CodingAgent
from ruflo_agents.file.agent import FileAgent
from ruflo_agents.verifier.agent import VerifierAgent
from ruflo_agents.hermes_adapter.adapter import HermesMemoryAdapter
from ruflo_agents.recovery.hooks import attempt_recovery


@pytest.fixture
def context():
    return AgentContext(task_id="test-1", goal="Test task", step_description="Click the submit button")


@pytest.mark.asyncio
async def test_gui_agent_can_handle(context):
    agent = GuiOperatorAgent()
    score = await agent.can_handle(context)
    assert score > 0  # "Click" should match


@pytest.mark.asyncio
async def test_browser_agent_can_handle():
    ctx = AgentContext(step_description="Browse to github.com")
    agent = BrowserAgent()
    assert await agent.can_handle(ctx) > 0


@pytest.mark.asyncio
async def test_coding_agent_can_handle():
    ctx = AgentContext(step_description="Write a Python script to process CSV")
    agent = CodingAgent()
    assert await agent.can_handle(ctx) > 0


@pytest.mark.asyncio
async def test_file_agent_destructive_needs_approval():
    ctx = AgentContext(step_description="Delete the old backup files")
    agent = FileAgent()
    result = await agent.execute(ctx)
    assert result.needs_approval is True


@pytest.mark.asyncio
async def test_verifier_agent():
    ctx = AgentContext(step_description="Verify the file was created")
    agent = VerifierAgent()
    result = await agent.execute(ctx)
    assert result.success is True


@pytest.mark.asyncio
async def test_hermes_memory():
    memory = HermesMemoryAdapter()
    await memory.store_episodic("task-1", "Opened Firefox and navigated to example.com")
    await memory.store_semantic("User prefers dark mode")
    await memory.store_procedural("open_firefox", ["click dock icon", "wait for window"])

    results = await memory.recall("Firefox")
    assert len(results) > 0
    assert memory.stats["procedural"] == 1


@pytest.mark.asyncio
async def test_recovery_retry():
    ctx = AgentContext(step_description="Test recovery")
    result = await attempt_recovery("test_agent", ctx, "Connection timeout", attempt=1)
    assert result.should_retry is True


@pytest.mark.asyncio
async def test_recovery_exhausted():
    ctx = AgentContext(step_description="Test exhausted")
    result = await attempt_recovery("test_agent", ctx, "Fatal error", attempt=3)
    assert result.should_retry is False
    assert result.needs_approval is True
