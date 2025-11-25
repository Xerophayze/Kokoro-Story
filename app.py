"""
Kokoro-Story - Web-based TTS application
"""
from flask import Flask, render_template, request, jsonify, send_file
from flask_cors import CORS
import json
import logging
import os
import re
import uuid
from pathlib import Path
from datetime import datetime
import threading
import queue
import time
import stat

from src.text_processor import TextProcessor
from src.voice_manager import VoiceManager
from src.voice_sample_generator import generate_voice_samples
from src.tts_engine import TTSEngine, KOKORO_AVAILABLE
from src.replicate_api import ReplicateAPI
from src.audio_merger import AudioMerger

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
CHAPTER_HEADING_PATTERN = re.compile(r'^\s*(chapter(?:\s+[^\n\r]*)?)', re.IGNORECASE | re.MULTILINE)

# Global state
jobs = {}  # Track all jobs (queued, processing, completed)
job_queue = queue.Queue()  # Thread-safe job queue
current_job_id = None  # Currently processing job
cancel_flags = {}  # Cancellation flags for jobs
queue_lock = threading.Lock()  # Lock for thread-safe operations
worker_thread = None  # Background worker thread


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


def save_job_metadata(job_dir: Path, metadata: dict):
    """Persist metadata for generated outputs."""
    metadata_path = job_dir / JOB_METADATA_FILENAME
    with open(metadata_path, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=2)


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
        
        # Determine chapter sections when requested
        chapter_sections = [{"title": "Full Story", "content": text}]
        if split_by_chapter:
            detected = split_text_into_chapters(text)
            if detected:
                chapter_sections = detected
            else:
                logger.info("Chapter splitting enabled but no chapter headings detected; falling back to single output")
                split_by_chapter = False
        
        mode = config['mode']
        output_format = config['output_format']
        merger = AudioMerger(
            crossfade_ms=int(config['crossfade_duration'] * 1000)
        )
        chapter_outputs = []
        
        # Prepare TTS engine/API
        engine = None
        api = None
        if mode == "local":
            if not KOKORO_AVAILABLE:
                raise Exception("Kokoro not installed. Use Replicate API or install kokoro.")
            engine = TTSEngine()
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
                    speed=config['speed']
                )
            return api.generate_batch(
                segments=segments,
                voice_config=voice_assignments,
                output_dir=str(output_dir),
                speed=config['speed']
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

                    slug = slugify_filename(chapter['title'], f"chapter-{idx:02d}")
                    output_filename = f"{slug}.{output_format}"
                    output_path = chapter_dir / output_filename
                    merger.merge_wav_files(
                        input_files=audio_files,
                        output_path=str(output_path),
                        format=output_format
                    )

                    # Cleanup empty chunk directory
                    if chunk_dir.exists():
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
        finally:
            if engine:
                engine.cleanup()

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
            "chapters": chapter_outputs
        }
        save_job_metadata(job_dir, metadata)
        
        # Update job as completed
        with queue_lock:
            jobs[job_id]['status'] = 'completed'
            jobs[job_id]['progress'] = 100
            jobs[job_id]['output_file'] = chapter_outputs[0]['file_url']
            jobs[job_id]['chapter_outputs'] = chapter_outputs
            jobs[job_id]['chapter_mode'] = split_by_chapter
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
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    return {
        "mode": "local",
        "replicate_api_key": "",
        "chunk_size": 500,
        "sample_rate": 24000,
        "speed": 1.0,
        "output_format": "mp3",
        "crossfade_duration": 0.1
    }


def save_config(config):
    """Save configuration to file"""
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)


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


@app.route('/api/analyze', methods=['POST'])
def analyze_text():
    """Analyze text and return statistics"""
    try:
        data = request.json
        text = data.get('text', '')
        
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

        if not text:
            return jsonify({
                "success": False,
                "error": "No text provided"
            }), 400
        
        # Load config
        config = load_config()
        
        # Create job
        job_id = str(uuid.uuid4())
        
        with queue_lock:
            jobs[job_id] = {
                "status": "queued",
                "progress": 0,
                "created_at": datetime.now().isoformat(),
                "text_preview": text[:100] + "..." if len(text) > 100 else text,
                "chapter_mode": split_by_chapter
            }
        
        # Create job data
        job_data = {
            "job_id": job_id,
            "text": text,
            "voice_assignments": voice_assignments,
            "config": config,
            "split_by_chapter": split_by_chapter
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


@app.route('/api/library', methods=['GET'])
def get_library():
    """Get list of all generated audio files"""
    try:
        library_items = []

        if OUTPUT_DIR.exists():
            for job_dir in OUTPUT_DIR.iterdir():
                if not job_dir.is_dir():
                    continue

                job_id = job_dir.name
                metadata = load_job_metadata(job_dir)

                if metadata and metadata.get("chapters"):
                    chapters_data = []
                    total_size = 0
                    created_ts = None
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
                            "chapters": chapters_data
                        })
                    continue

                # Fallback for legacy jobs without metadata
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

        # Sort by creation time, newest first
        library_items.sort(key=lambda x: x['created_at'], reverse=True)

        return jsonify({
            "success": True,
            "items": library_items
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
        
        # Delete directory and all contents
        import shutil
        shutil.rmtree(job_dir)
        
        # Remove from jobs dict if present
        if job_id in jobs:
            del jobs[job_id]
        
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
        with queue_lock:
            # Get all jobs sorted by creation time
            all_jobs = []
            for job_id, job_info in jobs.items():
                all_jobs.append({
                    "job_id": job_id,
                    "status": job_info.get("status", "unknown"),
                    "progress": job_info.get("progress", 0),
                    "created_at": job_info.get("created_at", ""),
                    "text_preview": job_info.get("text_preview", ""),
                    "output_file": job_info.get("output_file", ""),
                    "error": job_info.get("error", "")
                })
            
            # Sort by creation time (newest first)
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
