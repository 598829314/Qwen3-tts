import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path

try:
    import numpy as np
    from fastapi.testclient import TestClient

    from qwen3_tts_api import (
        BASE_MODEL_ID,
        VOICE_DESIGN_MODEL_ID,
        ModelManager,
        ModelNotFoundError,
        PromptNotFoundError,
        Qwen3TTSBackend,
        StoredVoiceClonePrompt,
        VoiceClonePromptStore,
        create_app,
    )
except ImportError as exc:  # pragma: no cover - system python may not have FastAPI
    np = None
    TestClient = None
    IMPORT_ERROR = exc
else:
    IMPORT_ERROR = None


if IMPORT_ERROR is None:
    @dataclass
    class FakeResult:
        audio: np.ndarray
        sample_rate: int = 24000


    class FakeModel:
        def __init__(self, model_id: str) -> None:
            self.model_id = model_id
            self.sample_rate = 24000

        def generate(self, **kwargs):
            if self.model_id == VOICE_DESIGN_MODEL_ID and not kwargs.get("instruct"):
                raise ValueError("missing instruct")
            return [FakeResult(audio=np.array([0.1, -0.1, 0.2], dtype=np.float32))]


    class FakeModelManager:
        def __init__(self) -> None:
            self.model_root = Path("/fake")
            self._models = {
                BASE_MODEL_ID: FakeModel(BASE_MODEL_ID),
                VOICE_DESIGN_MODEL_ID: FakeModel(VOICE_DESIGN_MODEL_ID),
            }
            self._loaded_model_id = None
            self._load_counts = {BASE_MODEL_ID: 0, VOICE_DESIGN_MODEL_ID: 0}

        @property
        def loaded_model_id(self):
            return self._loaded_model_id

        def load_counts(self):
            return dict(self._load_counts)

        def preload(self):
            self.get_model(BASE_MODEL_ID)

        def list_models(self):
            return [
                {
                    "id": BASE_MODEL_ID,
                    "object": "model",
                    "owned_by": "local",
                    "kind": "base",
                    "capabilities": ["tts", "voice", "voice_clone"],
                    "available": True,
                },
                {
                    "id": VOICE_DESIGN_MODEL_ID,
                    "object": "model",
                    "owned_by": "local",
                    "kind": "voice_design",
                    "capabilities": ["tts", "voice_design"],
                    "available": True,
                },
            ]

        def get_model(self, model_id: str):
            if model_id not in self._models:
                raise ModelNotFoundError(model_id)
            if self._loaded_model_id != model_id:
                self._loaded_model_id = model_id
                self._load_counts[model_id] += 1
            return self._models[model_id]


    class FakePromptStore:
        def __init__(self) -> None:
            self._prompts = {}

        def count(self) -> int:
            return len(self._prompts)

        def create(self, **kwargs):
            prompt = StoredVoiceClonePrompt(
                prompt_id="prompt-1",
                model_id=BASE_MODEL_ID,
                language="chinese",
                ref_text=kwargs["ref_text"],
                audio_sha256="abc",
                created_at=1.0,
                ref_audio_filename=kwargs["ref_audio_filename"] or "ref.wav",
                ref_codes=np.array([[[1, 2], [3, 4]]], dtype=np.int32),
                ref_text_ids=np.array([[1, 2, 3]], dtype=np.int32),
                speaker_embed=np.array([[0.2, 0.3]], dtype=np.float32),
            )
            self._prompts[prompt.prompt_id] = prompt
            return {
                "prompt_id": prompt.prompt_id,
                "model_id": prompt.model_id,
                "language": prompt.language,
                "ref_text": prompt.ref_text,
                "audio_sha256": prompt.audio_sha256,
                "created_at": prompt.created_at,
                "ref_audio_filename": prompt.ref_audio_filename,
            }

        def load(self, prompt_id: str):
            if prompt_id not in self._prompts:
                raise PromptNotFoundError(prompt_id)
            return self._prompts[prompt_id]

        def delete(self, prompt_id: str) -> bool:
            return self._prompts.pop(prompt_id, None) is not None


