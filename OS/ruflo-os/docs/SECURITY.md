# Ruflo OS Security Architecture

## Zero-Trust Security Model

### 1. Sandbox Isolation
Every agent task runs in an isolated OpenShell sandbox:
- Landlock filesystem restrictions (default: `/sandbox`, `/tmp` only)
- seccomp syscall filtering via allowlist in `nemoclaw/security/syscall_allowlist.txt`
- Network namespace isolation with egress whitelist per task type
- Each task runs in its own sandbox instance

### 2. Kernel-Level Security
- Input injection requires elevated capability (`CAP_INPUT_INJECT`)
- All model inference routed through Nemoclaw gateway (never direct)
- eBPF programs verified by kernel verifier before loading
- Model weights verified via SHA256 checksums before loading

### 3. Audit & Transparency
- Full audit trail: every action logged to SQLite + JSONL (Hermes audit logger)
- User approval required for:
  - Network access to domains not in whitelist
  - File system access outside `/home/$USER` and `/tmp`
  - Running scripts with sudo/root
  - Sending emails or messages
  - Making purchases or form submissions

### 4. Input Control
- Screen lock feature: user can instantly reclaim control
- Panic button: `Cmd+Shift+Escape` immediately kills all agent processes
- All inter-process communication via Unix domain sockets (not TCP)
- Agent operates as non-root user `ruflo`

### 5. Network Security
- eBPF XDP program for network policy enforcement
- Egress whitelist in `nemoclaw/security/network_policy.yaml`
- All external API calls routed through Nemoclaw gateway
- No direct inbound connections to agent services

### 6. Model Security
- Only verified models from HuggingFace/GitHub/NVIDIA loaded
- Local model storage in `/opt/ruflo/models` with restricted permissions
- Cloud API keys stored in environment variables, never committed
- Model switching via Hermes `/model` command preserves state