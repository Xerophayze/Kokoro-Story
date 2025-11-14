"""Utilities for generating Kokoro voice preview samples."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, List

from src.voice_manager import VOICES
from src.tts_engine import TTSEngine, KOKORO_AVAILABLE

SAMPLES_DIR = Path("static/samples")
MANIFEST_PATH = SAMPLES_DIR / "manifest.json"
DEFAULT_SAMPLE_TEXT = "Hello! I'm {voice}, and this is my Kokoro preview."
SUPPORTED_EXTENSION = "wav"


logger = logging.getLogger(__name__)


def build_voice_catalog() -> List[Dict[str, str]]:
    """Flatten the VOICES configuration into a catalog of unique voices."""
    catalog: List[Dict[str, str]] = []
    seen = set()

    for language_key, config in VOICES.items():
        lang_code = config["lang_code"]
        for voice_name in config["voices"]:
            if voice_name in seen:
                continue
            seen.add(voice_name)
            catalog.append(
                {
                    "voice": voice_name,
                    "lang_code": lang_code,
                    "language_key": language_key,
                }
            )

    return catalog


def friendly_voice_name(voice: str) -> str:
    """Convert a voice identifier like ``af_heart`` to ``Heart``."""
    if not voice:
        return ""

    parts = voice.split("_")
    if len(parts) > 1:
        core = parts[1:]
    else:
        core = parts

    return " ".join(core).title()


def ensure_samples_dir() -> None:
    SAMPLES_DIR.mkdir(parents=True, exist_ok=True)


def load_existing_manifest() -> Dict[str, Dict]:
    if MANIFEST_PATH.exists():
        try:
            with MANIFEST_PATH.open("r", encoding="utf-8") as handle:
                return json.load(handle)
        except json.JSONDecodeError:
            # Invalid manifest – start fresh
            return {}
    return {}


def save_manifest(manifest: Dict[str, Dict]) -> None:
    with MANIFEST_PATH.open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2, sort_keys=True)


def generate_voice_samples(
    *,
    overwrite: bool = False,
    device: str = "auto",
    sample_text: str = DEFAULT_SAMPLE_TEXT,
) -> Dict[str, object]:
    """Generate preview audio samples for every Kokoro voice.

    Returns a manifest mapping voice names -> metadata containing file path,
    lang_code and language key. The manifest is persisted to
    ``static/samples/manifest.json``.
    """
    if not KOKORO_AVAILABLE:
        raise RuntimeError(
            "Kokoro is not installed. Install kokoro>=0.9.4 to generate samples."
        )

    if not sample_text:
        sample_text = DEFAULT_SAMPLE_TEXT

    ensure_samples_dir()
    manifest = load_existing_manifest()
    generated: List[str] = []
    skipped_existing: List[str] = []
    failed: List[Dict[str, str]] = []

    engine = TTSEngine(device=device)
    catalog = build_voice_catalog()

    for entry in catalog:
        voice_name = entry["voice"]
        lang_code = entry["lang_code"]
        language_key = entry["language_key"]

        filename = f"{voice_name}.{SUPPORTED_EXTENSION}"
        output_path = SAMPLES_DIR / filename

        if output_path.exists() and not overwrite:
            if voice_name not in manifest:
                manifest[voice_name] = {
                    "file": f"/static/samples/{filename}",
                    "lang_code": lang_code,
                    "language_key": language_key,
                }
            skipped_existing.append(voice_name)
            continue

        rendered_text = sample_text.format(voice=friendly_voice_name(voice_name))

        try:
            engine.generate_audio(
                text=rendered_text,
                voice=voice_name,
                lang_code=lang_code,
                speed=1.0,
                output_path=str(output_path),
            )
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error("Failed to generate preview for %s: %s", voice_name, exc)
            failed.append({
                "voice": voice_name,
                "lang_code": lang_code,
                "language_key": language_key,
                "error": str(exc),
            })
            # Remove partially written file if any
            if output_path.exists():
                try:
                    output_path.unlink()
                except OSError:
                    pass
            continue

        manifest[voice_name] = {
            "file": f"/static/samples/{filename}",
            "lang_code": lang_code,
            "language_key": language_key,
        }
        generated.append(voice_name)

    engine.cleanup()
    save_manifest(manifest)
    return {
        "manifest": manifest,
        "generated": generated,
        "skipped_existing": skipped_existing,
        "failed": failed,
    }
