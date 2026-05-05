import json
from typing import List, Optional
from pathlib import Path
import structlog
from ..core.inference_router import ModelInfo

logger = structlog.get_logger(__name__)

class RegistryManager:
    """Add/remove models from HF or GitHub URL to registry."""

    def __init__(self, registry_path: str = "model_registry.json"):
        self.registry_path = Path(registry_path)
        self.models: List[ModelInfo] = []
        self._load()

    def _load(self) -> None:
        if self.registry_path.exists():
            with open(self.registry_path, "r") as f:
                data = json.load(f)
                self.models = [ModelInfo(**m) for m in data.get("models", [])]
            logger.info("Registry loaded", count=len(self.models))

    def _save(self) -> None:
        self.registry_path.parent.mkdir(exist_ok=True)
        with open(self.registry_path, "w") as f:
            json.dump({"models": [m.dict() for m in self.models]}, f, indent=2)
        logger.info("Registry saved", count=len(self.models))

    def add_model(self, model: ModelInfo) -> None:
        if any(m.id == model.id for m in self.models):
            raise ValueError(f"Model {model.id} already exists")
        self.models.append(model)
        self._save()

    def remove_model(self, model_id: str) -> None:
        self.models = [m for m in self.models if m.id != model_id]
        self._save()

    def get_model(self, model_id: str) -> Optional[ModelInfo]:
        return next((m for m in self.models if m.id == model_id), None)

    def list_models(self) -> List[ModelInfo]:
        return self.models

    def update_model(self, model_id: str, **kwargs) -> None:
        model = self.get_model(model_id)
        if not model:
            raise ValueError(f"Model {model_id} not found")
        for k, v in kwargs.items():
            if hasattr(model, k):
                setattr(model, k, v)
        self._save()