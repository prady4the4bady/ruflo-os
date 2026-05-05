# NemOS Monorepo Structure#

## Directory Tree#

```
nemos-os/
├── docs/
│   ├── product-requirements.md
│   ├── system-architecture.md
│   ├── threat-model.md
│   ├── deployment-architecture.md
│   ├── model-onboarding-spec.md
│   ├── automation-safety-spec.md
│   ├── wayland-automation-strategy.md
│   ├── x11-compatibility-spec.md
│   ├── ui-ux-guidelines.md
│   ├── observability-spec.md
│   ├── release-engineering.md
│   └── ADRs/                    # Architecture Decision Records
│       ├── 0001-record-architecture-decisions.md
│       ├── 0002-use-wlroots-not-mutter.md
│       ├── 0003-local-inference-first.md
│       ├── 0004-sandbox-with-landlock.md
│       └── 0005-openai-compatible-gateway.md
│
├── platform/
│   ├── desktop-shell/           # Wayland compositor (wlroots-based)
│   │   ├── src/
│   │   ├── protocols/
│   │   ├── meson.build
│   │   └── README.md
│   ├── session-services/        # systemd services, session management
│   │   ├── nemos-shell.service
│   │   ├── nemos-agent.service
│   │   └── nemos-gateway.service
│   ├── settings-app/           # GTK4 settings application
│   ├── launcher/               # Spotlight-like launcher
│   ├── dock/                   # macOS-inspired dock
│   └── notification-center/     # Desktop notifications
│
├── ai-core/
│   ├── model-gateway/          # FastAPI + vLLM/Ollama backend
│   │   ├── src/
│   │   ├── Dockerfile
│   │   └── README.md
│   ├── model-registry/         # HuggingFace/GitHub model management
│   ├── runtime-manager/        # Ollama/vLLM process management
│   ├── policy-engine/          # NemoClaw-inspired security layer
│   ├── context-broker/         # Prompt/context isolation
│   └── memory-service/         # ChromaDB + episodic memory
│
├── orchestration/
│   ├── workflow-engine/         # Ruflo-inspired DAG execution
│   │   ├── src/
│   │   └── README.md
│   ├── agent-runtime/          # ReAct loop implementation
│   ├── task-queue/             # NATS/Redis task distribution
│   ├── artifact-store/          # S3-compatible object storage
│   └── rag-connectors/         # Vector store integrations
│
├── agents/
│   ├── conductor/             # Task planning + delegation
│   ├── desktop-operator/       # GUI automation agent
│   ├── browser-agent/          # Playwright-based web agent
│   ├── system-agent/           # Shell/file operations agent
│   ├── research-agent/         # Information gathering agent
│   ├── coding-agent/           # Code editing + testing agent
│   ├── memory-agent/           # User preference learning
│   ├── safety-agent/           # Policy enforcement agent
│   └── reflection-agent/       # Self-critique agent
│
├── automation/
│   ├── screen-observer/        # Screen capture + OCR
│   │   ├── src/
│   │   └── README.md
│   ├── ocr-service/             # Tesseract + EasyOCR pipeline
│   ├── vision-service/          # LLaVA/Qwen-VL integration
│   ├── input-controller/       # ydotool/ Wayland injection
│   ├── playwright-runner/       # Browser automation wrapper
│   ├── shell-runner/           # seccomp-sandboxed shell
│   └── file-ops/               # Sandboxed file operations
│
├── security/
│   ├── sandbox-runner/         # Landlock + seccomp wrapper
│   ├── policy-daemon/          # Central policy enforcement
│   ├── audit-log/              # JSONL + SQLite audit trail
│   ├── signature-verifier/      # Model/plugin signature checks
│   ├── model-provenance/        # Checksum + provenance tracking
│   └── ebpf-observability/     # eBPF-based monitoring
│
├── infra/
│   ├── compose/                # Docker Compose files
│   ├── k8s-optional/           # Kubernetes manifests (optional)
│   ├── otel/                    # OpenTelemetry configs
│   ├── prometheus/              # Metrics collection
│   ├── grafana/                 # Dashboards
│   └── ci/                      # GitHub Actions workflows
│
├── scripts/
│   ├── bootstrap.sh            # Initial system setup
│   ├── dev-up.sh               # Development environment
│   ├── test-all.sh             # Run all tests
│   ├── package.sh              # Build packages
│   └── release.sh             # Release engineering
│
├── tests/
│   ├── unit/                   # Unit tests per component
│   ├── integration/            # Service integration tests
│   ├── e2e/                    # End-to-end desktop tests
│   ├── desktop/                 # Desktop automation tests
│   └── security/                # Penetration + fuzzing
│
├── .github/
│   ├── workflows/              # CI/CD pipeline
│   └── ISSUE_TEMPLATE/          # Bug reports + feature requests
│
├── .editorconfig
├── .gitignore
├── Cargo.toml                  # Rust workspace (if using Rust)
├── pyproject.toml              # Python workspace
├── package.json                # Node.js workspace (if using TypeScript)
├── Makefile
└── README.md
```

