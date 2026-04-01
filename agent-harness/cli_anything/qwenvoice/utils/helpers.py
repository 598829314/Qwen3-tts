"""
QwenVoice CLI - Utilities
Helper functions for file handling, output formatting, etc.
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional


def resolve_output_path(
    text: str,
    mode: str,
    output_dir: Optional[str] = None,
    voice: Optional[str] = None,
) -> str:
    """
    Resolve output file path for generation.

    Args:
        text: Input text (used for filename).
        mode: Generation mode.
        output_dir: Custom output directory.
        voice: Speaker name (for custom mode).

    Returns:
        Resolved absolute file path.
    """
    # Default output directory
    if output_dir is None:
        app_support = os.path.expanduser("~/Library/Application Support/QwenVoice")
        outputs_dir = os.path.join(app_support, "outputs")

        # Mode-specific subfolder
        mode_subfolder = {
            "custom": "CustomVoice",
            "design": "VoiceDesign",
            "clone": "Clones",
        }.get(mode, "")

        output_dir = os.path.join(outputs_dir, mode_subfolder)

    # Create output directory if needed
    os.makedirs(output_dir, exist_ok=True)

    # Generate filename from text
    safe_text = text[:20].strip()
    safe_text = "".join(c for c in safe_text if c.isalnum() or c in (" ", "-", "_"))
    safe_text = safe_text.replace(" ", "_")

    filename = f"{safe_text}.wav"
    return os.path.join(output_dir, filename)


def print_json(data: Any) -> None:
    """
    Print data as formatted JSON.

    Args:
        data: Data to print (must be JSON-serializable).
    """
    print(json.dumps(data, indent=2, ensure_ascii=False))


def read_batch_file(path: str) -> list:
    """
    Read batch generation file.

    Args:
        path: Path to JSON file with batch items.

    Returns:
        List of batch item dictionaries.

    Raises:
        FileNotFoundError: If file doesn't exist.
        ValueError: If file is not valid JSON or has wrong format.
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"Batch file not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in batch file: {e}")

    if not isinstance(data, list):
        raise ValueError("Batch file must contain a JSON array of items")

    return data


def validate_audio_file(path: str) -> bool:
    """
    Check if a file is a valid audio file.

    Args:
        path: File path.

    Returns:
        True if file exists and has audio extension.
    """
    valid_extensions = {".wav", ".mp3", ".m4a", ".aiff", ".flac", ".ogg"}
    return Path(path).exists() and Path(path).suffix.lower() in valid_extensions


def format_duration(seconds: float) -> str:
    """
    Format duration in seconds as readable string.

    Args:
        seconds: Duration in seconds.

    Returns:
        Formatted string (e.g., "1m 23s" or "45s").
    """
    if seconds >= 60:
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes}m {secs}s"
    else:
        return f"{int(seconds)}s"


def format_size(bytes_: int) -> str:
    """
    Format byte size as readable string.

    Args:
        bytes_: Size in bytes.

    Returns:
        Formatted string (e.g., "1.5 GB" or "500 MB").
    """
    for unit, divisor in [
        ("TB", 1024**4),
        ("GB", 1024**3),
        ("MB", 1024**2),
        ("KB", 1024**1),
    ]:
        if bytes_ >= divisor:
            return f"{bytes_ / divisor:.1f} {unit}"
    return f"{bytes_} B"


def get_default_app_support_dir() -> str:
    """
    Get default QwenVoice app support directory.

    Returns:
        Absolute path to app support directory.
    """
    return os.path.expanduser("~/Library/Application Support/QwenVoice")


def validate_temperature(value: float) -> bool:
    """
    Validate temperature parameter.

    Args:
        value: Temperature value.

    Returns:
        True if in valid range.
    """
    return 0.0 <= value <= 1.5


def validate_language(code: str) -> bool:
    """
    Validate language code.

    Args:
        code: Language code.

    Returns:
        True if code is supported.
    """
    valid_codes = {
        "auto", "en", "zh", "es", "fr", "de", "ja", "ko",
        "zh-CN", "zh-TW", "en-US", "en-GB",
    }
    return code.lower() in valid_codes


def sanitize_filename(name: str) -> str:
    """
    Sanitize a string for safe filename usage.

    Args:
        name: Input string.

    Returns:
        Sanitized filename.
    """
    # Remove unsafe characters
    safe = "".join(c for c in name if c.isalnum() or c in (" ", "-", "_"))
    # Replace spaces with underscores
    safe = safe.replace(" ", "_")
    # Limit length
    return safe[:50]


def print_progress(percent: int, message: str) -> None:
    """
    Print progress message to stderr.

    Args:
        percent: Progress percentage (0-100).
        message: Progress message.
    """
    print(f"[{percent}%] {message}", file=__import__("sys").stderr)
