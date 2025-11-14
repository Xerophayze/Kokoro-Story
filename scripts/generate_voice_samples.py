"""Generate sample audio files for all Kokoro voices.

This script iterates through every voice defined in ``src.voice_manager.VOICES``
and produces a short preview clip that can be played from the UI. The clips
are saved under ``static/samples`` and a manifest file is written so the
frontend knows which sample belongs to which voice.

Usage
-----
python scripts/generate_voice_samples.py [--overwrite] [--device DEVICE] [--text "Sample"]

Options
-------
--overwrite   Regenerate samples even if an audio file already exists.
--device      Force the device for Kokoro ("cuda", "cpu", or "auto", default).
--text        Custom sample text. ``{voice}`` in the text will be replaced with
              the friendly name of the voice.

Requirements
------------
- Kokoro must be installed and functional on the target device.
- The script should be executed from the project root so relative paths match.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from src.voice_manager import VOICES
from src.tts_engine import TTSEngine, KOKORO_AVAILABLE

SAMPLES_DIR = Path("static/samples")
MANIFEST_PATH = SAMPLES_DIR / "manifest.json"
DEFAULT_SAMPLE_TEXT = "Hello! I'm {voice}, and this is my Kokoro preview."  # noqa: E501
SUPPORTED_EXTENSION = "wav"


def build_voice_catalog() -> list[dict]:
    """Flatten the VOICES structure into a list of unique voices."""
    catalog = []
    seen = set()

    for language_key, config in VOICES.items():
        lang_code = config["lang_code"]
        for voice_name in config["voices"]:
            if voice_name in seen:
                continue
            seen.add(voice_name)
            catalog.append({
                "voice": voice_name,
                "lang_code": lang_code,
                "language_key": language_key,
            })

    return catalog


def friendly_voice_name(voice: str) -> str:
    """Convert a voice identifier like ``af_heart`` to ``Af Heart``."""
    return voice.replace("_", " ").title()


def ensure_samples_dir() -> None:
    SAMPLES_DIR.mkdir(parents=True, exist_ok=True)


def load_existing_manifest() -> dict:
    if MANIFEST_PATH.exists():
        try:
            with MANIFEST_PATH.open("r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            print("Warning: manifest.json is invalid JSON. Regenerating.")
    return {}


def synthesize_samples(device: str, overwrite: bool, sample_text: str) -> dict:
    if not KOKORO_AVAILABLE:
        print("Error: Kokoro is not installed. Please install kokoro>=0.9.4.")
        sys.exit(1)

    ensure_samples_dir()

    engine = TTSEngine(device=device)
    manifest = load_existing_manifest()

    catalog = build_voice_catalog()
    print(f"Found {len(catalog)} unique voices to process.")

    for entry in catalog:
        voice_name = entry["voice"]
        lang_code = entry["lang_code"]
        language_key = entry["language_key"]

        filename = f"{voice_name}.{SUPPORTED_EXTENSION}"
        output_path = SAMPLES_DIR / filename

        if output_path.exists() and not overwrite:
            print(f"Skipping {voice_name}: sample already exists (use --overwrite to regenerate).")
            if voice_name not in manifest:
                manifest[voice_name] = {
                    "file": f"/static/samples/{filename}",
                    "lang_code": lang_code,
                    "language_key": language_key,
                }
            continue

        text_to_speak = sample_text.format(voice=friendly_voice_name(voice_name))

        print(f"Generating sample for {voice_name} (lang {lang_code})...")
        try:
            engine.generate_audio(
                text=text_to_speak,
                voice=voice_name,
                lang_code=lang_code,
                speed=1.0,
                output_path=str(output_path)
            )
        except Exception as exc:  # pragma: no cover - defensive
            print(f"  Failed to generate {voice_name}: {exc}")
            continue

        manifest[voice_name] = {
            "file": f"/static/samples/{filename}",
            "lang_code": lang_code,
            "language_key": language_key,
        }

    engine.cleanup()
    return manifest


def save_manifest(manifest: dict) -> None:
    with MANIFEST_PATH.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
    print(f"Manifest written to {MANIFEST_PATH}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate Kokoro voice preview samples")
    parser.add_argument(
        "--device",
        choices=["auto", "cuda", "cpu"],
        default="auto",
        help="Device to use for Kokoro inference (default: auto)",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Regenerate samples even if the audio file already exists",
    )
    parser.add_argument(
        "--text",
        default=DEFAULT_SAMPLE_TEXT,
        help="Sample text to speak (you can use {voice} placeholder)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    manifest = synthesize_samples(
        device=args.device,
        overwrite=args.overwrite,
        sample_text=args.text,
    )
    save_manifest(manifest)


if __name__ == "__main__":
    main()
