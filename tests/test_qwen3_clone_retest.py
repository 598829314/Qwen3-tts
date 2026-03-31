import tempfile
import unittest
import wave
from pathlib import Path

from qwen3_clone_retest import (
    ValidationReport,
    encode_multipart_formdata,
    inspect_wav,
    validate_reference_wav,
)


def write_wav(path: Path, *, channels: int, sample_rate: int, duration_sec: float) -> None:
    frame_count = int(sample_rate * duration_sec)
    frame = (b"\x00\x00" * channels)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(frame * frame_count)


class CloneRetestUnitTest(unittest.TestCase):
    def test_inspect_wav_returns_expected_stats(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "ref.wav"
            write_wav(path, channels=1, sample_rate=24000, duration_sec=6.0)

            stats = inspect_wav(path)

            self.assertEqual(stats.channels, 1)
            self.assertEqual(stats.frame_rate, 24000)
            self.assertAlmostEqual(stats.duration_sec, 6.0, places=2)

    def test_validate_reference_wav_accepts_short_mono_clip(self) -> None:
        report = validate_reference_wav(
            inspect_wav(self._make_wav(channels=1, sample_rate=24000, duration_sec=6.2))
        )
        self.assertTrue(report.ok)
        self.assertEqual(report.errors, [])

    def test_validate_reference_wav_rejects_stereo_and_long_duration(self) -> None:
        report = validate_reference_wav(
            inspect_wav(self._make_wav(channels=2, sample_rate=24000, duration_sec=16.0))
        )
        self.assertFalse(report.ok)
        self.assertGreaterEqual(len(report.errors), 2)

    def test_multipart_encoder_includes_fields_and_file(self) -> None:
        body, boundary = encode_multipart_formdata(
            fields={"ref_text": "你好", "language": "chinese"},
            files={"ref_audio": ("ref.wav", b"RIFFDATA", "audio/wav")},
        )

        self.assertIn(boundary.encode("utf-8"), body)
        self.assertIn(b'name="ref_text"', body)
        self.assertIn(b"\xe4\xbd\xa0\xe5\xa5\xbd", body)
        self.assertIn(b'filename="ref.wav"', body)
        self.assertIn(b"RIFFDATA", body)

    def _make_wav(self, *, channels: int, sample_rate: int, duration_sec: float) -> Path:
        tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(tempdir.cleanup)
        path = Path(tempdir.name) / "ref.wav"
        write_wav(path, channels=channels, sample_rate=sample_rate, duration_sec=duration_sec)
        return path


if __name__ == "__main__":
    unittest.main()
