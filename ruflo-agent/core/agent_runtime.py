import os
import json
import time
import base64
import asyncio
from typing import Optional, Dict, List, Any
from pydantic import BaseModel, Field
import structlog
from PIL import ImageGrab
import io

logger = structlog.get_logger(__name__)

class Action(BaseModel):
    tool: str
    params: Dict[str, Any]

class AgentStep(BaseModel):
    thought: str
    action: Action
    is_complete: bool
    completion_message: Optional[str] = None

class TaskContext(BaseModel):
    task: str
    step: int = 0
    screen_description: str = ""
    screenshot_base64: str = ""
    available_tools: List[str] = Field(default_factory=list)
    history: List[Dict] = Field(default_factory=list)
    memory: List[str] = Field(default_factory=list)

class RufloAgentRuntime:
    """Autonomous execution engine using ReAct (Reason + Act) loop."""

    def __init__(self, config_path: str = "agent.config.yaml"):
        self.config = self._load_config(config_path)
        self.tools = self._init_tools()
        self.memory = None
        self.planner = None
        self.running = False
        self.current_task: Optional[TaskContext] = None

    def _load_config(self, config_path: str) -> dict:
        try:
            with open(config_path, "r") as f:
                import yaml
                return yaml.safe_load(f)
        except FileNotFoundError:
            return {}

    def _init_tools(self) -> Dict[str, Any]:
        from ..tools import (ScreenCapture, CursorControl, KeyboardControl,
                            BrowserTool, FileTool, TerminalTool, VisionTool)
        return {
            "screen_capture": ScreenCapture(),
            "cursor_control": CursorControl(),
            "keyboard_control": KeyboardControl(),
            "browser_tool": BrowserTool(),
            "file_tool": FileTool(),
            "terminal_tool": TerminalTool(),
            "vision_tool": VisionTool(),
        }

    async def perceive(self) -> Dict[str, Any]:
        """Capture screen, OCR, accessibility tree."""
        screenshot = ImageGrab.grab()
        buffered = io.BytesIO()
        screenshot.save(buffered, format="PNG")
        img_str = base64.b64encode(buffered.getvalue()).decode()

        # Get OCR text
        from ..perception import OCREngine
        ocr_text = OCREngine().extract_text(screenshot)

        # Get accessibility tree
        from ..perception import AccessibilityReader
        acc_tree = AccessibilityReader().get_accessible_tree()

        return {
            "screenshot_base64": img_str,
            "screen_description": f"{ocr_text}\n{json.dumps(acc_tree)}",
            "resolution": screenshot.size
        }

    async def think(self, context: TaskContext) -> AgentStep:
        """Send context to LLM, get next action."""
        # Placeholder for LLM call
        # In production, this calls InferenceRouter
        return AgentStep(
            thought="Need to click the search bar",
            action=Action(tool="cursor_control", params={"x": 500, "y": 300}),
            is_complete=False
        )

    async def act(self, action: Action) -> Dict[str, Any]:
        """Execute action via computer control tools."""
        if action.tool not in self.tools:
            raise ValueError(f"Tool {action.tool} not found")
        tool = self.tools[action.tool]
        result = await tool.execute(**action.params)
        return result

    async def observe(self) -> Dict[str, Any]:
        """Capture new screen state after action."""
        return await self.perceive()

    async def run_task(self, task: str) -> str:
        """Main ReAct loop."""
        self.running = True
        context = TaskContext(
            task=task,
            available_tools=list(self.tools.keys())
        )
        logger.info("Starting task", task=task)

        while self.running and not context.step > 50:  # Max 50 steps
            # Perceive
            perceive_data = await self.perceive()
            context.screenshot_base64 = perceive_data["screenshot_base64"]
            context.screen_description = perceive_data["screen_description"]

            # Think
            step = await self.think(context)
            context.history.append(step.dict())
            context.step += 1

            if step.is_complete:
                logger.info("Task completed", message=step.completion_message)
                return step.completion_message or "Task completed"

            # Act
            act_result = await self.act(step.action)
            logger.info("Action executed", tool=step.action.tool, result=act_result)

            # Observe
            observe_data = await self.observe()
            # Update context with observation

        return "Task stopped or max steps reached"

    async def stop(self) -> None:
        self.running = False
        logger.info("Agent stopped")