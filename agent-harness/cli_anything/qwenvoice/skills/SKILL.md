---
name: qwenvoice
description: "QwenVoice TTS CLI - Text-to-speech with custom voices, voice design, and voice cloning"
version: "0.1.0"
author: "cli-anything"
license: "MIT"
requirements:
  - "macOS 15+ with Apple Silicon"
  - "Python 3.11+"
  - "QwenVoice backend (server.py)"
homepage: "https://github.com/PowerBeef/QwenVoice"
repository: "https://github.com/PowerBeef/QwenVoice"
keywords:
  - tts
  - text-to-speech
  - voice cloning
  - ml
  - mlx
  - qwen
categories:
  - audio
  - machine-learning
  - productivity
command: "cli-anything-qwenvoice"
---

# QwenVoice CLI Skill

QwenVoice CLI provides command-line access to QwenVoice TTS capabilities, including custom voices, voice design, and voice cloning - all running locally on Apple Silicon using MLX.

## Installation

```bash
pip install cli-anything-qwenvoice
```

Verify installation:
```bash
cli-anything-qwenvoice --help
cli-anything-qwenvoice ping
```

## Quick Start

### 1. Check Available Models

```bash
cli-anything-qwenvoice model list
```

### 2. Generate Speech

#### Custom Voice (built-in speakers)

```bash
cli-anything-qwenvoice generate "Hello, world!" \
  --mode custom \
  --voice vivian \
  --output hello.wav
```

Available speakers: `ryan`, `aiden`, `serena`, `vivian`

#### Voice Design (custom voice from description)

```bash
cli-anything-qwenvoice generate "The quick brown fox." \
  --mode design \
  --instruct "Warm grandmotherly voice" \
  --output fox.wav
```

#### Voice Cloning (clone from reference audio)

```bash
cli-anything-qwenvoice generate "This is a cloned voice." \
  --mode clone \
  --ref-audio reference.wav \
  --output clone.wav
```

## Command Groups

### Model Management

```bash
# List all models
cli-anything-qwenvoice model list

# Load a specific model
cli-anything-qwenvoice model load pro_custom
cli-anything-qwenvoice model load pro_design
cli-anything-qwenvoice model load pro_clone

# Unload current model
cli-anything-qwenvoice model unload

# Get model information
cli-anything-qwenvoice model info pro_custom
```

**Model IDs**:
- `pro_custom` - Custom Voice mode (built-in speakers)
- `pro_design` - Voice Design mode (custom voices)
- `pro_clone` - Voice Cloning mode

### Audio Generation

```bash
# Generate with options
cli-anything-qwenvoice generate "Your text here" \
  --mode custom \
  --voice ryan \
  --instruct "Whisper quietly" \
  --language en \
  --temperature 0.7 \
  --output output.wav
```

**Generation Parameters**:
- `--mode, -m`: Generation mode (custom, design, clone) [required]
- `--voice`: Speaker name (for custom mode)
- `--instruct`: Voice description (for design mode)
- `--ref-audio`: Reference audio path (for clone mode)
- `--ref-text`: Reference transcript (optional, for clone mode)
- `--language, -l`: Language code (default: auto)
- `--temperature, -t`: Sampling temperature 0.0-1.5 (default: 0.6)
- `--max-tokens`: Maximum tokens to generate
- `--output, -o`: Output file path
- `--benchmark`: Enable benchmarking

**Language Codes**:
- `auto` - Auto-detect (default)
- `en` - English
- `zh` - Chinese
- `es` - Spanish
- `fr` - French
- `de` - German
- `ja` - Japanese
- `ko` - Korean

### Batch Generation

```bash
cli-anything-qwenvoice batch batch.json --output-dir ./outputs
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

# Enroll a new voice
cli-anything-qwenvoice voice enroll "MyVoice" sample.wav \
  --transcript "Optional transcript for better accuracy"

# Delete a voice
cli-anything-qwenvoice voice delete "MyVoice"
```

