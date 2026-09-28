"""Strict TOML configuration for model-granular resources."""

from pathlib import Path
import tomllib

from .models import CostClass, ResourceConfig, RiskLevel, Role, RouterConfig, RISK_ORDER

DEFAULT_CONFIG_PATH = Path("router.toml")
DEFAULT_STATE = Path("~/.local/state/viltech-ai-router/state.json")
DEFAULT_TELEMETRY = Path("~/.local/state/viltech-ai-router/telemetry.jsonl")
ADAPTERS = {"agy", "opencode", "codex"}


def _positive(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def load_config(config_path: Path | None = None) -> RouterConfig:
    """Load a local TOML file; reject invalid resources rather than silently weakening policy."""
    path = config_path or DEFAULT_CONFIG_PATH
    with Path(path).open("rb") as stream:
        raw = tomllib.load(stream)
    router = raw.get("router", {})
    cooldown = _positive(router.get("default_cooldown_seconds", 300), "default_cooldown_seconds")
    timeout = _positive(
        router.get("worker_timeout_seconds", router.get("provider_timeout_seconds", 600)),
        "worker_timeout_seconds",
    )
    resources = {}
    for name, item in raw.get("resources", {}).items():
        if not isinstance(item, dict):
            raise ValueError(f"resources.{name} must be a table")
        adapter = item.get("adapter")
        if adapter not in ADAPTERS:
            raise ValueError(f"resources.{name}.adapter must be agy, opencode, or codex")
        model = item.get("model")
        if not isinstance(model, str) or not model:
            raise ValueError(f"resources.{name}.model is required")
        binary = item.get("bin", adapter)
        if not isinstance(binary, str) or not binary:
            raise ValueError(f"resources.{name}.bin must be nonempty")
        roles = tuple(Role(value) for value in item.get("roles", []))
        if not roles:
            raise ValueError(f"resources.{name}.roles must be nonempty")
        min_risk = RiskLevel(item.get("min_risk", "low"))
        max_risk = RiskLevel(item.get("max_risk", "high"))
        if RISK_ORDER[min_risk] > RISK_ORDER[max_risk]:
            raise ValueError(f"resources.{name}: min_risk exceeds max_risk")
        enabled = item.get("enabled", True)
        if not isinstance(enabled, bool):
            raise ValueError(f"resources.{name}.enabled must be boolean")
        for optional in ("variant", "effort"):
            if optional in item and (not isinstance(item[optional], str) or not item[optional]):
                raise ValueError(f"resources.{name}.{optional} must be nonempty text")
        resources[name] = ResourceConfig(
            name=name, adapter=adapter, bin=binary, model=model, roles=roles,
            min_risk=min_risk, max_risk=max_risk,
            priority=_positive(item.get("priority", 50), f"resources.{name}.priority"),
            cost_class=CostClass(item.get("cost_class", "standard")),
            quota_retry_seconds=_positive(item.get("quota_retry_seconds", cooldown), f"resources.{name}.quota_retry_seconds"),
            timeout_seconds=_positive(item.get("timeout_seconds", timeout), f"resources.{name}.timeout_seconds"),
            enabled=enabled, variant=item.get("variant"), effort=item.get("effort"),
        )
    if not resources:
        raise ValueError("configuration requires at least one [resources.<name>] table")
    return RouterConfig(
        state_file=Path(router.get("state_file", str(DEFAULT_STATE))).expanduser(),
        telemetry_file=Path(router.get("telemetry_file", str(DEFAULT_TELEMETRY))).expanduser(),
        default_cooldown_seconds=cooldown, worker_timeout_seconds=timeout,
        resources=resources, raw=raw,
    )
