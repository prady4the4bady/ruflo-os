# Ruflo OS Architecture

## Overview
Ruflo OS is a production-grade AI-native Linux distribution where an AI agent (Ruflo) can take over the computer to execute natural language tasks.

## Architecture Layers

### Layer 1: Kernel (prady4the4bady/linux fork)
- Custom AI_BRIDGE kernel module for userspace-kernel IPC
- Ruflo Input virtual input driver
- eBPF hooks for AI-controlled syscall monitoring
- Custom `ruflo_defconfig` kernel configuration

### Layer 2: NemoClaw (AI Architecture Layer)
- **Inference Router**: Routes to local/cloud models based on task requirements
- **Model Manager**: HuggingFace/GitHub model loader with quantization
- **Sandbox Manager**: OpenShell-based per-task isolation
- **Policy Engine**: Security policy enforcement
- **Nemoclaw Daemon**: Main system daemon (PID-tracked)

### Layer 3: Ruflo Agent (Autonomous Task Execution)
- **Agent Runtime**: ReAct (Reason + Act) loop
- **Task Planner**: Breaks user intent into executable steps
- **Tool Executor**: Computer control (screen, cursor, keyboard, browser)
- **Memory Manager**: ChromaDB-backed short/long-term memory
- **RAG Engine**: Retrieval-Augmented Generation for context
- **Swarm Coordinator**: Multi-agent parallel execution

### Layer 4: Hermes Agent (Growing Intelligence)
- Skill system with dynamic creation
- Model switching via `/model` command
- Audit logging (JSONL + SQLite)
- AgentNet identity integration (Ed25519 keys)

### Layer 5: Ruflo Shell (macOS-inspired Desktop)
- wlroots-based Wayland compositor
- macOS-style UI: Dock, Menu Bar, Spotlight, Notifications
- Mission Control (Exposé) and Spaces (virtual desktops)
- Smooth window animations (scale+fade)
- Frosted glass vibrancy effects

### Layer 6: User Intent Interface
- TaskIntakeApp: Natural language task input
- AgentMonitor: Live task execution view
- ModelManager: Pull/manage AI models

## Data Flow
```
User Task → TaskIntakeApp → Ruflo Agent → ReAct Loop
→ Perception (Screen OCR + Accessibility Tree)
→ Reasoning (LLM via Inference Router)
→ Action (Computer Control Tools)
→ Observation (New Screen State)
→ Repeat until task complete
```

## Security Model
- Zero-trust: Every task runs in isolated sandbox
- Kernel-level input injection requires CAP_INPUT_INJECT
- All inter-process communication via Unix domain sockets
- Full audit trail (JSONL + SQLite)
- User approval required for sensitive operations