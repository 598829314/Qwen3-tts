#!/usr/bin/env python3

from __future__ import annotations

import argparse
import importlib.util
import os
import plistlib
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
BUILD_DIR = SCRIPT_DIR / "_build"
EXPORT_DIR = SCRIPT_DIR / "_export"
DIST_DIR = SCRIPT_DIR / "dist"
APP_NAME = "Qwen3-TTS"
APP_BUNDLE = f"{APP_NAME}.app"
PYTHON_SERIES = "3.12"
RUNTIME_LAYER = "cpython-3.12"
FRAMEWORK_LAYER = "framework-qwen3-tts-framework"
APP_LAYER = "app-qwen3-tts-app"

RESOURCE_FILES = [
    "README.md",
    "qwen3_clone_retest.py",
    "qwen3_tts_api.py",
    "qwen3_tts_service.py",
    "qwen3_ttsctl.py",
    "qwen3_tts_menubar.py",
    "qwen3_tts_paths.py",
    "qwen3_voice_clone.py",
]

RESOURCE_DIRS = [
    "packaging/qwen3_tts_app",
    "assets",
]


def run_cmd(cmd: list[str], cwd: Path | None = None, env: dict[str, str] | None = None) -> None:
    print(f"  -> {' '.join(str(part) for part in cmd)}")
    result = subprocess.run(cmd, cwd=cwd, env=env, check=False)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def ensure_venvstacks_available() -> list[str]:
    if importlib.util.find_spec("venvstacks") is not None:
        return [sys.executable, "-m", "venvstacks"]

    binary = shutil.which("venvstacks")
    if binary:
        return [binary]

    raise SystemExit(
        "venvstacks is not installed. Activate your build environment and run: pip install venvstacks"
    )


def clean_all(preserve_venv: bool = False) -> None:
    for path in (DIST_DIR, BUILD_DIR):
        if path.exists():
            shutil.rmtree(path)
    if not preserve_venv and EXPORT_DIR.exists():
        shutil.rmtree(EXPORT_DIR)


def build_venvstacks() -> None:
    print("\n[1/3] Building venvstacks environments...")
    venvstacks = ensure_venvstacks_available()
    if EXPORT_DIR.exists():
        shutil.rmtree(EXPORT_DIR)
    if BUILD_DIR.exists():
        shutil.rmtree(BUILD_DIR)

    stage_root = Path(tempfile.gettempdir()) / "qwen3_tts_packaging_stage"
    if stage_root.exists():
        shutil.rmtree(stage_root)
    stage_root.mkdir(parents=True, exist_ok=True)

    stage_toml = stage_root / "venvstacks.toml"
    shutil.copy2(SCRIPT_DIR / "venvstacks.toml", stage_toml)
    shutil.copytree(SCRIPT_DIR / "qwen3_tts_app", stage_root / "qwen3_tts_app")
    stage_export_dir = stage_root / "_export"
    stage_build_dir = stage_root / "_build"

    run_cmd(venvstacks + ["lock", str(stage_toml), "--if-needed"], cwd=stage_root)
    run_cmd(venvstacks + ["build", str(stage_toml), "--no-lock"], cwd=stage_root)
    run_cmd(
        venvstacks
        + [
            "local-export",
            str(stage_toml),
            "--output-dir",
            str(stage_export_dir),
        ],
        cwd=stage_root,
    )

    shutil.copytree(stage_export_dir, EXPORT_DIR, symlinks=True)
    if stage_build_dir.exists():
        shutil.copytree(stage_build_dir, BUILD_DIR, symlinks=True)


def _copy_tree(src: Path, dst: Path) -> None:
    shutil.copytree(
        src,
        dst,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )


