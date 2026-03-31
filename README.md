# Qwen3-TTS Workspace

This workspace provides a minimal file-producing client for the existing `oMLX` TTS API.

It intentionally targets the current OpenAI-compatible endpoint:

- `POST /v1/audio/speech`
- `GET /health`
- `GET /v1/models`

It does not add a proxy service or wrap model-specific fields outside the current oMLX contract.
The primary output is a stable local `.wav` file path that another tool such as OpenClaw can consume later.

## Unified contract

Request JSON:

```json
{
  "model": "Qwen3-TTS-12Hz-1.7B-Base-4bit",
  "input": "你好，这是一个测试。",
  "voice": "optional-voice",
  "speed": 1.0,
  "response_format": "wav"
}
```

Notes:

- `voice` is best-effort only.
- Do not depend on `speaker`, `language`, `instruct`, or `ref_audio`.
- Response is WAV bytes with `Content-Type: audio/wav`.
- This workspace saves those bytes to a local `.wav` file and returns the absolute path.

## Python usage

```python
from omlx_tts_client import OMLXTTSClient

client = OMLXTTSClient(
    api_key="1234",
    base_url="http://127.0.0.1:10087",
    default_model="Qwen3-TTS-12Hz-1.7B-Base-4bit",
)

path = client.save_wav(
    "你好，这是一个测试。",
    output_dir="~/Library/Application Support/openclaw/tts",
    file_prefix="openclaw",
)
print(path)
```

## CLI usage

Health check:

```bash
python3 omlx_tts_client.py --api-key 1234 --health
```

Model discovery:

```bash
python3 omlx_tts_client.py --api-key 1234 --list-models
```

Probe candidate oMLX TTS models:

```bash
python3 omlx_tts_probe.py --api-key 1234
```

Synthesize to a stable WAV file:

```bash
python3 omlx_tts_client.py \
  --api-key 1234 \
  --output-dir ~/Library/Application\ Support/openclaw/tts \
  --file-prefix openclaw \
  "你好，这是一个测试。"
```

The command prints the absolute path of the generated `.wav` file.

If you want a fixed filename instead of a generated one:

```bash
python3 omlx_tts_client.py \
  --api-key 1234 \
  --output-dir ~/Library/Application\ Support/openclaw/tts \
  --output-name latest.wav \
  "你好，这是一个测试。"
```

## OpenClaw integration contract

OpenClaw can keep using `oMLX` only:

1. Generate the final text reply.
2. Call `POST /v1/audio/speech`.
3. Save the returned WAV bytes to `OMLX_TTS_OUTPUT_DIR`.
4. Keep the absolute file path for later playback or upload.

Recommended environment variables are provided in [openclaw_tts.env.example](/Users/gengwenhao/Documents/Kimi%20CLI/03Project/Qwen3-tts/openclaw_tts.env.example).

## curl examples

Unauthorized request should return `401`:

```bash
curl -i http://127.0.0.1:10087/v1/models
```

Authorized model discovery:

```bash
curl -s http://127.0.0.1:10087/v1/models \
  -H 'Authorization: Bearer 1234'
```

Basic TTS call:

```bash
curl http://127.0.0.1:10087/v1/audio/speech \
  -H 'Authorization: Bearer 1234' \
  -H 'Content-Type: application/json' \
  -o output.wav \
  -d '{
    "model": "Qwen3-TTS-12Hz-1.7B-Base-4bit",
    "input": "你好，这是一个测试。",
    "voice": "optional-voice",
    "speed": 1.0,
    "response_format": "wav"
  }'
```

For your current machine, `Qwen3-TTS-12Hz-1.7B-Base-4bit` is the verified working oMLX TTS model. `CustomVoice` and `CosyVoice3` are not good defaults under the current `oMLX v0.3.0rc1`.

## Current limitation

This client follows the current `oMLX v0.3.0rc1` TTS contract only. It is a unified basic TTS entrypoint that writes WAV files. It is not a full `Qwen3-TTS CustomVoice` feature wrapper.

## Standalone Qwen3-TTS API

The workspace also includes a standalone local API server that does **not** modify `oMLX`. It talks directly to `mlx-audio` and exposes:

- Base TTS
- Base voice clone with reusable `voice_clone_prompt_id`
- VoiceDesign TTS

Server entrypoint:

- [qwen3_tts_api.py](/Users/gengwenhao/Documents/Kimi%20CLI/03Project/Qwen3-tts/qwen3_tts_api.py)

Environment example:

- [qwen3_tts_api.env.example](/Users/gengwenhao/Documents/Kimi%20CLI/03Project/Qwen3-tts/qwen3_tts_api.env.example)

Dependencies:

- [requirements-api.txt](/Users/gengwenhao/Documents/Kimi%20CLI/03Project/Qwen3-tts/requirements-api.txt)
- [requirements-app.txt](/Users/gengwenhao/Documents/Kimi%20CLI/03Project/Qwen3-tts/requirements-app.txt)

