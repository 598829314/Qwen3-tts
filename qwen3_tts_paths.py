from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional


APP_NAME = "Qwen3-TTS"
REPO_ROOT = Path(__file__).resolve().parent


def find_bundle_contents(start: Optional[Path] = None) -> Optional[Path]:
    current = (start or Path(__file__).resolve()).resolve()
    for parent in [current, *current.parents]:
        if parent.name == "Contents" and parent.parent.suffix == ".app":
            return parent
    return None


def get_bundle_contents_dir(start: Optional[Path] = None) -> Optional[Path]:
    return find_bundle_contents(start)


def get_bundle_resources_dir(start: Optional[Path] = None) -> Optional[Path]:
    contents = find_bundle_contents(start)
    if contents is None:
        return None
    return contents / "Resources"


def get_bundle_python_executable(start: Optional[Path] = None) -> Optional[Path]:
    contents = find_bundle_contents(start)
    if contents is None:
        return None

    candidates = [
        contents / "MacOS" / "python3",
        contents / "Frameworks" / "cpython-3.11" / "bin" / "python3",
        contents / "Python" / "cpython-3.11" / "bin" / "python3",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def get_default_workspace_dir() -> Path:
    return get_bundle_resources_dir() or REPO_ROOT


def get_app_support_dir() -> Path:
    path = Path.home() / "Library" / "Application Support" / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_default_prompt_cache_dir() -> Path:
    path = get_app_support_dir() / "cache" / "voice_clone_prompts"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_default_python_executable() -> str:
    bundled = get_bundle_python_executable()
    if bundled is not None:
        return str(bundled)

    default_venv_python = Path.home() / "venvs" / "tts" / "bin" / "python"
    if default_venv_python.exists():
        return str(default_venv_python)
    return sys.executable
