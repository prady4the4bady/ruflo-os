# Control Plane

Task orchestration, policy enforcement, and audit service for Ruflo OS.

## Features

- **Task Lifecycle**: Create, get, approve, cancel, replay tasks
- **WebSocket Streaming**: Real-time task event broadcasting
- **Orchestrator Engine**: Task decomposition, dependency tracking, retries
- **Budget Manager**: Token and cost budget enforcement
- **Approval Broker**: Async approval workflows with timeout
- **Policy Evaluator**: Deny-by-default action gating with configurable rules
- **Audit Service**: Append-only hash-chained tamper-evident logs

## API

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/tasks` | Create task |
| GET | `/api/v1/tasks` | List tasks |
| GET | `/api/v1/tasks/{id}` | Get task |
| POST | `/api/v1/tasks/{id}/approve` | Approve/reject task |
| POST | `/api/v1/tasks/{id}/cancel` | Cancel task |
| POST | `/api/v1/tasks/{id}/replay` | Replay task |
| WS | `/ws/events` | Real-time event stream |

## Quick Start

```bash
pip install -e ".[dev]"
docker compose up -d postgres
uvicorn ruflo_control_plane.main:app --reload --port 9000
pytest tests/ -v
```

## Security

All actions pass through the PolicyEvaluator before execution. The default policy is **deny-all** with explicit allows for safe operations.
