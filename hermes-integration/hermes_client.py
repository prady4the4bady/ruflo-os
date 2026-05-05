"""
Hermes Client - Integration with NousResearch Hermes Agent.
Provides task submission, skill loading, and audit logging.
"""
import httpx
import structlog
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)

HERMES_URL = "http://localhost:8002"


class AgentResponse(BaseModel):
    """Response from Hermes Agent."""
    steps: List[Dict[str, Any]] = Field(default_factory=list)
    result: str = ""
    model_used: str = ""
    tokens_used: int = 0
    success: bool = True


class Skill(BaseModel):
    """Skill definition from Hermes."""
    name: str
    description: str = ""
    trigger_phrases: List[str] = Field(default_factory=list)
    steps: List[str] = Field(default_factory=list)
    required_tools: List[str] = Field(default_factory=list)


class HermesClient:
    """
    Client for Hermes Agent API integration.
    Connects to NousResearch Hermes Agent for intelligence.
    """

    def __init__(self, base_url: str = HERMES_URL, api_key: Optional[str] = None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._client = None

    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            headers = {}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            self._client = httpx.Client(
                base_url=self.base_url,
                headers=headers,
                timeout=60.0
            )
        return self._client

    def send_task(self, task: str, tools: Optional[List[str]] = None) -> AgentResponse:
        """
        Send task to Hermes Agent.
        Returns AgentResponse with steps, result, model used.
        """
        try:
            payload = {"task": task}
            if tools:
                payload["tools"] = tools

            resp = self.client.post("/agent/task", json=payload)
            resp.raise_for_status()

            data = resp.json()
            return AgentResponse(**data)

        except httpx.TimeoutException:
            logger.error("Task timeout", task=task[:50])
            return AgentResponse(success=False, result="Task timeout")
        except Exception as e:
            logger.error("Task failed", error=str(e))
            return AgentResponse(success=False, result=str(e))

    def get_model(self) -> str:
        """Get current model from Hermes /model command."""
        try:
            resp = self.client.get("/agent/model")
            resp.raise_for_status()
            return resp.json().get("model", "unknown")
        except Exception as e:
            logger.error("Get model failed", error=str(e))
            return "unknown"

    def switch_model(self, model_id: str) -> bool:
        """Switch model via Hermes /model command."""
        try:
            resp = self.client.post(
                "/agent/model",
                json={"model": model_id}
            )
            return resp.status_code == 200
        except Exception as e:
            logger.error("Model switch failed", error=str(e))
            return False

    def load_skill_from_hermes(self, skill_name: str) -> Optional[Skill]:
        """Load skill from Hermes skill system."""
        try:
            resp = self.client.post(
                "/skills/load",
                json={"name": skill_name}
            )
            resp.raise_for_status()
            return Skill(**resp.json())
        except Exception as e:
            logger.error("Skill load failed", error=str(e))
            return None

    def get_audit_logs(self, limit: int = 100) -> List[Dict]:
        """Get Hermes audit log (JSONL + SQLite)."""
        try:
            resp = self.client.get("/audit", params={"limit": limit})
            resp.raise_for_status()
            return resp.json().get("logs", [])
        except Exception as e:
            logger.error("Audit log failed", error=str(e))
            return []

    def subscribe_to_agentnet(self, callback):
        """
        Subscribe to AgentNet for multi-agent coordination.
        Uses websockets for real-time communication.
        """
        import websockets
        import asyncio

        async def _subscribe():
            async with websockets.connect("ws://localhost:8003/agentnet") as ws:
                await ws.send_json({"action": "subscribe"})
                async for msg in ws:
                    callback(json.loads(msg))

        try:
            asyncio.get_event_loop().run_until_complete(_subscribe())
        except Exception as e:
            logger.error("AgentNet subscription failed", error=str(e))


if __name__ == "__main__":
    # Test Hermes client
    client = HermesClient()
    print("Testing Hermes connection...")

    model = client.get_model()
    print(f"Current model: {model}")

    # Send a test task
    resp = client.send_task("Research the latest AI news")
    print(f"Task result: {resp.result[:100]}")
