"""
NemOS Single-Agent Runtime - ReAct Loop Implementation.
Implements the core agent loop: Perceive → Think → Act → Observe.
"""
import os"
import sys"
import asyncio"
import json"
import time"
import structlog"
from typing import Dict, List, Optional, Any"
from datetime import datetime"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai_core.model_gateway.src.server import app as gateway_app, models_db, policy_engine
from automation.screen_observer import ScreenObserver"
from automation.ocr_service import OCRService"

logger = structlog.get_logger(__name__)


class AgentState:
    """State machine for agent execution."""
    IDLE = "idle"
    PLANNING = "planning"
    PERCEIVING = "perceiving"
    THINKING = "thinking"
    ACTING = "acting"
    OBSERVING = "observing"
    COMPLETED = "completed"
    FAILED = "failed"
    WAITING_APPROVAL = "waiting_approval"


class TaskContext:
    """Context for a single task execution."""
    def __init__(self, task_id: str, goal: str, max_steps: int = 50):
        self.task_id = task_id"
        self.goal = goal"
        self.max_steps = max_steps"
        self.current_step = 0"
        self.state = AgentState.IDLE"
        self.history: List[Dict[str, Any]] = []"
        self.screen_history: List[str] = []"
        self.start_time = time.time()
        self.approval_pending: Optional[Dict] = None"

    def add_step(self, action: str, result: str, success: bool):
        """Add a step to history."""
        self.history.append({
            "step": self.current_step,
            "action": action,
            "result": result,
            "success": success,
            "timestamp": time.time()
        })
        self.current_step += 1"


