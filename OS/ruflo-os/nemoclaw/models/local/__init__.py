"""
Local model backends
"""
from .vllm_backend import VLLMBackend 
from .ollama_backend import OllamaBackend 

__all__ = ["VLLMBackend", "OllamaBackend"]
