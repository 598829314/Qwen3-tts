from __future__ import annotations

import argparse
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, List, Optional, Sequence, Union


ROOT_DIR = Path(__file__).resolve().parent
DEFAULT_MODEL_PATH = (
    Path.home()
    / ".lmstudio/models/mlx-community/Qwen3-TTS-12Hz-1.7B-Base-4bit"
)
DEFAULT_OUTPUT_DIR = ROOT_DIR / "outputs"
DEFAULT_REF_AUDIO = ROOT_DIR / "gwhgwh.wav"
DEFAULT_REF_TEXT_CANDIDATES = (
    ROOT_DIR / "gwhgwh.txt",
    ROOT_DIR / "文本.txt",
)


def resolve_ref_text_path(explicit_path: Optional[Union[str, Path]] = None) -> Path:
    if explicit_path:
        path = Path(explicit_path).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"Reference text file not found: {path}")
        return path

    for candidate in DEFAULT_REF_TEXT_CANDIDATES:
        if candidate.exists():
            return candidate

    candidate_list = ", ".join(str(path) for path in DEFAULT_REF_TEXT_CANDIDATES)
    raise FileNotFoundError(
        "Reference transcript file not found. Expected one of: "
        f"{candidate_list}"
    )


def load_ref_text(ref_text_path: Optional[Union[str, Path]] = None) -> str:
    path = resolve_ref_text_path(ref_text_path)
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError(f"Reference transcript is empty: {path}")
    return text


def normalize_language(language: Optional[str]) -> str:
    if not language:
        return "chinese"

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


def ensure_output_dir(output_dir: Union[str, Path]) -> Path:
    path = Path(output_dir).expanduser().resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def build_output_path(
    output_dir: Union[str, Path],
    prefix: str = "clone",
    stem: Optional[str] = None,
) -> Path:
    directory = ensure_output_dir(output_dir)
    if stem:
        safe_stem = "".join(
            char if char.isalnum() or char in ("-", "_") else "_"
            for char in stem.strip()
        ).strip("_")
        base_name = safe_stem or prefix
    else:
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        base_name = f"{prefix}-{timestamp}-{uuid.uuid4().hex[:8]}"
    return directory / f"{base_name}.wav"


@dataclass
class VoiceClonePrompt:
    ref_audio_path: str
    ref_text: str
    language: str
    ref_audio: Any
    ref_codes: Any
    ref_text_ids: Any
    speaker_embed: Any


