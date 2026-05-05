# Runtime

Secure sandbox runtime, NemoClaw bridge, and resource brokers for Ruflo OS.

## Components

| Module | Purpose |
|--------|---------|
| `sandbox/manager.py` | Sandbox lifecycle (create, execute, pause, destroy) |
| `sandbox/policy.py` | Policy templates: default, restricted, coding, browser, offline |
| `brokers/file_broker.py` | Opaque-handle file access — agents never see real paths |
| `brokers/secret_broker.py` | Scoped secret handles — agents never see raw credentials |
| `brokers/network_broker.py` | Allow-list network enforcement |
| `nemoclaw/bridge.py` | NemoClaw integration bridge (mock adapter until SDK available) |
| `events.py` | Structured event types for all runtime operations |

## Security Model

- **Deny-by-default**: All access goes through brokers with explicit allow-lists
- **Non-root workers**: Sandbox processes run as `ruflo-worker` user
- **Opaque handles**: Agents receive handle IDs, never raw paths or secrets
- **Use limits**: Secret handles have max-use counts and revocation
- **Policy templates**: Predefined security profiles per task type

## Quick Start

```bash
pip install -e ".[dev]"
pytest tests/ -v
```
