# Ruflo OS Model Guide

## Default Models (Section 12)

### Default (General Purpose)
- **Name**: Nous-Hermes-3-Llama-3.1-70B
- **Source**: HuggingFace
- **Repo**: `NousResearch/Hermes-3-Llama-3.1-70B-GGUF`
- **File**: `Hermes-3-Llama-3.1-70B.Q4_K_M.gguf`
- **Use Cases**: General reasoning, planning
- **Context Length**: 131072 tokens
- **VRAM Required**: ~42GB

### Vision
- **Name**: LLaVA-1.6-34B
- **Source**: HuggingFace
- **Repo**: `liuhaotian/llava-v1.6-34b`
- **Use Cases**: Screen understanding, element detection
- **VRAM Required**: ~68GB

### Code
- **Name**: DeepSeek-Coder-V2-16B
- **Source**: HuggingFace
- **Repo**: `deepseek-ai/DeepSeek-Coder-V2-Lite-Instruct-GGUF`
- **Use Cases**: Code writing, terminal tasks
- **VRAM Required**: ~32GB

### Fast
- **Name**: Phi-3.5-Mini-Instruct
- **Source**: HuggingFace
- **Repo**: `microsoft/Phi-3.5-mini-instruct-gguf`
- **Use Cases**: Quick actions, simple navigation
- **VRAM Required**: ~4GB

### Cloud Fallback
- **Name**: nvidia/nemotron-3-super-120b-a12b
- **Source**: NVIDIA Cloud
- **API Base**: `https://integrate.api.nvidia.com/v1`
- **Use Cases**: All (fallback when local unavailable)

## Pulling Custom Models

### Via API
```bash
# From HuggingFace
curl -X POST http://localhost:7474/api/v1/models/pull \
  -H "Content-Type: application/json" \
  -d '{"source": "huggingface", "identifier": "meta-llama/Llama-3.3-70B-Instruct"}'

# From GitHub URL
curl -X POST http://localhost:7474/api/v1/models/pull \
  -H "Content-Type: application/json" \
  -d '{"source": "github", "identifier": "https://github.com/ggerganov/llama.cpp/releases/download/b3000/llama-model.gguf"}'
```

### Via Model Manager UI
1. Open ModelManager app
2. Paste HuggingFace repo URL or GitHub release URL
3. Click Pull
4. (Optional) Click "Set as Default" to use for all future tasks

## Model Quantization
Use `model-hub/quantizer.py` to quantize models to GGUF:
```bash
python model-hub/quantizer.py /path/to/model /path/to/output.gguf 4
```