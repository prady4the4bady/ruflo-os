# Ruflo OS — Architecture Decision Records

## ADR-001: Debian Bookworm as Base Distribution

**Status**: Accepted  
**Date**: 2026-05-02

**Context**: Need a stable, well-supported base for an AI-native desktop OS.

**Decision**: Use Debian 12 (Bookworm) as the base distribution.

**Rationale**: Debian offers the best stability/freshness balance for a production OS. Bookworm ships Linux 6.1+ with backport support for 6.8.x, has native systemd integration, and the largest package ecosystem. Ubuntu was considered but rejected due to snap enforcement. Fedora was rejected due to faster release cycles requiring more maintenance.

---

## ADR-002: KDE Plasma 6 over GNOME

**Status**: Accepted

**Decision**: Use KDE Plasma 6 (Wayland) as the desktop environment.

**Rationale**: Plasma 6 provides better Wayland support, more customization flexibility (critical for macOS-like theming), QML-based widget system for AI Activity Center, and native global menu support. GNOME's opinionated design would require fighting the framework for our dock/launcher design.

---

## ADR-003: FastAPI for All Python Services

**Status**: Accepted

**Decision**: Use FastAPI for model gateway, control plane, and accessibility service.

**Rationale**: FastAPI provides async-first design, automatic OpenAPI docs, Pydantic validation, and excellent performance. Consistent framework across services reduces cognitive load and enables shared tooling.

---

## ADR-004: Broker-Mediated Resource Access

**Status**: Accepted

**Decision**: All agent access to files, secrets, and network goes through broker services.

**Rationale**: Direct resource access from agents is a critical security risk. Brokers provide: (1) opaque handles preventing path traversal, (2) audit logging, (3) revocation, (4) policy enforcement, (5) use limits for secrets. This is the single most important security architecture decision.

---

## ADR-005: 4-Tier GUI Automation Fallback

**Status**: Accepted

**Decision**: GUI automation uses AT-SPI → ydotool → xdotool → VLM grounding.

**Rationale**: No single GUI automation method works in all scenarios. AT-SPI is most reliable for accessible apps but not all apps expose it. ydotool works on Wayland but requires uinput. xdotool only works on X11. VLM grounding is universal but slow and less precise. Tiered fallback maximizes coverage.

---

## ADR-006: Hash-Chained Audit Logs

**Status**: Accepted

**Decision**: All agent actions are recorded in hash-chained, append-only logs.

**Rationale**: Tamper-evident audit trails are essential for trust in AI-operated systems. Hash chaining means any modification to historical entries is detectable. This provides forensic capability for investigating unexpected agent behavior.
