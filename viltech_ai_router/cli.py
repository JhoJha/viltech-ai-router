"""Local stdlib command-line interface."""

import argparse
from pathlib import Path
from .adapters import create_adapter
from .config import load_config
from .models import RiskLevel, Role, TaskRequest
from .router import Router


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="viltech-ai-router")
    parser.add_argument("--config", type=Path, default=Path("router.toml"))
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("inventory", "status", "route", "run", "state-reset"):
        command = sub.add_parser(name)
        command.add_argument("--config", type=Path, default=argparse.SUPPRESS)
        if name in ("route", "run"):
            command.add_argument("--role", choices=[role.value for role in Role], default="coder")
            command.add_argument("--risk", choices=[risk.value for risk in RiskLevel], default="low")
            command.add_argument("--repo-dir", type=Path, default=Path("."))
        if name == "run":
            prompts = command.add_mutually_exclusive_group(required=True)
            prompts.add_argument("--prompt")
            prompts.add_argument("--prompt-file", type=Path)
        if name == "state-reset":
            command.add_argument("--resource")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        config = load_config(args.config)
        router = Router(config)
        if args.command == "inventory":
            for resource in config.resources.values():
                installed = create_adapter(resource).is_installed()
                print(f"{resource.name}\t{resource.adapter}\t{resource.model}\tinstalled={str(installed).lower()}\tstate={router.state.get_state(resource.name).value}")
        elif args.command == "status":
            for resource in config.resources.values():
                state = router.state.get_state(resource.name).value
                remaining = router.state.get_cooldown_remaining(resource.name)
                print(f"{resource.name}\t{state}\tcooldown_seconds={remaining:.0f}")
        elif args.command == "state-reset":
            if args.resource and args.resource not in config.resources:
                raise ValueError("unknown resource")
            router.state.reset(args.resource)
            print(f"state reset: {args.resource or 'all'}")
        else:
            repo_dir = args.repo_dir.expanduser().resolve()
            if not repo_dir.is_dir():
                raise ValueError("repo_dir must be an existing directory")
            prompt = "" if args.command == "route" else (args.prompt if args.prompt is not None else args.prompt_file.read_text(encoding="utf-8"))
            task = TaskRequest(Role(args.role), RiskLevel(args.risk), prompt, repo_dir)
            if args.command == "route":
                decision = router.route(task)
                print(f"selected={decision.selected_resource or 'none'}")
                print(f"candidates={','.join(decision.candidates)}")
                for name, reason in decision.rejected_reasons.items():
                    print(f"rejected={name}:{reason}")
                return 0 if decision.selected_resource else 2
            decision, results = router.run(task)
            print(f"planned={decision.selected_resource or 'none'}")
            for result in results:
                print(f"attempt={result.resource_name} result={result.error_category.value} exit_code={result.exit_code}")
            if results:
                print(f"final_resource={results[-1].resource_name}")
            return 0 if results and results[-1].exit_code == 0 else 2
        return 0
    except (OSError, ValueError, KeyError) as exc:
        # Avoid printing exception text: file paths and provider output can be sensitive.
        print(f"error: {type(exc).__name__}")
        return 2
