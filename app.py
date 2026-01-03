"""
Kokoro-Story - Web-based TTS application
"""
from flask import Flask, render_template, request, jsonify, send_file
from flask_cors import CORS
import base64
import io
import json
import logging
import os
import queue
import re
import soundfile as sf
import stat
import tempfile
import threading
import time
import uuid
import zipfile
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Dict, Optional

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
from src.gemini_processor import GeminiProcessor, GeminiProcessorError
from src.replicate_api import ReplicateAPI
from src.text_processor import TextProcessor
from src.tts_engine import TTSEngine, KOKORO_AVAILABLE, DEFAULT_SAMPLE_RATE
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
JOB_METADATA_FILENAME = "metadata.json"
DEFAULT_GEMINI_MODEL = "gemini-1.5-flash"
LIBRARY_CACHE_TTL = 5  # seconds
DEFAULT_CONFIG = {
    "mode": "local",
    "replicate_api_key": "",
    "chunk_size": 500,
    "sample_rate": 24000,
    "speed": 1.0,
    "output_format": "mp3",
    "crossfade_duration": 0.1,
    "intro_silence_ms": 0,
    "inter_chunk_silence_ms": 0,
    "gemini_api_key": "",
    "gemini_model": DEFAULT_GEMINI_MODEL,
    "gemini_prompt": ""
}
# Allow headings like [narrator]\nChapter 1 or Chapter 1 without tags.
CHAPTER_HEADING_PATTERN = re.compile(
    r'^\s*(?:\[[^\]]+\]\s*)*(chapter(?:\s+[^\n\r]*)?)',
    re.IGNORECASE | re.MULTILINE
)

# Global state
jobs = {}  # Track all jobs (queued, processing, completed)
job_queue = queue.Queue()  # Thread-safe job queue
current_job_id = None  # Currently processing job
cancel_flags = {}  # Cancellation flags for jobs
queue_lock = threading.Lock()  # Lock for thread-safe operations
worker_thread = None  # Background worker thread
tts_engine_instance = None  # Cached TTS engine
tts_engine_lock = threading.Lock()
library_cache = {
    "items": None,
    "timestamp": 0.0,
}


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


def get_tts_engine():
    """Return a shared TTSEngine instance to avoid repeatedly re-loading Kokoro models."""
    if not KOKORO_AVAILABLE:
        raise ImportError("Kokoro is not installed. Run setup to enable local mode.")

    global tts_engine_instance
    with tts_engine_lock:
        if tts_engine_instance is None:
            tts_engine_instance = TTSEngine()
        return tts_engine_instance


def clear_cached_custom_voice(voice_code: str | None = None) -> int:
    """Ensure cached blended tensors stay in sync after CRUD operations."""
    global tts_engine_instance
    if tts_engine_instance is None:
        return 0
    return tts_engine_instance.clear_custom_voice_cache(voice_code)


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
            chapters.append({"title": "Prologue", "content": pre_content})

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
        processor = TextProcessor(chunk_size=config.get('chunk_size', 500))
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


