# Ruflo OS — Integration Status

## External Dependencies Status

| Component | Status | Notes |
|-----------|--------|-------|
| **NemoClaw** | 🟡 Mock Adapter | NemoClaw SDK not publicly available. Using `LocalNemoClawBridge` which routes through the model gateway. Swap adapter when SDK is released. |
| **OpenShell** | 🟡 Abstracted | OpenShell is abstracted behind the `SandboxManager`. Current impl uses process-level isolation. Full container isolation requires Linux deployment. |
| **Hermes** | 🟡 Mock Adapter | Hermes agent SDK not available. Using `HermesMemoryAdapter` with in-memory 3-layer storage. Replace with SDK when available. |
| **Ruflo Swarm** | 🟡 Mock Adapter | Ruflo swarm orchestration SDK not available. Using `RufloAdapter` with template-based decomposition. Replace with SDK when available. |
| **Ollama** | 🟢 Production | Full provider adapter implemented. Requires Ollama running locally. |
| **vLLM** | 🟢 Production | Full provider adapter using OpenAI-compatible API. |
| **SGLang** | 🟢 Production | Full provider adapter using OpenAI-compatible API. |
| **Anthropic** | 🟢 Production | Full provider adapter using Messages API. |
| **OpenAI** | 🟢 Production | Full provider adapter using Chat Completions API. |
| **Gemini** | 🟢 Production | Full provider adapter using Generative Language API. |
| **AT-SPI2** | 🟢 Production | Requires `python3-pyatspi` on Linux. Gracefully unavailable on other platforms. |
| **ydotool** | 🟢 Production | Requires `ydotool` + `ydotoold` on Linux. Gracefully unavailable otherwise. |
| **xdotool** | 🟢 Production | Requires `xdotool` on Linux with X11/XWayland. Gracefully unavailable otherwise. |

## Integration Swap Guide

When NemoClaw, OpenShell, Hermes, or Ruflo SDKs become available:

1. Install the SDK package
2. Create a new adapter class implementing the same interface (e.g., `RealNemoClawBridge(NemoClawBridge)`)
3. Update the factory/initialization code to use the real adapter
4. Run the existing test suite — all tests should pass with the new adapter
5. Add integration tests specific to the real SDK

The abstraction interfaces are designed to be stable. No changes should be needed to the control plane, agents, or accessibility layers when swapping adapters.
