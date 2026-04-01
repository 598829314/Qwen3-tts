#!/usr/bin/env python3
"""
QwenVoice CLI - Main Entry Point
Command-line interface for QwenVoice TTS system.
"""

import sys
import json
import os
from pathlib import Path
from typing import Optional, Any

import click

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from core import QwenVoiceClient, ModelManager, Generator, VoiceManager
from utils import (
    resolve_output_path,
    print_json,
    read_batch_file,
    validate_audio_file,
    get_default_app_support_dir,
    validate_temperature,
    validate_language,
)

# Global state
ctx = {
    "client": None,
    "model_manager": None,
    "generator": None,
    "voice_manager": None,
    "json_output": False,
    "verbose": False,
}


def init_client(
    server_path: Optional[str] = None,
    app_support_dir: Optional[str] = None,
):
    """Initialize the RPC client and managers."""
    client = QwenVoiceClient(
        server_path=server_path,
        app_support_dir=app_support_dir or get_default_app_support_dir(),
    )
    client.start()

    ctx["client"] = client
    ctx["model_manager"] = ModelManager(client)
    ctx["generator"] = Generator(client, ctx["model_manager"])
    ctx["voice_manager"] = VoiceManager(client)

    return client


def cleanup_client():
    """Cleanup the RPC client."""
    if ctx.get("client"):
        ctx["client"].stop()
        ctx["client"] = None


def print_output(data: Any, json_mode: Optional[bool] = None):
    """Print output in text or JSON format."""
    if json_mode or ctx.get("json_output"):
        print_json(data)
    else:
        if isinstance(data, str):
            print(data)
        elif isinstance(data, dict):
            if data.get("success"):
                result = data.get("result", data)
                if isinstance(result, dict):
                    for key, value in result.items():
                        print(f"{key}: {value}")
                else:
                    print(result)
            else:
                print(data)
        else:
            print(data)


# Main CLI group
@click.group()
@click.option(
    "--json", "json_output",
    is_flag=True,
    help="Output in JSON format",
)
@click.option(
    "--verbose", "-v",
    is_flag=True,
    help="Verbose output",
)
@click.option(
    "--server-path",
    help="Path to server.py (auto-detected if not provided)",
)
@click.option(
    "--app-support-dir",
    help="Custom app support directory",
)
@click.pass_context
def cli(
    ctx_click,
    json_output,
    verbose,
    server_path,
    app_support_dir,
):
    """QwenVoice CLI - Text-to-Speech with custom voices, voice design, and cloning."""
    ctx_click.ensure_object(dict)

    # Store options in context
    ctx["json_output"] = json_output
    ctx["verbose"] = verbose

    # Initialize client for non-repl commands
    if ctx_click.invoked_subcommand != "repl":
        try:
            init_client(server_path, app_support_dir)
        except Exception as e:
            click.echo(f"Error initializing client: {e}", err=True)
            sys.exit(1)


@cli.command()
@click.option(
    "--app-support-dir",
    help="Custom app support directory",
)
def init(app_support_dir):
    """Initialize QwenVoice directories."""
    # Client auto-initializes on start
    result = ctx["client"]._call("init", {
        "app_support_dir": app_support_dir or get_default_app_support_dir(),
    })
    print_output(result)
    cleanup_client()


# Model management commands
@cli.group()
def model():
    """Model management commands."""
    pass


@model.command("list")
@click.option(
    "--format", "output_format",
    type=click.Choice(["table", "json"]),
    default="table",
    help="Output format",
)
def list_models(output_format):
    """List available models."""
    models = ctx["model_manager"].list_models()

    if output_format == "json" or ctx["json_output"]:
        print_json(models)
    else:
        ctx["model_manager"].print_model_table(models)

    cleanup_client()


@model.command("load")
@click.argument(
    "model_id",
    type=click.Choice(["pro_custom", "pro_design", "pro_clone"]),
)
@click.option(
    "--benchmark",
    is_flag=True,
    help="Enable benchmarking",
)
def load_model(model_id, benchmark):
    """Load a model into memory."""
    try:
        result = ctx["model_manager"].load_model(model_id, benchmark=benchmark)

        if ctx["json_output"]:
            print_json(result)
        else:
            click.echo(f"✓ Model loaded: {model_id}")
            if benchmark and result.get("timings"):
                click.echo(f"  Load time: {result['timings'].get('load_ms', 0)}ms")

    except Exception as e:
        click.echo(f"Error loading model: {e}", err=True)
        sys.exit(1)
    finally:
        cleanup_client()


