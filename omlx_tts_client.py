"""Client utilities for oMLX TTS over the OpenAI-compatible audio API."""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib import error, request
from uuid import uuid4


DEFAULT_BASE_URL = "http://127.0.0.1:10087"
DEFAULT_MODEL = "Qwen3-TTS-12Hz-1.7B-Base-4bit"
DEFAULT_OUTPUT_DIR = os.path.expanduser("~/Library/Application Support/openclaw/tts")


class OMLXTTSAPIError(RuntimeError):
    """Raised when the oMLX API returns a non-success response."""

    def __init__(self, status_code: int, message: str, body: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


@dataclass(frozen=True)
class OMLXTTSClient:
    """Thin HTTP client for the existing oMLX `/v1/audio/speech` API."""

    api_key: str
    base_url: str = DEFAULT_BASE_URL
    default_model: str = DEFAULT_MODEL
    timeout: float = 120.0

    def health(self) -> dict[str, Any]:
        """Return the oMLX health response."""
        return self._json_request("GET", "/health")

    def list_models(self) -> dict[str, Any]:
        """Return available models from oMLX."""
        return self._json_request("GET", "/v1/models")

    def synthesize(
        self,
        text: str,
        *,
        model: str | None = None,
        voice: str | None = None,
        speed: float | None = None,
        response_format: str = "wav",
    ) -> bytes:
        """Synthesize audio and return WAV bytes."""
        if not text:
            raise ValueError("text must not be empty")

        payload: dict[str, Any] = {
            "model": model or self.default_model,
            "input": text,
            "response_format": response_format,
        }
        if voice is not None:
            payload["voice"] = voice
        if speed is not None:
            payload["speed"] = speed

        return self._binary_request("POST", "/v1/audio/speech", payload)

    def save_wav(
        self,
        text: str,
        *,
        output_dir: str | os.PathLike[str] = DEFAULT_OUTPUT_DIR,
        file_name: str | None = None,
        file_prefix: str = "tts",
        **kwargs: Any,
    ) -> str:
        """Synthesize text and save the WAV response to disk."""
        audio = self.synthesize(text, **kwargs)
        target_dir = Path(output_dir).expanduser().resolve()
        target_dir.mkdir(parents=True, exist_ok=True)

        if file_name is None:
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            file_name = f"{file_prefix}-{stamp}-{uuid4().hex[:8]}.wav"
        elif not file_name.endswith(".wav"):
            file_name = f"{file_name}.wav"

        target_path = target_dir / file_name
        target_path.write_bytes(audio)
        return str(target_path)

    def _json_request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        req = self._build_request(method, path, data)
        try:
            with request.urlopen(req, timeout=self.timeout) as resp:
                body = resp.read().decode("utf-8")
        except error.HTTPError as exc:
            raise self._http_error(exc) from exc
        except error.URLError as exc:
            raise RuntimeError(
                f"failed to reach oMLX at {self.base_url}: {exc.reason}"
            ) from exc

        try:
            return json.loads(body)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"expected JSON response from {path}, got: {body[:200]}"
            ) from exc

    def _binary_request(self, method: str, path: str, payload: dict[str, Any]) -> bytes:
        data = json.dumps(payload).encode("utf-8")
        req = self._build_request(method, path, data)
        try:
            with request.urlopen(req, timeout=self.timeout) as resp:
                return resp.read()
        except error.HTTPError as exc:
            raise self._http_error(exc) from exc
        except error.URLError as exc:
            raise RuntimeError(
                f"failed to reach oMLX at {self.base_url}: {exc.reason}"
            ) from exc

    def _build_request(self, method: str, path: str, data: bytes | None) -> request.Request:
        req = request.Request(
            url=f"{self.base_url.rstrip('/')}{path}",
            data=data,
            method=method,
        )
        req.add_header("Authorization", f"Bearer {self.api_key}")
        if data is not None:
            req.add_header("Content-Type", "application/json")
        return req

    @staticmethod
    def _http_error(exc: error.HTTPError) -> OMLXTTSAPIError:
        raw_body = exc.read().decode("utf-8", errors="replace")
        message = raw_body
        try:
            parsed = json.loads(raw_body)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict):
            message = (
                parsed.get("error", {}).get("message")
                or parsed.get("detail")
                or raw_body
            )
        return OMLXTTSAPIError(exc.code, message, raw_body)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Call oMLX TTS through the existing /v1/audio/speech endpoint."
    )
    parser.add_argument("text", nargs="?", help="Text to synthesize.")
    parser.add_argument(
        "--output-dir",
        default=os.getenv("OMLX_TTS_OUTPUT_DIR", DEFAULT_OUTPUT_DIR),
        help=f"Directory for generated WAV files. Default: {DEFAULT_OUTPUT_DIR}",
    )
    parser.add_argument(
        "--output-name",
        help="Optional fixed output filename. If omitted, a unique filename is generated.",
    )
    parser.add_argument(
        "--file-prefix",
        default=os.getenv("OMLX_TTS_FILE_PREFIX", "tts"),
        help="Prefix for generated filenames. Default: tts",
    )
    parser.add_argument(
        "--base-url",
        default=os.getenv("OMLX_BASE_URL", DEFAULT_BASE_URL),
        help=f"oMLX base URL. Default: {DEFAULT_BASE_URL}",
    )
    parser.add_argument(
        "--api-key",
        default=os.getenv("OMLX_API_KEY"),
        help="API key for oMLX. Defaults to OMLX_API_KEY.",
    )
    parser.add_argument(
        "--model",
        default=os.getenv("OMLX_TTS_MODEL", DEFAULT_MODEL),
        help=f"TTS model name. Default: {DEFAULT_MODEL}",
    )
    parser.add_argument(
        "--voice",
        default=os.getenv("OMLX_TTS_VOICE"),
        help="Optional best-effort voice value.",
    )
    parser.add_argument("--speed", type=float, help="Optional speech speed multiplier.")
    parser.add_argument(
        "--health",
        action="store_true",
        help="Check /health and print the JSON response.",
    )
    parser.add_argument(
        "--list-models",
        action="store_true",
        help="Call /v1/models and print the JSON response.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if not args.api_key:
        parser.error("missing --api-key (or set OMLX_API_KEY)")

    client = OMLXTTSClient(
        api_key=args.api_key,
        base_url=args.base_url,
        default_model=args.model,
    )

    try:
        if args.health:
            print(json.dumps(client.health(), ensure_ascii=False, indent=2))
            return 0
        if args.list_models:
            print(json.dumps(client.list_models(), ensure_ascii=False, indent=2))
            return 0
        if not args.text:
            parser.error("text is required unless --health or --list-models is used")
        output_path = client.save_wav(
            args.text,
            output_dir=args.output_dir,
            file_name=args.output_name,
            file_prefix=args.file_prefix,
            voice=args.voice,
            speed=args.speed,
        )
        print(output_path)
        return 0
    except OMLXTTSAPIError as exc:
        print(f"oMLX API error ({exc.status_code}): {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # pragma: no cover - CLI safety net
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
