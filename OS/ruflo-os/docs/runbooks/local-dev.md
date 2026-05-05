# Ruflo OS — Local Development Runbook

## Prerequisites

| Tool | Version | Install |
|------|---------|---------|
| Python | ≥ 3.11 | `apt install python3.11` |
| uv | latest | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Node.js | ≥ 20 | `apt install nodejs` |
| pnpm | ≥ 9 | `npm install -g pnpm` |
| Docker | ≥ 24 | `apt install docker.io` |
| Rust | ≥ 1.75 | `curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs \| sh` |

## Quick Start

```bash
# Clone
git clone https://github.com/prady4the4bady/ruflo-os.git
cd ruflo-os

# Install Python services
make build-python

# Start observability stack
cd observability && docker compose up -d && cd ..

# Start model gateway
cd model-gateway
cp .env.example .env
uvicorn ruflo_model_gateway.main:app --reload --port 8100 &

# Start control plane (needs PostgreSQL)
cd ../control-plane
docker compose up -d postgres
uvicorn ruflo_control_plane.main:app --reload --port 9000 &

# Start accessibility service
cd ../accessibility
uvicorn ruflo_accessibility.api:create_app --factory --reload --port 8200 &
```

## Running Tests

```bash
# All Python tests
make test

# Individual service
cd model-gateway && pytest tests/ -v
cd control-plane && pytest tests/ -v
cd runtime && pytest tests/ -v
cd agents && pytest tests/ -v
cd accessibility && pytest tests/ -v

# With coverage
pytest --cov=src --cov-report=html
```

## Lint & Format

```bash
make lint

# Individual
ruff check --fix .
ruff format .
mypy .
```

## Docker

```bash
# Build all images
make docker-build

# Start all services
make docker-up

# View logs
docker compose logs -f model-gateway
```

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Port 8100 in use | `lsof -i :8100` and kill the process |
| PostgreSQL won't start | `docker compose -f control-plane/docker-compose.yml logs postgres` |
| Ollama not responding | `systemctl status ollama` or `ollama serve` |
| AT-SPI not available | Install `python3-pyatspi` and ensure `at-spi2-core` is running |
