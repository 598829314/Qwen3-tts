"""
Unit tests for QwenVoice CLI core modules.
Uses mocks and synthetic data - no external dependencies.
"""

import json
import pytest
from unittest.mock import Mock, patch, MagicMock, call
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.client import QwenVoiceClient, QwenVoiceRPCError
from core.models import ModelManager, format_model_info
from core.generate import Generator, format_generation_result
from core.voice import VoiceManager, format_voice_info


class TestQwenVoiceClient:
    """Test JSON-RPC client."""

    def test_init(self):
        """Test client initialization."""
        client = QwenVoiceClient(server_path="/fake/server.py")
        assert client.server_path == "/fake/server.py"
        assert client.process is None
        assert client.request_id == 0

    @patch("subprocess.Popen")
    @patch("os.path.exists")
    def test_start_server(self, mock_exists, mock_popen):
        """Test starting the server."""
        mock_exists.return_value = True
        mock_process = MagicMock()
        mock_process.stdout.readline.return_value = '{"jsonrpc": "2.0", "result": {"status": "ok"}, "id": 1}\n'
        mock_popen.return_value = mock_process

        client = QwenVoiceClient(server_path="/fake/server.py")
        client.start()

        assert client.process is not None
        mock_popen.assert_called_once()

    @patch("subprocess.Popen")
    def test_call_success(self, mock_popen):
        """Test successful RPC call."""
        mock_process = MagicMock()
        mock_process.stdout.readline.return_value = '{"jsonrpc": "2.0", "result": {"data": "test"}, "id": 1}\n'
        mock_popen.return_value = mock_process

        client = QwenVoiceClient(server_path="/fake/server.py")
        client.process = mock_process

        result = client._call("test_method", {"param": "value"})

        assert result == {"data": "test"}

    @patch("subprocess.Popen")
    def test_call_error(self, mock_popen):
        """Test RPC error handling."""
        mock_process = MagicMock()
        mock_process.stdout.readline.return_value = '{"jsonrpc": "2.0", "error": {"code": -32601, "message": "Method not found"}, "id": 1}\n'
        mock_popen.return_value = mock_process

        client = QwenVoiceClient(server_path="/fake/server.py")
        client.process = mock_process

        with pytest.raises(QwenVoiceRPCError):
            client._call("unknown_method")

    @patch("subprocess.Popen")
    def test_ping(self, mock_popen):
        """Test ping command."""
        mock_process = MagicMock()
        mock_process.stdout.readline.return_value = '{"jsonrpc": "2.0", "result": {"status": "ok"}, "id": 1}\n'
        mock_popen.return_value = mock_process

        client = QwenVoiceClient(server_path="/fake/server.py")
        client.process = mock_process

        result = client.ping()
        assert result == {"status": "ok"}

    @patch("subprocess.Popen")
    def test_load_model(self, mock_popen):
        """Test load_model command."""
        mock_process = MagicMock()
        mock_process.stdout.readline.return_value = '{"jsonrpc": "2.0", "result": {"model_id": "pro_custom"}, "id": 1}\n'
        mock_popen.return_value = mock_process

        client = QwenVoiceClient(server_path="/fake/server.py")
        client.process = mock_process

        result = client.load_model(model_id="pro_custom")
        assert result["model_id"] == "pro_custom"


