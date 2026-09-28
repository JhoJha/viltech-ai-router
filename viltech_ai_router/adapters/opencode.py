"""OpenCode CLI command shape."""

from .base import BaseAdapter
from ..models import TaskRequest


class OpenCodeAdapter(BaseAdapter):
    def build_command(self, task: TaskRequest) -> list[str]:
        command = [self.config.bin, "run", "-m", self.config.model]
        if self.config.variant:
            command += ["--variant", self.config.variant]
        return command + ["--dir", str(task.repo_dir), "--format", "json"]

    def stdin_payload(self, task: TaskRequest) -> str:
        return task.prompt + "\n"
