# QwenVoice CLI

Command-line interface for [QwenVoice](https://github.com/PowerBeef/QwenVoice), a native macOS TTS application with custom voices, voice design, and voice cloning.

## Features

- **Three Generation Modes**:
  - Custom Voice: Built-in speakers (Ryan, Aiden, Serena, Vivian)
  - Voice Design: Create custom voices from descriptions
  - Voice Cloning: Clone voices from reference audio

- **Batch Processing**: Generate multiple audio clips at once
- **Voice Management**: Enroll, list, and delete cloned voices
- **JSON Output**: Machine-readable output for automation
- **REPL Mode**: Interactive session with persistent model loading

## Requirements

- macOS 15+ with Apple Silicon
- Python 3.11+
- QwenVoice backend (server.py)

## Installation

### Development Install

```bash
cd agent-harness
pip install -e .
```

This installs the `cli-anything-qwenvoice` command to your PATH.

### Verify Installation

```bash
cli-anything-qwenvoice --help
cli-anything-qwenvoice ping
```

## Quick Start

### 1. List Available Models

```bash
cli-anything-qwenvoice model list
```

### 2. Load a Model

```bash
cli-anything-qwenvoice model load pro_custom
```

### 3. Generate Audio

#### Custom Voice Mode (built-in speakers)

```bash
cli-anything-qwenvoice generate "Hello, world!" \
  --mode custom \
  --voice vivian \
  --output hello.wav
```

#### Voice Design Mode (custom voice)

```bash
cli-anything-qwenvoice generate "The quick brown fox." \
  --mode design \
  --instruct "Warm grandmotherly voice" \
  --output fox.wav
```

#### Voice Cloning Mode

```bash
cli-anything-qwenvoice generate "This is a test." \
  --mode clone \
  --ref-audio reference.wav \
  --output test.wav
```

## Commands

### Model Management

```bash
# List models
cli-anything-qwenvoice model list

# Load model
cli-anything-qwenvoice model load pro_custom
cli-anything-qwenvoice model load pro_design
cli-anything-qwenvoice model load pro_clone

# Unload model
cli-anything-qwenvoice model unload

# Get model info
cli-anything-qwenvoice model info pro_custom
```

### Generation

```bash
# Generate with options
cli-anything-qwenvoice generate "Text here" \
  --mode custom \
  --voice ryan \
  --instruct "Whisper quietly" \
  --language en \
  --temperature 0.7 \
  --output output.wav

# Batch generation
cli-anything-qwenvoice batch batch.json \
  --output-dir ./outputs
```

Batch file format:
```json
[
  {
    "text": "First sentence",
    "ref_audio": "ref1.wav",
    "ref_text": "Optional transcript"
  },
  {
    "text": "Second sentence",
    "ref_audio": "ref2.wav"
  }
]
```

### Voice Management

```bash
# List enrolled voices
cli-anything-qwenvoice voice list

# Enroll a voice
cli-anything-qwenvoice voice enroll "MyVoice" sample.wav \
  --transcript "Optional transcript"

# Delete a voice
cli-anything-qwenvoice voice delete "MyVoice"
```

### Other Commands

```bash
# Convert audio
cli-anything-qwenvoice convert input.mp3 --output output.wav

# List speakers
cli-anything-qwenvoice speakers

# Ping backend
cli-anything-qwenvoice ping
```

## REPL Mode

Interactive mode with persistent model loading:

```bash
cli-anything-qwenvoice repl
```

In REPL:
```
qwenvoice> model load pro_custom
qwenvoice> generate "Hello" --mode custom --voice vivian --output 1.wav
qwenvoice> generate "World" --mode custom --voice vivian --output 2.wav
qwenvoice> model unload
qwenvoice> exit
```

## JSON Output

All commands support JSON output for automation:

```bash
cli-anything-qwenvoice --json generate "Test" \
  --mode custom \
  --voice vivian \
  --output test.wav
```

Returns:
```json
{
  "output_path": "/path/to/test.wav",
  "duration_seconds": 2.45,
  "timings": {...}
}
```

## Options

### Global Options

- `--json`: Output in JSON format
- `--verbose, -v`: Verbose output
- `--server-path`: Path to server.py
- `--app-support-dir`: Custom app support directory

### Generation Parameters

- `--mode, -m`: Generation mode (custom, design, clone)
- `--voice`: Speaker name (for custom mode)
- `--instruct`: Voice description (for design mode)
- `--ref-audio`: Reference audio path (for clone mode)
- `--ref-text`: Reference transcript (for clone mode)
- `--language, -l`: Language code (default: auto)
- `--temperature, -t`: Sampling temperature (0.0-1.5, default: 0.6)
- `--max-tokens`: Maximum tokens to generate
- `--output, -o`: Output file path
- `--benchmark`: Enable benchmarking

## Language Support

Supported language codes:
- `auto`: Auto-detect (default)
- `en`: English
- `zh`: Chinese
- `es`: Spanish
- `fr`: French
- `de`: German
- `ja`: Japanese
- `ko`: Korean

## Tone Control

Use natural language instructions with `--instruct`:
- "Normal tone" (default)
- "Whisper quietly"
- "Speak excitedly"
- "Warm and gentle"
- "Formal announcement"

## File Paths

Default paths:
- App Support: `~/Library/Application Support/QwenVoice/`
- Models: `~/Library/Application Support/QwenVoice/models/`
- Outputs: `~/Library/Application Support/QwenVoice/outputs/`
- Voices: `~/Library/Application Support/QwenVoice/voices/`

## Examples

### Generate a podcast intro

```bash
cli-anything-qwenvoice generate \
  "Welcome to today's episode." \
  --mode design \
  --instruct "Professional podcast host voice, clear and confident" \
  --output intro.wav
```

### Clone a voice for audiobook

```bash
# Enroll the voice
cli-anything-qwenvoice voice enroll "Narrator" narrator.wav \
  --transcript "Full chapter text"

# Generate chapter
cli-anything-qwenvoice generate \
  "Chapter one. Once upon a time..." \
  --mode clone \
  --ref-audio ~/Library/Application\ Support/QwenVoice/voices/Narrator.wav \
  --output chapter1.wav
```

### Multi-language generation

```bash
cli-anything-qwenvoice generate \
  "你好，世界！" \
  --mode design \
  --instruct "Clear young female voice" \
  --language zh \
  --output ni_hao.wav
```

## Architecture

The CLI communicates with the QwenVoice Python backend via JSON-RPC 2.0:

```
CLI (Click) → Core Modules → JSON-RPC Client → Backend Server → MLX Inference
```

Core modules:
- `client.py`: JSON-RPC 2.0 client
- `models.py`: Model management
- `generate.py`: Audio generation
- `voice.py`: Voice enrollment/management

## Troubleshooting

### Backend not found
```
Error: Cannot find QwenVoice backend server.py
```
Provide the server path:
```bash
cli-anything-qwenvoice --server-path /path/to/server.py ping
```

### Model not loaded
```
Error: No model loaded
```
Load a model first:
```bash
cli-anything-qwenvoice model load pro_custom
```

### Invalid audio format
Convert to supported format:
```bash
cli-anything-qwenvoice convert input.m4a --output input.wav
```

## Development

### Running from source

```bash
cd agent-harness/cli_anything/qwenvoice
python qwenvoice_cli.py --help
```

### Testing

```bash
cd agent-harness/cli_anything/qwenvoice/tests
pytest -v
```

## License

This CLI harness is part of the cli-anything project. QwenVoice is licensed separately.

## Credits

- [QwenVoice](https://github.com/PowerBeef/QwenVoice) - Original macOS application
- [Qwen3-TTS](https://github.com/QwenLM/Qwen3-TTS) - TTS engine
- [MLX](https://github.com/ml-explore/mlx) - Inference framework
