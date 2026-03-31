# Qwen3-TTS macOS App Packaging

This directory builds a self-contained `Qwen3-TTS.app` bundle for local macOS use.

The bundle includes:

- CPython runtime
- `mlx-audio` and API dependencies
- PyObjC menu bar shell
- the standalone Qwen3-TTS API and service controller scripts
- the workspace README and clone retest helper scripts

It does **not** build a DMG, sign the app, or notarize it.

## Requirements

- Apple Silicon macOS
- Python 3.12
- `venvstacks` installed in the Python environment used to run `build.py`

Install the build tool:

```bash
source ~/venvs/tts/bin/activate
pip install venvstacks
```

## Build

```bash
cd "/Users/gengwenhao/Documents/Kimi CLI/03Project/Qwen3-tts/packaging"
source ~/venvs/tts/bin/activate

python build.py
```

Reuse exported environments and rebuild only the app bundle:

```bash
python build.py --skip-venv
```

## Output

```text
packaging/
├── _build/
├── _export/
└── dist/
    └── Qwen3-TTS.app
```

Double-click the generated app:

```text
packaging/dist/Qwen3-TTS.app
```

The app keeps using:

- `~/Library/Application Support/Qwen3-TTS/config.json`
- `~/Library/Application Support/Qwen3-TTS/logs/server.log`
- `~/Library/Application Support/Qwen3-TTS/run/server.pid`