@unittest.skipIf(IMPORT_ERROR is not None, f"FastAPI stack unavailable: {IMPORT_ERROR}")
class Qwen3TTSAPITest(unittest.TestCase):
    def setUp(self) -> None:
        self.manager = FakeModelManager()
        self.prompt_store = FakePromptStore()
        self.backend = Qwen3TTSBackend(
            model_manager=self.manager,
            prompt_store=self.prompt_store,
            clone_generator=lambda model, text, prompt, **kwargs: np.array(
                [0.2, -0.2, 0.1], dtype=np.float32
            ),
        )
        self.client = TestClient(create_app(backend=self.backend, api_key="secret"))
        self.client.__enter__()

    def tearDown(self) -> None:
        self.client.__exit__(None, None, None)

    def test_health_reports_loaded_model_and_prompt_count(self) -> None:
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["loaded_model"], BASE_MODEL_ID)
        self.assertEqual(payload["prompt_cache_count"], 0)

    def test_v1_models_requires_auth(self) -> None:
        response = self.client.get("/v1/models")
        self.assertEqual(response.status_code, 401)

    def test_v1_models_returns_capabilities(self) -> None:
        response = self.client.get(
            "/v1/models",
            headers={"Authorization": "Bearer secret"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["data"]), 2)
        self.assertEqual(payload["data"][0]["id"], BASE_MODEL_ID)

    def test_base_speech_returns_audio_wav(self) -> None:
        response = self.client.post(
            "/v1/audio/speech",
            headers={"Authorization": "Bearer secret"},
            json={
                "model": BASE_MODEL_ID,
                "input": "你好",
                "response_format": "wav",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "audio/wav")
        self.assertTrue(response.content.startswith(b"RIFF"))

    def test_voice_design_requires_instruct(self) -> None:
        response = self.client.post(
            "/v1/audio/speech",
            headers={"Authorization": "Bearer secret"},
            json={
                "model": VOICE_DESIGN_MODEL_ID,
                "input": "你好",
                "response_format": "wav",
            },
        )
        self.assertEqual(response.status_code, 400)

    def test_base_rejects_instruct(self) -> None:
        response = self.client.post(
            "/v1/audio/speech",
            headers={"Authorization": "Bearer secret"},
            json={
                "model": BASE_MODEL_ID,
                "input": "你好",
                "response_format": "wav",
                "instruct": "warm",
            },
        )
        self.assertEqual(response.status_code, 400)

    def test_create_and_use_voice_clone_prompt(self) -> None:
        create_response = self.client.post(
            "/v1/audio/voice-clone-prompts",
            headers={"Authorization": "Bearer secret"},
            files={"ref_audio": ("ref.wav", b"RIFFfake", "audio/wav")},
            data={"ref_text": "你好", "language": "Chinese"},
        )
        self.assertEqual(create_response.status_code, 200)
        prompt_id = create_response.json()["prompt_id"]

        speech_response = self.client.post(
            "/v1/audio/speech",
            headers={"Authorization": "Bearer secret"},
            json={
                "model": BASE_MODEL_ID,
                "input": "今天开会到这里",
                "response_format": "wav",
                "voice_clone_prompt_id": prompt_id,
            },
        )
        self.assertEqual(speech_response.status_code, 200)
        self.assertTrue(speech_response.content.startswith(b"RIFF"))

    def test_voice_clone_without_lang_code_preserves_prompt_language(self) -> None:
        captured = {}
        backend = Qwen3TTSBackend(
            model_manager=self.manager,
            prompt_store=self.prompt_store,
            clone_generator=lambda model, text, prompt, **kwargs: captured.setdefault(
                "language", kwargs.get("language")
            ) or np.array([0.2, -0.2, 0.1], dtype=np.float32),
        )
        client = TestClient(create_app(backend=backend, api_key="secret"))
        client.__enter__()
        self.addCleanup(client.__exit__, None, None, None)

        create_response = client.post(
            "/v1/audio/voice-clone-prompts",
            headers={"Authorization": "Bearer secret"},
            files={"ref_audio": ("ref.wav", b"RIFFfake", "audio/wav")},
            data={"ref_text": "你好", "language": "Chinese"},
        )
        prompt_id = create_response.json()["prompt_id"]

        speech_response = client.post(
            "/v1/audio/speech",
            headers={"Authorization": "Bearer secret"},
            json={
                "model": BASE_MODEL_ID,
                "input": "今天开会到这里",
                "response_format": "wav",
                "voice_clone_prompt_id": prompt_id,
            },
        )

        self.assertEqual(speech_response.status_code, 200)
        self.assertIsNone(captured["language"])

    def test_voice_clone_with_explicit_lang_code_forwards_normalized_language(self) -> None:
        captured = {}

        def clone_generator(model, text, prompt, **kwargs):
            captured["language"] = kwargs.get("language")
            return np.array([0.2, -0.2, 0.1], dtype=np.float32)

        backend = Qwen3TTSBackend(
            model_manager=self.manager,
            prompt_store=self.prompt_store,
            clone_generator=clone_generator,
        )
        client = TestClient(create_app(backend=backend, api_key="secret"))
        client.__enter__()
        self.addCleanup(client.__exit__, None, None, None)

        create_response = client.post(
            "/v1/audio/voice-clone-prompts",
            headers={"Authorization": "Bearer secret"},
            files={"ref_audio": ("ref.wav", b"RIFFfake", "audio/wav")},
            data={"ref_text": "你好", "language": "Chinese"},
        )
        prompt_id = create_response.json()["prompt_id"]

        speech_response = client.post(
            "/v1/audio/speech",
            headers={"Authorization": "Bearer secret"},
            json={
                "model": BASE_MODEL_ID,
                "input": "今天开会到这里",
                "response_format": "wav",
                "voice_clone_prompt_id": prompt_id,
                "lang_code": "Chinese",
            },
        )

        self.assertEqual(speech_response.status_code, 200)
        self.assertEqual(captured["language"], "chinese")

    def test_delete_voice_clone_prompt(self) -> None:
        self.prompt_store.create(
            model=None,
            ref_audio_bytes=b"RIFFfake",
            ref_audio_filename="ref.wav",
            ref_text="你好",
            language="Chinese",
        )
        response = self.client.delete(
            "/v1/audio/voice-clone-prompts/prompt-1",
            headers={"Authorization": "Bearer secret"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["deleted"])

    def test_rejects_invalid_response_format(self) -> None:
        response = self.client.post(
            "/v1/audio/speech",
            headers={"Authorization": "Bearer secret"},
            json={
                "model": BASE_MODEL_ID,
                "input": "你好",
                "response_format": "mp3",
            },
        )
        self.assertEqual(response.status_code, 400)


@unittest.skipIf(IMPORT_ERROR is not None, f"FastAPI stack unavailable: {IMPORT_ERROR}")
class ModelManagerUnitTest(unittest.TestCase):
    def test_reuses_loaded_model_for_same_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / BASE_MODEL_ID).mkdir()
            (root / VOICE_DESIGN_MODEL_ID).mkdir()
            load_calls = []
            cache_events = []

            def loader(path: Path):
                load_calls.append(path.name)
                return {"path": str(path)}

            manager = ModelManager(
                model_root=root,
                loader=loader,
                cache_clearer=lambda: cache_events.append("clear"),
                gc_collector=lambda: cache_events.append("gc"),
            )

            first = manager.get_model(BASE_MODEL_ID)
            second = manager.get_model(BASE_MODEL_ID)

            self.assertEqual(first, second)
            self.assertEqual(load_calls, [BASE_MODEL_ID])
            self.assertEqual(manager.load_counts()[BASE_MODEL_ID], 1)

    def test_switching_models_clears_cache_and_reloads(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / BASE_MODEL_ID).mkdir()
            (root / VOICE_DESIGN_MODEL_ID).mkdir()
            load_calls = []
            cache_events = []

            def loader(path: Path):
                load_calls.append(path.name)
                return {"path": str(path)}

            manager = ModelManager(
                model_root=root,
                loader=loader,
                cache_clearer=lambda: cache_events.append("clear"),
                gc_collector=lambda: cache_events.append("gc"),
            )

            manager.get_model(BASE_MODEL_ID)
            manager.get_model(VOICE_DESIGN_MODEL_ID)

            self.assertEqual(load_calls, [BASE_MODEL_ID, VOICE_DESIGN_MODEL_ID])
            self.assertIn("clear", cache_events)
            self.assertIn("gc", cache_events)
            self.assertEqual(manager.loaded_model_id, VOICE_DESIGN_MODEL_ID)


@unittest.skipIf(IMPORT_ERROR is not None, f"FastAPI stack unavailable: {IMPORT_ERROR}")
class VoiceClonePromptStoreUnitTest(unittest.TestCase):
    def test_create_load_delete_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)

            def fake_builder(model, ref_audio_path, ref_text, language):
                return (
                    {
                        "ref_codes": np.array([[[1, 2], [3, 4]]], dtype=np.int32),
                        "ref_text_ids": np.array([[1, 2, 3]], dtype=np.int32),
                        "speaker_embed": np.array([[0.5, 0.6]], dtype=np.float32),
                    },
                    {"language": "chinese"},
                )

            store = VoiceClonePromptStore(cache_dir=root, artifact_builder=fake_builder)
            metadata = store.create(
                model=object(),
                ref_audio_bytes=b"RIFFfake",
                ref_audio_filename="ref.wav",
                ref_text="你好",
                language="Chinese",
            )
            prompt = store.load(metadata["prompt_id"])

            self.assertEqual(prompt.prompt_id, metadata["prompt_id"])
            self.assertEqual(prompt.model_id, BASE_MODEL_ID)
            self.assertEqual(prompt.language, "chinese")
            self.assertEqual(store.count(), 1)
            self.assertTrue(store.delete(prompt.prompt_id))
            self.assertEqual(store.count(), 0)


if __name__ == "__main__":
    unittest.main()
