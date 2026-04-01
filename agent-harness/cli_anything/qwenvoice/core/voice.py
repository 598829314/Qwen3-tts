"""
QwenVoice CLI - Voice Management
Handles voice enrollment, listing, and deletion.
"""

from pathlib import Path
from typing import Dict, List, Any, Optional

from .client import QwenVoiceClient


class VoiceManager:
    """Manages enrolled voices for voice cloning."""

    def __init__(self, client: QwenVoiceClient):
        """
        Initialize voice manager.

        Args:
            client: QwenVoice RPC client.
        """
        self.client = client

    def list_voices(self) -> List[Dict[str, Any]]:
        """
        List all enrolled voices.

        Returns:
            List of voice dictionaries with name, has_transcript, wav_path.
        """
        return self.client.list_voices()

    def enroll_voice(
        self,
        name: str,
        audio_path: str,
        transcript: str = "",
        convert: bool = True,
    ) -> Dict[str, Any]:
        """
        Enroll a new voice for cloning.

        Args:
            name: Voice name (will be sanitized).
            audio_path: Path to audio file (WAV, MP3, etc.).
            transcript: Optional transcript for better accuracy.
            convert: Auto-convert audio to required format.

        Returns:
            Enrollment result with sanitized name and wav path.
        """
        # Validate input
        if not name:
            raise ValueError("Voice name cannot be empty")

        if not audio_path or not Path(audio_path).exists():
            raise ValueError(f"Audio file not found: {audio_path}")

        # Optionally convert audio first
        if convert:
            converted = self.client.convert_audio(audio_path)
            audio_path = converted["wav_path"]

        # Enroll the voice
        return self.client.enroll_voice(
            name=name,
            audio_path=audio_path,
            transcript=transcript,
        )

    def delete_voice(self, name: str) -> Dict[str, Any]:
        """
        Delete an enrolled voice.

        Args:
            name: Voice name to delete.

        Returns:
            Deletion result.
        """
        if not name:
            raise ValueError("Voice name cannot be empty")

        return self.client.delete_voice(name=name)

    def get_voice_path(self, name: str) -> Optional[str]:
        """
        Get the file path for an enrolled voice.

        Args:
            name: Voice name.

        Returns:
            WAV file path or None if not found.
        """
        voices = self.list_voices()
        for voice in voices:
            if voice["name"] == name:
                return voice.get("wav_path")
        return None

    def voice_exists(self, name: str) -> bool:
        """
        Check if a voice is enrolled.

        Args:
            name: Voice name.

        Returns:
            True if voice exists.
        """
        return self.get_voice_path(name) is not None

    def prepare_reference(
        self,
        ref_audio: str,
        ref_text: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Prepare a clone reference for faster repeated cloning.

        This pre-processes the reference audio and caches the context.

        Args:
            ref_audio: Reference audio path.
            ref_text: Optional transcript.

        Returns:
            Preparation result.
        """
        if not ref_audio or not Path(ref_audio).exists():
            raise ValueError(f"Reference audio not found: {ref_audio}")

        return self.client.prepare_clone_reference(
            ref_audio=ref_audio,
            ref_text=ref_text,
        )

    def prime_reference(
        self,
        ref_audio: str,
        ref_text: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Prime a clone reference into memory.

        Use this before generating multiple clips with the same reference.

        Args:
            ref_audio: Reference audio path.
            ref_text: Optional transcript.

        Returns:
            Prime result.
        """
        if not ref_audio or not Path(ref_audio).exists():
            raise ValueError(f"Reference audio not found: {ref_audio}")

        return self.client.prime_clone_reference(
            ref_audio=ref_audio,
            ref_text=ref_text,
        )

    def print_voice_table(self, voices: Optional[List[Dict[str, Any]]] = None) -> None:
        """
        Print a formatted table of enrolled voices.

        Args:
            voices: List of voice dicts (uses list_voices() if None).
        """
        if voices is None:
            voices = self.list_voices()

        if not voices:
            print("No enrolled voices.")
            return

        # Print table header
        print(f"{'Name':<30} {'Has Transcript':<15} {'Path'}")
        print("-" * 80)

        # Print each voice
        for voice in voices:
            has_transcript = "Yes" if voice.get("has_transcript") else "No"
            path = voice.get("wav_path", "")

            print(f"{voice['name']:<30} {has_transcript:<15} {path}")


def format_voice_info(voice: Dict[str, Any]) -> str:
    """
    Format voice info as a readable string.

    Args:
        voice: Voice info dictionary.

    Returns:
        Formatted string.
    """
    lines = [
        f"Name: {voice['name']}",
        f"Has Transcript: {'Yes' if voice.get('has_transcript') else 'No'}",
    ]

    if voice.get("wav_path"):
        lines.append(f"Path: {voice['wav_path']}")

    return "\n".join(lines)
