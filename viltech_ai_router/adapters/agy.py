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
# Since agy 1.5 (auto-updated on 2026-11-04) headless mode also auto-denies the file
# tools unless an allow rule names the path: write and edit are allowed only inside
# the task's repository, so a write elsewhere is still denied (and ends the turn).
def sandbox_settings(repo_dir) -> str:
    raiz = f"{repo_dir}/"
    return json.dumps(
        {
            "enableTerminalSandbox": True,
            "toolPermission": "proceed-in-sandbox",
            "permissions": {"allow": [f"write_file({raiz})", f"edit_file({raiz})"]},
        },
        separators=(",", ":"),
    )


class AgyAdapter(BaseAdapter):
    def build_command(self, task: TaskRequest) -> list[str]:
        command = [self.config.bin, "--model", self.config.model]
        if self.config.effort:
            command += ["--effort", self.config.effort]
        return command + [
            "--sandbox",
            "--settings",
            sandbox_settings(task.repo_dir),
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