@model.command("unload")
def unload_model():
    """Unload the current model."""
    result = ctx["model_manager"].unload_model()
    print_output({"success": True, "result": result})
    cleanup_client()


@model.command("info")
@click.argument("model_id", required=False)
def model_info(model_id):
    """Get information about models."""
    if model_id:
        info = ctx["model_manager"].get_model(model_id)
        if info:
            print_output(info)
        else:
            click.echo(f"Model not found: {model_id}", err=True)
            sys.exit(1)
    else:
        models = ctx["model_manager"].list_models()
        print_output(models)

    cleanup_client()


# Generation commands
@cli.command()
@click.argument("text")
@click.option(
    "--mode", "-m",
    type=click.Choice(["custom", "design", "clone"]),
    required=True,
    help="Generation mode",
)
@click.option(
    "--voice",
    help="Speaker name (for custom mode)",
)
@click.option(
    "--instruct",
    help="Voice description (for design mode)",
)
@click.option(
    "--ref-audio",
    help="Reference audio path (for clone mode)",
)
@click.option(
    "--ref-text",
    help="Reference transcript (for clone mode)",
)
@click.option(
    "--output", "-o",
    help="Output file path",
)
@click.option(
    "--language", "-l",
    help="Language code (default: auto)",
)
@click.option(
    "--temperature", "-t",
    type=float,
    default=0.6,
    help="Sampling temperature (0.0-1.5)",
)
@click.option(
    "--max-tokens",
    type=int,
    help="Maximum tokens to generate",
)
@click.option(
    "--benchmark",
    is_flag=True,
    help="Enable benchmarking",
)
def generate(
    text,
    mode,
    voice,
    instruct,
    ref_audio,
    ref_text,
    output,
    language,
    temperature,
    max_tokens,
    benchmark,
):
    """Generate audio from text."""
    try:
        # Validate temperature
        if not validate_temperature(temperature):
            click.echo("Error: temperature must be between 0.0 and 1.5", err=True)
            sys.exit(1)

        # Validate language
        if language and not validate_language(language):
            click.echo(f"Warning: language code '{language}' may not be supported", err=True)

        # Validate ref_audio for clone mode
        if mode == "clone" and ref_audio and not validate_audio_file(ref_audio):
            click.echo(f"Error: invalid audio file: {ref_audio}", err=True)
            sys.exit(1)

        # Resolve output path
        if not output:
            output = resolve_output_path(text, mode, voice=voice)

        # Generate
        result = ctx["generator"].generate(
            text=text,
            mode=mode,
            voice=voice,
            instruct=instruct,
            ref_audio=ref_audio,
            ref_text=ref_text,
            language=language,
            temperature=temperature,
            max_tokens=max_tokens,
            output_path=output,
            benchmark=benchmark,
        )

        if ctx["json_output"]:
            print_json(result)
        else:
            from core import format_generation_result
            click.echo(format_generation_result(result, verbose=ctx["verbose"]))

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    finally:
        cleanup_client()


@cli.command("batch")
@click.argument("input_file", type=click.Path(exists=True))
@click.option(
    "--mode", "-m",
    type=click.Choice(["clone"]),
    default="clone",
    help="Generation mode",
)
@click.option(
    "--output-dir", "-o",
    help="Output directory",
)
@click.option(
    "--language", "-l",
    help="Language code",
)
@click.option(
    "--temperature", "-t",
    type=float,
    default=0.6,
    help="Sampling temperature",
)
@click.option(
    "--benchmark",
    is_flag=True,
    help="Enable benchmarking",
)
def generate_batch(
    input_file,
    mode,
    output_dir,
    language,
    temperature,
    benchmark,
):
    """Generate audio from batch file."""
    try:
        # Read batch file
        items = read_batch_file(input_file)

        # Generate
        result = ctx["generator"].generate_batch(
            items=items,
            mode=mode,
            language=language,
            temperature=temperature,
            benchmark=benchmark,
            output_dir=output_dir,
        )

        if ctx["json_output"]:
            print_json(result)
        else:
            click.echo(f"✓ Generated {len(result.get('outputs', []))} files")
            if output_dir:
                click.echo(f"  Output directory: {output_dir}")

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    finally:
        cleanup_client()


# Voice management commands
@cli.group()
def voice():
    """Voice management commands."""
    pass


