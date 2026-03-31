import unittest
from pathlib import Path

from qwen3_tts_paths import (
    APP_NAME,
    REPO_ROOT,
    find_bundle_contents,
    get_app_support_dir,
    get_default_prompt_cache_dir,
    get_default_workspace_dir,
)


class Qwen3TTSPathsTest(unittest.TestCase):
    def test_find_bundle_contents_from_fake_bundle_path(self) -> None:
        fake = Path(
            "/Applications/Qwen3-TTS.app/Contents/Resources/qwen3_tts_service.py"
        )
        contents = find_bundle_contents(fake)
        self.assertEqual(contents, Path("/Applications/Qwen3-TTS.app/Contents"))

    def test_default_workspace_is_repo_root_in_dev_mode(self) -> None:
        self.assertEqual(get_default_workspace_dir(), REPO_ROOT)

    def test_default_prompt_cache_dir_is_under_app_support(self) -> None:
        prompt_cache_dir = get_default_prompt_cache_dir()
        self.assertIn(APP_NAME, str(prompt_cache_dir))
        self.assertIn("Application Support", str(prompt_cache_dir))
        self.assertTrue(prompt_cache_dir.exists())

    def test_app_support_dir_exists(self) -> None:
        app_support_dir = get_app_support_dir()
        self.assertTrue(app_support_dir.exists())


if __name__ == "__main__":
    unittest.main()
