"""
Custom voice storage utilities for TTS-Story.

Allows creation of blended voices composed of existing Kokoro voice packs.
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Dict, List, Optional


DATA_DIR = Path("data")
DATA_DIR.mkdir(parents=True, exist_ok=True)
CUSTOM_VOICE_PATH = DATA_DIR / "custom_voices.json"
CUSTOM_CODE_PREFIX = "custom_"


def _load_payload() -> List[Dict]:
    if not CUSTOM_VOICE_PATH.exists():
        return []
    try:
        with CUSTOM_VOICE_PATH.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
            if isinstance(data, list):
                return data
    except json.JSONDecodeError:
        pass
    return []


def _save_payload(items: List[Dict]) -> None:
    with CUSTOM_VOICE_PATH.open("w", encoding="utf-8") as fh:
        json.dump(items, fh, indent=2)


def list_custom_voices() -> List[Dict]:
    """Return raw custom voice definitions (internal storage format)."""
    return _load_payload()


def list_custom_voice_entries() -> List[Dict]:
    """Return normalized custom voice entries with public codes."""
    return [_to_public_entry(item) for item in _load_payload()]


def get_custom_voice(voice_id: str) -> Optional[Dict]:
    """Retrieve a single custom voice definition by id."""
    for item in _load_payload():
        if item.get("id") == voice_id:
            return item
    return None


def save_custom_voice(voice: Dict) -> Dict:
    """
    Persist a new custom voice definition.

    Args:
        voice: dict containing id, name, lang_code, components, and metadata
    """
    items = _load_payload()
    existing_ids = {item.get("id") for item in items}
    voice_id = voice.get("id") or str(uuid.uuid4())
    while voice_id in existing_ids:
        voice_id = str(uuid.uuid4())
    voice["id"] = voice_id
    items.append(voice)
    _save_payload(items)
    return voice


def delete_custom_voice(voice_id: str) -> bool:
    """Delete a custom voice definition."""
    items = _load_payload()
    new_items = [item for item in items if item.get("id") != voice_id]
    if len(new_items) == len(items):
        return False
    _save_payload(new_items)
    return True


def replace_custom_voice(voice: Dict) -> Dict:
    """Replace an existing voice definition (used for future updates)."""
    items = _load_payload()
    replaced = False
    for idx, item in enumerate(items):
        if item.get("id") == voice.get("id"):
            items[idx] = voice
            replaced = True
            break
    if not replaced:
        items.append(voice)
    _save_payload(items)
    return voice


def get_custom_voice_by_code(code: str) -> Optional[Dict]:
    """Lookup custom voice using its public code (custom_<id>)."""
    if not code or not code.startswith(CUSTOM_CODE_PREFIX):
        return None
    voice_id = code[len(CUSTOM_CODE_PREFIX):]
    voice = get_custom_voice(voice_id)
    if not voice:
        return None
    return _to_public_entry(voice)


def _to_public_entry(raw: Dict) -> Dict:
    """Convert stored record into public entry with code metadata."""
    voice_id = raw.get("id")
    return {
        "id": voice_id,
        "code": f"{CUSTOM_CODE_PREFIX}{voice_id}",
        "name": raw.get("name") or "Custom Voice",
        "lang_code": (raw.get("lang_code") or "a").lower(),
        "components": raw.get("components") or [],
        "created_at": raw.get("created_at"),
        "updated_at": raw.get("updated_at"),
        "notes": raw.get("notes"),
    }
