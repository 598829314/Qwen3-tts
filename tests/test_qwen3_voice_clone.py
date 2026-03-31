import tempfile
import unittest
from pathlib import Path

from qwen3_voice_clone import build_output_path, normalize_language, resolve_ref_text_path


class Qwen3VoiceCloneHelpersTest(unittest.TestCase):
    def test_normalize_language(self) -> None:
        self.assertEqual(normalize_language("Chinese"), "chinese")
        self.assertEqual(normalize_language("zh-CN"), "chinese")
        self.assertEqual(normalize_language("英文"), "english")
        self.assertEqual(normalize_language("auto"), "auto")

    def test_build_output_path_uses_wav_suffix(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = build_output_path(tmpdir, prefix="clone-test")
            self.assertEqual(path.suffix, ".wav")
            self.assertEqual(path.parent.resolve(), Path(tmpdir).resolve())

    def test_resolve_ref_text_path_finds_existing_workspace_file(self) -> None:
        path = resolve_ref_text_path()
        self.assertTrue(path.exists())
        self.assertIn(path.name, {"gwhgwh.txt", "文本.txt"})


if __name__ == "__main__":
    unittest.main()
