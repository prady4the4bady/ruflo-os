import os
import sys
import time
import signal
import structlog
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field
import asyncio
import aiofiles

logger = structlog.get_logger(__name__)

class NemoclawConfig(BaseModel):
    inference_router: dict = Field(default_factory=dict)
    sandbox: dict = Field(default_factory=dict)
    model_cache_dir: str = "/opt/ruflo/models"
    socket_path: str = "/run/nemoclaw.sock"
    health_port: int = 8001
    kernel_device: str = "/dev/ai_bridge"

class NemoclawDaemon:
    """PID-tracked system daemon — the brain of the AI layer."""

    def __init__(self, config_path: str = "/app/nemoclaw.config.yaml"):
        self.config = self._load_config(config_path)
        self.inference_router = None
        self.model_manager = None
        self.sandbox_manager = None
        self.policy_engine = None
        self.kernel_fd: Optional[int] = None
        self.running = False
        self.health_status = "starting"
        self._setup_signal_handlers()

    def _load_config(self, config_path: str) -> NemoclawConfig:
        if os.path.exists(config_path):
            with open(config_path, "r") as f:
                import yaml
                data = yaml.safe_load(f)
                return NemoclawConfig(**data)
        logger.warning("Config not found, using defaults", path=config_path)
        return NemoclawConfig()

    def _setup_signal_handlers(self) -> None:
        signal.signal(signal.SIGTERM, self._handle_shutdown)
        signal.signal(signal.SIGINT, self._handle_shutdown)

    def _handle_shutdown(self, signum, frame) -> None:
        logger.info("Shutdown signal received", signal=signum)
        self.running = False

    async def initialize(self) -> None:
        """Initialize all components."""
        from .inference_router import InferenceRouter
        from .model_manager import ModelManager
        from .sandbox_manager import SandboxManager
        from .policy_engine import PolicyEngine

        logger.info("Initializing Nemoclaw Daemon")
        self.inference_router = InferenceRouter(self.config.kernel_device)
        self.model_manager = ModelManager(self.config.model_cache_dir)
        self.sandbox_manager = SandboxManager()
        self.policy_engine = PolicyEngine()

        # Open kernel bridge device
        try:
            self.kernel_fd = os.open(self.config.kernel_device, os.O_RDWR | os.O_NONBLOCK)
            logger.info("Opened kernel device", device=self.config.kernel_device)
        except OSError as e:
            logger.warning("Failed to open kernel device", error=str(e))
            self.kernel_fd = None

        # Create Unix domain socket
        await self._create_socket()
        self.health_status = "healthy"
        logger.info("Nemoclaw Daemon initialized")

    async def _create_socket(self) -> None:
        """Create Unix domain socket for agent IPC."""
        import socket
        import stat

        if os.path.exists(self.config.socket_path):
            os.unlink(self.config.socket_path)

        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.bind(self.config.socket_path)
        self.sock.listen(5)
        os.chmod(self.config.socket_path, stat.S_IRWXU | stat.S_IRWXG)
        logger.info("Unix socket created", path=self.config.socket_path)

    async def health_check(self) -> dict:
        """Health check endpoint."""
        return {
            "status": self.health_status,
            "components": {
                "inference_router": self.inference_router is not None,
                "model_manager": self.model_manager is not None,
                "sandbox_manager": self.sandbox_manager is not None,
                "policy_engine": self.policy_engine is not None,
                "kernel_device": self.kernel_fd is not None
            },
            "timestamp": time.time()
        }

    async def run(self) -> None:
        """Main daemon loop."""
        self.running = True
        logger.info("Nemoclaw Daemon started")
        while self.running:
            # Watch model registry for changes
            # Handle socket connections
            # Read kernel events
            await asyncio.sleep(1)
        await self.shutdown()

    async def shutdown(self) -> None:
        """Graceful shutdown with task state persistence."""
        logger.info("Shutting down Nemoclaw Daemon")
        self.health_status = "shutting_down"

        if self.kernel_fd:
            os.close(self.kernel_fd)

        if os.path.exists(self.config.socket_path):
            os.unlink(self.config.socket_path)

        # Persist task state
        state = {
            "sandboxes": self.sandbox_manager.list_sandboxes() if self.sandbox_manager else {},
            "timestamp": time.time()
        }
        state_path = Path("/var/ruflo/nemoclaw_state.json")
        state_path.parent.mkdir(exist_ok=True)
        async with aiofiles.open(state_path, "w") as f:
            await f.write(str(state))

        logger.info("Nemoclaw Daemon stopped")

if __name__ == "__main__":
    import asyncio
    daemon = NemoclawDaemon()
    asyncio.run(daemon.initialize())
    asyncio.run(daemon.run())