class TestModelManager:
    """Test model management."""

    def setup_method(self):
        """Setup test fixtures."""
        self.mock_client = MagicMock()
        self.manager = ModelManager(self.mock_client)

    def test_list_models(self):
        """Test listing models."""
        self.mock_client.get_model_info.return_value = [
            {
                "id": "pro_custom",
                "name": "Custom Voice",
                "mode": "custom",
                "downloaded": True,
            }
        ]

        models = self.manager.list_models()
        assert len(models) == 1
        assert models[0]["id"] == "pro_custom"

    def test_get_model(self):
        """Test getting specific model."""
        self.mock_client.get_model_info.return_value = [
            {
                "id": "pro_custom",
                "name": "Custom Voice",
                "mode": "custom",
                "downloaded": True,
            },
            {
                "id": "pro_design",
                "name": "Voice Design",
                "mode": "design",
                "downloaded": False,
            },
        ]

        model = self.manager.get_model("pro_custom")
        assert model["id"] == "pro_custom"

        assert self.manager.get_model("unknown") is None

    def test_is_downloaded(self):
        """Test checking if model is downloaded."""
        self.mock_client.get_model_info.return_value = [
            {"id": "pro_custom", "downloaded": True},
            {"id": "pro_design", "downloaded": False},
        ]

        assert self.manager.is_downloaded("pro_custom") is True
        assert self.manager.is_downloaded("pro_design") is False

    def test_load_model(self):
        """Test loading a model."""
        self.mock_client.load_model.return_value = {"model_id": "pro_custom"}
        self.mock_client.get_model_info.return_value = [
            {"id": "pro_custom", "mode": "custom"}
        ]

        result = self.manager.load_model("pro_custom")
        assert result["model_id"] == "pro_custom"
        assert self.manager.current_model == "pro_custom"

    def test_unload_model(self):
        """Test unloading a model."""
        self.mock_client.unload_model.return_value = {"status": "ok"}

        # Load then unload
        self.mock_client.load_model.return_value = {"model_id": "pro_custom"}
        self.manager.load_model("pro_custom")

        result = self.manager.unload_model()
        assert result["status"] == "ok"
        assert self.manager.current_model is None

    def test_get_model_for_mode(self):
        """Test mapping mode to model ID."""
        assert self.manager.get_model_for_mode("custom") == "pro_custom"
        assert self.manager.get_model_for_mode("design") == "pro_design"
        assert self.manager.get_model_for_mode("clone") == "pro_clone"
        assert self.manager.get_model_for_mode("unknown") is None


class TestGenerator:
    """Test audio generation."""

    def setup_method(self):
        """Setup test fixtures."""
        self.mock_client = MagicMock()
        self.mock_model_manager = MagicMock()
        self.generator = Generator(self.mock_client, self.mock_model_manager)

    def test_generate_custom_voice(self):
        """Test generating with custom voice mode."""
        self.mock_model_manager.current_model = "pro_custom"
        self.mock_client.generate.return_value = {
            "output_path": "/path/to/output.wav",
            "duration_seconds": 2.5,
        }

        result = self.generator.generate_custom(
            text="Hello, world!",
            voice="vivian",
            output_path="/tmp/test.wav",
        )

        assert result["output_path"] == "/path/to/output.wav"
        self.mock_client.generate.assert_called_once()

    def test_generate_design(self):
        """Test generating with design mode."""
        self.mock_model_manager.current_model = "pro_design"
        self.mock_client.generate.return_value = {
            "output_path": "/path/to/output.wav",
        }

        result = self.generator.generate_design(
            text="Test text",
            instruct="Warm voice",
        )

        assert result["output_path"] == "/path/to/output.wav"

    def test_generate_clone(self):
        """Test generating with clone mode."""
        self.mock_model_manager.current_model = "pro_clone"
        self.mock_client.generate.return_value = {
            "output_path": "/path/to/clone.wav",
        }

        result = self.generator.generate_clone(
            text="Cloned text",
            ref_audio="/path/to/ref.wav",
        )

        assert result["output_path"] == "/path/to/clone.wav"

    def test_validate_params_custom(self):
        """Test parameter validation for custom mode."""
        # Should raise error without voice
        with pytest.raises(ValueError, match="Mode 'custom' requires --voice"):
            self.generator._validate_generation_params(
                mode="custom",
                voice=None,
                instruct=None,
                ref_audio=None,
            )

        # Should not raise with voice
        self.generator._validate_generation_params(
            mode="custom",
            voice="vivian",
            instruct=None,
            ref_audio=None,
        )

    def test_validate_params_design(self):
        """Test parameter validation for design mode."""
        with pytest.raises(ValueError, match="Mode 'design' requires --instruct"):
            self.generator._validate_generation_params(
                mode="design",
                voice=None,
                instruct=None,
                ref_audio=None,
            )

    def test_validate_params_clone(self):
        """Test parameter validation for clone mode."""
        with pytest.raises(ValueError, match="Mode 'clone' requires --ref-audio"):
            self.generator._validate_generation_params(
                mode="clone",
                voice=None,
                instruct=None,
                ref_audio=None,
            )

    def test_generate_batch(self):
        """Test batch generation."""
        items = [
            {"text": "First", "ref_audio": "/ref1.wav"},
            {"text": "Second", "ref_audio": "/ref2.wav"},
        ]

        self.mock_client.generate_clone_batch.return_value = {
            "outputs": ["/out1.wav", "/out2.wav"],
        }

        result = self.generator.generate_batch(items)

        assert len(result["outputs"]) == 2


