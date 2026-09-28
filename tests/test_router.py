"""Focused stdlib tests of resource selection, subprocess boundaries and privacy."""

from dataclasses import replace
import json
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch

from viltech_ai_router.adapters import create_adapter
from viltech_ai_router.classifier import classify_error
from viltech_ai_router.config import load_config
from viltech_ai_router.models import (CostClass, ErrorCategory, ExecutionResult, ResourceConfig,
                                      ResourceState, RiskLevel, Role, RouterConfig, TaskRequest)
from viltech_ai_router.router import Router
from viltech_ai_router.state import StateManager


class RouterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        common = dict(adapter="agy", bin="agy", model="flash", roles=(Role.CODER,),
                      min_risk=RiskLevel.LOW, max_risk=RiskLevel.HIGH,
                      quota_retry_seconds=3, timeout_seconds=2)
        self.resources = {
            "flash": ResourceConfig(name="flash", priority=10, cost_class=CostClass.LOW, **common),
            "premium": ResourceConfig(name="premium", priority=1, cost_class=CostClass.PREMIUM,
                                      min_risk=RiskLevel.HIGH, **{k: v for k, v in common.items() if k != "min_risk"}),
        }
        self.config = RouterConfig(self.root / "state.json", self.root / "telemetry.jsonl", 3, 2, self.resources)
        self.task = TaskRequest(Role.CODER, RiskLevel.LOW, "secret prompt", self.root)

    @patch("viltech_ai_router.adapters.base.shutil.which", return_value="/bin/fake")
    def test_low_risk_excludes_premium_and_high_selects_priority(self, _):
        router = Router(self.config)
        self.assertEqual(router.route(self.task).candidates, ["flash"])
        high = replace(self.task, risk=RiskLevel.HIGH)
        self.assertEqual(router.route(high).candidates, ["premium", "flash"])

    @patch("viltech_ai_router.adapters.base.shutil.which", return_value="/bin/fake")
    def test_cost_breaks_priority_tie(self, _):
        resources = dict(self.resources)
        resources["premium"] = replace(resources["premium"], min_risk=RiskLevel.LOW, priority=10)
        self.assertEqual(Router(replace(self.config, resources=resources)).route(self.task).candidates,
                         ["flash", "premium"])

    def test_commands_are_model_specific(self):
        agy = self.resources["flash"]
        self.assertEqual(create_adapter(agy).build_command(self.task),
                         ["agy", "--model", "flash", "--input-format", "stream-json",
                          "--output-format", "stream-json"])
        self.assertIn(
            '"content":"secret prompt"',
            create_adapter(agy).stdin_payload(self.task),
        )
        opencode = replace(agy, adapter="opencode", bin="opencode", model="provider/model", variant="fast")
        self.assertEqual(create_adapter(opencode).build_command(self.task),
                         ["opencode", "run", "-m", "provider/model", "--variant", "fast",
                          "--dir", str(self.root), "--format", "json"])
        self.assertEqual(create_adapter(opencode).stdin_payload(self.task), "secret prompt\n")
        codex = replace(agy, adapter="codex", bin="codex", model="gpt-6-sol")
        self.assertEqual(create_adapter(codex).build_command(self.task),
                         ["codex", "-a", "never", "-s", "workspace-write", "-C",
                          str(self.root), "-m", "gpt-6-sol", "exec", "--ephemeral", "-"])
        self.assertEqual(create_adapter(codex).stdin_payload(self.task), "secret prompt")

    def test_classifier_and_timeout(self):
        for message, expected in [
            ("429 too many requests", ErrorCategory.RATE_LIMIT),
            ("quota exceeded", ErrorCategory.QUOTA_EXHAUSTED),
            ("401 unauthorized", ErrorCategory.AUTH_ERROR),
            ("deadline exceeded", ErrorCategory.PROVIDER_TIMEOUT),
            ("503 service unavailable", ErrorCategory.PROVIDER_DOWN),
        ]:
            self.assertEqual(classify_error(1, "", message), (expected, True))
        self.assertEqual(classify_error(1, "", "tests failed"), (ErrorCategory.TASK_FAILURE, False))
        self.assertEqual(
            classify_error(1, "", "worker timed out while running local tests"),
            (ErrorCategory.UNKNOWN_ERROR, False),
        )
        with patch("viltech_ai_router.adapters.base.subprocess.run", side_effect=subprocess.TimeoutExpired("agy", 2)):
            result = create_adapter(self.resources["flash"]).execute(self.task)
        self.assertEqual(result.error_category, ErrorCategory.WORKER_TIMEOUT)
        self.assertFalse(result.is_infrastructure_failure)
        with patch("viltech_ai_router.adapters.base.subprocess.run", side_effect=FileNotFoundError):
            result = create_adapter(self.resources["flash"]).execute(self.task)
        self.assertEqual(result.error_category, ErrorCategory.OFFLINE)

    def test_exhausted_auto_recovers_and_auth_persists(self):
        state = StateManager(self.config.state_file)
        state.set_state("flash", ResourceState.EXHAUSTED, 3, "quota_exhausted")
        self.assertEqual(state.get_state("flash"), ResourceState.EXHAUSTED)
        state._data["resources"]["flash"]["cooldown_until"] = time.time() - 1
        state.save()
        self.assertEqual(StateManager(self.config.state_file).get_state("flash"), ResourceState.AVAILABLE)
        state.set_state("flash", ResourceState.AUTH_ERROR, 0, "auth_error")
        self.assertEqual(state.get_state("flash"), ResourceState.AUTH_ERROR)
        state.reset("flash")
        self.assertEqual(state.get_state("flash"), ResourceState.AVAILABLE)

    def _result(self, name, category, infra):
        return ExecutionResult(name, "agy", "flash", 1, "sensitive stdout", "sensitive stderr",
                               category, 0.1, infra)

    @patch("viltech_ai_router.adapters.base.shutil.which", return_value="/bin/fake")
    def test_infra_failover_once_and_safe_telemetry(self, _):
        resources = dict(self.resources)
        resources["premium"] = replace(resources["premium"], min_risk=RiskLevel.LOW)
        router = Router(replace(self.config, resources=resources))
        first = self._result("premium", ErrorCategory.QUOTA_EXHAUSTED, True)
        second = replace(self._result("flash", ErrorCategory.NONE, False), exit_code=0)
        with patch("viltech_ai_router.router.create_adapter") as factory:
            factory.return_value.is_installed.return_value = True
            factory.return_value.execute.side_effect = [first, second]
            decision, results = router.run(self.task)
        self.assertEqual([result.resource_name for result in results], ["premium", "flash"])
        self.assertEqual(router.state.get_state("premium"), ResourceState.EXHAUSTED)
        records = [json.loads(line) for line in self.config.telemetry_file.read_text().splitlines()]
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]["resource"], "premium")
        self.assertEqual(records[0]["model"], "flash")
        self.assertNotIn("secret prompt", self.config.telemetry_file.read_text())
        self.assertNotIn("sensitive", self.config.telemetry_file.read_text())
        self.assertNotIn(str(self.root), self.config.telemetry_file.read_text())

    @patch("viltech_ai_router.adapters.base.shutil.which", return_value="/bin/fake")
    def test_task_failure_does_not_fail_over(self, _):
        resources = dict(self.resources)
        resources["premium"] = replace(resources["premium"], min_risk=RiskLevel.LOW)
        router = Router(replace(self.config, resources=resources))
        with patch("viltech_ai_router.router.create_adapter") as factory:
            factory.return_value.is_installed.return_value = True
            factory.return_value.execute.return_value = self._result("premium", ErrorCategory.TASK_FAILURE, False)
            _, results = router.run(self.task)
            self.assertEqual(factory.return_value.execute.call_count, 1)
        self.assertEqual(len(results), 1)

    @patch("viltech_ai_router.adapters.base.shutil.which", return_value="/bin/fake")
    def test_worker_timeout_does_not_fail_over(self, _):
        resources = dict(self.resources)
        resources["premium"] = replace(resources["premium"], min_risk=RiskLevel.LOW)
        router = Router(replace(self.config, resources=resources))
        timeout = self._result("premium", ErrorCategory.WORKER_TIMEOUT, False)
        with patch("viltech_ai_router.router.create_adapter") as factory:
            factory.return_value.is_installed.return_value = True
            factory.return_value.execute.return_value = timeout
            _, results = router.run(self.task)
            self.assertEqual(factory.return_value.execute.call_count, 1)
        self.assertEqual([item.error_category for item in results], [ErrorCategory.WORKER_TIMEOUT])

    @patch("viltech_ai_router.adapters.base.shutil.which", return_value="/bin/fake")
    def test_low_risk_never_spills_to_premium_when_cheap_resources_unavailable(self, _):
        premium = replace(
            self.resources["premium"],
            name="premium_only",
            min_risk=RiskLevel.HIGH,
            max_risk=RiskLevel.HIGH,
        )
        cheap = replace(self.resources["flash"], name="cheap")
        config = replace(self.config, resources={"cheap": cheap, "premium_only": premium})
        router = Router(config)
        router.state.set_state("cheap", ResourceState.EXHAUSTED, 60, "quota_exhausted")
        decision = router.route(self.task)
        self.assertIsNone(decision.selected_resource)
        self.assertEqual(decision.candidates, [])
        self.assertEqual(decision.rejected_reasons["premium_only"], "risk")

    @patch("viltech_ai_router.adapters.base.shutil.which", return_value="/bin/fake")
    def test_auth_failure_skips_same_provider_and_uses_other(self, _):
        resources = {
            "first": replace(self.resources["flash"], name="first", priority=1),
            "same_provider": replace(self.resources["flash"], name="same_provider", priority=2),
            "other_provider": replace(self.resources["flash"], name="other_provider",
                                      adapter="opencode", bin="opencode", priority=3),
        }
        router = Router(replace(self.config, resources=resources))
        failure = self._result("first", ErrorCategory.AUTH_ERROR, True)
        success = replace(self._result("other_provider", ErrorCategory.NONE, False), exit_code=0)
        with patch("viltech_ai_router.router.create_adapter") as factory:
            factory.return_value.is_installed.return_value = True
            factory.return_value.execute.side_effect = [failure, success]
            _, results = router.run(self.task)
        self.assertEqual([item.resource_name for item in results], ["first", "other_provider"])
        self.assertEqual(router.state.get_state("first"), ResourceState.AUTH_ERROR)

    def test_config_resource_defaults_and_validation(self):
        path = self.root / "router.toml"
        path.write_text('''[router]
default_cooldown_seconds = 9
worker_timeout_seconds = 7
[resources.worker]
adapter = "agy"
model = "flash"
roles = ["coder"]
''')
        config = load_config(path)
        self.assertEqual(config.resources["worker"].quota_retry_seconds, 9)
        self.assertEqual(config.resources["worker"].timeout_seconds, 7)
        path.write_text(path.read_text().replace('roles = ["coder"]', 'roles = ["invalid"]'))
        with self.assertRaises(ValueError):
            load_config(path)


if __name__ == "__main__":
    unittest.main()