class Qwen3VoiceCloner:
    def __init__(
        self,
        model_path: Union[str, Path] = DEFAULT_MODEL_PATH,
        output_dir: Union[str, Path] = DEFAULT_OUTPUT_DIR,
        file_prefix: str = "clone",
    ) -> None:
        self.model_path = str(Path(model_path).expanduser().resolve())
        self.output_dir = ensure_output_dir(output_dir)
        self.file_prefix = file_prefix
        self._model: Any = None
        self._mx: Any = None
        self._np: Any = None
        self._audio_write: Any = None
        self._load_audio: Any = None
        self._generation_result_cls: Any = None

    @property
    def model(self) -> Any:
        self._ensure_model_loaded()
        return self._model

    def _ensure_backend_loaded(self) -> None:
        if self._mx is not None:
            return

        import numpy as np
        import mlx.core as mx
        from mlx_audio.audio_io import write as audio_write
        from mlx_audio.tts.models.base import GenerationResult
        from mlx_audio.tts.utils import load_model
        from mlx_audio.utils import load_audio

        self._np = np
        self._mx = mx
        self._audio_write = audio_write
        self._load_audio = load_audio
        self._generation_result_cls = GenerationResult
        self._load_model_fn = load_model

    def _ensure_model_loaded(self) -> None:
        self._ensure_backend_loaded()
        if self._model is None:
            self._model = self._load_model_fn(self.model_path)

    def _load_ref_audio(self, ref_audio: Union[str, Path]) -> Any:
        self._ensure_model_loaded()
        audio_path = str(Path(ref_audio).expanduser().resolve())
        if not Path(audio_path).exists():
            raise FileNotFoundError(f"Reference audio file not found: {audio_path}")
        return self._load_audio(audio_path, sample_rate=self.model.sample_rate)

    def create_voice_clone_prompt(
        self,
        ref_audio: Union[str, Path] = DEFAULT_REF_AUDIO,
        ref_text: Optional[str] = None,
        language: str = "Chinese",
    ) -> VoiceClonePrompt:
        self._ensure_model_loaded()
        mx = self._mx
        model = self.model

        ref_text_value = ref_text or load_ref_text()
        ref_audio_value = self._load_ref_audio(ref_audio)
        normalized_language = normalize_language(language)

        audio_for_spk = ref_audio_value
        if ref_audio_value.ndim == 1:
            ref_audio_batch = ref_audio_value[None, None, :]
        elif ref_audio_value.ndim == 2:
            ref_audio_batch = ref_audio_value[None, :]
        else:
            ref_audio_batch = ref_audio_value

        ref_codes = model.speech_tokenizer.encode(ref_audio_batch)
        mx.eval(ref_codes)

        ref_chat = f"<|im_start|>assistant\n{ref_text_value}<|im_end|>\n"
        ref_ids = mx.array(model.tokenizer.encode(ref_chat))[None, :]
        ref_text_ids = ref_ids[:, 3:-2]

        speaker_embed = None
        if model.speaker_encoder is not None:
            speaker_embed = model.extract_speaker_embedding(audio_for_spk)
            mx.eval(speaker_embed)

        return VoiceClonePrompt(
            ref_audio_path=str(Path(ref_audio).expanduser().resolve()),
            ref_text=ref_text_value,
            language=normalized_language,
            ref_audio=audio_for_spk,
            ref_codes=ref_codes,
            ref_text_ids=ref_text_ids,
            speaker_embed=speaker_embed,
        )

    def _prepare_inputs_from_prompt(
        self,
        text: str,
        prompt: VoiceClonePrompt,
        language: Optional[str] = None,
    ) -> tuple[Any, Any, Any, Any]:
        self._ensure_model_loaded()
        mx = self._mx
        model = self.model
        config = model.config.talker_config

        normalized_language = normalize_language(language or prompt.language)

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

        combined_text_ids = mx.concatenate([prompt.ref_text_ids, text_ids], axis=1)
        text_embed = model.talker.text_projection(
            model.talker.get_text_embeddings()(combined_text_ids)
        )
        text_embed = mx.concatenate([text_embed, tts_eos_embed], axis=1)
        text_lens = text_embed.shape[1]

        ref_codes = prompt.ref_codes
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
            if normalized_language in config.codec_language_id:
                language_id = config.codec_language_id[normalized_language]

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

        if prompt.speaker_embed is not None:
            codec_prefix_embed = mx.concatenate(
                [
                    codec_prefix_embed,
                    prompt.speaker_embed.reshape(1, 1, -1),
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
        return input_embeds, trailing_text_hidden, tts_pad_embed, ref_codes

    def _generate_from_cached_prompt(
        self,
        text: str,
        prompt: VoiceClonePrompt,
        language: Optional[str] = None,
        temperature: float = 0.9,
        max_tokens: int = 4096,
        top_k: int = 50,
        top_p: float = 1.0,
        repetition_penalty: float = 1.5,
        verbose: bool = False,
    ) -> Any:
        self._ensure_model_loaded()
        mx = self._mx
        model = self.model
        start_time = time.time()

        input_embeds, trailing_text_hidden, tts_pad_embed, ref_codes = (
            self._prepare_inputs_from_prompt(text=text, prompt=prompt, language=language)
        )

        target_token_count = len(model.tokenizer.encode(text))
        effective_max_tokens = min(max_tokens, max(75, target_token_count * 6))

        cache = model.talker.make_cache()
        code_cache = model.talker.code_predictor.make_cache()
        generated_codes = []
        generated_token_ids = []
        config = model.config.talker_config
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
                text_embed = trailing_text_hidden[:, trailing_idx : trailing_idx + 1, :]
                trailing_idx += 1
            else:
                text_embed = tts_pad_embed

            codec_embed = model.talker.get_input_embeddings()(next_token)
            for idx, code in enumerate(code_tokens[1:]):
                codec_embed = codec_embed + model.talker.code_predictor.codec_embedding[idx](code)

            input_embeds = text_embed + codec_embed
            mx.eval(input_embeds, is_eos)

            if is_eos.item():
                break

            generated_token_ids.append(int(next_token[0, 0]))
            generated_codes.append(all_codes)

            if step > 0 and step % 50 == 0:
                mx.clear_cache()

        if not generated_codes:
            raise RuntimeError("Model returned no audio tokens for the requested text.")

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
            elapsed_time = time.time() - start_time
            print(
                f"[clone] tokens={len(generated_codes)} samples={audio.shape[0]} "
                f"elapsed={elapsed_time:.2f}s"
            )
        return audio

    def _save_audio(self, audio: Any, sample_rate: int, output_path: Path) -> str:
        self._ensure_backend_loaded()
        self._audio_write(str(output_path), self._np.array(audio), sample_rate, format="wav")
        return str(output_path.resolve())

    def _iter_texts(self, text: Union[str, Sequence[str]]) -> List[str]:
        if isinstance(text, str):
            items = [text]
        else:
            items = [item for item in text]
        normalized = [item.strip() for item in items if item and item.strip()]
        if not normalized:
            raise ValueError("Input text is empty.")
        return normalized

    def generate_voice_clone(
        self,
        text: Union[str, Sequence[str]],
        language: str = "Chinese",
        ref_audio: Union[str, Path] = DEFAULT_REF_AUDIO,
        ref_text: Optional[str] = None,
        voice_clone_prompt: Optional[VoiceClonePrompt] = None,
        speed: float = 1.0,
        output_dir: Optional[Union[str, Path]] = None,
        join_sentences: bool = False,
        x_vector_only_mode: bool = False,
        verbose: bool = False,
    ) -> Union[str, List[str]]:
        self._ensure_model_loaded()
        texts = self._iter_texts(text)
        target_output_dir = ensure_output_dir(output_dir or self.output_dir)

        if voice_clone_prompt is not None and x_vector_only_mode:
            raise ValueError("voice_clone_prompt and x_vector_only_mode cannot be used together.")

        if voice_clone_prompt is None:
            ref_text_value = None if x_vector_only_mode else (ref_text or load_ref_text())
        else:
            ref_text_value = None

        audio_chunks = []
        saved_paths: List[str] = []

        for index, sentence in enumerate(texts):
            if voice_clone_prompt is not None:
                audio = self._generate_from_cached_prompt(
                    text=sentence,
                    prompt=voice_clone_prompt,
                    language=language,
                    verbose=verbose,
                )
            else:
                results = list(
                    self.model.generate(
                        text=sentence,
                        lang_code=normalize_language(language),
                        ref_audio=str(Path(ref_audio).expanduser().resolve()),
                        ref_text=ref_text_value,
                        speed=speed,
                        verbose=verbose,
                    )
                )
                if not results:
                    raise RuntimeError("Model returned no audio for the requested text.")
                audio = results[-1].audio

            if join_sentences:
                audio_chunks.append(audio)
                continue

            output_path = build_output_path(
                target_output_dir,
                prefix=self.file_prefix,
                stem=f"{self.file_prefix}_{index:03d}" if len(texts) > 1 else None,
            )
            saved_paths.append(self._save_audio(audio, self.model.sample_rate, output_path))

        if join_sentences:
            audio = self._mx.concatenate(audio_chunks, axis=0)
            output_path = build_output_path(target_output_dir, prefix=self.file_prefix)
            return self._save_audio(audio, self.model.sample_rate, output_path)

        return saved_paths[0] if len(saved_paths) == 1 else saved_paths


_DEFAULT_CLONER: Optional[Qwen3VoiceCloner] = None
_DEFAULT_PROMPT: Optional[VoiceClonePrompt] = None


def get_default_cloner() -> Qwen3VoiceCloner:
    global _DEFAULT_CLONER
    if _DEFAULT_CLONER is None:
        _DEFAULT_CLONER = Qwen3VoiceCloner()
    return _DEFAULT_CLONER


def get_default_prompt() -> VoiceClonePrompt:
    global _DEFAULT_PROMPT
    if _DEFAULT_PROMPT is None:
        cloner = get_default_cloner()
        _DEFAULT_PROMPT = cloner.create_voice_clone_prompt(
            ref_audio=DEFAULT_REF_AUDIO,
            ref_text=load_ref_text(),
            language="Chinese",
        )
    return _DEFAULT_PROMPT


def tts_clone(text: str) -> str:
    cloner = get_default_cloner()
    prompt = get_default_prompt()
    return str(
        cloner.generate_voice_clone(
            text=text,
            voice_clone_prompt=prompt,
            language="Chinese",
        )
    )


def tts_clone_batch(texts: Sequence[str], join_sentences: bool = False) -> Union[str, List[str]]:
    cloner = get_default_cloner()
    prompt = get_default_prompt()
    return cloner.generate_voice_clone(
        text=texts,
        voice_clone_prompt=prompt,
        language="Chinese",
        join_sentences=join_sentences,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Qwen3-TTS Base voice clone")
    parser.add_argument("text", nargs="*", help="Text to synthesize")
    parser.add_argument("--text-file", type=str, help="UTF-8 text file with one sentence per line")
    parser.add_argument("--model", type=str, default=str(DEFAULT_MODEL_PATH))
    parser.add_argument("--ref-audio", type=str, default=str(DEFAULT_REF_AUDIO))
    parser.add_argument("--ref-text-file", type=str, default=None)
    parser.add_argument("--language", type=str, default="Chinese")
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument("--output-dir", type=str, default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--file-prefix", type=str, default="clone")
    parser.add_argument("--join", action="store_true", help="Join all sentences into one wav")
    parser.add_argument(
        "--mode",
        choices=("direct", "cached"),
        default="cached",
        help="direct = public model.generate; cached = reuse precomputed voice clone prompt",
    )
    parser.add_argument(
        "--x-vector-only",
        action="store_true",
        help="Fallback mode when ref_text is unavailable. Quality is lower.",
    )
    parser.add_argument("--verbose", action="store_true")
    return parser


def collect_cli_texts(args: argparse.Namespace) -> List[str]:
    texts: List[str] = []
    if args.text_file:
        file_path = Path(args.text_file).expanduser().resolve()
        lines = file_path.read_text(encoding="utf-8").splitlines()
        texts.extend(line.strip() for line in lines if line.strip())
    texts.extend(item.strip() for item in args.text if item.strip())
    if not texts:
        raise ValueError("No input text provided.")
    return texts


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    texts = collect_cli_texts(args)
    cloner = Qwen3VoiceCloner(
        model_path=args.model,
        output_dir=args.output_dir,
        file_prefix=args.file_prefix,
    )

    if args.mode == "cached":
        if args.x_vector_only:
            raise ValueError("cached mode requires ref_text; x-vector-only is only valid in direct mode.")
        prompt = cloner.create_voice_clone_prompt(
            ref_audio=args.ref_audio,
            ref_text=load_ref_text(args.ref_text_file),
            language=args.language,
        )
        result = cloner.generate_voice_clone(
            text=texts,
            language=args.language,
            voice_clone_prompt=prompt,
            join_sentences=args.join,
            verbose=args.verbose,
        )
    else:
        result = cloner.generate_voice_clone(
            text=texts,
            language=args.language,
            ref_audio=args.ref_audio,
            ref_text=None if args.x_vector_only else load_ref_text(args.ref_text_file),
            speed=args.speed,
            join_sentences=args.join,
            x_vector_only_mode=args.x_vector_only,
            verbose=args.verbose,
        )

    if isinstance(result, list):
        for item in result:
            print(item)
    else:
        print(result)


if __name__ == "__main__":
    main()
