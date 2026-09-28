# VilTech AI Router

Local, standard-library-only routing of software-engineering tasks to configured AI CLI resources (adapter + model). Quota and provider failures can fail over; task failures cannot. No prompt or provider output is written to state or telemetry.

## Quick path

```bash
python -m viltech_ai_router inventory --config router.toml
python -m viltech_ai_router status --config router.toml
python -m viltech_ai_router route --role coder --risk low --config router.toml
python -m viltech_ai_router run --prompt-file task.txt --repo-dir /path/to/repo --role coder --risk low --config router.toml
python -m viltech_ai_router state-reset --resource agy_flash --config router.toml
```

`route` is a dry-run; `run` invokes a provider and may incur usage. Review `router.toml` before running. Premium resources require high risk. State and telemetry are local JSON/JSONL files keyed by resource, with repo basename only. `state-reset` without `--resource` clears all resource state.

## Quota behavior in the MVP

The router does not claim an exact remaining subscription quota unless a CLI exposes that information safely. Instead it reacts to provider-reported errors such as quota exhaustion, rate limits, network/provider outages and provider timeouts. A failed resource is put into a resource-specific state and skipped while its cooldown is active; quota exhaustion becomes eligible again after `quota_retry_seconds`. This lets cheap alternatives such as OpenCode DeepSeek, Luna or Agy carry compatible work while premium resources cool down. Auth errors persist until reset, and ordinary code/test failures never trigger provider failover. Separately, `worker_timeout_seconds` bounds the entire local CLI process; that whole-worker timeout is treated as ambiguous local/task execution and **does not** automatically replay the task on another model.

Run tests with `python -m unittest discover -s tests -v`.