### Audio Conversion

```bash
# Convert audio to 24kHz mono WAV
cli-anything-qwenvoice convert input.mp3 --output output.wav
```

### Other Commands

```bash
# List available speakers
cli-anything-qwenvoice speakers

# Check backend connection
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
  --mode custom --voice vivian --output test.wav
```

Returns:
```json
{
  "output_path": "/path/to/test.wav",
  "duration_seconds": 2.45,
  "timings": {
    "generation_ms": 1500,
    "write_ms": 100
  }
}
```

## Usage Examples

### Generate Podcast Intro

```bash
cli-anything-qwenvoice generate \
  "Welcome to today's episode." \
  --mode design \
  --instruct "Professional podcast host voice, clear and confident" \
  --output intro.wav
```

### Multi-language Generation

```bash
# Chinese
cli-anything-qwenvoice generate \
  "你好，世界！" \
  --mode design \
  --instruct "Clear young female voice" \
  --language zh \
  --output ni_hao.wav

# Spanish
cli-anything-qwenvoice generate \
  "Hola, mundo!" \
  --mode custom \
  --voice ryan \
  --language es \
  --output hola.wav
```

### Clone Voice for Audiobook

```bash
# Enroll voice
cli-anything-qwenvoice voice enroll "Narrator" narrator_sample.wav

# Generate chapter
cli-anything-qwenvoice generate \
  "Chapter one. Once upon a time..." \
  --mode clone \
  --ref-audio ~/Library/Application\ Support/QwenVoice/voices/Narrator.wav \
  --output chapter1.wav
```

### Tone Control Examples

```bash
# Whisper
cli-anything-qwenvoice generate "Psst, listen closely..." \
  --mode custom --voice vivian \
  --instruct "Whisper quietly"

# Excited
cli-anything-qwenvoice generate "This is amazing news!" \
  --mode design --instruct "Speak excitedly"

# Formal
cli-anything-qwenvoice generate "Welcome to the annual meeting." \
  --mode design --instruct "Formal announcement tone"
```

## Agent-Specific Guidance

### For AI Agents Using This CLI

1. **Always load the correct model first**:
   - Use `pro_custom` for built-in speakers
   - Use `pro_design` for custom voice descriptions
   - Use `pro_clone` for voice cloning

2. **Reference audio for cloning**:
   - Must be WAV, MP3, AIFF, M4A, FLAC, or OGG
   - Will be auto-converted to 24kHz mono WAV
   - Optional transcript improves accuracy

3. **Output paths**:
   - If not specified, auto-generated from text
   - Default location: `~/Library/Application Support/QwenVoice/outputs/`

4. **Error handling**:
   - Check if model is loaded before generation
   - Validate audio files exist before cloning
   - Use `--json` flag for programmatic parsing

5. **Best practices**:
   - Use REPL mode for multiple generations (keeps model loaded)
   - Pre-enroll frequently used voices for cloning
   - Use batch generation for multiple clips
   - Adjust temperature (0.3-0.9) for variety vs consistency

## Architecture

```
CLI (Click) → Core Modules → JSON-RPC Client → Backend Server → MLX Inference
```

- **client.py**: JSON-RPC 2.0 communication
- **models.py**: Model loading and management
- **generate.py**: Audio generation orchestration
- **voice.py**: Voice enrollment and management

## Troubleshooting

### "Backend not found"
Provide server path:
```bash
cli-anything-qwenvoice --server-path /path/to/server.py ping
```

### "No model loaded"
Load a model first:
```bash
cli-anything-qwenvoice model load pro_custom
```

### "Invalid audio format"
Convert first:
```bash
cli-anything-qwenvoice convert input.m4a --output input.wav
```

## See Also

- [QwenVoice Repository](https://github.com/PowerBeef/QwenVoice)
- [Qwen3-TTS](https://github.com/QwenLM/Qwen3-TTS)
- [MLX Framework](https://github.com/ml-explore/mlx)