def _create_c_launcher(macos_dir: Path) -> None:
    launcher_c = macos_dir / "_launcher.c"
    launcher_c.write_text(
        r'''
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <limits.h>
#include <dlfcn.h>
#include <mach-o/dyld.h>

typedef int (*py_bytes_main_fn)(int, char **);

static void show_error(const char *msg) {
    char cmd[2048];
    snprintf(cmd, sizeof(cmd),
        "osascript -e 'display dialog \"%s\" buttons {\"OK\"} "
        "default button 1 with icon stop with title \"Qwen3-TTS\"'",
        msg);
    system(cmd);
}

int main(int argc, char *argv[]) {
    char exe_buf[PATH_MAX];
    char resolved[PATH_MAX];
    uint32_t size = sizeof(exe_buf);

    if (_NSGetExecutablePath(exe_buf, &size) != 0) {
        show_error("Failed to get executable path.");
        return 1;
    }
    if (!realpath(exe_buf, resolved)) {
        show_error("Failed to resolve executable path.");
        return 1;
    }

    char *slash = strrchr(resolved, '/');
    if (!slash) { show_error("Invalid executable path."); return 1; }
    *slash = '\0';
    char macos_dir[PATH_MAX];
    strncpy(macos_dir, resolved, sizeof(macos_dir) - 1);

    slash = strrchr(resolved, '/');
    if (!slash) { show_error("Invalid bundle path."); return 1; }
    *slash = '\0';
    char contents_dir[PATH_MAX];
    strncpy(contents_dir, resolved, sizeof(contents_dir) - 1);

    char frameworks_dir[PATH_MAX];
    snprintf(frameworks_dir, sizeof(frameworks_dir), "%s/Frameworks", contents_dir);

    char pythonhome[PATH_MAX];
    snprintf(pythonhome, sizeof(pythonhome), "%s/cpython-3.12", frameworks_dir);
    setenv("PYTHONHOME", pythonhome, 1);

    char pythonpath[PATH_MAX * 4];
    snprintf(
        pythonpath,
        sizeof(pythonpath),
        "%s/Resources:%s/app-qwen3-tts-app/lib/python3.12/site-packages:%s/framework-qwen3-tts-framework/lib/python3.12/site-packages",
        contents_dir, frameworks_dir, frameworks_dir
    );
    setenv("PYTHONPATH", pythonpath, 1);
    setenv("PYTHONDONTWRITEBYTECODE", "1", 1);

    char libpython[PATH_MAX];
    snprintf(libpython, sizeof(libpython), "%s/lib/libpython3.12.dylib", contents_dir);
    void *py = dlopen(libpython, RTLD_NOW | RTLD_GLOBAL);
    if (!py) {
        show_error("Failed to load bundled libpython.");
        return 1;
    }

    py_bytes_main_fn py_bytes_main = (py_bytes_main_fn)dlsym(py, "Py_BytesMain");
    if (!py_bytes_main) {
        show_error("Failed to resolve Py_BytesMain.");
        return 1;
    }

    char *py_argv[] = {"Qwen3-TTS", "-m", "qwen3_tts_app", NULL};
    return py_bytes_main(3, py_argv);
}
''',
        encoding="utf-8",
    )

    launcher_bin = macos_dir / APP_NAME
    result = subprocess.run(
        [
            "cc",
            "-arch",
            "arm64",
            "-mmacosx-version-min=14.0",
            "-O2",
            "-o",
            str(launcher_bin),
            str(launcher_c),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(f"launcher compilation failed:\n{result.stderr}")
    launcher_c.unlink(missing_ok=True)
    launcher_bin.chmod(0o755)


def _render_svg_with_appkit(svg_path: Path, png_path: Path) -> bool:
    script = f"""
import sys
from Foundation import NSData
from AppKit import NSImage, NSBitmapImageRep, NSPNGFileType, NSMakeRect, NSCompositingOperationSourceOver
from AppKit import NSGraphicsContext, NSImageInterpolationHigh

svg_data = NSData.dataWithContentsOfFile_(r"{svg_path}")
if svg_data is None:
    sys.exit(1)

image = NSImage.alloc().initWithData_(svg_data)
if image is None:
    sys.exit(1)

size = 1024
out_image = NSImage.alloc().initWithSize_((size, size))
out_image.lockFocus()
ctx = NSGraphicsContext.currentContext()
ctx.setImageInterpolation_(NSImageInterpolationHigh)
image.drawInRect_fromRect_operation_fraction_(
    NSMakeRect(0, 0, size, size),
    NSMakeRect(0, 0, image.size().width, image.size().height),
    NSCompositingOperationSourceOver,
    1.0,
)
out_image.unlockFocus()
rep = NSBitmapImageRep.alloc().initWithData_(out_image.TIFFRepresentation())
png_data = rep.representationUsingType_properties_(NSPNGFileType, {{}})
png_data.writeToFile_atomically_(r"{png_path}", True)
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0 and png_path.exists()


def _png_to_icns(png_path: Path, icon_path: Path, resources_dir: Path) -> None:
    iconset_dir = resources_dir / "AppIcon.iconset"
    if iconset_dir.exists():
        shutil.rmtree(iconset_dir)
    iconset_dir.mkdir(exist_ok=True)

    sizes = [
        (16, "icon_16x16.png"),
        (32, "icon_16x16@2x.png"),
        (32, "icon_32x32.png"),
        (64, "icon_32x32@2x.png"),
        (128, "icon_128x128.png"),
        (256, "icon_128x128@2x.png"),
        (256, "icon_256x256.png"),
        (512, "icon_256x256@2x.png"),
        (512, "icon_512x512.png"),
        (1024, "icon_512x512@2x.png"),
    ]

    for size, name in sizes:
        output = iconset_dir / name
        shutil.copy2(png_path, output)
        subprocess.run(
            ["sips", "-z", str(size), str(size), str(output)],
            capture_output=True,
            check=False,
        )

    subprocess.run(
        ["iconutil", "-c", "icns", str(iconset_dir), "-o", str(icon_path)],
        capture_output=True,
        check=False,
    )
    shutil.rmtree(iconset_dir, ignore_errors=True)


def create_app_icon(resources_dir: Path) -> None:
    svg_path = resources_dir / "assets" / "app-icon.svg"
    if not svg_path.exists():
        return

    png_path = resources_dir / "_AppIcon.png"
    icon_path = resources_dir / "AppIcon.icns"
    if _render_svg_with_appkit(svg_path, png_path):
        _png_to_icns(png_path, icon_path, resources_dir)
    png_path.unlink(missing_ok=True)


def create_app_bundle() -> Path:
    print("\n[2/3] Creating app bundle...")

    app_dir = DIST_DIR / APP_BUNDLE
    contents_dir = app_dir / "Contents"
    macos_dir = contents_dir / "MacOS"
    resources_dir = contents_dir / "Resources"
    frameworks_dir = contents_dir / "Frameworks"
    lib_dir = contents_dir / "lib"

    if app_dir.exists():
        shutil.rmtree(app_dir)
    macos_dir.mkdir(parents=True)
    resources_dir.mkdir(parents=True)
    frameworks_dir.mkdir(parents=True)
    lib_dir.mkdir(parents=True)

    for layer in (RUNTIME_LAYER, FRAMEWORK_LAYER, APP_LAYER):
        src = EXPORT_DIR / layer
        if not src.exists():
            raise SystemExit(f"missing exported layer: {src}")
        shutil.copytree(src, frameworks_dir / layer, symlinks=True)

    for rel_path in RESOURCE_FILES:
        shutil.copy2(PROJECT_ROOT / rel_path, resources_dir / Path(rel_path).name)

    for rel_dir in RESOURCE_DIRS:
        src_dir = PROJECT_ROOT / rel_dir
        dst_dir = resources_dir / Path(rel_dir).name
        _copy_tree(src_dir, dst_dir)

    create_app_icon(resources_dir)

    runtime_python = frameworks_dir / RUNTIME_LAYER / "bin" / "python3"
    if not runtime_python.exists():
        raise SystemExit(f"missing runtime python: {runtime_python}")

    macos_python = macos_dir / "python3"
    shutil.copy2(runtime_python, macos_python)
    macos_python.chmod(0o755)

    (lib_dir / "libpython3.12.dylib").symlink_to(
        "../Frameworks/cpython-3.12/lib/libpython3.12.dylib"
    )

    _create_c_launcher(macos_dir)

    ctl_launcher = macos_dir / "qwen3-ttsctl"
    ctl_launcher.write_text(
        "#!/bin/bash\n"
        'DIR="$(cd "$(dirname "$0")" && pwd)"\n'
        'CONTENTS="$(dirname "$DIR")"\n'
        'LAYERS="$CONTENTS/Frameworks"\n'
        'export PYTHONHOME="$LAYERS/cpython-3.12"\n'
        'export PYTHONPATH="$CONTENTS/Resources:$LAYERS/app-qwen3-tts-app/lib/python3.12/site-packages:$LAYERS/framework-qwen3-tts-framework/lib/python3.12/site-packages"\n'
        'export PYTHONDONTWRITEBYTECODE=1\n'
        'exec "$DIR/python3" "$CONTENTS/Resources/qwen3_ttsctl.py" "$@"\n',
        encoding="utf-8",
    )
    ctl_launcher.chmod(0o755)

    info_plist = {
        "CFBundleName": APP_NAME,
        "CFBundleDisplayName": APP_NAME,
        "CFBundleIdentifier": "com.gwh.qwen3tts.app",
        "CFBundleVersion": "0.1.0",
        "CFBundleShortVersionString": "0.1.0",
        "CFBundleExecutable": APP_NAME,
        "CFBundlePackageType": "APPL",
        "CFBundleIconFile": "AppIcon",
        "LSMinimumSystemVersion": "14.0",
        "LSUIElement": True,
        "NSHighResolutionCapable": True,
        "LSArchitecturePriority": ["arm64"],
    }
    with open(contents_dir / "Info.plist", "wb") as handle:
        plistlib.dump(info_plist, handle)

    print(f"  created {app_dir}")
    return app_dir


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the Qwen3-TTS macOS app bundle.")
    parser.add_argument(
        "--skip-venv",
        action="store_true",
        help="Reuse the existing exported venvstacks environments.",
    )
    args = parser.parse_args()

    print(f"Building {APP_NAME}.app")
    clean_all(preserve_venv=args.skip_venv)
    DIST_DIR.mkdir(parents=True, exist_ok=True)

    if not args.skip_venv or not EXPORT_DIR.exists():
        build_venvstacks()
    app_dir = create_app_bundle()

    print("\n[3/3] Done.")
    print(app_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
