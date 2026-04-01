"""
QwenVoice CLI - JSON-RPC Client
Handles communication with the QwenVoice Python backend.
"""

import json
import subprocess
import os
from typing import Any, Dict, Optional, Union
from pathlib import Path


class QwenVoiceRPCError(Exception):
    """Exception raised when RPC call fails."""

    def __init__(self, code: int, message: str, data: Any = None):
        self.code = code
        self.message = message
        self.data = data
        super().__init__(f"RPC Error {code}: {message}")


class QwenVoiceClient:
    """
    JSON-RPC 2.0 client for QwenVoice backend.

    Communicates with the Python backend via stdin/stdout over JSON-RPC 2.0.
    """

    def __init__(self, server_path: Optional[str] = None, app_support_dir: Optional[str] = None):
        """
        Initialize the RPC client.

        Args:
            server_path: Path to server.py. If None, uses bundled backend.
            app_support_dir: Custom app support directory path.
        """
        self.server_path = server_path
        self.app_support_dir = app_support_dir
        self.process: Optional[subprocess.Popen] = None
        self.request_id = 0
        self._initialized = False

    def _get_server_path(self) -> str:
        """Resolve the server.py path."""
        if self.server_path:
            return self.server_path

        # Check if we're in a development environment
        # Look for bundled backend in Resources
        here = Path(__file__).parent.parent.parent
        backend_paths = [
            here / "Sources" / "Resources" / "backend" / "server.py",
            here / "agent-harness" / "cli_anything" / "qwenvoice" / "backend" / "server.py",
        ]

        for path in backend_paths:
            if path.exists():
                return str(path)

        raise FileNotFoundError(
            "Cannot find QwenVoice backend server.py. "
            "Provide server_path explicitly."
        )

    def start(self) -> None:
        """Start the backend server process."""
        server_path = self._get_server_path()

        if not os.path.exists(server_path):
            raise FileNotFoundError(f"Server not found at: {server_path}")

        self.process = subprocess.Popen(
            ["/usr/bin/env", "python3", server_path],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,  # Line buffered
        )

        # Initialize the backend
        self._initialize()

    def _initialize(self) -> None:
        """Initialize the backend with paths."""
        params = {}
        if self.app_support_dir:
            params["app_support_dir"] = self.app_support_dir

        result = self._call("init", params)
        self._initialized = True
        return result

    def stop(self) -> None:
        """Stop the backend server process."""
        if self.process:
            self.process.stdin.close()
            self.process.wait(timeout=5)
            self.process = None
            self._initialized = False

    def _call(self, method: str, params: Optional[Dict[str, Any]] = None) -> Any:
        """
        Make a JSON-RPC 2.0 call.

        Args:
            method: RPC method name.
            params: Method parameters.

        Returns:
            The result field from the RPC response.

        Raises:
            QwenVoiceRPCError: If the RPC call fails.
        """
        if not self.process:
            raise RuntimeError("Server not started. Call start() first.")

        self.request_id += 1
        request = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {},
            "id": self.request_id,
        }

        # Send request
        request_line = json.dumps(request) + "\n"
        self.process.stdin.write(request_line)
        self.process.stdin.flush()

        # Read response
        response_line = self.process.stdout.readline()
        if not response_line:
            raise RuntimeError("Server closed connection")

        try:
            response = json.loads(response_line.strip())
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Invalid JSON response: {response_line}") from e

        # Handle errors
        if "error" in response:
            error = response["error"]
            raise QwenVoiceRPCError(
                code=error.get("code", -1),
                message=error.get("message", "Unknown error"),
                data=error.get("data"),
            )

        return response.get("result")

    # Convenience methods for common RPC calls

    def ping(self) -> Dict[str, str]:
        """Check if the server is alive."""
        return self._call("ping")

    def load_model(
        self,
        model_id: Optional[str] = None,
        model_path: Optional[str] = None,
        benchmark: bool = False,
    ) -> Dict[str, Any]:
        """
        Load a model into memory.

        Args:
            model_id: Model ID (pro_custom, pro_design, pro_clone).
            model_path: Absolute path to model folder.
            benchmark: Enable benchmarking.

        Returns:
            Model loading result with status and metadata.
        """
        params = {}
        if model_id:
            params["model_id"] = model_id
        if model_path:
            params["model_path"] = model_path
        if benchmark:
            params["benchmark"] = True

        return self._call("load_model", params)

    def prewarm_model(
        self,
        mode: str,
        voice: Optional[str] = None,
        instruct: Optional[str] = None,
        ref_audio: Optional[str] = None,
        ref_text: Optional[str] = None,
        language: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Prewarm the model with a short generation.

        Args:
            mode: Generation mode (custom, design, clone).
            voice: Speaker name (for custom mode).
            instruct: Voice description (for design mode).
            ref_audio: Reference audio path (for clone mode).
            ref_text: Reference transcript (for clone mode).
            language: Language code.

        Returns:
            Prewarm result with timing information.
        """
        params = {"mode": mode}
        if voice:
            params["voice"] = voice
        if instruct:
            params["instruct"] = instruct
        if ref_audio:
            params["ref_audio"] = ref_audio
        if ref_text:
            params["ref_text"] = ref_text
        if language:
            params["language"] = language

        return self._call("prewarm_model", params)

    def unload_model(self) -> Dict[str, str]:
        """Unload the current model from memory."""
        return self._call("unload_model")

    def generate(
        self,
        text: str,
        mode: str,
        output_path: Optional[str] = None,
        model_id: Optional[str] = None,
        voice: Optional[str] = None,
        instruct: Optional[str] = None,
        ref_audio: Optional[str] = None,
        ref_text: Optional[str] = None,
        language: Optional[str] = None,
        temperature: float = 0.6,
        max_tokens: Optional[int] = None,
        stream: bool = False,
        streaming_interval: float = 2.0,
        benchmark: bool = False,
        benchmark_label: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Generate audio from text.

        Args:
            text: Input text to synthesize.
            mode: Generation mode (custom, design, clone).
            output_path: Output audio file path.
            model_id: Model ID (auto-switches if different from loaded).
            voice: Speaker name (required for custom mode).
            instruct: Voice description (required for design mode).
            ref_audio: Reference audio path (required for clone mode).
            ref_text: Reference transcript (optional for clone mode).
            language: Language code (default: auto).
            temperature: Sampling temperature (0.0-1.5).
            max_tokens: Maximum tokens to generate.
            stream: Enable streaming preview.
            streaming_interval: Seconds between stream chunks.
            benchmark: Enable benchmarking.
            benchmark_label: Custom benchmark label.

        Returns:
            Generation result with output path and timing info.
        """
        params = {"text": text}
        if mode:
            params["mode"] = mode
        if output_path:
            params["output_path"] = output_path
        if model_id:
            params["model_id"] = model_id
        if voice:
            params["voice"] = voice
        if instruct:
            params["instruct"] = instruct
        if ref_audio:
            params["ref_audio"] = ref_audio
        if ref_text is not None:
            params["ref_text"] = ref_text
        if language:
            params["language"] = language
        if temperature != 0.6:
            params["temperature"] = temperature
        if max_tokens is not None:
            params["max_tokens"] = max_tokens
        if stream:
            params["stream"] = True
        if streaming_interval != 2.0:
            params["streaming_interval"] = streaming_interval
        if benchmark:
            params["benchmark"] = True
        if benchmark_label:
            params["benchmark_label"] = benchmark_label

        return self._call("generate", params)

    def generate_clone_batch(
        self,
        items: list,
        mode: str = "clone",
        model_id: Optional[str] = None,
        language: Optional[str] = None,
        temperature: float = 0.6,
        max_tokens: Optional[int] = None,
        benchmark: bool = False,
        output_dir: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Generate multiple audio clips from a batch.

        Args:
            items: List of batch items, each with text, ref_audio, optional ref_text.
            mode: Generation mode (must be clone).
            model_id: Model ID.
            language: Language code.
            temperature: Sampling temperature.
            max_tokens: Maximum tokens per item.
            benchmark: Enable benchmarking.
            output_dir: Output directory for generated files.

        Returns:
            Batch generation result with list of outputs.
        """
        params = {
            "items": items,
            "mode": mode,
        }
        if model_id:
            params["model_id"] = model_id
        if language:
            params["language"] = language
        if temperature != 0.6:
            params["temperature"] = temperature
        if max_tokens is not None:
            params["max_tokens"] = max_tokens
        if benchmark:
            params["benchmark"] = True
        if output_dir:
            params["output_dir"] = output_dir

        return self._call("generate_clone_batch", params)

    def convert_audio(
        self,
        input_path: str,
        output_path: Optional[str] = None,
    ) -> Dict[str, str]:
        """
        Convert audio to 24kHz mono WAV.

        Args:
            input_path: Input audio file path.
            output_path: Output WAV path (optional).

        Returns:
            Conversion result with wav_path.
        """
        params = {"input_path": input_path}
        if output_path:
            params["output_path"] = output_path

        return self._call("convert_audio", params)

    def list_voices(self) -> list:
        """
        List enrolled voices.

        Returns:
            List of voice dictionaries with name, has_transcript, wav_path.
        """
        return self._call("list_voices")

    def enroll_voice(
        self,
        name: str,
        audio_path: str,
        transcript: str = "",
    ) -> Dict[str, Any]:
        """
        Enroll a new voice.

        Args:
            name: Voice name.
            audio_path: Path to audio file.
            transcript: Optional transcript.

        Returns:
            Enrollment result with name and wav_path.
        """
        params = {
            "name": name,
            "audio_path": audio_path,
            "transcript": transcript,
        }
        return self._call("enroll_voice", params)

    def delete_voice(self, name: str) -> Dict[str, Any]:
        """
        Delete an enrolled voice.

        Args:
            name: Voice name to delete.

        Returns:
            Deletion result with success status.
        """
        return self._call("delete_voice", {"name": name})

    def get_model_info(self) -> list:
        """
        Get information about available models.

        Returns:
            List of model info dictionaries.
        """
        return self._call("get_model_info")

    def get_speakers(self) -> Dict[str, list]:
        """
        Get speaker map.

        Returns:
            Dictionary mapping language groups to speaker lists.
        """
        return self._call("get_speakers")

    def prepare_clone_reference(
        self,
        ref_audio: str,
        ref_text: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Prepare a clone reference audio for faster repeated cloning.

        Args:
            ref_audio: Reference audio path.
            ref_text: Optional transcript.

        Returns:
            Preparation result with cache info.
        """
        params = {"ref_audio": ref_audio}
        if ref_text is not None:
            params["ref_text"] = ref_text

        return self._call("prepare_clone_reference", params)

    def prime_clone_reference(
        self,
        ref_audio: str,
        ref_text: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Prime a clone reference into memory.

        Args:
            ref_audio: Reference audio path.
            ref_text: Optional transcript.

        Returns:
            Prime result with status.
        """
        params = {"ref_audio": ref_audio}
        if ref_text is not None:
            params["ref_text"] = ref_text

        return self._call("prime_clone_reference", params)

    def __enter__(self):
        """Context manager entry."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.stop()
