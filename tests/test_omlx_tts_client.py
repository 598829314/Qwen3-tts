import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib import error

from omlx_tts_client import OMLXTTSAPIError, OMLXTTSClient


class FakeResponse:
    def __init__(self, body: bytes):
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class TestOMLXTTSClient(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OMLXTTSClient(api_key="1234")

    @patch("omlx_tts_client.request.urlopen")
    def test_health_returns_json(self, mock_urlopen):
        mock_urlopen.return_value = FakeResponse(b'{"status":"ok"}')

        response = self.client.health()

        self.assertEqual(response["status"], "ok")

    @patch("omlx_tts_client.request.urlopen")
    def test_list_models_uses_auth_header(self, mock_urlopen):
        mock_urlopen.return_value = FakeResponse(b'{"data":[]}')

        self.client.list_models()

        req = mock_urlopen.call_args.args[0]
        self.assertEqual(req.get_header("Authorization"), "Bearer 1234")

    @patch("omlx_tts_client.request.urlopen")
    def test_synthesize_returns_binary_audio(self, mock_urlopen):
        mock_urlopen.return_value = FakeResponse(b"RIFF....WAVE")

        audio = self.client.synthesize("test", voice="Chelsie", speed=1.0)

        self.assertTrue(audio.startswith(b"RIFF"))
        req = mock_urlopen.call_args.args[0]
        payload = json.loads(req.data.decode("utf-8"))
        self.assertEqual(payload["voice"], "Chelsie")
        self.assertEqual(payload["speed"], 1.0)
        self.assertEqual(payload["response_format"], "wav")

    def test_synthesize_rejects_empty_text(self):
        with self.assertRaises(ValueError):
            self.client.synthesize("")

    @patch("omlx_tts_client.request.urlopen")
    def test_save_wav_returns_absolute_unique_path(self, mock_urlopen):
        mock_urlopen.return_value = FakeResponse(b"RIFF....WAVE")

        with tempfile.TemporaryDirectory() as tmpdir:
            first = Path(self.client.save_wav("hello", output_dir=tmpdir, file_prefix="openclaw"))
            second = Path(self.client.save_wav("hello", output_dir=tmpdir, file_prefix="openclaw"))

        self.assertTrue(first.is_absolute())
        self.assertNotEqual(first.name, second.name)
        self.assertEqual(first.suffix, ".wav")

    @patch("omlx_tts_client.request.urlopen")
    def test_http_error_raises_api_error(self, mock_urlopen):
        http_error = error.HTTPError(
            url="http://127.0.0.1:10087/v1/audio/speech",
            code=500,
            msg="Internal Server Error",
            hdrs=None,
            fp=None,
        )
        http_error.read = lambda: b'{"error":{"message":"tts failed"}}'
        mock_urlopen.side_effect = http_error

        with self.assertRaises(OMLXTTSAPIError) as ctx:
            self.client.synthesize("test")

        self.assertEqual(ctx.exception.status_code, 500)
        self.assertIn("tts failed", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
