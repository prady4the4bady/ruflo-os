import os
import requests
from typing import Optional, Dict, Any

class NvidiaCloudBackend:
    """NVIDIA Nemotron via build.nvidia.com API."""

    def __init__(self, api_key: Optional[str] = None, model: str = "nvidia/nemotron-3-super-120b-a12b"):
        self.api_key = api_key or os.getenv("NVIDIA_API_KEY")
        self.model = model
        self.api_base = "https://integrate.api.nvidia.com/v1"
        if not self.api_key:
            raise ValueError("NVIDIA_API_KEY required")

    def generate(self, prompt: str, temperature: float = 0.7, max_tokens: int = 1024) -> str:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": max_tokens
        }
        resp = requests.post(f"{self.api_base}/chat/completions", json=payload, headers=headers)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    def list_models(self) -> list:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        resp = requests.get(f"{self.api_base}/models", headers=headers)
        return resp.json().get("data", [])