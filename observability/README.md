# Observability

Monitoring, tracing, session replay, and eBPF observability for Ruflo OS.

## Structure

```
observability/
├── metrics/         # Prometheus exporters for each service
├── dashboards/      # Grafana JSON dashboard definitions
├── traces/          # OpenTelemetry collector and config
├── session-replay/  # Agent session recording and replay
├── ebpf-probes/     # eBPF probe scaffolding (C/BPF)
└── docker-compose.yml  # Local observability stack
```

## Stack

| Component | Purpose |
|-----------|---------|
| Prometheus | Metrics collection and alerting |
| Grafana | Dashboards and visualization |
| OpenTelemetry | Distributed tracing |
| Session Replay | Agent action recording and playback |
| eBPF Probes | Kernel-level syscall and network observability |

## Quick Start

```bash
docker compose up -d
# Grafana: http://localhost:3000
# Prometheus: http://localhost:9090
```
