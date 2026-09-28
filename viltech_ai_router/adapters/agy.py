"""Agy CLI command shape."""

import json

from .base import BaseAdapter
from ..models import TaskRequest


class AgyAdapter(BaseAdapter):
    def build_command(self, task: TaskRequest) -> list[str]:
        command = [self.config.bin, "--model", self.config.model]
        if self.config.effort:
            command += ["--effort", self.config.effort]
        return command + [
            "--input-format",
            "stream-json",
            "--output-format",
            "stream-json",
        ]

    def stdin_payload(self, task: TaskRequest) -> str:
        return json.dumps(
            {"event": "user", "message": {"content": task.prompt}},
            separators=(",", ":"),
        ) + "\n"
