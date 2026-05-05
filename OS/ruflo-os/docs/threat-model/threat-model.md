# Ruflo OS — Threat Model

## Trust Boundaries

```
┌─────────────────────────────────────────────────────────┐
│  TRUSTED ZONE (User-approved, auditable)                │
│  ┌────────────────┐  ┌────────────────┐                │
│  │ Control Plane  │  │ Model Gateway  │                │
│  │ (policy eval)  │  │ (inference)    │                │
│  └────────────────┘  └────────────────┘                │
│  ┌────────────────┐  ┌────────────────┐                │
│  │ Approval Broker│  │  Audit Chain   │                │
│  └────────────────┘  └────────────────┘                │
├─────────────────────────────────────────────────────────┤
│  SEMI-TRUSTED ZONE (Sandboxed, broker-mediated)         │
│  ┌────────────────┐  ┌────────────────┐                │
│  │ Agent Workers  │  │ GUI Operator   │                │
│  │ (non-root)     │  │ (display only) │                │
│  └────────────────┘  └────────────────┘                │
├─────────────────────────────────────────────────────────┤
│  UNTRUSTED ZONE                                         │
│  ┌────────────────┐  ┌────────────────┐                │
│  │ Model Outputs  │  │ User Prompts   │                │
│  │ (LLM text)     │  │ (may inject)   │                │
│  └────────────────┘  └────────────────┘                │
└─────────────────────────────────────────────────────────┘
```

## Threat Categories

### T1: Prompt Injection
- **Risk**: Attacker embeds instructions in user content or file contents
- **Mitigation**: System prompts are separated from user content; policy evaluator gates all actions regardless of prompt content; no action is auto-approved based on model output alone

### T2: Agent Privilege Escalation
- **Risk**: Agent attempts to access files, secrets, or network beyond its scope
- **Mitigation**: All access through brokers; opaque handles; deny-by-default policy; Landlock filesystem restrictions; seccomp syscall filtering

### T3: Secret Exfiltration
- **Risk**: Agent extracts API keys, passwords, or tokens
- **Mitigation**: Agents NEVER see raw secrets; SecretBroker issues scoped handles; actions are performed by the broker on behalf of the agent; network broker blocks unauthorized endpoints

### T4: Unauthorized Financial Actions
- **Risk**: Agent makes purchases or financial transactions
- **Mitigation**: PolicyEvaluator unconditionally DENIES `browser_purchase` and `submit_payment`; no override mechanism

### T5: Data Loss
- **Risk**: Agent deletes or overwrites important files
- **Mitigation**: Destructive operations require explicit user approval via ApprovalBroker; all file operations logged in audit chain; timeout-based auto-rejection

### T6: Supply Chain / Dependency
- **Risk**: Compromised model weights or poisoned packages
- **Mitigation**: Model registry tracks source URLs (HuggingFace/GitHub); package installation requires approval; pre-commit hooks with Bandit security scanning

### T7: Network Exfiltration
- **Risk**: Agent sends data to attacker-controlled servers
- **Mitigation**: NetworkBroker enforces allow-lists; cloud metadata endpoints always blocked; connection logging for forensics

### T8: Audit Tampering
- **Risk**: Attacker modifies audit logs to hide actions
- **Mitigation**: Hash-chained append-only log; chain verification detects any modification; logs stored with restricted write permissions

## Security Controls Summary

| Control | Layer | Implementation |
|---------|-------|----------------|
| Deny-by-default policy | Control Plane | `PolicyEvaluator` with regex rules |
| Approval gates | Control Plane | `ApprovalBroker` with async user consent |
| Opaque file handles | Runtime | `FileBroker` — agents never see real paths |
| Scoped secret handles | Runtime | `SecretBroker` — agents never see raw values |
| Network allow-lists | Runtime | `NetworkBroker` with pattern matching |
| Hash-chained audit | Control Plane | `AuditService` with SHA-256 chain |
| Non-root sandboxes | Runtime | `SandboxManager` with policy templates |
| Landlock filesystem | Kernel | `CONFIG_SECURITY_LANDLOCK=y` |
| seccomp-bpf | Kernel | `CONFIG_SECCOMP_FILTER=y` |
| eBPF monitoring | Kernel/Observability | Syscall tracing probes |
