from __future__ import annotations

import json
import os
import plistlib
import signal
import socket
import subprocess
import time
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional
from urllib import error, request

from qwen3_tts_paths import (
    APP_NAME,
    REPO_ROOT,
    get_app_support_dir,
    get_default_prompt_cache_dir,
    get_default_python_executable,
    get_default_workspace_dir,
)

ROOT_DIR = REPO_ROOT
LAUNCH_AGENT_LABEL = "com.gwh.qwen3tts.api"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 10088
DEFAULT_MODEL_ROOT = Path.home() / ".lmstudio/models/mlx-community"
DEFAULT_PROMPT_CACHE_DIR = get_default_prompt_cache_dir()


def get_config_path() -> Path:
    return get_app_support_dir() / "config.json"


def get_logs_dir() -> Path:
    path = get_app_support_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_log_path() -> Path:
    return get_logs_dir() / "server.log"


def get_run_dir() -> Path:
    path = get_app_support_dir() / "run"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_pid_path() -> Path:
    return get_run_dir() / "server.pid"


def get_managed_launch_agents_dir() -> Path:
    path = get_app_support_dir() / "LaunchAgents"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_managed_launch_agent_path() -> Path:
    return get_managed_launch_agents_dir() / f"{LAUNCH_AGENT_LABEL}.plist"


def get_user_launch_agent_dir() -> Path:
    path = Path.home() / "Library" / "LaunchAgents"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_user_launch_agent_path() -> Path:
    return get_user_launch_agent_dir() / f"{LAUNCH_AGENT_LABEL}.plist"


