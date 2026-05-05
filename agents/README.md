# Agents

Multi-agent orchestration layer for Ruflo OS.

## Architecture

```
RufloAdapter (swarm coordinator)
  ├── GuiOperatorAgent → accessibility service
  ├── BrowserAgent     → Playwright / GUI fallback
  ├── CodingAgent      → model gateway (coding models)
  ├── FileAgent        → runtime file broker
  └── VerifierAgent    → state verification

HermesMemoryAdapter (3-layer memory)
  ├── Episodic   → task traces
  ├── Semantic   → extracted facts
  └── Procedural → learned skills
```

## Quick Start

```bash
pip install -e ".[dev]"
pytest tests/ -v
```
