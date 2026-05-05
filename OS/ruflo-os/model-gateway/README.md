# Model Gateway

Unified AI model inference gateway for Ruflo OS providing OpenAI-compatible REST endpoints with multi-provider routing.

## Features

- **OpenAI-compatible API**: Drop-in replacement for OpenAI chat completions
- **6 Provider Adapters**: Ollama, vLLM, SGLang (local), Anthropic, OpenAI, Gemini (cloud)
- **Smart Routing**: Task-type, cost, and local-preference-aware model selection
- **Model Registry**: Persistent SQLite registry supporting Hugging Face/GitHub model URLs
- **Prometheus Metrics**: Request counts, latency histograms, token usage, provider health
- **Streaming**: Full SSE streaming support for all providers

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/v1/chat/completions` | Chat completion (streaming/non-streaming) |
| GET | `/v1/models` | List registered models |
| POST | `/v1/models/register` | Register a new model |
| DELETE | `/v1/models/{model_id}` | Deregister a model |
| GET | `/healthz` | Liveness probe |
| GET | `/readyz` | Readiness probe |
| GET | `/metrics` | Prometheus metrics |
| GET | `/docs` | OpenAPI documentation |

## Quick Start

```bash
# Install
pip install -e ".[dev]"

# Configure
cp .env.example .env

# Run
uvicorn ruflo_model_gateway.main:app --reload --port 8100

# Test
pytest tests/ -v
```

## Routing Logic

1. **Explicit provider**: `ollama/llama3` routes to Ollama
2. **Registry match**: Known model ID maps to registered provider
3. **Task-type routing**: `task_type=coding` prefers coding-capable models
4. **Local preference**: Tries Ollama → vLLM → SGLang before cloud
5. **Cloud fallback**: Anthropic → OpenAI → Gemini
6. **Default**: Falls back to configured default provider

## Docker

```bash
docker build -t ruflo-os/model-gateway .
docker run -p 8100:8100 --env-file .env ruflo-os/model-gateway
```
