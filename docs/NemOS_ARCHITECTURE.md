# NemOS System Architecture Document

## Executive Summary

NemOS is a production-grade, AI-native Linux desktop platform. It provides a local-first, secure environment where users issue high-level goals in natural language, and the system autonomously executes them across the desktop using local AI models, with cloud fallback when explicitly permitted.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                        User Layer                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │ Task Intake  │  │ Spotlight   │  │ Settings    │ │
│  └──────────────┘  └──────────────┘  └──────────────┘ │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼ (natural language goals)
┌─────────────────────────────────────────────────────────────┐
│                     Desktop Shell Layer                    │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │   Dock      │  │  Menu Bar   │  │ Notifications│ │
│  └──────────────┘  └──────────────┘  └──────────────┘ │
│  ┌─────────────────────────────────────────────┐  │
│  │         Wayland Compositor (wlroots)          │  │
│  └─────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼ (screen capture, input injection)
┌─────────────────────────────────────────────────────────────┐
│                    Agent Execution Layer                  │
│  ┌─────────────────────────────────────────────┐  │
│  │         Conductor Agent (Ruflo-style)           │  │
│  │  - Decomposes goals into task DAGs            │  │
│  │  - Manages multi-agent coordination          │  │
│  └─────────────────────────────────────────────┘  │
│           │              │              │                    │
│    ┌──────▼────┐ ┌──▼─────┐ ┌────▼─────┐              │
│    │ Desktop    │ │Browser  │ │Shell/    │              │
│    │ Operator  │ │Agent   │ │System    │              │
│    └──────────┘ └────────┘ │Agent    │              │
│                           └─────────┘              │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼ (tool calls)
┌─────────────────────────────────────────────────────────────┐
│                       AI Core Layer                     │
│  ┌─────────────────────────────────────────────┐  │
│  │         Model Gateway (NemoClaw-inspired)      │  │
│  │  - Local inference (vLLM/Ollama)           │  │
│  │  - Cloud fallback (OpenAI/NVIDIA)          │  │
│  │  - Policy-aware routing                  │  │
│  └─────────────────────────────────────────────┘  │
│  ┌─────────────────────────────────────────────┐  │
│  │         Policy Engine                      │  │
│  │  - Sandbox management (Landlock/seccomp)    │  │
│  │  - Action approval workflows             │  │
│  └─────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼ (Linux system calls)
┌─────────────────────────────────────────────────────────────┐
│                       Base OS Layer                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │  Linux      │  │  systemd   │  │  Packaging  │ │
│  │  Kernel     │  │  Services  │  │  & Updates  │ │
│  └──────────────┘  └──────────────┘  └──────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

## Layer Details

### Layer A — Base OS
- **Kernel:** Upstream Linux LTS (6.8.x+)
- **Init:** systemd
- **Package Management:** apt/dpkg with Flatpak support
- **Updates:** OSTree for atomic, rollback-capable updates
- **Hardware:** x86_64 and ARM64 support

**Key Decision:** NO custom kernel fork. Only minimal, out-of-tree modules when absolutely necessary (input injection, eBPF hooks).

### Layer B — Desktop Environment
- **Display Server:** Wayland-first (wlroots-based compositor)
- **X11 Support:** XWayland for legacy apps
- **Toolkit:** GTK4 for native apps, Qt6 as secondary
- **Accessibility:** AT-SPI2 integration for screen reading
- **UI Quality Target:** macOS-inspired (not clone), premium feel

**Key Decision:** Avoid Electron for core system components. Use native toolkits.

### Layer C — AI Core (NemoClaw-inspired)
- **Model Gateway:**
  - Local: vLLM, llama.cpp, Ollama
  - Cloud: OpenAI-compatible APIs, NVIDIA Nemotron
  - Unified routing with policy checks

- **Policy Engine:**
  - Sandboxing: Landlock (filesystem), seccomp (syscalls), namespaces (isolation)
  - Approval workflows for destructive actions
  - Network egress whitelists

- **Model Registry:**
  - HuggingFace integration
  - GitHub release asset support
  - GGUF/safetensors/pytorch formats
  - Checksum validation + provenance tracking

**Key Decision:** Keep AI logic in user-space. Kernel only for observability/sandboxing.

### Layer D — Orchestration (Ruflo-inspired)
- **Workflow Engine:** DAG-based task execution
- **Message Bus:** NATS or Redis Streams for agent communication
- **Agent Runtime:** ReAct loop (Reason + Act)
  - Perceive (screen capture + OCR + accessibility)
  - Think (LLM inference via Gateway)
  - Act (tool execution)
  - Observe (verify outcome)

- **Memory System:**
  - Short-term: in-memory deque
  - Long-term: ChromaDB (vector store)
  - Episodic: task summaries
  - Semantic: learned facts

**Key Decision:** Use Rust or Go for high-reliability backend services. Python for agent logic.

### Layer E — Adaptive Agent (Hermes-inspired)
- **Skill System:**
  - Dynamic skill creation from successful tasks
  - Skill marketplace (signed manifests)
  - YAML-based skill definitions

