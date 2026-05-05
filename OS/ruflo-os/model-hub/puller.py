"""
Model Hub Puller - CLI + library for pulling AI models.
Supports HuggingFace, GitHub, Ollama, and direct URL downloads.
"""
import argparse
import os
import sys
import structlog
from pathlib import Path
from typing import Optional, Dict, Any
import tqdm

logger = structlog.get_logger(__name__)

DEFAULT_MODEL_DIR = "/opt/ruflo/models"


def pull_huggingface(repo_id: str, filename: Optional[str] = None, model_dir: str = DEFAULT_MODEL_DIR) -> Dict[str, Any]:
    """
    Pull model from HuggingFace.
    repo_id: e.g., 'NousResearch/Hermes-3-Llama-3.1-70B-GGUF"
    filename: specific file to download (if None, downloads repo)
    """
    try:
        from huggingface_hub import snapshot_download, hf_hub_download
    except ImportError:
        logger.error("huggingface_hub not installed. Run: pip install huggingface_hub")
        return {"success": False, "error": "huggingface_hub not installed"}

    target_dir = Path(model_dir) / repo_id.replace("/", "_")
    target_dir.mkdir(parents=True, exist_ok=True)

    try:
        if filename:
            # Download single file
            logger.info("Downloading file", repo=repo_id, file=filename)
            local_path = hf_hub_download(
                repo_id=repo_id,
                filename=filename,
                cache_dir=str(target_dir)
            )
            result = {
                "success": True,
                "path": local_path,
                "source": "huggingface",
                "repo_id": repo_id,
                "filename": filename
            }
        else:
            # Download entire repo
            logger.info("Downloading repository", repo=repo_id)
            local_dir = snapshot_download(
                repo_id=repo_id,
                cache_dir=str(target_dir)
            )
            result = {
                "success": True,
                "path": local_dir,
                "source": "huggingface",
                "repo_id": repo_id
            }

        # Register in model registry
        _register_model(result)
        logger.info("Model pulled successfully", **result)
        return result

    except Exception as e:
        logger.error("HuggingFace pull failed", error=str(e))
        return {"success": False, "error": str(e)}


def pull_github(url: str, model_dir: str = DEFAULT_MODEL_DIR) -> Dict[str, Any]:
    """
    Pull model from GitHub release asset URL.
    URL format: https://github.com/USER/REPO/releases/download/v1/model.gguf
    """
    import urllib.parse
    import subprocess

    parsed = urllib.parse.urlparse(url)
    path_parts = parsed.path.split("/")
    if len(path_parts) < 4:
        return {"success": False, "error": "Invalid GitHub URL format"}

    repo = f"{path_parts[1]}/{path_parts[2]}"
    filename = path_parts[-1]
    model_id = f"github_{filename.split('.')[0]}"

    target_path = Path(model_dir) / model_id / filename
    target_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        logger.info("Downloading from GitHub", url=url)
        # Use wget with progress
        proc = subprocess.Popen(
            ["wget", "-O", str(target_path), "--progress=dot:giga", url],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT
        )
        proc.wait()

        if proc.returncode == 0:
            result = {
                "success": True,
                "path": str(target_path),
                "source": "github",
                "repo_id": repo,
                "filename": filename
            }
            _register_model(result)
            logger.info("GitHub model pulled", **result)
            return result
        else:
            return {"success": False, "error": f"wget failed with code {proc.returncode}"}

    except Exception as e:
        logger.error("GitHub pull failed", error=str(e))
        return {"success": False, "error": str(e)}


def pull_ollama(name: str) -> Dict[str, Any]:
    """Pull model via ollama CLI."""
    import subprocess
    try:
        logger.info("Pulling via ollama", model=name)
        result = subprocess.run(
            ["ollama", "pull", name],
            capture_output=True, text=True, timeout=3600
        )
        if result.returncode == 0:
            res = {
                "success": True,
                "source": "ollama",
                "model": name,
                "message": "Pulled via ollama"
            }
            _register_model(res)
            return res
        else:
            return {"success": False, "error": result.stderr}
    except Exception as e:
        logger.error("Ollama pull failed", error=str(e))
        return {"success": False, "error": str(e)}


