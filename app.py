"""
TTS-Story - Web-based TTS application
"""
from flask import Flask, render_template, request, jsonify, send_file
from flask_cors import CORS
import base64
import copy
import inspect
import io
import json
import logging
import math
import mimetypes
import os
import queue
import re
import shutil
import stat
import tempfile
import threading
import time
import uuid
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from time import perf_counter
from typing import Any, Dict, List, Optional, Tuple
from werkzeug.utils import secure_filename
import soundfile as sf

from src.audio_effects import VoiceFXSettings
from src.audio_merger import AudioMerger
from src.custom_voice_store import (
    CUSTOM_CODE_PREFIX,
    delete_custom_voice,
    get_custom_voice,
    get_custom_voice_by_code,
    list_custom_voice_entries,
    replace_custom_voice,
    save_custom_voice,
)
from src.document_extractor import extract_text_from_file, get_supported_formats
from src.gemini_processor import GeminiProcessor, GeminiProcessorError
from src.replicate_api import ReplicateAPI
from src.text_processor import TextProcessor
from src.engines import TtsEngineBase
from src.engines.chatterbox_turbo_local_engine import (
    CHATTERBOX_TURBO_AVAILABLE,
)
from src.engines.voxcpm_local_engine import VOXCPM_AVAILABLE
from src.engines.chatterbox_turbo_replicate_engine import (
    DEFAULT_CHATTERBOX_TURBO_REPLICATE_MODEL,
    DEFAULT_CHATTERBOX_TURBO_REPLICATE_VOICE,
)
from src.tts_engine import (
    TTSEngine,
    KOKORO_AVAILABLE,
    DEFAULT_SAMPLE_RATE,
    get_engine,
    AVAILABLE_ENGINES,
)
from src.voice_manager import VoiceManager
from src.voice_sample_generator import generate_voice_samples

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
CORS(app)

# Configuration
CONFIG_FILE = "config.json"
OUTPUT_DIR = Path("static/audio")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
VOICE_PROMPT_DIR = Path("data/voice_prompts")
VOICE_PROMPT_DIR.mkdir(parents=True, exist_ok=True)
VOICE_PROMPT_EXTENSIONS = {".wav", ".mp3", ".m4a", ".flac", ".ogg"}
CHATTERBOX_VOICE_REGISTRY = Path("data/chatterbox_voices.json")
JOB_METADATA_FILENAME = "metadata.json"
DEFAULT_GEMINI_MODEL = "gemini-1.5-flash"
LIBRARY_CACHE_TTL = 5  # seconds
MIN_CHATTERBOX_PROMPT_SECONDS = 5.0
DEFAULT_CONFIG = {
    "replicate_api_key": "",
    "chunk_size": 500,
    "sample_rate": 24000,
    "speed": 1.0,
    "output_format": "mp3",
    "output_bitrate_kbps": 128,
    "crossfade_duration": 0.1,
    "intro_silence_ms": 0,
    "inter_chunk_silence_ms": 0,
    "gemini_api_key": "",
    "gemini_model": DEFAULT_GEMINI_MODEL,
    "gemini_prompt": "",
    "gemini_prompt_presets": [],
    "tts_engine": "kokoro",
    "chatterbox_turbo_local_default_prompt": "",
    "chatterbox_turbo_local_temperature": 0.8,
    "chatterbox_turbo_local_top_p": 0.95,
    "chatterbox_turbo_local_top_k": 1000,
    "chatterbox_turbo_local_repetition_penalty": 1.2,
    "chatterbox_turbo_local_cfg_weight": 0.0,
    "chatterbox_turbo_local_exaggeration": 0.0,
    "chatterbox_turbo_local_norm_loudness": True,
    "chatterbox_turbo_local_prompt_norm_loudness": True,
    "chatterbox_turbo_local_device": "auto",
    "chatterbox_turbo_replicate_api_token": "",
    "chatterbox_turbo_replicate_model": DEFAULT_CHATTERBOX_TURBO_REPLICATE_MODEL,
    "chatterbox_turbo_replicate_voice": DEFAULT_CHATTERBOX_TURBO_REPLICATE_VOICE,
    "chatterbox_turbo_replicate_temperature": 0.8,
    "chatterbox_turbo_replicate_top_p": 0.95,
    "chatterbox_turbo_replicate_top_k": 1000,
    "chatterbox_turbo_replicate_repetition_penalty": 1.2,
    "chatterbox_turbo_replicate_seed": None,
    "voxcpm_local_model_id": "openbmb/VoxCPM1.5",
    "voxcpm_local_device": "auto",
    "voxcpm_local_default_prompt": "",
    "voxcpm_local_default_prompt_text": "",
    "voxcpm_local_cfg_value": 2.0,
    "voxcpm_local_inference_timesteps": 32,
    "voxcpm_local_normalize": True,  # Enable text normalization for numbers/abbreviations
    "voxcpm_local_denoise": False,
    "parallel_chunks": 3,
    "cleanup_vram_after_job": False,
}

CHATTERBOX_TURBO_LOCAL_SETTING_KEYS = {
    "chatterbox_turbo_local_default_prompt",
    "chatterbox_turbo_local_temperature",
    "chatterbox_turbo_local_top_p",
    "chatterbox_turbo_local_top_k",
    "chatterbox_turbo_local_repetition_penalty",
    "chatterbox_turbo_local_cfg_weight",
    "chatterbox_turbo_local_exaggeration",
    "chatterbox_turbo_local_norm_loudness",
    "chatterbox_turbo_local_prompt_norm_loudness",
    "chatterbox_turbo_local_device",
}
VOXCPM_LOCAL_SETTING_KEYS = {
    "voxcpm_local_model_id",
    "voxcpm_local_device",
    "voxcpm_local_default_prompt",
    "voxcpm_local_default_prompt_text",
    "voxcpm_local_cfg_value",
    "voxcpm_local_inference_timesteps",
    "voxcpm_local_normalize",
    "voxcpm_local_denoise",
}
CHATTERBOX_TURBO_LOCAL_OPTION_ALIASES = {
    "default_prompt": "chatterbox_turbo_local_default_prompt",
    "prompt": "chatterbox_turbo_local_default_prompt",
    "temperature": "chatterbox_turbo_local_temperature",
    "top_p": "chatterbox_turbo_local_top_p",
    "top_k": "chatterbox_turbo_local_top_k",
    "repetition_penalty": "chatterbox_turbo_local_repetition_penalty",
    "cfg_weight": "chatterbox_turbo_local_cfg_weight",
    "exaggeration": "chatterbox_turbo_local_exaggeration",
    "norm_loudness": "chatterbox_turbo_local_norm_loudness",
    "prompt_norm_loudness": "chatterbox_turbo_local_prompt_norm_loudness",
    "device": "chatterbox_turbo_local_device",
}
VOXCPM_LOCAL_OPTION_ALIASES = {
    "model": "voxcpm_local_model_id",
    "model_id": "voxcpm_local_model_id",
    "device": "voxcpm_local_device",
    "default_prompt": "voxcpm_local_default_prompt",
    "prompt_text": "voxcpm_local_default_prompt_text",
    "cfg_value": "voxcpm_local_cfg_value",
    "inference_timesteps": "voxcpm_local_inference_timesteps",
    "normalize": "voxcpm_local_normalize",
    "denoise": "voxcpm_local_denoise",
}
CHATTERBOX_TURBO_LOCAL_BOOLEAN_SETTINGS = {
    "chatterbox_turbo_local_norm_loudness",
    "chatterbox_turbo_local_prompt_norm_loudness",
}
CHATTERBOX_TURBO_LOCAL_FLOAT_SETTINGS = {
    "chatterbox_turbo_local_temperature": (0.05, 2.0, 0.8),
    "chatterbox_turbo_local_top_p": (0.1, 1.0, 0.95),
    "chatterbox_turbo_local_repetition_penalty": (1.0, 2.0, 1.2),
    "chatterbox_turbo_local_cfg_weight": (0.0, 2.0, 0.0),
    "chatterbox_turbo_local_exaggeration": (0.0, 2.0, 0.0),
}
CHATTERBOX_TURBO_LOCAL_INT_SETTINGS = {
    "chatterbox_turbo_local_top_k": (1, 4000, 1000),
    "chatterbox_turbo_local_chunk_size": (100, 1000, 450),
}
VOXCPM_LOCAL_BOOLEAN_SETTINGS = {
    "voxcpm_local_normalize",
    "voxcpm_local_denoise",
}
VOXCPM_LOCAL_FLOAT_SETTINGS = {
    "voxcpm_local_cfg_value": (0.1, 5.0, 2.0),
}
VOXCPM_LOCAL_INT_SETTINGS = {
    "voxcpm_local_inference_timesteps": (10, 100, 32),
}

CHATTERBOX_TURBO_REPLICATE_SETTING_KEYS = {
    "chatterbox_turbo_replicate_api_token",
    "chatterbox_turbo_replicate_model",
    "chatterbox_turbo_replicate_voice",
    "chatterbox_turbo_replicate_temperature",
    "chatterbox_turbo_replicate_top_p",
    "chatterbox_turbo_replicate_top_k",
    "chatterbox_turbo_replicate_repetition_penalty",
    "chatterbox_turbo_replicate_seed",
}
CHATTERBOX_TURBO_REPLICATE_OPTION_ALIASES = {
    "api_token": "chatterbox_turbo_replicate_api_token",
    "token": "chatterbox_turbo_replicate_api_token",
    "model": "chatterbox_turbo_replicate_model",
    "voice": "chatterbox_turbo_replicate_voice",
    "temperature": "chatterbox_turbo_replicate_temperature",
    "top_p": "chatterbox_turbo_replicate_top_p",
    "top_k": "chatterbox_turbo_replicate_top_k",
    "repetition_penalty": "chatterbox_turbo_replicate_repetition_penalty",
    "seed": "chatterbox_turbo_replicate_seed",
}
CHATTERBOX_TURBO_REPLICATE_FLOAT_SETTINGS = {
    "chatterbox_turbo_replicate_temperature": (0.05, 2.0, 0.8),
    "chatterbox_turbo_replicate_top_p": (0.1, 1.0, 0.95),
    "chatterbox_turbo_replicate_repetition_penalty": (1.0, 2.0, 1.2),
}
CHATTERBOX_TURBO_REPLICATE_INT_SETTINGS = {
    "chatterbox_turbo_replicate_top_k": (1, 4000, 1000),
}


def _measure_audio_duration(audio_path: Path) -> Optional[float]:
    """
    Return the duration of an audio file in seconds, or None if it cannot be determined.
    """
    try:
        info = sf.info(str(audio_path))
        if not info.frames or not info.samplerate:
            return None
        duration = info.frames / float(info.samplerate)
        return duration if duration > 0 else None
    except Exception as exc:  # pragma: no cover - logging only
        logger.warning("Unable to measure duration for %s: %s", audio_path, exc)
        return None


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off"}:
            return False
    return bool(value)


def _coerce_int(
    value: Any,
    *,
    minimum: int = 1,
    maximum: Optional[int] = None,
    fallback: int = 1,
) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = fallback
    if parsed < minimum:
        parsed = minimum
    if maximum is not None and parsed > maximum:
        parsed = maximum
    return parsed


def _coerce_float(
    value: Any,
    *,
    minimum: float,
    maximum: float,
    fallback: float,
) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = fallback
    if parsed < minimum:
        parsed = minimum
    if parsed > maximum:
        parsed = maximum
    return parsed


