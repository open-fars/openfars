from __future__ import annotations

import argparse
import json
import os
import shlex
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

from .config import OpenFARSConfig
from .human import HumanDecisionRequired, write_decision
from .leaderboards import LeaderboardSubscriber
from .models import ModelRouter
from .orchestrator import ResearchOrchestrator
from .release import Publisher, ReleaseBuilder
from .remote import SSHExecutor
from .web import serve
from .workspace import Workspace

COMMANDS = {
    "run",
    "status",
    "decide",
    "doctor",
    "remote-probe",
    "remote-run",
    "remote-push",
    "remote-pull",
    "models-refresh",
    "models-status",
    "bundle",
    "publish",
    "web",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="openfars", description="Multi-model, human-steered autonomous research"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run = subparsers.add_parser("run", help="start or resume a research project")
    _config_argument(run)
    run.add_argument("--topic", "--topics", nargs="+", default=[])
    run.add_argument("--project-id")
    run.add_argument("--human-mode", choices=["off", "cli", "file"])

    status = subparsers.add_parser("status", help="show project state")
    _config_argument(status)
    status.add_argument("project_id")

    decide = subparsers.add_parser("decide", help="answer a human checkpoint")
    _config_argument(decide)
    decide.add_argument("project_id")
    decide.add_argument("checkpoint", choices=["idea", "plan", "results", "publication"])
    action = decide.add_mutually_exclusive_group(required=True)
    action.add_argument("--approve", action="store_true")
    action.add_argument("--reject", action="store_true")
    decide.add_argument("--select", dest="selected_id")
    decide.add_argument("--feedback", default="")
    decide.add_argument(
        "--set",
        action="append",
        default=[],
        metavar="KEY=JSON",
        help="override one top-level field in the approved artifact",
    )

    doctor = subparsers.add_parser("doctor", help="validate model and compute configuration")
    _config_argument(doctor)

    remote_probe = subparsers.add_parser("remote-probe", help="inspect a remote GPU target")
    _config_argument(remote_probe)
    remote_probe.add_argument("target")

    remote_run = subparsers.add_parser("remote-run", help="run an explicit remote command")
    _config_argument(remote_run)
    remote_run.add_argument("target")
    remote_run.add_argument("remote_command", nargs=argparse.REMAINDER)

    remote_push = subparsers.add_parser("remote-push", help="sync code without credentials")
    _config_argument(remote_push)
    remote_push.add_argument("target")
    remote_push.add_argument("local", type=Path)
    remote_push.add_argument("--to", default=".")

    remote_pull = subparsers.add_parser("remote-pull", help="retrieve remote artifacts")
    _config_argument(remote_pull)
    remote_pull.add_argument("target")
    remote_pull.add_argument("remote")
    remote_pull.add_argument("local", type=Path)

    models_refresh = subparsers.add_parser(
        "models-refresh", help="refresh task-specific model leaderboard snapshots"
    )
    _config_argument(models_refresh)
    models_refresh.add_argument("--force", action="store_true")

    models_status = subparsers.add_parser(
        "models-status", help="show the cached model leaderboard snapshot"
    )
    _config_argument(models_status)

    bundle = subparsers.add_parser("bundle", help="build a local reproducible release bundle")
    _config_argument(bundle)
    bundle.add_argument("project_id")

    publish = subparsers.add_parser(
        "publish", help="publish an already-reviewed bundle with explicit authorization"
    )
    _config_argument(publish)
    publish.add_argument("project_id")
    publish.add_argument("--github", action="store_true")
    publish.add_argument("--huggingface-repo")
    publish.add_argument("--modelscope-repo")
    publish.add_argument("--repo-type", choices=["model", "dataset"], default="dataset")
    publish.add_argument("--confirm", action="store_true", required=True)

    web = subparsers.add_parser("web", help="launch the local research control plane")
    _config_argument(web)
    web.add_argument("--no-open", action="store_true")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    materialized = list(argv if argv is not None else sys.argv[1:])
    # Preserve the original `python run.py --topics ...` interface.
    if materialized and materialized[0] not in COMMANDS:
        materialized.insert(0, "run")
    elif not materialized:
        materialized = ["run"]
    args = build_parser().parse_args(materialized)
    config = OpenFARSConfig.load(args.config)

    if args.command == "run":
        config = config.with_human_mode(args.human_mode)
        try:
            workspace = ResearchOrchestrator(config).run(args.topic, project_id=args.project_id)
        except HumanDecisionRequired as pending:
            packet = (
                config.runtime.output_dir
                / pending.project_id
                / "decisions"
                / f"{pending.checkpoint}.packet.md"
            )
            print(f"Paused for human input: {pending.checkpoint}")
            print(f"Read: {packet}")
            print(str(pending))
            return 2
        state = workspace.read_json("state.json")
        print(f"Project: {workspace.project_id}")
        print(f"Stage: {state['stage']}")
        print(f"Artifacts: {workspace.project_dir}")
        return 0

    if args.command == "status":
        workspace = Workspace(config.runtime.output_dir, args.project_id)
        state = workspace.read_json("state.json")
        if state is None:
            print(f"Unknown project: {args.project_id}", file=sys.stderr)
            return 1
        print(json.dumps(state, ensure_ascii=False, indent=2))
        return 0

    if args.command == "decide":
        workspace = Workspace(config.runtime.output_dir, args.project_id)
        write_decision(
            workspace,
            args.checkpoint,
            action="approve" if args.approve else "reject",
            selected_id=args.selected_id,
            feedback=args.feedback,
            overrides=_parse_overrides(args.set),
        )
        print(f"Decision recorded. Resume with: openfars run --project-id {args.project_id}")
        return 0

    if args.command == "doctor":
        return _doctor(config)

    if args.command == "models-refresh":
        snapshot = LeaderboardSubscriber(config).refresh(force=args.force)
        print(json.dumps(snapshot, ensure_ascii=False, indent=2))
        return 0

    if args.command == "models-status":
        snapshot = LeaderboardSubscriber(config).status()
        print(json.dumps(snapshot, ensure_ascii=False, indent=2))
        return 0 if snapshot else 1

    if args.command == "bundle":
        workspace = Workspace(config.runtime.output_dir, args.project_id)
        manifest = ReleaseBuilder(config.release, ModelRouter(config, workspace), workspace).build()
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
        return 0

    if args.command == "publish":
        workspace = Workspace(config.runtime.output_dir, args.project_id)
        receipts = Publisher(config.release, workspace).publish(
            confirm=args.confirm,
            github=args.github,
            huggingface_repo=args.huggingface_repo,
            modelscope_repo=args.modelscope_repo,
            repo_type=args.repo_type,
        )
        print(json.dumps(receipts, ensure_ascii=False, indent=2))
        return 0

    if args.command == "web":
        serve(config, open_browser=not args.no_open)
        return 0

    target = _target(config, args.target)
    executor = SSHExecutor(target)
    if args.command == "remote-probe":
        result = executor.probe()
        print(result.stdout, end="")
        if result.stderr:
            print(result.stderr, file=sys.stderr, end="")
        return result.returncode
    if args.command == "remote-run":
        if not args.remote_command:
            raise ValueError("remote-run requires a command after the target")
        result = executor.run(shlex.join(args.remote_command))
        print(result.stdout, end="")
        if result.stderr:
            print(result.stderr, file=sys.stderr, end="")
        return result.returncode
    if args.command == "remote-push":
        executor.push(args.local, args.to)
        print(f"Synced to compute target '{args.target}'")
        return 0
    if args.command == "remote-pull":
        executor.pull(args.remote, args.local)
        print(f"Retrieved from compute target '{args.target}'")
        return 0
    return 1


def _config_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--config", type=Path, default=Path("openfars.yaml"), help="YAML configuration"
    )


