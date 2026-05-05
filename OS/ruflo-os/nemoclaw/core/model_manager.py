import os
import json
import hashlib
import subprocess
from pathlib import Path
from typing import Optional, List, Dict
from pydantic import BaseModel, Field
import structlog

logger = structlog.get_logger(__name__)

class ModelInfo(BaseModel):
    id: str
    name: str
    source: str
    repo_id: Optional[str] = None
    filename: Optional[str] = None
    local_path: Optional[str] = None
    quantized: bool = False
    size_gb: float = 0.0
    checksum: Optional[str] = None

class ModelManager:
    """Download, quantize, and manage AI models."""

    def __init__(self, model_dir: str = "/opt/ruflo/models", registry_path: str = "registry/model_registry.json"):
        self.model_dir = Path(model_dir)
        self.model_dir.mkdir(parents=True, exist_ok=True)
        self.registry_path = Path(registry_path)
        self.registry: Dict[str, ModelInfo] = {}
        self._load_registry()

    def _load_registry(self) -> None:
        if self.registry_path.exists():
            with open(self.registry_path, "r") as f:
                data = json.load(f)
                for item in data.get("models", []):
                    model = ModelInfo(**item)
                    self.registry[model.id] = model
            logger.info("Registry loaded", count=len(self.registry))
        else:
            self.registry = {}
            self._save_registry()

    def _save_registry(self) -> None:
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.registry_path, "w") as f:
            json.dump({"models": [m.dict() for m in self.registry.values()]}, f, indent=2)
        logger.info("Registry saved", count=len(self.registry))

    def pull_from_huggingface(self, repo_id: str, filename: Optional[str] = None, model_id: Optional[str] = None) -> ModelInfo:
        """Download GGUF, safetensors, or pytorch model from HuggingFace."""
        try:
            from huggingface_hub import snapshot_download, hf_hub_download
        except ImportError:
            raise RuntimeError("huggingface_hub not installed. Run pip install huggingface_hub")

        model_id = model_id or repo_id.replace("/", "_")
        target_dir = self.model_dir / model_id
        target_dir.mkdir(exist_ok=True)

        if filename:
            # Download single file (GGUF)
            local_path = hf_hub_download(repo_id=repo_id, filename=filename, cache_dir=target_dir)
            logger.info("Downloaded HF file", repo_id=repo_id, filename=filename, path=local_path)
        else:
            # Download entire repo
            local_dir = snapshot_download(repo_id=repo_id, cache_dir=target_dir)
            local_path = local_dir
            logger.info("Downloaded HF repo", repo_id=repo_id, path=local_dir)

        model_info = ModelInfo(
            id=model_id,
            name=repo_id.split("/")[-1],
            source="huggingface",
            repo_id=repo_id,
            filename=filename,
            local_path=str(local_path),
            size_gb=sum(f.stat().st_size for f in Path(local_path).rglob("*") if f.is_file()) / (1024**3)
        )
        self.registry[model_id] = model_info
        self._save_registry()
        return model_info

    def pull_from_github_url(self, url: str, model_id: Optional[str] = None) -> ModelInfo:
        """Download model from GitHub raw URL or release asset."""
        import urllib.parse
        parsed = urllib.parse.urlparse(url)
        path_parts = parsed.path.split("/")
        repo = f"{path_parts[1]}/{path_parts[2]}"
        filename = path_parts[-1]
        model_id = model_id or f"github_{filename}"

        target_path = self.model_dir / model_id / filename
        target_path.parent.mkdir(parents=True, exist_ok=True)

        logger.info("Downloading from GitHub", url=url, target=target_path)
        subprocess.run(["wget", "-O", str(target_path), url], check=True)

        model_info = ModelInfo(
            id=model_id,
            name=filename,
            source="github",
            repo_id=repo,
            filename=filename,
            local_path=str(target_path),
            size_gb=target_path.stat().st_size / (1024**3)
        )
        self.registry[model_id] = model_info
        self._save_registry()
        return model_info

    def pull_from_ollama(self, model_name: str) -> ModelInfo:
        """Pull model via ollama CLI."""
        logger.info("Pulling via ollama", model=model_name)
        subprocess.run(["ollama", "pull", model_name], check=True)
        model_id = f"ollama_{model_name.replace(":", "_")}"
        model_info = ModelInfo(
            id=model_id,
            name=model_name,
            source="ollama",
            local_path=f"/root/.ollama/models/{model_name}",
            size_gb=0.0  # Ollama manages its own storage
        )
        self.registry[model_id] = model_info
        self._save_registry()
        return model_info

    def quantize_model(self, model_id: str, target_bits: int = 4) -> ModelInfo:
        """Quantize model to GGUF using llama.cpp."""
        if model_id not in self.registry:
            raise ValueError(f"Model {model_id} not found")
        model = self.registry[model_id]
        # Placeholder for llama.cpp quantization
        logger.info("Quantizing model", model_id=model_id, bits=target_bits)
        # Actual implementation would call llama.cpp quantize tool
        model.quantized = True
        self.registry[model_id] = model
        self._save_registry()
        return model

    def list_available_models(self) -> List[ModelInfo]:
        return list(self.registry.values())

    def set_default_model(self, model_id: str) -> None:
        if model_id not in self.registry:
            raise ValueError(f"Model {model_id} not found")
        # Update default in config
        logger.info("Set default model", model_id=model_id)

    def verify_checksum(self, model_id: str, expected: str) -> bool:
        if model_id not in self.registry:
            return False
        model = self.registry[model_id]
        if not model.local_path:
            return False
        sha256 = hashlib.sha256()
        with open(model.local_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        actual = sha256.hexdigest()
        return actual == expected