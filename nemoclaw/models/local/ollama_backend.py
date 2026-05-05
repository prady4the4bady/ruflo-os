import os
import subprocess
from typing import Optional, Dict

class OllamaBackend:
    """Ollama local inference backend."""

    def __init__(self, model_name: str):
        self.model_name = model_name
        self._check_ollama()

    def _check_ollama(self) -> None:
        try:
            subprocess.run(["ollama", "list"], capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            raise RuntimeError("Ollama not installed or not running")

    def generate(self, prompt: str, temperature: float = 0.7, max_tokens: int = 1024) -> str:
        """Generate text using Ollama."""
        cmd = ["ollama", "run", self.model_name, prompt,
               "--temperature", str(temperature), "--num-predict", str(max_tokens)]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"Ollama generation failed: {result.stderr}")
        return result.stdout.strip()

    def list_models(self) -> list:
        result = subprocess.run(["ollama", "list"], capture_output=True, text=True)
        return result.stdout.splitlines()