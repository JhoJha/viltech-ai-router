"""Agy CLI command shape."""

import json

from .base import BaseAdapter, json_events
from ..models import TaskRequest


def _result(stdout: str) -> dict:
    """Return the final `result` event that stream-json mode emits."""
    for event in reversed(json_events(stdout)):
        if event.get("event") == "result" and isinstance(event.get("result"), dict):
            return event["result"]
    return {}


# Same contract as Codex `-s workspace-write -a never`: commands run unattended only
# inside the terminal sandbox (writes outside the repo fail); anything needing to leave
# it requires review, which headless mode auto-denies. Never use `command(...)` allow
# rules here: Antigravity lets those run outside the sandbox too.
SANDBOX_SETTINGS = '{"enableTerminalSandbox":true,"toolPermission":"proceed-in-sandbox"}'


class AgyAdapter(BaseAdapter):
    def build_command(self, task: TaskRequest) -> list[str]:
        command = [self.config.bin, "--model", self.config.model]
        if self.config.effort:
            command += ["--effort", self.config.effort]
        return command + [
            "--sandbox",
            "--settings",
            SANDBOX_SETTINGS,
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

    def output_error(self, stdout: str, stderr: str) -> str | None:
        result = _result(stdout)
        if result.get("status") == "ERROR":
            return result.get("error") or "agy result status ERROR"
        # agy reports SUCCESS with an empty answer when a tool was auto-denied.
        if not result.get("response") and "auto-denied" in stderr:
            return "permission auto-denied in headless mode"
        return None

    def extract_text(self, stdout: str) -> str:
        return (_result(stdout).get("response") or "").strip()
