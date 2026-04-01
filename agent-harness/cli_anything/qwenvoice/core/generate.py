"""
QwenVoice CLI - Audio Generation
Handles text-to-speech generation for all modes.
"""

from pathlib import Path
from typing import Dict, Any, Optional, List

from .client import QwenVoiceClient
from .models import ModelManager


class Generator:
    """Generates speech from text using QwenVoice."""

    def __init__(self, client: QwenVoiceClient, model_manager: ModelManager):
        """
        Initialize generator.

        Args:
            client: QwenVoice RPC client.
            model_manager: Model manager instance.
        """
        self.client = client
        self.model_manager = model_manager

    def generate(
        self,
        text: str,
        mode: str,
        output_path: Optional[str] = None,
        voice: Optional[str] = None,
        instruct: Optional[str] = None,
        ref_audio: Optional[str] = None,
        ref_text: Optional[str] = None,
        language: Optional[str] = None,
        temperature: float = 0.6,
        max_tokens: Optional[int] = None,
        benchmark: bool = False,
        auto_load_model: bool = True,
    ) -> Dict[str, Any]:
        """
        Generate audio from text.

        Args:
            text: Input text to synthesize.
            mode: Generation mode (custom, design, clone).
            output_path: Output audio file path.
            voice: Speaker name (required for custom mode).
            instruct: Voice description (required for design mode).
            ref_audio: Reference audio path (required for clone mode).
            ref_text: Reference transcript (optional for clone mode).
            language: Language code (default: auto).
            temperature: Sampling temperature (0.0-1.5).
            max_tokens: Maximum tokens to generate.
            benchmark: Enable benchmarking.
            auto_load_model: Auto-load correct model if needed.

        Returns:
            Generation result with output path and timing info.
        """
        # Validate parameters
        self._validate_generation_params(mode, voice, instruct, ref_audio)

        # Auto-load model if needed
        if auto_load_model:
            required_model_id = self.model_manager.get_model_for_mode(mode)
            if required_model_id and self.model_manager.current_model != required_model_id:
                self.model_manager.load_model(required_model_id, benchmark=benchmark)

        # Generate
        return self.client.generate(
            text=text,
            mode=mode,
            output_path=output_path,
            voice=voice,
            instruct=instruct,
            ref_audio=ref_audio,
            ref_text=ref_text,
            language=language,
            temperature=temperature,
            max_tokens=max_tokens,
            benchmark=benchmark,
        )

    def generate_custom(
        self,
        text: str,
        voice: str,
        instruct: Optional[str] = None,
        language: Optional[str] = None,
        temperature: float = 0.6,
        output_path: Optional[str] = None,
        benchmark: bool = False,
    ) -> Dict[str, Any]:
        """
        Generate using Custom Voice mode (built-in speakers).

        Args:
            text: Input text.
            voice: Speaker name (ryan, aiden, serena, vivian).
            instruct: Optional tone instruction.
            language: Language code.
            temperature: Sampling temperature.
            output_path: Output file path.
            benchmark: Enable benchmarking.

        Returns:
            Generation result.
        """
        return self.generate(
            text=text,
            mode="custom",
            voice=voice,
            instruct=instruct,
            language=language,
            temperature=temperature,
            output_path=output_path,
            benchmark=benchmark,
        )

    def generate_design(
        self,
        text: str,
        instruct: str,
        language: Optional[str] = None,
        temperature: float = 0.6,
        output_path: Optional[str] = None,
        benchmark: bool = False,
    ) -> Dict[str, Any]:
        """
        Generate using Voice Design mode (custom voice description).

        Args:
            text: Input text.
            instruct: Voice description (e.g., "Warm grandmotherly voice").
            language: Language code.
            temperature: Sampling temperature.
            output_path: Output file path.
            benchmark: Enable benchmarking.

        Returns:
            Generation result.
        """
        return self.generate(
            text=text,
            mode="design",
            instruct=instruct,
            language=language,
            temperature=temperature,
            output_path=output_path,
            benchmark=benchmark,
        )

    def generate_clone(
        self,
        text: str,
        ref_audio: str,
        ref_text: Optional[str] = None,
        language: Optional[str] = None,
        temperature: float = 0.6,
        output_path: Optional[str] = None,
        benchmark: bool = False,
    ) -> Dict[str, Any]:
        """
        Generate using Voice Cloning mode.

        Args:
            text: Input text.
            ref_audio: Reference audio file path.
            ref_text: Optional transcript for better accuracy.
            language: Language code.
            temperature: Sampling temperature.
            output_path: Output file path.
            benchmark: Enable benchmarking.

        Returns:
            Generation result.
        """
        return self.generate(
            text=text,
            mode="clone",
            ref_audio=ref_audio,
            ref_text=ref_text,
            language=language,
            temperature=temperature,
            output_path=output_path,
            benchmark=benchmark,
        )

    def generate_batch(
        self,
        items: List[Dict[str, Any]],
        mode: str = "clone",
        language: Optional[str] = None,
        temperature: float = 0.6,
        max_tokens: Optional[int] = None,
        benchmark: bool = False,
        output_dir: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Generate multiple audio clips in batch.

        Args:
            items: List of batch items. Each item should have:
                - text: Input text
                - ref_audio: Reference audio path
                - ref_text: Optional transcript
            mode: Generation mode (default: clone).
            language: Language code.
            temperature: Sampling temperature.
            max_tokens: Maximum tokens per item.
            benchmark: Enable benchmarking.
            output_dir: Output directory.

        Returns:
            Batch generation result.
        """
        # Validate items
        for i, item in enumerate(items):
            if "text" not in item:
                raise ValueError(f"Item {i} missing 'text' field")
            if "ref_audio" not in item:
                raise ValueError(f"Item {i} missing 'ref_audio' field")

        # Auto-load model if needed
        if mode == "clone":
            required_model_id = self.model_manager.get_model_for_mode(mode)
            if required_model_id and self.model_manager.current_model != required_model_id:
                self.model_manager.load_model(required_model_id, benchmark=benchmark)

        return self.client.generate_clone_batch(
            items=items,
            mode=mode,
            language=language,
            temperature=temperature,
            max_tokens=max_tokens,
            benchmark=benchmark,
            output_dir=output_dir,
        )

    def _validate_generation_params(
        self,
        mode: str,
        voice: Optional[str],
        instruct: Optional[str],
        ref_audio: Optional[str],
    ) -> None:
        """
        Validate generation parameters for the given mode.

        Raises:
            ValueError: If required parameters are missing.
        """
        if mode == "custom" and not voice:
            raise ValueError("Mode 'custom' requires --voice parameter")
        if mode == "design" and not instruct:
            raise ValueError("Mode 'design' requires --instruct parameter")
        if mode == "clone" and not ref_audio:
            raise ValueError("Mode 'clone' requires --ref-audio parameter")


def format_generation_result(result: Dict[str, Any], verbose: bool = True) -> str:
    """
    Format generation result as a readable string.

    Args:
        result: Generation result dictionary.
        verbose: Include detailed timing information.

    Returns:
        Formatted string.
    """
    lines = []

    if result.get("output_path"):
        lines.append(f"✓ Generated: {result['output_path']}")

    if result.get("duration_seconds"):
        duration = result["duration_seconds"]
        lines.append(f"  Duration: {duration:.2f}s")

    if verbose and result.get("timings"):
        timings = result["timings"]
        lines.append("  Timings:")

        for key, value in timings.items():
            if isinstance(value, (int, float)):
                if "ms" in key or key.endswith("_time"):
                    lines.append(f"    {key}: {value}ms")
                elif "seconds" in key or key.endswith("_sec"):
                    lines.append(f"    {key}: {value:.2f}s")

    if result.get("benchmark"):
        lines.append("  Benchmark data collected")

    return "\n".join(lines)
