# AGENTS.md — Instructions for AI Coding Agents

This file instructs AI coding agents (Claude Code, Copilot, etc.) on how to work within the Ruflo OS monorepo.

## Repository Overview

Ruflo OS is a production-grade AI-native Linux operating environment. It is a Debian Bookworm-derived distribution with a KDE Plasma 6 macOS-inspired shell, multi-agent orchestration, secure sandbox runtime, and unified model gateway.

## Architecture Layers

1. **OS Base** — Debian 12 + Linux 6.8.x kernel fork (`kernel/`, `distro/`)
2. **Secure Execution** — NemoClaw/OpenShell sandboxing (`runtime/`)
3. **Model Gateway** — Unified inference proxy (`model-gateway/`)
4. **Control Plane** — FastAPI task orchestration (`control-plane/`)
5. **Agent Layer** — Ruflo + Hermes orchestration (`agents/`)
6. **Accessibility** — AT-SPI + ydotool + VLM GUI control (`accessibility/`)
7. **Shell** — KDE Plasma 6 customization (`shell/`)
8. **Observability** — Prometheus + Grafana + OTel (`observability/`)

## Language Boundaries

| Subsystem | Primary Language | Reason |
|-----------|-----------------|--------|
| model-gateway | Python (FastAPI) | ML ecosystem, OpenAI-compatible API |
| control-plane | Python (FastAPI) | Orchestration, PostgreSQL integration |
| runtime | Python + Rust | Rust for sandbox perf, Python for orchestration |
| accessibility | Python | pyatspi2 bindings, subprocess wrappers |
| agents | Python | LLM integration, prompt engineering |
| shell | QML/C++/Shell | KDE Plasma native widget framework |
| observability | Python + YAML | Exporters, config, dashboards |
| distro | Shell/YAML/Make | Debian live-build, systemd, packaging |
| kernel | C/Kconfig/Shell | Kernel config, patches |

## Coding Standards

- **Python**: Use type hints everywhere. Models use Pydantic v2. Async with asyncio. Logging via `structlog`. Tests with `pytest`.
- **TypeScript/JavaScript**: Use strict mode. Validate external payloads with Zod.
- **Rust**: Use `thiserror` for errors, `tracing` for logs, `tokio` for async.
- **QML/C++**: Follow KDE coding conventions. Use KF6/Qt6 APIs.

## Security Rules (Mandatory)

1. Agents NEVER access secrets directly — only via broker-issued opaque handles
2. Destructive actions require explicit user approval
3. Sandbox workers run as non-root
4. All external actions are auditable
5. Default policy is deny-all
6. Prompt injection resistance in all LLM-facing components

## Testing

- Every module must have tests
- Run `make test` from root
- Per-service: `cd <service> && python -m pytest tests/ -v`

## Configuration

- All services use environment variables
- Each service has a `.env.example`
- Never commit real secrets

## File Organization

- Keep files focused (<400 lines preferred)
- One concern per module
- Clear import boundaries between services
- Each subsystem is independently deployable
