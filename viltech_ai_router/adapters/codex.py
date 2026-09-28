"""Codex CLI command shape with bounded sandbox and no approval prompts."""

from .base import BaseAdapter
from ..models import TaskRequest


class CodexAdapter(BaseAdapter):
    def build_command(self, task: TaskRequest) -> list[str]:
        return [
            self.config.bin,
            "-a",
            "never",
            "-s",
            "workspace-write",
            "-C",
            str(task.repo_dir),
            "-m",
            self.config.model,
            "exec",
            "--ephemeral",
            "-",
        ]

    def stdin_payload(self, task: TaskRequest) -> str:
        return task.prompt