- **Learning:**
  - User preference memory
  - Correction handling
  - Reflection/self-critique loop

**Key Decision:** Skills run in sandboxed environments with policy checks.

### Layer F — Action Layer
- **GUI Automation:**
  - Wayland: Privileged compositor plugin OR AT-SPI fallback
  - X11: xdotool/XTest
  - Vision: screen understanding via LLaVA/Qwen-VL

- **Browser Automation:** Playwright (primary), DOM fallback
- **Shell/System:** subprocess with seccomp filters
- **OCR:** Tesseract + EasyOCR pipeline

**Key Decision:** Accessibility APIs first, synthetic input last, vision-only when others fail.

## Data Flow Example

**User Goal:** "Research the latest AI news and summarize top 5 articles"

```
1. User types goal in TaskIntakeApp
   ↓
2. Conductor Agent receives goal
   ↓
3. TaskPlanner decomposes:
   - Step 1: Open Firefox
   - Step 2: Navigate to news site
   - Step 3: Extract article links
   - Step 4: Read top 5 articles
   - Step 5: Summarize with local LLM
   - Step 6: Save summary to ~/Documents
   ↓
4. Desktop Operator Agent executes:
   - Uses Playwright to open Firefox
   - Uses GUI automation to click/navigate
   - Uses OCR + vision to understand screen
   ↓
5. Research Agent gathers sources
   ↓
6. Model Gateway routes inference:
   - Vision tasks → LLaVA (local)
   - Summarization → Hermes 3 (local Q4)
   - Fallback → NVIDIA Nemotron (cloud)
   ↓
7. Memory Agent stores:
   - Summary in episodic memory
   - Learned: "User likes AI news"
   ↓
8. User receives notification with summary
   ↓
9. Audit log entry created (JSONL + SQLite)
```

## Security Architecture

### Defense in Depth
1. **Kernel Level:**
   - eBPF for syscall observability (not blocking)
   - Optional: Input mediation module (out-of-tree)

2. **Sandbox Level:**
   - Landlock: filesystem access restriction
   - seccomp: syscall filtering
   - Namespaces: PID, network, mount isolation
   - cgroups: resource limits

3. **Policy Level:**
   - Action allowlist/denylist
   - User approval for risky actions
   - Network egress whitelists

4. **Model Level:**
   - Provenance validation (checksums)
   - Signed model manifests
   - Local-first (privacy)

5. **User Level:**
   - Approval center for pending actions
   - Autonomy level configuration
   - Audit log review

## Technology Stack Summary

| Component | Technology | Justification |
|------------|-------------|---------------|
| Kernel | Upstream Linux 6.8 LTS | Stability, hardware support |
| Compositor | wlroots (C/Rust) | Modern Wayland ecosystem |
| UI Toolkit | GTK4 | Native Linux, accessible |
| AI Gateway | Python (FastAPI) | Rapid development, ML ecosystem |
| Agent Runtime | Python (asyncio) | LLM integration, orchestration |
| Message Bus | NATS or Redis | Reliable agent communication |
| Vector Store | ChromaDB | Local, embeddable |
| Browser Auto | Playwright | Modern, reliable |
| OCR | Tesseract + EasyOCR | Complementary strengths |
| Package | Flatpak + apt | Standard Linux |
| Updates | OSTree | Atomic, rollback-capable |
| Observability | OpenTelemetry + Prometheus | Industry standard |

## Production Milestones

### Phase 0 (Month 0-1): Discovery
- ✅ Feasibility assessment
- ✅ Architecture document
- ✅ Threat model
- ✅ Monorepo bootstrap

### Phase 1 (Month 1-3): MVP Vertical Slice
- Basic desktop shell with Wayland
- Single-agent runtime with ReAct loop
- Local model inference (Ollama/vLLM)
- One working demo: "Open browser, search, summarize"

### Phase 2 (Month 3-6): Alpha
- Multi-agent coordination (2-3 agent types)
- Working Wayland automation (via accessibility)
- Cloud model fallback
- Model registry with HuggingFace pulls
- Installer + ISO generation

### Phase 3 (Month 6-12): Beta
- Full multi-agent swarm
- RAG-enabled memory
- Skill system with marketplace
- Advanced policy engine
- Comprehensive test suite

### Phase 4 (Month 12-24): Production
- Enterprise security hardening
- NemoClaw-style distributed inference
- Hermes-style adaptive behavior
- Plugin ecosystem
- 24/7 production support

## Next Steps

1. **Generate monorepo structure** (Section 12 format)
2. **Bootstrap development environment** (scripts/setup-dev.sh)
3. **Implement first vertical slice** (working demo)
4. **Create ADRs** for key architectural decisions
5. **Set up CI/CD** with automated testing

## Key Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Wayland automation too limited | High | Fallback to X11, use accessibility APIs |
| Kernel patches rejected upstream | Medium | Keep out-of-tree, minimize scope |
| Model inference too slow on consumer HW | High | Smaller default models, cloud fallback |
| Security vulnerabilities in AI tools | Critical | Defense in depth, constant audits |
| Team scaling challenges | Medium | Monorepo, clear APIs, phase-based delivery |
