from __future__ import annotations

import argparse
import gc
import hashlib
import io
import json
import os
import shutil
import threading
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

from fastapi import APIRouter, Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from pydantic import BaseModel, Field

from qwen3_tts_paths import REPO_ROOT, get_default_prompt_cache_dir

ROOT_DIR = REPO_ROOT
SERVICE_VERSION = "0.1.0"
BASE_MODEL_ID = "Qwen3-TTS-12Hz-1.7B-Base-4bit"
VOICE_DESIGN_MODEL_ID = "Qwen3-TTS-12Hz-1.7B-VoiceDesign-8bit"
DEFAULT_MODEL_ROOT = Path.home() / ".lmstudio/models/mlx-community"
DEFAULT_PROMPT_CACHE_DIR = get_default_prompt_cache_dir()
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 10088

SUPPORTED_MODELS: dict[str, dict[str, Any]] = {
    BASE_MODEL_ID: {
        "kind": "base",
        "capabilities": ["tts", "voice", "voice_clone"],
    },
    VOICE_DESIGN_MODEL_ID: {
        "kind": "voice_design",
        "capabilities": ["tts", "voice_design"],
    },
}


def normalize_language(language: Optional[str]) -> str:
    if not language:
        return "auto"

    value = language.strip().lower()
    mapping = {
        "zh": "chinese",
        "zh-cn": "chinese",
        "chinese": "chinese",
        "中文": "chinese",
        "普通话": "chinese",
        "mandarin": "chinese",
        "en": "english",
        "en-us": "english",
        "english": "english",
        "英文": "english",
        "auto": "auto",
    }
    return mapping.get(value, value)


def mlx_to_numpy(value: Any, np_module: Any) -> Any:
    if hasattr(value, "tolist") and not hasattr(value, "__array__"):
        return np_module.array(value.tolist())
    return np_module.asarray(value)


def apply_speed(audio: Any, speed: float, np_module: Any) -> Any:
    if speed is None or abs(speed - 1.0) < 1e-6:
        return audio
    if speed <= 0:
        raise ValueError("speed must be greater than 0")

    array = mlx_to_numpy(audio, np_module).astype(np_module.float32).reshape(-1)
    if array.size <= 1:
        return array

    new_length = max(1, int(round(array.shape[0] / speed)))
    if new_length == array.shape[0]:
        return array

    old_positions = np_module.arange(array.shape[0], dtype=np_module.float32)
    new_positions = np_module.linspace(
        0, array.shape[0] - 1, new_length, dtype=np_module.float32
    )
    return np_module.interp(new_positions, old_positions, array).astype(np_module.float32)


def encode_wav_bytes(audio: Any, sample_rate: int, audio_write: Callable[..., None], np_module: Any) -> bytes:
    buffer = io.BytesIO()
    audio_write(buffer, mlx_to_numpy(audio, np_module), sample_rate, format="wav")
    return buffer.getvalue()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sanitize_filename(name: Optional[str], default_suffix: str = ".wav") -> str:
    raw = Path(name or f"reference{default_suffix}").name
    stem = "".join(ch if ch.isalnum() or ch in ("-", "_", ".") else "_" for ch in raw)
    if not stem:
        stem = f"reference{default_suffix}"
    if "." not in stem:
        stem = f"{stem}{default_suffix}"
    return stem


class ModelNotFoundError(RuntimeError):
    pass


class PromptNotFoundError(RuntimeError):
    pass


@dataclass(frozen=True)
class StoredVoiceClonePrompt:
    prompt_id: str
    model_id: str
    language: str
    ref_text: str
    audio_sha256: str
    created_at: float
    ref_audio_filename: str
    ref_codes: Any
    ref_text_ids: Any
    speaker_embed: Any | None


class SpeechRequestModel(BaseModel):
    model: str
    input: str = Field(min_length=1)
    response_format: str = "wav"
    speed: float = 1.0
    lang_code: str = "auto"
    temperature: float = 0.7
    top_p: float = 0.95
    top_k: int = 40
    repetition_penalty: float = 1.0
    max_tokens: int = 1200
    verbose: bool = False
    voice: str | None = None
    instruct: str | None = None
    voice_clone_prompt_id: str | None = None


