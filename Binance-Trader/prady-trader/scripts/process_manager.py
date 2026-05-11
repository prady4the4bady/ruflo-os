#!/usr/bin/env python3
"""
PRADY TRADER — Process Manager.
Master launcher supervising the headless trading runtime.
Auto-restarts crashed children with exponential backoff.

Run: python scripts/process_manager.py
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PYTHON = sys.executable
STATE_FILE = ROOT / "data" / "process_state.json"


@dataclass
class ManagedProcess:
    name: str
    cmd: list[str]
    process: Optional[subprocess.Popen] = None
    restart_count: int = 0
    last_start: float = 0.0
    max_restarts: int = 10
    backoff_base: float = 2.0


class ProcessManager:
    """Supervises child processes with auto-restart and heartbeat."""

    def __init__(self) -> None:
        self._processes: Dict[str, ManagedProcess] = {}
        self._running = True
        self._start_time = time.time()

        # Define managed processes
        self._processes["orchestrator"] = ManagedProcess(
            name="orchestrator",
            cmd=[PYTHON, str(ROOT / "scripts" / "start_paper.py")],
        )

    def start_all(self) -> None:
        """Start all managed processes."""
        print("=" * 60)
        print("  PRADY TRADER — Process Manager")
        print("=" * 60)
        print(f"  Python: {PYTHON}")
        print(f"  Root:   {ROOT}")
        print()

        for name, mp in self._processes.items():
            self._start_process(mp)

        self._persist_state()

    def _start_process(self, mp: ManagedProcess) -> None:
        """Start or restart a single process."""
        try:
            env = os.environ.copy()
            env["PYTHONPATH"] = str(ROOT)
            mp.process = subprocess.Popen(
                mp.cmd,
                cwd=str(ROOT),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
            mp.last_start = time.time()
            print(f"  [START] {mp.name} (PID={mp.process.pid})")
        except Exception as exc:
            print(f"  [ERROR] Failed to start {mp.name}: {exc}")

    def _check_and_restart(self) -> None:
        """Check if any process died and restart with backoff."""
        for name, mp in self._processes.items():
            if mp.process is None:
                continue
            retcode = mp.process.poll()
            if retcode is not None:
                print(f"  [DIED] {name} exited with code {retcode}")
                if mp.restart_count < mp.max_restarts:
                    backoff = min(mp.backoff_base ** mp.restart_count, 60.0)
                    print(f"  [RESTART] {name} in {backoff:.0f}s (attempt {mp.restart_count + 1}/{mp.max_restarts})")
                    time.sleep(backoff)
                    mp.restart_count += 1
                    self._start_process(mp)
                else:
                    print(f"  [GIVE UP] {name} exceeded max restarts ({mp.max_restarts})")

    def _persist_state(self) -> None:
        """Write process state for dashboard/monitoring."""
        try:
            STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            state = {
                "manager_pid": os.getpid(),
                "uptime_sec": round(time.time() - self._start_time, 1),
                "processes": {},
            }
            for name, mp in self._processes.items():
                state["processes"][name] = {
                    "pid": mp.process.pid if mp.process else None,
                    "alive": mp.process.poll() is None if mp.process else False,
                    "restart_count": mp.restart_count,
                    "last_start": mp.last_start,
                }
            STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")
        except Exception:
            pass

    def stop_all(self) -> None:
        """Gracefully stop all processes."""
        print("\n  [SHUTDOWN] Stopping all processes...")
        self._running = False
        for name, mp in self._processes.items():
            if mp.process and mp.process.poll() is None:
                print(f"  [STOP] {name} (PID={mp.process.pid})")
                mp.process.terminate()
                try:
                    mp.process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    mp.process.kill()
                    print(f"  [KILL] {name} force-killed")

        # Clean up state file
        try:
            if STATE_FILE.exists():
                STATE_FILE.unlink()
        except Exception:
            pass
        print("  [DONE] All processes stopped.")

    def run(self) -> None:
        """Main supervisor loop."""
        self.start_all()

        # Register signal handlers
        def _signal_handler(signum, frame):
            self.stop_all()
            sys.exit(0)

        signal.signal(signal.SIGINT, _signal_handler)
        signal.signal(signal.SIGTERM, _signal_handler)

        print(f"\n  Process Manager running (PID={os.getpid()})")
        print("  Press Ctrl+C to stop all.\n")

        while self._running:
            try:
                self._check_and_restart()
                self._persist_state()
                time.sleep(5)  # Check every 5 seconds
            except KeyboardInterrupt:
                break

        self.stop_all()


if __name__ == "__main__":
    pm = ProcessManager()
    pm.run()