def _parse_overrides(items: Sequence[str]) -> Dict[str, Any]:
    parsed: Dict[str, Any] = {}
    for item in items:
        if "=" not in item:
            raise ValueError(f"Override must be KEY=JSON: {item}")
        key, value = item.split("=", 1)
        if not key or "." in key or "/" in key:
            raise ValueError("Override keys must be one top-level field")
        try:
            parsed[key] = json.loads(value)
        except json.JSONDecodeError:
            parsed[key] = value
    return parsed


def _target(config: OpenFARSConfig, name: str):
    try:
        return config.compute[name]
    except KeyError as error:
        raise ValueError(f"Unknown compute target '{name}'") from error


def _doctor(config: OpenFARSConfig) -> int:
    healthy = True
    print("Model routes:")
    for name, route in config.models.items():
        key_status = "not required"
        if route.api_key_env:
            key_status = "set" if os.getenv(route.api_key_env) else "MISSING"
            healthy = healthy and key_status == "set"
        print(f"  {name}: {route.backend} -> {route.model} [{key_status}]")
    if config.compute:
        print("Compute targets:")
    for name, target in config.compute.items():
        try:
            exists = target.resolved_identity_file().is_file()
        except ValueError:
            exists = False
        healthy = healthy and exists
        print(
            f"  {name}: {target.user}@{target.host}:{target.port} [key {'ready' if exists else 'MISSING'}]"
        )
    return 0 if healthy else 1


if __name__ == "__main__":
    raise SystemExit(main())
