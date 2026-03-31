from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
import wave
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Optional

from qwen3_voice_clone import (
    DEFAULT_MODEL_PATH,
    Qwen3VoiceCloner,
    ROOT_DIR,
    load_ref_text,
    normalize_language,
    resolve_ref_text_path,
)


BASE_MODEL_ID = "Qwen3-TTS-12Hz-1.7B-Base-4bit"
DEFAULT_API_BASE_URL = "http://127.0.0.1:10088"
DEFAULT_OUTPUT_ROOT = ROOT_DIR / "outputs" / "clone-retest"
DEFAULT_REF_AUDIO = ROOT_DIR / "gwh_short.wav"
DEFAULT_REF_TEXT = ROOT_DIR / "gwh_short.txt"
DEFAULT_TARGET_TEXT = "今天的会议到此结束，谢谢大家。"


@dataclass
class WavStats:
    path: str
    channels: int
    sample_width: int
    frame_rate: int
    frame_count: int
    duration_sec: float
    size_bytes: int


@dataclass
class ValidationReport:
    ok: bool
    errors: list[str]
    warnings: list[str]


def inspect_wav(path: Path) -> WavStats:
    resolved = Path(path).expanduser().resolve()
    with wave.open(str(resolved), "rb") as handle:
        frame_count = handle.getnframes()
        frame_rate = handle.getframerate()
        duration = frame_count / frame_rate if frame_rate else 0.0
        return WavStats(
            path=str(resolved),
            channels=handle.getnchannels(),
            sample_width=handle.getsampwidth(),
            frame_rate=frame_rate,
            frame_count=frame_count,
            duration_sec=round(duration, 3),
            size_bytes=resolved.stat().st_size,
        )


def validate_reference_wav(stats: WavStats) -> ValidationReport:
    errors: list[str] = []
    warnings: list[str] = []

    if stats.channels != 1:
        errors.append(f"参考音频必须是单声道，当前是 {stats.channels} 声道。")
    if not (5.0 <= stats.duration_sec <= 8.0):
        errors.append(
            f"参考音频时长必须在 5 到 8 秒之间，当前是 {stats.duration_sec:.3f} 秒。"
        )
    if stats.sample_width != 2:
        warnings.append(f"参考音频不是 16-bit PCM，当前 sample_width={stats.sample_width} 字节。")
    if stats.frame_rate != 24000:
        warnings.append(
            f"参考音频采样率不是 24000 Hz，当前是 {stats.frame_rate} Hz。"
        )

    return ValidationReport(ok=not errors, errors=errors, warnings=warnings)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def ensure_output_root(path: Path) -> Path:
    resolved = Path(path).expanduser().resolve()
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def create_run_dir(output_root: Path) -> Path:
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    run_dir = ensure_output_root(output_root) / f"run-{timestamp}-{uuid.uuid4().hex[:8]}"
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_dir


