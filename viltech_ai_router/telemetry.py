"""Allowlisted JSONL attempt telemetry; never log provider output or prompts."""

import json
from datetime import datetime, timezone
from pathlib import Path
from .models import ExecutionResult, TaskRequest


class TelemetryLogger:
    def __init__(self, log_file: Path):
        self.log_file = log_file

    def log(self, task: TaskRequest, result: ExecutionResult, attempt: int) -> None:
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "task_id": task.task_id,
            "role": task.role.value,
            "risk": task.risk.value,
            "repo_name": task.repo_dir.resolve().name,
            "resource": result.resource_name,
            "adapter": result.adapter,
            "model": result.model,
            "exit_code": result.exit_code,
            "error_category": result.error_category.value,
            "duration_seconds": round(result.duration_seconds, 3),
            "attempt": attempt,
            "success": result.exit_code == 0,
        }
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        with self.log_file.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record) + "\n")
