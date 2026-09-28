"""Resource-keyed persistent health and cooldown state."""

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from .models import ResourceState

RECOVERABLE = {ResourceState.EXHAUSTED, ResourceState.COOLDOWN, ResourceState.RATE_LIMITED,
               ResourceState.PROVIDER_DOWN, ResourceState.OFFLINE}


class StateManager:
    def __init__(self, state_file: Path):
        self.state_file = state_file
        self._data = {"resources": {}}
        self.load()

    def load(self) -> None:
        if self.state_file.exists():
            try:
                data = json.loads(self.state_file.read_text(encoding="utf-8"))
                if isinstance(data, dict) and isinstance(data.get("resources"), dict):
                    self._data = data
            except (OSError, ValueError):
                self._data = {"resources": {}}

    def save(self) -> None:
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(json.dumps(self._data, indent=2) + "\n", encoding="utf-8")

    def get_state(self, resource_name: str) -> ResourceState:
        info = self._data["resources"].get(resource_name, {})
        try:
            state = ResourceState(info.get("state", "available"))
        except ValueError:
            return ResourceState.UNKNOWN
        if state in RECOVERABLE and time.time() >= info.get("cooldown_until", float("inf")):
            self.set_state(resource_name, ResourceState.AVAILABLE)
            return ResourceState.AVAILABLE
        return state

    def get_details(self, resource_name: str) -> dict:
        self.get_state(resource_name)
        return dict(self._data["resources"].get(resource_name, {}))

    def set_state(self, resource_name: str, state: ResourceState,
                  cooldown_seconds: float = 0, last_error: str = "") -> None:
        # Persist categories, never raw provider output, which may contain secrets.
        self._data["resources"][resource_name] = {
            "state": state.value,
            "cooldown_until": time.time() + cooldown_seconds if cooldown_seconds > 0 else 0,
            "last_error": last_error,
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }
        self.save()

    def get_cooldown_remaining(self, resource_name: str) -> float:
        info = self._data["resources"].get(resource_name, {})
        return max(0.0, info.get("cooldown_until", 0) - time.time())

    def reset(self, resource_name: str | None = None) -> None:
        if resource_name is None:
            self._data = {"resources": {}}
        else:
            self._data["resources"].pop(resource_name, None)
        self.save()