def build_auth_headers(api_key: Optional[str]) -> dict[str, str]:
    headers: dict[str, str] = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def http_json(
    url: str,
    payload: dict[str, Any],
    *,
    api_key: Optional[str] = None,
) -> tuple[int, bytes]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        **build_auth_headers(api_key),
    }
    request = urllib.request.Request(url, data=data, method="POST", headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def encode_multipart_formdata(
    *,
    fields: dict[str, str],
    files: dict[str, tuple[str, bytes, str]],
) -> tuple[bytes, str]:
    boundary = f"----Qwen3CloneRetest{uuid.uuid4().hex}"
    body = bytearray()

    for name, value in fields.items():
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8")
        )
        body.extend(value.encode("utf-8"))
        body.extend(b"\r\n")

    for name, (filename, content, content_type) in files.items():
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(
            (
                f'Content-Disposition: form-data; name="{name}"; '
                f'filename="{filename}"\r\n'
            ).encode("utf-8")
        )
        body.extend(f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"))
        body.extend(content)
        body.extend(b"\r\n")

    body.extend(f"--{boundary}--\r\n".encode("utf-8"))
    return bytes(body), boundary


def http_multipart(
    url: str,
    *,
    fields: dict[str, str],
    files: dict[str, tuple[str, bytes, str]],
    api_key: Optional[str] = None,
) -> tuple[int, bytes]:
    data, boundary = encode_multipart_formdata(fields=fields, files=files)
    headers = {
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        **build_auth_headers(api_key),
    }
    request = urllib.request.Request(url, data=data, method="POST", headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def save_summary(run_dir: Path, summary: dict[str, Any]) -> Path:
    summary_path = run_dir / "summary.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return summary_path


def write_binary(path: Path, content: bytes) -> Path:
    path.write_bytes(content)
    return path


def play_if_requested(path: Path, enabled: bool) -> None:
    if not enabled:
        return
    subprocess.run(["afplay", str(path)], check=False)


def run_native_clone(
    *,
    model_path: Path,
    ref_audio: Path,
    ref_text: str,
    language: str,
    target_text: str,
    run_dir: Path,
    verbose: bool,
) -> Path:
    cloner = Qwen3VoiceCloner(
        model_path=model_path,
        output_dir=run_dir,
        file_prefix="native-clone",
    )
    result = cloner.generate_voice_clone(
        text=target_text,
        language=language,
        ref_audio=ref_audio,
        ref_text=ref_text,
        output_dir=run_dir,
        verbose=verbose,
    )
    return Path(str(result)).expanduser().resolve()


def run_api_clone(
    *,
    api_base_url: str,
    api_key: Optional[str],
    ref_audio: Path,
    ref_text: str,
    language: str,
    target_text: str,
    run_dir: Path,
) -> tuple[str, Path]:
    audio_bytes = ref_audio.read_bytes()
    content_type = mimetypes.guess_type(ref_audio.name)[0] or "audio/wav"
    status, prompt_body = http_multipart(
        f"{api_base_url.rstrip('/')}/v1/audio/voice-clone-prompts",
        api_key=api_key,
        fields={
            "ref_text": ref_text,
            "language": language,
        },
        files={
            "ref_audio": (ref_audio.name, audio_bytes, content_type),
        },
    )
    if status != 200:
        raise RuntimeError(
            f"创建 voice clone prompt 失败: HTTP {status}: {prompt_body.decode('utf-8', errors='replace')}"
        )

    prompt_payload = json.loads(prompt_body.decode("utf-8"))
    prompt_id = prompt_payload["prompt_id"]
    output_path = run_dir / "api-clone.wav"
    status, wav_bytes = http_json(
        f"{api_base_url.rstrip('/')}/v1/audio/speech",
        api_key=api_key,
        payload={
            "model": BASE_MODEL_ID,
            "input": target_text,
            "voice_clone_prompt_id": prompt_id,
            "lang_code": normalize_language(language),
            "response_format": "wav",
        },
    )
    if status != 200:
        raise RuntimeError(
            f"API clone 合成失败: HTTP {status}: {wav_bytes.decode('utf-8', errors='replace')}"
        )
    write_binary(output_path, wav_bytes)
    return prompt_id, output_path.resolve()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Retest Qwen3-TTS Base voice clone with a short reference."
    )
    parser.add_argument(
        "--phase",
        choices=("native", "api", "both"),
        default="native",
        help="native: 仅跑 mlx-audio 原生；api: 仅跑本地 API；both: 顺序执行两者。",
    )
    parser.add_argument("--model", type=str, default=str(DEFAULT_MODEL_PATH))
    parser.add_argument("--ref-audio", type=str, default=str(DEFAULT_REF_AUDIO))
    parser.add_argument("--ref-text-file", type=str, default=str(DEFAULT_REF_TEXT))
    parser.add_argument("--language", type=str, default="Chinese")
    parser.add_argument("--target-text", type=str, default=DEFAULT_TARGET_TEXT)
    parser.add_argument("--output-root", type=str, default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--api-base-url", type=str, default=DEFAULT_API_BASE_URL)
    parser.add_argument(
        "--api-key",
        type=str,
        default=os.environ.get("QWEN3_TTS_API_KEY"),
    )
    parser.add_argument("--play", action="store_true", help="生成后直接播放样本")
    parser.add_argument("--verbose", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()

    ref_audio = Path(args.ref_audio).expanduser().resolve()
    if not ref_audio.exists():
        print(f"参考音频不存在: {ref_audio}", file=sys.stderr)
        return 1

    ref_text_path = resolve_ref_text_path(args.ref_text_file)
    ref_text = load_ref_text(ref_text_path)
    language = normalize_language(args.language)
    wav_stats = inspect_wav(ref_audio)
    validation = validate_reference_wav(wav_stats)

    print(json.dumps(
        {
            "reference_audio": asdict(wav_stats),
            "reference_text_path": str(ref_text_path),
            "reference_text_chars": len(ref_text),
            "validation": asdict(validation),
        },
        ensure_ascii=False,
        indent=2,
    ))

    if not validation.ok:
        return 1

    run_dir = create_run_dir(Path(args.output_root))
    summary: dict[str, Any] = {
        "run_dir": str(run_dir),
        "reference_audio": asdict(wav_stats),
        "reference_text_path": str(ref_text_path),
        "reference_text_chars": len(ref_text),
        "language": language,
        "target_text": args.target_text,
        "phase": args.phase,
        "outputs": {},
    }

    if args.phase in ("native", "both"):
        native_path = run_native_clone(
            model_path=Path(args.model).expanduser().resolve(),
            ref_audio=ref_audio,
            ref_text=ref_text,
            language=language,
            target_text=args.target_text,
            run_dir=run_dir,
            verbose=args.verbose,
        )
        native_stats = inspect_wav(native_path)
        summary["outputs"]["native"] = {
            "path": str(native_path),
            "sha256": sha256_bytes(native_path.read_bytes()),
            "wav": asdict(native_stats),
        }
        print(f"native_clone={native_path}")
        play_if_requested(native_path, args.play)

    if args.phase in ("api", "both"):
        prompt_id, api_path = run_api_clone(
            api_base_url=args.api_base_url,
            api_key=args.api_key,
            ref_audio=ref_audio,
            ref_text=ref_text,
            language=language,
            target_text=args.target_text,
            run_dir=run_dir,
        )
        api_stats = inspect_wav(api_path)
        summary["outputs"]["api"] = {
            "path": str(api_path),
            "prompt_id": prompt_id,
            "sha256": sha256_bytes(api_path.read_bytes()),
            "wav": asdict(api_stats),
        }
        print(f"api_clone={api_path}")
        play_if_requested(api_path, args.play)

    summary_path = save_summary(run_dir, summary)
    print(f"summary={summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
