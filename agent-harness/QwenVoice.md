# QwenVoice CLI Standard Operating Procedure

## Overview

QwenVoice is a native macOS TTS (Text-to-Speech) application using MLX inference on Apple Silicon. The CLI harness provides a command-line interface to all TTS functionality through a JSON-RPC backend.

## Architecture

- **Backend**: Python JSON-RPC 2.0 server (`server.py`)
- **Inference**: MLX framework with mlx-audio
- **Models**: Three model modes (Custom Voice, Voice Design, Voice Cloning)
- **Storage**: SQLite history + local file system

## Model Modes

### 1. Custom Voice (`custom`)
- Uses built-in English speakers: Ryan, Aiden, Serena, Vivian
- Parameters: `voice` (speaker name), optional `instruct` for tone adjustments
- Model: `Qwen3-TTS-12Hz-1.7B-CustomVoice-8bit`

### 2. Voice Design (`design`)
- Creates custom voices from natural language descriptions
- Parameters: `instruct` (voice description), optional language
- Model: `Qwen3-TTS-12Hz-1.7B-VoiceDesign-8bit`

### 3. Voice Cloning (`clone`)
- Clones voices from reference audio clips
- Parameters: `ref_audio` (path to audio file), optional `ref_text` (transcript)
- Model: `Qwen3-TTS-12Hz-1.7B-Base-8bit`

## Standard Workflow

### 1. Initialization
```bash
# Initialize paths (creates necessary directories)
init [--app-support-dir PATH]
```

### 2. Model Management
```bash
# List available models and check download status
list-models

# Load a model (required before generation)
load-model --model-id pro_custom
load-model --model-id pro_design
load-model --model-id pro_clone

# Unload current model (free memory)
unload-model
```

### 3. Audio Generation

#### Custom Voice Mode
```bash
# Generate with built-in speaker
generate \
  --text "Hello, world!" \
  --mode custom \
  --voice vivian \
  --output output.wav

# With temperature control
generate \
  --text "Hello, world!" \
  --mode custom \
  --voice serena \
  --temperature 0.7 \
  --output output.wav

# With tone instruction
generate \
  --text "Hello, world!" \
  --mode custom \
  --voice ryan \
  --instruct "Whisper quietly" \
  --output output.wav
```

#### Voice Design Mode
```bash
# Generate with voice description
generate \
  --text "Hello, world!" \
  --mode design \
  --instruct "A warm grandmotherly voice" \
  --output output.wav

# Multi-language
generate \
  --text "你好，世界！" \
  --mode design \
  --instruct "Clear young female voice" \
  --language zh \
  --output output.wav
```

#### Voice Cloning Mode
```bash
# Clone from reference audio
generate \
  --text "This is a cloned voice." \
  --mode clone \
  --ref-audio reference.wav \
  --output clone.wav

# With transcript for better accuracy
generate \
  --text "This is a cloned voice." \
  --mode clone \
  --ref-audio reference.wav \
  --ref-text "Reference transcript here" \
  --output clone.wav
```

### 4. Batch Generation

```bash
# Clone batch from JSON file
generate-clone-batch \
  --input batch.json \
  --output-dir ./outputs

# JSON format:
# [
#   {
#     "text": "First sentence",
#     "ref_audio": "ref1.wav",
#     "ref_text": "Optional transcript"
#   },
#   {
#     "text": "Second sentence",
#     "ref_audio": "ref2.wav"
#   }
# ]
```

### 5. Voice Management

```bash
# List enrolled voices
list-voices

# Enroll a new voice
enroll-voice \
  --name "MyVoice" \
  --audio-path sample.wav \
  --transcript "Optional transcript"

# Delete a voice
delete-voice --name "MyVoice"
```

### 6. Audio Conversion

```bash
# Convert audio to 24kHz mono WAV
convert-audio \
  --input input.mp3 \
  --output output.wav
```

## Language Support

Language codes for `--language` parameter:
- `auto`: Auto-detect (default)
- `en`: English
- `zh`: Chinese
- `es`: Spanish
- `fr`: French
- `de`: German
- `ja`: Japanese
- `ko`: Korean

## Tone and Emotion

Tone is controlled via natural language instructions in `--instruct`:
- "Normal tone" (default)
- "Whisper quietly"
- "Speak excitedly"
- "Warm and gentle"
- "Formal announcement"
- "Sad and melancholic"

## Generation Parameters

- `--temperature` (0.0-1.5): Controls randomness (default: 0.6)
  - Lower: More deterministic, conservative
  - Higher: More expressive, varied

- `--max-tokens`: Maximum audio tokens to generate
  - Default: model-specific
  - Longer text may require more tokens

- `--stream`: Enable streaming preview (requires request_id)
- `--streaming-interval`: Seconds between stream chunks (default: 2.0)

## Performance Tips

1. **Model Loading**: First generation after loading a model is slower (warm-up)
2. **Memory**: Only one model in memory at a time
3. **Caching**: Clone contexts are cached for reuse
4. **Batch Processing**: Use `generate-clone-batch` for multiple clips

## Error Handling

Common errors:
- `No model loaded`: Call `load-model` first
- `Unknown generation mode`: Check mode matches loaded model
- `Mode 'custom' requires a voice`: Provide `--voice` parameter
- `Mode 'design' requires instruct`: Provide `--instruct` parameter
- `Mode 'clone' requires ref_audio`: Provide `--ref-audio` parameter

## Paths and Storage

Default paths (macOS):
- App Support: `~/Library/Application Support/QwenVoice/`
- Models: `~/Library/Application Support/QwenVoice/models/`
- Outputs: `~/Library/Application Support/QwenVoice/outputs/`
- Voices: `~/Library/Application Support/QwenVoice/voices/`

Output subfolders by mode:
- Custom Voice: `outputs/CustomVoice/`
- Voice Design: `outputs/VoiceDesign/`
- Voice Cloning: `outputs/Clones/`

## Benchmarking

Use `--benchmark` flag to get detailed timing information:
- Model load time
- Generation time
- Audio write time
- Cache hit/miss status
- Memory allocation stats

## REPL Mode

In REPL mode, the model stays loaded between commands for interactive use:

```bash
cli-anything-qwenvoice repl
> load-model --model-id pro_custom
> generate --text "Hello" --mode custom --voice vivian --output 1.wav
> generate --text "World" --mode custom --voice vivian --output 2.wav
> unload-model
> exit
```

## JSON Output Mode

All commands support `--json` for machine-readable output:

```bash
generate --text "Hello" --mode custom --voice vivian --output out.wav --json
```

Returns:
```json
{
  "success": true,
  "output_path": "/path/to/output.wav",
  "duration_seconds": 2.45,
  "timings": {...}
}
```
