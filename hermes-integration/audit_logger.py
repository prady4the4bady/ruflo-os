import os
import json
import time
from typing import Optional, Dict, List
import structlog

logger = structlog.get_logger(__name__)

class AuditLogger:
    """JSONL + SQLite audit trail for all agent actions."""

    def __init__(self, log_dir: str = "/var/ruflo/audit", use_sqlite: bool = True):
        self.log_dir = log_dir
        os.makedirs(log_dir, exist_ok=True)
        self.jsonl_path = os.path.join(log_dir, "audit.jsonl")
        self.use_sqlite = use_sqlite
        self.conn = None

        if use_sqlite:
            try:
                import sqlite3
                self.db_path = os.path.join(log_dir, "audit.db")
                self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
                self._init_sqlite()
            except Exception as e:
                logger.error("SQLite init failed", error=str(e))
                self.use_sqlite = False

    def _init_sqlite(self) -> None:
        cursor = self.conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL,
                task_id TEXT,
                action_type TEXT,
                action_data TEXT,
                result TEXT,
                tool TEXT
            )
        """)
        self.conn.commit()

    def log_action(self, task_id: str, action_type: str, action_data: Dict, result: Optional[Dict] = None, tool: Optional[str] = None) -> None:
        entry = {
            "timestamp": time.time(),
            "task_id": task_id,
            "action_type": action_type,
            "action_data": action_data,
            "result": result,
            "tool": tool
        }

        # Write to JSONL
        with open(self.jsonl_path, "a") as f:
            f.write(json.dumps(entry) + "\n")

        # Write to SQLite
        if self.use_sqlite and self.conn:
            try:
                cursor = self.conn.cursor()
                cursor.execute(
                    "INSERT INTO audit_log (timestamp, task_id, action_type, action_data, result, tool) VALUES (?, ?, ?, ?, ?, ?)",
                    (entry["timestamp"], task_id, action_type, json.dumps(action_data), json.dumps(result) if result else None, tool)
                )
                self.conn.commit()
            except Exception as e:
                logger.error("SQLite log failed", error=str(e))

        logger.info("Audit log entry", task_id=task_id, action=action_type)

    def get_logs(self, task_id: Optional[str] = None, limit: int = 100) -> List[Dict]:
        if self.use_sqlite and self.conn:
            cursor = self.conn.cursor()
            if task_id:
                cursor.execute("SELECT * FROM audit_log WHERE task_id = ? ORDER BY timestamp DESC LIMIT ?", (task_id, limit))
            else:
                cursor.execute("SELECT * FROM audit_log ORDER BY timestamp DESC LIMIT ?", (limit,))
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
        else:
            # Read from JSONL
            logs = []
            try:
                with open(self.jsonl_path, "r") as f:
                    for line in f:
                        entry = json.loads(line)
                        if task_id and entry.get("task_id") != task_id:
                            continue
                        logs.append(entry)
                        if len(logs) >= limit:
                            break
            except FileNotFoundError:
                pass
            return logs