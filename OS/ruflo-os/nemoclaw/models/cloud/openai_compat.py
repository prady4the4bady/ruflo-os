import os
import requests
from typing import Optional, Dict, Any, List

class OpenAICompatBackend:
    """Any OpenAI-compatible endpoint."""

    def __init__(self, api_base: str, api_key: Optional[str] = None, model: str = "gpt-3.5-turbo"):
        self.api_base = api_base.rstrip("/")
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model = model

    def generate(self, prompt: str, temperature: float = 0.7, max_tokens: int = 1024, **kwargs) -> str:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": max_tokens,
            **kwargs
        }

        resp = requests.post(f"{self.api_base}/chat/completions", json=payload, headers=headers)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    def list_models(self) -> List[Dict]:
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        resp = requests.get(f"{self.api_base}/models", headers=headers)
        return resp.json().get("data", [])