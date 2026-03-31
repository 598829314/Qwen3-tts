"""Probe candidate oMLX TTS models and report which ones actually synthesize WAV."""

from __future__ import annotations

import argparse
import json
import os
from typing import Iterable

from omlx_tts_client import OMLXTTSAPIError, OMLXTTSClient


DEFAULT_CANDIDATE_PATTERNS = ("kokoro", "chatterbox", "vibevoice")


def _matches_candidate(model_id: str, patterns: Iterable[str]) -> bool:
    lowered = model_id.lower()
    return any(pattern in lowered for pattern in patterns)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Probe oMLX TTS candidate models through /v1/audio/speech."
    )
    parser.add_argument(
        "--base-url",
        default=os.getenv("OMLX_BASE_URL", "http://127.0.0.1:10087"),
        help="oMLX base URL.",
    )
    parser.add_argument(
        "--api-key",
        default=os.getenv("OMLX_API_KEY"),
        help="oMLX API key.",
    )
    parser.add_argument(
        "--text",
        default="你好，这是一个测试。",
        help="Probe text.",
    )
    parser.add_argument(
        "--voice",
        default=os.getenv("OMLX_TTS_VOICE"),
        help="Optional voice to test for all candidates.",
    )
    parser.add_argument(
        "--model",
        action="append",
        default=[],
        help="Explicit model id to probe. Can be passed multiple times.",
    )
    parser.add_argument(
        "--candidate-pattern",
        action="append",
        default=[],
        help="Additional substring pattern used to select candidate models from /v1/models.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if not args.api_key:
        parser.error("missing --api-key (or set OMLX_API_KEY)")

    client = OMLXTTSClient(api_key=args.api_key, base_url=args.base_url)
    patterns = tuple(args.candidate_pattern) or DEFAULT_CANDIDATE_PATTERNS
    models_payload = client.list_models()
    discovered = [item["id"] for item in models_payload.get("data", [])]

    requested = list(dict.fromkeys(args.model))
    if not requested:
        requested = [model for model in discovered if _matches_candidate(model, patterns)]

    report = {
        "base_url": args.base_url,
        "patterns": list(patterns),
        "requested_models": requested,
        "results": [],
    }

    for model in requested:
        entry = {"model": model, "voice": args.voice}
        if model not in discovered:
            entry["status"] = "missing"
            entry["error"] = "model not found in /v1/models"
            report["results"].append(entry)
            continue
        try:
            audio = client.synthesize(args.text, model=model, voice=args.voice)
            entry["status"] = "ok"
            entry["bytes"] = len(audio)
            entry["riff"] = audio[:4].decode("ascii", errors="replace")
        except OMLXTTSAPIError as exc:
            entry["status"] = "error"
            entry["http_status"] = exc.status_code
            entry["error"] = str(exc)
        except Exception as exc:  # pragma: no cover - CLI safety net
            entry["status"] = "error"
            entry["error"] = str(exc)
        report["results"].append(entry)

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