## Key Design Decisions#

| ADR | Title | Status |
|-----|-------|--------|
| 0001 | Record Architecture Decisions | ✅ Complete |
| 0002 | Use wlroots not Mutter | ✅ Complete |
| 0003 | Local Inference First | ✅ Complete |
| 0004 | Sandbox with Landlock | ✅ Complete |
| 0005 | OpenAI-Compatible Gateway | ✅ Complete |
| 0006 | GTK4 over Qt6 for Desktop | 🔄 Pending |
| 0007 | NATS over Redis for Message Bus | 🔄 Pending |
| 0008 | Ollama over vLLM for Local | ✅ Complete |
| 0009 | Playwright over Selenium | ✅ Complete |
| 0010 | Tesseract + EasyOCR Pipeline | ✅ Complete |

## Tech Stack Justification#

### Why wlroots over Mutter?#
- **wlroots:** Modern, minimal, Wayland-first#
- **Mutter:** GNOME Shell dependency, heavy#
- **Decision:** wlroots for custom compositor control#

### Why Local Inference First?#
- **Privacy:** User data never leaves device by default#
- **Cost:** No per-token cloud costs#
- **Latency:** Local models have lower latency for simple tasks#
- **Fallback:** Cloud only when explicitly enabled#

### Why Landlock + seccomp?#
- **Landlock:** Filesystem sandboxing (Linux 5.13+)#
- **seccomp:** Syscall filtering#
- **Alternative:** Docker containers (too heavy for per-task)#
- **Decision:** Use kernel-native sandboxing#

## Next Steps#

1. **Phase 0 Complete:** ✅ Feasibility + Architecture + Threat Model#
2. **Phase 1 (3 months):** Build vertical slice (see next section)#
3. **Phase 2 (6 months):** Alpha release with 3 agent types#
4. **Phase 3 (12 months):** Beta with skill system#
5. **Phase 4 (24 months):** Production enterprise release#

## First 30-Day Build Plan#

| Day | Task | Owner |
|-----|------|-------|
| 1-3 | Bootstrap monorepo, CI/CD | DevOps |
| 4-7 | Desktop shell skeleton (wlroots) | Desktop Eng |
| 8-12 | Model gateway (FastAPI + Ollama) | AI Eng |
| 13-18 | Single-agent runtime (ReAct loop) | Agent Eng |
| 19-23 | Screen capture + OCR pipeline | Automation Eng |
| 24-27 | Policy engine (Landlock + seccomp) | Security Eng |
| 28-30 | Demo: "Open browser, search, summarize" | Full Team |

## First Vertical Slice Demo#

**Goal:** "Open Firefox, search for 'AI news', summarize top 3 articles, save to ~/Documents/"

**Success Criteria:**
- ✅ Agent can see screen (screenshot + OCR)#
- ✅ Agent can move mouse + type (ydotool/X11)#
- ✅ Agent can open Firefox (desktop launcher)#
- ✅ Agent can use Playwright as fallback#
- ✅ Agent can summarize with local LLM (Phi-3.5 or Hermes 3)#
- ✅ Agent saves result to file#
- ✅ User sees approval prompt for file write#

**NOT Pass Criteria:**
- ❌ Multi-agent coordination (later)#
- ❌ Skill acquisition (later)#
- ❌ Cloud model fallback (later)#
- ❌ Enterprise security hardening (later)#
