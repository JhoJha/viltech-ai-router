# AGENTS.md — VilTech AI Router

## Objective
Build a small, auditable local control plane that routes software-engineering tasks across installed AI CLIs, detects provider/quota failures, fails over safely, and records telemetry.

## Safety
- Never read, print, copy, or persist API keys, auth tokens, cookies, or credential files.
- Never use dangerous bypass flags.
- Never push, create a remote repository, deploy, or modify other repositories unless the operator explicitly authorizes that separate action.
- Worker execution must be scoped to the target repository/worktree supplied by the operator.
- A provider failure must not cause destructive Git recovery commands.
- No git reset --hard, git clean, git stash, rebase, force push, or history rewrite.
- Persistent router state may contain provider/model names, timestamps, exit categories, duration, token/cost stats when exposed safely, but no prompts containing secrets and no raw credentials.
- Quota/rate-limit detection may use CLI errors; do not probe premium models just to consume quota.
- Fallback is role/risk aware: do not silently replace a required high-risk reviewer/planner with a weaker worker.

## MVP
- Python standard library only.
- TOML config.
- Adapters for Agy, OpenCode, Codex.
- Gentle/GGA may be exposed as a reviewer integration but GentleAI itself is not treated as a model provider.
- Commands: inventory, status, route, run.
- Resource states: available, near_limit, exhausted, cooldown, rate_limited, auth_error, provider_down, offline, unknown.
- Classify common quota/rate/auth/provider errors from subprocess exit/output.
- Fail over only on infrastructure/resource failures, not on arbitrary task/test failures.
- Append JSONL telemetry with no secrets.
- Unit tests for routing and error classification.
