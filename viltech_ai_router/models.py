"""Typed resource and execution models for the local router."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path


class Role(str, Enum):
    PLANNER = "planner"
    CODER = "coder"
    REVIEWER = "reviewer"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ResourceState(str, Enum):
    AVAILABLE = "available"
    NEAR_LIMIT = "near_limit"
    EXHAUSTED = "exhausted"
    COOLDOWN = "cooldown"
    RATE_LIMITED = "rate_limited"
    AUTH_ERROR = "auth_error"
    PROVIDER_DOWN = "provider_down"
    OFFLINE = "offline"
    UNKNOWN = "unknown"


class ErrorCategory(str, Enum):
    NONE = "none"
    RATE_LIMIT = "rate_limit"
    QUOTA_EXHAUSTED = "quota_exhausted"
    AUTH_ERROR = "auth_error"
    PROVIDER_TIMEOUT = "provider_timeout"
    WORKER_TIMEOUT = "worker_timeout"
    PROVIDER_DOWN = "provider_down"
    OFFLINE = "offline"
    TASK_FAILURE = "task_failure"
    UNKNOWN_ERROR = "unknown_error"


class CostClass(str, Enum):
    FREE = "free"
    LOW = "low"
    STANDARD = "standard"
    PREMIUM = "premium"


RISK_ORDER = {RiskLevel.LOW: 0, RiskLevel.MEDIUM: 1, RiskLevel.HIGH: 2}
COST_ORDER = {CostClass.FREE: 0, CostClass.LOW: 1, CostClass.STANDARD: 2, CostClass.PREMIUM: 3}


@dataclass(frozen=True)
class ResourceConfig:
    name: str
    adapter: str
    bin: str
    model: str
    roles: tuple[Role, ...]
    min_risk: RiskLevel = RiskLevel.LOW
    max_risk: RiskLevel = RiskLevel.HIGH
    priority: int = 50
    cost_class: CostClass = CostClass.STANDARD
    quota_retry_seconds: int = 300
    timeout_seconds: int = 600
    enabled: bool = True
    variant: str | None = None
    effort: str | None = None


@dataclass(frozen=True)
class RouterConfig:
    state_file: Path
    telemetry_file: Path
    default_cooldown_seconds: int
    worker_timeout_seconds: int
    resources: dict[str, ResourceConfig]
    raw: dict = field(default_factory=dict)


@dataclass(frozen=True)
class TaskRequest:
    role: Role
    risk: RiskLevel
    prompt: str
    repo_dir: Path
    task_id: str = field(default_factory=lambda: datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f"))


@dataclass(frozen=True)
class RouteDecision:
    selected_resource: str | None
    candidates: list[str]
    rejected_reasons: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ExecutionResult:
    resource_name: str
    adapter: str
    model: str
    exit_code: int
    stdout: str
    stderr: str
    error_category: ErrorCategory
    duration_seconds: float
    is_infrastructure_failure: bool
