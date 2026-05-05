import os
import sys
import time
import json
import structlog
from typing import Optional, Dict, List, Literal
from pydantic import BaseModel, Field
from enum import Enum

logger = structlog.get_logger(__name__)

class ModelType(str, Enum):
    LOCAL_GGUF = "local_gguf"
    LOCAL_SAFETENSORS = "local_safetensors"
    CLOUD_OPENAI = "cloud_openai"
    CLOUD_NVIDIA = "cloud_nvidia"
    CLOUD_HF = "cloud_hf"

class ModelInfo(BaseModel):
    id: str
    name: str
    type: ModelType
    source: str
    repo_id: Optional[str] = None
    filename: Optional[str] = None
    context_length: int = 4096
    use_cases: List[str] = Field(default_factory=list)
    loaded: bool = False
    vram_required_gb: float = 0.0
    api_base: Optional[str] = None

class RoutingDecision(BaseModel):
    model_id: str
    reason: str
    latency_ms: float

class InferenceRouter:
    """Routes LLM calls to local or cloud based on task requirements, hardware, and preferences."""

    def __init__(self, config_path: str = "/app/nemoclaw.config.yaml"):
        self.config_path = config_path
        self.models: Dict[str, ModelInfo] = {}
        self.default_model_id: str = "default"
        self.gpu_available: bool = False
        self.gpu_vram_gb: float = 0.0
        self._load_registry()
        self._detect_hardware()

    def _detect_hardware(self) -> None:
        """Auto-detect GPU capabilities (CUDA/ROCm/Metal/CPU)."""
        try:
            import torch
            if torch.cuda.is_available():
                self.gpu_available = True
                self.gpu_vram_gb = torch.cuda.get_device_properties(0).total_mem / (1024 ** 3)
                logger.info("GPU detected", vram_gb=self.gpu_vram_gb, device=torch.cuda.get_device_name(0))
            else:
                self.gpu_available = False
                logger.info("No GPU detected, using CPU")
        except ImportError:
            self.gpu_available = False
            logger.warning("torch not available, assuming CPU")

    def _load_registry(self) -> None:
        """Load model registry from JSON file."""
        registry_path = os.path.join(os.path.dirname(self.config_path), "registry", "model_registry.json")
        if os.path.exists(registry_path):
            with open(registry_path, "r") as f:
                data = json.load(f)
                for model_data in data.get("models", []):
                    model = ModelInfo(**model_data)
                    self.models[model.id] = model
            logger.info("Loaded model registry", count=len(self.models))
        else:
            logger.warning("Model registry not found", path=registry_path)

    def route(
        self,
        task: str,
        prefer_speed: bool = False,
        prefer_quality: bool = False,
        force_model: Optional[str] = None
    ) -> RoutingDecision:
        """Route to the best model for the given task."""
        start = time.time()

        if force_model and force_model in self.models:
            model = self.models[force_model]
            return RoutingDecision(
                model_id=force_model,
                reason=f"Forced model {force_model}",
                latency_ms=(time.time() - start) * 1000
            )

        # Task-based routing
        task_lower = task.lower()
        if any(kw in task_lower for kw in ["code", "program", "script", "debug"]):
            for mid, m in self.models.items():
                if "code" in m.use_cases:
                    return RoutingDecision(mid, "Code task matched", (time.time() - start)*1000)
        if any(kw in task_lower for kw in ["image", "screen", "see", "visual", "button"]):
            for mid, m in self.models.items():
                if "vision" in m.use_cases:
                    return RoutingDecision(mid, "Vision task matched", (time.time() - start)*1000)
        if prefer_speed or any(kw in task_lower for kw in ["quick", "fast", "simple"]):
            for mid, m in self.models.items():
                if "fast" in m.use_cases:
                    return RoutingDecision(mid, "Fast task matched", (time.time() - start)*1000)

        # Default model
        if self.default_model_id in self.models:
            return RoutingDecision(
                self.default_model_id,
                "Default model selected",
                (time.time() - start)*1000
            )

        # Fallback to any loaded model
        for mid, m in self.models.items():
            if m.loaded:
                return RoutingDecision(mid, "Fallback to loaded model", (time.time() - start)*1000)

        raise RuntimeError("No suitable model found for task")

    def list_models(self) -> List[ModelInfo]:
        return list(self.models.values())

    def get_model(self, model_id: str) -> Optional[ModelInfo]:
        return self.models.get(model_id)

    def update_model_status(self, model_id: str, loaded: bool) -> None:
        if model_id in self.models:
            self.models[model_id].loaded = loaded
            logger.info("Model status updated", model_id=model_id, loaded=loaded)

    def hot_swap(self, new_default_id: str) -> None:
        """Hot-swap default model without restart."""
        if new_default_id not in self.models:
            raise ValueError(f"Model {new_default_id} not found")
        old = self.default_model_id
        self.default_model_id = new_default_id
        logger.info("Hot-swapped default model", old=old, new=new_default_id)

    def cloud_fallback(self, task: str) -> RoutingDecision:
        """Fallback to cloud model (NVIDIA Nemotron)."""
        for mid, m in self.models.items():
            if m.type == ModelType.CLOUD_NVIDIA:
                return RoutingDecision(mid, "Cloud fallback", 0.0)
        raise RuntimeError("No cloud fallback model configured")

    def __del__(self):
        pass