Install API dependencies into the existing `tts` venv:

```bash
source ~/venvs/tts/bin/activate
pip install -r requirements-api.txt
```

Run the service:

```bash
cd "/Users/gengwenhao/Documents/Kimi CLI/03Project/Qwen3-tts"
source ~/venvs/tts/bin/activate

python qwen3_tts_api.py \
  --host 127.0.0.1 \
  --port 10088
```

Optional auth:

```bash
python qwen3_tts_api.py \
  --host 127.0.0.1 \
  --port 10088 \
  --api-key 1234
```

## Managed local service

The workspace also includes an `oMLX`-style control layer for the standalone API:

- [qwen3_tts_service.py](/Users/gengwenhao/Documents/Kimi%20CLI/03Project/Qwen3-tts/qwen3_tts_service.py)
- [qwen3_ttsctl.py](/Users/gengwenhao/Documents/Kimi%20CLI/03Project/Qwen3-tts/qwen3_ttsctl.py)

It manages:

- background start and stop
- health-aware status
- local logs
- LaunchAgent login startup on macOS

Default runtime files:

- `~/Library/Application Support/Qwen3-TTS/config.json`
- `~/Library/Application Support/Qwen3-TTS/logs/server.log`
- `~/Library/Application Support/Qwen3-TTS/run/server.pid`
- `~/Library/LaunchAgents/com.gwh.qwen3tts.api.plist`

Start the managed background service:

```bash
cd "/Users/gengwenhao/Documents/Kimi CLI/03Project/Qwen3-tts"
source ~/venvs/tts/bin/activate

python qwen3_ttsctl.py start
```

Check status:

```bash
python qwen3_ttsctl.py status
```

Stop or restart:

```bash
python qwen3_ttsctl.py stop
python qwen3_ttsctl.py restart
```

Tail recent logs:

```bash
python qwen3_ttsctl.py logs -n 100
```

Install or remove login startup:

```bash
python qwen3_ttsctl.py install-login
python qwen3_ttsctl.py uninstall-login
```

The `status` command prints JSON that includes:

- `status`
- `pid`
- `api_url`
- `loaded_model`
- `prompt_cache_count`
- `log_path`

## Menu bar app

There is also a lightweight macOS menu bar shell that reuses the same `ServerManager`:

- [qwen3_tts_menubar.py](/Users/gengwenhao/Documents/Kimi%20CLI/03Project/Qwen3-tts/qwen3_tts_menubar.py)

It provides:

- Start Server
- Stop Server
- Restart Server
- Copy API URL
- Open Config
- Open Logs
- Open App Support
- Open Models Folder
- Open Settings
- Open API Docs
- Quit

The menu now also shows live status details:

- current API URL
- loaded model
- cached voice clone prompt count

Install GUI dependencies into the existing `tts` venv:

```bash
source ~/venvs/tts/bin/activate
pip install -r requirements-app.txt
```

Run the menu bar app:

```bash
cd "/Users/gengwenhao/Documents/Kimi CLI/03Project/Qwen3-tts"
source ~/venvs/tts/bin/activate

python qwen3_tts_menubar.py
```

This menu bar script is also the source for the packaged `.app` build described below.

## Packaged macOS app

The workspace now includes a self-contained macOS app build pipeline:

- [packaging/build.py](/Users/gengwenhao/Documents/Kimi%20CLI/03Project/Qwen3-tts/packaging/build.py)
- [packaging/README.md](/Users/gengwenhao/Documents/Kimi%20CLI/03Project/Qwen3-tts/packaging/README.md)
- [packaging/venvstacks.toml](/Users/gengwenhao/Documents/Kimi%20CLI/03Project/Qwen3-tts/packaging/venvstacks.toml)

Build the app:

```bash
cd "/Users/gengwenhao/Documents/Kimi CLI/03Project/Qwen3-tts/packaging"
source ~/venvs/tts/bin/activate

python build.py
```

Reuse previously exported environments and rebuild only the app bundle:

```bash
python build.py --skip-venv
```

Output:

```text
packaging/dist/Qwen3-TTS.app
```

### Standalone API contract

Health:

```bash
curl http://127.0.0.1:10088/health
```

Model discovery:

```bash
curl http://127.0.0.1:10088/v1/models \
  -H 'Authorization: Bearer 1234'
```

Base TTS:

```bash
curl http://127.0.0.1:10088/v1/audio/speech \
  -H 'Authorization: Bearer 1234' \
  -H 'Content-Type: application/json' \
  -o base.wav \
  -d '{
    "model": "Qwen3-TTS-12Hz-1.7B-Base-4bit",
    "input": "今天的会议到此结束，谢谢大家。",
    "response_format": "wav"
  }'
```

Create a reusable Base voice clone prompt:

