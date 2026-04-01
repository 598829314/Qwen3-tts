"""
QwenVoice CLI - Model Management
Handles model loading, listing, and information.
"""

import json
from pathlib import Path
from typing import Dict, List, Optional, Any

from .client import QwenVoiceClient


class ModelManager:
    """Manages QwenVoice models."""

    def __init__(self, client: QwenVoiceClient):
        """
        Initialize model manager.

        Args:
            client: QwenVoice RPC client instance.
        """
        self.client = client
        self._current_model_id: Optional[str] = None

    def list_models(self) -> List[Dict[str, Any]]:
        """
        List all available models with download status.

        Returns:
            List of model info dictionaries.
        """
        return self.client.get_model_info()

    def get_model(self, model_id: str) -> Optional[Dict[str, Any]]:
        """
        Get information about a specific model.

        Args:
            model_id: Model identifier.

        Returns:
            Model info dict or None if not found.
        """
        models = self.list_models()
        for model in models:
            if model["id"] == model_id:
                return model
        return None

    def is_downloaded(self, model_id: str) -> bool:
        """
        Check if a model is downloaded.

        Args:
            model_id: Model identifier.

        Returns:
            True if model files exist.
        """
        model = self.get_model(model_id)
        return model.get("downloaded", False) if model else False

    def load_model(
        self,
        model_id: str,
        benchmark: bool = False,
    ) -> Dict[str, Any]:
        """
        Load a model into memory.

        Args:
            model_id: Model identifier (pro_custom, pro_design, pro_clone).
            benchmark: Enable benchmarking.

        Returns:
            Loading result with timing information.
        """
        result = self.client.load_model(model_id=model_id, benchmark=benchmark)
        self._current_model_id = model_id
        return result

    def unload_model(self) -> Dict[str, str]:
        """
        Unload the current model from memory.

        Returns:
            Unload result.
        """
        result = self.client.unload_model()
        self._current_model_id = None
        return result

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
        Prewarm the loaded model with a short generation.

        Args:
            mode: Generation mode (custom, design, clone).
            voice: Speaker name (for custom mode).
            instruct: Voice description (for design mode).
            ref_audio: Reference audio path (for clone mode).
            ref_text: Reference transcript (for clone mode).
            language: Language code.

        Returns:
            Prewarm result with timing breakdown.
        """
        return self.client.prewarm_model(
            mode=mode,
            voice=voice,
            instruct=instruct,
            ref_audio=ref_audio,
            ref_text=ref_text,
            language=language,
        )

    @property
    def current_model(self) -> Optional[str]:
        """Get the currently loaded model ID."""
        return self._current_model_id

    def get_model_for_mode(self, mode: str) -> Optional[str]:
        """
        Get the model ID for a given mode.

        Args:
            mode: Generation mode (custom, design, clone).

        Returns:
            Model ID or None if mode not found.
        """
        mode_to_model = {
            "custom": "pro_custom",
            "design": "pro_design",
            "clone": "pro_clone",
        }
        return mode_to_model.get(mode)

    def print_model_table(self, models: Optional[List[Dict[str, Any]]] = None) -> None:
        """
        Print a formatted table of models.

        Args:
            models: List of model info dicts (uses list_models() if None).
        """
        if models is None:
            models = self.list_models()

        if not models:
            print("No models found.")
            return

        # Print table header
        print(f"{'ID':<15} {'Name':<20} {'Mode':<10} {'Downloaded':<12} {'Size':<12}")
        print("-" * 80)

        # Print each model
        for model in models:
            size_gb = model.get("size_bytes", 0) / (1024**3)
            size_str = f"{size_gb:.2f} GB" if size_gb > 0 else "N/A"
            downloaded = "Yes" if model.get("downloaded") else "No"

            print(f"{model['id']:<15} {model['name']:<20} {model['mode']:<10} "
                  f"{downloaded:<12} {size_str:<12}")

    def validate_mode_for_model(self, mode: str, model_id: Optional[str] = None) -> bool:
        """
        Validate that a mode is compatible with a model.

        Args:
            mode: Generation mode.
            model_id: Model ID (uses current model if None).

        Returns:
            True if mode is compatible.
        """
        if model_id is None:
            model_id = self._current_model_id

        if not model_id:
            return False

        model = self.get_model(model_id)
        if not model:
            return False

        return model.get("mode") == mode


def format_model_info(model: Dict[str, Any]) -> str:
    """
    Format model info as a readable string.

    Args:
        model: Model info dictionary.

    Returns:
        Formatted string.
    """
    lines = [
        f"ID: {model['id']}",
        f"Name: {model['name']}",
        f"Mode: {model['mode']}",
        f"Tier: {model['tier']}",
        f"Downloaded: {'Yes' if model.get('downloaded') else 'No'}",
    ]

    if model.get("size_bytes"):
        size_gb = model["size_bytes"] / (1024**3)
        lines.append(f"Size: {size_gb:.2f} GB")

    if model.get("hugging_face_repo"):
        lines.append(f"Hugging Face: {model['hugging_face_repo']}")

    return "\n".join(lines)