class TestVoiceManager:
    """Test voice management."""

    def setup_method(self):
        """Setup test fixtures."""
        self.mock_client = MagicMock()
        self.manager = VoiceManager(self.mock_client)

    def test_list_voices(self):
        """Test listing voices."""
        self.mock_client.list_voices.return_value = [
            {
                "name": "Voice1",
                "has_transcript": True,
                "wav_path": "/path/to/voice1.wav",
            }
        ]

        voices = self.manager.list_voices()
        assert len(voices) == 1
        assert voices[0]["name"] == "Voice1"

    @patch("pathlib.Path.exists")
    def test_enroll_voice(self, mock_exists):
        """Test enrolling a voice."""
        mock_exists.return_value = True
        self.mock_client.convert_audio.return_value = {
            "wav_path": "/converted.wav",
        }
        self.mock_client.enroll_voice.return_value = {
            "name": "MyVoice",
            "wav_path": "/path/to/MyVoice.wav",
        }

        result = self.manager.enroll_voice(
            name="MyVoice",
            audio_path="/input.mp3",
            transcript="Test transcript",
        )

        assert result["name"] == "MyVoice"

    def test_delete_voice(self):
        """Test deleting a voice."""
        self.mock_client.delete_voice.return_value = {
            "success": True,
        }

        result = self.manager.delete_voice("MyVoice")
        assert result["success"] is True

    def test_voice_exists(self):
        """Test checking if voice exists."""
        self.mock_client.list_voices.return_value = [
            {"name": "Voice1", "wav_path": "/path1.wav"},
            {"name": "Voice2", "wav_path": "/path2.wav"},
        ]

        assert self.manager.voice_exists("Voice1") is True
        assert self.manager.voice_exists("Unknown") is False

    def test_get_voice_path(self):
        """Test getting voice path."""
        self.mock_client.list_voices.return_value = [
            {"name": "Voice1", "wav_path": "/path1.wav"},
        ]

        path = self.manager.get_voice_path("Voice1")
        assert path == "/path1.wav"

        path = self.manager.get_voice_path("Unknown")
        assert path is None


class TestFormatters:
    """Test output formatting functions."""

    def test_format_model_info(self):
        """Test model info formatting."""
        model = {
            "id": "pro_custom",
            "name": "Custom Voice",
            "mode": "custom",
            "tier": "pro",
            "downloaded": True,
            "size_bytes": 5368709120,  # 5 GB
        }

        text = format_model_info(model)
        assert "ID: pro_custom" in text
        assert "Name: Custom Voice" in text
        assert "Mode: custom" in text
        assert "5.00 GB" in text

    def test_format_generation_result(self):
        """Test generation result formatting."""
        result = {
            "output_path": "/path/to/output.wav",
            "duration_seconds": 2.45,
            "timings": {
                "generation_ms": 1500,
                "write_ms": 100,
            },
        }

        text = format_generation_result(result, verbose=True)
        assert "/path/to/output.wav" in text
        assert "2.45s" in text
        assert "1500ms" in text

    def test_format_voice_info(self):
        """Test voice info formatting."""
        voice = {
            "name": "MyVoice",
            "has_transcript": True,
            "wav_path": "/path/to/voice.wav",
        }

        text = format_voice_info(voice)
        assert "Name: MyVoice" in text
        assert "Yes" in text
        assert "/path/to/voice.wav" in text


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
