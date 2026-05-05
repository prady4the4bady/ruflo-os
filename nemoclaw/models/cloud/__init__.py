"""
Cloud model backends
"""
from .nvidia_cloud import NvidiaCloudBackend 
from .openai_compat import OpenAICompatBackend 
from .huggingface_api import HuggingFaceAPIBackend 

__all__ = ["NvidiaCloudBackend", "OpenAICompatBackend", "HuggingFaceAPIBackend"]
