"""Local stdlib command-line interface."""

import argparse
import os
from pathlib import Path
import sys
from .adapters import create_adapter
from .config import load_config
from .models import RiskLevel, Role, TaskRequest
from .router import Router


def _default_config() -> Path:
    """$VILTECH_ROUTER_CONFIG, then ./router.toml, then the one next to the package,
    so the router can run from inside the repo it works on."""
    if os.environ.get("VILTECH_ROUTER_CONFIG"):
        return Path(os.environ["VILTECH_ROUTER_CONFIG"]).expanduser()
    local = Path("router.toml")
    return local if local.is_file() else Path(__file__).resolve().parent.parent / "router.toml"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="viltech-ai-router")
    parser.add_argument("--config", type=Path, default=None)
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
        config = load_config(args.config or _default_config())
        router = Router(config)
        if args.command == "inventory":
            for resource in config.resources.values():
                installed = create_adapter(resource).is_installed()
                print(f"{resource.name}\t{resource.adapter}\t{resource.model}\tinstalled={str(installed).lower()}\tstate={router.state.get_state(resource.name).value}\tenabled={str(resource.enabled).lower()}\tsensitive_ok={str(resource.sensitive_ok).lower()}")
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
            if args.command == "route":
                prompt = ""
            elif args.prompt is not None:
                prompt = args.prompt
            elif str(args.prompt_file) == "-":
                prompt = sys.stdin.read()
            else:
                prompt = args.prompt_file.read_text(encoding="utf-8")
            task = TaskRequest(Role(args.role), RiskLevel(args.risk), prompt, repo_dir)
            if args.command == "route":
                decision = router.route(task)
                print(f"sensitive_repo={str(config.is_sensitive(repo_dir)).lower()}")
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
                final = results[-1]
                print(f"final_resource={final.resource_name}")
                if final.exit_code == 0:
                    # The worker's answer goes to the operator's terminal only, never to telemetry.
                    print("----- respuesta -----")
                    print(create_adapter(config.resources[final.resource_name]).extract_text(final.stdout))
            return 0 if results and results[-1].exit_code == 0 else 2
        return 0
    except (OSError, ValueError, KeyError) as exc:
        # Avoid printing exception text: file paths and provider output can be sensitive.
        print(f"error: {type(exc).__name__}")
        return 2
