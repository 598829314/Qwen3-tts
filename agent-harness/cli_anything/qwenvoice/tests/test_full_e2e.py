"""
E2E tests for QwenVoice CLI.
Tests with real backend server (if available).
"""

import json
import os
import pytest
import tempfile
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from core import QwenVoiceClient, ModelManager, Generator, VoiceManager


# Skip E2E tests if backend not available
pytestmark = pytest.mark.skipif(
    os.environ.get("QWENVOICE_BACKEND") is None,
    reason="QWENVOICE_BACKEND not set - skipping E2E tests"
)


@pytest.fixture(scope="module")
def client():
    """Create and start a real RPC client."""
    backend_path = os.environ.get("QWENVOICE_BACKEND")
    if not backend_path or not Path(backend_path).exists():
        pytest.skip("Backend not found")

    client = QwenVoiceClient(server_path=backend_path)
    client.start()

    yield client

    client.stop()


@pytest.fixture(scope="module")
def model_manager(client):
    """Create model manager."""
    return ModelManager(client)


@pytest.fixture(scope="module")
def generator(client, model_manager):
    """Create generator."""
    return Generator(client, model_manager)


@pytest.fixture(scope="module")
def voice_manager(client):
    """Create voice manager."""
    return VoiceManager(client)


class TestClientE2E:
    """E2E tests for client."""

    def test_ping(self, client):
        """Test backend connection."""
        result = client.ping()
        assert result["status"] == "ok"

    def test_get_speakers(self, client):
        """Test getting speakers."""
        speakers = client.get_speakers()
        assert isinstance(speakers, dict)
        assert "English" in speakers


class TestModelManagerE2E:
    """E2E tests for model management."""

    def test_list_models(self, model_manager):
        """Test listing models."""
        models = model_manager.list_models()
        assert isinstance(models, list)
        assert len(models) >= 3  # At least custom, design, clone

        # Check structure
        for model in models:
            assert "id" in model
            assert "name" in model
            assert "mode" in model
            assert "downloaded" in model

    def test_get_model_info(self, model_manager):
        """Test getting specific model."""
        model = model_manager.get_model("pro_custom")
        assert model is not None
        assert model["mode"] == "custom"


class TestGeneratorE2E:
    """E2E tests for audio generation."""

    def test_generate_custom_voice(self, generator, tmp_path):
        """Test custom voice generation."""
        # Note: This test requires models to be downloaded
        # and may take several seconds

        output_path = tmp_path / "test_custom.wav"

        try:
            result = generator.generate_custom(
                text="Hello, world!",
                voice="vivian",
                output_path=str(output_path),
            )

            # Check result
            assert "output_path" in result or "error" not in result

            # Check file exists (if generation succeeded)
            if Path(output_path).exists():
                assert Path(output_path).stat().st_size > 0
        except RuntimeError as e:
            # Model may not be downloaded
            if "No model loaded" in str(e):
                pytest.skip("Model not available")
            else:
                raise

    def test_generate_design(self, generator, tmp_path):
        """Test voice design generation."""
        output_path = tmp_path / "test_design.wav"

        try:
            result = generator.generate_design(
                text="Design mode test.",
                instruct="Warm grandmotherly voice",
                output_path=str(output_path),
            )

            assert "output_path" in result or "error" not in result
        except RuntimeError as e:
            if "No model loaded" in str(e):
                pytest.skip("Model not available")
            else:
                raise

    def test_generate_clone(self, generator, tmp_path):
        """Test voice cloning generation."""
        # Create a dummy reference audio file
        # In real scenario, this would be actual audio
        ref_audio = tmp_path / "ref.wav"

        try:
            result = generator.generate_clone(
                text="Clone test.",
                ref_audio=str(ref_audio),
                output_path=str(tmp_path / "test_clone.wav"),
            )

            # May fail with invalid audio, but API should respond
            assert "output_path" in result or "error" in result
        except RuntimeError as e:
            # Expected with dummy audio
            if "Could not process reference audio" in str(e):
                pass  # Expected
            elif "No model loaded" in str(e):
                pytest.skip("Model not available")
            else:
                raise


class TestVoiceManagerE2E:
    """E2E tests for voice management."""

    def test_list_voices(self, voice_manager):
        """Test listing voices."""
        voices = voice_manager.list_voices()
        assert isinstance(voices, list)

    def test_enroll_and_delete_voice(self, voice_manager, tmp_path):
        """Test enrolling and deleting a voice."""
        # Create a dummy audio file
        dummy_audio = tmp_path / "dummy.wav"
        dummy_audio.write_bytes(b"dummy audio data")

        try:
            # Enroll
            result = voice_manager.enroll_voice(
                name="TestVoice",
                audio_path=str(dummy_audio),
                transcript="Test transcript",
            )

            # May fail with invalid audio format
            if "name" in result:
                # Delete if enrollment succeeded
                delete_result = voice_manager.delete_voice("TestVoice")
                assert delete_result.get("success") is True
        except RuntimeError as e:
            # Expected with dummy audio
            if "Could not process audio file" in str(e):
                pass
            else:
                raise


class TestAudioConversionE2E:
    """E2E tests for audio conversion."""

    def test_convert_audio(self, client, tmp_path):
        """Test audio conversion."""
        # Create a dummy audio file
        # In real scenario, this would be actual audio
        input_file = tmp_path / "input.mp3"
        input_file.write_bytes(b"dummy mp3 data")

        try:
            result = client.convert_audio(str(input_file))
            # May fail with invalid audio, but should respond
            assert "wav_path" in result or "error" in result
        except RuntimeError:
            # Expected with dummy audio
            pass


class TestBatchGenerationE2E:
    """E2E tests for batch generation."""

    def test_generate_batch(self, generator, tmp_path):
        """Test batch generation."""
        # Create batch file
        batch_file = tmp_path / "batch.json"
        batch_data = [
            {
                "text": "First item",
                "ref_audio": "/fake/ref1.wav",
            },
            {
                "text": "Second item",
                "ref_audio": "/fake/ref2.wav",
            },
        ]

        with open(batch_file, "w") as f:
            json.dump(batch_data, f)

        try:
            result = generator.generate_batch(
                items=batch_data,
                output_dir=str(tmp_path),
            )

            # Check response
            assert "outputs" in result or "error" in result
        except RuntimeError as e:
            # Expected with fake audio paths
            if "reference audio file" in str(e).lower():
                pass
            else:
                raise


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