class ServerStatus(str, Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    ERROR = "error"
    UNRESPONSIVE = "unresponsive"


@dataclass
class ServiceConfig:
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    api_key: str = ""
    model_root: str = str(DEFAULT_MODEL_ROOT)
    prompt_cache_dir: str = str(DEFAULT_PROMPT_CACHE_DIR)
    preload_model: str = "Qwen3-TTS-12Hz-1.7B-Base-4bit"
    launch_at_login: bool = False
    start_server_on_launch: bool = False
    python_executable: str = get_default_python_executable()
    workspace_dir: str = str(get_default_workspace_dir())

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "ServiceConfig":
        config_path = (path or get_config_path()).expanduser().resolve()
        if config_path.exists():
            try:
                payload = json.loads(config_path.read_text(encoding="utf-8"))
                valid_keys = {field.name for field in cls.__dataclass_fields__.values()}
                filtered = {key: value for key, value in payload.items() if key in valid_keys}
                return cls(**filtered)
            except Exception:
                pass
        return cls()

    def save(self, path: Optional[Path] = None) -> Path:
        config_path = (path or get_config_path()).expanduser().resolve()
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            json.dumps(asdict(self), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return config_path

    @property
    def api_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    @property
    def health_url(self) -> str:
        return f"{self.api_url}/health"


def _http_get_json(url: str, timeout: float = 2.0) -> tuple[bool, Optional[dict[str, Any]], Optional[str]]:
    try:
        with request.urlopen(url, timeout=timeout) as response:
            body = response.read().decode("utf-8")
        return True, json.loads(body), None
    except error.HTTPError as exc:
        return False, None, f"http {exc.code}"
    except error.URLError as exc:
        return False, None, str(exc.reason)
    except Exception as exc:
        return False, None, str(exc)


def _pid_is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _find_port_owner_pid(port: int) -> Optional[int]:
    try:
        result = subprocess.run(
            ["lsof", "-ti", f":{port}", "-sTCP:LISTEN"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except Exception:
        return None

    if result.returncode == 0 and result.stdout.strip():
        try:
            return int(result.stdout.strip().splitlines()[0])
        except ValueError:
            return None
    return None


def _is_port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


class PortConflictError(RuntimeError):
    def __init__(self, port: int, pid: Optional[int] = None):
        self.port = port
        self.pid = pid
        if pid is None:
            super().__init__(f"port {port} is already in use")
        else:
            super().__init__(f"port {port} is already in use by pid {pid}")


class ServerManager:
    def __init__(
        self,
        config: Optional[ServiceConfig] = None,
        *,
        config_path: Optional[Path] = None,
        pid_path: Optional[Path] = None,
        log_path: Optional[Path] = None,
        user_launch_agent_path: Optional[Path] = None,
        managed_launch_agent_path: Optional[Path] = None,
        command_builder: Optional[Callable[[ServiceConfig, Path], list[str]]] = None,
    ) -> None:
        self.config = config or ServiceConfig.load(config_path)
        self.config_path = (config_path or get_config_path()).expanduser().resolve()
        self.pid_path = (pid_path or get_pid_path()).expanduser().resolve()
        self.log_path = (log_path or get_log_path()).expanduser().resolve()
        self.user_launch_agent_path = (
            user_launch_agent_path or get_user_launch_agent_path()
        ).expanduser().resolve()
        self.managed_launch_agent_path = (
            managed_launch_agent_path or get_managed_launch_agent_path()
        ).expanduser().resolve()
        self.command_builder = command_builder or self._default_command_builder
        self._process: Optional[subprocess.Popen[Any]] = None

    def save_config(self) -> Path:
        return self.config.save(self.config_path)

    def _default_command_builder(self, config: ServiceConfig, config_path: Path) -> list[str]:
        return [
            config.python_executable,
            str((ROOT_DIR / "qwen3_ttsctl.py").resolve()),
            "run-server",
            "--config",
            str(config_path),
        ]

    def read_pid(self) -> Optional[int]:
        if not self.pid_path.exists():
            return None
        try:
            return int(self.pid_path.read_text(encoding="utf-8").strip())
        except Exception:
            return None

    def write_pid(self, pid: int) -> None:
        self.pid_path.parent.mkdir(parents=True, exist_ok=True)
        self.pid_path.write_text(str(pid), encoding="utf-8")

    def remove_pid(self) -> None:
        if self.pid_path.exists():
            self.pid_path.unlink()

    def check_health(self) -> tuple[bool, Optional[dict[str, Any]], Optional[str]]:
        return _http_get_json(self.config.health_url, timeout=2.0)

    def status(self) -> dict[str, Any]:
        pid = self.read_pid()
        if (
            pid is not None
            and self._process is not None
            and self._process.pid == pid
            and self._process.poll() is not None
        ):
            try:
                self._process.wait(timeout=0)
            except Exception:
                pass
            self._process = None
            self.remove_pid()
            pid = None

        health_ok, health_payload, health_error = self.check_health()
        port_owner_pid = _find_port_owner_pid(self.config.port)

        if pid is not None and not _pid_is_running(pid):
            self.remove_pid()
            pid = None

        if pid is not None and health_ok:
            status = ServerStatus.RUNNING
        elif pid is not None and not health_ok:
            status = ServerStatus.UNRESPONSIVE
        elif health_ok:
            status = ServerStatus.RUNNING
            pid = port_owner_pid or pid
        else:
            status = ServerStatus.STOPPED

        return {
            "status": status.value,
            "pid": pid,
            "api_url": self.config.api_url,
            "loaded_model": None if not health_payload else health_payload.get("loaded_model"),
            "prompt_cache_count": None if not health_payload else health_payload.get("prompt_cache_count"),
            "log_path": str(self.log_path),
            "config_path": str(self.config_path),
            "launch_agent_path": str(self.user_launch_agent_path),
            "managed_launch_agent_path": str(self.managed_launch_agent_path),
            "launch_at_login": self.user_launch_agent_path.exists(),
            "health_error": health_error,
            "port_owner_pid": port_owner_pid,
        }

    def _wait_for_health(self, timeout: float = 30.0) -> tuple[bool, dict[str, Any]]:
        deadline = time.time() + timeout
        last_state = self.status()
        while time.time() < deadline:
            ok, payload, _ = self.check_health()
            last_state = self.status()
            if ok and payload is not None:
                return True, last_state
            time.sleep(0.5)
        return False, last_state

    def start(self, timeout: float = 30.0) -> dict[str, Any]:
        self.save_config()
        current = self.status()
        if current["status"] == ServerStatus.RUNNING.value:
            return current
        if current["status"] == ServerStatus.UNRESPONSIVE.value and current["pid"]:
            raise RuntimeError("managed server exists but is unresponsive; run restart or stop first")

        if _is_port_open(self.config.host, self.config.port):
            owner_pid = _find_port_owner_pid(self.config.port)
            raise PortConflictError(self.config.port, owner_pid)

        command = self.command_builder(self.config, self.config_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.log_path, "a", encoding="utf-8") as handle:
            handle.write(
                f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] starting qwen3-tts service: {' '.join(command)}\n"
            )
        with open(self.log_path, "a", encoding="utf-8") as log_handle:
            process = subprocess.Popen(
                command,
                cwd=self.config.workspace_dir,
                stdout=log_handle,
                stderr=log_handle,
                start_new_session=True,
            )
        self._process = process
        self.write_pid(process.pid)

        ok, state = self._wait_for_health(timeout=timeout)
        if ok:
            return state

        if process.poll() is not None:
            self.remove_pid()
            self._process = None
        raise RuntimeError(
            f"service failed to become healthy within {timeout:.0f}s; check logs at {self.log_path}"
        )

    def stop(self, timeout: float = 20.0) -> dict[str, Any]:
        pid = self.read_pid()
        if pid is None:
            return self.status()

        try:
            pgid = os.getpgid(pid)
        except OSError:
            self.remove_pid()
            self._process = None
            return self.status()

        os.killpg(pgid, signal.SIGTERM)
        deadline = time.time() + timeout
        while time.time() < deadline:
            if (
                self._process is not None
                and self._process.pid == pid
                and self._process.poll() is not None
            ):
                try:
                    self._process.wait(timeout=0)
                except Exception:
                    pass
                self.remove_pid()
                self._process = None
                return self.status()
            if not _pid_is_running(pid):
                self.remove_pid()
                if self._process is not None and self._process.pid == pid:
                    self._process = None
                return self.status()
            time.sleep(0.25)

        try:
            os.killpg(pgid, signal.SIGKILL)
        except OSError:
            pass

        time.sleep(0.5)
        self.remove_pid()
        if self._process is not None and self._process.pid == pid:
            self._process = None
        return self.status()

    def restart(self, timeout: float = 30.0) -> dict[str, Any]:
        self.stop()
        return self.start(timeout=timeout)

    def read_logs(self, lines: int = 200) -> str:
        if not self.log_path.exists():
            return ""
        content = self.log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(content[-lines:])

    def _build_launch_agent_plist(self) -> dict[str, Any]:
        self.save_config()
        program_arguments = self.command_builder(self.config, self.config_path)
        return {
            "Label": LAUNCH_AGENT_LABEL,
            "ProgramArguments": program_arguments,
            "WorkingDirectory": self.config.workspace_dir,
            "RunAtLoad": True,
            "StandardOutPath": str(self.log_path),
            "StandardErrorPath": str(self.log_path),
        }

    def install_login(self) -> dict[str, Any]:
        self.config.launch_at_login = True
        self.config.start_server_on_launch = True
        self.save_config()
        plist = self._build_launch_agent_plist()

        self.managed_launch_agent_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.managed_launch_agent_path, "wb") as handle:
            plistlib.dump(plist, handle)

        self.user_launch_agent_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.user_launch_agent_path, "wb") as handle:
            plistlib.dump(plist, handle)

        subprocess.run(
            ["launchctl", "unload", str(self.user_launch_agent_path)],
            capture_output=True,
            check=False,
        )
        subprocess.run(
            ["launchctl", "load", str(self.user_launch_agent_path)],
            capture_output=True,
            check=False,
        )

        return {
            "installed": True,
            "launch_agent_path": str(self.user_launch_agent_path),
            "managed_launch_agent_path": str(self.managed_launch_agent_path),
        }

    def uninstall_login(self) -> dict[str, Any]:
        self.config.launch_at_login = False
        self.config.start_server_on_launch = False
        self.save_config()

        subprocess.run(
            ["launchctl", "unload", str(self.user_launch_agent_path)],
            capture_output=True,
            check=False,
        )

        if self.user_launch_agent_path.exists():
            self.user_launch_agent_path.unlink()
        if self.managed_launch_agent_path.exists():
            self.managed_launch_agent_path.unlink()

        return {
            "installed": False,
            "launch_agent_path": str(self.user_launch_agent_path),
            "managed_launch_agent_path": str(self.managed_launch_agent_path),
        }
