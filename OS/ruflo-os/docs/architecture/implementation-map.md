# Ruflo OS — Implementation Map

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     User Interface                          │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────────┐ │
│  │   Dock   │  │ Launcher │  │ Top Bar  │  │ AI Activity│ │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └─────┬──────┘ │
│       └──────────────┴─────────────┴──────────────┘        │
│                     KDE Plasma 6 / Wayland                  │
├─────────────────────────────────────────────────────────────┤
│                     Control Plane (:9000)                    │
│  ┌─────────┐ ┌──────────┐ ┌────────┐ ┌──────┐ ┌────────┐  │
│  │  Tasks  │ │Orchestr. │ │Approval│ │Policy│ │ Audit  │  │
│  │  API    │ │ Engine   │ │ Broker │ │Engine│ │Service │  │
│  └─────────┘ └──────────┘ └────────┘ └──────┘ └────────┘  │
├─────────────────────────────────────────────────────────────┤
│                     Agent Layer                             │
│  ┌────────┐ ┌────────┐ ┌──────┐ ┌──────┐ ┌────────┐       │
│  │  GUI   │ │Browser │ │Coding│ │ File │ │Verifier│       │
│  │Operator│ │ Agent  │ │Agent │ │Agent │ │ Agent  │       │
│  └───┬────┘ └────────┘ └──────┘ └──┬───┘ └────────┘       │
│      │    Ruflo Swarm + Hermes     │                       │
├──────┼─────────────────────────────┼───────────────────────┤
│      ▼                             ▼                       │
│  Accessibility (:8200)       Runtime / Brokers              │
│  ┌──────┐ ┌───────┐       ┌──────┐ ┌──────┐ ┌────────┐   │
│  │AT-SPI│ │ydotool│       │ File │ │Secret│ │Network │   │
│  └──────┘ └───────┘       │Broker│ │Broker│ │Broker  │   │
│  ┌──────┐ ┌───────┐       └──────┘ └──────┘ └────────┘   │
│  │xdotool│ │  VLM  │       ┌──────────────────┐           │
│  └──────┘ └───────┘       │  Sandbox Manager  │           │
│                            │  NemoClaw Bridge  │           │
│                            └──────────────────┘           │
├─────────────────────────────────────────────────────────────┤
│                  Model Gateway (:8100)                       │
│  ┌──────┐ ┌──────┐ ┌──────┐ ┌─────────┐ ┌──────┐ ┌──────┐│
│  │Ollama│ │ vLLM │ │SGLang│ │Anthropic│ │OpenAI│ │Gemini││
│  └──────┘ └──────┘ └──────┘ └─────────┘ └──────┘ └──────┘│
│              ┌──────────┐  ┌────────────┐                  │
│              │  Router  │  │  Registry  │                  │
│              └──────────┘  └────────────┘                  │
├─────────────────────────────────────────────────────────────┤
│                     OS Base                                 │
│  Debian 12 │ Linux 6.8.x │ Landlock │ seccomp │ eBPF      │
│  cgroups v2 │ PipeWire │ SDDM │ systemd │ uinput          │
└─────────────────────────────────────────────────────────────┘
```

## Service Ports

| Service | Port | Protocol |
|---------|------|----------|
| Model Gateway | 8100 | HTTP |
| Accessibility | 8200 | HTTP |
| Control Plane | 9000 | HTTP/WS |
| PostgreSQL | 5432 | TCP |
| Prometheus | 9090 | HTTP |
| Grafana | 3000 | HTTP |
| OTel Collector | 4317/4318 | gRPC/HTTP |
| Jaeger UI | 16686 | HTTP |

## Subsystem Map

| Directory | Phase | Status | Language |
|-----------|-------|--------|----------|
| `kernel/` | 8 | ✅ Scaffold | C, Kconfig |
| `distro/` | 8 | ✅ Scaffold | Shell, YAML |
| `shell/` | 6 | ✅ Scaffold | QML, JS, Shell |
| `control-plane/` | 2 | ✅ Implemented | Python |
| `agents/` | 5 | ✅ Implemented | Python |
| `model-gateway/` | 1 | ✅ Implemented | Python |
| `runtime/` | 3 | ✅ Implemented | Python |
| `accessibility/` | 4 | ✅ Implemented | Python |
| `observability/` | 7 | ✅ Scaffold | YAML, C |
| `docs/` | 9 | ✅ Written | Markdown |
