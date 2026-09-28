# Feature: local-mvp-resource-router

## Objective
Deliver the local MVP of VilTech AI Router with RESOURCE/MODEL-granular routing: TOML `[resources.<name>]` config, risk/cost-aware selection, single-pass failover on infrastructure failures only, privacy-safe telemetry, and stdlib-only CLI (`inventory`, `status`, `route`, `run`, `state-reset`). Local implementation only: work-unit commits are allowed; no push, remote repository, PR or deploy.

## Problem
Scaffold routes at CLI-adapter granularity (`[adapters.*]`), but one adapter exposes many models with different quotas/risk profiles. Routing must be per-resource (adapter + model) so premium models are protected and quota failures are tracked per model.

## Why
Preserve the useful scaffold (enums, classifier patterns, state cooldown logic, telemetry shape) but refactor its granularity and command shapes to the corrected plan.

## Scope
- Refactor `viltech_ai_router/` to resource granularity; add `router.py` (selection + failover), `cli.py`, `__main__.py`.
- Rewrite `router.toml` with real discovered resources.
- Remove duplicate placeholder `src/viltech_router/` (done: verified unreferenced, untracked).
- Add `tests/` unittest suite.
- Update README minimally.
- Local work-unit commits allowed. NO push/PR/remote/deploy.

## Constraints
- Python stdlib only (tomllib, argparse, subprocess, unittest). No external deps.
- State and telemetry keyed by resource name.
- Failover ONLY on quota/rate/provider-down/provider-timeout/offline infra failures; NEVER on task/test/code failure.
- Auth error persists for the resource (state), never retried in same run; may fall through to a different provider.
- EXHAUSTED uses configurable `quota_retry_seconds` cooldown → auto-recovery without manual state deletion.
- Subprocess timeout → `provider_timeout` infra failure.
- Telemetry records NO prompt/stdout/stderr/source/credentials.
- No dangerous bypass flags (Codex uses `-s workspace-write -a never`).

## Tasks
- [x] T-1 models.py: ResourceConfig (name, adapter, bin, model, variant/effort optional, roles, min_risk, max_risk, priority, cost_class, quota_retry_seconds, timeout_seconds optional), RouterConfig (state_file, telemetry_file, default_cooldown_seconds, worker_timeout_seconds, resources, raw), add ErrorCategory.PROVIDER_TIMEOUT + WORKER_TIMEOUT, TaskRequest/RouteDecision/ExecutionResult keyed by resource.
- [x] T-2 config.py: load `[resources.<name>]` per schema; keep [router] defaults; validate enums; per-resource quota_retry_seconds fallback to router default; timeout fallback to worker_timeout_seconds (legacy provider_timeout_seconds accepted as alias).
- [x] T-3 classifier.py: provider-reported timeout patterns (`timed out`, `timeout`, `deadline exceeded`, `request timeout`) remain infrastructure signals; rate/quota/auth/provider_down/task_failure ordering preserved.
- [x] T-4 state.py: resource-keyed `{"resources": {...}}`; cooldown auto-recovery for exhausted (quota_retry_seconds), rate_limited/provider_down/offline (default cooldown); auth_error persists (no auto-recovery); `state-reset` support (clear all or one resource).
- [x] T-5 telemetry.py: key by resource; include adapter+model; repo basename only; allowlisted JSONL excludes prompt/stdout/stderr/source/credentials.
- [x] T-6 adapters: base.execute has a whole-worker timeout (TimeoutExpired → WORKER_TIMEOUT, non-failover) and FileNotFoundError → offline infra. Prompts use stdin, not argv: Agy uses stream-json stdin, OpenCode uses stdin + `--dir`, Codex uses `exec --ephemeral -` with global sandbox/approval flags before `exec`; factory uses ResourceConfig.
- [x] T-7 router.py: candidate selection filters (enabled, role, risk window [min,max], state eligible, bin installed) + sort (priority, cost_class) asc; rejected_reasons per resource; run() iterates candidates once, records telemetry, updates resource state and fails over only on classified infrastructure/resource failures; task/unknown/whole-worker timeout stop without replay.
- [x] T-8 cli.py + __main__.py: argparse commands inventory/status/route/run/state-reset; route is dry-run; run supports --prompt | --prompt-file, --repo-dir, --role, --risk; python -m viltech_ai_router.
- [x] T-9 router.toml: real resources configured. Low/medium order is OpenCode DeepSeek → OpenCode Luna → Agy Gemini Flash; high-risk premium order is Agy Opus → Codex Sol. Risk windows prevent low/medium spill into premium.
- [x] T-10 tests/: unittest covers risk/cost routing, model-specific command + stdin shapes, provider timeout vs whole-worker timeout, quota/rate/auth/provider patterns, exhausted cooldown recovery, infra failover, privacy, NO failover on task failure, and no low-risk premium spillover.
- [x] T-11 README update (resource granularity, commands, reactive quota boundary, cooldown behavior, and whole-worker timeout semantics).

## Acceptance criteria
- All unittest tests pass via `python -m unittest discover -s tests -v`.
- `python -m viltech_ai_router inventory --config router.toml` lists the 5 resources.
- `python -m viltech_ai_router route --role coder --risk low` dry-runs without executing; premium resources excluded for low/medium risk.
- Real dogfood `run` completed with `opencode_deepseek`; deterministic fake-provider E2E demonstrated quota exhaustion → fallback success and privacy-safe telemetry.
- State file uses resource keys; exhausted auto-recovers after quota_retry_seconds.

## Route declaration
- T-1..T-11: delegated direct (one bounded writer) — writer trigger (2+ non-trivial files).
- Verification: parent runs tests + dry-run inventory/route (delegated verification gate; RDD off/unknown path → assess + structural readback).

## Progress
- 2026-09-27: scaffold inspected; real CLIs inventoried; cheap Agy planner timed out, OpenCode DeepSeek produced the MVP plan; DeepSeek implementation timed out, Codex Sol completed most code; orchestrator corrected CLI details and routing policy.
- 2026-09-27: tests + deterministic failover E2E passed; real low-risk dogfood routed to OpenCode DeepSeek successfully with no prompt in telemetry.
- 2026-09-27: independent Agy/Gemini one-shot review found three HIGHs and two MEDIUMs. Prompt argv exposure fixed with stdin transports; whole-worker timeout changed to non-failover; OpenCode gained explicit `--dir` while every subprocess already runs with cwd=repo and Codex uses `-C`; no-premium-spill test added. Generic local `timed out` text no longer counts as provider timeout. Offline auto-recovery remains acceptable for MVP because every route re-checks binary presence before execution.
- 2026-09-27: final verification: 11/11 unittest PASS, compileall PASS, diff check PASS, secret scan 0 findings. Real Agy stream-json stdin probe returned `AGY_STDIN_OK`; real router dogfood with final stdin transport routed low-risk review to `opencode_deepseek` and exited 0. Deterministic fake E2E again proved quota exhaustion → exactly one fallback success with prompt absent from state/telemetry.
- Local implementation commit: `cf803cf0b2354281fa6952129c7c7903ef1e1bcd` (`feat(router): add multimodel quota-aware failover`). No remote, push, PR or deploy.

## Checks
- `python -m unittest discover -s tests -v`
- `python -m viltech_ai_router inventory --config router.toml`
- `python -m viltech_ai_router route --role coder --risk low --config router.toml`
- `python -m viltech_ai_router status --config router.toml`