import json
import plistlib
import socket
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from qwen3_tts_service import PortConflictError, ServerManager, ServiceConfig


FAKE_SERVER_SOURCE = """
import argparse
import json
import signal
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


parser = argparse.ArgumentParser()
parser.add_argument("--host", required=True)
parser.add_argument("--port", type=int, required=True)
parser.add_argument("--model", required=True)
args = parser.parse_args()


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            body = json.dumps({
                "status": "ok",
                "loaded_model": args.model,
                "prompt_cache_count": 0,
            }).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(404)
        self.end_headers()

    def log_message(self, format, *args):
        return


server = ThreadingHTTPServer((args.host, args.port), Handler)


def _stop(*_args):
    server.server_close()
    sys.exit(0)


signal.signal(signal.SIGTERM, _stop)
signal.signal(signal.SIGINT, _stop)
server.serve_forever()
"""


SLEEPER_SOURCE = """
import signal
import sys
import time

running = True


def _stop(*_args):
    sys.exit(0)


signal.signal(signal.SIGTERM, _stop)
signal.signal(signal.SIGINT, _stop)

while running:
    time.sleep(0.5)
"""


def get_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def make_command_builder(script_path: Path):
    def _builder(config: ServiceConfig, _config_path: Path) -> list[str]:
        return [
            sys.executable,
            str(script_path),
            "--host",
            config.host,
            "--port",
            str(config.port),
            "--model",
            config.preload_model,
        ]

    return _builder


class Qwen3TTSServiceManagerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmpdir.name)
        self.config_path = self.root / "config.json"
        self.pid_path = self.root / "run" / "server.pid"
        self.log_path = self.root / "logs" / "server.log"
        self.user_launch_agent_path = self.root / "LaunchAgents" / "user.plist"
        self.managed_launch_agent_path = self.root / "LaunchAgents" / "managed.plist"
        self.fake_server_path = self.root / "fake_server.py"
        self.fake_server_path.write_text(textwrap.dedent(FAKE_SERVER_SOURCE), encoding="utf-8")
        self.sleeper_path = self.root / "sleeper.py"
        self.sleeper_path.write_text(textwrap.dedent(SLEEPER_SOURCE), encoding="utf-8")

    def tearDown(self) -> None:
        try:
            manager = self.build_manager(port=get_free_port())
            manager.stop(timeout=1)
        except Exception:
            pass
        self.tmpdir.cleanup()

    def build_manager(self, *, port: int, command_builder=None) -> ServerManager:
        config = ServiceConfig(
            host="127.0.0.1",
            port=port,
            api_key="",
            model_root=str(self.root / "models"),
            prompt_cache_dir=str(self.root / "cache"),
            preload_model="Qwen3-TTS-12Hz-1.7B-Base-4bit",
            launch_at_login=False,
            start_server_on_launch=False,
            python_executable=sys.executable,
            workspace_dir=str(self.root),
        )
        return ServerManager(
            config=config,
            config_path=self.config_path,
            pid_path=self.pid_path,
            log_path=self.log_path,
            user_launch_agent_path=self.user_launch_agent_path,
            managed_launch_agent_path=self.managed_launch_agent_path,
            command_builder=command_builder or make_command_builder(self.fake_server_path),
        )

    def test_start_status_restart_stop_cycle(self) -> None:
        manager = self.build_manager(port=get_free_port())

        started = manager.start(timeout=10)
        self.assertEqual(started["status"], "running")
        first_pid = started["pid"]
        self.assertIsInstance(first_pid, int)
        self.assertIn("starting qwen3-tts service", self.log_path.read_text(encoding="utf-8"))

        status = manager.status()
        self.assertEqual(status["status"], "running")
        self.assertEqual(status["loaded_model"], "Qwen3-TTS-12Hz-1.7B-Base-4bit")

        restarted = manager.restart(timeout=10)
        self.assertEqual(restarted["status"], "running")
        self.assertNotEqual(restarted["pid"], first_pid)

        stopped = manager.stop(timeout=5)
        self.assertEqual(stopped["status"], "stopped")
        self.assertFalse(self.pid_path.exists())

    def test_status_reports_unresponsive_when_pid_exists_without_health(self) -> None:
        config = ServiceConfig(
            host="127.0.0.1",
            port=get_free_port(),
            workspace_dir=str(self.root),
            python_executable=sys.executable,
        )
        manager = ServerManager(
            config=config,
            config_path=self.config_path,
            pid_path=self.pid_path,
            log_path=self.log_path,
            user_launch_agent_path=self.user_launch_agent_path,
            managed_launch_agent_path=self.managed_launch_agent_path,
            command_builder=lambda *_args: [sys.executable, str(self.sleeper_path)],
        )

        sleeper = subprocess.Popen(
            [sys.executable, str(self.sleeper_path)],
            start_new_session=True,
        )
        self.addCleanup(lambda: sleeper.poll() is None and sleeper.terminate())
        manager.write_pid(sleeper.pid)
        time.sleep(0.2)

        status = manager.status()
        self.assertEqual(status["status"], "unresponsive")
        self.assertEqual(status["pid"], sleeper.pid)

        sleeper.terminate()
        sleeper.wait(timeout=5)

    def test_start_raises_port_conflict(self) -> None:
        port = get_free_port()
        conflict = subprocess.Popen(
            [sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
            cwd=str(self.root),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        self.addCleanup(lambda: conflict.poll() is None and conflict.terminate())
        time.sleep(0.5)

        manager = self.build_manager(port=port)
        with self.assertRaises(PortConflictError):
            manager.start(timeout=3)

        conflict.terminate()
        conflict.wait(timeout=5)

    def test_install_and_uninstall_login_write_plist(self) -> None:
        config = ServiceConfig(
            host="127.0.0.1",
            port=get_free_port(),
            api_key="",
            model_root=str(self.root / "models"),
            prompt_cache_dir=str(self.root / "cache"),
            preload_model="Qwen3-TTS-12Hz-1.7B-Base-4bit",
            launch_at_login=False,
            start_server_on_launch=False,
            python_executable=sys.executable,
            workspace_dir=str(self.root),
        )
        manager = ServerManager(
            config=config,
            config_path=self.config_path,
            pid_path=self.pid_path,
            log_path=self.log_path,
            user_launch_agent_path=self.user_launch_agent_path,
            managed_launch_agent_path=self.managed_launch_agent_path,
        )

        with patch("qwen3_tts_service.subprocess.run") as run_mock:
            installed = manager.install_login()
            self.assertTrue(installed["installed"])
            self.assertTrue(self.user_launch_agent_path.exists())
            self.assertTrue(self.managed_launch_agent_path.exists())

            with open(self.user_launch_agent_path, "rb") as handle:
                user_payload = json.loads(json.dumps(plistlib.load(handle)))
            self.assertEqual(user_payload["Label"], "com.gwh.qwen3tts.api")
            self.assertIn("run-server", user_payload["ProgramArguments"])
            self.assertEqual(user_payload["WorkingDirectory"], str(self.root))
            self.assertTrue(run_mock.called)

        with patch("qwen3_tts_service.subprocess.run") as run_mock:
            removed = manager.uninstall_login()
            self.assertFalse(removed["installed"])
            self.assertFalse(self.user_launch_agent_path.exists())
            self.assertFalse(self.managed_launch_agent_path.exists())
            self.assertTrue(run_mock.called)


if __name__ == "__main__":
    unittest.main()
