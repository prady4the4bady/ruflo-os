"""VLM grounding service — vision-based GUI element detection."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import httpx
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class GroundingResult:
    """Result of VLM-based GUI element grounding."""
    found: bool = False
    element_type: str = ""
    label: str = ""
    bounds: tuple[int, int, int, int] = (0, 0, 0, 0)
    confidence: float = 0.0
    suggested_action: str = ""
    raw_response: str = ""


class VLMGrounding:
    """Uses a Vision Language Model to identify GUI elements in screenshots.

    This is Tier D — the last resort when AT-SPI, ydotool, and xdotool
    cannot identify or interact with the target element.

    Routes inference through the Ruflo model gateway using a vision-capable
    model (e.g., UI-TARS, Qwen2-VL, or a cloud multimodal API).
    """

    def __init__(self, model_gateway_url: str = "http://localhost:8100") -> None:
        self.model_gateway_url = model_gateway_url
        self._client = httpx.AsyncClient(timeout=60.0)

    async def ground(
        self,
        screenshot_b64: str,
        instruction: str,
        context: str = "",
    ) -> GroundingResult:
        """Ask VLM to identify GUI elements matching the instruction."""
        prompt = (
            f"You are a GUI element detector. Analyze this screenshot and find the element "
            f"described by: '{instruction}'. "
            f"Return the element type, label, bounding box (x, y, width, height), "
            f"and the recommended action (click, type, scroll).\n"
            f"Context: {context}" if context else ""
        )

        try:
            response = await self._client.post(
                f"{self.model_gateway_url}/v1/chat/completions",
                json={
                    "model": "vision",
                    "messages": [
                        {"role": "user", "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{screenshot_b64}"}},
                        ]},
                    ],
                    "task_type": "vision",
                    "max_tokens": 512,
                },
            )
            if response.status_code == 200:
                data = response.json()
                text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                return GroundingResult(found=bool(text), raw_response=text, confidence=0.7)
        except Exception as exc:
            logger.error("vlm_grounding.failed", error=str(exc))

        return GroundingResult(found=False)

    async def health_check(self) -> bool:
        try:
            resp = await self._client.get(f"{self.model_gateway_url}/healthz")
            return resp.status_code == 200
        except Exception:
            return False