@voice.command("list")
@click.option(
    "--format", "output_format",
    type=click.Choice(["table", "json"]),
    default="table",
    help="Output format",
)
def list_voices(output_format):
    """List enrolled voices."""
    voices = ctx["voice_manager"].list_voices()

    if output_format == "json" or ctx["json_output"]:
        print_json(voices)
    else:
        ctx["voice_manager"].print_voice_table(voices)

    cleanup_client()


@voice.command("enroll")
@click.argument("name")
@click.argument("audio_path", type=click.Path(exists=True))
@click.option(
    "--transcript", "-t",
    help="Optional transcript for better accuracy",
)
def enroll_voice(name, audio_path, transcript):
    """Enroll a new voice for cloning."""
    try:
        result = ctx["voice_manager"].enroll_voice(
            name=name,
            audio_path=audio_path,
            transcript=transcript or "",
        )

        if ctx["json_output"]:
            print_json(result)
        else:
            click.echo(f"✓ Voice enrolled: {result['name']}")
            click.echo(f"  Path: {result['wav_path']}")

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    finally:
        cleanup_client()


@voice.command("delete")
@click.argument("name")
def delete_voice(name):
    """Delete an enrolled voice."""
    try:
        result = ctx["voice_manager"].delete_voice(name)

        if ctx["json_output"]:
            print_json(result)
        else:
            click.echo(f"✓ Voice deleted: {name}")

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    finally:
        cleanup_client()


# Audio conversion command
@cli.command()
@click.argument("input_path", type=click.Path(exists=True))
@click.option(
    "--output", "-o",
    help="Output WAV path",
)
def convert(input_path, output):
    """Convert audio to 24kHz mono WAV."""
    try:
        result = ctx["client"].convert_audio(input_path, output)

        if ctx["json_output"]:
            print_json(result)
        else:
            click.echo(f"✓ Converted: {result['wav_path']}")

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    finally:
        cleanup_client()


# Speakers command
@cli.command()
def speakers():
    """List available speakers."""
    speakers = ctx["client"].get_speakers()

    if ctx["json_output"]:
        print_json(speakers)
    else:
        for language, speaker_list in speakers.items():
            click.echo(f"{language}:")
            for speaker in speaker_list:
                click.echo(f"  - {speaker}")

    cleanup_client()


# PING command
@cli.command()
def ping():
    """Check if the backend is alive."""
    try:
        result = ctx["client"].ping()
        print_output(result)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    finally:
        cleanup_client()


# REPL command
@cli.command()
@click.option(
    "--server-path",
    help="Path to server.py",
)
@click.option(
    "--app-support-dir",
    help="Custom app support directory",
)
def repl(server_path, app_support_dir):
    """Start interactive REPL mode."""
    click.echo("QwenVoice CLI - REPL Mode")
    click.echo("Type 'help' for commands, 'exit' to quit")
    click.echo("-" * 40)

    # Initialize client
    init_client(server_path, app_support_dir)

    try:
        while True:
            try:
                # Read command
                user_input = input("qwenvoice> ").strip()

                if not user_input:
                    continue

                if user_input.lower() in ("exit", "quit"):
                    break

                if user_input.lower() == "help":
                    click.echo("""
Available commands:
  model list                    List models
  model load <model_id>         Load a model
  model unload                  Unload current model
  generate <text> [options]     Generate audio
  voice list                    List enrolled voices
  voice enroll <name> <path>    Enroll a voice
  voice delete <name>           Delete a voice
  convert <path>                Convert audio
  speakers                      List speakers
  ping                          Check backend
  exit                          Exit REPL
                    """)
                    continue

                # Execute command (simple parsing)
                import shlex
                parts = shlex.split(user_input)
                if not parts:
                    continue

                # Build CLI args and invoke
                from click.testing import CliRunner
                runner = CliRunner()

                # Standalone commands
                command_args = parts[1:] if len(parts) > 1 else []

                # Invoke through CLI
                try:
                    result = runner.invoke(
                        cli,
                        parts,
                        catch_exceptions=False,
                        standalone_mode=False,
                    )
                    if result.output:
                        click.echo(result.output)
                except SystemExit:
                    pass
                except Exception as e:
                    click.echo(f"Error: {e}", err=True)

            except EOFError:
                break
            except KeyboardInterrupt:
                click.echo("\nUse 'exit' to quit")

    finally:
        cleanup_client()
        click.echo("\nGoodbye!")


if __name__ == "__main__":
    # For REPL mode, handle cleanup specially
    if len(sys.argv) > 1 and sys.argv[1] == "repl":
        cli(standalone_mode=False)
    else:
        cli()