```bash
curl http://127.0.0.1:10088/v1/audio/voice-clone-prompts \
  -H 'Authorization: Bearer 1234' \
  -F 'ref_audio=@./gwh_short.wav' \
  -F 'ref_text=你好，我是耿文豪。今天我们测试一下语音克隆。' \
  -F 'language=Chinese'
```

Use the returned `prompt_id`:

```bash
curl http://127.0.0.1:10088/v1/audio/speech \
  -H 'Authorization: Bearer 1234' \
  -H 'Content-Type: application/json' \
  -o clone.wav \
  -d '{
    "model": "Qwen3-TTS-12Hz-1.7B-Base-4bit",
    "input": "今天的会议到此结束，谢谢大家。",
    "voice_clone_prompt_id": "REPLACE_WITH_PROMPT_ID",
    "lang_code": "chinese",
    "response_format": "wav"
  }'
```

VoiceDesign:

```bash
curl http://127.0.0.1:10088/v1/audio/speech \
  -H 'Authorization: Bearer 1234' \
  -H 'Content-Type: application/json' \
  -o designed.wav \
  -d '{
    "model": "Qwen3-TTS-12Hz-1.7B-VoiceDesign-8bit",
    "input": "欢迎使用新的语音接口。",
    "instruct": "A calm professional female Mandarin voice with clear pronunciation.",
    "response_format": "wav"
  }'
```

Delete a cached clone prompt:

```bash
curl -X DELETE http://127.0.0.1:10088/v1/audio/voice-clone-prompts/REPLACE_WITH_PROMPT_ID \
  -H 'Authorization: Bearer 1234'
```

### Tests

The standalone API tests depend on the `tts` virtualenv because `fastapi` is installed there:

```bash
cd "/Users/gengwenhao/Documents/Kimi CLI/03Project/Qwen3-tts"
source ~/venvs/tts/bin/activate
python -m unittest discover -s tests -p 'test_*.py'
```

## Qwen3 Voice Clone

`oMLX /v1/audio/speech` currently does not expose `ref_audio` and `ref_text`, so it cannot perform `Qwen3-TTS Base` voice cloning.

For local voice clone, use [qwen3_voice_clone.py](/Users/gengwenhao/Documents/Kimi%20CLI/03Project/Qwen3-tts/qwen3_voice_clone.py), which calls `mlx-audio` directly with the Base model.

For clone retests with a new short reference, use [qwen3_clone_retest.py](/Users/gengwenhao/Documents/Kimi%20CLI/03Project/Qwen3-tts/qwen3_clone_retest.py). It validates the reference clip, runs a native `mlx-audio` clone sample first, and can then run the standalone API clone with explicit `lang_code=chinese`.

Reference assets expected in this workspace:

- [gwhgwh.wav](/Users/gengwenhao/Documents/Kimi%20CLI/03Project/Qwen3-tts/gwhgwh.wav)
- [文本.txt](/Users/gengwenhao/Documents/Kimi%20CLI/03Project/Qwen3-tts/文本.txt) or `gwhgwh.txt`

Recommended retest assets:

- `./gwh_short.wav`
- `./gwh_short.txt`

The retest script is strict on purpose:

- reference audio must be mono
- duration must be between 5 and 8 seconds
- API clone requests are sent with `lang_code=chinese`

Native-first retest:

```bash
source ~/venvs/tts/bin/activate

python qwen3_clone_retest.py \
  --phase native \
  --ref-audio ./gwh_short.wav \
  --ref-text-file ./gwh_short.txt
```

If the native sample is intelligible, run the API phase:

```bash
source ~/venvs/tts/bin/activate

python qwen3_clone_retest.py \
  --phase api \
  --api-key 1234 \
  --ref-audio ./gwh_short.wav \
  --ref-text-file ./gwh_short.txt
```

Or run both in one pass:

```bash
source ~/venvs/tts/bin/activate

python qwen3_clone_retest.py \
  --phase both \
  --api-key 1234 \
  --ref-audio ./gwh_short.wav \
  --ref-text-file ./gwh_short.txt
```

Direct mode:

```bash
source ~/venvs/tts/bin/activate

python qwen3_voice_clone.py \
  --mode direct \
  --ref-audio ./gwhgwh.wav \
  --ref-text-file ./文本.txt \
  "今天的会议到此结束，谢谢大家"
```

Cached mode:

```bash
source ~/venvs/tts/bin/activate

python qwen3_voice_clone.py \
  --mode cached \
  --ref-audio ./gwhgwh.wav \
  --ref-text-file ./文本.txt \
  "今天的会议到此结束，谢谢大家"
```

From Python:

```python
from qwen3_voice_clone import tts_clone, tts_clone_batch

path = tts_clone("今天的会议到此结束，谢谢大家")
print(path)

paths = tts_clone_batch(["句子1", "句子2"])
print(paths)
```
