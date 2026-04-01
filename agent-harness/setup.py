"""
QwenVoice CLI - setup.py
Package configuration for cli-anything-qwenvoice
"""

from setuptools import setup, find_namespace_packages
import os

here = os.path.abspath(os.path.dirname(__file__))

# Read README for long description
readme_path = os.path.join(os.path.dirname(here), "README.md")
if os.path.exists(readme_path):
    with open(readme_path, "r", encoding="utf-8") as f:
        long_description = f.read()
else:
    long_description = "CLI harness for QwenVoice TTS system"

setup(
    name="cli-anything-qwenvoice",
    version="0.1.0",
    description="Command-line interface for QwenVoice TTS with custom voices and cloning",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="cli-anything",
    author_email="",
    url="https://github.com/PowerBeef/QwenVoice",
    project_urls={
        "Bug Reports": "https://github.com/PowerBeef/QwenVoice/issues",
        "Source": "https://github.com/PowerBeef/QwenVoice",
    },

    packages=find_namespace_packages(
        include=["cli_anything.*"],
        exclude=["*.tests", "*.tests.*", "tests.*", "tests"],
    ),

    package_data={
        "cli_anything.qwenvoice": [
            "README.md",
            "skills/SKILL.md",
        ],
    },

    python_requires=">=3.11",

    install_requires=[
        "click>=8.0.0",
    ],

    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "pytest-cov>=4.0.0",
        ],
    },

    entry_points={
        "console_scripts": [
            "cli-anything-qwenvoice=cli_anything.qwenvoice.qwenvoice_cli:cli",
        ],
    },

    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Intended Audience :: End Users/Desktop",
        "Topic :: Multimedia :: Sound/Audio :: Speech",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "Operating System :: MacOS",
        "Environment :: Console",
    ],

    keywords="tts text-to-speech voice cloning ml mlx qwen",

    license="MIT",

    zip_safe=False,
)