def _normalize_engine_options(engine_name: str, options: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not options:
        return {}
    if engine_name == "chatterbox_turbo_local":
        return _normalize_chatterbox_turbo_local_options(options)
    if engine_name == "chatterbox_turbo_replicate":
        return _normalize_chatterbox_turbo_replicate_options(options)
    if engine_name == "voxcpm_local":
        return _normalize_voxcpm_local_options(options)
    return {}


def _normalize_chatterbox_turbo_local_options(options: Dict[str, Any]) -> Dict[str, Any]:
    normalized: Dict[str, Any] = {}
    for raw_key, value in options.items():
        if raw_key is None:
            continue
        key = str(raw_key).strip().lower()
        canonical = CHATTERBOX_TURBO_LOCAL_OPTION_ALIASES.get(key)
        if not canonical and key in CHATTERBOX_TURBO_LOCAL_SETTING_KEYS:
            canonical = key
        if canonical and canonical in CHATTERBOX_TURBO_LOCAL_SETTING_KEYS:
            normalized[canonical] = value

    result: Dict[str, Any] = {}
    for key, value in normalized.items():
        if key in CHATTERBOX_TURBO_LOCAL_BOOLEAN_SETTINGS:
            result[key] = _coerce_bool(value)
            continue
        if key in CHATTERBOX_TURBO_LOCAL_FLOAT_SETTINGS:
            minimum, maximum, fallback = CHATTERBOX_TURBO_LOCAL_FLOAT_SETTINGS[key]
            result[key] = _coerce_float(value, minimum=minimum, maximum=maximum, fallback=fallback)
            continue
        if key in CHATTERBOX_TURBO_LOCAL_INT_SETTINGS:
            minimum, maximum, fallback = CHATTERBOX_TURBO_LOCAL_INT_SETTINGS[key]
            result[key] = _coerce_int(value, minimum=minimum, maximum=maximum, fallback=fallback)
            continue
        result[key] = (value or "").strip() if isinstance(value, str) else (value or "")
    return result


def _normalize_voxcpm_local_options(options: Dict[str, Any]) -> Dict[str, Any]:
    normalized: Dict[str, Any] = {}
    for raw_key, value in options.items():
        if raw_key is None:
            continue
        key = str(raw_key).strip().lower()
        canonical = VOXCPM_LOCAL_OPTION_ALIASES.get(key)
        if not canonical and key in VOXCPM_LOCAL_SETTING_KEYS:
            canonical = key
        if canonical and canonical in VOXCPM_LOCAL_SETTING_KEYS:
            normalized[canonical] = value

    result: Dict[str, Any] = {}
    for key, value in normalized.items():
        if key in VOXCPM_LOCAL_BOOLEAN_SETTINGS:
            result[key] = _coerce_bool(value)
            continue
        if key in VOXCPM_LOCAL_FLOAT_SETTINGS:
            minimum, maximum, fallback = VOXCPM_LOCAL_FLOAT_SETTINGS[key]
            result[key] = _coerce_float(value, minimum=minimum, maximum=maximum, fallback=fallback)
            continue
        if key in VOXCPM_LOCAL_INT_SETTINGS:
            minimum, maximum, fallback = VOXCPM_LOCAL_INT_SETTINGS[key]
            result[key] = _coerce_int(value, minimum=minimum, maximum=maximum, fallback=fallback)
            continue
        result[key] = (value or "").strip() if isinstance(value, str) else (value or "")
    return result


def _normalize_chatterbox_turbo_replicate_options(options: Dict[str, Any]) -> Dict[str, Any]:
    normalized: Dict[str, Any] = {}
    for raw_key, value in options.items():
        if raw_key is None:
            continue
        key = str(raw_key).strip().lower()
        canonical = CHATTERBOX_TURBO_REPLICATE_OPTION_ALIASES.get(key)
        if not canonical and key in CHATTERBOX_TURBO_REPLICATE_SETTING_KEYS:
            canonical = key
        if canonical and canonical in CHATTERBOX_TURBO_REPLICATE_SETTING_KEYS:
            normalized[canonical] = value

    result: Dict[str, Any] = {}
    for key, value in normalized.items():
        if key in CHATTERBOX_TURBO_REPLICATE_FLOAT_SETTINGS:
            minimum, maximum, fallback = CHATTERBOX_TURBO_REPLICATE_FLOAT_SETTINGS[key]
            result[key] = _coerce_float(value, minimum=minimum, maximum=maximum, fallback=fallback)
            continue
        if key in CHATTERBOX_TURBO_REPLICATE_INT_SETTINGS:
            minimum, maximum, fallback = CHATTERBOX_TURBO_REPLICATE_INT_SETTINGS[key]
            result[key] = _coerce_int(value, minimum=minimum, maximum=maximum, fallback=fallback)
            continue
        if key == "chatterbox_turbo_replicate_seed":
            const_value = value
            if isinstance(const_value, str):
                const_value = const_value.strip()
            if const_value not in (None, ""):
                try:
                    result[key] = int(const_value)
                except (TypeError, ValueError):
                    pass
            continue
        result[key] = (value or "").strip() if isinstance(value, str) else (value or "")
    return result


def _apply_engine_option_overrides(config: Dict[str, Any], engine_name: str, options: Optional[Dict[str, Any]]):
    overrides = _normalize_engine_options(engine_name, options or {})
    config.update(overrides)
# Allow headings like [narrator]\nChapter 1 or Chapter 1 without tags.
CHAPTER_HEADING_PATTERN = re.compile(
    r'^\s*(?:\[[^\]]+\]\s*)*(chapter(?:\s+[^\n\r]*)?)',
    re.IGNORECASE | re.MULTILINE
)

# Exceptions
class JobCancelled(Exception):
    """Raised when a job is cancelled mid-processing."""


# Global state
jobs = {}  # Track all jobs (queued, processing, completed)
job_queue = queue.Queue()  # Thread-safe job queue
current_job_id = None  # Currently processing job
cancel_flags = {}  # Cancellation flags for jobs
queue_lock = threading.Lock()  # Lock for thread-safe operations
worker_thread = None  # Background worker thread
tts_engine_instances: Dict[str, TtsEngineBase] = {}
engine_config_signatures: Dict[str, str] = {}
tts_engine_lock = threading.Lock()
# Lock to prevent concurrent GPU inference across all TTS operations
# This prevents GPU contention and "badcase" retry loops with VoxCPM
gpu_inference_lock = threading.Lock()
# Use max_workers=1 to prevent parallel GPU inference which causes contention
# and "badcase" retry loops with VoxCPM and other GPU-based engines
chunk_regen_executor = ThreadPoolExecutor(max_workers=1)
library_cache = {
    "items": None,
    "timestamp": 0.0,
}


def _job_dir_from_entry(job_id: str, job_entry: Dict[str, Any]) -> Path:
    directory = job_entry.get("job_dir")
    if directory:
        return Path(directory)
    return OUTPUT_DIR / job_id


def _chunk_file_url(job_id: str, relative_path: Optional[str]) -> Optional[str]:
    if not relative_path:
        return None
    rel = Path(relative_path).as_posix()
    return f"/static/audio/{job_id}/{rel}"


def _find_chunk_record(job_entry: Dict[str, Any], chunk_id: str):
    for idx, chunk in enumerate(job_entry.get("chunks") or []):
        if chunk.get("id") == chunk_id:
            return idx, chunk
    return None, None


def _clone_voice_assignment(assignment: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not isinstance(assignment, dict):
        return None
    return copy.deepcopy(assignment)


def _voice_label_from_assignment(assignment: Optional[Dict[str, Any]]) -> Optional[str]:
    if not isinstance(assignment, dict):
        return None
    if assignment.get("voice"):
        return assignment.get("voice")
    # Check for audio_prompt_path (Chatterbox uses this)
    prompt = assignment.get("audio_prompt_path")
    if isinstance(prompt, str) and prompt:
        # Extract filename and remove .wav extension for cleaner display
        filename = Path(prompt).name if "/" in prompt or "\\" in prompt else prompt
        return filename.replace('.wav', '') if filename.endswith('.wav') else filename
    return None


def _normalize_voice_payload(raw_payload: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not isinstance(raw_payload, dict):
        return None
    cleaned = {}
    for key, value in raw_payload.items():
        if value is None:
            continue
        if isinstance(value, str):
            trimmed = value.strip()
            if not trimmed:
                continue
            cleaned[key] = trimmed
            continue
        cleaned[key] = value
    return cleaned or None


def _has_active_regen_tasks(job_entry: Dict[str, Any]) -> bool:
    tasks = job_entry.get("regen_tasks") or {}
    for task in tasks.values():
        if (task or {}).get("status") in {"queued", "running"}:
            return True
    return False


def _ensure_review_ready(job_entry: Dict[str, Any]):
    if not job_entry.get("review_mode"):
        raise ValueError("Job was not created with review mode enabled.")
    if not job_entry.get("job_dir"):
        raise ValueError("Job output directory is unavailable.")


def _load_review_manifest(job_id: str, job_entry: Dict[str, Any]) -> Dict[str, Any]:
    manifest_name = job_entry.get("review_manifest") or "review_manifest.json"
    job_dir = _job_dir_from_entry(job_id, job_entry)
    manifest_path = job_dir / manifest_name
    if not manifest_path.exists():
        raise FileNotFoundError("Review manifest not found for this job.")
    with manifest_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _update_regen_status(job_id: str, chunk_id: str, **fields):
    with queue_lock:
        job_entry = jobs.get(job_id)
        if not job_entry:
            return
        regen_tasks = job_entry.setdefault("regen_tasks", {})
        task_state = regen_tasks.setdefault(chunk_id, {})
        task_state.update(fields)


def _perform_chunk_regeneration(
    job_id: str,
    chunk_id: str,
    text_to_render: str,
    voice_override: Optional[Dict[str, Any]] = None,
    engine_override: Optional[str] = None,
):
    with queue_lock:
        job_entry = jobs.get(job_id)
        if not job_entry:
            raise ValueError("Job not found.")
        idx, chunk = _find_chunk_record(job_entry, chunk_id)
        if chunk is None:
            raise ValueError("Chunk not found.")
        config_snapshot = copy.deepcopy(job_entry.get("config_snapshot") or load_config())
        job_voice_assignments = copy.deepcopy(job_entry.get("voice_assignments") or {})
        job_dir = _job_dir_from_entry(job_id, job_entry)
        speaker = chunk.get("speaker") or "default"
        relative_file = chunk.get("relative_file")
        speed = config_snapshot.get("speed", 1.0)
        sample_rate = config_snapshot.get("sample_rate")
        # Allow engine override for cross-engine regeneration
        if engine_override:
            config_snapshot["tts_engine"] = engine_override

    normalized_override = _normalize_voice_payload(voice_override)
    chunk_voice_assignment = _clone_voice_assignment(chunk.get("voice_assignment"))
    default_assignment = _clone_voice_assignment(
        job_voice_assignments.get(speaker) or job_voice_assignments.get("default")
    )
    effective_assignment = chunk_voice_assignment or default_assignment
    if normalized_override:
        effective_assignment = {**(effective_assignment or {}), **normalized_override}

    voice_config = copy.deepcopy(job_voice_assignments) if job_voice_assignments else {}
    if effective_assignment:
        voice_config = voice_config or {}
        voice_config[speaker] = effective_assignment

    chunk_text = (text_to_render or "").strip()
    if not chunk_text:
        raise ValueError("Chunk text cannot be empty.")
    if not relative_file:
        raise ValueError("Chunk does not have an associated file path.")

    # Use system temp directory instead of job_dir to avoid Windows permission issues
    tmp_dir = Path(tempfile.mkdtemp(prefix="tts_chunk_regen_"))
    generated_files: List[str] = []
    try:
        segments = [{
            "speaker": speaker,
            "text": chunk_text,
            "chunks": [chunk_text],
        }]
        engine_name = _normalize_engine_name(config_snapshot.get("tts_engine"))
        
        # Acquire GPU lock to prevent concurrent inference which causes
        # GPU contention and "badcase" retry loops with VoxCPM
        with gpu_inference_lock:
            engine = get_tts_engine(engine_name, config=config_snapshot)
            generated_files = engine.generate_batch(
                segments=segments,
                voice_config=voice_config,
                output_dir=str(tmp_dir),
                speed=speed,
                sample_rate=sample_rate,
            )

        if not generated_files:
            raise RuntimeError("TTS engine did not return any audio for the chunk.")
        temp_file = Path(generated_files[0])
        target_path = job_dir / relative_file
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(temp_file), str(target_path))
    finally:
        # Clean up temp directory - retry with longer delays on Windows
        for attempt in range(5):
            try:
                if tmp_dir.exists():
                    shutil.rmtree(tmp_dir)
                break
            except Exception as e:
                if attempt < 4:
                    time.sleep(0.2 * (attempt + 1))  # Increasing delay: 0.2, 0.4, 0.6, 0.8s
                else:
                    logger.warning("Failed to clean up temp dir %s: %s", tmp_dir, e)

    with queue_lock:
        job_entry = jobs.get(job_id)
        if not job_entry:
            return
        _, chunk = _find_chunk_record(job_entry, chunk_id)
        if chunk:
            chunk["text"] = chunk_text
            chunk["regenerated_at"] = datetime.now().isoformat()
            if effective_assignment:
                chunk["voice_assignment"] = copy.deepcopy(effective_assignment)
                voice_label = _voice_label_from_assignment(effective_assignment)
                if voice_label:
                    chunk["voice_label"] = voice_label
                else:
                    chunk.pop("voice_label", None)

    _persist_chunks_metadata(job_id, job_dir)


def _persist_chunks_metadata(job_id: str, job_dir: Path):
    """Update the chunks_metadata.json file with current chunk state."""
    with queue_lock:
        job_entry = jobs.get(job_id)
        if not job_entry:
            return
        job_chunks = job_entry.get("chunks") or []
        config_snapshot = job_entry.get("config_snapshot") or {}
        engine_name = _normalize_engine_name(config_snapshot.get("tts_engine"))

    chunks_meta_path = job_dir / "chunks_metadata.json"
    existing_meta = {}
    if chunks_meta_path.exists():
        try:
            with chunks_meta_path.open("r", encoding="utf-8") as handle:
                existing_meta = json.load(handle)
        except Exception:
            pass

    chunks_meta = {
        "engine": engine_name,
        "created_at": existing_meta.get("created_at", datetime.now().isoformat()),
        "updated_at": datetime.now().isoformat(),
        "chunks": job_chunks,
    }
    with chunks_meta_path.open("w", encoding="utf-8") as handle:
        json.dump(chunks_meta, handle, indent=2)


def _schedule_chunk_regeneration(
    job_id: str,
    chunk_id: str,
    text_to_render: str,
    voice_payload: Optional[Dict[str, Any]] = None,
    engine_override: Optional[str] = None,
):
    requested_at = datetime.now().isoformat()
    normalized_voice = _normalize_voice_payload(voice_payload)
    normalized_engine = _normalize_engine_name(engine_override) if engine_override else None
    with queue_lock:
        job_entry = jobs.get(job_id)
        if not job_entry:
            raise ValueError("Job not found.")
        regen_tasks = job_entry.setdefault("regen_tasks", {})
        regen_tasks[chunk_id] = {
            "status": "queued",
            "requested_at": requested_at,
            "error": None,
            "voice": normalized_voice,
            "engine": normalized_engine,
        }

    def task():
        try:
            _update_regen_status(job_id, chunk_id, status="running", started_at=datetime.now().isoformat(), error=None)
            _perform_chunk_regeneration(job_id, chunk_id, text_to_render, voice_override=normalized_voice, engine_override=normalized_engine)
            _update_regen_status(job_id, chunk_id, status="completed", completed_at=datetime.now().isoformat())
        except Exception as exc:  # noqa: BLE001
            logger.error("Chunk regeneration failed for job %s chunk %s: %s", job_id, chunk_id, exc, exc_info=True)
            _update_regen_status(
                job_id,
                chunk_id,
                status="failed",
                error=str(exc),
                completed_at=datetime.now().isoformat(),
            )

    chunk_regen_executor.submit(task)


@contextmanager
def log_request_timing(label: str, warn_ms: float = 750.0):
    """Log slow endpoint or processing sections."""
    start = perf_counter()
    try:
        yield
    finally:
        duration_ms = (perf_counter() - start) * 1000.0
        if duration_ms >= warn_ms:
            logger.warning(f"{label} took {duration_ms:.1f} ms")
        else:
            logger.debug(f"{label} took {duration_ms:.1f} ms")


def invalidate_library_cache():
    """Clear cached library listing so next request reloads from disk."""
    library_cache["items"] = None
    library_cache["timestamp"] = 0.0


def _normalize_engine_name(name: Optional[str]) -> str:
    value = (name or DEFAULT_CONFIG["tts_engine"]).strip().lower()
    return value or DEFAULT_CONFIG["tts_engine"]


def _engine_signature(engine_name: str, config: Dict) -> str:
    """Generate a signature capturing settings that require a fresh engine."""
    config = config or {}
    if engine_name == "chatterbox_turbo_local":
        parts = (
            (config.get("chatterbox_turbo_local_default_prompt") or "").strip(),
            str(config.get("chatterbox_turbo_local_temperature")),
            str(config.get("chatterbox_turbo_local_top_p")),
            str(config.get("chatterbox_turbo_local_top_k")),
            str(config.get("chatterbox_turbo_local_repetition_penalty")),
            str(config.get("chatterbox_turbo_local_cfg_weight")),
            str(config.get("chatterbox_turbo_local_exaggeration")),
            str(bool(config.get("chatterbox_turbo_local_norm_loudness", True))),
            str(bool(config.get("chatterbox_turbo_local_prompt_norm_loudness", True))),
        )
        return f"{engine_name}::{'|'.join(parts)}"
    if engine_name == "chatterbox_turbo_replicate":
        parts = (
            (config.get("chatterbox_turbo_replicate_api_token") or "").strip(),
            (config.get("chatterbox_turbo_replicate_model") or "").strip(),
            (config.get("chatterbox_turbo_replicate_voice") or "").strip(),
            str(config.get("chatterbox_turbo_replicate_temperature")),
            str(config.get("chatterbox_turbo_replicate_top_p")),
            str(config.get("chatterbox_turbo_replicate_top_k")),
            str(config.get("chatterbox_turbo_replicate_repetition_penalty")),
            str(config.get("chatterbox_turbo_replicate_seed")),
        )
        return f"{engine_name}::{'|'.join(parts)}"
    if engine_name == "voxcpm_local":
        parts = (
            (config.get("voxcpm_local_model_id") or "").strip(),
            (config.get("voxcpm_local_default_prompt") or "").strip(),
            (config.get("voxcpm_local_default_prompt_text") or "").strip(),
            str(config.get("voxcpm_local_cfg_value")),
            str(config.get("voxcpm_local_inference_timesteps")),
            str(bool(config.get("voxcpm_local_normalize", False))),
            str(bool(config.get("voxcpm_local_denoise", False))),
            (config.get("voxcpm_local_device") or "").strip(),
        )
        return f"{engine_name}::{'|'.join(parts)}"
    if engine_name == "kokoro_replicate":
        parts = (
            (config.get("replicate_api_key") or "").strip(),
        )
        return f"{engine_name}::{'|'.join(parts)}"
    return engine_name


def _create_engine(engine_name: str, config: Dict) -> TtsEngineBase:
    """Instantiate a specific engine with configuration-derived options."""
    config = config or {}
    if engine_name == "kokoro":
        if not KOKORO_AVAILABLE:
            raise ImportError("Kokoro is not installed. Run setup to enable local mode.")
        device = config.get("device", "auto")
        return TTSEngine(device=device)

    if engine_name == "chatterbox_turbo_local":
        if not CHATTERBOX_TURBO_AVAILABLE:
            raise ImportError(
                "chatterbox-tts is not installed. Run setup to enable the local Chatterbox Turbo engine."
            )
        device = (config.get("chatterbox_turbo_local_device") or config.get("device") or "auto").strip()
        return get_engine(
            "chatterbox_turbo_local",
            device=device or "auto",
            default_prompt=(config.get("chatterbox_turbo_local_default_prompt") or "").strip() or None,
            temperature=float(config.get("chatterbox_turbo_local_temperature") or 0.8),
            top_p=float(config.get("chatterbox_turbo_local_top_p") or 0.95),
            top_k=int(config.get("chatterbox_turbo_local_top_k") or 1000),
            repetition_penalty=float(config.get("chatterbox_turbo_local_repetition_penalty") or 1.2),
            cfg_weight=float(config.get("chatterbox_turbo_local_cfg_weight") or 0.0),
            exaggeration=float(config.get("chatterbox_turbo_local_exaggeration") or 0.0),
            norm_loudness=bool(config.get("chatterbox_turbo_local_norm_loudness", True)),
            prompt_norm_loudness=bool(config.get("chatterbox_turbo_local_prompt_norm_loudness", True)),
        )

    if engine_name == "chatterbox_turbo_replicate":
        # Use shared replicate_api_key, fall back to engine-specific token for backward compatibility
        api_token = (config.get("replicate_api_key") or config.get("chatterbox_turbo_replicate_api_token") or "").strip()
        if not api_token:
            raise ValueError("Replicate API token is required for Chatterbox (Replicate). Configure it in the Kokoro · Replicate settings section.")
        return get_engine(
            "chatterbox_turbo_replicate",
            api_token=api_token,
            model_version=(config.get("chatterbox_turbo_replicate_model") or DEFAULT_CHATTERBOX_TURBO_REPLICATE_MODEL).strip()
            or DEFAULT_CHATTERBOX_TURBO_REPLICATE_MODEL,
            default_voice=(config.get("chatterbox_turbo_replicate_voice") or DEFAULT_CHATTERBOX_TURBO_REPLICATE_VOICE).strip()
            or DEFAULT_CHATTERBOX_TURBO_REPLICATE_VOICE,
            temperature=float(config.get("chatterbox_turbo_replicate_temperature") or 0.8),
            top_p=float(config.get("chatterbox_turbo_replicate_top_p") or 0.95),
            top_k=int(config.get("chatterbox_turbo_replicate_top_k") or 1000),
            repetition_penalty=float(config.get("chatterbox_turbo_replicate_repetition_penalty") or 1.2),
            seed=(
                int(config["chatterbox_turbo_replicate_seed"])
                if config.get("chatterbox_turbo_replicate_seed") not in (None, "")
                else None
            ),
        )

    if engine_name == "voxcpm_local":
        if not VOXCPM_AVAILABLE:
            raise ImportError("voxcpm is not installed. Run setup to enable VoxCPM local mode.")
        device = (config.get("voxcpm_local_device") or "auto").strip()
        return get_engine(
            "voxcpm_local",
            device=device or "auto",
            model_id=(config.get("voxcpm_local_model_id") or "openbmb/VoxCPM1.5").strip(),
            default_prompt=(config.get("voxcpm_local_default_prompt") or "").strip() or None,
            default_prompt_text=(config.get("voxcpm_local_default_prompt_text") or "").strip() or None,
            cfg_value=float(config.get("voxcpm_local_cfg_value") or 2.0),
            inference_timesteps=int(config.get("voxcpm_local_inference_timesteps") or 32),
            normalize=bool(config.get("voxcpm_local_normalize", False)),
            denoise=bool(config.get("voxcpm_local_denoise", False)),
        )

    if engine_name == "kokoro_replicate":
        api_key = (config.get("replicate_api_key") or "").strip()
        if not api_key:
            raise ValueError("Replicate API key is required for Kokoro (Replicate).")
        return ReplicateAPI(api_key)

    raise ValueError(f"Unsupported local TTS engine '{engine_name}'.")


def get_tts_engine(engine_name: Optional[str] = None, config: Optional[Dict] = None):
    """Return a shared engine instance keyed by engine name and config signature.
    
    When switching to a different engine, unloads other engines to free GPU memory.
    """
    import gc
    
    selected = _normalize_engine_name(engine_name)
    config = config or load_config()
    signature = _engine_signature(selected, config)

    with tts_engine_lock:
        cached = tts_engine_instances.get(selected)
        if cached and engine_config_signatures.get(selected) == signature:
            return cached

        # Unload OTHER engines to free GPU memory before loading new one
        # This prevents multiple large models from being loaded simultaneously
        other_engines = [name for name in tts_engine_instances.keys() if name != selected]
        for other_name in other_engines:
            other_engine = tts_engine_instances.get(other_name)
            if other_engine:
                try:
                    logger.info("Unloading engine '%s' to free GPU memory for '%s'", other_name, selected)
                    other_engine.cleanup()
                except Exception:
                    logger.warning("Failed to cleanup engine '%s'", other_name, exc_info=True)
                tts_engine_instances.pop(other_name, None)
                engine_config_signatures.pop(other_name, None)
        
        # Force garbage collection and clear CUDA cache after unloading
        if other_engines:
            gc.collect()
            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                    allocated = torch.cuda.memory_allocated(0) / 1024**3
                    logger.info("GPU memory after unloading other engines: %.2f GB", allocated)
            except Exception:
                pass

        if cached:
            try:
                cached.cleanup()
            except Exception:
                logger.warning("Failed to cleanup engine '%s' before reload.", selected, exc_info=True)

        engine = _create_engine(selected, config)
        tts_engine_instances[selected] = engine
        engine_config_signatures[selected] = signature
        return engine


def clear_cached_custom_voice(voice_code: str | None = None) -> int:
    """Ensure cached blended tensors stay in sync after CRUD operations."""
    engine = tts_engine_instances.get("kokoro")
    if engine is None:
        return 0
    return engine.clear_custom_voice_cache(voice_code)


def _cleanup_engine_vram(engine_name: Optional[str] = None) -> None:
    """Clean up VRAM for a specific engine or all engines."""
    import gc
    
    with tts_engine_lock:
        if engine_name:
            engine = tts_engine_instances.get(engine_name)
            if engine:
                try:
                    engine.cleanup()
                    logger.info("VRAM cleanup completed for engine: %s", engine_name)
                except Exception as e:
                    logger.warning("VRAM cleanup failed for engine %s: %s", engine_name, e)
                # Remove from cache to force reload on next use
                tts_engine_instances.pop(engine_name, None)
                engine_config_signatures.pop(engine_name, None)
        else:
            # Clean all engines
            for name, engine in list(tts_engine_instances.items()):
                try:
                    engine.cleanup()
                except Exception as e:
                    logger.warning("VRAM cleanup failed for engine %s: %s", name, e)
            tts_engine_instances.clear()
            engine_config_signatures.clear()
    
    gc.collect()
    
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass


def _voice_manager_for_custom_voices() -> VoiceManager:
    """Create a fresh VoiceManager to validate custom voice payloads."""
    return VoiceManager()


def _normalize_component(component) -> Dict[str, float]:
    """Normalize a component entry into {'voice': str, 'weight': float}."""
    voice = None
    weight = 1.0

    if isinstance(component, str):
        voice = component.strip()
    elif isinstance(component, dict):
        voice = str(component.get("voice") or component.get("name") or "").strip()
        weight_candidate = component.get("weight") or component.get("ratio") or component.get("mix")
        if weight_candidate is not None:
            try:
                weight = float(weight_candidate)
            except (TypeError, ValueError):
                raise ValueError("Component weight must be numeric.")
    else:
        raise ValueError("Invalid component format.")

    if not voice:
        raise ValueError("Component voice is required.")
    if weight <= 0:
        raise ValueError("Component weight must be greater than zero.")

    return {"voice": voice, "weight": weight}


def _prepare_custom_voice_payload(data: dict, existing: Optional[dict] = None) -> dict:
    """Validate and normalize incoming custom voice payloads."""
    if not isinstance(data, dict):
        raise ValueError("Invalid payload format.")

    existing = existing or {}
    name = (data.get("name") or existing.get("name") or "Custom Voice").strip()
    if not name:
        raise ValueError("Custom voice name cannot be empty.")
    if len(name) > 80:
        raise ValueError("Custom voice name must be 80 characters or fewer.")

    lang_code = (data.get("lang_code") or existing.get("lang_code") or "a").lower()
    manager = _voice_manager_for_custom_voices()
    if not manager.supports_lang_code(lang_code):
        raise ValueError(f"Unsupported language code '{lang_code}'.")

    components_input = data.get("components")
    if components_input is None:
        components_input = existing.get("components")
    if not components_input:
        raise ValueError("Custom voice requires at least one component voice.")

    normalized_components = [_normalize_component(component) for component in components_input]
    for component in normalized_components:
        if not manager.validate_voice(component["voice"], lang_code):
            raise ValueError(f"Voice '{component['voice']}' is not available for language '{lang_code}'.")

    total_weight = sum(component["weight"] for component in normalized_components)
    if total_weight <= 0:
        raise ValueError("Total component weight must be greater than zero.")

    notes_value = (data.get("notes") or existing.get("notes") or "").strip()

    payload = existing.copy()
    payload.update({
        "name": name,
        "lang_code": lang_code,
        "components": normalized_components,
        "notes": notes_value or None,
    })
    return payload


def _to_public_custom_voice(entry: dict) -> dict:
    """Ensure API responses include normalized metadata."""
    if not entry:
        return {}
    public = entry.copy()
    if "code" not in public and public.get("id"):
        public["code"] = f"{CUSTOM_CODE_PREFIX}{public['id']}"
    public["components"] = public.get("components", [])
    return public


def _get_raw_custom_voice(identifier: str) -> Optional[dict]:
    """Fetch raw custom voice definition by id or code."""
    if not identifier:
        return None
    voice_id = identifier
    if identifier.startswith(CUSTOM_CODE_PREFIX):
        entry = get_custom_voice_by_code(identifier)
        voice_id = entry.get("id") if entry else None
    if not voice_id:
        return None
    return get_custom_voice(voice_id)


def slugify_filename(value: str, default: str = "chapter") -> str:
    """Create a filesystem-friendly slug."""
    if not value:
        return default
    value = re.sub(r'[^A-Za-z0-9]+', '-', value)
    value = re.sub(r'-{2,}', '-', value).strip('-')
    return value or default


def split_text_into_chapters(text: str):
    """
    Split text into chapters by detecting lines that start with the word 'Chapter'.
    Returns list of dicts with title/content.
    """
    matches = list(CHAPTER_HEADING_PATTERN.finditer(text))
    chapters = []

    if not matches:
        clean_text = text.strip()
        if clean_text:
            chapters.append({"title": "Full Story", "content": clean_text})
        return chapters

    first_start = matches[0].start()
    if first_start > 0:
        pre_content = text[:first_start].strip()
        if pre_content:
            # Create a "Title" chapter for content before the first chapter heading
            # This allows the narrator to announce the title separately with adjustable timing
            chapters.append({"title": "Title", "content": pre_content})

    for idx, match in enumerate(matches):
        start = match.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        content = text[start:end].strip()
        if content:
            title = match.group(1).strip()
            chapters.append({
                "title": title or f"Chapter {idx + 1}",
                "content": content
            })

    return chapters


def build_gemini_sections(text: str, prefer_chapters: bool, config: dict):
    """Create sections for Gemini processing based on chapters or chunks."""
    sections = []
    if not text:
        return sections

    chapter_matches = list(CHAPTER_HEADING_PATTERN.finditer(text))
    if prefer_chapters and chapter_matches:
        for chapter in split_text_into_chapters(text):
            sections.append({
                "title": chapter.get("title"),
                "content": (chapter.get("content") or "").strip(),
                "source": "chapter"
            })
    else:
        processor = _create_text_processor_for_engine(config.get("tts_engine"), config.get('chunk_size', 500), config)
        chunks = processor.chunk_text(text)
        if not chunks:
            chunks = [text]
        for chunk in chunks:
            clean_chunk = chunk.strip()
            if not clean_chunk:
                continue
            sections.append({
                "title": None,
                "content": clean_chunk,
                "source": "chunk"
            })

    return sections


def compose_gemini_prompt(section: dict, prompt_prefix: str = "", known_speakers=None) -> str:
    """Build the prompt for a Gemini section, optionally referencing known speakers."""
    parts = []
    if prompt_prefix:
        parts.append(prompt_prefix.strip())

    speakers = [s for s in (known_speakers or []) if s]
    if speakers:
        speaker_line = (
            "Known speaker tags so far (reference only, keep names consistent): "
            + ", ".join(speakers)
        )
        parts.append(speaker_line)

    content = (section.get("content") or "").strip()
    if content:
        parts.append(content)
    return "\n\n".join(parts).strip()


def _is_chatterbox_engine(engine_name: str) -> bool:
    normalized = _normalize_engine_name(engine_name)
    return normalized.startswith("chatterbox")


def _create_text_processor_for_engine(engine_name: str, chunk_size: int, config: Optional[Dict] = None) -> TextProcessor:
    if _is_chatterbox_engine(engine_name):
        # Use configurable chunk size for Chatterbox, default 450
        chatterbox_chunk_size = 450
        if config:
            chatterbox_chunk_size = config.get("chatterbox_turbo_local_chunk_size", 450)
        # Hard limit is soft limit + 50 to allow sentence completion
        return TextProcessor(
            chunk_strategy="characters",
            char_soft_limit=chatterbox_chunk_size,
            char_hard_limit=chatterbox_chunk_size + 50,
        )
    return TextProcessor(chunk_size=chunk_size)


def estimate_total_chunks(
    text: str,
    split_by_chapter: bool,
    chunk_size: int,
    include_full_story: bool = False,
    engine_name: Optional[str] = None,
    config: Optional[Dict] = None,
) -> int:
    """Estimate total chunk count for a job to power progress indicators."""
    processor = _create_text_processor_for_engine(engine_name or DEFAULT_CONFIG["tts_engine"], chunk_size, config)
    sections = [{"content": text}]
    if split_by_chapter:
        detected = split_text_into_chapters(text)
        if detected:
            sections = detected

    total_chunks = 0
    for section in sections:
        section_text = (section.get("content") or "").strip()
        if not section_text:
            continue
        segments = processor.process_text(section_text)
        for segment in segments:
            total_chunks += len(segment.get("chunks", []))

    return max(total_chunks, 1)


def save_job_metadata(job_dir: Path, metadata: dict):
    """Persist metadata for generated outputs."""
    metadata_path = job_dir / JOB_METADATA_FILENAME
    with open(metadata_path, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=2)
    invalidate_library_cache()


def load_job_metadata(job_dir: Path):
    """Load metadata for a generated job if it exists."""
    metadata_path = job_dir / JOB_METADATA_FILENAME
    if metadata_path.exists():
        try:
            with open(metadata_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as err:
            logger.warning(f"Failed to load metadata from {metadata_path}: {err}")
    return None


def handle_remove_readonly(func, path, exc_info):
    """Handle read-only files on Windows when deleting directories"""
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except Exception as err:  # pragma: no cover - safeguard
        logger.error(f"Failed to remove read-only attribute for {path}: {err}")

def process_job_worker():
    """Background worker that processes jobs from the queue"""
    global current_job_id
    
    logger.info("Job worker thread started")
    
    while True:
        try:
            # Get next job from queue (blocking)
            job_data = job_queue.get(timeout=1)
            
            if job_data is None:  # Poison pill to stop thread
                logger.info("Job worker thread stopping")
                break
            
            job_id = job_data['job_id']
            
            # Check if job was cancelled while in queue
            if cancel_flags.get(job_id, False):
                logger.info(f"Job {job_id} was cancelled before processing")
                with queue_lock:
                    jobs[job_id]['status'] = 'cancelled'
                job_queue.task_done()
                continue
            
            # Set as current job
            with queue_lock:
                current_job_id = job_id
                jobs[job_id]['status'] = 'processing'
                jobs[job_id]['started_at'] = datetime.now().isoformat()
            
            logger.info(f"Processing job {job_id}")
            
            # Process the job
            try:
                process_audio_job(job_data)
            except Exception as e:
                logger.error(f"Error processing job {job_id}: {e}", exc_info=True)
                with queue_lock:
                    jobs[job_id]['status'] = 'failed'
                    jobs[job_id]['error'] = str(e)
            
            # Clear current job
            with queue_lock:
                current_job_id = None
            
            job_queue.task_done()
            
        except queue.Empty:
            continue
        except Exception as e:
            logger.error(f"Worker thread error: {e}", exc_info=True)
            time.sleep(1)


def process_audio_job(job_data):
    """Process a single audio generation job"""
    job_id = job_data['job_id']
    text = job_data['text']
    voice_assignments = job_data['voice_assignments']
    config = job_data['config']
    split_by_chapter = job_data.get('split_by_chapter', False)
    generate_full_story = job_data.get('generate_full_story', False)
    
    try:
        # Check for cancellation
        if cancel_flags.get(job_id, False):
            raise JobCancelled()
        
        review_mode = bool(job_data.get('review_mode', False))
        merge_options_override = job_data.get('merge_options') or {}
        processor = _create_text_processor_for_engine(config.get("tts_engine"), config["chunk_size"], config)
        job_dir = Path(job_data.get('job_dir') or (OUTPUT_DIR / job_id))
        job_dir.mkdir(parents=True, exist_ok=True)
        total_chunks = max(1, job_data.get('total_chunks') or jobs.get(job_id, {}).get('total_chunks') or 1)
        processed_chunks = 0
        job_start_time = datetime.now()

        def update_progress(increment: int = 1):
            if cancel_flags.get(job_id, False):
                raise JobCancelled()
            nonlocal processed_chunks
            processed_chunks += increment
            processed_chunks = min(processed_chunks, total_chunks)
            elapsed = max((datetime.now() - job_start_time).total_seconds(), 0.001)
            remaining = max(total_chunks - processed_chunks, 0)
            eta_seconds = None
            if processed_chunks and remaining:
                eta_seconds = int((elapsed / processed_chunks) * remaining)
            elif remaining == 0:
                eta_seconds = 0

            percent = int((processed_chunks / total_chunks) * 100)
            percent = max(0, min(100, percent))

            with queue_lock:
                job_entry = jobs.get(job_id)
                if job_entry:
                    job_entry['processed_chunks'] = processed_chunks
                    job_entry['total_chunks'] = total_chunks
                    job_entry['progress'] = percent if job_entry.get('status') != 'completed' else 100
                    job_entry['eta_seconds'] = eta_seconds
                    job_entry['last_update'] = datetime.now().isoformat()
        
        # Determine chapter sections when requested
        chapter_sections = [{"title": "Full Story", "content": text}]
        if split_by_chapter:
            detected = split_text_into_chapters(text)
            if detected:
                chapter_sections = detected
            else:
                logger.info("Chapter splitting enabled but no chapter headings detected; falling back to single output")
                split_by_chapter = False
        
        chapter_count = len(chapter_sections)
        with queue_lock:
            job_entry = jobs.get(job_id)
            if job_entry:
                job_entry['chapter_count'] = chapter_count
                job_entry['chapter_mode'] = split_by_chapter
                job_entry['full_story_requested'] = generate_full_story
        
        output_format = config['output_format']
        crossfade_seconds = float(config.get('crossfade_duration', 0) or 0)
        merger = None if review_mode else AudioMerger(
            crossfade_ms=int(max(0.0, crossfade_seconds) * 1000),
            intro_silence_ms=int(max(0, config.get('intro_silence_ms', 0) or 0)),
            inter_chunk_silence_ms=int(max(0, config.get('inter_chunk_silence_ms', 0) or 0)),
            bitrate_kbps=int(config.get('output_bitrate_kbps') or 0)
        )
        chapter_outputs = []
        full_story_entry = None
        all_full_story_chunks = [] if (split_by_chapter and generate_full_story) else None
        chunk_dirs_to_cleanup = []
        review_manifest = {
            "chapter_mode": split_by_chapter,
            "chapters": [],
            "full_story_requested": generate_full_story,
            "output_format": output_format,
            "chunk_dirs_to_cleanup": [],
            "all_full_story_chunks": [],
        }
        
        # Prepare TTS engine
        engine_name = _normalize_engine_name(config.get("tts_engine"))
        engine = get_tts_engine(engine_name, config=config)

        job_chunks: List[Dict[str, Any]] = []

        def register_chunk(chapter_idx: int, chunk_idx: int, segment: Dict[str, Any], file_path: str):
            chunk_id = f"{chapter_idx}-{chunk_idx}-{len(job_chunks)}"
            speaker_name = segment.get("speaker")
            speaker_assignment = None
            if voice_assignments:
                candidate = voice_assignments.get(speaker_name) or voice_assignments.get("default")
                speaker_assignment = _clone_voice_assignment(candidate)
            voice_label = _voice_label_from_assignment(speaker_assignment)
            record = {
                "id": chunk_id,
                "order_index": len(job_chunks),
                "chapter_index": chapter_idx,
                "chunk_index": chunk_idx,
                "speaker": segment.get("speaker"),
                "text": segment.get("text"),
                "file_path": file_path,
                "relative_file": os.path.relpath(file_path, job_dir),
                "duration_seconds": segment.get("duration_seconds"),
                "voice_assignment": speaker_assignment,
            }
            if voice_label:
                record["voice_label"] = voice_label
            job_chunks.append(record)
            with queue_lock:
                job_entry = jobs.get(job_id)
                if job_entry is not None:
                    job_entry.setdefault("chunks", []).append(record)

        def make_chunk_callback(chapter_idx: int):
            def chunk_cb(chunk_idx: int, segment: Dict[str, Any], file_path: str):
                register_chunk(chapter_idx, chunk_idx, segment, file_path)
                update_progress(0)  # keep progress logic centralized
            return chunk_cb

        def generate_chunks(chapter_idx: int, section_text: str, output_dir: Path):
            if cancel_flags.get(job_id, False):
                raise JobCancelled()
            segments = processor.process_text(section_text)
            if not segments:
                return []
            output_dir.mkdir(parents=True, exist_ok=True)
            chunk_cb = make_chunk_callback(chapter_idx)
            supports_chunk_cb = False
            flat_segments: List[Dict[str, Any]] = []
            for seg_idx, segment in enumerate(segments):
                speaker = segment.get("speaker")
                chunks = segment.get("chunks") or []
                for chunk_idx, chunk_text in enumerate(chunks):
                    flat_segments.append({
                        "segment_index": seg_idx,
                        "chunk_index": chunk_idx,
                        "speaker": speaker,
                        "text": chunk_text,
                    })
            engine_kwargs = {
                "segments": segments,
                "voice_config": voice_assignments,
                "output_dir": str(output_dir),
                "speed": config['speed'],
                "progress_cb": update_progress,
            }
            sig_params = inspect.signature(engine.generate_batch).parameters
            if "sample_rate" in sig_params:
                engine_kwargs["sample_rate"] = config.get("sample_rate")
            if "chunk_cb" in sig_params:
                engine_kwargs["chunk_cb"] = chunk_cb
                supports_chunk_cb = True
            if "parallel_workers" in sig_params:
                engine_kwargs["parallel_workers"] = max(1, min(10, int(config.get("parallel_chunks", 1) or 1)))
            audio_files = engine.generate_batch(**engine_kwargs)

            if not supports_chunk_cb and audio_files:
                for order_idx, file_path in enumerate(audio_files):
                    if order_idx >= len(flat_segments):
                        break
                    descriptor = flat_segments[order_idx]
                    register_chunk(
                        chapter_idx,
                        descriptor["chunk_index"],
                        descriptor,
                        file_path,
                    )
            return audio_files

        try:
            if split_by_chapter:
                for idx, chapter in enumerate(chapter_sections, start=1):
                    if cancel_flags.get(job_id, False):
                        raise JobCancelled()

                    chapter_dir = job_dir / f"chapter_{idx:02d}"
                    chunk_dir = chapter_dir / "chunks"
                    audio_files = generate_chunks(idx - 1, chapter["content"], chunk_dir)
                    if not audio_files:
                        logger.warning(f"Chapter {idx} had no audio chunks; skipping")
                        continue

                    if all_full_story_chunks is not None:
                        all_full_story_chunks.extend(audio_files)
                        chunk_dirs_to_cleanup.append(chunk_dir)

                    slug = slugify_filename(chapter['title'], f"chapter-{idx:02d}")
                    output_filename = f"{slug}.{output_format}"
                    output_path = chapter_dir / output_filename

                    if review_mode:
                        rel_chunk_dir = os.path.relpath(chunk_dir, job_dir)
                        rel_chapter_dir = os.path.relpath(chapter_dir, job_dir)
                        rel_chunk_files = [os.path.relpath(path, job_dir) for path in audio_files]
                        review_manifest["chapters"].append({
                            "index": idx - 1,  # 0-indexed to match chunk.chapter_index
                            "title": chapter['title'],
                            "chunk_dir": rel_chunk_dir,
                            "chunk_files": rel_chunk_files,
                            "chapter_dir": rel_chapter_dir,
                            "output_filename": output_filename,
                        })
                        review_manifest["chunk_dirs_to_cleanup"].append(rel_chunk_dir)
                    else:
                        merger.merge_wav_files(
                            input_files=audio_files,
                            output_path=str(output_path),
                            format=output_format,
                            cleanup_chunks=not generate_full_story
                        )
                        update_progress()

                        # Cleanup empty chunk directory
                        if chunk_dir.exists() and not generate_full_story:
                            try:
                                chunk_dir.rmdir()
                            except OSError:
                                pass

                        relative_path = Path(f"chapter_{idx:02d}") / output_filename
                        chapter_outputs.append({
                            "index": idx,
                            "title": chapter['title'],
                            "file_url": f"/static/audio/{job_id}/{relative_path.as_posix()}",
                            "relative_path": relative_path.as_posix()
                        })
            else:
                chunk_dir = job_dir / "chunks"
                audio_files = generate_chunks(0, text, chunk_dir)
                if not audio_files:
                    raise ValueError("Unable to generate audio chunks")
                output_file = job_dir / f"output.{output_format}"
                if review_mode:
                    rel_chunk_dir = os.path.relpath(chunk_dir, job_dir)
                    rel_chapter_dir = os.path.relpath(job_dir, job_dir)
                    rel_chunk_files = [os.path.relpath(path, job_dir) for path in audio_files]
                    review_manifest["chapters"].append({
                        "index": 1,
                        "title": "Full Story",
                        "chunk_dir": rel_chunk_dir,
                        "chunk_files": rel_chunk_files,
                        "chapter_dir": rel_chapter_dir,
                        "output_filename": output_file.name,
                    })
                    review_manifest["chunk_dirs_to_cleanup"].append(rel_chunk_dir)
                else:
                    merger.merge_wav_files(
                        input_files=audio_files,
                        output_path=str(output_file),
                        format=output_format
                    )
                    update_progress()
                    if chunk_dir.exists():
                        try:
                            chunk_dir.rmdir()
                        except OSError:
                            pass

                    chapter_outputs.append({
                        "index": 1,
                        "title": "Full Story",
                        "file_url": f"/static/audio/{job_id}/output.{output_format}",
                        "relative_path": f"output.{output_format}"
                    })

        except Exception:
            raise

        if all_full_story_chunks and not review_mode:
            full_story_name = f"full_story.{output_format}"
            full_story_path = job_dir / full_story_name
            merger.merge_wav_files(
                input_files=all_full_story_chunks,
                output_path=str(full_story_path),
                format=output_format
            )
            update_progress()

            for chunk_dir in chunk_dirs_to_cleanup:
                if chunk_dir.exists():
                    try:
                        chunk_dir.rmdir()
                    except OSError:
                        pass

            full_story_entry = {
                "title": "Full Story",
                "file_url": f"/static/audio/{job_id}/{full_story_name}",
                "relative_path": full_story_name
            }

        if cancel_flags.get(job_id, False):
            raise JobCancelled()

        if review_mode:
            manifest_path = job_dir / "review_manifest.json"
            review_manifest["all_full_story_chunks"] = [
                os.path.relpath(path, job_dir) for path in (all_full_story_chunks or [])
            ]
            with manifest_path.open("w", encoding="utf-8") as handle:
                json.dump(review_manifest, handle, indent=2)
            chunks_meta_path = job_dir / "chunks_metadata.json"
            chunks_meta = {
                "engine": engine_name,
                "created_at": datetime.now().isoformat(),
                "chunks": job_chunks,
            }
            with chunks_meta_path.open("w", encoding="utf-8") as handle:
                json.dump(chunks_meta, handle, indent=2)
            
            # Auto-finish: merge audio and complete the job (review happens in library)
            with queue_lock:
                job_entry = jobs.get(job_id)
                if job_entry:
                    job_entry['review_manifest'] = manifest_path.name
                    job_entry['chapter_mode'] = split_by_chapter
                    job_entry['full_story_requested'] = generate_full_story
            
            _merge_review_job(job_id, jobs.get(job_id), review_manifest)
            logger.info(f"Job {job_id} auto-finished and moved to library for chunk review")
            return

        if not chapter_outputs:
            raise ValueError("No audio outputs were generated")

        metadata = {
            "chapter_mode": split_by_chapter,
            "output_format": output_format,
            "chapters": chapter_outputs,
            "chapter_count": chapter_count,
            "full_story": full_story_entry
        }
        save_job_metadata(job_dir, metadata)
        
        # Update job as completed
        with queue_lock:
            jobs[job_id]['status'] = 'completed'
            jobs[job_id]['progress'] = 100
            jobs[job_id]['processed_chunks'] = total_chunks
            jobs[job_id]['total_chunks'] = total_chunks
            jobs[job_id]['eta_seconds'] = 0
            primary_output = full_story_entry or (chapter_outputs[0] if chapter_outputs else None)
            jobs[job_id]['output_file'] = primary_output['file_url'] if primary_output else ''
            jobs[job_id]['chapter_outputs'] = chapter_outputs
            jobs[job_id]['chapter_mode'] = split_by_chapter
            jobs[job_id]['full_story_requested'] = generate_full_story
            if full_story_entry:
                jobs[job_id]['full_story'] = full_story_entry
            jobs[job_id]['completed_at'] = datetime.now().isoformat()

        
        logger.info(f"Job {job_id} completed successfully with {len(chapter_outputs)} output file(s)")
        
        # Optional VRAM cleanup after job completion
        if config.get("cleanup_vram_after_job", False):
            _cleanup_engine_vram(engine_name)
        
    except JobCancelled:
        logger.info(f"Job {job_id} cancelled – halting synthesis")
        with queue_lock:
            job_entry = jobs.get(job_id)
            if job_entry:
                job_entry['status'] = 'cancelled'
                job_entry['eta_seconds'] = None
                job_entry['last_update'] = datetime.now().isoformat()
        return
    except Exception as e:
        logger.error(f"Error in job {job_id}: {e}", exc_info=True)
        with queue_lock:
            jobs[job_id]['status'] = 'failed'
            jobs[job_id]['error'] = str(e)
        raise
    finally:
        cancel_flags.pop(job_id, None)


def start_worker_thread():
    """Start the background worker thread"""
    global worker_thread
    if worker_thread is None or not worker_thread.is_alive():
        worker_thread = threading.Thread(target=process_job_worker, daemon=True)
        worker_thread.start()
        logger.info("Worker thread started")


def load_config():
    """Load configuration from file"""
    config = DEFAULT_CONFIG.copy()
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                data = json.load(f)
            if isinstance(data, dict):
                config.update({k: v for k, v in data.items() if k in DEFAULT_CONFIG})
        except Exception as exc:
            logger.warning(f"Failed to load config.json, using defaults: {exc}")
    return config


def save_config(config):
    """Save configuration to file"""
    merged = DEFAULT_CONFIG.copy()
    if isinstance(config, dict):
        merged.update({k: v for k, v in config.items() if k in DEFAULT_CONFIG})
    with open(CONFIG_FILE, 'w') as f:
        json.dump(merged, f, indent=2)


@app.route('/')
def index():
    """Main page"""
    return render_template('index.html')


def _load_chatterbox_voice_entries() -> List[Dict[str, Any]]:
    if not CHATTERBOX_VOICE_REGISTRY.exists():
        return []
    try:
        with CHATTERBOX_VOICE_REGISTRY.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
            if isinstance(data, list):
                return data
            logger.warning("Chatterbox voice registry contains invalid data. Resetting.")
            return []
    except (json.JSONDecodeError, OSError) as exc:
        logger.error("Unable to read chatterbox voice registry: %s", exc)
        return []


def _save_chatterbox_voice_entries(entries: List[Dict[str, Any]]) -> None:
    CHATTERBOX_VOICE_REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    with CHATTERBOX_VOICE_REGISTRY.open("w", encoding="utf-8") as handle:
        json.dump(entries, handle, indent=2)


def _cleanup_orphaned_chatterbox_voices() -> int:
    """Remove voice entries from registry where the audio file no longer exists.
    
    Returns the number of orphaned entries removed.
    """
    entries = _load_chatterbox_voice_entries()
    if not entries:
        return 0
    
    valid_entries = []
    removed_count = 0
    for entry in entries:
        file_name = entry.get("file_name")
        if not file_name:
            removed_count += 1
            continue
        file_path = VOICE_PROMPT_DIR / file_name
        if file_path.is_file():
            valid_entries.append(entry)
        else:
            logger.info(f"Removing orphaned Chatterbox voice entry: {entry.get('name', file_name)} (file missing: {file_name})")
            removed_count += 1
    
    if removed_count > 0:
        _save_chatterbox_voice_entries(valid_entries)
        logger.info(f"Cleaned up {removed_count} orphaned Chatterbox voice entries")
    
    return removed_count


def _slugify_filename(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    value = value.strip("_")
    return value or "voice"


def _serialize_chatterbox_voice(entry: Dict[str, Any]) -> Dict[str, Any]:
    file_name = entry.get("file_name")
    file_path = VOICE_PROMPT_DIR / file_name if file_name else None
    exists = file_path.is_file() if file_path else False
    size_bytes = entry.get("size_bytes")
    duration_seconds = entry.get("duration_seconds")
    if exists:
        try:
            size_bytes = file_path.stat().st_size
            if duration_seconds is None:
                duration_seconds = _measure_audio_duration(file_path)
        except OSError:
            size_bytes = None
            duration_seconds = None
    return {
        "id": entry.get("id"),
        "name": entry.get("name"),
        "file_name": file_name,
        "prompt_path": file_name,
        "created_at": entry.get("created_at"),
        "size_bytes": size_bytes,
        "missing_file": not exists,
        "duration_seconds": duration_seconds,
        "is_valid_prompt": bool(duration_seconds and duration_seconds >= MIN_CHATTERBOX_PROMPT_SECONDS),
        "gender": entry.get("gender"),  # Male, Female, or None
        "language": entry.get("language"),  # Language code like en-US
        "source": "local",  # local voices vs external
    }


def _resolve_chatterbox_voice(entry_id: str, entries: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    for entry in entries:
        if entry.get("id") == entry_id:
            return entry
    return None


@app.route('/api/voices', methods=['GET'])
def get_voices():
    """Get available voices"""
    voice_manager = VoiceManager()
    missing = voice_manager.missing_samples()
    return jsonify({
        "success": True,
        "voices": voice_manager.get_all_voices(),
        "samples_ready": voice_manager.all_samples_present(),
        "missing_samples": missing,
        "total_unique_voices": voice_manager.total_unique_voice_count(),
        "sample_count": voice_manager.sample_count()
    })


def _get_audio_duration(file_path: Path) -> Optional[float]:
    """Get audio duration in seconds using pydub."""
    try:
        from pydub import AudioSegment
        audio = AudioSegment.from_file(str(file_path))
        return len(audio) / 1000.0  # pydub returns milliseconds
    except Exception as e:
        logger.debug("Could not get duration for %s: %s", file_path.name, e)
        return None


# Cache for voice prompt durations to avoid re-reading files
_voice_prompt_duration_cache: Dict[str, float] = {}


@app.route('/api/voice-prompts', methods=['GET'])
def list_voice_prompts():
    """List available reference audio prompts."""
    try:
        # Load chatterbox voice registry for metadata lookup
        chatterbox_entries = _load_chatterbox_voice_entries()
        chatterbox_by_file = {e.get("file_name"): e for e in chatterbox_entries if e.get("file_name")}
        
        prompts = []
        for path in sorted(VOICE_PROMPT_DIR.glob('*')):
            if not path.is_file():
                continue
            if path.suffix.lower() not in VOICE_PROMPT_EXTENSIONS:
                continue
            try:
                size_bytes = path.stat().st_size
                mtime = path.stat().st_mtime
            except OSError:
                size_bytes = None
                mtime = None
            
            # Check cache for duration (keyed by name + mtime)
            cache_key = f"{path.name}:{mtime}" if mtime else None
            duration_seconds = None
            if cache_key and cache_key in _voice_prompt_duration_cache:
                duration_seconds = _voice_prompt_duration_cache[cache_key]
            else:
                duration_seconds = _get_audio_duration(path)
                if cache_key and duration_seconds is not None:
                    _voice_prompt_duration_cache[cache_key] = duration_seconds
            
            # Get metadata from chatterbox registry if available
            registry_entry = chatterbox_by_file.get(path.name, {})
            gender = registry_entry.get("gender")
            language = registry_entry.get("language")
            display_name = registry_entry.get("name") or path.stem.replace('_', ' ').replace('-', ' ').title()
            
            prompts.append(
                {
                    "name": path.name,
                    "display": display_name,
                    "size_bytes": size_bytes,
                    "duration_seconds": duration_seconds,
                    "gender": gender,
                    "language": language,
                }
            )
        return jsonify({"success": True, "prompts": prompts})
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("Failed to list voice prompts: %s", exc, exc_info=True)
        return jsonify({"success": False, "error": "Failed to list voice prompts"}), 500


@app.route('/api/voice-prompts/upload', methods=['POST'])
def upload_voice_prompt():
    """Upload a new reference prompt clip."""
    file = request.files.get('file')
    if not file or not file.filename:
        return jsonify({"success": False, "error": "No file provided"}), 400

    filename = secure_filename(file.filename)
    if not filename:
        return jsonify({"success": False, "error": "Invalid filename"}), 400

    suffix = Path(filename).suffix.lower()
    if suffix not in VOICE_PROMPT_EXTENSIONS:
        allowed = ", ".join(sorted(ext.lstrip(".") for ext in VOICE_PROMPT_EXTENSIONS))
        return jsonify(
            {
                "success": False,
                "error": f"Unsupported file type '{suffix}'. Allowed: {allowed}",
            }
        ), 400

    target_path = VOICE_PROMPT_DIR / filename
    stem = Path(filename).stem
    counter = 1
    while target_path.exists():
        target_path = VOICE_PROMPT_DIR / f"{stem}_{counter}{suffix}"
        counter += 1

    try:
        file.save(target_path)
    except Exception as exc:  # pragma: no cover - filesystem failure
        logger.error("Failed to save uploaded prompt: %s", exc, exc_info=True)
        return jsonify({"success": False, "error": "Failed to save file"}), 500

    return jsonify(
        {
            "success": True,
            "prompt": {
                "name": target_path.name,
                "display": target_path.stem.replace('_', ' ').replace('-', ' ').title(),
                "size_bytes": target_path.stat().st_size,
            },
        }
    ), 201


@app.route('/api/chatterbox-voices', methods=['GET'])
def list_chatterbox_voices():
    entries = _load_chatterbox_voice_entries()
    serialized = [_serialize_chatterbox_voice(entry) for entry in entries]
    return jsonify({"success": True, "voices": serialized})


@app.route('/api/chatterbox-voices', methods=['POST'])
def create_chatterbox_voice():
    name = (request.form.get("name") or "").strip()
    file = request.files.get("file")
    if not name:
        return jsonify({"success": False, "error": "Voice name is required."}), 400
    if not file or not file.filename:
        return jsonify({"success": False, "error": "Audio file is required."}), 400

    filename = secure_filename(file.filename)
    suffix = Path(filename).suffix.lower()
    if suffix not in VOICE_PROMPT_EXTENSIONS:
        allowed = ", ".join(sorted(ext.lstrip(".") for ext in VOICE_PROMPT_EXTENSIONS))
        return jsonify(
            {
                "success": False,
                "error": f"Unsupported file type '{suffix}'. Allowed: {allowed}",
            }
        ), 400

    slug = _slugify_filename(name)
    target_path = VOICE_PROMPT_DIR / f"{slug}{suffix}"
    counter = 1
    while target_path.exists():
        target_path = VOICE_PROMPT_DIR / f"{slug}_{counter}{suffix}"
        counter += 1

    try:
        file.save(target_path)
    except Exception as exc:  # pragma: no cover - filesystem failure
        logger.error("Failed to save chatterbox voice: %s", exc, exc_info=True)
        return jsonify({"success": False, "error": "Failed to save file"}), 500

    entries = _load_chatterbox_voice_entries()
    duration_seconds = _measure_audio_duration(target_path)
    if not duration_seconds:
        target_path.unlink(missing_ok=True)
        return jsonify({
            "success": False,
            "error": "Unable to determine audio duration. Please upload a standard WAV/MP3 clip."
        }), 400
    if duration_seconds < MIN_CHATTERBOX_PROMPT_SECONDS:
        target_path.unlink(missing_ok=True)
        return jsonify({
            "success": False,
            "error": f"Clip is only {duration_seconds:.2f}s. Chatterbox Turbo requires at least {MIN_CHATTERBOX_PROMPT_SECONDS:.0f} seconds."
        }), 400

    entry = {
        "id": str(uuid.uuid4()),
        "name": name,
        "file_name": target_path.name,
        "created_at": datetime.utcnow().isoformat(),
        "size_bytes": target_path.stat().st_size,
        "duration_seconds": duration_seconds,
    }
    entries.append(entry)
    _save_chatterbox_voice_entries(entries)

    serialized = _serialize_chatterbox_voice(entry)
    return jsonify({"success": True, "voice": serialized}), 201


@app.route('/api/chatterbox-voices/<voice_id>', methods=['PUT'])
def rename_chatterbox_voice(voice_id: str):
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"success": False, "error": "Voice name is required."}), 400

    entries = _load_chatterbox_voice_entries()
    entry = _resolve_chatterbox_voice(voice_id, entries)
    if not entry:
        return jsonify({"success": False, "error": "Voice not found."}), 404

    entry["name"] = name
    _save_chatterbox_voice_entries(entries)
    return jsonify({"success": True, "voice": _serialize_chatterbox_voice(entry)})


@app.route('/api/chatterbox-voices/<voice_id>', methods=['DELETE'])
def delete_chatterbox_voice(voice_id: str):
    entries = _load_chatterbox_voice_entries()
    entry = _resolve_chatterbox_voice(voice_id, entries)
    if not entry:
        return jsonify({"success": False, "error": "Voice not found."}), 404

    file_name = entry.get("file_name")
    file_path = VOICE_PROMPT_DIR / file_name if file_name else None
    if file_path and file_path.exists():
        try:
            file_path.unlink()
        except OSError as exc:  # pragma: no cover - filesystem failure
            logger.warning("Unable to delete voice prompt file %s: %s", file_path, exc)

    entries = [item for item in entries if item.get("id") != voice_id]
    _save_chatterbox_voice_entries(entries)
    return jsonify({"success": True})


@app.route('/api/chatterbox-voices/<voice_id>/preview')
def preview_chatterbox_voice(voice_id: str):
    entries = _load_chatterbox_voice_entries()
    entry = _resolve_chatterbox_voice(voice_id, entries)
    if not entry:
        return jsonify({"success": False, "error": "Voice not found."}), 404
    file_name = entry.get("file_name")
    if not file_name:
        return jsonify({"success": False, "error": "Voice has no associated file."}), 404
    file_path = VOICE_PROMPT_DIR / file_name
    if not file_path.exists():
        return jsonify({"success": False, "error": "Audio file missing on disk."}), 404
    mime_type, _ = mimetypes.guess_type(file_path.name)
    return send_file(
        file_path,
        mimetype=mime_type or 'audio/mpeg',
        conditional=True,
        as_attachment=False,
        download_name=file_path.name,
    )


# External TTS samples from GitHub
EXTERNAL_VOICES_CACHE_FILE = Path("data/external_voices_cache.json")
EXTERNAL_VOICES_URL = "https://raw.githubusercontent.com/yaph/tts-samples/main/data/voices.json"
EXTERNAL_SAMPLES_BASE_URL = "https://raw.githubusercontent.com/yaph/tts-samples/main/mp3"
EXTERNAL_VOICES_DIR = Path("data/external_voices")
EXTERNAL_VOICES_DIR.mkdir(parents=True, exist_ok=True)

# Mapping from locale code prefix to GitHub folder name
LOCALE_TO_FOLDER = {
    'af': 'Afrikaans', 'sq': 'Albanian', 'am': 'Amharic', 'ar': 'Arabic',
    'az': 'Azerbaijani', 'bn': 'Bengali', 'bs': 'Bosnian', 'bg': 'Bulgarian',
    'my': 'Burmese', 'ca': 'Catalan', 'zh': 'Chinese', 'yue': 'Chinese',
    'wuu': 'Chinese', 'hr': 'Croatian', 'cs': 'Czech', 'da': 'Danish',
    'nl': 'Dutch', 'en': 'English', 'et': 'Estonian', 'fil': 'Filipino',
    'fi': 'Finnish', 'fr': 'French', 'gl': 'Galician', 'ka': 'Georgian',
    'de': 'German', 'el': 'Greek', 'gu': 'Gujarati', 'he': 'Hebrew',
    'hi': 'Hindi', 'hu': 'Hungarian', 'is': 'Icelandic', 'id': 'Indonesian',
    'ga': 'Irish', 'it': 'Italian', 'ja': 'Japanese', 'jv': 'Javanese',
    'kn': 'Kannada', 'kk': 'Kazakh', 'km': 'Khmer', 'ko': 'Korean',
    'lo': 'Lao', 'lv': 'Latvian', 'lt': 'Lithuanian', 'mk': 'Macedonian',
    'ms': 'Malay', 'ml': 'Malayalam', 'mt': 'Maltese', 'mr': 'Marathi',
    'mn': 'Mongolian', 'ne': 'Nepali', 'nb': 'Norwegian', 'ps': 'Pashto',
    'fa': 'Persian', 'pl': 'Polish', 'pt': 'Portuguese', 'ro': 'Romanian',
    'ru': 'Russian', 'sr': 'Serbian', 'si': 'Sinhala', 'sk': 'Slovak',
    'sl': 'Slovenian', 'so': 'Somali', 'es': 'Spanish', 'su': 'Sundanese',
    'sw': 'Swahili', 'sv': 'Swedish', 'ta': 'Tamil', 'te': 'Telugu',
    'th': 'Thai', 'tr': 'Turkish', 'uk': 'Ukrainian', 'ur': 'Urdu',
    'uz': 'Uzbek', 'vi': 'Vietnamese', 'cy': 'Welsh', 'zu': 'Zulu',
    'eu': 'Basque',
}

def _get_github_folder_for_locale(locale: str) -> str:
    """Get the GitHub folder name for a locale code like 'en-GB' -> 'English'."""
    if not locale:
        return "English"
    # Extract language code (e.g., 'en' from 'en-GB')
    lang_code = locale.split('-')[0].lower()
    return LOCALE_TO_FOLDER.get(lang_code, "English")

_external_voices_cache: Optional[List[Dict[str, Any]]] = None
_external_voices_cache_time: float = 0


def _fetch_external_voices(force_refresh: bool = False) -> List[Dict[str, Any]]:
    """Fetch external TTS voice samples from GitHub with caching."""
    global _external_voices_cache, _external_voices_cache_time
    
    cache_max_age = 3600 * 24  # 24 hours
    now = time.time()
    
    # Return memory cache if fresh
    if not force_refresh and _external_voices_cache and (now - _external_voices_cache_time) < cache_max_age:
        return _external_voices_cache
    
    # Try to load from file cache
    if not force_refresh and EXTERNAL_VOICES_CACHE_FILE.exists():
        try:
            cache_mtime = EXTERNAL_VOICES_CACHE_FILE.stat().st_mtime
            if (now - cache_mtime) < cache_max_age:
                with EXTERNAL_VOICES_CACHE_FILE.open("r", encoding="utf-8") as f:
                    _external_voices_cache = json.load(f)
                    _external_voices_cache_time = now
                    return _external_voices_cache
        except Exception as e:
            logger.warning("Failed to load external voices cache: %s", e)
    
    # Fetch from GitHub
    try:
        import urllib.request
        logger.info("Fetching external TTS voices from GitHub...")
        with urllib.request.urlopen(EXTERNAL_VOICES_URL, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8"))
        
        # Save to file cache
        EXTERNAL_VOICES_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with EXTERNAL_VOICES_CACHE_FILE.open("w", encoding="utf-8") as f:
            json.dump(data, f)
        
        _external_voices_cache = data
        _external_voices_cache_time = now
        logger.info("Fetched %d external TTS voices", len(data))
        return data
    except Exception as e:
        logger.error("Failed to fetch external voices: %s", e)
        # Return stale cache if available
        if _external_voices_cache:
            return _external_voices_cache
        return []


def _serialize_external_voice(voice: Dict[str, Any]) -> Dict[str, Any]:
    """Serialize an external voice entry for the API."""
    short_name = voice.get("ShortName", "")
    locale = voice.get("Locale", "")
    gender = voice.get("Gender", "")
    friendly_name = voice.get("FriendlyName", "")
    
    # Extract clean name from FriendlyName (e.g., "Microsoft Jenny Online (Natural) - English (United States)")
    name_match = re.match(r"Microsoft (\w+)", friendly_name)
    display_name = name_match.group(1) if name_match else short_name
    
    # Check if downloaded locally
    local_file = EXTERNAL_VOICES_DIR / f"{short_name}.mp3"
    is_downloaded = local_file.exists()
    
    # Get correct GitHub folder name (e.g., "English" not "en-GB")
    folder_name = _get_github_folder_for_locale(locale)
    
    return {
        "id": f"external:{short_name}",
        "name": display_name,
        "short_name": short_name,
        "file_name": f"{short_name}.mp3" if is_downloaded else None,
        "prompt_path": str(local_file) if is_downloaded else None,
        "gender": gender,
        "language": locale,
        "friendly_name": friendly_name,
        "source": "external",
        "is_downloaded": is_downloaded,
        "download_url": f"{EXTERNAL_SAMPLES_BASE_URL}/{folder_name}/{short_name}.mp3",
        "voice_personalities": voice.get("VoiceTag", {}).get("VoicePersonalities", []),
    }


@app.route('/api/external-voices', methods=['GET'])
def list_external_voices():
    """List available external TTS voice samples from GitHub."""
    try:
        force_refresh = request.args.get('refresh', '').lower() == 'true'
        voices = _fetch_external_voices(force_refresh=force_refresh)
        serialized = [_serialize_external_voice(v) for v in voices]
        return jsonify({
            "success": True,
            "voices": serialized,
            "total": len(serialized),
        })
    except Exception as e:
        logger.error("Failed to list external voices: %s", e, exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/external-voices/<voice_id>/download', methods=['POST'])
def download_external_voice(voice_id: str):
    """Download an external voice sample to use locally."""
    try:
        # Find the voice in the cache
        voices = _fetch_external_voices()
        voice = None
        for v in voices:
            if v.get("ShortName") == voice_id:
                voice = v
                break
        
        if not voice:
            return jsonify({"success": False, "error": "Voice not found"}), 404
        
        short_name = voice.get("ShortName")
        locale = voice.get("Locale")
        folder_name = _get_github_folder_for_locale(locale)
        download_url = f"{EXTERNAL_SAMPLES_BASE_URL}/{folder_name}/{short_name}.mp3"
        local_file = EXTERNAL_VOICES_DIR / f"{short_name}.mp3"
        
        # Download the file
        import urllib.request
        logger.info("Downloading external voice: %s", short_name)
        urllib.request.urlretrieve(download_url, str(local_file))
        
        # Also copy to voice_prompts directory for use with TTS engines
        voice_prompt_file = VOICE_PROMPT_DIR / f"{short_name}.mp3"
        shutil.copy(str(local_file), str(voice_prompt_file))
        
        # Add to chatterbox voices registry
        entries = _load_chatterbox_voice_entries()
        existing = next((e for e in entries if e.get("file_name") == f"{short_name}.mp3"), None)
        if not existing:
            # Extract display name
            friendly_name = voice.get("FriendlyName", "")
            name_match = re.match(r"Microsoft (\w+)", friendly_name)
            display_name = name_match.group(1) if name_match else short_name
            
            new_entry = {
                "id": str(uuid.uuid4()),
                "name": f"{display_name} ({locale})",
                "file_name": f"{short_name}.mp3",
                "created_at": datetime.utcnow().isoformat(),
                "gender": voice.get("Gender"),
                "language": locale,
            }
            entries.append(new_entry)
            _save_chatterbox_voice_entries(entries)
        
        return jsonify({
            "success": True,
            "voice": _serialize_external_voice(voice),
            "message": f"Downloaded {short_name}.mp3"
        })
    except Exception as e:
        logger.error("Failed to download external voice %s: %s", voice_id, e, exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/external-voices/<voice_id>/preview')
def preview_external_voice(voice_id: str):
    """Stream preview of an external voice (downloads if not cached)."""
    try:
        voices = _fetch_external_voices()
        voice = None
        for v in voices:
            if v.get("ShortName") == voice_id:
                voice = v
                break
        
        if not voice:
            return jsonify({"success": False, "error": "Voice not found"}), 404
        
        short_name = voice.get("ShortName")
        local_file = EXTERNAL_VOICES_DIR / f"{short_name}.mp3"
        
        # Download if not cached
        if not local_file.exists():
            locale = voice.get("Locale")
            folder_name = _get_github_folder_for_locale(locale)
            download_url = f"{EXTERNAL_SAMPLES_BASE_URL}/{folder_name}/{short_name}.mp3"
            import urllib.request
            urllib.request.urlretrieve(download_url, str(local_file))
        
        return send_file(
            local_file,
            mimetype='audio/mpeg',
            conditional=True,
            as_attachment=False,
            download_name=f"{short_name}.mp3",
        )
    except Exception as e:
        logger.error("Failed to preview external voice %s: %s", voice_id, e, exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/chatterbox-voices/<voice_id>/update', methods=['PUT'])
def update_chatterbox_voice_metadata(voice_id: str):
    """Update metadata (gender, language) for a chatterbox voice."""
    data = request.get_json() or {}
    
    entries = _load_chatterbox_voice_entries()
    entry = _resolve_chatterbox_voice(voice_id, entries)
    if not entry:
        return jsonify({"success": False, "error": "Voice not found."}), 404
    
    # Update allowed fields
    if "gender" in data:
        entry["gender"] = data["gender"] if data["gender"] in ("Male", "Female", None) else None
    if "language" in data:
        entry["language"] = data["language"]
    if "name" in data and data["name"]:
        entry["name"] = data["name"].strip()
    
    _save_chatterbox_voice_entries(entries)
    return jsonify({"success": True, "voice": _serialize_chatterbox_voice(entry)})


@app.route('/api/voices/samples', methods=['POST'])
def generate_voice_samples_api():
    """Generate preview samples for all voices."""
    overwrite = request.json.get('overwrite', False) if request.is_json else False
    sample_text = request.json.get('text') if request.is_json else None
    device = request.json.get('device', 'auto') if request.is_json else 'auto'

    logger.info("Voice sample generation requested", extra={
        "overwrite": overwrite,
        "device": device
    })

    try:
        report = generate_voice_samples(
            overwrite=overwrite,
            device=device,
            sample_text=sample_text or None,
        )
    except RuntimeError as err:
        logger.error(f"Voice sample generation failed: {err}")
        return jsonify({
            "success": False,
            "error": str(err)
        }), 400
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("Unexpected error during voice sample generation", exc_info=True)
        return jsonify({
            "success": False,
            "error": "Failed to generate voice samples"
        }), 500


def _serialize_chunk_for_response(job_id: str, chunk: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": chunk.get("id"),
        "order_index": chunk.get("order_index"),
        "chapter_index": chunk.get("chapter_index"),
        "chunk_index": chunk.get("chunk_index"),
        "speaker": chunk.get("speaker"),
        "text": chunk.get("text"),
        "relative_file": chunk.get("relative_file"),
        "file_url": _chunk_file_url(job_id, chunk.get("relative_file")),
        "duration_seconds": chunk.get("duration_seconds"),
        "regenerated_at": chunk.get("regenerated_at"),
        "voice": chunk.get("voice_label"),
        "voice_assignment": chunk.get("voice_assignment"),
    }


@app.route('/api/jobs/<job_id>/chunks', methods=['GET'])
def get_job_chunks(job_id: str):
    """Return chunk metadata for a review-enabled job."""
    try:
        with queue_lock:
            job_entry = jobs.get(job_id)
            if not job_entry:
                return jsonify({"success": False, "error": "Job not found"}), 404
            _ensure_review_ready(job_entry)
            chunks = [dict(item) for item in (job_entry.get("chunks") or [])]
            regen_tasks = copy.deepcopy(job_entry.get("regen_tasks") or {})
            review_status = {
                "status": job_entry.get("status"),
                "chapter_mode": job_entry.get("chapter_mode"),
                "full_story_requested": job_entry.get("full_story_requested"),
                "has_active_regen": _has_active_regen_tasks(job_entry),
                "engine": job_entry.get("engine"),
            }

        payload = {
            "success": True,
            "chunks": [_serialize_chunk_for_response(job_id, c) for c in chunks],
            "regen_tasks": regen_tasks,
            "review": review_status,
        }
        return jsonify(payload)
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("Failed to load chunks for job %s: %s", job_id, exc, exc_info=True)
        return jsonify({"success": False, "error": "Failed to load job chunks"}), 500


@app.route('/api/jobs/<job_id>/review/regen', methods=['POST'])
def request_chunk_regeneration(job_id: str):
    """Schedule a chunk regeneration request."""
    data = request.json or {}
    chunk_id = (data.get("chunk_id") or "").strip()
    updated_text = (data.get("text") or "").strip()
    voice_payload = data.get("voice") or {}
    engine_override = (data.get("engine") or "").strip() or None

    if not chunk_id:
        return jsonify({"success": False, "error": "chunk_id is required"}), 400
    if not updated_text:
        return jsonify({"success": False, "error": "Updated text cannot be empty"}), 400

    try:
        with queue_lock:
            job_entry = jobs.get(job_id)
            if not job_entry:
                return jsonify({"success": False, "error": "Job not found"}), 404
            _ensure_review_ready(job_entry)
            _, chunk = _find_chunk_record(job_entry, chunk_id)
            if chunk is None:
                return jsonify({"success": False, "error": "Chunk not found"}), 404
            regen_tasks = job_entry.setdefault("regen_tasks", {})
            task_state = regen_tasks.get(chunk_id)
            if task_state and task_state.get("status") in {"queued", "running"}:
                return jsonify({"success": False, "error": "Chunk regeneration already in progress"}), 409

        _schedule_chunk_regeneration(job_id, chunk_id, updated_text, voice_payload, engine_override=engine_override)
        return jsonify({"success": True})
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("Failed to schedule chunk regen for job %s chunk %s: %s", job_id, chunk_id, exc, exc_info=True)
        return jsonify({"success": False, "error": "Failed to schedule chunk regeneration"}), 500


@app.route('/api/jobs/<job_id>/review/regen-all', methods=['POST'])
def request_full_job_regeneration(job_id: str):
    """Schedule regeneration for every chunk in the job."""
    data = request.json or {}
    chunk_updates_raw = data.get("chunks") or []
    global_engine_override = (data.get("engine") or "").strip() or None
    chunk_updates: Dict[str, Dict[str, Any]] = {}
    for entry in chunk_updates_raw:
        if not isinstance(entry, dict):
            continue
        chunk_key = (entry.get("chunk_id") or "").strip()
        if not chunk_key:
            continue
        chunk_updates[chunk_key] = {
            "text": (entry.get("text") or "").strip(),
            "voice": entry.get("voice"),
            "engine": (entry.get("engine") or "").strip() or None,
        }

    try:
        with queue_lock:
            job_entry = jobs.get(job_id)
            if not job_entry:
                return jsonify({"success": False, "error": "Job not found"}), 404
            _ensure_review_ready(job_entry)
            if _has_active_regen_tasks(job_entry):
                return jsonify({"success": False, "error": "Chunk regeneration already in progress"}), 409
            job_chunks = job_entry.get("chunks") or []
            if not job_chunks:
                return jsonify({"success": False, "error": "No chunks available to regenerate"}), 400
            tasks_to_schedule: List[Tuple[str, str, Optional[Dict[str, Any]], Optional[str]]] = []
            for chunk in job_chunks:
                chunk_id = chunk.get("id")
                if not chunk_id:
                    continue
                overrides = chunk_updates.get(chunk_id) or {}
                text_value = (overrides.get("text") or chunk.get("text") or "").strip()
                if not text_value:
                    raise ValueError(f"Chunk {chunk_id} does not have text to regenerate.")
                voice_payload = overrides.get("voice")
                engine_override = overrides.get("engine") or global_engine_override
                tasks_to_schedule.append((chunk_id, text_value, voice_payload, engine_override))
        for chunk_id, text_value, voice_payload, engine_override in tasks_to_schedule:
            _schedule_chunk_regeneration(job_id, chunk_id, text_value, voice_payload, engine_override=engine_override)
        return jsonify({"success": True, "queued_chunks": len(tasks_to_schedule)})
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("Failed to queue full regeneration for job %s: %s", job_id, exc, exc_info=True)
        return jsonify({"success": False, "error": "Failed to queue full regeneration"}), 500


@app.route('/api/jobs/<job_id>/review/apply-fx', methods=['POST'])
def apply_chunk_audio_effects(job_id: str):
    """Apply audio effects (speed, pitch) to one or more chunks without regenerating."""
    from src.audio_effects import AudioPostProcessor, VoiceFXSettings
    import soundfile as sf
    
    data = request.json or {}
    chunks_fx = data.get("chunks") or []
    
    if not chunks_fx:
        return jsonify({"success": False, "error": "No chunks specified"}), 400
    
    try:
        with queue_lock:
            job_entry = jobs.get(job_id)
            if not job_entry:
                return jsonify({"success": False, "error": "Job not found"}), 404
            _ensure_review_ready(job_entry)
            job_dir = _job_dir_from_entry(job_id, job_entry)
            job_chunks = job_entry.get("chunks") or []
            chunk_map = {c.get("id"): c for c in job_chunks if c.get("id")}
        
        processor = AudioPostProcessor()
        processed_count = 0
        errors = []
        
        for fx_entry in chunks_fx:
            chunk_id = (fx_entry.get("chunk_id") or "").strip()
            if not chunk_id:
                continue
            
            chunk = chunk_map.get(chunk_id)
            if not chunk:
                errors.append(f"Chunk {chunk_id} not found")
                continue
            
            relative_file = chunk.get("relative_file")
            if not relative_file:
                errors.append(f"Chunk {chunk_id} has no audio file")
                continue
            
            audio_path = job_dir / relative_file
            if not audio_path.exists():
                errors.append(f"Audio file not found for chunk {chunk_id}")
                continue
            
            # Parse FX settings
            speed = float(fx_entry.get("speed", 1.0) or 1.0)
            pitch = float(fx_entry.get("pitch", 0.0) or 0.0)
            
            # Skip if no changes
            if abs(speed - 1.0) < 1e-3 and abs(pitch) < 1e-3:
                continue
            
            try:
                # Load audio
                audio_data, sample_rate = sf.read(str(audio_path), dtype='float32')
                
                # Create FX settings - use no blending for post-apply effects
                fx = VoiceFXSettings(
                    pitch_semitones=max(-12.0, min(12.0, pitch)),
                    speed=max(0.5, min(2.0, speed)),
                    tone="neutral"
                )
                
                # Apply effects without blending (blend_override=0 means no original mixed in)
                processed = processor.apply(audio_data, sample_rate, fx, blend_override=0.0)
                
                # Save back to file
                sf.write(str(audio_path), processed, sample_rate)
                
                # Update chunk metadata
                with queue_lock:
                    job_entry = jobs.get(job_id)
                    if job_entry:
                        for c in job_entry.get("chunks", []):
                            if c.get("id") == chunk_id:
                                c["fx_applied"] = {"speed": speed, "pitch": pitch}
                                c["modified_at"] = datetime.now().isoformat()
                                break
                
                processed_count += 1
                
            except Exception as exc:
                logger.error("Failed to apply FX to chunk %s: %s", chunk_id, exc, exc_info=True)
                errors.append(f"Failed to process chunk {chunk_id}: {str(exc)}")
        
        # Persist metadata changes
        _persist_chunks_metadata(job_id, job_dir)
        
        return jsonify({
            "success": True,
            "processed": processed_count,
            "errors": errors if errors else None
        })
        
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception as exc:
        logger.error("Failed to apply audio effects for job %s: %s", job_id, exc, exc_info=True)
        return jsonify({"success": False, "error": "Failed to apply audio effects"}), 500


@app.route('/api/jobs/<job_id>/review/preview-fx', methods=['POST'])
def preview_chunk_audio_effects(job_id: str):
    """Preview audio effects on a chunk without saving. Returns the processed audio file."""
    from src.audio_effects import AudioPostProcessor, VoiceFXSettings
    import soundfile as sf
    import tempfile
    import io
    
    data = request.json or {}
    chunk_id = (data.get("chunk_id") or "").strip()
    speed = float(data.get("speed", 1.0) or 1.0)
    pitch = float(data.get("pitch", 0.0) or 0.0)
    
    if not chunk_id:
        return jsonify({"success": False, "error": "chunk_id is required"}), 400
    
    try:
        # First try to restore job from library if not in memory
        job_dir = OUTPUT_DIR / job_id
        if not job_dir.exists():
            return jsonify({"success": False, "error": "Job not found"}), 404
        
        # Load chunks metadata to find the chunk
        chunks_meta_path = job_dir / "chunks_metadata.json"
        chunk = None
        if chunks_meta_path.exists():
            with chunks_meta_path.open("r", encoding="utf-8") as f:
                chunks_meta = json.load(f)
                for c in chunks_meta.get("chunks", []):
                    if c.get("id") == chunk_id:
                        chunk = c
                        break
        
        if not chunk:
            return jsonify({"success": False, "error": "Chunk not found"}), 404
        
        relative_file = chunk.get("relative_file")
        if not relative_file:
            return jsonify({"success": False, "error": "Chunk has no audio file"}), 400
        
        audio_path = job_dir / relative_file
        if not audio_path.exists():
            return jsonify({"success": False, "error": "Audio file not found"}), 404
        
        # Load audio
        audio_data, sample_rate = sf.read(str(audio_path), dtype='float32')
        
        # If no effects, just return the original
        if abs(speed - 1.0) < 1e-3 and abs(pitch) < 1e-3:
            return send_file(str(audio_path), mimetype='audio/wav')
        
        # Create FX settings and apply without blending
        fx = VoiceFXSettings(
            pitch_semitones=max(-12.0, min(12.0, pitch)),
            speed=max(0.5, min(2.0, speed)),
            tone="neutral"
        )
        
        processor = AudioPostProcessor()
        processed = processor.apply(audio_data, sample_rate, fx, blend_override=0.0)
        
        # Write to in-memory buffer
        buffer = io.BytesIO()
        sf.write(buffer, processed, sample_rate, format='WAV')
        buffer.seek(0)
        
        return send_file(
            buffer,
            mimetype='audio/wav',
            as_attachment=False,
            download_name=f"preview_{chunk_id}.wav"
        )
        
    except Exception as exc:
        logger.error("Failed to preview audio effects for job %s chunk %s: %s", job_id, chunk_id, exc, exc_info=True)
        return jsonify({"success": False, "error": "Failed to preview audio effects"}), 500


def _merge_review_job(job_id: str, job_entry: Dict[str, Any], manifest: Dict[str, Any]):
    config_snapshot = copy.deepcopy(job_entry.get("config_snapshot") or load_config())
    merge_options = job_entry.get("merge_options") or {}
    output_format = merge_options.get("output_format") or config_snapshot.get("output_format") or "mp3"
    crossfade_seconds = float(merge_options.get("crossfade_duration") or 0)
    merger = AudioMerger(
        crossfade_ms=int(max(0.0, crossfade_seconds) * 1000),
        intro_silence_ms=int(max(0, merge_options.get("intro_silence_ms") or 0)),
        inter_chunk_silence_ms=int(max(0, merge_options.get("inter_chunk_silence_ms") or 0)),
        bitrate_kbps=int(merge_options.get("output_bitrate_kbps") or 0),
    )
    job_dir = _job_dir_from_entry(job_id, job_entry)

    chapter_outputs = []
    for chapter in manifest.get("chapters", []):
        rel_chunk_files = chapter.get("chunk_files") or []
        chunk_paths = [str(job_dir / rel_path) for rel_path in rel_chunk_files]
        if not chunk_paths:
            continue
        # Verify chunk files exist before merging
        missing_chunks = [p for p in chunk_paths if not Path(p).exists()]
        if missing_chunks:
            logger.error(f"Missing chunk files for merge: {missing_chunks}")
            continue
        logger.info(f"Merging {len(chunk_paths)} chunks: {chunk_paths}")
        output_filename = chapter.get("output_filename") or f"chapter_{chapter.get('index', 0):02d}.{output_format}"
        chapter_dir = job_dir / (chapter.get("chapter_dir") or ".")
        chapter_dir.mkdir(parents=True, exist_ok=True)
        output_path = chapter_dir / output_filename
        logger.info(f"Output path: {output_path}")
        merger.merge_wav_files(
            input_files=chunk_paths,
            output_path=str(output_path),
            format=output_format,
            cleanup_chunks=False,
        )
        # Verify output was created with content
        if output_path.exists():
            output_size = output_path.stat().st_size
            logger.info(f"Merged output size: {output_size} bytes")
            if output_size < 1000:
                logger.warning(f"Output file suspiciously small: {output_size} bytes")
        rel_path = (Path(chapter.get("chapter_dir") or ".") / output_filename).as_posix()
        # Normalize "./filename" to just "filename"
        if rel_path.startswith("./"):
            rel_path = rel_path[2:]
        chapter_outputs.append({
            "index": chapter.get("index"),
            "title": chapter.get("title"),
            "file_url": f"/static/audio/{job_id}/{rel_path}",
            "relative_path": rel_path,
        })

    full_story_entry = None
    all_full_story_chunks = manifest.get("all_full_story_chunks") or []
    if all_full_story_chunks:
        chunk_paths = [str(job_dir / rel_path) for rel_path in all_full_story_chunks]
        full_story_name = f"full_story.{output_format}"
        full_story_path = job_dir / full_story_name
        merger.merge_wav_files(
            input_files=chunk_paths,
            output_path=str(full_story_path),
            format=output_format,
            cleanup_chunks=False,
        )
        full_story_entry = {
            "title": "Full Story",
            "file_url": f"/static/audio/{job_id}/{full_story_name}",
            "relative_path": full_story_name,
        }

    metadata = {
        "chapter_mode": job_entry.get("chapter_mode"),
        "output_format": output_format,
        "chapters": chapter_outputs,
        "chapter_count": len(chapter_outputs),
        "full_story": full_story_entry,
    }
    save_job_metadata(job_dir, metadata)

    with queue_lock:
        entry = jobs.get(job_id)
        if entry:
            entry["status"] = "completed"
            entry["progress"] = 100
            entry["eta_seconds"] = 0
            entry["chapter_outputs"] = chapter_outputs
            entry["completed_at"] = datetime.now().isoformat()
            if full_story_entry:
                entry["full_story"] = full_story_entry
            entry["output_file"] = (full_story_entry or (chapter_outputs[0] if chapter_outputs else {})).get("file_url")


@app.route('/api/jobs/<job_id>/review/finish', methods=['POST'])
def finish_review_job(job_id: str):
    """Finalize a review-mode job by merging audio and updating metadata."""
    try:
        with queue_lock:
            job_entry = jobs.get(job_id)
            if not job_entry:
                return jsonify({"success": False, "error": "Job not found"}), 404
            _ensure_review_ready(job_entry)
            # Allow recompile for completed jobs with review_mode (chunk review from library)
            if job_entry.get("status") not in ("waiting_review", "completed"):
                return jsonify({"success": False, "error": "Job is not ready for recompile"}), 409
            if _has_active_regen_tasks(job_entry):
                return jsonify({"success": False, "error": "Wait for all chunk regenerations to finish"}), 409

        manifest = _load_review_manifest(job_id, job_entry)
        _merge_review_job(job_id, job_entry, manifest)
        return jsonify({"success": True})
    except FileNotFoundError as exc:
        return jsonify({"success": False, "error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("Failed to finalize review job %s: %s", job_id, exc, exc_info=True)
        return jsonify({"success": False, "error": "Failed to finalize review job"}), 500

    voice_manager = VoiceManager()  # Reload manifest with updated manifest file
    missing = voice_manager.missing_samples()

    return jsonify({
        "success": True,
        "samples": report.get("manifest", {}),
        "generated": report.get("generated", []),
        "skipped_existing": report.get("skipped_existing", []),
        "failed": report.get("failed", []),
        "samples_ready": voice_manager.all_samples_present(),
        "missing_samples": missing,
        "total_unique_voices": voice_manager.total_unique_voice_count(),
        "sample_count": voice_manager.sample_count()
    })


@app.route('/api/preview', methods=['POST'])
def preview_audio():
    """Generate a short preview clip with optional FX settings."""
    data = request.json or {}
    voice = (data.get('voice') or '').strip()
    lang_code = (data.get('lang_code') or 'a').strip()
    text = (data.get('text') or '').strip()
    speed = float(data.get('speed') or 1.0)
    fx_settings = VoiceFXSettings.from_payload(data.get('fx'))
    requested_engine = (data.get('tts_engine') or '').strip().lower()

    if not voice:
        return jsonify({"success": False, "error": "Voice is required for preview."}), 400
    if not text:
        text = "This is a quick Kokoro preview."

    config = load_config()
    # Use requested engine if provided, otherwise fall back to config
    if requested_engine:
        engine_name = _normalize_engine_name(requested_engine)
    else:
        engine_name = _normalize_engine_name(config.get("tts_engine"))
    sample_rate = int(config.get('sample_rate', DEFAULT_SAMPLE_RATE))
    audio_bytes = None

    try:
        logger.info("Preview request: engine=%s, voice=%s, lang_code=%s", engine_name, voice, lang_code)
        engine = get_tts_engine(engine_name, config=config)
        # Check if engine has generate_audio method that returns numpy array
        if hasattr(engine, 'generate_audio'):
            audio = engine.generate_audio(
                text=text,
                voice=voice,
                lang_code=lang_code,
                speed=speed,
                sample_rate=sample_rate,
                fx_settings=fx_settings,
            )
            if hasattr(audio, 'size') and audio.size == 0:
                raise RuntimeError("No audio produced for the requested preview.")
            if hasattr(audio, 'size'):
                # Numpy array - write to buffer
                buffer = io.BytesIO()
                sf.write(buffer, audio, sample_rate, format='wav')
                audio_bytes = buffer.getvalue()
            elif isinstance(audio, str) and os.path.exists(audio):
                # File path returned
                with open(audio, 'rb') as fh:
                    audio_bytes = fh.read()
            elif isinstance(audio, bytes):
                audio_bytes = audio
            else:
                raise RuntimeError("Unexpected audio format from engine.")
    except Exception as exc:
        logger.error("Preview generation failed: %s", exc, exc_info=True)
        return jsonify({"success": False, "error": str(exc)}), 400

    if not audio_bytes:
        return jsonify({"success": False, "error": "Preview failed to generate audio."}), 500

    encoded = base64.b64encode(audio_bytes).decode('ascii')
    return jsonify({
        "success": True,
        "audio_base64": encoded,
        "mime_type": "audio/wav",
    })


@app.route('/api/custom-voices', methods=['GET', 'POST'])
def custom_voices_collection():
    """List or create custom voice blends."""
    if request.method == 'GET':
        entries = list_custom_voice_entries()
        return jsonify({
            "success": True,
            "voices": [_to_public_custom_voice(entry) for entry in entries],
        })

    try:
        payload = _prepare_custom_voice_payload(request.json or {})
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400

    now = datetime.now().isoformat()
    payload["created_at"] = now
    payload["updated_at"] = now
    saved = save_custom_voice(payload)
    clear_cached_custom_voice()
    return jsonify({
        "success": True,
        "voice": _to_public_custom_voice(saved),
    }), 201


@app.route('/api/custom-voices/<voice_id>', methods=['GET', 'PUT', 'DELETE'])
def custom_voice_detail(voice_id):
    """Retrieve, update, or delete a custom voice definition."""
    raw = _get_raw_custom_voice(voice_id)
    if not raw:
        return jsonify({"success": False, "error": "Custom voice not found."}), 404

    if request.method == 'GET':
        return jsonify({"success": True, "voice": _to_public_custom_voice(raw)})

    if request.method == 'DELETE':
        delete_custom_voice(raw["id"])
        clear_cached_custom_voice(f"{CUSTOM_CODE_PREFIX}{raw['id']}")
        return jsonify({"success": True, "deleted": True})

    try:
        payload = _prepare_custom_voice_payload(request.json or {}, existing=raw)
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400

    payload["id"] = raw["id"]
    payload["created_at"] = raw.get("created_at")
    payload["updated_at"] = datetime.now().isoformat()
    updated = replace_custom_voice(payload)
    clear_cached_custom_voice(f"{CUSTOM_CODE_PREFIX}{raw['id']}")
    return jsonify({"success": True, "voice": _to_public_custom_voice(updated)})


@app.route('/api/settings', methods=['GET', 'POST'])
def settings():
    """Get or update settings"""
    if request.method == 'GET':
        config = load_config()
        return jsonify({
            "success": True,
            "settings": config
        })
    else:
        try:
            new_settings = request.json
            config = load_config()
            config.update(new_settings)
            save_config(config)
            
            return jsonify({
                "success": True,
                "message": "Settings updated"
            })
        except Exception as e:
            logger.error(f"Error updating settings: {e}")
            return jsonify({
                "success": False,
                "error": str(e)
            }), 400


@app.route('/api/gemini/models', methods=['POST'])
def list_gemini_models():
    """List available Gemini models using the provided or saved API key."""
    try:
        data = request.json or {}
        api_key = (data.get('api_key') or '').strip()

        if not api_key:
            config = load_config()
            api_key = (config.get('gemini_api_key') or '').strip()

        if not api_key:
            return jsonify({
                "success": False,
                "error": "Gemini API key is required"
            }), 400

        models = GeminiProcessor.list_available_models(api_key)
        return jsonify({
            "success": True,
            "models": models
        })

    except GeminiProcessorError as exc:
        return jsonify({
            "success": False,
            "error": str(exc)
        }), 400
    except Exception as e:  # pragma: no cover - general failure
        logger.error(f"Error listing Gemini models: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": "Failed to list Gemini models"
        }), 500


@app.route('/api/analyze', methods=['POST'])
def analyze_text():
    """Analyze text and return statistics"""
    try:
        with log_request_timing("POST /api/analyze"):
            data = request.json
            text = (data.get('text') or '').strip()

            if not text:
                return jsonify({
                    "success": False,
                    "error": "No text provided"
                }), 400

            config = load_config()
            selected_engine = config.get("tts_engine")
            requested_engine = (data.get('tts_engine') or '').strip()
            if requested_engine:
                normalized = _normalize_engine_name(requested_engine)
                if normalized not in AVAILABLE_ENGINES:
                    return jsonify({
                        "success": False,
                        "error": f"Unsupported TTS engine: {requested_engine}"
                    }), 400
                selected_engine = normalized

            processor = _create_text_processor_for_engine(selected_engine, config["chunk_size"], config)
            stats = processor.get_statistics(text)
            chapter_matches = list(CHAPTER_HEADING_PATTERN.finditer(text))
            if chapter_matches:
                chapters = split_text_into_chapters(text)
                stats['chapter_detection'] = {
                    "detected": True,
                    "count": len(chapters),
                    "titles": [c.get('title') for c in chapters if c.get('title')]
                }
            else:
                stats['chapter_detection'] = {
                    "detected": False,
                    "count": 0,
                    "titles": []
                }

            return jsonify({
                "success": True,
                "statistics": stats
            })

    except Exception as e:
        logger.error(f"Error analyzing text: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/api/gemini/process', methods=['POST'])
def process_text_with_gemini():
    """Send text (optionally chapterized) through Google Gemini."""
    try:
        data = request.json or {}
        text = (data.get('text') or '').strip()
        prefer_chapters = bool(data.get('prefer_chapters', True))
        prompt_override = (data.get('prompt_override') or '').strip()

        if not text:
            return jsonify({
                "success": False,
                "error": "No text provided"
            }), 400

        config = load_config()
        api_key = (config.get('gemini_api_key') or '').strip()
        if not api_key:
            return jsonify({
                "success": False,
                "error": "Gemini API key not configured"
            }), 400

        model_name = config.get('gemini_model') or DEFAULT_GEMINI_MODEL
        prompt_prefix = prompt_override or (config.get('gemini_prompt') or '').strip()

        sections = build_gemini_sections(text, prefer_chapters, config)
        if not sections:
            return jsonify({
                "success": False,
                "error": "Unable to create sections for Gemini processing"
            }), 400

        processor = GeminiProcessor(api_key=api_key, model_name=model_name)
        text_processor = TextProcessor(chunk_size=config.get('chunk_size', 500))
        known_speakers = set(text_processor.extract_speakers(text))

        processed_sections = []
        for idx, section in enumerate(sections, start=1):
            chapter_text = section.get('content', '').strip()
            if not chapter_text:
                continue

            combined_prompt = compose_gemini_prompt(
                section,
                prompt_prefix,
                sorted(known_speakers)
            )
            response_text = processor.generate_text(combined_prompt)
            detected_speakers = text_processor.extract_speakers(response_text)
            for speaker_name in detected_speakers:
                known_speakers.add(speaker_name)
            processed_sections.append({
                "index": idx,
                "title": section.get('title'),
                "source": section.get('source'),
                "output": response_text.strip(),
                "speakers": detected_speakers
            })

        if not processed_sections:
            return jsonify({
                "success": False,
                "error": "Gemini processing produced no output"
            }), 500

        final_text = "\n\n".join(
            section['output']
            for section in processed_sections
            if section.get('output')
        ).strip()

        return jsonify({
            "success": True,
            "result_text": final_text,
            "processed_sections": processed_sections,
            "chapter_mode": any(section.get('source') == 'chapter' for section in sections),
            "section_count": len(processed_sections)
        })

    except GeminiProcessorError as exc:
        return jsonify({
            "success": False,
            "error": str(exc)
        }), 400
    except Exception as e:  # pragma: no cover - general failure
        logger.error(f"Error during Gemini processing: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": "Failed to process text with Gemini"
        }), 500


@app.route('/api/gemini/process-full', methods=['POST'])
def process_full_text_with_gemini():
    """Send the entire text to Gemini using the configured pre-prompt without chunking."""
    try:
        data = request.json or {}
        text = (data.get('text') or '').strip()
        prompt_override = (data.get('prompt_override') or '').strip()

        if not text:
            return jsonify({
                "success": False,
                "error": "No text provided"
            }), 400

        config = load_config()
        api_key = (config.get('gemini_api_key') or '').strip()
        if not api_key:
            return jsonify({
                "success": False,
                "error": "Gemini API key not configured"
            }), 400

        model_name = config.get('gemini_model') or DEFAULT_GEMINI_MODEL
        prompt_prefix = prompt_override or (config.get('gemini_prompt') or '').strip()

        prompt_parts = []
        if prompt_prefix:
            prompt_parts.append(prompt_prefix)
        prompt_parts.append(text)
        combined_prompt = "\n\n".join(part.strip() for part in prompt_parts if part).strip()

        processor = GeminiProcessor(api_key=api_key, model_name=model_name)
        response_text = processor.generate_text(combined_prompt)

        return jsonify({
            "success": True,
            "result_text": response_text.strip()
        })

    except GeminiProcessorError as exc:
        return jsonify({
            "success": False,
            "error": str(exc)
        }), 400
    except Exception as e:  # pragma: no cover - general failure
        logger.error(f"Error during full-text Gemini processing: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": "Failed to process text with Gemini"
        }), 500


@app.route('/api/gemini/sections', methods=['POST'])
def get_gemini_sections():
    """Return the list of Gemini sections for the provided text."""
    try:
        data = request.json or {}
        text = (data.get('text') or '').strip()
        prefer_chapters = bool(data.get('prefer_chapters', True))

        if not text:
            return jsonify({
                "success": False,
                "error": "No text provided"
            }), 400

        config = load_config()
        sections = build_gemini_sections(text, prefer_chapters, config)

        sanitized = []
        for idx, section in enumerate(sections, start=1):
            sanitized.append({
                "id": idx,
                "title": section.get('title'),
                "content": section.get('content'),
                "source": section.get('source')
            })

        return jsonify({
            "success": True,
            "sections": sanitized,
            "count": len(sanitized)
        })

    except Exception as e:  # pragma: no cover - general failure
        logger.error(f"Error building Gemini sections: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": "Failed to build Gemini sections"
        }), 500


@app.route('/api/gemini/process-section', methods=['POST'])
def process_gemini_section():
    """Process a single text section via Gemini."""
    try:
        data = request.json or {}
        content = (data.get('content') or '').strip()
        prompt_override = (data.get('prompt_override') or '').strip()

        if not content:
            return jsonify({
                "success": False,
                "error": "No section content provided"
            }), 400

        config = load_config()
        api_key = (config.get('gemini_api_key') or '').strip()
        if not api_key:
            return jsonify({
                "success": False,
                "error": "Gemini API key not configured"
            }), 400

        model_name = config.get('gemini_model') or DEFAULT_GEMINI_MODEL
        prompt_prefix = prompt_override or (config.get('gemini_prompt') or '').strip()

        raw_known = data.get('known_speakers') or []
        known_speakers = []
        if isinstance(raw_known, list):
            for entry in raw_known:
                if isinstance(entry, str):
                    normalized = entry.strip().lower()
                    if normalized:
                        known_speakers.append(normalized)

        processor = GeminiProcessor(api_key=api_key, model_name=model_name)
        text_processor = TextProcessor()
        prompt = compose_gemini_prompt(
            {"content": content},
            prompt_prefix,
            known_speakers
        )
        response_text = processor.generate_text(prompt)
        detected_speakers = text_processor.extract_speakers(response_text)

        return jsonify({
            "success": True,
            "result_text": response_text.strip(),
            "speakers": detected_speakers
        })

    except GeminiProcessorError as exc:
        return jsonify({
            "success": False,
            "error": str(exc)
        }), 400
    except Exception as e:  # pragma: no cover - general failure
        logger.error(f"Error processing Gemini section: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": "Failed to process section with Gemini"
        }), 500


@app.route('/api/generate', methods=['POST'])
def generate_audio():
    """Add audio generation job to queue"""
    try:
        # Ensure worker thread is running
        start_worker_thread()
        data = request.json or {}
        text = data.get('text', '')
        voice_assignments = data.get('voice_assignments', {})
        logger.info("Received voice_assignments: %s", voice_assignments)
        split_by_chapter = bool(data.get('split_by_chapter', False))
        generate_full_story = bool(data.get('generate_full_story', False)) and split_by_chapter
        requested_format = (data.get('output_format') or '').strip().lower()
        requested_bitrate = data.get('output_bitrate_kbps')
        requested_engine = (data.get('tts_engine') or '').strip().lower()
        engine_options = data.get('engine_options') if isinstance(data.get('engine_options'), dict) else None
        review_mode = bool(data.get('review_mode', False))

        if not text:
            return jsonify({
                "success": False,
                "error": "No text provided"
            }), 400

        allowed_formats = {"mp3", "wav", "ogg"}
        if requested_format and requested_format not in allowed_formats:
            return jsonify({
                "success": False,
                "error": f"Unsupported output format: {requested_format}"
            }), 400

        if requested_bitrate is not None:
            try:
                requested_bitrate = int(requested_bitrate)
            except (TypeError, ValueError):
                return jsonify({
                    "success": False,
                    "error": "Output bitrate must be an integer"
                }), 400
            if requested_bitrate < 32 or requested_bitrate > 512:
                return jsonify({
                    "success": False,
                    "error": "Output bitrate must be between 32 and 512 kbps"
                }), 400

        # Load config
        config = load_config()
        if requested_engine:
            normalized_engine = _normalize_engine_name(requested_engine)
            if normalized_engine not in AVAILABLE_ENGINES:
                return jsonify({
                    "success": False,
                    "error": f"Unsupported TTS engine: {requested_engine}"
                }), 400
            config['tts_engine'] = normalized_engine

        active_engine = _normalize_engine_name(config.get('tts_engine'))
        _apply_engine_option_overrides(config, active_engine, engine_options)
        if requested_format:
            config['output_format'] = requested_format
        if requested_bitrate:
            config['output_bitrate_kbps'] = requested_bitrate
        
        # Create job
        job_id = str(uuid.uuid4())
        estimated_chunks = estimate_total_chunks(
            text,
            split_by_chapter,
            int(config.get('chunk_size', 500)),
            include_full_story=generate_full_story,
            engine_name=active_engine,
            config=config,
        )
        
        merge_options = {
            "output_format": config.get('output_format'),
            "crossfade_duration": float(config.get('crossfade_duration') or 0),
            "intro_silence_ms": int(config.get('intro_silence_ms', 0) or 0),
            "inter_chunk_silence_ms": int(config.get('inter_chunk_silence_ms', 0) or 0),
            "output_bitrate_kbps": int(config.get('output_bitrate_kbps') or 0),
        }

        job_dir = (OUTPUT_DIR / job_id).as_posix()

        with queue_lock:
            jobs[job_id] = {
                "status": "queued",
                "text_preview": text[:200],
                "created_at": datetime.now().isoformat(),
                "review_mode": review_mode,
                "chapter_mode": split_by_chapter,
                "full_story_requested": generate_full_story,
                "job_dir": job_dir,
                "merge_options": merge_options,
                "chunks": [],
                "voice_assignments": voice_assignments,
                "config_snapshot": copy.deepcopy(config),
                "source_text": text,
                "regen_tasks": {},
                "engine": config.get("tts_engine"),
            }
        
        # Create job data
        job_data = {
            "job_id": job_id,
            "text": text,
            "voice_assignments": voice_assignments,
            "config": config,
            "split_by_chapter": split_by_chapter,
            "generate_full_story": generate_full_story,
            "total_chunks": estimated_chunks,
            "review_mode": review_mode,
            "merge_options": merge_options,
        }

        # Add to queue
        job_queue.put(job_data)
        logger.info(f"Job {job_id} added to queue. Queue size: {job_queue.qsize()}")
        
        return jsonify({
            "success": True,
            "job_id": job_id,
            "status": "queued",
            "queue_position": job_queue.qsize()
        })
        
    except Exception as e:
        logger.error(f"Error queueing job: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/api/download/<job_id>', methods=['GET'])
def download_audio(job_id):
    """Download generated audio"""
    try:
        logger.info(f"Download request for job {job_id}")

        # Get output format from config
        config = load_config()
        output_format = config.get('output_format', 'mp3')
        requested_file = request.args.get('file') if request else None

        # Try to find the file - check both mp3 and wav
        file_path = None
        job_dir = OUTPUT_DIR / job_id

        if requested_file:
            safe_relative = Path(requested_file)
            if safe_relative.is_absolute() or ".." in safe_relative.parts:
                return jsonify({
                    "success": False,
                    "error": "Invalid file path"
                }), 400
            candidate_path = job_dir / safe_relative
            if candidate_path.exists():
                file_path = candidate_path
                output_format = candidate_path.suffix.lstrip('.')

        if file_path is None:
            for ext in [output_format, 'mp3', 'wav', 'ogg']:
                test_path = job_dir / f"output.{ext}"
                if test_path.exists():
                    file_path = test_path
                    output_format = ext
                    break

        if not file_path or not file_path.exists():
            logger.error(f"File not found for job {job_id} in {job_dir}")
            return jsonify({
                "success": False,
                "error": f"Audio file not found for job {job_id}"
            }), 404

        logger.info(f"Sending file: {file_path}")
        return send_file(
            file_path,
            as_attachment=True,
            download_name=f"kokoro_story_{job_id}.{output_format}"
        )
        
    except Exception as e:
        logger.error(f"Error downloading file for job {job_id}: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/api/download/<job_id>/zip', methods=['GET'])
def download_audio_bundle(job_id):
    """Download all chapter outputs for a job as a ZIP archive."""
    try:
        job_dir = OUTPUT_DIR / job_id
        if not job_dir.exists():
            return jsonify({
                "success": False,
                "error": "Job directory not found"
            }), 404

        metadata = load_job_metadata(job_dir)
        chapters = (metadata or {}).get("chapters")
        full_story = (metadata or {}).get("full_story")
        if not chapters and not full_story:
            # Fallback to single-file download
            return download_audio(job_id)

        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for chapter in (chapters or []):
                rel_path = chapter.get("relative_path")
                if not rel_path:
                    continue
                file_path = job_dir / Path(rel_path)
                if not file_path.exists():
                    continue
                arc_name = Path(rel_path).as_posix()
                zip_file.write(file_path, arcname=arc_name)

            if full_story:
                rel_path = full_story.get("relative_path")
                if rel_path:
                    file_path = job_dir / Path(rel_path)
                    if file_path.exists():
                        arc_name = Path(rel_path).as_posix()
                        zip_file.write(file_path, arcname=arc_name)

        zip_buffer.seek(0)
        return send_file(
            zip_buffer,
            mimetype='application/zip',
            as_attachment=True,
            download_name=f"kokoro_story_{job_id}.zip"
        )

    except Exception as e:
        logger.error(f"Error generating ZIP for job {job_id}: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


def _build_library_listing():
    """Scan disk and return library metadata list."""
    library_items = []

    if not OUTPUT_DIR.exists():
        return library_items

    for job_dir in OUTPUT_DIR.iterdir():
        if not job_dir.is_dir():
            continue

        job_id = job_dir.name
        metadata = load_job_metadata(job_dir)

        if metadata and metadata.get("chapters"):
            chapters_data = []
            total_size = 0
            created_ts = None
            full_story_entry = None
            for chapter in metadata["chapters"]:
                rel_path = chapter.get("relative_path")
                if not rel_path:
                    continue
                file_path = job_dir / Path(rel_path)
                if not file_path.exists():
                    continue

                stat = file_path.stat()
                created_time = datetime.fromtimestamp(stat.st_ctime)
                created_ts = created_ts or created_time
                total_size += stat.st_size
                chapters_data.append({
                    "index": chapter.get("index"),
                    "title": chapter.get("title"),
                    "output_file": f"/static/audio/{job_id}/{Path(rel_path).as_posix()}",
                    "relative_path": Path(rel_path).as_posix(),
                    "file_size": stat.st_size,
                    "format": file_path.suffix.lstrip('.')
                })

            full_meta = metadata.get("full_story")
            if full_meta and full_meta.get("relative_path"):
                full_path = job_dir / Path(full_meta["relative_path"])
                if full_path.exists():
                    stat = full_path.stat()
                    total_size += stat.st_size
                    full_story_entry = {
                        "title": full_meta.get("title", "Full Story"),
                        "output_file": f"/static/audio/{job_id}/{full_meta['relative_path']}",
                        "relative_path": full_meta['relative_path'],
                        "file_size": stat.st_size,
                        "format": full_path.suffix.lstrip('.')
                    }

            if chapters_data:
                chapters_data.sort(key=lambda c: c.get("index") or 0)
                chunks_meta_path = job_dir / "chunks_metadata.json"
                manifest_path = job_dir / "review_manifest.json"
                has_chunks = chunks_meta_path.exists() or manifest_path.exists()
                # Get engine from chunks_metadata if available
                engine = None
                if chunks_meta_path.exists():
                    try:
                        with chunks_meta_path.open("r", encoding="utf-8") as f:
                            chunks_meta = json.load(f)
                            engine = chunks_meta.get("engine")
                    except Exception:
                        pass
                library_items.append({
                    "job_id": job_id,
                    "output_file": chapters_data[0]["output_file"],
                    "relative_path": chapters_data[0]["relative_path"],
                    "created_at": (created_ts or datetime.now()).isoformat(),
                    "file_size": total_size,
                    "format": metadata.get("output_format", chapters_data[0]["format"]),
                    "chapter_mode": metadata.get("chapter_mode", False),
                    "chapters": chapters_data,
                    "full_story": full_story_entry,
                    "has_chunks": has_chunks,
                    "engine": engine,
                })
            continue

        output_files = list(job_dir.glob("output.*"))
        if output_files:
            output_file = output_files[0]
            stat = output_file.stat()
            created_time = datetime.fromtimestamp(stat.st_ctime)
            # Get engine from chunks_metadata if available
            engine = None
            chunks_meta_path = job_dir / "chunks_metadata.json"
            if chunks_meta_path.exists():
                try:
                    with chunks_meta_path.open("r", encoding="utf-8") as f:
                        chunks_meta = json.load(f)
                        engine = chunks_meta.get("engine")
                except Exception:
                    pass
            library_items.append({
                "job_id": job_id,
                "output_file": f"/static/audio/{job_id}/{output_file.name}",
                "relative_path": output_file.name,
                "created_at": created_time.isoformat(),
                "file_size": stat.st_size,
                "format": output_file.suffix.lstrip('.'),
                "chapter_mode": False,
                "chapters": [{
                    "index": 1,
                    "title": "Full Story",
                    "output_file": f"/static/audio/{job_id}/{output_file.name}",
                    "relative_path": output_file.name,
                    "file_size": stat.st_size,
                    "format": output_file.suffix.lstrip('.')
                }],
                "engine": engine,
            })

    library_items.sort(key=lambda x: x['created_at'], reverse=True)
    return library_items


@app.route('/api/library', methods=['GET'])
def get_library():
    """Get list of all generated audio files"""
    try:
        with log_request_timing("GET /api/library"):
            now = time.time()
            cached_items = library_cache["items"]
            if cached_items is not None and (now - library_cache["timestamp"]) <= LIBRARY_CACHE_TTL:
                return jsonify({
                    "success": True,
                    "items": cached_items,
                    "cached": True
                })

            library_items = _build_library_listing()
            library_cache["items"] = library_items
            library_cache["timestamp"] = now

            return jsonify({
                "success": True,
                "items": library_items,
                "cached": False
            })
        
    except Exception as e:
        logger.error(f"Error getting library: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/api/library/<job_id>/restore-review', methods=['POST'])
def restore_library_item_to_review(job_id):
    """Restore a completed library item back to review mode for chunk editing."""
    try:
        job_dir = OUTPUT_DIR / job_id
        if not job_dir.exists():
            return jsonify({"success": False, "error": "Item not found"}), 404

        manifest_path = job_dir / "review_manifest.json"
        chunks_meta_path = job_dir / "chunks_metadata.json"

        if not manifest_path.exists() and not chunks_meta_path.exists():
            return jsonify({"success": False, "error": "No chunk data available for this item"}), 400

        manifest = {}
        if manifest_path.exists():
            with manifest_path.open("r", encoding="utf-8") as handle:
                manifest = json.load(handle)

        chunks_meta = {}
        if chunks_meta_path.exists():
            with chunks_meta_path.open("r", encoding="utf-8") as handle:
                chunks_meta = json.load(handle)

        config_snapshot = load_config()
        engine_name = chunks_meta.get("engine") or config_snapshot.get("tts_engine", "kokoro")
        # Ensure config_snapshot uses the original job's engine, not the current config
        config_snapshot["tts_engine"] = engine_name
        logger.info(f"Restoring job {job_id} with engine: {engine_name}")

        # Prefer chunks from chunks_metadata.json if available (has text/voice data)
        chunks = chunks_meta.get("chunks") or []

        # If no chunks in metadata, build from manifest
        if not chunks and manifest:
            order_index = 0
            for chapter in manifest.get("chapters", []):
                chapter_index = chapter.get("index", 0)
                chunk_files = chapter.get("chunk_files") or []
                for chunk_idx, rel_path in enumerate(chunk_files):
                    chunk_path = job_dir / rel_path
                    if not chunk_path.exists():
                        continue
                    chunk_id = f"{chapter_index}-{chunk_idx}-{order_index}"
                    chunks.append({
                        "id": chunk_id,
                        "order_index": order_index,
                        "chapter_index": chapter_index,
                        "chunk_index": chunk_idx,
                        "speaker": "default",
                        "text": "",
                        "relative_file": rel_path,
                        "duration_seconds": None,
                    })
                    order_index += 1

        # Verify chunk files exist on disk
        valid_chunks = []
        for chunk in chunks:
            rel_file = chunk.get("relative_file")
            if rel_file and (job_dir / rel_file).exists():
                valid_chunks.append(chunk)

        if not valid_chunks:
            return jsonify({"success": False, "error": "No chunk files found on disk"}), 400

        with queue_lock:
            jobs[job_id] = {
                "job_id": job_id,
                "status": "completed",  # Keep as completed - review happens in library
                "progress": 100,
                "eta_seconds": 0,
                "review_mode": True,
                "review_manifest": manifest_path.name if manifest_path.exists() else None,
                "chapter_mode": manifest.get("chapter_mode", False),
                "full_story_requested": manifest.get("full_story_requested", False),
                "job_dir": str(job_dir),
                "config_snapshot": config_snapshot,
                "chunks": valid_chunks,
                "regen_tasks": {},
                "engine": engine_name,
                "restored_at": datetime.now().isoformat(),
            }

        invalidate_library_cache()
        return jsonify({"success": True, "job_id": job_id, "chunk_count": len(valid_chunks)})

    except Exception as exc:
        logger.error("Failed to restore library item %s to review: %s", job_id, exc, exc_info=True)
        return jsonify({"success": False, "error": "Failed to restore item to review mode"}), 500


@app.route('/api/library/<job_id>/chunks', methods=['GET'])
def get_library_item_chunks(job_id):
    """Get chunk metadata for a library item."""
    try:
        job_dir = OUTPUT_DIR / job_id
        if not job_dir.exists():
            return jsonify({"success": False, "error": "Item not found"}), 404

        chunks_meta_path = job_dir / "chunks_metadata.json"
        if not chunks_meta_path.exists():
            return jsonify({"success": False, "error": "No chunk data available for this item"}), 400

        with chunks_meta_path.open("r", encoding="utf-8") as handle:
            chunks_meta = json.load(handle)

        chunks = chunks_meta.get("chunks") or []
        for chunk in chunks:
            rel_file = chunk.get("relative_file")
            if rel_file:
                chunk["file_url"] = f"/static/audio/{job_id}/{rel_file}"

        # Load chapter information from review_manifest if available
        chapters = []
        manifest_path = job_dir / "review_manifest.json"
        if manifest_path.exists():
            with manifest_path.open("r", encoding="utf-8") as handle:
                manifest = json.load(handle)
                chapter_mode = manifest.get("chapter_mode", False)
                if chapter_mode:
                    for ch in manifest.get("chapters", []):
                        chapters.append({
                            "index": ch.get("index"),
                            "title": ch.get("title"),
                            "output_filename": ch.get("output_filename"),
                        })

        return jsonify({
            "success": True,
            "job_id": job_id,
            "engine": chunks_meta.get("engine", "kokoro"),
            "created_at": chunks_meta.get("created_at"),
            "updated_at": chunks_meta.get("updated_at"),
            "chunks": chunks,
            "chapters": chapters,
            "has_chapters": len(chapters) > 1,
        })

    except Exception as exc:
        logger.error("Failed to get chunks for library item %s: %s", job_id, exc, exc_info=True)
        return jsonify({"success": False, "error": "Failed to load chunk data"}), 500


@app.route('/api/library/<job_id>', methods=['DELETE'])
def delete_library_item(job_id):
    """Delete a library item"""
    try:
        job_dir = OUTPUT_DIR / job_id
        
        if not job_dir.exists():
            return jsonify({
                "success": False,
                "error": "Item not found"
            }), 404
        
        # Delete directory and all contents (handle Windows read-only files)
        import shutil
        shutil.rmtree(job_dir, onerror=handle_remove_readonly)
        
        # Remove from jobs dict if present
        if job_id in jobs:
            del jobs[job_id]
        invalidate_library_cache()
        
        return jsonify({
            "success": True
        })
        
    except Exception as e:
        logger.error(f"Error deleting library item: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/api/library/clear', methods=['POST'])
def clear_library():
    """Clear all library items"""
    try:
        if OUTPUT_DIR.exists():
            import shutil
            for job_dir in OUTPUT_DIR.iterdir():
                if job_dir.is_dir():
                    shutil.rmtree(job_dir, onerror=handle_remove_readonly)
        
        # Clear jobs dict
        jobs.clear()
        
        return jsonify({
            "success": True
        })
        
    except Exception as e:
        logger.error(f"Error clearing library: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/api/cancel/<job_id>', methods=['POST'])
def cancel_job(job_id):
    """Cancel a job"""
    try:
        with queue_lock:
            if job_id not in jobs:
                return jsonify({
                    "success": False,
                    "error": "Job not found"
                }), 404
            
            # Set cancellation flag
            cancel_flags[job_id] = True
            
            # Update job status
            jobs[job_id]["status"] = "cancelled"
            jobs[job_id]["progress"] = 0
            jobs[job_id]["cancelled_at"] = datetime.now().isoformat()
        
        logger.info(f"Job {job_id} marked for cancellation")
        
        return jsonify({
            "success": True,
            "message": "Job cancelled"
        })
        
    except Exception as e:
        logger.error(f"Error cancelling job: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/api/queue', methods=['GET'])
def get_queue():
    """Get current job queue and all jobs"""
    try:
        with log_request_timing("GET /api/queue"):
            with queue_lock:
                all_jobs = []
                for job_id, job_info in jobs.items():
                    all_jobs.append({
                        "job_id": job_id,
                        "status": job_info.get("status", "unknown"),
                        "progress": job_info.get("progress", 0),
                        "created_at": job_info.get("created_at", ""),
                        "text_preview": job_info.get("text_preview", ""),
                        "output_file": job_info.get("output_file", ""),
                        "error": job_info.get("error", ""),
                        "total_chunks": job_info.get("total_chunks"),
                        "processed_chunks": job_info.get("processed_chunks", 0),
                        "eta_seconds": job_info.get("eta_seconds"),
                        "chapter_mode": job_info.get("chapter_mode", False),
                        "chapter_count": job_info.get("chapter_count"),
                        "full_story_requested": job_info.get("full_story_requested", False),
                        "review_mode": job_info.get("review_mode", False),
                        "review_has_active_regen": job_info.get("review_mode", False) and _has_active_regen_tasks(job_info),
                    })
                
                all_jobs.sort(key=lambda x: x['created_at'], reverse=True)
            
            return jsonify({
                "success": True,
                "jobs": all_jobs,
                "current_job": current_job_id,
                "queue_size": job_queue.qsize()
            })
        
    except Exception as e:
        logger.error(f"Error getting queue: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/api/extract-document', methods=['POST'])
def extract_document_text():
    """Extract text content from an uploaded document file."""
    if 'file' not in request.files:
        return jsonify({"success": False, "error": "No file provided"}), 400
    
    file = request.files['file']
    if not file.filename:
        return jsonify({"success": False, "error": "No file selected"}), 400
    
    filename = secure_filename(file.filename)
    
    try:
        file_content = file.read()
        text, format_name = extract_text_from_file(filename, file_content)
        
        if not text.strip():
            return jsonify({
                "success": False,
                "error": f"No text content found in {format_name} file"
            }), 400
        
        return jsonify({
            "success": True,
            "text": text,
            "format": format_name,
            "filename": filename,
            "char_count": len(text),
            "word_count": len(text.split()),
        })
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except ImportError as e:
        return jsonify({
            "success": False,
            "error": f"Missing library: {str(e)}. Please install required dependencies."
        }), 500
    except Exception as e:
        logger.error("Document extraction failed: %s", e, exc_info=True)
        return jsonify({"success": False, "error": f"Failed to extract text: {str(e)}"}), 500


@app.route('/api/supported-formats', methods=['GET'])
def list_supported_formats():
    """Return list of supported document formats for upload."""
    return jsonify({
        "success": True,
        "formats": get_supported_formats()
    })


@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    config = load_config()
    
    # Get VRAM info if available
    vram_info = {}
    try:
        import torch
        if torch.cuda.is_available():
            vram_info = {
                "allocated_mb": round(torch.cuda.memory_allocated(0) / 1024**2, 1),
                "reserved_mb": round(torch.cuda.memory_reserved(0) / 1024**2, 1),
                "max_allocated_mb": round(torch.cuda.max_memory_allocated(0) / 1024**2, 1),
            }
    except Exception:
        pass
    
    return jsonify({
        "success": True,
        "tts_engine": config.get('tts_engine', 'kokoro'),
        "kokoro_available": KOKORO_AVAILABLE,
        "cuda_available": False if not KOKORO_AVAILABLE else __import__('torch').cuda.is_available(),
        "vram": vram_info,
        "loaded_engines": list(tts_engine_instances.keys()),
    })


@app.route('/api/cleanup-vram', methods=['POST'])
def cleanup_vram():
    """Manually trigger VRAM cleanup for all loaded engines."""
    import gc
    
    cleaned_engines = []
    errors = []
    
    with tts_engine_lock:
        for engine_name, engine in list(tts_engine_instances.items()):
            try:
                engine.cleanup()
                cleaned_engines.append(engine_name)
            except Exception as e:
                errors.append(f"{engine_name}: {str(e)}")
        
        # Clear the engine cache to force reload on next use
        tts_engine_instances.clear()
        engine_config_signatures.clear()
    
    # Additional garbage collection
    gc.collect()
    
    # Get VRAM info after cleanup
    vram_after = {}
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.reset_peak_memory_stats()
            vram_after = {
                "allocated_mb": round(torch.cuda.memory_allocated(0) / 1024**2, 1),
                "reserved_mb": round(torch.cuda.memory_reserved(0) / 1024**2, 1),
            }
    except Exception:
        pass
    
    return jsonify({
        "success": len(errors) == 0,
        "cleaned_engines": cleaned_engines,
        "errors": errors,
        "vram_after": vram_after,
    })


def _cleanup_orphaned_regen_folders():
    """Clean up leftover chunk_regen_* temp folders from previous sessions."""
    cleaned = 0
    
    # Clean up old-style folders in job directories (legacy)
    try:
        for job_dir in OUTPUT_DIR.iterdir():
            if not job_dir.is_dir():
                continue
            for item in job_dir.iterdir():
                if item.is_dir() and item.name.startswith("chunk_regen_"):
                    try:
                        shutil.rmtree(item)
                        cleaned += 1
                    except Exception as e:
                        logger.warning("Failed to clean up orphaned temp dir %s: %s", item, e)
    except Exception as e:
        logger.warning("Error scanning for orphaned regen folders in OUTPUT_DIR: %s", e)
    
    # Clean up new-style folders in system temp directory
    try:
        temp_base = Path(tempfile.gettempdir())
        for item in temp_base.iterdir():
            if item.is_dir() and item.name.startswith("tts_chunk_regen_"):
                try:
                    shutil.rmtree(item)
                    cleaned += 1
                except Exception as e:
                    logger.warning("Failed to clean up orphaned temp dir %s: %s", item, e)
    except Exception as e:
        logger.warning("Error scanning for orphaned regen folders in temp dir: %s", e)
    
    if cleaned:
        logger.info("Cleaned up %d orphaned chunk regen temp folders", cleaned)


if __name__ == '__main__':
    logger.info("Starting TTS-Story server")
    _cleanup_orphaned_chatterbox_voices()
    _cleanup_orphaned_regen_folders()
    app.run(host='0.0.0.0', port=5000, debug=True)
