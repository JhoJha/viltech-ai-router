"""Subprocess boundary for configured CLI resources."""

from abc import ABC, abstractmethod
import json
import shutil
import subprocess
import time
from ..classifier import classify_error
from ..models import ErrorCategory, ExecutionResult, ResourceConfig, TaskRequest


def json_events(stdout: str) -> list[dict]:
    """Parse NDJSON output, skipping lines that are not JSON objects."""
    events = []
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict):
            events.append(event)
    return events


class BaseAdapter(ABC):
    def __init__(self, config: ResourceConfig):
        self.config = config

    def is_installed(self) -> bool:
        return shutil.which(self.config.bin) is not None

    @abstractmethod
    def build_command(self, task: TaskRequest) -> list[str]:
        """Return argv without invoking the provider."""

    def stdin_payload(self, task: TaskRequest) -> str | None:
        """Return prompt transport for stdin when supported by the CLI."""
        return None

    def output_error(self, stdout: str, stderr: str) -> str | None:
        """Return the error a CLI reported in its output despite exiting 0."""
        return None

    def extract_text(self, stdout: str) -> str:
        """Return the worker's final answer from the CLI output."""
        return stdout.strip()

    def execute(self, task: TaskRequest) -> ExecutionResult:
        start = time.monotonic()
        try:
            process = subprocess.run(
                self.build_command(task), cwd=str(task.repo_dir), capture_output=True,
                text=True, timeout=self.config.timeout_seconds, input=self.stdin_payload(task),
            )
            code, stdout, stderr = process.returncode, process.stdout or "", process.stderr or ""
            reported = self.output_error(stdout, stderr) if code == 0 else None
            if reported is not None:
                code, stderr = 1, f"{stderr}\n{reported}"
            category, infra = classify_error(code, stdout, stderr)
        except subprocess.TimeoutExpired:
            code, stdout, stderr = 124, "", ""
            # This is a whole-worker timeout. It may be caused by long tests or a
            # stuck local tool, so it must not automatically replay on another model.
            category, infra = ErrorCategory.WORKER_TIMEOUT, False
        except FileNotFoundError:
            code, stdout, stderr = 127, "", ""
            category, infra = ErrorCategory.OFFLINE, True
        except OSError:
            code, stdout, stderr = 1, "", ""
            category, infra = ErrorCategory.UNKNOWN_ERROR, False
        return ExecutionResult(
            resource_name=self.config.name, adapter=self.config.adapter, model=self.config.model,
            exit_code=code, stdout=stdout, stderr=stderr, error_category=category,
            duration_seconds=time.monotonic() - start, is_infrastructure_failure=infra,
        )
