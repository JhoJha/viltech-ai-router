"""Deterministic, one-pass resource routing and infrastructure-only failover."""

from .adapters import create_adapter
from .models import (COST_ORDER, RISK_ORDER, ErrorCategory, ExecutionResult,
                     ResourceConfig, ResourceState, RouteDecision, RouterConfig, TaskRequest)
from .state import StateManager
from .telemetry import TelemetryLogger

ERROR_STATES = {
    ErrorCategory.QUOTA_EXHAUSTED: ResourceState.EXHAUSTED,
    ErrorCategory.RATE_LIMIT: ResourceState.RATE_LIMITED,
    ErrorCategory.AUTH_ERROR: ResourceState.AUTH_ERROR,
    ErrorCategory.PROVIDER_TIMEOUT: ResourceState.PROVIDER_DOWN,
    ErrorCategory.PROVIDER_DOWN: ResourceState.PROVIDER_DOWN,
    ErrorCategory.OFFLINE: ResourceState.OFFLINE,
}


class Router:
    def __init__(self, config: RouterConfig, state: StateManager | None = None,
                 telemetry: TelemetryLogger | None = None):
        self.config = config
        self.state = state or StateManager(config.state_file)
        self.telemetry = telemetry or TelemetryLogger(config.telemetry_file)

    def route(self, task: TaskRequest) -> RouteDecision:
        eligible: list[ResourceConfig] = []
        rejected = {}
        for resource in self.config.resources.values():
            reason = None
            if not resource.enabled:
                reason = "disabled"
            elif task.role not in resource.roles:
                reason = "role"
            elif not (RISK_ORDER[resource.min_risk] <= RISK_ORDER[task.risk] <= RISK_ORDER[resource.max_risk]):
                reason = "risk"
            elif self.state.get_state(resource.name) not in (ResourceState.AVAILABLE, ResourceState.NEAR_LIMIT):
                reason = f"state:{self.state.get_state(resource.name).value}"
            elif not create_adapter(resource).is_installed():
                reason = "binary_missing"
            if reason:
                rejected[resource.name] = reason
            else:
                eligible.append(resource)
        eligible.sort(key=lambda item: (item.priority, COST_ORDER[item.cost_class], item.name))
        candidates = [item.name for item in eligible]
        return RouteDecision(candidates[0] if candidates else None, candidates, rejected)

    def run(self, task: TaskRequest) -> tuple[RouteDecision, list[ExecutionResult]]:
        if not task.repo_dir.is_dir():
            raise ValueError("repo_dir must be an existing directory")
        decision = self.route(task)
        results = []
        attempted = set()
        auth_failed_adapters = set()
        for name in decision.candidates:
            if name in attempted:
                continue
            resource = self.config.resources[name]
            if resource.adapter in auth_failed_adapters:
                continue
            attempted.add(name)
            result = create_adapter(resource).execute(task)
            results.append(result)
            self.telemetry.log(task, result, len(results))
            if result.exit_code == 0:
                self.state.set_state(name, ResourceState.AVAILABLE)
                break
            if not result.is_infrastructure_failure:
                break
            state = ERROR_STATES.get(result.error_category)
            if state is None:
                break
            if state == ResourceState.AUTH_ERROR:
                auth_failed_adapters.add(resource.adapter)
            cooldown = (resource.quota_retry_seconds if state == ResourceState.EXHAUSTED
                        else self.config.default_cooldown_seconds if state != ResourceState.AUTH_ERROR else 0)
            self.state.set_state(name, state, cooldown, result.error_category.value)
        return decision, results
