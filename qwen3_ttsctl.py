from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Optional

from qwen3_tts_service import (
    DEFAULT_MODEL_ROOT,
    DEFAULT_PROMPT_CACHE_DIR,
    PortConflictError,
    ServerManager,
    ServiceConfig,
)

BASE_MODEL_ID = "Qwen3-TTS-12Hz-1.7B-Base-4bit"


def _str_or_none(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    text = value.strip()
    return text or None


def add_config_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", type=Path, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--pid-path", type=Path, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--log-path", type=Path, default=None, help=argparse.SUPPRESS)
    parser.add_argument(
        "--user-launch-agent-path",
        type=Path,
        default=None,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--managed-launch-agent-path",
        type=Path,
        default=None,
        help=argparse.SUPPRESS,
    )
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--model-root", default=None)
    parser.add_argument("--prompt-cache-dir", default=None)
    parser.add_argument("--preload-model", default=None)
    parser.add_argument("--python-executable", default=None)
    parser.add_argument("--workspace-dir", default=None)
    parser.add_argument(
        "--launch-at-login",
        dest="launch_at_login",
        action="store_true",
        default=None,
    )
    parser.add_argument(
        "--no-launch-at-login",
        dest="launch_at_login",
        action="store_false",
    )
    parser.add_argument(
        "--start-server-on-launch",
        dest="start_server_on_launch",
        action="store_true",
        default=None,
    )
    parser.add_argument(
        "--no-start-server-on-launch",
        dest="start_server_on_launch",
        action="store_false",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Manage the local Qwen3-TTS API service.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    add_config_arguments(common)

    start = subparsers.add_parser("start", parents=[common], help="Start the background service.")
    start.add_argument("--timeout", type=float, default=30.0)

    stop = subparsers.add_parser("stop", parents=[common], help="Stop the background service.")
    stop.add_argument("--timeout", type=float, default=20.0)

    restart = subparsers.add_parser(
        "restart",
        parents=[common],
        help="Restart the background service.",
    )
    restart.add_argument("--timeout", type=float, default=30.0)

    subparsers.add_parser("status", parents=[common], help="Show current service status.")

    logs = subparsers.add_parser("logs", parents=[common], help="Show recent server logs.")
    logs.add_argument("-n", "--lines", type=int, default=200)

    subparsers.add_parser(
        "install-login",
        parents=[common],
        help="Install a LaunchAgent and start the service at login.",
    )
    subparsers.add_parser(
        "uninstall-login",
        parents=[common],
        help="Remove the LaunchAgent used for login startup.",
    )

    run_server = subparsers.add_parser(
        "run-server",
        parents=[common],
        help=argparse.SUPPRESS,
    )
    run_server.add_argument(
        "--foreground",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    return parser


def load_config_from_args(args: argparse.Namespace) -> ServiceConfig:
    config = ServiceConfig.load(args.config)
    if args.host is not None:
        config.host = args.host
    if args.port is not None:
        config.port = args.port
    if args.api_key is not None:
        config.api_key = args.api_key
    if args.model_root is not None:
        config.model_root = args.model_root
    if args.prompt_cache_dir is not None:
        config.prompt_cache_dir = args.prompt_cache_dir
    if args.preload_model is not None:
        config.preload_model = args.preload_model
    if args.python_executable is not None:
        config.python_executable = args.python_executable
    if args.workspace_dir is not None:
        config.workspace_dir = args.workspace_dir
    if args.launch_at_login is not None:
        config.launch_at_login = args.launch_at_login
    if args.start_server_on_launch is not None:
        config.start_server_on_launch = args.start_server_on_launch
    return config


def build_manager(args: argparse.Namespace) -> ServerManager:
    config = load_config_from_args(args)
    return ServerManager(
        config=config,
        config_path=args.config,
        pid_path=args.pid_path,
        log_path=args.log_path,
        user_launch_agent_path=args.user_launch_agent_path,
        managed_launch_agent_path=args.managed_launch_agent_path,
    )


def print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def command_start(args: argparse.Namespace) -> int:
    manager = build_manager(args)
    try:
        state = manager.start(timeout=args.timeout)
    except PortConflictError as exc:
        print_json(
            {
                "status": "error",
                "error": str(exc),
                "port": exc.port,
                "pid": exc.pid,
            }
        )
        return 1
    except Exception as exc:
        print_json({"status": "error", "error": str(exc)})
        return 1

    print_json(state)
    return 0


def command_stop(args: argparse.Namespace) -> int:
    manager = build_manager(args)
    try:
        state = manager.stop(timeout=args.timeout)
    except Exception as exc:
        print_json({"status": "error", "error": str(exc)})
        return 1
    print_json(state)
    return 0


def command_restart(args: argparse.Namespace) -> int:
    manager = build_manager(args)
    try:
        state = manager.restart(timeout=args.timeout)
    except PortConflictError as exc:
        print_json(
            {
                "status": "error",
                "error": str(exc),
                "port": exc.port,
                "pid": exc.pid,
            }
        )
        return 1
    except Exception as exc:
        print_json({"status": "error", "error": str(exc)})
        return 1
    print_json(state)
    return 0


def command_status(args: argparse.Namespace) -> int:
    manager = build_manager(args)
    print_json(manager.status())
    return 0


def command_logs(args: argparse.Namespace) -> int:
    manager = build_manager(args)
    content = manager.read_logs(lines=args.lines)
    if content:
        print(content)
    return 0


def command_install_login(args: argparse.Namespace) -> int:
    manager = build_manager(args)
    try:
        payload = manager.install_login()
    except Exception as exc:
        print_json({"status": "error", "error": str(exc)})
        return 1
    print_json(payload)
    return 0


def command_uninstall_login(args: argparse.Namespace) -> int:
    manager = build_manager(args)
    try:
        payload = manager.uninstall_login()
    except Exception as exc:
        print_json({"status": "error", "error": str(exc)})
        return 1
    print_json(payload)
    return 0


def build_api_argv(config: ServiceConfig) -> list[str]:
    argv = [
        "--host",
        config.host,
        "--port",
        str(config.port),
        "--model-root",
        config.model_root or str(DEFAULT_MODEL_ROOT),
        "--prompt-cache-dir",
        config.prompt_cache_dir or str(DEFAULT_PROMPT_CACHE_DIR),
        "--preload-model",
        config.preload_model or BASE_MODEL_ID,
    ]
    api_key = _str_or_none(config.api_key)
    if api_key:
        argv.extend(["--api-key", api_key])
    return argv


def command_run_server(args: argparse.Namespace) -> int:
    from qwen3_tts_api import main as api_main

    config = load_config_from_args(args)
    config_path = config.save(args.config)
    print(
        json.dumps(
            {
                "event": "starting-qwen3-tts-api",
                "api_url": config.api_url,
                "config_path": str(config_path),
                "model_root": config.model_root,
                "prompt_cache_dir": config.prompt_cache_dir,
                "preload_model": config.preload_model,
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    return api_main(build_api_argv(config))


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    handlers = {
        "start": command_start,
        "stop": command_stop,
        "restart": command_restart,
        "status": command_status,
        "logs": command_logs,
        "install-login": command_install_login,
        "uninstall-login": command_uninstall_login,
        "run-server": command_run_server,
    }
    return handlers[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