class ModelManager:
    def __init__(
        self,
        model_root: Path = DEFAULT_MODEL_ROOT,
        preload_model_id: str = BASE_MODEL_ID,
        loader: Optional[Callable[[Path], Any]] = None,
        cache_clearer: Optional[Callable[[], None]] = None,
        gc_collector: Optional[Callable[[], None]] = None,
    ) -> None:
        self.model_root = Path(model_root).expanduser().resolve()
        self.preload_model_id = preload_model_id
        self._loader = loader
        self._cache_clearer = cache_clearer
        self._gc_collector = gc_collector or gc.collect
        self._lock = threading.RLock()
        self._loaded_model: Any = None
        self._loaded_model_id: Optional[str] = None
        self._load_counts = {model_id: 0 for model_id in SUPPORTED_MODELS}
        self._backend_loaded = False

    def _ensure_backend(self) -> None:
        if self._backend_loaded:
            return
        if self._loader is None or self._cache_clearer is None:
            import mlx.core as mx
            from mlx_audio.tts.utils import load_model

            if self._loader is None:
                self._loader = load_model
            if self._cache_clearer is None:
                self._cache_clearer = mx.clear_cache
        self._backend_loaded = True

    def model_path(self, model_id: str) -> Path:
        if model_id not in SUPPORTED_MODELS:
            raise ModelNotFoundError(f"unsupported model: {model_id}")
        path = self.model_root / model_id
        if not path.exists():
            raise ModelNotFoundError(f"model not found on disk: {path}")
        return path

    def list_models(self) -> list[dict[str, Any]]:
        models = []
        for model_id, info in SUPPORTED_MODELS.items():
            models.append(
                {
                    "id": model_id,
                    "object": "model",
                    "owned_by": "local",
                    "kind": info["kind"],
                    "capabilities": info["capabilities"],
                    "available": (self.model_root / model_id).exists(),
                }
            )
        return models

    @property
    def loaded_model_id(self) -> Optional[str]:
        return self._loaded_model_id

    def load_counts(self) -> dict[str, int]:
        return dict(self._load_counts)

    def preload(self) -> None:
        self.get_model(self.preload_model_id)

    def _unload_locked(self) -> None:
        if self._loaded_model is None:
            return
        self._loaded_model = None
        self._loaded_model_id = None
        self._gc_collector()
        if self._cache_clearer is not None:
            self._cache_clearer()

    def get_model(self, model_id: str) -> Any:
        with self._lock:
            if self._loaded_model is not None and self._loaded_model_id == model_id:
                return self._loaded_model

            self._ensure_backend()
            path = self.model_path(model_id)
            self._unload_locked()
            assert self._loader is not None
            self._loaded_model = self._loader(path)
            self._loaded_model_id = model_id
            self._load_counts[model_id] += 1
            return self._loaded_model


