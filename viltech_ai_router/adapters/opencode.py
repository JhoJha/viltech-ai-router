"""OpenCode CLI command shape."""

from .base import BaseAdapter, json_events
from ..models import TaskRequest


class OpenCodeAdapter(BaseAdapter):
    def build_command(self, task: TaskRequest) -> list[str]:
        command = [self.config.bin, "run", "-m", self.config.model]
        if self.config.variant:
            command += ["--variant", self.config.variant]
        return command + ["--dir", str(task.repo_dir), "--format", "json"]

    def stdin_payload(self, task: TaskRequest) -> str:
        return task.prompt + "\n"

    def output_error(self, stdout: str, stderr: str) -> str | None:
        for event in json_events(stdout):
            if event.get("type") == "error":
                error = event.get("error") or {}
                data = error.get("data") if isinstance(error, dict) else None
                message = data.get("message") if isinstance(data, dict) else None
                return message or "opencode error event"
        return None

    def extract_text(self, stdout: str) -> str:
        parts = [event.get("part", {}).get("text", "") for event in json_events(stdout)
                 if event.get("type") == "text"]
        return "\n".join(part for part in parts if part).strip()