def estimate_total_chunks(
    text: str,
    split_by_chapter: bool,
    chunk_size: int,
    include_full_story: bool = False
) -> int:
    """Estimate total chunk count for a job to power progress indicators."""
    processor = TextProcessor(chunk_size=chunk_size)
    sections = [{"content": text}]
    if split_by_chapter:
        detected = split_text_into_chapters(text)
        if detected:
            sections = detected

    merge_steps = len(sections) if sections else 1
    if include_full_story and split_by_chapter and sections:
        merge_steps += 1  # additional merge for full-length audiobook
    total_chunks = 0
    for section in sections:
        section_text = (section.get("content") or "").strip()
        if not section_text:
            continue
        segments = processor.process_text(section_text)
        for segment in segments:
            total_chunks += len(segment.get("chunks", []))

    return max(total_chunks + merge_steps, 1)


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
            logger.info(f"Job {job_id} cancelled during processing")
            with queue_lock:
                jobs[job_id]['status'] = 'cancelled'
            return
        
        processor = TextProcessor(chunk_size=config['chunk_size'])
        job_dir = OUTPUT_DIR / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        total_chunks = max(1, job_data.get('total_chunks') or jobs.get(job_id, {}).get('total_chunks') or 1)
        processed_chunks = 0
        job_start_time = datetime.now()

        def update_progress(increment: int = 1):
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
        
        mode = config['mode']
        output_format = config['output_format']
        crossfade_seconds = float(config.get('crossfade_duration', 0) or 0)
        merger = AudioMerger(
            crossfade_ms=int(max(0.0, crossfade_seconds) * 1000),
            intro_silence_ms=int(max(0, config.get('intro_silence_ms', 0) or 0)),
            inter_chunk_silence_ms=int(max(0, config.get('inter_chunk_silence_ms', 0) or 0))
        )
        chapter_outputs = []
        full_story_entry = None
        all_full_story_chunks = [] if (split_by_chapter and generate_full_story) else None
        chunk_dirs_to_cleanup = []
        
        # Prepare TTS engine/API
        engine = None
        api = None
        if mode == "local":
            if not KOKORO_AVAILABLE:
                raise Exception("Kokoro not installed. Use Replicate API or install kokoro.")
            engine = get_tts_engine()
        else:
            api_key = config.get('replicate_api_key', '')
            if not api_key:
                raise Exception("Replicate API key not configured")
            api = ReplicateAPI(api_key)

        def generate_chunks(section_text, output_dir: Path):
            segments = processor.process_text(section_text)
            if not segments:
                return []
            output_dir.mkdir(parents=True, exist_ok=True)
            if mode == "local":
                return engine.generate_batch(
                    segments=segments,
                    voice_config=voice_assignments,
                    output_dir=str(output_dir),
                    speed=config['speed'],
                    progress_cb=update_progress
                )
            return api.generate_batch(
                segments=segments,
                voice_config=voice_assignments,
                output_dir=str(output_dir),
                speed=config['speed'],
                progress_cb=update_progress
            )

        try:
            if split_by_chapter:
                for idx, chapter in enumerate(chapter_sections, start=1):
                    if cancel_flags.get(job_id, False):
                        logger.info(f"Job {job_id} cancelled before finishing chapter {idx}")
                        with queue_lock:
                            jobs[job_id]['status'] = 'cancelled'
                        return

                    chapter_dir = job_dir / f"chapter_{idx:02d}"
                    chunk_dir = chapter_dir / "chunks"
                    audio_files = generate_chunks(chapter["content"], chunk_dir)
                    if not audio_files:
                        logger.warning(f"Chapter {idx} had no audio chunks; skipping")
                        continue

                    if all_full_story_chunks is not None:
                        all_full_story_chunks.extend(audio_files)
                        chunk_dirs_to_cleanup.append(chunk_dir)

                    slug = slugify_filename(chapter['title'], f"chapter-{idx:02d}")
                    output_filename = f"{slug}.{output_format}"
                    output_path = chapter_dir / output_filename
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
                audio_files = generate_chunks(text, chunk_dir)
                if not audio_files:
                    raise ValueError("Unable to generate audio chunks")
                output_file = job_dir / f"output.{output_format}"
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

        if all_full_story_chunks:
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
            logger.info(f"Job {job_id} cancelled before completion")
            with queue_lock:
                jobs[job_id]['status'] = 'cancelled'
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
        
    except Exception as e:
        logger.error(f"Error in job {job_id}: {e}", exc_info=True)
        with queue_lock:
            jobs[job_id]['status'] = 'failed'
            jobs[job_id]['error'] = str(e)
        raise


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

    if not voice:
        return jsonify({"success": False, "error": "Voice is required for preview."}), 400
    if not text:
        text = "This is a quick Kokoro preview."

    config = load_config()
    mode = config.get('mode', 'local')
    sample_rate = int(config.get('sample_rate', DEFAULT_SAMPLE_RATE))
    audio_bytes = None

    try:
        if mode == 'local':
            if not KOKORO_AVAILABLE:
                raise RuntimeError("Local Kokoro is unavailable. Switch to Replicate mode for previews.")
            engine = get_tts_engine()
            audio = engine.generate_audio(
                text=text,
                voice=voice,
                lang_code=lang_code,
                speed=speed,
                sample_rate=sample_rate,
                fx_settings=fx_settings,
            )
            if audio.size == 0:
                raise RuntimeError("No audio produced for the requested preview.")
            buffer = io.BytesIO()
            sf.write(buffer, audio, sample_rate, format='wav')
            audio_bytes = buffer.getvalue()
        else:
            api_key = (config.get('replicate_api_key') or '').strip()
            if not api_key:
                raise RuntimeError("Replicate API key is required for preview in replicate mode.")
            api = ReplicateAPI(api_key)
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
                tmp_path = tmp.name
            try:
                api.generate_audio(
                    text=text,
                    voice=voice,
                    speed=speed,
                    output_path=tmp_path,
                    fx_settings=fx_settings,
                )
                with open(tmp_path, 'rb') as fh:
                    audio_bytes = fh.read()
            finally:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
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
            processor = TextProcessor(chunk_size=config['chunk_size'])
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
        prompt_prefix = (config.get('gemini_prompt') or '').strip()

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
        prompt_prefix = (config.get('gemini_prompt') or '').strip()

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
        prompt_prefix = (config.get('gemini_prompt') or '').strip()

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
        data = request.json
        text = data.get('text', '')
        voice_assignments = data.get('voice_assignments', {})
        split_by_chapter = bool(data.get('split_by_chapter', False))
        generate_full_story = bool(data.get('generate_full_story', False)) and split_by_chapter

        if not text:
            return jsonify({
                "success": False,
                "error": "No text provided"
            }), 400
        
        # Load config
        config = load_config()
        
        # Create job
        job_id = str(uuid.uuid4())
        estimated_chunks = estimate_total_chunks(
            text,
            split_by_chapter,
            int(config.get('chunk_size', 500)),
            include_full_story=generate_full_story
        )
        
        with queue_lock:
            jobs[job_id] = {
                "status": "queued",
                "progress": 0,
                "created_at": datetime.now().isoformat(),
                "text_preview": text[:100] + "..." if len(text) > 100 else text,
                "chapter_mode": split_by_chapter,
                "total_chunks": estimated_chunks,
                "processed_chunks": 0,
                "eta_seconds": None,
                "chapter_count": None,
                "full_story_requested": generate_full_story
            }
        
        # Create job data
        job_data = {
            "job_id": job_id,
            "text": text,
            "voice_assignments": voice_assignments,
            "config": config,
            "split_by_chapter": split_by_chapter,
            "total_chunks": estimated_chunks,
            "generate_full_story": generate_full_story
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
                library_items.append({
                    "job_id": job_id,
                    "output_file": chapters_data[0]["output_file"],
                    "relative_path": chapters_data[0]["relative_path"],
                    "created_at": (created_ts or datetime.now()).isoformat(),
                    "file_size": total_size,
                    "format": metadata.get("output_format", chapters_data[0]["format"]),
                    "chapter_mode": metadata.get("chapter_mode", False),
                    "chapters": chapters_data,
                    "full_story": full_story_entry
                })
            continue

        output_files = list(job_dir.glob("output.*"))
        if output_files:
            output_file = output_files[0]
            stat = output_file.stat()
            created_time = datetime.fromtimestamp(stat.st_ctime)
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
                }]
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
                        "full_story_requested": job_info.get("full_story_requested", False)
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


@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    config = load_config()
    
    return jsonify({
        "success": True,
        "mode": config['mode'],
        "kokoro_available": KOKORO_AVAILABLE,
        "cuda_available": False if not KOKORO_AVAILABLE else __import__('torch').cuda.is_available()
    })


if __name__ == '__main__':
    logger.info("Starting Kokoro-Story server")
    app.run(host='0.0.0.0', port=5000, debug=True)
