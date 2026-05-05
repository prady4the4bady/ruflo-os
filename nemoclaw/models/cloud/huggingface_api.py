import os
import requests
from typing import Optional, Dict, Any, List

class HuggingFaceAPIBackend:
    """HuggingFace Inference API."""

    def __init__(self, api_key: Optional[str] = None, model: str = "meta-llama/Llama-3.1-70B-Instruct"):
        self.api_key = api_key or os.getenv("HF_API_KEY")
        self.model = model
        self.api_base = "https://api-inference.huggingface.co/models"

    def generate(self, prompt: str, temperature: float = 0.7, max_tokens: int = 1024) -> str:
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload = {
            "inputs": prompt,
            "parameters": {
                "temperature": temperature,
                "max_new_tokens": max_tokens,
                "return_full_text": False
            }
        }

        resp = requests.post(f"{self.api_base}/{self.model}", json=payload, headers=headers)
        resp.raise_for_status()
        result = resp.json()

        if isinstance(result, list) and len(result) > 0:
            return result[0].get("generated_text", "")
        return str(result)

    def list_models(self, search: Optional[str] = None) -> List[Dict]:
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        url = "https://huggingface.co/api/models"
        if search:
            url += f"?search={search}"
        resp = requests.get(url, headers=headers)
        return resp.json()