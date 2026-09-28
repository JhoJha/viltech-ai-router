"""Subprocess boundary for configured CLI resources."""

from abc import ABC, abstractmethod
import shutil
import subprocess
import time
from ..classifier import classify_error
from ..models import ErrorCategory, ExecutionResult, ResourceConfig, TaskRequest


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

    def execute(self, task: TaskRequest) -> ExecutionResult:
        start = time.monotonic()
        try:
            process = subprocess.run(
                self.build_command(task), cwd=str(task.repo_dir), capture_output=True,
                text=True, timeout=self.config.timeout_seconds, input=self.stdin_payload(task),
            )
            code, stdout, stderr = process.returncode, process.stdout or "", process.stderr or ""
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