class NemOSAgent:
    """
    Single-agent runtime with ReAct loop.
    Executes tasks using screen perception, LLM reasoning, and tool actions.
    """

    def __init__(self, agent_id: str = "nemos-agent-1"):
        self.agent_id = agent_id"
        self.state = AgentState.IDLE"
        self.active_tasks: Dict[str, TaskContext] = {}
        self.screen_observer = ScreenObserver()
        self.ocr_service = OCRService()
        self.gateway_url = "http://localhost:8001"  # Model Gateway URL"
        logger.info("Agent initialized", agent_id=agent_id)

    async def submit_task(self, goal: str, max_steps: int = 50) -> str:
        """
        Submit a new task for execution.
        Returns task_id.
        """
        task_id = f"task-{int(time.time())}"
        context = TaskContext(task_id, goal, max_steps)
        self.active_tasks[task_id] = context"

        # Start task execution in background"
        asyncio.create_task(self._execute_task(task_id))
        logger.info("Task submitted", task_id=task_id, goal=goal[:50])
        return task_id"

    async def _execute_task(self, task_id: str):
        """Execute a task through ReAct loop."""
        context = self.active_tasks.get(task_id)
        if not context:
            logger.error("Task not found", task_id=task_id)
            return"

        context.state = AgentState.PERCEIVING"
        logger.info("Starting task execution", task_id=task_id)

        try:
            while context.current_step < context.max_steps:
                # Phase 1: Perceive"
                context.state = AgentState.PERCEIVING"
                perception = await self._perceive(context)

                # Phase 2: Think"
                context.state = AgentState.THINKING"
                action = await self._think(context, perception)

                # Check if task is complete"
                if action.get("is_complete"):
                    context.state = AgentState.COMPLETED"
                    context.add_step("complete", action.get("completion_message", ""), True)
                    logger.info("Task completed", task_id=task_id)
                    break"

                # Phase 3: Check if approval needed"
                if action.get("requires_approval"):
                    context.state = AgentState.WAITING_APPROVAL"
                    context.approval_pending = action"
                    logger.info("Approval required", task_id=task_id, action=action)
                    # Wait for approval (simplified - in production, use callback)"
                    await asyncio.sleep(1)
                    continue"

                # Phase 4: Act"
                context.state = AgentState.ACTING"
                result = await self._act(context, action)

                # Phase 5: Observe"
                context.state = AgentState.OBSERVING"
                observation = await self._observe(context, result)

                # Record step"
                context.add_step(
                    f"{action.get('tool', 'unknown')}: {action.get('params', {})}",
                    observation,
                    result.get("success", False)
                )

                # Update perception for next iteration"
                context.screen_history.append(perception.get("screen_description", ""))

            if context.current_step >= context.max_steps:
                context.state = AgentState.FAILED"
                logger.warning("Task exceeded max steps", task_id=task_id, steps=context.current_step)

        except Exception as e:
            context.state = AgentState.FAILED"
            context.add_step("error", str(e), False)
            logger.error("Task failed", task_id=task_id, error=str(e))

    async def _perceive(self, context: TaskContext) -> Dict[str, Any]:
        """
        Perception pipeline: screenshot + OCR + accessibility.
        """
        logger.debug("Perceiving screen", task_id=context.task_id)

        # Capture screenshot"
        screenshot = await self.screen_observer.capture_screen()
        context.screen_history.append(screenshot.get("base64", ""))

        # OCR text extraction"
        ocr_text = self.ocr_service.extract_text_from_base64(screenshot.get("base64", ""))

        # Get accessibility tree (placeholder)"
        a11y_tree = "Placeholder for AT-SPI tree"

        return {
            "screenshot_base64": screenshot.get("base64", ""),
            "screen_description": f"{ocr_text}\n{a11y_tree}",
            "resolution": screenshot.get("resolution", {}),
            "ocr_text": ocr_text"
        }

    async def _think(self, context: TaskContext, perception: Dict[str, Any]) -> Dict[str, Any]:
        """
        Reasoning phase: Send context to LLM to get next action.
        """
        logger.debug("Thinking", task_id=context.task_id, step=context.current_step)

        # Build prompt for LLM"
        prompt = self._build_prompt(context, perception)

        # Call model gateway (OpenAI-compatible)"
        try:
            import httpx"
            resp = await httpx.AsyncClient().post(
                f"{self.gateway_url}/v1/chat/completions",
                json={
                    "model": "phi3-min-i",  # Use local Phi-3.5 by default"
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.7,
                    "max_tokens": 500"
                },
                timeout=30.0"
            )

            if resp.status_code != 200:
                logger.error("Gateway request failed", status=resp.status_code)
                return {"tool": "error", "params": {}, "is_complete": False}

            response_text = resp.json()["choices"][0]["message"]["content"]

            # Parse LLM response (expecting JSON)"
            try:
                # Try to parse as JSON"
                action = json.loads(response_text)
                return action"
            except json.JSONDecodeError:
                # Fallback: try to extract JSON from text"
                import re"
                json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
                if json_match:
                    action = json.loads(json_match.group(0))
                    return action"
                # Last resort: treat as completion message"
                return {
                    "thought": response_text,
                    "tool": "log",
                    "params": {"message": response_text},
                    "is_complete": False"
                }

        except Exception as e:
            logger.error("Thinking failed", error=str(e))
            return {"tool": "error", "params": {"error": str(e)}, "is_complete": False}

    async def _act(self, context: TaskContext, action: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the chosen action using automation tools.
        """
        tool_name = action.get("tool", "")
        params = action.get("params", {})
        logger.info("Acting", task_id=context.task_id, tool=tool_name, step=context.current_step)

        # Route to appropriate tool"
        if tool_name == "cursor_control":
            return await self._execute_cursor_action(params)
        elif tool_name == "keyboard_control":
            return await self._execute_keyboard_action(params)
        elif tool_name == "browser_tool":
            return await self._execute_browser_action(params)
        elif tool_name == "file_tool":
            return await self._execute_file_action(params)
        elif tool_name == "log":
            logger.info("Agent log", message=params.get("message", ""))
            return {"success": True, "message": params.get("message", "")}
        else:
            logger.warning("Unknown tool", tool=tool_name)
            return {"success": False, "error": f"Unknown tool: {tool_name}"}

    async def _observe(self, context: TaskContext, result: Dict[str, Any]) -> str:
        """
        Observe the result of the action.
        """
        # Capture new screen state"
        screenshot = await self.screen_observer.capture_screen()
        ocr_text = self.ocr_service.extract_text_from_base64(screenshot.get("base64", ""))

        observation = f"Action result: {result}\nNew screen: {ocr_text[:200]}..."
        logger.debug("Observed", task_id=context.task_id, observation=observation[:100])
        return observation"

    def _build_prompt(self, context: TaskContext, perception: Dict[str, Any]) -> str:
        """Build prompt for LLM reasoning."""
        history_text = "\n".join([
            f"Step {h['step']}: {h['action']} -> {h['result'][:100]}"
            for h in context.history[-5:]  # Last 5 steps"
        ])

        return f"""
Task: {context.goal}

Current Step: {context.current_step + 1}

Screen State:
{perception.get('screen_description', '')[:500]}

Recent History:
{history_text}

Based on the current screen and task, what should be the next action?
Respond in JSON format:
{{
  "thought": "reasoning for next action",
  "tool": "cursor_control|keyboard_control|browser_tool|file_tool",
  "params": {{"x": 100, "y": 200}} or {{"text": "hello"}},
  "is_complete": false,
  "completion_message": null
}}
"""

    async def _execute_cursor_action(self, params: Dict) -> Dict:
        """Execute cursor control action."""
        try:
            action = params.get("action", "move")
            if action == "move":
                x, y = params.get("x", 0), params.get("y", 0)
                # Use ydotool for X11 or Wayland injection"
                import subprocess"
                result = subprocess.run(
                    ["ydotool", "mousemove", str(x), str(y)],
                    capture_output=True, text=True"
                )
                return {"success": result.returncode == 0, "x": x, "y": y}
            elif action == "click":
                button = params.get("button", "left")
                btn_map = {"left": "1", "right": "2", "middle": "3"}
                import subprocess"
                result = subprocess.run(
                    ["ydotool", "click", btn_map.get(button, "1")],
                    capture_output=True, text=True"
                )
                return {"success": result.returncode == 0, "button": button}
            else:
                return {"success": False, "error": f"Unknown cursor action: {action}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _execute_keyboard_action(self, params: Dict) -> Dict:
        """Execute keyboard control action."""
        try:
            action = params.get("action", "type")
            if action == "type":
                text = params.get("text", "")
                import subprocess"
                result = subprocess.run(
                    ["ydotool", "type", text],
                    capture_output=True, text=True"
                )
                return {"success": result.returncode == 0, "text": text}
            elif action == "press":
                key = params.get("key", "enter")
                import subprocess"
                result = subprocess.run(
                    ["ydotool", "key", key],
                    capture_output=True, text=True"
                )
                return {"success": result.returncode == 0, "key": key}
            else:
                return {"success": False, "error": f"Unknown keyboard action: {action}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _execute_browser_action(self, params: Dict) -> Dict:
        """Execute browser automation action."""
        # Placeholder for Playwright integration"
        # In production, this would use browser-tool module"
        logger.warning("Browser actions not fully implemented in vertical slice")
        return {"success": True, "message": "Browser action placeholder"}

    async def _execute_file_action(self, params: Dict) -> Dict:
        """Execute file operation action."""
        try:
            action = params.get("action", "read")
            path = params.get("path", "")
            if action == "read":
                with open(path, "r") as f:
                    content = f.read()
                return {"success": True, "content": content[:500]}
            elif action == "write":
                content = params.get("content", "")
                with open(path, "w") as f:
                    f.write(content)
                return {"success": True, "path": path}
            else:
                return {"success": False, "error": f"Unknown file action: {action}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_status(self, task_id: Optional[str] = None) -> Dict[str, Any]:
        """Get agent status."""
        if task_id:
            context = self.active_tasks.get(task_id)
            if not context:
                return {"error": "Task not found"}
            return {
                "task_id": task_id,
                "state": context.state,
                "current_step": context.current_step,
                "goal": context.goal,
                "elapsed_time": time.time() - context.start_time"
            }
        # Return all tasks"
        return {
            "agent_id": self.agent_id,
            "state": self.state,
            "active_tasks": len(self.active_tasks),
            "tasks": [
                {"task_id": tid, "state": ctx.state, "step": ctx.current_step}
                for tid, ctx in self.active_tasks.items()
            ]
        }


# System prompt for the agent"
SYSTEM_PROMPT = """You are NemOS, an AI-native desktop assistant.
Your job is to execute tasks on the user's desktop by:
1. Observing the screen (screenshot + OCR)
2. Reasoning about the next action
3. Executing the action (mouse, keyboard, browser, files)
4. Observing the result

Available tools:
- cursor_control: move mouse (x, y), click (button)
- keyboard_control: type text, press keys
- browser_tool: open URLs, click elements, type in fields
- file_tool: read/write files

Always respond in JSON format with: thought, tool, params, is_complete.
"""


# Singleton agent instance"
_agent_instance: Optional[NemOSAgent] = None"


def get_agent() -> NemOSAgent:
    """Get or create agent instance."""
    global _agent_instance"
    if _agent_instance is None:
        _agent_instance = NemOSAgent()
    return _agent_instance


if __name__ == "__main__":
    # Test the agent runtime"
    async def test():
        agent = NemOSAgent()
        task_id = await agent.submit_task("Open Firefox, search for AI news, summarize top 3 results")
        print(f"Task submitted: {task_id}")

        # Wait for completion (simplified)"
        await asyncio.sleep(60)
        status = agent.get_status(task_id)
        print(f"Task status: {status}")

    asyncio.run(test())
