"""Command-line interface; live operations require explicit OAuth and approval."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from pydantic import ValidationError

from . import __version__
from .auth import authorize, session_factory
from .config import load_config
from .demo import run_demo
from .engine import apply_plan, build_plan, check_apply
from .errors import PurgeError, SafetyError
from .gmail import GmailMailbox
from .models import Plan, Settings, State, utc_now
from .storage import exclusive_lock, read_model, write_model


def emit(value: object) -> None:
    # JSON escapes control characters from optional message header samples.
    print(json.dumps(value, ensure_ascii=True, indent=2))


def plan_summary(plan: Plan, *, samples: bool = False) -> dict[str, object]:
    plan.verify()
    rules: list[dict[str, object]] = []
    for item in plan.payload.rules:
        entry: dict[str, object] = {
            "name": item.rule.name,
            "action": item.rule.action,
            "count": len(item.message_ids),
            "destination": item.rule.label,
            "query": item.effective_query,
        }
        if samples:
            entry["samples"] = [sample.model_dump() for sample in item.samples]
        rules.append(entry)
    return {
        "source": plan.payload.source,
        "account": plan.payload.account_email,
        "created_at": plan.payload.created_at.isoformat(),
        "expires_at": plan.payload.expires_at.isoformat(),
        "total": plan.payload.total,
        "trash_total": plan.payload.trash_total,
        "confirmation_token": plan.confirmation_token,
        "sha256": plan.sha256,
        "rules": rules,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gmail-purge", description="Plan-first Gmail cleanup. Never permanently deletes mail."
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)
    auth = commands.add_parser("auth", help="Interactive Desktop OAuth bootstrap")
    auth.add_argument("--credentials", type=Path, required=True)
    auth.add_argument(
        "--write", action="store_true", help="Authorize gmail.modify instead of readonly"
    )
    auth.add_argument("--no-browser", action="store_true")

    config = commands.add_parser("config-check", help="Validate a TOML rules file without Gmail")
    config.add_argument("--config", type=Path, default=Path("config.local.toml"))

    plan = commands.add_parser("plan", help="Read-only snapshot of exact candidate message IDs")
    plan.add_argument("--config", type=Path, default=Path("config.local.toml"))
    plan.add_argument("--output", type=Path)
    plan.add_argument("--max-messages", type=int, default=2000)
    plan.add_argument("--sample-size", type=int, default=5)

    review = commands.add_parser("review", help="Review a plan locally, without Gmail")
    review.add_argument("--plan", type=Path)
    review.add_argument("--show-samples", action="store_true")

    apply = commands.add_parser("apply", help="Apply a reviewed, unexpired plan with checkpoints")
    apply.add_argument("--plan", type=Path)
    apply.add_argument("--state", type=Path)
    apply.add_argument("--confirm", required=True)
    apply.add_argument("--allow-trash", action="store_true")
    apply.add_argument("--quiet", action="store_true")

    status = commands.add_parser("status", help="Inspect a local checkpoint")
    status.add_argument("--plan", type=Path)
    status.add_argument("--state", type=Path)

    demo = commands.add_parser("demo", help="Synthetic offline run; no Gmail connection")
    demo.add_argument("--messages", type=int, default=12000)
    demo.add_argument("--output", type=Path)

    audit = commands.add_parser("audit", help="Read-only connected account and label inventory")
    for command in (auth, config, plan, review, apply, status, demo, audit):
        command.add_argument("--data-dir", type=Path, default=Path(".gmail-purge"))
    return parser


def state_path_for(plan_path: Path, explicit: Path | None) -> Path:
    return explicit or plan_path.with_name(f"{plan_path.stem}.state.json")


def progress(state: State) -> None:
    print(
        f"visited={state.visited} applied={state.applied} already_done={state.already_done} "
        f"protected={state.skipped_protected} missing={state.skipped_missing}",
        file=sys.stderr,
    )


def run(args: argparse.Namespace) -> int:
    data_dir: Path = args.data_dir
    if args.command == "auth":
        with exclusive_lock(data_dir / ".lock"):
            path = authorize(
                args.credentials, data_dir, write=args.write, browser=not args.no_browser
            )
        emit({"authorized": "modify" if args.write else "readonly", "token_file": str(path)})
        return 0
    if args.command == "config-check":
        config = load_config(args.config)
        emit({"valid": True, "enabled_rules": [rule.name for rule in config.rules if rule.enabled]})
        return 0
    if args.command == "demo":
        with exclusive_lock(data_dir / ".lock"):
            emit(run_demo(args.output or data_dir / "demo", args.messages))
        return 0
    if args.command == "audit":
        with GmailMailbox(Settings(), session_factory(data_dir, write=False)) as mailbox:
            emit({"account": mailbox.account(), "labels": mailbox.labels()})
        return 0
    if args.command == "plan":
        config = load_config(args.config)
        output: Path = args.output or data_dir / "plan.json"
        if output.exists():
            raise SafetyError("Plan output already exists. Use a new --output path.")
        with (
            exclusive_lock(data_dir / ".lock"),
            GmailMailbox(config.settings, session_factory(data_dir, write=False)) as mailbox,
        ):
            plan = build_plan(
                mailbox,
                config,
                max_messages=args.max_messages,
                sample_size=args.sample_size,
            )
            write_model(output, plan, overwrite=False)
        emit(plan_summary(plan))
        return 0

    plan_path: Path = args.plan or data_dir / "plan.json"
    plan = read_model(plan_path, Plan)
    plan.verify()
    if args.command == "review":
        emit(plan_summary(plan, samples=args.show_samples))
        return 0
    state_path = state_path_for(plan_path, args.state)
    if args.command == "status":
        if state_path.exists():
            state = read_model(state_path, State)
            state.verify(plan)
            emit(state.model_dump(mode="json"))
        else:
            emit({"started": False, "total": plan.payload.total})
        return 0
    if args.command == "apply":
        check_apply(plan, args.confirm, args.allow_trash, utc_now())
        if plan.payload.source != "gmail":
            raise SafetyError("Synthetic plans cannot be applied to Gmail")
        with (
            exclusive_lock(data_dir / ".lock"),
            GmailMailbox(plan.payload.settings, session_factory(data_dir, write=True)) as mailbox,
        ):
            state = apply_plan(
                mailbox,
                plan,
                state_path,
                confirmation=args.confirm,
                allow_trash=args.allow_trash,
                progress=None if args.quiet else progress,
            )
        emit(state.model_dump(mode="json"))
        return 0
    raise AssertionError("unreachable")


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return run(args)
    except SafetyError as exc:
        print(f"Safety stop: {exc}", file=sys.stderr)
        return 2
    except (ValidationError, ValueError):
        print("Input validation failed. Check the config or artifact schema.", file=sys.stderr)
        return 2
    except PurgeError as exc:
        print(f"Operational stop: {exc}", file=sys.stderr)
        return 3
    except OSError:
        print(
            "Local I/O failed. Check file paths and permissions before resuming.", file=sys.stderr
        )
        return 3
    except KeyboardInterrupt:
        print(
            "Interrupted. Re-run the same apply command to resume the last checkpoint.",
            file=sys.stderr,
        )
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