def pull_from_url(url: str, model_dir: str = DEFAULT_MODEL_DIR) -> Dict[str, Any]:
    """Pull model from direct URL with progress bar."""
    import urllib.request
    from tqdm import tqdm

    filename = url.split("/")[-1]
    model_id = filename.split(".")[0]
    target_path = Path(model_dir) / model_id / filename
    target_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        logger.info("Downloading from URL", url=url)

        # Get file size
        req = urllib.request.Request(url, method="HEAD")
        response = urllib.request.urlopen(req)
        total_size = int(response.headers.get("content-length", 0))

        # Download with progress
        with tqdm.tqdm(total=total_size, unit="B", unit_scale=True) as pbar:
            def report_hook(block_num, block_size, total_size):
                pbar.update(block_size)

            urllib.request.urlretrieve(url, str(target_path), reporthook=report_hook)

        result = {
            "success": True,
            "path": str(target_path),
            "source": "url",
            "url": url,
            "filename": filename
        }
        _register_model(result)
        logger.info("URL model pulled", **result)
        return result

    except Exception as e:
        logger.error("URL pull failed", error=str(e))
        return {"success": False, "error": str(e)}


def _register_model(info: Dict[str, Any]):
    """Register model in registry after download."""
    registry_path = Path(DEFAULT_MODEL_DIR).parent / "nemoclaw/registry/model_registry.json"
    if not registry_path.exists():
        return

    try:
        with open(registry_path, "r") as f:
            data = __import__("json").load(f)

        # Find or create model entry
        model_id = info.get("model") or info.get("filename", "unknown").split(".")[0]
        entry = next((m for m in data.get("models", []) if m.get("id") == model_id), None)

        if not entry:
            entry = {"id": model_id}
            data.setdefault("models", []).append(entry)

        entry["source"] = info.get("source", "unknown")
        entry["local_path"] = info.get("path")
        entry["loaded"] = True

        with open(registry_path, "w") as f:
            __import__("json").dump(data, f, indent=2)

    except Exception as e:
        logger.error("Failed to register model", error=str(e))


def auto_detect_format(filename: str) -> str:
    """Auto-detect model format from filename."""
    if filename.endswith(".gguf"):
        return "GGUF"
    elif filename.endswith(".safetensors"):
        return "safetensors"
    elif filename.endswith(".bin") or "pytorch" in filename:
        return "pytorch"
    else:
        return "unknown"


def main():
    parser = argparse.ArgumentParser(description="Ruflo OS Model Puller")
    parser.add_argument("--source", choices=["hf", "github", "ollama", "url"], required=True)
    parser.add_argument("--id", help="Model ID, repo, or URL")
    parser.add_argument("--file", help="Filename (for HuggingFace)")
    parser.add_argument("--dir", default=DEFAULT_MODEL_DIR, help="Model directory")

    args = parser.parse_args()

    if args.source == "hf":
        if not args.id:
            print("Error: --id required for HuggingFace")
            sys.exit(1)
        result = pull_huggingface(args.id, args.file, args.dir)
    elif args.source == "github":
        if not args.id:
            print("Error: --id (URL) required for GitHub")
            sys.exit(1)
        result = pull_github(args.id, args.dir)
    elif args.source == "ollama":
        if not args.id:
            print("Error: --id (model name) required for Ollama")
            sys.exit(1)
        result = pull_ollama(args.id)
    elif args.source == "url":
        if not args.id:
            print("Error: --id (URL) required")
            sys.exit(1)
        result = pull_from_url(args.id, args.dir)
    else:
        print("Error: Unknown source")
        sys.exit(1)

    if result["success"]:
        print(f"✓ Model pulled: {result}")
        sys.exit(0)
    else:
        print(f"✗ Failed: {result.get('error')}")
        sys.exit(1)


if __name__ == "__main__":
    main()
