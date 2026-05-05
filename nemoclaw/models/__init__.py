"""
Nemoclaw Models
"""
from .local.vllm_backend import VLLMBackend 
from .local.ollama_backend import OllamaBackend 
from .cloud.nvidia_cloud import NvidiaCloudBackend 
from .cloud.openai_compat import OpenAICompatBackend 
from .cloud.huggingface_api import HuggingFaceAPIBackend 

__all__ = [
    "VLLMBackend", "OllamaBackend", "NvidiaCloudBackend", "OpenAICompatBackend", "HuggingFaceAPIBackend"
]
