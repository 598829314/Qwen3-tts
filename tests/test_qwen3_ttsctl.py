import io
import json
import tempfile
import types
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import qwen3_ttsctl


class Qwen3TTSControlCliTest(unittest.TestCase):
    def test_status_outputs_required_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config_path = root / "config.json"
            pid_path = root / "server.pid"
            log_path = root / "server.log"
            user_plist = root / "user.plist"
            managed_plist = root / "managed.plist"

            buffer = io.StringIO()
            with redirect_stdout(buffer):
                exit_code = qwen3_ttsctl.main(
                    [
                        "status",
                        "--config",
                        str(config_path),
                        "--pid-path",
                        str(pid_path),
                        "--log-path",
                        str(log_path),
                        "--user-launch-agent-path",
                        str(user_plist),
                        "--managed-launch-agent-path",
                        str(managed_plist),
                    ]
                )

            self.assertEqual(exit_code, 0)
            payload = json.loads(buffer.getvalue())
            for key in (
                "status",
                "pid",
                "api_url",
                "loaded_model",
                "prompt_cache_count",
                "log_path",
            ):
                self.assertIn(key, payload)

    def test_run_server_builds_api_arguments_from_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config_path = root / "config.json"
            buffer = io.StringIO()
            fake_module = types.ModuleType("qwen3_tts_api")

            def fake_api_main(argv):
                fake_api_main.called_with = argv
                return 0

            fake_api_main.called_with = None
            fake_module.main = fake_api_main

            with (
                redirect_stdout(buffer),
                patch.dict("sys.modules", {"qwen3_tts_api": fake_module}),
            ):
                exit_code = qwen3_ttsctl.main(
                    [
                        "run-server",
                        "--config",
                        str(config_path),
                        "--host",
                        "127.0.0.1",
                        "--port",
                        "19088",
                        "--api-key",
                        "secret",
                        "--model-root",
                        str(root / "models"),
                        "--prompt-cache-dir",
                        str(root / "cache"),
                        "--preload-model",
                        "Qwen3-TTS-12Hz-1.7B-Base-4bit",
                    ]
                )

            self.assertEqual(exit_code, 0)
            api_argv = fake_api_main.called_with
            self.assertEqual(
                api_argv,
                [
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "19088",
                    "--model-root",
                    str(root / "models"),
                    "--prompt-cache-dir",
                    str(root / "cache"),
                    "--preload-model",
                    "Qwen3-TTS-12Hz-1.7B-Base-4bit",
                    "--api-key",
                    "secret",
                ],
            )
            self.assertTrue(config_path.exists())
            log_line = json.loads(buffer.getvalue().strip())
            self.assertEqual(log_line["event"], "starting-qwen3-tts-api")


if __name__ == "__main__":
    unittest.main()
