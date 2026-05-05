import os
import subprocess
from typing import Optional, Dict, Any

class BaseBackend:
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}

    def generate(self, prompt: str, **kwargs) -> str:
        raise NotImplementedError

class VLLMBackend(BaseBackend):
    """vLLM local inference backend."""

    def __init__(self, model_path: str, **kwargs):
        super().__init__(kwargs)
        self.model_path = model_path
        # Placeholder for vLLM initialization
        # from vllm import LLM
        # self.llm = LLM(model=model_path)

    def generate(self, prompt: str, **kwargs) -> str:
        # Placeholder for vLLM generation
        return f"vLLM response to: {prompt[:50]}"

class OllamaBackend(BaseBackend):
    """Ollama local inference backend."""

    def __init__(self, model_name: str, **kwargs):
        super().__init__(kwargs)
        self.model_name = model_name

    def generate(self, prompt: str, **kwargs) -> str:
        try:
            result = subprocess.run(
                ["ollama", "run", self.model_name, prompt],
                capture_output=True, text=True, check=True
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            return f"Ollama error: {e.stderr}"