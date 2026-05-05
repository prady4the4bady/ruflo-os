# NemOS (Ruflo OS) - AI-Native Desktop Environment

A production-grade AI-native Linux operating environment built on Debian Bookworm with KDE Plasma 6-inspired shell.

## Architecture

```
ruflo-os/
├── kernel/          # Linux 6.8.x kernel fork
├── distro/          # Debian live-build configuration
├── model-gateway/   # Unified inference proxy (FastAPI)
├── control-plane/   # FastAPI task orchestration
├── runtime/         # NemoClaw/OpenShell sandboxing
├── agents/          # Ruflo + Hermes orchestration
├── accessibility/   # AT-SPI + ydotool + VLM GUI control
├── shell/           # KDE Plasma 6 customization
├── ruflo-shell/     # GTK4/Adwaita desktop shell
├── observability/   # Prometheus + Grafana + OTel
└── tests/           # Test suites
```

## Components Built

### 1. Desktop Shell (`ruflo-shell/`)
- **Dock** - macOS-style dock with running apps
- **MenuBar** - Top bar with system controls
- **Spotlight** - Quick launcher (Cmd+Space)
- **Notifications** - Toast notifications
- **TaskHistory** - View past tasks
- **ApprovalsCenter** - User approval for risky actions
- **AutomationMonitor** - Monitor running tasks
- **PrivacyDashboard** - Privacy settings
- **PermissionsDashboard** - App permissions
- **MemoryViewer** - User preferences and memory
- **WorkflowsApp** - Automation workflows
- **DeveloperConsole** - Logs and debugging
- **SystemHealth** - System metrics
- **Onboarding** - First-run experience
- **RollbackRecovery** - System recovery

### 2. Model Gateway (`model-gateway/`)
- OpenAI-compatible API
- Local model support (Ollama)
- Cloud model fallback (NVIDIA, OpenRouter)
- Semantic caching with Redis

### 3. Control Plane (`control-plane/`)
- Task management API
- PostgreSQL persistence
- Redis pub/sub
- RBAC authorization

### 4. Agent Layer (`agents/`)
- Ruflo + Hermes orchestration
- Multi-agent support
- Screen observation
- OCR service

### 5. Accessibility (`accessibility/`)
- AT-SPI integration
- ydotool for input simulation
- VLM for GUI understanding

## Quick Start

```bash
# Install dependencies
make install

# Run tests
make test

# Run desktop (requires GTK4/Adwaita)
make run

# Run services
make run-gateway  # Model Gateway on :8001
make run-control   # Control Plane on :8000
make run-agent     # Agent Orchestrator
```

## Testing

```bash
# All tests
pytest tests/ -v

# Unit tests
pytest tests/unit/ -v

# Integration tests
pytest tests/integration/ -v

# E2E tests
pytest tests/e2e/ -v

# Desktop tests
pytest tests/desktop/ -v
```

## Configuration

Each service has a `.env.example` file. Copy to `.env` and configure:
- `model-gateway/.env`
- `control-plane/.env`
- `agents/.env`

## License

MIT
