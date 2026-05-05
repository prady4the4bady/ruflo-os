"""Sandbox policy templates — filesystem, network, process, and inference constraints."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SandboxPolicy:
    """Security policy for a sandbox worker.

    Defines what the sandboxed process can access across four domains:
    filesystem, network, process, and inference.
    """

    name: str = "default"

    # Filesystem policy
    fs_read_paths: list[str] = field(default_factory=lambda: ["/tmp/ruflo-sandbox-*"])
    fs_write_paths: list[str] = field(default_factory=lambda: ["/tmp/ruflo-sandbox-*"])
    fs_deny_paths: list[str] = field(
        default_factory=lambda: [
            "/etc/shadow", "/etc/passwd", "/root",
            "/home/*/.*ssh*", "/home/*/.*gnupg*",
            "/var/run/docker.sock",
        ]
    )

    # Network policy
    network_allowed: bool = False
    network_allow_hosts: list[str] = field(default_factory=list)
    network_deny_hosts: list[str] = field(default_factory=lambda: ["169.254.169.254"])
    network_allow_ports: list[int] = field(default_factory=lambda: [80, 443])
    network_max_connections: int = 10

    # Process policy
    process_max_pids: int = 64
    process_max_memory_mb: int = 2048
    process_max_cpu_percent: float = 80.0
    process_allow_sudo: bool = False
    process_allow_ptrace: bool = False

    # Inference policy
    inference_allowed: bool = True
    inference_max_tokens_per_call: int = 8192
    inference_max_calls_per_minute: int = 60
    inference_allowed_models: list[str] = field(default_factory=lambda: ["*"])

    # Execution timeout
    timeout_seconds: int = 300


class PolicyTemplate:
    """Factory for predefined sandbox policy templates."""

    _templates: dict[str, SandboxPolicy] = {}

    @classmethod
    def _init_templates(cls) -> None:
        if cls._templates:
            return

        cls._templates["default"] = SandboxPolicy(
            name="default",
            network_allowed=True,
            network_allow_hosts=["*"],
        )

        cls._templates["restricted"] = SandboxPolicy(
            name="restricted",
            fs_write_paths=["/tmp/ruflo-sandbox-*"],
            network_allowed=False,
            process_max_pids=16,
            process_max_memory_mb=512,
            inference_max_tokens_per_call=4096,
            timeout_seconds=120,
        )

        cls._templates["network_only"] = SandboxPolicy(
            name="network_only",
            network_allowed=True,
            network_allow_hosts=["*"],
            fs_write_paths=[],
            process_allow_sudo=False,
        )

        cls._templates["offline"] = SandboxPolicy(
            name="offline",
            network_allowed=False,
            inference_allowed=False,
            process_max_memory_mb=1024,
            timeout_seconds=60,
        )

        cls._templates["coding"] = SandboxPolicy(
            name="coding",
            network_allowed=True,
            network_allow_hosts=["github.com", "pypi.org", "npmjs.com", "crates.io"],
            network_allow_ports=[80, 443, 22],
            process_max_memory_mb=4096,
            process_max_pids=128,
            inference_max_tokens_per_call=16384,
            timeout_seconds=600,
        )

        cls._templates["browser"] = SandboxPolicy(
            name="browser",
            network_allowed=True,
            network_allow_hosts=["*"],
            fs_write_paths=["/tmp/ruflo-sandbox-*", "/tmp/ruflo-downloads-*"],
            process_max_memory_mb=4096,
            timeout_seconds=300,
        )

    @classmethod
    def get(cls, name: str) -> SandboxPolicy:
        """Get a policy template by name."""
        cls._init_templates()
        if name not in cls._templates:
            raise ValueError(
                f"Unknown policy template: {name}. "
                f"Available: {list(cls._templates.keys())}"
            )
        # Return a copy to avoid mutation of templates
        template = cls._templates[name]
        return SandboxPolicy(
            name=template.name,
            fs_read_paths=list(template.fs_read_paths),
            fs_write_paths=list(template.fs_write_paths),
            fs_deny_paths=list(template.fs_deny_paths),
            network_allowed=template.network_allowed,
            network_allow_hosts=list(template.network_allow_hosts),
            network_deny_hosts=list(template.network_deny_hosts),
            network_allow_ports=list(template.network_allow_ports),
            network_max_connections=template.network_max_connections,
            process_max_pids=template.process_max_pids,
            process_max_memory_mb=template.process_max_memory_mb,
            process_max_cpu_percent=template.process_max_cpu_percent,
            process_allow_sudo=template.process_allow_sudo,
            process_allow_ptrace=template.process_allow_ptrace,
            inference_allowed=template.inference_allowed,
            inference_max_tokens_per_call=template.inference_max_tokens_per_call,
            inference_max_calls_per_minute=template.inference_max_calls_per_minute,
            inference_allowed_models=list(template.inference_allowed_models),
            timeout_seconds=template.timeout_seconds,
        )

    @classmethod
    def list_templates(cls) -> list[str]:
        cls._init_templates()
        return list(cls._templates.keys())