def build_base_clone_artifacts(
    model: Any,
    ref_audio_path: Path,
    ref_text: str,
    language: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    import mlx.core as mx
    import numpy as np
    from mlx_audio.utils import load_audio

    ref_audio_value = load_audio(str(ref_audio_path), sample_rate=model.sample_rate)
    audio_for_spk = ref_audio_value
    if ref_audio_value.ndim == 1:
        ref_audio_batch = ref_audio_value[None, None, :]
    elif ref_audio_value.ndim == 2:
        ref_audio_batch = ref_audio_value[None, :]
    else:
        ref_audio_batch = ref_audio_value

    ref_codes = model.speech_tokenizer.encode(ref_audio_batch)
    mx.eval(ref_codes)

    ref_chat = f"<|im_start|>assistant\n{ref_text}<|im_end|>\n"
    ref_ids = mx.array(model.tokenizer.encode(ref_chat))[None, :]
    ref_text_ids = ref_ids[:, 3:-2]

    speaker_embed = None
    if model.speaker_encoder is not None:
        speaker_embed = model.extract_speaker_embedding(audio_for_spk)
        mx.eval(speaker_embed)

    artifacts = {
        "ref_codes": mlx_to_numpy(ref_codes, np).astype(np.int32),
        "ref_text_ids": mlx_to_numpy(ref_text_ids, np).astype(np.int32),
        "speaker_embed": (
            None
            if speaker_embed is None
            else mlx_to_numpy(speaker_embed, np).astype(np.float32)
        ),
    }
    metadata = {
        "language": normalize_language(language),
    }
    return artifacts, metadata


class VoiceClonePromptStore:
    def __init__(
        self,
        cache_dir: Path = DEFAULT_PROMPT_CACHE_DIR,
        artifact_builder: Callable[[Any, Path, str, str], tuple[dict[str, Any], dict[str, Any]]] = build_base_clone_artifacts,
    ) -> None:
        self.cache_dir = Path(cache_dir).expanduser().resolve()
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._artifact_builder = artifact_builder

    def _prompt_dir(self, prompt_id: str) -> Path:
        return self.cache_dir / prompt_id

    def count(self) -> int:
        return sum(1 for path in self.cache_dir.iterdir() if path.is_dir())

    def create(
        self,
        *,
        model: Any,
        ref_audio_bytes: bytes,
        ref_audio_filename: Optional[str],
        ref_text: str,
        language: str,
    ) -> dict[str, Any]:
        import numpy as np

        prompt_id = uuid.uuid4().hex
        prompt_dir = self._prompt_dir(prompt_id)
        prompt_dir.mkdir(parents=True, exist_ok=False)

        audio_name = sanitize_filename(ref_audio_filename)
        ref_audio_path = prompt_dir / audio_name
        ref_audio_path.write_bytes(ref_audio_bytes)

        artifacts, derived_metadata = self._artifact_builder(
            model,
            ref_audio_path,
            ref_text,
            language,
        )

        np.savez_compressed(
            prompt_dir / "artifacts.npz",
            ref_codes=artifacts["ref_codes"],
            ref_text_ids=artifacts["ref_text_ids"],
            speaker_embed=(
                np.array([], dtype=np.float32)
                if artifacts["speaker_embed"] is None
                else artifacts["speaker_embed"]
            ),
            has_speaker_embed=np.array(
                [artifacts["speaker_embed"] is not None], dtype=np.uint8
            ),
        )

        metadata = {
            "prompt_id": prompt_id,
            "model_id": BASE_MODEL_ID,
            "language": derived_metadata["language"],
            "ref_text": ref_text,
            "audio_sha256": sha256_bytes(ref_audio_bytes),
            "created_at": time.time(),
            "ref_audio_filename": audio_name,
        }
        (prompt_dir / "metadata.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return metadata

    def load(self, prompt_id: str) -> StoredVoiceClonePrompt:
        import numpy as np

        prompt_dir = self._prompt_dir(prompt_id)
        metadata_path = prompt_dir / "metadata.json"
        artifacts_path = prompt_dir / "artifacts.npz"

        if not metadata_path.exists() or not artifacts_path.exists():
            raise PromptNotFoundError(f"voice clone prompt not found: {prompt_id}")

        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        artifacts = np.load(artifacts_path, allow_pickle=False)
        has_speaker_embed = bool(artifacts["has_speaker_embed"][0])
        speaker_embed = artifacts["speaker_embed"] if has_speaker_embed else None
        return StoredVoiceClonePrompt(
            prompt_id=metadata["prompt_id"],
            model_id=metadata["model_id"],
            language=metadata["language"],
            ref_text=metadata["ref_text"],
            audio_sha256=metadata["audio_sha256"],
            created_at=float(metadata["created_at"]),
            ref_audio_filename=metadata["ref_audio_filename"],
            ref_codes=artifacts["ref_codes"],
            ref_text_ids=artifacts["ref_text_ids"],
            speaker_embed=speaker_embed,
        )

    def delete(self, prompt_id: str) -> bool:
        prompt_dir = self._prompt_dir(prompt_id)
        if not prompt_dir.exists():
            return False
        shutil.rmtree(prompt_dir)
        return True


def generate_base_clone_audio(
    model: Any,
    text: str,
    prompt: StoredVoiceClonePrompt,
    *,
    language: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: int = 1200,
    top_k: int = 40,
    top_p: float = 0.95,
    repetition_penalty: float = 1.5,
    verbose: bool = False,
) -> Any:
    import mlx.core as mx
    import numpy as np

    config = model.config.talker_config
    normalized_language = normalize_language(language or prompt.language)

    ref_codes = mx.array(prompt.ref_codes)
    ref_text_ids = mx.array(prompt.ref_text_ids)
    speaker_embed = None
    if prompt.speaker_embed is not None and np.asarray(prompt.speaker_embed).size > 0:
        speaker_embed = mx.array(prompt.speaker_embed)

    target_chat = (
        f"<|im_start|>assistant\n{text}<|im_end|>\n<|im_start|>assistant\n"
    )
    target_ids = mx.array(model.tokenizer.encode(target_chat))[None, :]
    text_ids = target_ids[:, 3:-5]

    tts_tokens = mx.array(
        [
            [
                model.config.tts_bos_token_id,
                model.config.tts_eos_token_id,
                model.config.tts_pad_token_id,
            ]
        ]
    )
    tts_embeds = model.talker.text_projection(
        model.talker.get_text_embeddings()(tts_tokens)
    )
    tts_bos_embed = tts_embeds[:, 0:1, :]
    tts_eos_embed = tts_embeds[:, 1:2, :]
    tts_pad_embed = tts_embeds[:, 2:3, :]

    combined_text_ids = mx.concatenate([ref_text_ids, text_ids], axis=1)
    text_embed = model.talker.text_projection(
        model.talker.get_text_embeddings()(combined_text_ids)
    )
    text_embed = mx.concatenate([text_embed, tts_eos_embed], axis=1)
    text_lens = text_embed.shape[1]

    ref_codec_embed = model.talker.get_input_embeddings()(ref_codes[:, 0, :])
    for idx in range(config.num_code_groups - 1):
        ref_codec_embed = (
            ref_codec_embed
            + model.talker.code_predictor.codec_embedding[idx](ref_codes[:, idx + 1, :])
        )

    codec_bos_embed = model.talker.get_input_embeddings()(
        mx.array([[config.codec_bos_id]])
    )
    codec_embed_icl = mx.concatenate([codec_bos_embed, ref_codec_embed], axis=1)
    codec_lens = codec_embed_icl.shape[1]

    codec_pad_embed = model.talker.get_input_embeddings()(
        mx.array([[config.codec_pad_id]])
    )
    text_with_codec_pad = text_embed + mx.broadcast_to(
        codec_pad_embed, (1, text_lens, codec_pad_embed.shape[-1])
    )
    codec_with_text_pad = codec_embed_icl + mx.broadcast_to(
        tts_pad_embed, (1, codec_lens, tts_pad_embed.shape[-1])
    )
    icl_input_embed = mx.concatenate([text_with_codec_pad, codec_with_text_pad], axis=1)
    trailing_text_hidden = tts_pad_embed

    language_id = None
    if normalized_language != "auto" and config.codec_language_id:
        language_id = config.codec_language_id.get(normalized_language)

    if language_id is None:
        codec_prefill = [
            config.codec_nothink_id,
            config.codec_think_bos_id,
            config.codec_think_eos_id,
        ]
    else:
        codec_prefill = [
            config.codec_think_id,
            config.codec_think_bos_id,
            language_id,
            config.codec_think_eos_id,
        ]

    codec_prefix_embed = model.talker.get_input_embeddings()(mx.array([codec_prefill]))
    codec_prefix_suffix = model.talker.get_input_embeddings()(
        mx.array([[config.codec_pad_id, config.codec_bos_id]])
    )
    if speaker_embed is not None:
        codec_prefix_embed = mx.concatenate(
            [
                codec_prefix_embed,
                speaker_embed.reshape(1, 1, -1),
                codec_prefix_suffix,
            ],
            axis=1,
        )
    else:
        codec_prefix_embed = mx.concatenate(
            [codec_prefix_embed, codec_prefix_suffix],
            axis=1,
        )

    role_embed = model.talker.text_projection(
        model.talker.get_text_embeddings()(target_ids[:, :3])
    )
    pad_count = codec_prefix_embed.shape[1] - 2
    pad_embeds = mx.broadcast_to(tts_pad_embed, (1, pad_count, tts_pad_embed.shape[-1]))
    combined_prefix = mx.concatenate([pad_embeds, tts_bos_embed], axis=1)
    combined_prefix = combined_prefix + codec_prefix_embed[:, :-1, :]
    input_embeds = mx.concatenate([role_embed, combined_prefix, icl_input_embed], axis=1)

    target_token_count = len(model.tokenizer.encode(text))
    effective_max_tokens = min(max_tokens, max(75, target_token_count * 6))

    cache = model.talker.make_cache()
    code_cache = model.talker.code_predictor.make_cache()
    generated_codes = []
    generated_token_ids = []
    eos_token_id = config.codec_eos_token_id
    suppress_tokens = [
        idx
        for idx in range(config.vocab_size - 1024, config.vocab_size)
        if idx != eos_token_id
    ]
    trailing_idx = 0

    for step in range(effective_max_tokens):
        logits, hidden = model.talker(input_embeds, cache=cache)
        next_token = model._sample_token(
            logits,
            temperature=temperature,
            top_k=top_k,
            top_p=top_p,
            repetition_penalty=repetition_penalty,
            generated_tokens=(generated_token_ids if generated_token_ids else None),
            suppress_tokens=suppress_tokens,
            eos_token_id=eos_token_id,
        )
        is_eos = next_token[0, 0] == eos_token_id

        code_tokens = [next_token]
        code_hidden = hidden[:, -1:, :]
        for cache_slot in code_cache:
            cache_slot.keys = None
            cache_slot.values = None
            cache_slot.offset = 0

        for code_idx in range(config.num_code_groups - 1):
            if code_idx == 0:
                code_0_embed = model.talker.get_input_embeddings()(next_token)
                code_input = mx.concatenate([code_hidden, code_0_embed], axis=1)
            else:
                code_embed = model.talker.code_predictor.codec_embedding[code_idx - 1](
                    code_tokens[-1]
                )
                code_input = code_embed

            code_logits, code_cache, _ = model.talker.code_predictor(
                code_input,
                cache=code_cache,
                generation_step=code_idx,
            )
            next_code = model._sample_token(
                code_logits,
                temperature=temperature,
                top_k=top_k,
                top_p=top_p,
            )
            code_tokens.append(next_code)

        all_codes = mx.concatenate(code_tokens, axis=1)

        if trailing_idx < trailing_text_hidden.shape[1]:
            text_embed_step = trailing_text_hidden[:, trailing_idx : trailing_idx + 1, :]
            trailing_idx += 1
        else:
            text_embed_step = tts_pad_embed

        codec_embed = model.talker.get_input_embeddings()(next_token)
        for idx, code in enumerate(code_tokens[1:]):
            codec_embed = codec_embed + model.talker.code_predictor.codec_embedding[idx](code)

        input_embeds = text_embed_step + codec_embed
        mx.eval(input_embeds, is_eos)
        if is_eos.item():
            break

        generated_token_ids.append(int(next_token[0, 0]))
        generated_codes.append(all_codes)
        if step > 0 and step % 50 == 0:
            mx.clear_cache()

    if not generated_codes:
        raise RuntimeError("model returned no audio tokens for the requested text")

    gen_codes = mx.stack(generated_codes, axis=1)
    ref_codes_t = mx.transpose(ref_codes, (0, 2, 1))
    full_codes = mx.concatenate([ref_codes_t, gen_codes], axis=1)

    ref_len = ref_codes.shape[2]
    total_len = full_codes.shape[1]
    audio, audio_lengths = model.speech_tokenizer.decode(full_codes)
    audio = audio[0]
    valid_len = int(audio_lengths[0])
    if 0 < valid_len < audio.shape[0]:
        audio = audio[:valid_len]

    cut = int(ref_len / max(total_len, 1) * audio.shape[0])
    if 0 < cut < audio.shape[0]:
        audio = audio[cut:]

    mx.eval(audio)
    if verbose:
        print(f"[voice-clone] generated {len(generated_codes)} tokens")
    return audio


class Qwen3TTSBackend:
    def __init__(
        self,
        model_manager: Optional[ModelManager] = None,
        prompt_store: Optional[VoiceClonePromptStore] = None,
        clone_generator: Callable[..., Any] = generate_base_clone_audio,
    ) -> None:
        self.model_manager = model_manager or ModelManager()
        self.prompt_store = prompt_store or VoiceClonePromptStore()
        self.clone_generator = clone_generator
        self._backend_loaded = False
        self._audio_write: Any = None
        self._np: Any = None

    def _ensure_backend(self) -> None:
        if self._backend_loaded:
            return
        import numpy as np
        from mlx_audio.audio_io import write as audio_write

        self._np = np
        self._audio_write = audio_write
        self._backend_loaded = True

    def preload(self) -> None:
        self.model_manager.preload()

    def health(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "service": "qwen3-tts-api",
            "version": SERVICE_VERSION,
            "loaded_model": self.model_manager.loaded_model_id,
            "prompt_cache_count": self.prompt_store.count(),
            "model_root": str(self.model_manager.model_root),
            "load_counts": self.model_manager.load_counts(),
        }

    def list_models(self) -> dict[str, Any]:
        return {"object": "list", "data": self.model_manager.list_models()}

    def create_voice_clone_prompt(
        self,
        *,
        ref_audio_bytes: bytes,
        ref_audio_filename: Optional[str],
        ref_text: str,
        language: str,
    ) -> dict[str, Any]:
        model = self.model_manager.get_model(BASE_MODEL_ID)
        metadata = self.prompt_store.create(
            model=model,
            ref_audio_bytes=ref_audio_bytes,
            ref_audio_filename=ref_audio_filename,
            ref_text=ref_text,
            language=language,
        )
        metadata["object"] = "voice_clone_prompt"
        return metadata

    def delete_voice_clone_prompt(self, prompt_id: str) -> dict[str, Any]:
        deleted = self.prompt_store.delete(prompt_id)
        if not deleted:
            raise PromptNotFoundError(f"voice clone prompt not found: {prompt_id}")
        return {"id": prompt_id, "object": "voice_clone_prompt", "deleted": True}

    def _collect_audio(self, results: list[Any]) -> tuple[Any, int]:
        self._ensure_backend()
        if not results:
            raise RuntimeError("model returned no audio")
        audio_parts = [mlx_to_numpy(result.audio, self._np).reshape(-1) for result in results]
        sample_rate = int(results[-1].sample_rate)
        if len(audio_parts) == 1:
            return audio_parts[0], sample_rate
        return self._np.concatenate(audio_parts, axis=0), sample_rate

    def synthesize(self, request: SpeechRequestModel) -> bytes:
        self._ensure_backend()

        if request.response_format.lower() != "wav":
            raise HTTPException(status_code=400, detail="only response_format='wav' is supported")

        if request.model not in SUPPORTED_MODELS:
            raise ModelNotFoundError(f"unsupported model: {request.model}")

        if request.voice_clone_prompt_id and request.instruct:
            raise HTTPException(status_code=400, detail="voice_clone_prompt_id and instruct cannot be used together")

        if request.model == BASE_MODEL_ID and request.instruct:
            raise HTTPException(status_code=400, detail="Base model does not accept instruct")

        if request.model == VOICE_DESIGN_MODEL_ID and request.voice_clone_prompt_id:
            raise HTTPException(status_code=400, detail="VoiceDesign model does not accept voice_clone_prompt_id")

        if request.model == VOICE_DESIGN_MODEL_ID and not request.instruct:
            raise HTTPException(status_code=400, detail="VoiceDesign model requires instruct")

        language = normalize_language(request.lang_code)
        clone_language = None if language == "auto" else language

        if request.voice_clone_prompt_id:
            prompt = self.prompt_store.load(request.voice_clone_prompt_id)
            if prompt.model_id != BASE_MODEL_ID:
                raise HTTPException(status_code=400, detail="voice clone prompt is not compatible with the requested model")
            model = self.model_manager.get_model(BASE_MODEL_ID)
            audio = self.clone_generator(
                model,
                request.input,
                prompt,
                language=clone_language,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                top_k=request.top_k,
                top_p=request.top_p,
                repetition_penalty=max(request.repetition_penalty, 1.5),
                verbose=request.verbose,
            )
            sample_rate = int(model.sample_rate)
        else:
            model = self.model_manager.get_model(request.model)
            kwargs = {
                "text": request.input,
                "lang_code": language,
                "temperature": request.temperature,
                "top_p": request.top_p,
                "top_k": request.top_k,
                "repetition_penalty": request.repetition_penalty,
                "max_tokens": request.max_tokens,
                "verbose": request.verbose,
            }
            if request.model == BASE_MODEL_ID and request.voice is not None:
                kwargs["voice"] = request.voice
            if request.model == VOICE_DESIGN_MODEL_ID:
                kwargs["instruct"] = request.instruct
            results = list(model.generate(**kwargs))
            audio, sample_rate = self._collect_audio(results)

        audio = apply_speed(audio, request.speed, self._np)
        return encode_wav_bytes(audio, sample_rate, self._audio_write, self._np)


def create_auth_dependency(api_key: Optional[str]) -> Callable[[Request], None]:
    def verify(request: Request) -> None:
        if not api_key:
            return
        auth_header = request.headers.get("Authorization")
        if auth_header != f"Bearer {api_key}":
            raise HTTPException(status_code=401, detail="unauthorized")

    return verify


def create_app(
    *,
    backend: Optional[Qwen3TTSBackend] = None,
    api_key: Optional[str] = None,
) -> FastAPI:
    backend = backend or Qwen3TTSBackend()
    require_auth = create_auth_dependency(api_key)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        backend.preload()
        yield

    app = FastAPI(title="Qwen3-TTS API", version=SERVICE_VERSION, lifespan=lifespan)
    app.state.backend = backend

    v1 = APIRouter(prefix="/v1", dependencies=[Depends(require_auth)])

    @app.get("/health")
    def health() -> dict[str, Any]:
        return backend.health()

    @v1.get("/models")
    def list_models() -> dict[str, Any]:
        return backend.list_models()

    @v1.post("/audio/speech")
    def audio_speech(request: SpeechRequestModel) -> Response:
        try:
            wav_bytes = backend.synthesize(request)
        except ModelNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except PromptNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return Response(content=wav_bytes, media_type="audio/wav")

    @v1.post("/audio/voice-clone-prompts")
    async def create_voice_clone_prompt(
        ref_audio: UploadFile = File(...),
        ref_text: str = Form(...),
        language: str = Form("chinese"),
    ) -> dict[str, Any]:
        ref_text_value = ref_text.strip()
        if not ref_text_value:
            raise HTTPException(status_code=400, detail="ref_text must not be empty")

        ref_audio_bytes = await ref_audio.read()
        if not ref_audio_bytes:
            raise HTTPException(status_code=400, detail="ref_audio must not be empty")

        try:
            return backend.create_voice_clone_prompt(
                ref_audio_bytes=ref_audio_bytes,
                ref_audio_filename=ref_audio.filename,
                ref_text=ref_text_value,
                language=language,
            )
        except ModelNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @v1.delete("/audio/voice-clone-prompts/{prompt_id}")
    def delete_voice_clone_prompt(prompt_id: str) -> dict[str, Any]:
        try:
            return backend.delete_voice_clone_prompt(prompt_id)
        except PromptNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    app.include_router(v1)
    return app


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the standalone Qwen3-TTS API server.")
    parser.add_argument("--host", default=os.getenv("QWEN3_TTS_API_HOST", DEFAULT_HOST))
    parser.add_argument("--port", type=int, default=int(os.getenv("QWEN3_TTS_API_PORT", DEFAULT_PORT)))
    parser.add_argument("--api-key", default=os.getenv("QWEN3_TTS_API_KEY"))
    parser.add_argument(
        "--model-root",
        default=os.getenv("QWEN3_TTS_MODEL_ROOT", str(DEFAULT_MODEL_ROOT)),
        help=f"Directory containing {BASE_MODEL_ID} and {VOICE_DESIGN_MODEL_ID}.",
    )
    parser.add_argument(
        "--prompt-cache-dir",
        default=os.getenv("QWEN3_TTS_PROMPT_CACHE_DIR", str(DEFAULT_PROMPT_CACHE_DIR)),
        help="Directory used to persist voice clone prompt artifacts.",
    )
    parser.add_argument(
        "--preload-model",
        default=os.getenv("QWEN3_TTS_PRELOAD_MODEL", BASE_MODEL_ID),
        choices=list(SUPPORTED_MODELS),
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    import uvicorn

    args = build_parser().parse_args(argv)
    model_manager = ModelManager(
        model_root=Path(args.model_root),
        preload_model_id=args.preload_model,
    )
    prompt_store = VoiceClonePromptStore(cache_dir=Path(args.prompt_cache_dir))
    app = create_app(
        backend=Qwen3TTSBackend(model_manager=model_manager, prompt_store=prompt_store),
        api_key=args.api_key,
    )
    uvicorn.run(app, host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
