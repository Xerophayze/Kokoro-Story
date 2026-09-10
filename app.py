"""
TTS-Story - Web-based TTS application
"""
from flask import Flask, render_template, request, jsonify, send_file, Response, abort
from flask_cors import CORS
import base64
import asyncio
import webbrowser
import copy
import inspect
import hashlib
import hmac
import io
import json
import concurrent.futures
import gc
import logging
import math
import mimetypes
import os
import queue
import re
import shutil
import sqlite3
import stat
import subprocess
import sys
import tempfile
import threading
import time
import zipfile
import uuid
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timedelta
from functools import lru_cache, wraps
from pathlib import Path
from time import perf_counter
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo
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
from src.help_center import create_help_blueprint
from src.library_metadata import (
    can_reuse_active_review_job,
    get_custom_chapter_title,
    infer_collection_title_from_chunks,
    merge_generated_library_metadata,
)
from src.library_cleanup import remove_directory_with_retries
from src.json_storage import write_json_atomic
from src.pause_markers import (
    pause_seconds_for_text,
    sanitize_display_title,
    split_text_and_pause_markers,
    write_silence_wav,
)
from src.atlas_cloud_processor import (
    AtlasCloudProcessor,
    AtlasCloudProcessorError,
    DEFAULT_ATLAS_CLOUD_BASE_URL,
    DEFAULT_ATLAS_CLOUD_MODEL,
)
from src.openrouter_processor import (
    OpenRouterProcessor,
    OpenRouterProcessorError,
    DEFAULT_OPENROUTER_BASE_URL,
    DEFAULT_OPENROUTER_MODEL,
)
from src.local_llm_processor import (
    DEFAULT_LOCAL_LLM_BASE_URLS,
    LocalLLMProcessor,
    LocalLLMProcessorError,
    LLM_PROVIDER_LMSTUDIO,
    LLM_PROVIDER_OLLAMA,
)
from src.replicate_api import ReplicateAPI
from src.system_tools import find_system_tool
from src.text_processor import TextProcessor
from src.engines import TtsEngineBase
from src.engines.chatterbox_turbo_local_engine import (
    CHATTERBOX_TURBO_AVAILABLE,
    CHATTERBOX_TURBO_UNAVAILABLE_REASON,
)
from src.engines.voxcpm_local_engine import VOXCPM_AVAILABLE
from src.engines.qwen3_custom_voice_engine import QWEN3_AVAILABLE
from src.engines.qwen3_voice_clone_engine import QWEN3_AVAILABLE as QWEN3_CLONE_AVAILABLE
from src.engines.omnivoice_clone_engine import (
    omnivoice_available,
    omnivoice_unavailable_reason,
)
from src.engines.pocket_tts_engine import POCKET_TTS_AVAILABLE
from src.engines.kitten_tts_engine import (
    KITTEN_TTS_AVAILABLE,
    KITTEN_TTS_BUILTIN_VOICES,
    KITTEN_TTS_DEFAULT_MODEL,
)
from src.engines.index_tts_engine import (
    INDEX_TTS_AVAILABLE,
    INDEX_TTS_UNAVAILABLE_REASON,
    INDEX_TTS_SAMPLE_RATE,
)
from src.engines.dots_tts_engine import (
    DOTS_TTS_AVAILABLE,
    DOTS_TTS_UNAVAILABLE_REASON,
    DotsTTSEngine,
)
from src.engines.chatterbox_turbo_replicate_engine import (
    DEFAULT_CHATTERBOX_TURBO_REPLICATE_MODEL,
    DEFAULT_CHATTERBOX_TURBO_REPLICATE_VOICE,
)
from src.engines.azure_speech_engine import (
    AzureSpeechEngine,
    AzureSpeechError,
    DEFAULT_AZURE_SPEECH_OUTPUT_FORMAT,
    DEFAULT_AZURE_SPEECH_REQUESTS_PER_MINUTE,
    DEFAULT_AZURE_SPEECH_VOICE,
)
from src.engines.edge_tts_engine import (
    EDGE_TTS_AVAILABLE,
    EDGE_TTS_UNAVAILABLE_REASON,
    EdgeTTSEngine,
    EdgeTTSError,
    DEFAULT_EDGE_TTS_VOICE,
)
from src.engines.elevenlabs_engine import (
    ElevenLabsEngine,
    ElevenLabsError,
    DEFAULT_ELEVENLABS_BASE_URL,
    DEFAULT_ELEVENLABS_MODEL,
    DEFAULT_ELEVENLABS_OUTPUT_FORMAT,
    DEFAULT_ELEVENLABS_VOICE,
)
from src.engines.openai_tts_engine import (
    OpenAITTSEngine,
    OpenAITTSError,
    DEFAULT_OPENAI_TTS_BASE_URL,
    DEFAULT_OPENAI_TTS_MODEL,
    DEFAULT_OPENAI_TTS_VOICE,
    OPENAI_TTS_VOICES,
)
from src.engines.localai_tts_engine import DEFAULT_LOCALAI_TTS_BASE_URL, LocalAITTSEngine
from src.engines.breeze_api_engine import BreezeAPIEngine, BreezeAPIError
from src.breeze_productions import BreezeProductions, ProductionError
from src.localai_tts_client import LocalAITTSDiscoveryError, discover_localai_tts_catalog
from src.localai_voice_profiles import (
    LocalAIVoiceProfileManager,
    build_tts_story_voice_reference,
)
from src.voice_transcription import VoiceTranscriptionError, VoiceTranscriptGenerator
from src.tts_engine import (
    TTSEngine,
    KOKORO_AVAILABLE,
    DEFAULT_SAMPLE_RATE,
    get_engine,
    AVAILABLE_ENGINES,
)
from src.engines.isolated_proxy import isolated_engine_available
from src.voice_manager import VoiceManager
from src.voice_sample_generator import generate_voice_samples
# Keep the Gemini wrapper after engine imports. Its SDK is also lazy-loaded in
# GeminiProcessor so native gRPC/protobuf libraries do not precede PyTorch on Windows.
from src.gemini_processor import GeminiProcessor, GeminiProcessorError

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Suppress werkzeug INFO logs (polling requests to /api/queue)
logging.getLogger('werkzeug').setLevel(logging.WARNING)

# Initialize Flask app
app = Flask(__name__)
CORS(app)
app.register_blueprint(create_help_blueprint())

# Configuration
CONFIG_FILE = "config.json"
# Use Flask's static folder so paths stay correct even when the server is launched
# from a different working directory.
OUTPUT_DIR = Path(app.static_folder) / "audio"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
JOBS_DATA_DIR = Path("data/jobs")
JOBS_ARCHIVE_DIR = JOBS_DATA_DIR / "archive"
JOBS_DB_PATH = JOBS_DATA_DIR / "jobs.db"
JOBS_DATA_DIR.mkdir(parents=True, exist_ok=True)
JOBS_ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
VOICE_PROMPT_DIR = Path("data/voice_prompts")
BREEZE_PRODUCTIONS = BreezeProductions(Path(__file__).resolve().parent / 'data/breeze_productions', VOICE_PROMPT_DIR)
VOICE_PROMPT_DIR.mkdir(parents=True, exist_ok=True)
VOICE_PROMPT_EXTENSIONS = {".wav", ".mp3", ".m4a", ".flac", ".ogg"}
CHATTERBOX_VOICE_REGISTRY = Path("data/chatterbox_voices.json")
EXTERNAL_VOICES_ARCHIVE_FILE = Path("data/external_voice_archives.json")
PREP_PROGRESS_DIR = Path("data/prep")
PREP_PROGRESS_DIR.mkdir(parents=True, exist_ok=True)
LLM_PROFILE_USAGE_FILE = Path("data/llm_profile_usage.json")
LLM_PROFILE_USAGE_LOCK = threading.Lock()
PROJECTS_FILE = Path(__file__).resolve().parent / "data" / "projects.json"
ENGINE_FIRST_RUN_NOTICE_FILE = Path(__file__).resolve().parent / "data" / "engine-first-run.json"
ENGINE_FIRST_RUN_NOTICE_LOCK = threading.Lock()
FIRST_RUN_MARKER = Path(__file__).resolve().parent / ".first_run_pending"
ENGINE_INSTALL_LOG_DIR = Path(__file__).resolve().parent / "data" / "engine-installs"
ENGINE_INSTALL_LOG_DIR.mkdir(parents=True, exist_ok=True)
ENGINE_INSTALL_LOCK = threading.Lock()
ENGINE_INSTALL_JOBS: Dict[str, Dict[str, Any]] = {}
SERVER_INSTANCE_ID = uuid.uuid4().hex
SERVER_RESTART_EXIT_CODE = 75

ENGINE_INSTALL_GENERATION_IDS = {
    "kokoro": {"kokoro"},
    "chatterbox_turbo_local": {"chatterbox_turbo_local"},
    "voxcpm_local": {"voxcpm_local"},
    "pocket_tts": {"pocket_tts", "pocket_tts_preset"},
    "qwen3": {"qwen3_custom", "qwen3_clone"},
    "omnivoice": {"omnivoice_clone", "omnivoice_design"},
    "kitten_tts": {"kitten_tts"},
    "index_tts": {"index_tts"},
    "dots_tts": {"dots_tts"},
    "edge_tts": {"edge_tts"},
    "audio8_tts": {"audio8_tts"},
    "breeze_tts_2": {"breeze_tts_2"},
}
PROJECTS_LOCK = threading.RLock()
JOB_METADATA_FILENAME = "metadata.json"
DEFAULT_GEMINI_MODEL = "gemini-1.5-flash"
DEFAULT_LLM_PROVIDER = "gemini"
SUPPORTED_LLM_PROVIDERS = ("gemini", "atlas", "openrouter", "local")
LIBRARY_CACHE_TTL = 5  # seconds
MIN_CHATTERBOX_PROMPT_SECONDS = 5.0
MIN_VOICE_DESIGN_PREVIEW_SECONDS = 10.0
MIN_VOICE_DESIGN_PREVIEW_WORDS = 40
MAX_VOICE_DESIGN_PREVIEW_SECONDS = 45.0
# Qwen's bundled generation config permits 8,192 codec frames. At 12 Hz that
# can represent more than eleven minutes of audio when a sampled generation
# misses its normal end token. Casting previews are only 12-20 seconds, so a
# generous 768-frame ceiling prevents one bad seed from occupying the GPU for
# an hour without truncating a valid preview.
MAX_VOICE_DESIGN_PREVIEW_TOKENS = 768
VOICE_DESIGN_MAX_ATTEMPTS = 2
VOICE_DESIGN_CUDA_CLEANUP_INTERVAL = 8
# Qwen's stock 0.9 temperatures are intentionally creative, but VoiceDesign
# casting needs prompt adherence more than maximum variety.  These conservative
# defaults still let separate candidate seeds produce alternatives while greatly
# reducing gender/style drift, whispering, and other extreme performances.
VOICE_DESIGN_CASTING_GENERATION = {
    "temperature": 0.6,
    "top_p": 0.9,
    "top_k": 40,
    "subtalker_temperature": 0.6,
    "subtalker_top_p": 0.9,
    "subtalker_top_k": 40,
    "max_new_tokens": MAX_VOICE_DESIGN_PREVIEW_TOKENS,
}
DEFAULT_CONFIG = {
    "replicate_api_key": "",
    "chunk_size": 500,
    "kokoro_chunk_size": 500,
    "chatterbox_turbo_local_chunk_size": 450,
    "voxcpm_chunk_size": 550,
    "qwen3_chunk_size": 500,
    "pocket_tts_chunk_size": 450,
    "sample_rate": 24000,
    "speed": 1.0,
    "output_format": "mp3",
    "output_bitrate_kbps": 128,
    "crossfade_duration": 0.1,
    "intro_silence_ms": 0,
    "inter_chunk_silence_ms": 0,
    "pause_marker_three_seconds": 0.25,
    "pause_marker_six_seconds": 0.5,
    "gemini_api_key": "",
    "gemini_model": DEFAULT_GEMINI_MODEL,
    "gemini_prompt": "",
    "gemini_prompt_presets": [],
    "gemini_speaker_profile_prompt": "",
    "llm_provider": DEFAULT_LLM_PROVIDER,
    "llm_backup_profiles": [],
    "atlas_cloud_api_key": "",
    "atlas_cloud_base_url": DEFAULT_ATLAS_CLOUD_BASE_URL,
    "atlas_cloud_model": DEFAULT_ATLAS_CLOUD_MODEL,
    "atlas_cloud_timeout": 120,
    "openrouter_api_key": "",
    "openrouter_base_url": DEFAULT_OPENROUTER_BASE_URL,
    "openrouter_model": DEFAULT_OPENROUTER_MODEL,
    "openrouter_timeout": 120,
    "azure_speech_key": "",
    "azure_speech_region": "",
    "azure_speech_default_voice": DEFAULT_AZURE_SPEECH_VOICE,
    "azure_speech_output_format": DEFAULT_AZURE_SPEECH_OUTPUT_FORMAT,
    "azure_speech_timeout": 60,
    "azure_speech_max_parallel": 2,
    "azure_speech_requests_per_minute": DEFAULT_AZURE_SPEECH_REQUESTS_PER_MINUTE,
    "azure_speech_chunk_size": 1000,
    "azure_speech_default_style": "",
    "azure_speech_default_role": "",
    "azure_speech_default_style_degree": 1.0,
    "edge_tts_default_voice": DEFAULT_EDGE_TTS_VOICE,
    "edge_tts_timeout": 60,
    "edge_tts_max_parallel": 2,
    "edge_tts_max_retries": 4,
    "edge_tts_chunk_size": 1000,
    "edge_tts_default_volume": 0,
    "elevenlabs_api_key": "",
    "elevenlabs_base_url": DEFAULT_ELEVENLABS_BASE_URL,
    "elevenlabs_model": DEFAULT_ELEVENLABS_MODEL,
    "elevenlabs_default_voice": DEFAULT_ELEVENLABS_VOICE,
    "elevenlabs_output_format": DEFAULT_ELEVENLABS_OUTPUT_FORMAT,
    "elevenlabs_timeout": 120,
    "elevenlabs_max_parallel": 2,
    "elevenlabs_chunk_size": 4000,
    "elevenlabs_stability": 0.5,
    "elevenlabs_similarity_boost": 0.75,
    "elevenlabs_style": 0.0,
    "elevenlabs_use_speaker_boost": True,
    "openai_tts_api_key": "",
    "openai_tts_base_url": DEFAULT_OPENAI_TTS_BASE_URL,
    "openai_tts_model": DEFAULT_OPENAI_TTS_MODEL,
    "openai_tts_default_voice": DEFAULT_OPENAI_TTS_VOICE,
    "openai_tts_custom_voices": "",
    "openai_tts_instructions": "",
    "openai_tts_timeout": 120,
    "openai_tts_max_parallel": 2,
    "openai_tts_chunk_size": 4000,
    "localai_tts_api_key": "",
    "breeze_api_key": "",
    "breeze_api_model": "breeze-tts-2",
    "breeze_api_default_voice": "",
    "breeze_api_instructions": "",
    "breeze_api_timeout": 180,
    "breeze_api_max_parallel": 1,
    "breeze_api_max_retries": 2,
    "breeze_api_guidance_scale": 4.0,
    "breeze_api_chunk_size": 1000,
    "localai_tts_base_url": DEFAULT_LOCALAI_TTS_BASE_URL,
    "localai_tts_model": "",
    "localai_tts_default_voice": "",
    "localai_tts_default_language": "",
    "localai_tts_instructions": "",
    "localai_tts_timeout": 180,
    "localai_tts_max_parallel": 1,
    "localai_tts_max_retries": 4,
    "localai_tts_chunk_size": 1000,
    "audio8_tts_model_id": "Audio8/Audio8-TTS-Preview-0.6b",
    "audio8_tts_device": "auto",
    "audio8_tts_dtype": "auto",
    "audio8_tts_temperature": 0.8,
    "audio8_tts_top_p": 0.95,
    "audio8_tts_top_k": 50,
    "audio8_tts_max_new_tokens": 1024,
    "audio8_tts_retry_max_new_tokens": 2000,
    "audio8_tts_seed": 42,
    "audio8_tts_default_prompt": "",
    "audio8_tts_default_prompt_text": "",
    "audio8_tts_chunk_size": 140,
    "audio8_tts_hard_chunk_size": 400,
    "breeze_tts_2_model_id": "BreezeBlue/Breeze-TTS-2",
    "breeze_tts_2_runtime": "pytorch",
    "breeze_tts_2_device": "auto",
    "breeze_tts_2_seed": 42,
    "breeze_tts_2_clone_cfg_scale": 1.0,
    "breeze_tts_2_design_cfg_scale": 4.0,
    "breeze_tts_2_direction_cfg_scale": 4.0,
    "breeze_tts_2_max_new_tokens": 1500,
    "breeze_tts_2_max_seq_len": 2048,
    "breeze_tts_2_fast_mode": False,
    "breeze_tts_2_default_prompt": "",
    "breeze_tts_2_default_prompt_text": "",
    "breeze_tts_2_default_instruction": "Speak clearly and naturally.",
    "breeze_tts_2_chunk_size": 500,
    "localai_tts_voice_profile_consent_confirmed": False,
    "cloud_tts_concurrent_jobs": 2,
    "llm_local_provider": LLM_PROVIDER_LMSTUDIO,
    "llm_local_base_url": DEFAULT_LOCAL_LLM_BASE_URLS[LLM_PROVIDER_LMSTUDIO],
    "llm_local_model": "",
    "llm_local_api_key": "",
    "llm_local_timeout": 120,
    "llm_local_temperature": 0.2,
    "llm_local_top_p": 1.0,
    "llm_local_top_k": 0,
    "llm_local_repeat_penalty": 1.0,
    "llm_local_max_tokens": 0,
    "llm_local_disable_reasoning": False,
    "llm_gemini_chunk_size": 500,
    "llm_local_chunk_size": 500,
    "llm_gemini_chunk_chapters": True,
    "llm_local_chunk_chapters": True,
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
    "qwen3_custom_model_id": "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice",
    "qwen3_custom_device": "auto",
    "qwen3_custom_dtype": "bfloat16",
    "qwen3_custom_attn_implementation": "flash_attention_2",
    "qwen3_custom_default_language": "Auto",
    "qwen3_custom_default_instruct": "",
    "qwen3_clone_model_id": "Qwen/Qwen3-TTS-12Hz-1.7B-Base",
    "qwen3_clone_device": "auto",
    "qwen3_clone_dtype": "bfloat16",
    "qwen3_clone_attn_implementation": "flash_attention_2",
    "qwen3_clone_default_language": "Auto",
    "qwen3_clone_default_prompt": "",
    "qwen3_clone_default_prompt_text": "",
    "qwen3_voice_design_model_id": "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign",
    "omnivoice_clone_model_id": "k2-fsa/OmniVoice",
    "omnivoice_clone_device": "auto",
    "omnivoice_clone_dtype": "float16",
    "omnivoice_clone_num_step": 32,
    "omnivoice_clone_default_prompt": "",
    "omnivoice_clone_default_prompt_text": "",
    "omnivoice_design_model_id": "k2-fsa/OmniVoice",
    "omnivoice_design_device": "auto",
    "omnivoice_design_dtype": "float16",
    "omnivoice_design_num_step": 32,
    "omnivoice_design_default_instruct": "",
    "omnivoice_chunk_size": 500,
    "omnivoice_post_process": True,
    "omnivoice_duration_safety_margin": 0.25,
    "omnivoice_batch_size": 1,
    "pocket_tts_model_variant": "b6369a24",
    "pocket_tts_temp": 0.7,
    "pocket_tts_lsd_decode_steps": 1,
    "pocket_tts_noise_clamp": None,
    "pocket_tts_eos_threshold": -4.0,
    "pocket_tts_default_prompt": "",
    "huggingface_token": "",
    "pocket_tts_prompt_truncate": False,
    "pocket_tts_num_threads": None,
    "pocket_tts_interop_threads": None,
    "kitten_tts_model_id": "KittenML/kitten-tts-mini-0.8",
    "kitten_tts_default_voice": "Jasper",
    "kitten_tts_chunk_size": 300,
    "index_tts_model_version": "IndexTTS-2",
    "index_tts_use_fp16": False,
    "index_tts_use_deepspeed": False,
    "index_tts_use_torch_compile": False,
    "index_tts_use_accel": False,
    "index_tts_num_beams": 1,
    "index_tts_diffusion_steps": 12,
    "index_tts_temperature": 0.8,
    "index_tts_top_p": 0.8,
    "index_tts_top_k": 30,
    "index_tts_repetition_penalty": 10.0,
    "index_tts_max_mel_tokens": 1500,
    "index_tts_max_text_tokens_per_segment": 120,
    "index_tts_device": "auto",
    "index_tts_default_prompt": "",
    "index_tts_chunk_size": 400,
    "dots_tts_model_id": "rednote-hilab/dots.tts-soar",
    "dots_tts_precision": "auto",
    "dots_tts_optimize": False,
    "dots_tts_num_steps": 10,
    "dots_tts_guidance_scale": 1.2,
    "dots_tts_speaker_scale": 1.5,
    "dots_tts_seed": 42,
    "dots_tts_language": "none",
    "dots_tts_normalize_text": False,
    "dots_tts_device": "auto",
    "dots_tts_default_prompt": "",
    "dots_tts_default_prompt_text": "",
    "dots_tts_allow_xvector_only": False,
    "dots_tts_chunk_size": 250,
    "replicate_max_parallel": 3,
    "parallel_chunks": 3,
    "group_chunks_by_speaker": False,
    "cleanup_vram_after_job": False,
    "remote_engine_management_enabled": False,
    "remote_engine_management_token": "",
}

SECRET_CONFIG_KEYS = {
    "atlas_cloud_api_key",
    "openrouter_api_key",
    "gemini_api_key",
    "replicate_api_key",
    "llm_local_api_key",
    "chatterbox_turbo_replicate_api_token",
    "azure_speech_key",
    "elevenlabs_api_key",
    "openai_tts_api_key",
    "localai_tts_api_key",
    "breeze_api_key",
    "huggingface_token",
    "remote_engine_management_token",
}

POCKET_TTS_PRESET_VOICES = [
    "alba",
    "marius",
    "javert",
    "jean",
    "fantine",
    "cosette",
    "eponine",
    "azelma",
]

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
QWEN3_CUSTOM_SETTING_KEYS = {
    "qwen3_custom_model_id",
    "qwen3_custom_device",
    "qwen3_custom_dtype",
    "qwen3_custom_attn_implementation",
    "qwen3_custom_default_language",
    "qwen3_custom_default_instruct",
}
QWEN3_CLONE_SETTING_KEYS = {
    "qwen3_clone_model_id",
    "qwen3_clone_device",
    "qwen3_clone_dtype",
    "qwen3_clone_attn_implementation",
    "qwen3_clone_default_language",
    "qwen3_clone_default_prompt",
    "qwen3_clone_default_prompt_text",
}
POCKET_TTS_SETTING_KEYS = {
    "huggingface_token",
    "pocket_tts_model_variant",
    "pocket_tts_temp",
    "pocket_tts_lsd_decode_steps",
    "pocket_tts_noise_clamp",
    "pocket_tts_eos_threshold",
    "pocket_tts_default_prompt",
    "pocket_tts_prompt_truncate",
    "pocket_tts_num_threads",
    "pocket_tts_interop_threads",
}
DOTS_TTS_SETTING_KEYS = {
    "dots_tts_model_id",
    "dots_tts_precision",
    "dots_tts_optimize",
    "dots_tts_num_steps",
    "dots_tts_guidance_scale",
    "dots_tts_speaker_scale",
    "dots_tts_seed",
    "dots_tts_language",
    "dots_tts_normalize_text",
    "dots_tts_device",
    "dots_tts_default_prompt",
    "dots_tts_default_prompt_text",
    "dots_tts_allow_xvector_only",
    "dots_tts_chunk_size",
}
AUDIO8_TTS_SETTING_KEYS = {
    "audio8_tts_model_id", "audio8_tts_device", "audio8_tts_dtype",
    "audio8_tts_temperature", "audio8_tts_top_p", "audio8_tts_top_k",
    "audio8_tts_max_new_tokens", "audio8_tts_retry_max_new_tokens",
    "audio8_tts_seed", "audio8_tts_default_prompt",
    "audio8_tts_default_prompt_text", "audio8_tts_chunk_size", "audio8_tts_hard_chunk_size",
}
BREEZE_TTS_2_SETTING_KEYS = {
    "breeze_tts_2_runtime",
    "breeze_tts_2_model_id", "breeze_tts_2_device", "breeze_tts_2_seed",
    "breeze_tts_2_clone_cfg_scale", "breeze_tts_2_design_cfg_scale",
    "breeze_tts_2_direction_cfg_scale", "breeze_tts_2_max_new_tokens",
    "breeze_tts_2_max_seq_len", "breeze_tts_2_fast_mode",
    "breeze_tts_2_default_prompt", "breeze_tts_2_default_prompt_text",
    "breeze_tts_2_default_instruction", "breeze_tts_2_chunk_size",
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
QWEN3_CUSTOM_OPTION_ALIASES = {
    "model": "qwen3_custom_model_id",
    "model_id": "qwen3_custom_model_id",
    "device": "qwen3_custom_device",
    "dtype": "qwen3_custom_dtype",
    "attn_implementation": "qwen3_custom_attn_implementation",
    "default_language": "qwen3_custom_default_language",
    "default_instruct": "qwen3_custom_default_instruct",
}
QWEN3_CLONE_OPTION_ALIASES = {
    "model": "qwen3_clone_model_id",
    "model_id": "qwen3_clone_model_id",
    "device": "qwen3_clone_device",
    "dtype": "qwen3_clone_dtype",
    "attn_implementation": "qwen3_clone_attn_implementation",
    "default_language": "qwen3_clone_default_language",
    "default_prompt": "qwen3_clone_default_prompt",
    "prompt_text": "qwen3_clone_default_prompt_text",
}
POCKET_TTS_OPTION_ALIASES = {
    "model": "pocket_tts_model_variant",
    "model_variant": "pocket_tts_model_variant",
    "temp": "pocket_tts_temp",
    "temperature": "pocket_tts_temp",
    "lsd_decode_steps": "pocket_tts_lsd_decode_steps",
    "noise_clamp": "pocket_tts_noise_clamp",
    "eos_threshold": "pocket_tts_eos_threshold",
    "default_prompt": "pocket_tts_default_prompt",
    "prompt": "pocket_tts_default_prompt",
    "prompt_truncate": "pocket_tts_prompt_truncate",
    "num_threads": "pocket_tts_num_threads",
    "interop_threads": "pocket_tts_interop_threads",
}
DOTS_TTS_OPTION_ALIASES = {
    "model": "dots_tts_model_id",
    "model_id": "dots_tts_model_id",
    "model_name_or_path": "dots_tts_model_id",
    "precision": "dots_tts_precision",
    "optimize": "dots_tts_optimize",
    "num_steps": "dots_tts_num_steps",
    "steps": "dots_tts_num_steps",
    "guidance_scale": "dots_tts_guidance_scale",
    "speaker_scale": "dots_tts_speaker_scale",
    "seed": "dots_tts_seed",
    "language": "dots_tts_language",
    "normalize_text": "dots_tts_normalize_text",
    "device": "dots_tts_device",
    "default_prompt": "dots_tts_default_prompt",
    "prompt": "dots_tts_default_prompt",
    "prompt_text": "dots_tts_default_prompt_text",
    "allow_xvector_only": "dots_tts_allow_xvector_only",
    "chunk_size": "dots_tts_chunk_size",
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


def _is_external_voice_id(voice_id: str) -> bool:
    return bool(voice_id) and voice_id.startswith("external:")


def _strip_external_voice_id(voice_id: str) -> str:
    return voice_id.replace("external:", "", 1)


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


def _normalize_engine_options(engine_name: str, options: Dict[str, Any]) -> Dict[str, Any]:
    if engine_name == "chatterbox_turbo_local":
        return _normalize_chatterbox_turbo_local_options(options)
    if engine_name == "chatterbox_turbo_replicate":
        return _normalize_chatterbox_turbo_replicate_options(options)
    if engine_name == "voxcpm_local":
        return _normalize_voxcpm_local_options(options)
    if engine_name == "qwen3_custom":
        return _normalize_qwen3_custom_options(options)
    if engine_name == "qwen3_clone":
        return _normalize_qwen3_clone_options(options)
    if engine_name == "omnivoice_clone":
        return _normalize_omnivoice_clone_options(options)
    if engine_name == "omnivoice_design":
        return _normalize_omnivoice_design_options(options)
    if engine_name in {"pocket_tts", "pocket_tts_preset"}:
        return _normalize_pocket_tts_options(options)
    if engine_name == "kitten_tts":
        return _normalize_kitten_tts_options(options)
    if engine_name == "index_tts":
        return _normalize_index_tts_options(options)
    if engine_name == "dots_tts":
        return _normalize_dots_tts_options(options)
    if engine_name == "audio8_tts":
        return _normalize_audio8_tts_options(options)
    if engine_name == "breeze_tts_2":
        return _normalize_breeze_tts_2_options(options)
    return {}


def _normalize_audio8_tts_options(options: Dict[str, Any]) -> Dict[str, Any]:
    normalized = {
        str(key).strip().lower(): value for key, value in (options or {}).items()
        if key is not None and str(key).strip().lower() in AUDIO8_TTS_SETTING_KEYS
    }
    result: Dict[str, Any] = {}
    for key, value in normalized.items():
        if key in {"audio8_tts_temperature", "audio8_tts_top_p"}:
            maximum = 2.0 if key.endswith("temperature") else 1.0
            result[key] = _coerce_float(value, minimum=0.01, maximum=maximum,
                                        fallback=float(DEFAULT_CONFIG[key]))
        elif key in {"audio8_tts_top_k", "audio8_tts_max_new_tokens",
                     "audio8_tts_retry_max_new_tokens", "audio8_tts_seed",
                     "audio8_tts_chunk_size", "audio8_tts_hard_chunk_size"}:
            limits = {
                "audio8_tts_top_k": (0, 1000), "audio8_tts_max_new_tokens": (64, 4000),
                "audio8_tts_retry_max_new_tokens": (64, 4000), "audio8_tts_seed": (0, 2147483647),
                "audio8_tts_chunk_size": (40, 150), "audio8_tts_hard_chunk_size": (150, 1000),
            }[key]
            result[key] = _coerce_int(value, minimum=limits[0], maximum=limits[1],
                                      fallback=int(DEFAULT_CONFIG[key]))
        else:
            result[key] = str(value or "").strip()
    if "audio8_tts_retry_max_new_tokens" in result:
        result["audio8_tts_retry_max_new_tokens"] = max(
            int(result.get("audio8_tts_max_new_tokens", DEFAULT_CONFIG["audio8_tts_max_new_tokens"])),
            int(result["audio8_tts_retry_max_new_tokens"]),
        )
    if "audio8_tts_hard_chunk_size" in result or "audio8_tts_chunk_size" in result:
        soft_limit = int(result.get("audio8_tts_chunk_size", DEFAULT_CONFIG["audio8_tts_chunk_size"]))
        hard_limit = int(result.get("audio8_tts_hard_chunk_size", DEFAULT_CONFIG["audio8_tts_hard_chunk_size"]))
        result["audio8_tts_hard_chunk_size"] = max(soft_limit, hard_limit)
    return result


def _normalize_breeze_tts_2_options(options: Dict[str, Any]) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for raw_key, value in (options or {}).items():
        key = str(raw_key or "").strip().lower()
        if key not in BREEZE_TTS_2_SETTING_KEYS:
            continue
        if key == "breeze_tts_2_runtime":
            result[key] = value if isinstance(value, str) and value in {"pytorch", "q8"} else "pytorch"
        elif key == "breeze_tts_2_fast_mode":
            result[key] = _coerce_bool(value)
        elif key in {
            "breeze_tts_2_clone_cfg_scale", "breeze_tts_2_design_cfg_scale",
            "breeze_tts_2_direction_cfg_scale",
        }:
            result[key] = _coerce_float(value, minimum=0.1, maximum=10.0,
                                        fallback=float(DEFAULT_CONFIG[key]))
        elif key == "breeze_tts_2_seed":
            result[key] = _coerce_int(value, minimum=0, maximum=2147483647, fallback=42)
        elif key == "breeze_tts_2_max_new_tokens":
            result[key] = _coerce_int(value, minimum=64, maximum=3000, fallback=1500)
        elif key == "breeze_tts_2_max_seq_len":
            result[key] = _coerce_int(value, minimum=512, maximum=4096, fallback=2048)
        elif key == "breeze_tts_2_chunk_size":
            result[key] = _coerce_int(value, minimum=100, maximum=1500, fallback=500)
        else:
            result[key] = str(value or "").strip()
    return result


def _breeze_runtime_ready(config=None):
    from src.engines.isolated_proxy import breeze_runtime_available
    # Keep the app-level availability check for install/uninstall state.
    if not isolated_engine_available('breeze_tts_2'):
        return False
    return breeze_runtime_available((config if config is not None else load_config()).get('breeze_tts_2_runtime', 'pytorch'))


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


def _normalize_pocket_tts_options(options: Dict[str, Any]) -> Dict[str, Any]:
    normalized: Dict[str, Any] = {}
    for raw_key, value in options.items():
        if raw_key is None:
            continue
        key = str(raw_key).strip().lower()
        canonical = POCKET_TTS_OPTION_ALIASES.get(key)
        if not canonical and key in POCKET_TTS_SETTING_KEYS:
            canonical = key
        if canonical and canonical in POCKET_TTS_SETTING_KEYS:
            normalized[canonical] = value

    result: Dict[str, Any] = {}
    for key, value in normalized.items():
        if key in {"pocket_tts_temp", "pocket_tts_noise_clamp", "pocket_tts_eos_threshold"}:
            result[key] = None if value in (None, "") else _coerce_float(
                value,
                minimum=-10.0,
                maximum=10.0,
                fallback=DEFAULT_CONFIG.get(key),
            )
            continue
        if key == "pocket_tts_lsd_decode_steps":
            result[key] = _coerce_int(value, minimum=1, maximum=8, fallback=DEFAULT_CONFIG.get(key, 1))
            continue
        if key == "pocket_tts_prompt_truncate":
            result[key] = _coerce_bool(value)
            continue
        if key in {"pocket_tts_num_threads", "pocket_tts_interop_threads"}:
            result[key] = None if value in (None, "") else _coerce_int(
                value,
                minimum=1,
                maximum=64,
                fallback=DEFAULT_CONFIG.get(key),
            )
            continue
        result[key] = (value or "").strip() if isinstance(value, str) else value
    return result


def _normalize_kitten_tts_options(options: Dict[str, Any]) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for raw_key, value in options.items():
        if raw_key is None:
            continue
        key = str(raw_key).strip().lower()
        if key == "kitten_tts_model_id":
            result[key] = (value or KITTEN_TTS_DEFAULT_MODEL).strip()
        elif key == "kitten_tts_default_voice":
            v = (value or "Jasper").strip()
            result[key] = v if v in KITTEN_TTS_BUILTIN_VOICES else "Jasper"
        elif key == "kitten_tts_chunk_size":
            result[key] = _coerce_int(value, minimum=50, maximum=600, fallback=300)
    return result


def _normalize_index_tts_options(options: Dict[str, Any]) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for raw_key, value in options.items():
        if raw_key is None:
            continue
        key = str(raw_key).strip().lower()
        if key == "index_tts_model_version":
            v = (value or "IndexTTS-2").strip()
            result[key] = v if v in {"IndexTTS-2", "IndexTTS-1.5", "IndexTTS"} else "IndexTTS-2"
        elif key == "index_tts_use_fp16":
            result[key] = _coerce_bool(value)
        elif key == "index_tts_use_deepspeed":
            result[key] = _coerce_bool(value)
        elif key == "index_tts_use_torch_compile":
            result[key] = _coerce_bool(value)
        elif key == "index_tts_use_accel":
            result[key] = _coerce_bool(value)
        elif key == "index_tts_num_beams":
            result[key] = max(1, int(value or 1))
        elif key == "index_tts_diffusion_steps":
            result[key] = max(1, int(value or 25))
        elif key == "index_tts_temperature":
            result[key] = max(0.01, float(value or 0.8))
        elif key == "index_tts_top_p":
            result[key] = max(0.01, min(1.0, float(value or 0.8)))
        elif key == "index_tts_top_k":
            result[key] = max(1, int(value or 30))
        elif key == "index_tts_repetition_penalty":
            result[key] = max(1.0, float(value or 10.0))
        elif key == "index_tts_max_mel_tokens":
            result[key] = max(100, int(value or 1500))
        elif key == "index_tts_max_text_tokens_per_segment":
            result[key] = max(20, int(value or 120))
        elif key == "index_tts_device":
            v = (value or "auto").strip().lower()
            result[key] = v if v else "auto"
        elif key == "index_tts_default_prompt":
            result[key] = (value or "").strip()
        elif key == "index_tts_chunk_size":
            result[key] = _coerce_int(value, minimum=100, maximum=1000, fallback=400)
    return result


def _normalize_dots_tts_options(options: Dict[str, Any]) -> Dict[str, Any]:
    normalized: Dict[str, Any] = {}
    for raw_key, value in options.items():
        if raw_key is None:
            continue
        key = str(raw_key).strip().lower()
        canonical = DOTS_TTS_OPTION_ALIASES.get(key)
        if not canonical and key in DOTS_TTS_SETTING_KEYS:
            canonical = key
        if canonical and canonical in DOTS_TTS_SETTING_KEYS:
            normalized[canonical] = value

    result: Dict[str, Any] = {}
    for key, value in normalized.items():
        if key in {"dots_tts_optimize", "dots_tts_normalize_text", "dots_tts_allow_xvector_only"}:
            result[key] = _coerce_bool(value)
        elif key == "dots_tts_num_steps":
            result[key] = _coerce_int(value, minimum=1, maximum=64, fallback=10)
        elif key == "dots_tts_guidance_scale":
            result[key] = _coerce_float(value, minimum=0.1, maximum=5.0, fallback=1.2)
        elif key == "dots_tts_speaker_scale":
            result[key] = _coerce_float(value, minimum=0.1, maximum=3.0, fallback=1.5)
        elif key == "dots_tts_seed":
            result[key] = None if value in (None, "") else _coerce_int(value, minimum=0, maximum=2147483647, fallback=42)
        elif key == "dots_tts_chunk_size":
            result[key] = _coerce_int(value, minimum=100, maximum=1000, fallback=250)
        elif key == "dots_tts_precision":
            v = (value or "auto").strip().lower()
            result[key] = v if v in {"auto", "bfloat16", "bf16", "float16", "fp16", "float32", "fp32"} else "auto"
        elif key == "dots_tts_language":
            result[key] = (value or "none").strip() or "none"
        else:
            result[key] = (value or "").strip() if isinstance(value, str) else value
    return result


OMNIVOICE_CLONE_SETTING_KEYS = {
    "omnivoice_clone_model_id",
    "omnivoice_clone_device",
    "omnivoice_clone_dtype",
    "omnivoice_clone_num_step",
    "omnivoice_clone_default_prompt",
    "omnivoice_clone_default_prompt_text",
    "omnivoice_chunk_size",
    "omnivoice_post_process",
    "omnivoice_duration_safety_margin",
    "omnivoice_batch_size",
}

OMNIVOICE_DESIGN_SETTING_KEYS = {
    "omnivoice_design_model_id",
    "omnivoice_design_device",
    "omnivoice_design_dtype",
    "omnivoice_design_num_step",
    "omnivoice_design_default_instruct",
    "omnivoice_chunk_size",
    "omnivoice_post_process",
    "omnivoice_duration_safety_margin",
    "omnivoice_batch_size",
}


def _normalize_omnivoice_clone_options(options: Dict[str, Any]) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for raw_key, value in options.items():
        if raw_key is None:
            continue
        key = str(raw_key).strip().lower()
        if key in OMNIVOICE_CLONE_SETTING_KEYS:
            if key == "omnivoice_duration_safety_margin":
                result[key] = _coerce_float(value, minimum=0.0, maximum=2.0, fallback=0.25)
            elif key == "omnivoice_batch_size":
                result[key] = _coerce_int(value, minimum=1, maximum=8, fallback=1)
            else:
                result[key] = (value or "").strip() if isinstance(value, str) else value
    return result


def _normalize_omnivoice_design_options(options: Dict[str, Any]) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for raw_key, value in options.items():
        if raw_key is None:
            continue
        key = str(raw_key).strip().lower()
        if key in OMNIVOICE_DESIGN_SETTING_KEYS:
            if key == "omnivoice_duration_safety_margin":
                result[key] = _coerce_float(value, minimum=0.0, maximum=2.0, fallback=0.25)
            elif key == "omnivoice_batch_size":
                result[key] = _coerce_int(value, minimum=1, maximum=8, fallback=1)
            else:
                result[key] = (value or "").strip() if isinstance(value, str) else value
    return result


def _normalize_qwen3_clone_options(options: Dict[str, Any]) -> Dict[str, Any]:
    normalized: Dict[str, Any] = {}
    for raw_key, value in options.items():
        if raw_key is None:
            continue
        key = str(raw_key).strip().lower()
        canonical = QWEN3_CLONE_OPTION_ALIASES.get(key)
        if not canonical and key in QWEN3_CLONE_SETTING_KEYS:
            canonical = key
        if canonical and canonical in QWEN3_CLONE_SETTING_KEYS:
            normalized[canonical] = value

    result: Dict[str, Any] = {}
    for key in QWEN3_CLONE_SETTING_KEYS:
        if key in normalized:
            result[key] = normalized[key]
    return result


def _normalize_qwen3_custom_options(options: Dict[str, Any]) -> Dict[str, Any]:
    normalized: Dict[str, Any] = {}
    for raw_key, value in options.items():
        if raw_key is None:
            continue
        key = str(raw_key).strip().lower()
        canonical = QWEN3_CUSTOM_OPTION_ALIASES.get(key)
        if not canonical and key in QWEN3_CUSTOM_SETTING_KEYS:
            canonical = key
        if canonical and canonical in QWEN3_CUSTOM_SETTING_KEYS:
            normalized[canonical] = value

    result: Dict[str, Any] = {}
    for key, value in normalized.items():
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
BOOK_HEADING_PATTERN = re.compile(
    r'^\s*(?:\[[^\]]+\]\s*)*(book\b[^\n\r]*)$',
    re.IGNORECASE | re.MULTILINE
)

SECTION_HEADING_KEYWORDS = [
    "book",
    "chapter",
    "section",
    "letter",
    "part",
    "introduction",
    "intro",
    "prologue",
    "preface",
    "foreword",
    "epilogue",
    "afterword",
    "appendix",
    "author note",
    "author's note",
]

def _parse_section_headings_from_db(custom_heading: Optional[str]) -> Optional[Any]:
    """Parse section headings from database custom_heading field.
    Handles both old format (comma-separated string) and new format (JSON with enabled_headings).
    """
    if not custom_heading:
        return None
    try:
        # Try to parse as JSON first (new format)
        parsed = json.loads(custom_heading)
        if isinstance(parsed, dict) and "enabled_headings" in parsed:
            return parsed["enabled_headings"]
        # If it's a list, return it directly
        if isinstance(parsed, list):
            return parsed
    except (json.JSONDecodeError, TypeError):
        pass
    # Fall back to old comma-separated format
    return str(custom_heading).split(",") if custom_heading else None


def _normalize_custom_headings(value: Optional[Any]) -> List[str]:
    if not value:
        return []
    if isinstance(value, list):
        raw_values = value
    else:
        raw_values = str(value).split(",")
    normalized = []
    for entry in raw_values:
        if not entry:
            continue
        candidate = str(entry).strip()
        if candidate:
            normalized.append(candidate)
    return normalized


def _book_heading_enabled(section_headings: Optional[Any]) -> bool:
    """Book mode is available by default, but obeys an explicit UI selection."""
    if section_headings is None:
        return True
    return "book" in {
        heading.lower() for heading in _normalize_custom_headings(section_headings)
    }


def _without_book_heading(section_headings: Optional[Any]) -> Optional[List[str]]:
    """Return headings handled by the regular, non-book section detector."""
    if section_headings is None:
        return None
    return [
        heading
        for heading in _normalize_custom_headings(section_headings)
        if heading.lower() != "book"
    ]


def _find_book_heading_matches(text: str, section_headings: Optional[Any]) -> List[re.Match]:
    if not _book_heading_enabled(section_headings):
        return []
    return list(BOOK_HEADING_PATTERN.finditer(text or ""))


def _keyword_to_regex(keyword: str) -> str:
    normalized = keyword.strip()
    escaped = re.escape(normalized)
    if not escaped:
        return ""
    escaped = escaped.replace(r"\ ", r"\s+")

    # A word boundary makes symbol-only markers impossible to match and is
    # unreliable for languages that do not put spaces before heading numbers.
    last_character = normalized[-1]
    if last_character.isascii() and last_character.isalpha():
        # Do not match prose words such as "particular", but allow compact
        # headings such as "Episode1".
        return escaped + r"(?![^\W\d_])"
    if last_character.isascii() and (last_character.isdigit() or last_character == "_"):
        return escaped + r"\b"
    return escaped


def _clean_heading_text(value: Optional[str]) -> str:
    if not value:
        return ""
    cleaned = re.sub(r"\[[^\]]+\]", "", str(value))
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return sanitize_display_title(cleaned)


def _build_section_heading_pattern(section_headings: Optional[Any] = None) -> re.Pattern:
    keywords = []
    if section_headings is not None:
        for heading in _normalize_custom_headings(section_headings):
            lowered = heading.lower()
            if lowered not in keywords:
                keywords.append(lowered)
    # If no section_headings provided (None), use default keywords
    # If section_headings is explicitly empty list, use no keywords
    if section_headings is None and not keywords:
        keywords = list(SECTION_HEADING_KEYWORDS)
    keyword_regex = "|".join(filter(None, (_keyword_to_regex(word) for word in keywords)))
    if not keyword_regex:
        # An explicit empty selection means detection is disabled.  Use an
        # impossible expression instead of silently restoring "chapter".
        keyword_regex = r"(?!)"
    return re.compile(
        rf'^\s*(?:\[[^\]]+\]\s*)*(({keyword_regex})[^\n\r]*)$',
        re.IGNORECASE | re.MULTILINE
    )

# Exceptions
class JobCancelled(Exception):
    """Raised when a job is cancelled mid-processing."""


class JobPaused(Exception):
    """Raised when a job is paused after completing a chunk."""


# Global state
jobs = {}  # Track all jobs (queued, processing, completed)
job_queue = queue.Queue()  # Thread-safe job queue
current_job_id = None  # Legacy single-job indicator for older clients
current_job_ids = set()  # All jobs currently processing
cancel_flags = {}  # Cancellation flags for jobs
cancel_events = {}  # Cancellation events for immediate job aborts
pause_flags = {}  # Pause flags for jobs
queue_lock = threading.Lock()  # Lock for thread-safe operations
_chunks_metadata_locks = defaultdict(threading.Lock)
worker_thread = None  # Background worker thread
cloud_job_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="cloud-job")
cloud_job_condition = threading.Condition()
active_cloud_jobs = 0
CLOUD_TTS_ENGINES = {
    "breeze_api",
    "kokoro_replicate",
    "chatterbox_turbo_replicate",
    "azure_speech",
    "edge_tts",
    "elevenlabs",
    "openai_tts",
}
tts_engine_instances: Dict[str, TtsEngineBase] = {}
engine_config_signatures: Dict[str, str] = {}
tts_engine_lock = threading.Lock()
azure_voice_cache: Dict[str, Dict[str, Any]] = {}
azure_voice_cache_lock = threading.Lock()
edge_voice_cache: Dict[str, Any] = {"timestamp": 0.0, "voices": []}
edge_voice_cache_lock = threading.Lock()
elevenlabs_catalog_cache: Dict[str, Dict[str, Any]] = {}
elevenlabs_catalog_cache_lock = threading.Lock()
# Lock to prevent concurrent GPU inference across all TTS operations
# This prevents GPU contention and "badcase" retry loops with VoxCPM
gpu_inference_lock = threading.Lock()
voice_transcript_generator = VoiceTranscriptGenerator(device="cpu")
# Use max_workers=1 to prevent parallel GPU inference which causes contention
# and "badcase" retry loops with VoxCPM and other GPU-based engines
chunk_regen_executor = ThreadPoolExecutor(max_workers=1)
qwen3_voice_design_model = None
qwen3_voice_design_signature = None
qwen3_voice_design_generation_count = 0
qwen3_voice_design_process = None
qwen3_voice_design_log_handle = None
qwen3_voice_design_process_lock = threading.Lock()
breeze_voice_design_process = None
breeze_voice_design_log_handle = None
breeze_voice_design_process_lock = threading.Lock()
gpu_generation_lifecycle_lock = threading.RLock()
library_cache = {
    "items": None,
    "timestamp": 0.0,
}


def _job_dir_from_entry(job_id: str, job_entry: Dict[str, Any]) -> Path:
    directory = job_entry.get("job_dir")
    if directory:
        candidate = Path(directory)
        try:
            resolved = candidate.resolve()
            expected_root = (OUTPUT_DIR / job_id).resolve()
            if resolved == expected_root:
                return resolved
            if expected_root in resolved.parents:
                return resolved
        except Exception:
            pass
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
    if (assignment.get('extra') or {}).get('breeze_sample_name'):
        return assignment['extra']['breeze_sample_name']
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


def _normalize_speaker_key(speaker: Optional[str]) -> str:
    return (speaker or "").strip().lower()


def _normalize_voice_assignments_map(voice_assignments: Any) -> Dict[str, Dict[str, Any]]:
    if not isinstance(voice_assignments, dict):
        return {}
    normalized: Dict[str, Dict[str, Any]] = {}
    for raw_key, assignment in voice_assignments.items():
        if not isinstance(assignment, dict):
            continue
        if raw_key == "default":
            normalized["default"] = assignment
            continue
        normalized[_normalize_speaker_key(raw_key)] = assignment
    return normalized


def _prepare_voice_assignments(text: str, voice_assignments: Any) -> Dict[str, Dict[str, Any]]:
    normalized = _normalize_voice_assignments_map(voice_assignments)
    if not normalized:
        return {}
    if "default" not in normalized and len(normalized) == 1:
        normalized["default"] = next(iter(normalized.values()))
    speakers = _extract_speakers_for_text(text)
    if "default" in speakers and "default" not in normalized:
        normalized["default"] = next(iter(normalized.values()))
    # When there are multiple speaker assignments, text outside speaker tags is
    # rendered as "default". Always ensure a "default" fallback so prompt-based
    # engines (OmniVoice Clone, Chatterbox Turbo, etc.) don't reject the job.
    if "default" not in normalized and len(normalized) > 1:
        normalized["default"] = next(iter(normalized.values()))
    return normalized


def _extract_speakers_for_text(text: str) -> List[str]:
    processor = TextProcessor()
    speakers = processor.extract_speakers(text)
    return speakers or ["default"]


def _check_speaker_tag_balance(text: str) -> List[str]:
    """Return a list of human-readable error strings for any unbalanced speaker tags.

    Detects:
    - Opening tags with no matching close: [narrator] ... (no [/narrator])
    - Closing tags with no matching open: [/narrator] at the start
    - Mismatched nesting: [narrator] ... [/sola]
    """
    from src.tag_validation import tag_errors
    return tag_errors(text)


def _validate_voice_assignments_for_engine(
    engine_name: str,
    text: str,
    voice_assignments: Any,
    config: Dict[str, Any],
) -> None:
    engine_name = _normalize_engine_name(engine_name)

    # Run independently of detected speaker count, including orphan control tags.
    tag_errors = _check_speaker_tag_balance(text)
    if tag_errors:
        raise ValueError(
            "Speaker/direction tags are unbalanced — please fix the text before submitting.\n"
            + "\n".join(f"  • {e}" for e in tag_errors)
        )

    speakers = _extract_speakers_for_text(text)
    normalized_assignments = _normalize_voice_assignments_map(voice_assignments)
    default_assignment = normalized_assignments.get("default") or {}
    if not default_assignment and len(normalized_assignments) == 1:
        default_assignment = next(iter(normalized_assignments.values())) or {}
    missing_voices: List[str] = []
    missing_prompts: List[str] = []

    for speaker in speakers:
        assignment = normalized_assignments.get(speaker) or default_assignment or {}
        voice = (assignment.get("voice") or "").strip()
        prompt = (assignment.get("audio_prompt_path") or "").strip()

        if engine_name in {"kokoro", "qwen3_custom"} and not voice:
            missing_voices.append(speaker)

        if engine_name == "azure_speech":
            default_voice = (config.get("azure_speech_default_voice") or "").strip()
            if not voice and not default_voice:
                missing_voices.append(speaker)

        if engine_name == "edge_tts":
            default_voice = (config.get("edge_tts_default_voice") or "").strip()
            if not voice and not default_voice:
                missing_voices.append(speaker)

        if engine_name == "elevenlabs":
            default_voice = (config.get("elevenlabs_default_voice") or "").strip()
            if not voice and not default_voice:
                missing_voices.append(speaker)

        if engine_name == "openai_tts":
            default_voice = (config.get("openai_tts_default_voice") or "").strip()
            if not voice and not default_voice:
                missing_voices.append(speaker)

        if engine_name == "localai_tts":
            # A LocalAI model may provide its own default voice. Voice-profile
            # selection remains optional for compatibility with those models.
            pass

        if engine_name == "breeze_api" and not prompt and not voice and not config.get("breeze_api_default_voice"):
            missing_voices.append(speaker)

        if engine_name == "chatterbox_turbo_replicate":
            default_voice = (config.get("chatterbox_turbo_replicate_voice") or "").strip()
            if not prompt and not voice and not default_voice:
                missing_voices.append(speaker)

        if engine_name == "chatterbox_turbo_local":
            default_prompt = (config.get("chatterbox_turbo_local_default_prompt") or "").strip()
            if not prompt and not default_prompt:
                missing_prompts.append(speaker)

        if engine_name == "qwen3_clone":
            default_prompt = (config.get("qwen3_clone_default_prompt") or "").strip()
            if not prompt and not default_prompt:
                missing_prompts.append(speaker)

        if engine_name == "omnivoice_clone":
            default_prompt = (config.get("omnivoice_clone_default_prompt") or "").strip()
            if not prompt and not default_prompt:
                missing_prompts.append(speaker)

        if engine_name in {"pocket_tts", "pocket_tts_preset"}:
            default_prompt = (config.get("pocket_tts_default_prompt") or "").strip()
            if not prompt and not voice and not default_prompt:
                missing_prompts.append(speaker)

        if engine_name == "kitten_tts":
            default_voice = (config.get("kitten_tts_default_voice") or "").strip()
            if not voice and not default_voice:
                missing_voices.append(speaker)

        if engine_name == "index_tts":
            default_prompt = (config.get("index_tts_default_prompt") or "").strip()
            if not prompt and not default_prompt:
                missing_prompts.append(speaker)

        if engine_name == "dots_tts":
            default_prompt = (config.get("dots_tts_default_prompt") or "").strip()
            if not prompt and not default_prompt:
                missing_prompts.append(speaker)

    if missing_voices or missing_prompts:
        pieces = []
        if missing_voices:
            pieces.append(
                "Select a voice for: " + ", ".join(missing_voices)
            )
        if missing_prompts:
            pieces.append(
                "Select a reference audio prompt for: " + ", ".join(missing_prompts)
            )
        raise ValueError(". ".join(pieces))


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


def _update_review_post_progress(job_id: str, step_index: int, ratio: float) -> None:
    with queue_lock:
        entry = jobs.get(job_id)
        if not entry:
            return
        total_steps = int(entry.get("post_process_total") or 0)
        if total_steps <= 0:
            return
        clamped = max(0.0, min(float(ratio or 0), 1.0))
        overall = ((max(step_index - 1, 0)) + clamped) / total_steps
        entry["post_process_percent"] = int(min(overall * 100, 100))
        entry["post_process_active"] = True


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
        config_snapshot = _hydrate_config_secrets(job_entry.get("config_snapshot") or load_config())
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

    word_replacements = job_entry.get("word_replacements") or []
    chunk_text = (text_to_render or "").strip()
    if not chunk_text:
        raise ValueError("Chunk text cannot be empty.")
    if not relative_file:
        raise ValueError("Chunk does not have an associated file path.")

    # Use system temp directory instead of job_dir to avoid Windows permission issues
    tmp_dir = Path(tempfile.mkdtemp(prefix="tts_chunk_regen_"))
    generated_files: List[str] = []
    try:
        regen_text = _apply_word_replacements(chunk_text, word_replacements) if word_replacements else chunk_text
        render_parts = split_text_and_pause_markers(regen_text, allow_attached=True)
        has_pause_controls = any(kind == "pause" for kind, _value in render_parts)
        spoken_parts = [value.strip() for kind, value in render_parts if kind == "text" and value.strip()]
        segments = [{
            "speaker": speaker,
            "text": " ".join(spoken_parts),
            "chunks": spoken_parts,
            "emotion": chunk.get("emotion"),
            "delivery_instruction": chunk.get("delivery_instruction") or chunk.get("emotion"),
        }] if spoken_parts else []
        engine_name = _normalize_engine_name(config_snapshot.get("tts_engine"))

        if engine_name == 'breeze_api':
            # Keep review regeneration bound to its production snapshot.
            voice_config = BREEZE_PRODUCTIONS.bind(job_id, voice_config)

        if spoken_parts:
            # Acquire GPU lock to prevent concurrent inference which causes
            # GPU contention and "badcase" retry loops with VoxCPM.
            with gpu_inference_lock:
                engine = get_tts_engine(engine_name, config=config_snapshot)
                generated_files = engine.generate_batch(
                    segments=segments,
                    voice_config=voice_config,
                    output_dir=str(tmp_dir),
                    speed=speed,
                    sample_rate=sample_rate,
                )

            if len(generated_files or []) != len(spoken_parts):
                raise RuntimeError(
                    "TTS engine did not return all spoken parts surrounding the pause marker."
                )

        if has_pause_controls:
            # A review chunk may come from an older job where attached controls
            # such as ``CHAPTER ONE******`` were stored with the spoken text.
            # Rebuild that one logical chunk from separately rendered speech
            # and digital silence so regeneration cannot speak or discard stars.
            from pydub import AudioSegment

            combined_audio = AudioSegment.empty()
            spoken_index = 0
            silence_rate = int(sample_rate or 24000)
            for kind, value in render_parts:
                if kind == "pause":
                    pause_seconds = pause_seconds_for_text(
                        value,
                        config_snapshot.get("pause_marker_three_seconds", 0.25),
                        config_snapshot.get("pause_marker_six_seconds", 0.5),
                    )
                    if pause_seconds is not None:
                        combined_audio += AudioSegment.silent(
                            duration=int(round(pause_seconds * 1000)),
                            frame_rate=silence_rate,
                        )
                elif value.strip():
                    combined_audio += AudioSegment.from_file(generated_files[spoken_index])
                    spoken_index += 1
            temp_file = tmp_dir / f"pause_aware_{chunk_id}.wav"
            combined_audio.export(temp_file, format="wav")
        else:
            if not generated_files:
                raise RuntimeError("TTS engine did not return any audio for the chunk.")
            temp_file = Path(generated_files[0])
        target_path = job_dir / relative_file
        target_path.parent.mkdir(parents=True, exist_ok=True)

        # Extract leading/trailing silence from voice assignment
        leading_silence_ms = int((effective_assignment or {}).get("leading_silence_ms", 0) or 0)
        trailing_silence_ms = int((effective_assignment or {}).get("trailing_silence_ms", 0) or 0)

        # Always apply silence (even if zero) to ensure any existing silence is removed
        from src.audio_merger import apply_chunk_silence
        temp_with_silence = tmp_dir / f"chunk_with_silence_{chunk_id}.wav"
        apply_chunk_silence(
            str(temp_file),
            str(temp_with_silence),
            leading_ms=leading_silence_ms,
            trailing_ms=trailing_silence_ms,
        )
        shutil.move(str(temp_with_silence), str(target_path))
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
            chunk["engine"] = engine_name
            if effective_assignment:
                chunk["voice_assignment"] = copy.deepcopy(effective_assignment)
                voice_label = _voice_label_from_assignment(effective_assignment)
                if voice_label:
                    chunk["voice_label"] = voice_label
                else:
                    chunk.pop("voice_label", None)

    _persist_chunks_metadata(job_id, job_dir)


def _persist_chunks_metadata(job_id: str, job_dir: Path):
    """Update chunks_metadata.json without letting bookkeeping stop synthesis."""
    metadata_lock = _chunks_metadata_locks[job_id]
    with metadata_lock:
        with queue_lock:
            job_entry = jobs.get(job_id)
            if not job_entry:
                return False
            # The writer runs outside queue_lock; isolate it from later chunk
            # callbacks while JSON serialization is in progress.
            job_chunks = copy.deepcopy(job_entry.get("chunks") or [])
            config_snapshot = job_entry.get("config_snapshot") or {}
            engine_name = _normalize_engine_name(config_snapshot.get("tts_engine"))

        chunks_meta_path = job_dir / "chunks_metadata.json"
        existing_meta = {}
        if chunks_meta_path.exists():
            try:
                with chunks_meta_path.open("r", encoding="utf-8") as handle:
                    existing_meta = json.load(handle)
            except (OSError, json.JSONDecodeError):
                pass

        chunks_meta = {
            "engine": engine_name,
            "created_at": existing_meta.get("created_at", datetime.now().isoformat()),
            "updated_at": datetime.now().isoformat(),
            "chunks": job_chunks,
        }
        if existing_meta.get("timing_metrics"):
            chunks_meta["timing_metrics"] = existing_meta["timing_metrics"]
        try:
            write_json_atomic(chunks_meta_path, chunks_meta)
            return True
        except OSError as exc:
            logger.warning(
                "Job %s: Could not save chunks_metadata.json after retries; "
                "generation will continue and the checkpoint will be retried: %s",
                job_id,
                exc,
            )
            return False


def _load_chunks_metadata(job_dir: Path) -> List[Dict[str, Any]]:
    chunks_meta_path = job_dir / "chunks_metadata.json"
    if not chunks_meta_path.exists():
        return []
    try:
        with chunks_meta_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        chunks = payload.get("chunks") if isinstance(payload, dict) else None
        return [dict(item) for item in (chunks or []) if isinstance(item, dict)]
    except Exception:
        return []


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


def _get_jobs_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(JOBS_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_jobs_db() -> None:
    with _get_jobs_db_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                job_id TEXT PRIMARY KEY,
                status TEXT,
                created_at TEXT,
                updated_at TEXT,
                text_preview TEXT,
                text_path TEXT,
                text_length INTEGER,
                engine TEXT,
                split_by_chapter INTEGER,
                generate_full_story INTEGER,
                review_mode INTEGER,
                custom_heading TEXT,
                merge_options TEXT,
                voice_assignments TEXT,
                config_snapshot TEXT,
                job_dir TEXT,
                total_chunks INTEGER,
                processed_chunks INTEGER,
                progress INTEGER,
                eta_seconds INTEGER,
                post_process_total INTEGER,
                post_process_done INTEGER,
                post_process_percent INTEGER,
                post_process_active INTEGER,
                chapter_mode INTEGER,
                chapter_count INTEGER,
                book_mode INTEGER,
                book_count INTEGER,
                full_story_requested INTEGER,
                paused_at TEXT,
                interrupted_at TEXT,
                last_completed_chunk_index INTEGER,
                resume_from_chunk_index INTEGER,
                archived INTEGER DEFAULT 0,
                error TEXT,
                job_payload TEXT
            )
            """
        )
        conn.commit()


def _job_text_dir(job_id: str) -> Path:
    job_dir = JOBS_DATA_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    return job_dir


def _write_job_text(job_id: str, text: str) -> str:
    job_dir = _job_text_dir(job_id)
    text_path = job_dir / "input.txt"
    text_path.write_text(text or "", encoding="utf-8")
    return str(text_path)


def _load_job_text(text_path: Optional[str]) -> str:
    if not text_path:
        return ""
    try:
        return Path(text_path).read_text(encoding="utf-8")
    except Exception:
        return ""


def _serialize_job_payload(job_entry: Dict[str, Any]) -> Dict[str, Any]:
    payload = dict(job_entry.get("job_payload") or {})
    if not isinstance(payload, dict):
        payload = {}
    for key in ("timing_metrics", "started_at", "completed_at", "job_type"):
        value = job_entry.get(key)
        if value is not None:
            payload[key] = value
    word_replacements = job_entry.get("word_replacements")
    if word_replacements is not None:
        payload["word_replacements"] = word_replacements
    return payload


def _serialize_job_entry(job_id: str, job_entry: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "job_id": job_id,
        "status": job_entry.get("status"),
        "created_at": job_entry.get("created_at"),
        "updated_at": datetime.now().isoformat(),
        "text_preview": job_entry.get("text_preview"),
        "text_path": job_entry.get("text_path"),
        "text_length": job_entry.get("text_length"),
        "engine": job_entry.get("engine"),
        "split_by_chapter": int(bool(job_entry.get("chapter_mode"))),
        "generate_full_story": int(bool(job_entry.get("full_story_requested"))),
        "review_mode": int(bool(job_entry.get("review_mode"))),
        "custom_heading": json.dumps({"enabled_headings": job_entry.get("section_headings")}) if job_entry.get("section_headings") is not None else None,
        "merge_options": json.dumps(job_entry.get("merge_options") or {}),
        "voice_assignments": json.dumps(job_entry.get("voice_assignments") or {}),
        "config_snapshot": json.dumps(_redact_config_secrets(job_entry.get("config_snapshot") or {})),
        "job_dir": job_entry.get("job_dir"),
        "total_chunks": job_entry.get("total_chunks"),
        "processed_chunks": job_entry.get("processed_chunks"),
        "progress": job_entry.get("progress"),
        "eta_seconds": job_entry.get("eta_seconds"),
        "post_process_total": job_entry.get("post_process_total"),
        "post_process_done": job_entry.get("post_process_done"),
        "post_process_percent": job_entry.get("post_process_percent"),
        "post_process_active": int(bool(job_entry.get("post_process_active"))),
        "chapter_mode": int(bool(job_entry.get("chapter_mode"))),
        "chapter_count": job_entry.get("chapter_count"),
        "book_mode": int(bool(job_entry.get("book_mode"))),
        "book_count": job_entry.get("book_count"),
        "full_story_requested": int(bool(job_entry.get("full_story_requested"))),
        "paused_at": job_entry.get("paused_at"),
        "interrupted_at": job_entry.get("interrupted_at"),
        "last_completed_chunk_index": job_entry.get("last_completed_chunk_index"),
        "resume_from_chunk_index": job_entry.get("resume_from_chunk_index"),
        "archived": int(bool(job_entry.get("archived"))),
        "error": job_entry.get("error"),
        "job_payload": json.dumps(_serialize_job_payload(job_entry)),
    }


def _persist_job_state(job_id: str, job_entry: Optional[Dict[str, Any]] = None, force: bool = False) -> None:
    with queue_lock:
        entry = job_entry or jobs.get(job_id)
        if not entry:
            return
        now = time.monotonic()
        last_persisted = entry.get("_last_persisted")
        if not force and last_persisted and (now - last_persisted) < 2:
            return
        entry["_last_persisted"] = now
        payload = _serialize_job_entry(job_id, entry)

    with _get_jobs_db_connection() as conn:
        conn.execute(
            """
            INSERT INTO jobs (
                job_id, status, created_at, updated_at, text_preview, text_path, text_length, engine,
                split_by_chapter, generate_full_story, review_mode, custom_heading, merge_options,
                voice_assignments, config_snapshot, job_dir, total_chunks, processed_chunks, progress,
                eta_seconds, post_process_total, post_process_done, post_process_percent, post_process_active,
                chapter_mode, chapter_count, book_mode, book_count, full_story_requested, paused_at,
                interrupted_at, last_completed_chunk_index, resume_from_chunk_index, archived, error, job_payload
            ) VALUES (
                :job_id, :status, :created_at, :updated_at, :text_preview, :text_path, :text_length, :engine,
                :split_by_chapter, :generate_full_story, :review_mode, :custom_heading, :merge_options,
                :voice_assignments, :config_snapshot, :job_dir, :total_chunks, :processed_chunks, :progress,
                :eta_seconds, :post_process_total, :post_process_done, :post_process_percent, :post_process_active,
                :chapter_mode, :chapter_count, :book_mode, :book_count, :full_story_requested, :paused_at,
                :interrupted_at, :last_completed_chunk_index, :resume_from_chunk_index, :archived, :error, :job_payload
            )
            ON CONFLICT(job_id) DO UPDATE SET
                status=excluded.status,
                created_at=COALESCE(jobs.created_at, excluded.created_at),
                updated_at=excluded.updated_at,
                text_preview=excluded.text_preview,
                text_path=excluded.text_path,
                text_length=excluded.text_length,
                engine=excluded.engine,
                split_by_chapter=excluded.split_by_chapter,
                generate_full_story=excluded.generate_full_story,
                review_mode=excluded.review_mode,
                custom_heading=excluded.custom_heading,
                merge_options=excluded.merge_options,
                voice_assignments=excluded.voice_assignments,
                config_snapshot=excluded.config_snapshot,
                job_dir=excluded.job_dir,
                total_chunks=excluded.total_chunks,
                processed_chunks=excluded.processed_chunks,
                progress=excluded.progress,
                eta_seconds=excluded.eta_seconds,
                post_process_total=excluded.post_process_total,
                post_process_done=excluded.post_process_done,
                post_process_percent=excluded.post_process_percent,
                post_process_active=excluded.post_process_active,
                chapter_mode=excluded.chapter_mode,
                chapter_count=excluded.chapter_count,
                book_mode=excluded.book_mode,
                book_count=excluded.book_count,
                full_story_requested=excluded.full_story_requested,
                paused_at=excluded.paused_at,
                interrupted_at=excluded.interrupted_at,
                last_completed_chunk_index=excluded.last_completed_chunk_index,
                resume_from_chunk_index=excluded.resume_from_chunk_index,
                archived=excluded.archived,
                error=excluded.error,
                job_payload=excluded.job_payload
            """,
            payload,
        )
        conn.commit()


def _load_jobs_from_db() -> Dict[str, Dict[str, Any]]:
    loaded: Dict[str, Dict[str, Any]] = {}
    with _get_jobs_db_connection() as conn:
        rows = conn.execute("SELECT * FROM jobs WHERE status != 'deleted'").fetchall()
    for row in rows:
        job_id = row["job_id"]
        loaded[job_id] = {
            "status": row["status"],
            "created_at": row["created_at"] or row["updated_at"],
            "updated_at": row["updated_at"],
            "text_preview": row["text_preview"],
            "text_path": row["text_path"],
            "text_length": row["text_length"],
            "engine": row["engine"],
            "chapter_mode": bool(row["chapter_mode"]),
            "full_story_requested": bool(row["full_story_requested"]),
            "review_mode": bool(row["review_mode"]),
            "custom_heading": row["custom_heading"],
            "section_headings": _parse_section_headings_from_db(row["custom_heading"]),
            "merge_options": json.loads(row["merge_options"] or "{}"),
            "voice_assignments": json.loads(row["voice_assignments"] or "{}"),
            "config_snapshot": json.loads(row["config_snapshot"] or "{}"),
            "job_dir": row["job_dir"],
            "total_chunks": row["total_chunks"],
            "processed_chunks": row["processed_chunks"],
            "progress": row["progress"],
            "eta_seconds": row["eta_seconds"],
            "post_process_total": row["post_process_total"],
            "post_process_done": row["post_process_done"],
            "post_process_percent": row["post_process_percent"],
            "post_process_active": bool(row["post_process_active"]),
            "chapter_count": row["chapter_count"],
            "book_mode": bool(row["book_mode"]),
            "book_count": row["book_count"],
            "paused_at": row["paused_at"],
            "interrupted_at": row["interrupted_at"],
            "last_completed_chunk_index": row["last_completed_chunk_index"],
            "resume_from_chunk_index": row["resume_from_chunk_index"],
            "archived": bool(row["archived"]),
            "error": row["error"],
            "job_payload": json.loads(row["job_payload"] or "{}"),
            "chunks": [],
            "regen_tasks": {},
        }
        _extra = loaded[job_id]["job_payload"]
        for key in ("timing_metrics", "started_at", "completed_at", "word_replacements", "job_type"):
            if key in _extra:
                loaded[job_id][key] = _extra[key]
    return loaded


def _purge_stale_jobs(days: int = 7) -> None:
    """Hard-delete terminal-state jobs (cancelled/failed/interrupted/deleted) older than `days` days."""
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    terminal_statuses = "('cancelled', 'failed', 'interrupted', 'deleted')"
    with _get_jobs_db_connection() as conn:
        stale = conn.execute(
            f"SELECT job_id, status FROM jobs WHERE status IN {terminal_statuses} AND updated_at < ?",
            (cutoff,),
        ).fetchall()
        # Also purge any deleted-status rows regardless of age
        deleted_rows = conn.execute(
            "SELECT job_id, status FROM jobs WHERE status = 'deleted'"
        ).fetchall()
    all_to_purge = {row["job_id"]: row["status"] for row in stale}
    all_to_purge.update({row["job_id"]: row["status"] for row in deleted_rows})
    for job_id, status in all_to_purge.items():
        try:
            with _get_jobs_db_connection() as conn:
                conn.execute("DELETE FROM jobs WHERE job_id=?", (job_id,))
                conn.commit()
            logger.info("Purged stale job %s (status=%s)", job_id, status)
        except Exception as exc:
            logger.warning("Failed to purge stale job %s: %s", job_id, exc)


def _archive_old_jobs(max_jobs: int = 500) -> None:
    with _get_jobs_db_connection() as conn:
        row = conn.execute("SELECT COUNT(*) AS cnt FROM jobs WHERE archived=0").fetchone()
        count = int(row["cnt"] or 0) if row else 0
        if count <= max_jobs:
            return
        to_archive = conn.execute(
            "SELECT job_id FROM jobs WHERE archived=0 ORDER BY created_at ASC LIMIT ?",
            (count - max_jobs,),
        ).fetchall()
    for row in to_archive:
        job_id = row["job_id"]
        job_audio_dir = OUTPUT_DIR / job_id
        job_data_dir = JOBS_DATA_DIR / job_id
        archive_root = JOBS_ARCHIVE_DIR / job_id
        try:
            archive_root.mkdir(parents=True, exist_ok=True)
            if job_audio_dir.exists():
                shutil.move(str(job_audio_dir), str(archive_root / "audio"))
            if job_data_dir.exists():
                shutil.move(str(job_data_dir), str(archive_root / "data"))
            with _get_jobs_db_connection() as conn:
                conn.execute(
                    "UPDATE jobs SET archived=1, status='archived' WHERE job_id=?",
                    (job_id,),
                )
                conn.commit()
        except Exception as exc:
            logger.warning("Failed to archive job %s: %s", job_id, exc)


def _build_job_payload(job_id: str, text: str, job_entry: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "job_id": job_id,
        "text_path": job_entry.get("text_path"),
        "voice_assignments": job_entry.get("voice_assignments") or {},
        "config_snapshot": _redact_config_secrets(job_entry.get("config_snapshot") or {}),
        "split_by_chapter": bool(job_entry.get("chapter_mode")),
        "generate_full_story": bool(job_entry.get("full_story_requested")),
        "review_mode": bool(job_entry.get("review_mode")),
        "merge_options": job_entry.get("merge_options") or {},
        "job_dir": job_entry.get("job_dir"),
        "custom_heading": json.dumps({"enabled_headings": job_entry.get("section_headings")}) if job_entry.get("section_headings") is not None else None,
        "section_headings": job_entry.get("section_headings"),
        "total_chunks": job_entry.get("total_chunks"),
        "engine": job_entry.get("engine"),
        "word_replacements": job_entry.get("word_replacements") or [],
        "text_preview": (text or "")[:200],
    }


def _build_job_data_from_entry(job_id: str, job_entry: Dict[str, Any]) -> Dict[str, Any]:
    payload = job_entry.get("job_payload") or {}
    text_path = payload.get("text_path") or job_entry.get("text_path")
    text = _load_job_text(text_path)
    config = _hydrate_config_secrets(job_entry.get("config_snapshot") or load_config())
    return {
        "job_id": job_id,
        "text": text,
        "voice_assignments": job_entry.get("voice_assignments") or {},
        "config": config,
        "split_by_chapter": bool(job_entry.get("chapter_mode")),
        "generate_full_story": bool(job_entry.get("full_story_requested")),
        "total_chunks": job_entry.get("total_chunks") or 0,
        "review_mode": bool(job_entry.get("review_mode")),
        "merge_options": job_entry.get("merge_options") or {},
        "job_dir": job_entry.get("job_dir"),
        "section_headings": job_entry.get("section_headings"),
        "resume_from_chunk_index": job_entry.get("resume_from_chunk_index") or 0,
        "word_replacements": payload.get("word_replacements") or job_entry.get("word_replacements") or [],
    }


def _restore_jobs_from_db() -> None:
    loaded = _load_jobs_from_db()
    with queue_lock:
        jobs.clear()
        jobs.update(loaded)
        for job_id, job_entry in jobs.items():
            status = job_entry.get("status")
            if status in {"processing", "queued", "pausing"}:
                if status == "processing":
                    # Check if the job actually finished — output files on disk mean it completed
                    job_dir_str = job_entry.get("job_dir")
                    _actually_completed = False
                    if job_dir_str:
                        _jdir = Path(job_dir_str)
                        # Completed jobs have output.mp3/wav or chapter subdirs with audio
                        _audio_exts = {".mp3", ".wav", ".flac", ".ogg", ".m4a"}
                        if any(f.suffix in _audio_exts for f in _jdir.glob("output*")):
                            _actually_completed = True
                        elif any(f.suffix in _audio_exts for f in _jdir.rglob("chapter_*/*")):
                            _actually_completed = True
                        elif any(f.suffix in _audio_exts for f in _jdir.rglob("*/Title*")):
                            _actually_completed = True
                    if _actually_completed:
                        job_entry["status"] = "completed"
                        job_entry["progress"] = 100
                        job_entry["interrupted_at"] = None
                        job_entry["eta_seconds"] = 0
                    else:
                        job_entry["status"] = "interrupted"
                        job_entry["interrupted_at"] = datetime.now().isoformat()
                        last_completed = job_entry.get("last_completed_chunk_index")
                        if last_completed is not None:
                            job_entry["resume_from_chunk_index"] = max(0, int(last_completed) + 1)
                else:
                    job_entry["status"] = "paused"
                job_entry["eta_seconds"] = None
    for job_id in loaded.keys():
        _persist_job_state(job_id, force=True)


def _normalize_engine_name(name: Optional[str]) -> str:
    value = (name or DEFAULT_CONFIG["tts_engine"]).strip().lower()
    return value or DEFAULT_CONFIG["tts_engine"]


def _resolve_qwen_device(device: str) -> str:
    import torch
    candidate = (device or "auto").strip().lower()
    if candidate == "auto":
        return "cuda" if torch.cuda.is_available() else "cpu"
    if candidate.startswith("cuda") and not torch.cuda.is_available():
        raise RuntimeError("CUDA device requested but no GPU is available.")
    return candidate


def _resolve_qwen_dtype(dtype_value: str):
    import torch
    normalized = (dtype_value or "").strip().lower()
    if normalized in {"bf16", "bfloat16"}:
        return torch.bfloat16
    if normalized in {"fp16", "float16"}:
        return torch.float16
    return torch.float32


def _resolve_qwen_attn(attn_value: Optional[str]) -> Optional[str]:
    from src.attention_backend import resolve_qwen_attention_backend

    return resolve_qwen_attention_backend(attn_value, logger=logger)


def _ensure_qwen3_model(model_id: str) -> Path:
    from huggingface_hub import snapshot_download
    local_model_dir = Path(__file__).parent / "models" / "qwen3"
    local_model_dir.mkdir(parents=True, exist_ok=True)
    model_path = local_model_dir / model_id.replace("/", "_")
    if not model_path.exists() or not any(model_path.iterdir()):
        logger.info("Downloading Qwen3 model to %s (this may take a few minutes)...", model_path)
        try:
            snapshot_download(
                repo_id=model_id,
                local_dir=str(model_path),
                local_dir_use_symlinks=False,
            )
        except Exception as exc:
            logger.error("Failed to download Qwen3 model %s: %s", model_id, exc, exc_info=True)
            raise RuntimeError(
                "Qwen3 VoiceDesign model files are missing. Download the model while online "
                "(repo: %s) into %s, then retry." % (model_id, model_path)
            ) from exc
    return model_path


def _qwen3_voice_design_signature(config: Dict[str, Any]) -> str:
    model_id = (config.get("qwen3_voice_design_model_id") or "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign").strip()
    device = (config.get("qwen3_custom_device") or "auto").strip()
    dtype = (config.get("qwen3_custom_dtype") or "bfloat16").strip()
    attn = (config.get("qwen3_custom_attn_implementation") or "flash_attention_2").strip()
    return f"{model_id}|{device}|{dtype}|{attn}"


def _get_qwen3_voice_design_model(config: Dict[str, Any]):
    if not isolated_engine_available("qwen3_custom"):
        raise ImportError("Qwen3-TTS is not installed. Install it from Settings → Engine Settings.")
    global qwen3_voice_design_model, qwen3_voice_design_signature
    config = config or {}
    signature = _qwen3_voice_design_signature(config)
    with tts_engine_lock:
        if qwen3_voice_design_model is not None and qwen3_voice_design_signature == signature:
            return qwen3_voice_design_model
        from qwen_tts import Qwen3TTSModel  # type: ignore
        model_id = (config.get("qwen3_voice_design_model_id") or "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign").strip()
        device = _resolve_qwen_device(config.get("qwen3_custom_device") or "auto")
        dtype = _resolve_qwen_dtype(config.get("qwen3_custom_dtype") or "bfloat16")
        attn = _resolve_qwen_attn(config.get("qwen3_custom_attn_implementation") or "flash_attention_2")
        model_path = _ensure_qwen3_model(model_id)
        logger.info(
            "Loading Qwen3 VoiceDesign model=%s device=%s dtype=%s attn=%s",
            model_id,
            device,
            dtype,
            attn or "auto",
        )
        qwen3_voice_design_model = Qwen3TTSModel.from_pretrained(
            str(model_path),
            device_map=device,
            dtype=dtype,
            attn_implementation=attn or None,
        )
        qwen3_voice_design_signature = signature
        return qwen3_voice_design_model


def _run_isolated_qwen_voice_design(request_payload: Dict[str, Any]) -> Dict[str, Any]:
    """Run casting in Qwen's persistent isolated process and keep its model warm."""
    global qwen3_voice_design_process, qwen3_voice_design_log_handle
    python = Path(__file__).resolve().parent / "engines" / "qwen3" / ".venv" / (
        "Scripts/python.exe" if os.name == "nt" else "bin/python"
    )
    worker = Path(__file__).resolve().parent / "engines" / "qwen3_voice_design_worker.py"
    if not python.is_file() or not worker.is_file():
        raise ImportError("Qwen3-TTS isolated runtime is not installed.")
    with gpu_generation_lifecycle_lock, qwen3_voice_design_process_lock:
        _release_cached_narration_engines()
        if qwen3_voice_design_process is None or qwen3_voice_design_process.poll() is not None:
            log_path = Path(__file__).resolve().parent / "data" / "qwen3-voice-design-worker.log"
            log_path.parent.mkdir(parents=True, exist_ok=True)
            if qwen3_voice_design_log_handle:
                qwen3_voice_design_log_handle.close()
            qwen3_voice_design_log_handle = log_path.open("a", encoding="utf-8", errors="replace")
            qwen3_voice_design_process = subprocess.Popen(
                [str(python), "-u", str(worker)],
                cwd=str(Path(__file__).resolve().parent),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=qwen3_voice_design_log_handle,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
        process = qwen3_voice_design_process
        process.stdin.write(json.dumps(request_payload, ensure_ascii=False) + "\n")
        process.stdin.flush()
        request_id = request_payload["id"]
        for line in process.stdout:
            if not line.startswith("TTS_STORY_QWEN_RESULT "):
                continue
            response = json.loads(line[len("TTS_STORY_QWEN_RESULT "):])
            if response.get("id") != request_id:
                continue
            if not response.get("success"):
                raise RuntimeError(response.get("error") or "Qwen3 VoiceDesign worker failed")
            return response
        raise RuntimeError("Qwen3 VoiceDesign worker stopped without returning a result.")


def _run_isolated_breeze_voice_design(request_payload: Dict[str, Any]) -> Dict[str, Any]:
    """Run Breeze casting in its persistent isolated process and keep the model warm."""
    global breeze_voice_design_process, breeze_voice_design_log_handle
    python = Path(__file__).resolve().parent / "engines" / "breeze_tts_2" / ".venv" / (
        "Scripts/python.exe" if os.name == "nt" else "bin/python"
    )
    worker = Path(__file__).resolve().parent / "engines" / "breeze_voice_design_worker.py"
    if not python.is_file() or not worker.is_file() or not isolated_engine_available("breeze_tts_2"):
        raise ImportError("Breeze TTS 2 isolated runtime is not installed.")
    license_marker = Path(__file__).resolve().parent / "engines" / "breeze_tts_2" / ".license_accepted"
    if not license_marker.is_file():
        raise PermissionError(
            "Accept the BreezeBlue Research and Non-Commercial License in Breeze TTS 2 settings first."
        )
    with gpu_generation_lifecycle_lock, breeze_voice_design_process_lock:
        _release_cached_narration_engines()
        if breeze_voice_design_process is None or breeze_voice_design_process.poll() is not None:
            log_path = Path(__file__).resolve().parent / "data" / "breeze-voice-design-worker.log"
            log_path.parent.mkdir(parents=True, exist_ok=True)
            if breeze_voice_design_log_handle:
                breeze_voice_design_log_handle.close()
            breeze_voice_design_log_handle = log_path.open("a", encoding="utf-8", errors="replace")
            breeze_voice_design_process = subprocess.Popen(
                [str(python), "-u", str(worker)],
                cwd=str(Path(__file__).resolve().parent),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=breeze_voice_design_log_handle,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
        process = breeze_voice_design_process
        process.stdin.write(json.dumps(request_payload, ensure_ascii=False) + "\n")
        process.stdin.flush()
        request_id = request_payload["id"]
        for line in process.stdout:
            if not line.startswith("TTS_STORY_BREEZE_RESULT "):
                continue
            response = json.loads(line[len("TTS_STORY_BREEZE_RESULT "):])
            if response.get("id") != request_id:
                continue
            if not response.get("success"):
                raise RuntimeError(response.get("error") or "Breeze voice-design worker failed")
            return response
        raise RuntimeError("Breeze voice-design worker stopped without returning a result.")


def _engine_signature(engine_name: str, config: Dict) -> str:
    if engine_name == "breeze_api":
        return "breeze_api::" + hashlib.sha256(json.dumps({k: v for k, v in config.items() if k.startswith("breeze_api_")}, sort_keys=True).encode()).hexdigest()
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
        )
        return f"{engine_name}::{'|'.join(parts)}"
    if engine_name == "qwen3_custom":
        parts = (
            (config.get("qwen3_custom_model_id") or "").strip(),
            (config.get("qwen3_custom_device") or "").strip(),
            (config.get("qwen3_custom_dtype") or "").strip(),
            (config.get("qwen3_custom_attn_implementation") or "").strip(),
            (config.get("qwen3_custom_default_language") or "").strip(),
            (config.get("qwen3_custom_default_instruct") or "").strip(),
        )
        return f"{engine_name}::{'|'.join(parts)}"
    if engine_name == "qwen3_clone":
        parts = (
            (config.get("qwen3_clone_model_id") or "").strip(),
            (config.get("qwen3_clone_device") or "").strip(),
            (config.get("qwen3_clone_dtype") or "").strip(),
            (config.get("qwen3_clone_attn_implementation") or "").strip(),
            (config.get("qwen3_clone_default_language") or "").strip(),
            (config.get("qwen3_clone_default_prompt") or "").strip(),
            (config.get("qwen3_clone_default_prompt_text") or "").strip(),
        )
        return f"{engine_name}::{'|'.join(parts)}"
    if engine_name == "omnivoice_clone":
        parts = (
            (config.get("omnivoice_clone_model_id") or "").strip(),
            (config.get("omnivoice_clone_device") or "").strip(),
            (config.get("omnivoice_clone_dtype") or "").strip(),
            str(config.get("omnivoice_clone_num_step") or 32),
            str(config.get("omnivoice_batch_size") or 1),
            (config.get("omnivoice_clone_default_prompt") or "").strip(),
            (config.get("omnivoice_clone_default_prompt_text") or "").strip(),
            str(config.get("omnivoice_post_process", True)),
            str(config.get("omnivoice_duration_safety_margin", 0.25)),
        )
        return f"{engine_name}::{'|'.join(parts)}"
    if engine_name == "omnivoice_design":
        parts = (
            (config.get("omnivoice_design_model_id") or "").strip(),
            (config.get("omnivoice_design_device") or "").strip(),
            (config.get("omnivoice_design_dtype") or "").strip(),
            str(config.get("omnivoice_design_num_step") or 32),
            (config.get("omnivoice_design_default_instruct") or "").strip(),
            str(config.get("omnivoice_post_process", True)),
            str(config.get("omnivoice_duration_safety_margin", 0.25)),
        )
        return f"{engine_name}::{'|'.join(parts)}"
    if engine_name == "audio8_tts":
        parts = tuple(str(config.get(key, "")) for key in (
            "audio8_tts_model_id", "audio8_tts_device", "audio8_tts_dtype",
            "audio8_tts_temperature", "audio8_tts_top_p", "audio8_tts_top_k",
            "audio8_tts_max_new_tokens", "audio8_tts_retry_max_new_tokens",
            "audio8_tts_seed", "audio8_tts_default_prompt", "audio8_tts_default_prompt_text",
            "audio8_tts_chunk_size", "audio8_tts_hard_chunk_size",
        ))
        return f"{engine_name}::{'|'.join(parts)}"
    if engine_name == "breeze_tts_2":
        parts = tuple(str(config.get(key, "")) for key in (
            "breeze_tts_2_runtime",
            "breeze_tts_2_model_id", "breeze_tts_2_device", "breeze_tts_2_seed",
            "breeze_tts_2_clone_cfg_scale", "breeze_tts_2_design_cfg_scale",
            "breeze_tts_2_direction_cfg_scale", "breeze_tts_2_max_new_tokens",
            "breeze_tts_2_max_seq_len", "breeze_tts_2_fast_mode",
            "breeze_tts_2_default_prompt", "breeze_tts_2_default_prompt_text",
            "breeze_tts_2_default_instruction", "breeze_tts_2_chunk_size",
        ))
        return f"{engine_name}::{'|'.join(parts)}"
    if engine_name == "dots_tts":
        parts = (
            (config.get("dots_tts_model_id") or "").strip(),
            (config.get("dots_tts_precision") or "").strip(),
            str(bool(config.get("dots_tts_optimize", False))),
            str(config.get("dots_tts_num_steps") or 10),
            str(config.get("dots_tts_guidance_scale") or 1.2),
            str(config.get("dots_tts_speaker_scale") or 1.5),
            str(config.get("dots_tts_seed")),
            (config.get("dots_tts_language") or "none").strip(),
            str(bool(config.get("dots_tts_normalize_text", False))),
            (config.get("dots_tts_device") or "auto").strip(),
            (config.get("dots_tts_default_prompt") or "").strip(),
            (config.get("dots_tts_default_prompt_text") or "").strip(),
            str(bool(config.get("dots_tts_allow_xvector_only", False))),
        )
        return f"{engine_name}::{'|'.join(parts)}"
    if engine_name in {"pocket_tts", "pocket_tts_preset"}:
        huggingface_token = (config.get("huggingface_token") or "").strip()
        parts = (
            (config.get("pocket_tts_model_variant") or "").strip(),
            str(config.get("pocket_tts_temp")),
            str(config.get("pocket_tts_lsd_decode_steps")),
            str(config.get("pocket_tts_noise_clamp")),
            str(config.get("pocket_tts_eos_threshold")),
            (config.get("pocket_tts_default_prompt") or "").strip(),
            str(bool(config.get("pocket_tts_prompt_truncate", False))),
            str(config.get("pocket_tts_num_threads")),
            str(config.get("pocket_tts_interop_threads")),
            hashlib.sha256(huggingface_token.encode("utf-8")).hexdigest()[:12]
            if huggingface_token else "no-hf-token",
        )
        return f"{engine_name}::{'|'.join(parts)}"
    if engine_name == "kokoro_replicate":
        parts = (
            (config.get("replicate_api_key") or "").strip(),
        )
        return f"{engine_name}::{'|'.join(parts)}"
    if engine_name == "azure_speech":
        parts = (
            (config.get("azure_speech_key") or "").strip(),
            (config.get("azure_speech_region") or "").strip().lower(),
            (config.get("azure_speech_output_format") or DEFAULT_AZURE_SPEECH_OUTPUT_FORMAT).strip(),
            str(config.get("azure_speech_timeout") or 60),
            str(config.get("azure_speech_max_parallel") or 2),
            str(config.get("azure_speech_requests_per_minute") or 0),
            (config.get("azure_speech_default_voice") or DEFAULT_AZURE_SPEECH_VOICE).strip(),
            (config.get("azure_speech_default_style") or "").strip(),
            (config.get("azure_speech_default_role") or "").strip(),
            str(config.get("azure_speech_default_style_degree") or 1.0),
        )
        return f"{engine_name}::{'|'.join(parts)}"
    if engine_name == "edge_tts":
        parts = (
            (config.get("edge_tts_default_voice") or DEFAULT_EDGE_TTS_VOICE).strip(),
            str(config.get("edge_tts_timeout") or 60),
            str(config.get("edge_tts_max_parallel") or 2),
            str(config.get("edge_tts_max_retries") if config.get("edge_tts_max_retries") is not None else 4),
            str(config.get("edge_tts_default_volume") or 0),
            str(config.get("pause_marker_three_seconds", 0.25)),
            str(config.get("pause_marker_six_seconds", 0.5)),
        )
        return f"{engine_name}::{'|'.join(parts)}"
    if engine_name == "elevenlabs":
        parts = (
            (config.get("elevenlabs_api_key") or "").strip(),
            (config.get("elevenlabs_base_url") or DEFAULT_ELEVENLABS_BASE_URL).strip(),
            (config.get("elevenlabs_model") or DEFAULT_ELEVENLABS_MODEL).strip(),
            (config.get("elevenlabs_default_voice") or DEFAULT_ELEVENLABS_VOICE).strip(),
            (config.get("elevenlabs_output_format") or DEFAULT_ELEVENLABS_OUTPUT_FORMAT).strip(),
            str(config.get("elevenlabs_timeout") or 120),
            str(config.get("elevenlabs_max_parallel") or 2),
            str(config.get("elevenlabs_stability") if config.get("elevenlabs_stability") is not None else 0.5),
            str(config.get("elevenlabs_similarity_boost") if config.get("elevenlabs_similarity_boost") is not None else 0.75),
            str(config.get("elevenlabs_style") if config.get("elevenlabs_style") is not None else 0.0),
            str(bool(config.get("elevenlabs_use_speaker_boost", True))),
        )
        return f"{engine_name}::{'|'.join(parts)}"
    if engine_name == "openai_tts":
        parts = (
            (config.get("openai_tts_api_key") or "").strip(),
            (config.get("openai_tts_base_url") or DEFAULT_OPENAI_TTS_BASE_URL).strip(),
            (config.get("openai_tts_model") or DEFAULT_OPENAI_TTS_MODEL).strip(),
            (config.get("openai_tts_default_voice") or DEFAULT_OPENAI_TTS_VOICE).strip(),
            (config.get("openai_tts_instructions") or "").strip(),
            str(config.get("openai_tts_timeout") or 120),
            str(config.get("openai_tts_max_parallel") or 2),
        )
        return f"{engine_name}::{'|'.join(parts)}"
    if engine_name == "localai_tts":
        parts = (
            (config.get("localai_tts_api_key") or "").strip(),
            (config.get("localai_tts_base_url") or DEFAULT_LOCALAI_TTS_BASE_URL).strip(),
            (config.get("localai_tts_model") or "").strip(),
            (config.get("localai_tts_default_voice") or "").strip(),
            (config.get("localai_tts_default_language") or "").strip(),
            (config.get("localai_tts_instructions") or "").strip(),
            str(config.get("localai_tts_timeout") or 180),
            str(config.get("localai_tts_max_parallel") or 1),
            str(config.get("localai_tts_max_retries") if config.get("localai_tts_max_retries") is not None else 4),
            str(bool(config.get("localai_tts_voice_profile_consent_confirmed", False))),
        )
        return f"{engine_name}::{'|'.join(parts)}"
    return engine_name


def _create_engine(engine_name: str, config: Dict) -> TtsEngineBase:
    if engine_name == "breeze_api":
        return BreezeAPIEngine(
            config.get("breeze_api_key", ""), model_id=config.get("breeze_api_model") or "breeze-tts-2",
            default_voice=config.get("breeze_api_default_voice") or "",
            instructions=config.get("breeze_api_instructions") or "",
            timeout=config.get("breeze_api_timeout", 180),
            max_parallel=config.get("breeze_api_max_parallel", 1),
            max_retries=config.get("breeze_api_max_retries", 2),
            guidance_scale=config.get("breeze_api_guidance_scale", 4),
            productions=BREEZE_PRODUCTIONS, production_progress=_breeze_production_progress)
    """Instantiate a specific engine with configuration-derived options."""
    config = config or {}
    if engine_name == "kokoro":
        if not isolated_engine_available("kokoro"):
            raise ImportError("Kokoro is not installed. Install it from Settings → Engine Settings.")
        device = config.get("device", "auto")
        logger.info("Creating Kokoro engine with device='%s'", device)
        engine = get_engine("kokoro", device=device)
        logger.info("Kokoro isolated engine proxy created for device='%s'", device)
        return engine

    if engine_name == "chatterbox_turbo_local":
        if not CHATTERBOX_TURBO_AVAILABLE:
            raise ImportError(
                "Chatterbox Turbo is unavailable: "
                f"{CHATTERBOX_TURBO_UNAVAILABLE_REASON or 'runtime import failed'}. "
                "Install or repair Chatterbox Local from Settings → Engine Settings."
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
        if not isolated_engine_available("voxcpm_local"):
            raise ImportError("VoxCPM is not installed. Install it from Settings → Engine Settings.")
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

    if engine_name == "qwen3_custom":
        if not isolated_engine_available("qwen3_custom"):
            raise ImportError("Qwen3-TTS is not installed. Install it from Settings → Engine Settings.")
        device = (config.get("qwen3_custom_device") or "auto").strip()
        return get_engine(
            "qwen3_custom",
            device=device or "auto",
            model_id=(config.get("qwen3_custom_model_id") or "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice").strip(),
            dtype=(config.get("qwen3_custom_dtype") or "bfloat16").strip(),
            attn_implementation=(config.get("qwen3_custom_attn_implementation") or "flash_attention_2").strip(),
            default_language=(config.get("qwen3_custom_default_language") or "Auto").strip() or "Auto",
            default_instruct=(config.get("qwen3_custom_default_instruct") or "").strip() or None,
        )

    if engine_name == "qwen3_clone":
        if not isolated_engine_available("qwen3_clone"):
            raise ImportError("Qwen3-TTS is not installed. Install it from Settings → Engine Settings.")
        device = (config.get("qwen3_clone_device") or "auto").strip()
        return get_engine(
            "qwen3_clone",
            device=device or "auto",
            model_id=(config.get("qwen3_clone_model_id") or "Qwen/Qwen3-TTS-12Hz-1.7B-Base").strip(),
            dtype=(config.get("qwen3_clone_dtype") or "bfloat16").strip(),
            attn_implementation=(config.get("qwen3_clone_attn_implementation") or "flash_attention_2").strip(),
            default_language=(config.get("qwen3_clone_default_language") or "Auto").strip() or "Auto",
            default_prompt=(config.get("qwen3_clone_default_prompt") or "").strip() or None,
            default_prompt_text=(config.get("qwen3_clone_default_prompt_text") or "").strip() or None,
        )

    if engine_name == "audio8_tts":
        if not isolated_engine_available("audio8_tts"):
            raise ImportError("Audio8 TTS is not installed. Install it from Settings → Engine Settings.")
        return get_engine(
            "audio8_tts",
            device=(config.get("audio8_tts_device") or "auto").strip(),
            model_id=(config.get("audio8_tts_model_id") or "Audio8/Audio8-TTS-Preview-0.6b").strip(),
            dtype=(config.get("audio8_tts_dtype") or "auto").strip(),
            temperature=float(config.get("audio8_tts_temperature") or 0.8),
            top_p=float(config.get("audio8_tts_top_p") or 0.95),
            top_k=int(config.get("audio8_tts_top_k") if config.get("audio8_tts_top_k") is not None else 50),
            max_new_tokens=int(config.get("audio8_tts_max_new_tokens") or 1024),
            retry_max_new_tokens=int(config.get("audio8_tts_retry_max_new_tokens") or 2000),
            max_input_chars=int(config.get("audio8_tts_hard_chunk_size") or 400),
            seed=int(config.get("audio8_tts_seed") if config.get("audio8_tts_seed") is not None else 42),
            default_prompt=(config.get("audio8_tts_default_prompt") or "").strip() or None,
            default_prompt_text=(config.get("audio8_tts_default_prompt_text") or "").strip() or None,
        )

    if engine_name == "breeze_tts_2":
        if not _breeze_runtime_ready(config):
            raise ImportError("The selected Breeze runtime is not installed. Install it in Settings → Breeze TTS 2, or select the installed runtime and save Settings.")
        license_marker = Path(__file__).resolve().parent / "engines" / "breeze_tts_2" / ".license_accepted"
        if not license_marker.is_file():
            raise PermissionError(
                "Breeze TTS 2 requires acceptance of its Research and Non-Commercial License in Settings."
            )
        return get_engine(
            "breeze_tts_2",
            runtime=config.get("breeze_tts_2_runtime") or "pytorch",
            device=(config.get("breeze_tts_2_device") or "auto").strip(),
            model_id=(config.get("breeze_tts_2_model_id") or "BreezeBlue/Breeze-TTS-2").strip(),
            seed=int(config.get("breeze_tts_2_seed") if config.get("breeze_tts_2_seed") is not None else 42),
            clone_cfg_scale=float(config.get("breeze_tts_2_clone_cfg_scale") or 1.0),
            design_cfg_scale=float(config.get("breeze_tts_2_design_cfg_scale") or 4.0),
            direction_cfg_scale=float(config.get("breeze_tts_2_direction_cfg_scale") or 4.0),
            max_new_tokens=int(config.get("breeze_tts_2_max_new_tokens") or 1500),
            max_seq_len=int(config.get("breeze_tts_2_max_seq_len") or 2048),
            fast_mode=bool(config.get("breeze_tts_2_fast_mode", False)),
            default_prompt=(config.get("breeze_tts_2_default_prompt") or "").strip() or None,
            default_prompt_text=(config.get("breeze_tts_2_default_prompt_text") or "").strip() or None,
            default_instruction=(config.get("breeze_tts_2_default_instruction") or "Speak clearly and naturally.").strip(),
        )

    if engine_name == "omnivoice_clone":
        if not omnivoice_available():
            raise ImportError(f"OmniVoice engine not available. {omnivoice_unavailable_reason()} Install OmniVoice from Settings.")
        return get_engine(
            "omnivoice_clone",
            device=(config.get("omnivoice_clone_device") or "auto").strip() or "auto",
            model_id=(config.get("omnivoice_clone_model_id") or "k2-fsa/OmniVoice").strip(),
            dtype=(config.get("omnivoice_clone_dtype") or "float16").strip(),
            num_step=int(config.get("omnivoice_clone_num_step") or 32),
            batch_size=int(config.get("omnivoice_batch_size") or 1),
            default_prompt=(config.get("omnivoice_clone_default_prompt") or "").strip() or None,
            default_prompt_text=(config.get("omnivoice_clone_default_prompt_text") or "").strip() or None,
            post_process=bool(config.get("omnivoice_post_process", True)),
            duration_safety_margin=float(config.get("omnivoice_duration_safety_margin", 0.25)),
        )

    if engine_name == "omnivoice_design":
        if not omnivoice_available():
            raise ImportError(f"OmniVoice design engine not available. {omnivoice_unavailable_reason()} Install OmniVoice from Settings.")
        return get_engine(
            "omnivoice_design",
            device=(config.get("omnivoice_design_device") or "auto").strip() or "auto",
            model_id=(config.get("omnivoice_design_model_id") or "k2-fsa/OmniVoice").strip(),
            dtype=(config.get("omnivoice_design_dtype") or "float16").strip(),
            num_step=int(config.get("omnivoice_design_num_step") or 32),
            default_instruct=(config.get("omnivoice_design_default_instruct") or "").strip() or None,
            post_process=bool(config.get("omnivoice_post_process", True)),
            duration_safety_margin=float(config.get("omnivoice_duration_safety_margin", 0.25)),
        )

    if engine_name == "dots_tts":
        if not DOTS_TTS_AVAILABLE:
            raise ImportError(
                f"Dot.TTS is not available: {DOTS_TTS_UNAVAILABLE_REASON} "
                "Please run setup.bat to set up the Dot.TTS isolated environment."
            )
        seed_value = config.get("dots_tts_seed", 42)
        return get_engine(
            "dots_tts",
            device=(config.get("dots_tts_device") or "auto").strip() or "auto",
            model_id=(config.get("dots_tts_model_id") or "rednote-hilab/dots.tts-soar").strip(),
            precision=(config.get("dots_tts_precision") or "auto").strip(),
            optimize=bool(config.get("dots_tts_optimize", False)),
            num_steps=int(config.get("dots_tts_num_steps") or 10),
            guidance_scale=float(config.get("dots_tts_guidance_scale") or 1.2),
            speaker_scale=float(config.get("dots_tts_speaker_scale") or 1.5),
            seed=None if seed_value in (None, "") else int(seed_value),
            language=(config.get("dots_tts_language") or "none").strip() or "none",
            normalize_text=bool(config.get("dots_tts_normalize_text", False)),
            default_prompt=(config.get("dots_tts_default_prompt") or "").strip() or None,
            default_prompt_text=(config.get("dots_tts_default_prompt_text") or "").strip() or None,
            allow_xvector_only=bool(config.get("dots_tts_allow_xvector_only", False)),
        )

    if engine_name in {"pocket_tts", "pocket_tts_preset"}:
        if not isolated_engine_available(engine_name):
            raise ImportError("Pocket TTS is not installed. Install it from Settings → Engine Settings.")
        return get_engine(
            "pocket_tts",
            environment={"HF_TOKEN": (config.get("huggingface_token") or "").strip()},
            device="cpu",
            model_variant=(config.get("pocket_tts_model_variant") or "b6369a24").strip(),
            temp=float(config.get("pocket_tts_temp") or 0.7),
            lsd_decode_steps=int(config.get("pocket_tts_lsd_decode_steps") or 1),
            noise_clamp=config.get("pocket_tts_noise_clamp"),
            eos_threshold=float(config.get("pocket_tts_eos_threshold") or -4.0),
            default_prompt=(config.get("pocket_tts_default_prompt") or "").strip() or None,
            prompt_truncate=bool(config.get("pocket_tts_prompt_truncate", False)),
            num_threads=config.get("pocket_tts_num_threads"),
            interop_threads=config.get("pocket_tts_interop_threads"),
        )

    if engine_name == "kitten_tts":
        if not isolated_engine_available("kitten_tts"):
            raise ImportError("KittenTTS is not installed. Install it from Settings → Engine Settings.")
        return get_engine(
            "kitten_tts",
            model_id=(config.get("kitten_tts_model_id") or KITTEN_TTS_DEFAULT_MODEL).strip(),
            default_voice=(config.get("kitten_tts_default_voice") or "Jasper").strip(),
        )

    if engine_name == "index_tts":
        if not INDEX_TTS_AVAILABLE:
            raise ImportError(
                f"IndexTTS is not available: {INDEX_TTS_UNAVAILABLE_REASON}"
            )
        device_raw = (config.get("index_tts_device") or "auto").strip().lower()
        device = None if device_raw in ("auto", "") else device_raw
        return get_engine(
            "index_tts",
            model_version=(config.get("index_tts_model_version") or "IndexTTS-2").strip(),
            use_fp16=bool(config.get("index_tts_use_fp16", False)),
            use_deepspeed=bool(config.get("index_tts_use_deepspeed", False)),
            use_torch_compile=bool(config.get("index_tts_use_torch_compile", False)),
            use_accel=bool(config.get("index_tts_use_accel", False)),
            num_beams=int(config.get("index_tts_num_beams", 1)),
            diffusion_steps=int(config.get("index_tts_diffusion_steps", 12)),
            temperature=float(config.get("index_tts_temperature", 0.8)),
            top_p=float(config.get("index_tts_top_p", 0.8)),
            top_k=int(config.get("index_tts_top_k", 30)),
            repetition_penalty=float(config.get("index_tts_repetition_penalty", 10.0)),
            max_mel_tokens=int(config.get("index_tts_max_mel_tokens", 1500)),
            max_text_tokens_per_segment=int(config.get("index_tts_max_text_tokens_per_segment", 120)),
            device=device,
            default_prompt=(config.get("index_tts_default_prompt") or "").strip() or None,
        )

    if engine_name == "azure_speech":
        api_key = (config.get("azure_speech_key") or "").strip()
        region = (config.get("azure_speech_region") or "").strip()
        if not api_key:
            raise ValueError("Azure Speech resource key is required. Configure it in Azure Speech settings.")
        if not region:
            raise ValueError("Azure Speech region is required. Configure it in Azure Speech settings.")
        return get_engine(
            "azure_speech",
            subscription_key=api_key,
            region=region,
            output_format=(
                config.get("azure_speech_output_format") or DEFAULT_AZURE_SPEECH_OUTPUT_FORMAT
            ).strip(),
            timeout=int(config.get("azure_speech_timeout") or 60),
            max_parallel=int(config.get("azure_speech_max_parallel") or 2),
            requests_per_minute=int(
                config.get("azure_speech_requests_per_minute")
                if config.get("azure_speech_requests_per_minute") is not None
                else DEFAULT_AZURE_SPEECH_REQUESTS_PER_MINUTE
            ),
            default_voice=(
                config.get("azure_speech_default_voice") or DEFAULT_AZURE_SPEECH_VOICE
            ).strip(),
            default_style=(config.get("azure_speech_default_style") or "").strip(),
            default_role=(config.get("azure_speech_default_role") or "").strip(),
            default_style_degree=float(config.get("azure_speech_default_style_degree") or 1.0),
        )

    if engine_name == "edge_tts":
        if not isolated_engine_available("edge_tts"):
            raise ImportError(
                "Edge TTS is unavailable: "
                "edge-tts is not installed. Install it from Settings → Engine Settings."
            )
        return get_engine(
            "edge_tts",
            default_voice=(config.get("edge_tts_default_voice") or DEFAULT_EDGE_TTS_VOICE).strip(),
            timeout=int(config.get("edge_tts_timeout") or 60),
            max_parallel=int(config.get("edge_tts_max_parallel") or 2),
            max_retries=int(
                config.get("edge_tts_max_retries")
                if config.get("edge_tts_max_retries") is not None
                else 4
            ),
            default_volume=int(config.get("edge_tts_default_volume") or 0),
            pause_marker_three_seconds=float(config.get("pause_marker_three_seconds", 0.25)),
            pause_marker_six_seconds=float(config.get("pause_marker_six_seconds", 0.5)),
        )

    if engine_name == "elevenlabs":
        api_key = (config.get("elevenlabs_api_key") or "").strip()
        if not api_key:
            raise ValueError("An ElevenLabs API key is required. Configure it in ElevenLabs settings.")
        return get_engine(
            "elevenlabs",
            api_key=api_key,
            base_url=(config.get("elevenlabs_base_url") or DEFAULT_ELEVENLABS_BASE_URL).strip(),
            model_id=(config.get("elevenlabs_model") or DEFAULT_ELEVENLABS_MODEL).strip(),
            default_voice=(config.get("elevenlabs_default_voice") or DEFAULT_ELEVENLABS_VOICE).strip(),
            output_format=(
                config.get("elevenlabs_output_format") or DEFAULT_ELEVENLABS_OUTPUT_FORMAT
            ).strip(),
            timeout=int(config.get("elevenlabs_timeout") or 120),
            max_parallel=int(config.get("elevenlabs_max_parallel") or 2),
            stability=float(
                config.get("elevenlabs_stability")
                if config.get("elevenlabs_stability") is not None else 0.5
            ),
            similarity_boost=float(
                config.get("elevenlabs_similarity_boost")
                if config.get("elevenlabs_similarity_boost") is not None else 0.75
            ),
            style=float(
                config.get("elevenlabs_style")
                if config.get("elevenlabs_style") is not None else 0.0
            ),
            use_speaker_boost=bool(config.get("elevenlabs_use_speaker_boost", True)),
        )

    if engine_name == "openai_tts":
        base_url = (config.get("openai_tts_base_url") or DEFAULT_OPENAI_TTS_BASE_URL).strip()
        api_key = (config.get("openai_tts_api_key") or "").strip()
        if "api.openai.com" in base_url.lower() and not api_key:
            raise ValueError("An OpenAI API key is required for the official OpenAI TTS endpoint.")
        return get_engine(
            "openai_tts",
            api_key=api_key,
            base_url=base_url,
            model_id=(config.get("openai_tts_model") or DEFAULT_OPENAI_TTS_MODEL).strip(),
            default_voice=(config.get("openai_tts_default_voice") or DEFAULT_OPENAI_TTS_VOICE).strip(),
            instructions=(config.get("openai_tts_instructions") or "").strip(),
            timeout=int(config.get("openai_tts_timeout") or 120),
            max_parallel=int(config.get("openai_tts_max_parallel") or 2),
        )

    if engine_name == "localai_tts":
        model_id = (config.get("localai_tts_model") or "").strip()
        if not model_id:
            raise ValueError("Select a LocalAI TTS model in Settings and save before generating audio.")
        api_key = (config.get("localai_tts_api_key") or "").strip()
        base_url = (config.get("localai_tts_base_url") or DEFAULT_LOCALAI_TTS_BASE_URL).strip()
        profile_manager = LocalAIVoiceProfileManager(
            base_url,
            api_key,
            consent_confirmed=bool(
                config.get("localai_tts_voice_profile_consent_confirmed", False)
            ),
            timeout=int(config.get("localai_tts_timeout") or 180),
        )
        return get_engine(
            "localai_tts",
            api_key=api_key,
            base_url=base_url,
            model_id=model_id,
            default_voice=(config.get("localai_tts_default_voice") or "").strip(),
            default_language=(config.get("localai_tts_default_language") or "").strip(),
            instructions=(config.get("localai_tts_instructions") or "").strip(),
            timeout=int(config.get("localai_tts_timeout") or 180),
            max_parallel=int(config.get("localai_tts_max_parallel") or 1),
            max_retries=int(config.get("localai_tts_max_retries") if config.get("localai_tts_max_retries") is not None else 4),
            voice_resolver=profile_manager.resolve,
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
    config = _hydrate_config_secrets(config or load_config())
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


def slugify_filename(value: str, default: str = "chapter", max_length: int = 60) -> str:
    """Create a filesystem-friendly slug."""
    if not value:
        return default
    value = re.sub(r'[^A-Za-z0-9]+', '-', value)
    value = re.sub(r'-{2,}', '-', value).strip('-')
    if max_length and len(value) > max_length:
        value = value[:max_length].rstrip('-')
    return value or default


def _build_sections_from_matches(
    text: str,
    matches: List[re.Match],
    default_label: str,
    base_offset: int = 0
) -> List[Dict[str, Any]]:
    sections: List[Dict[str, Any]] = []
    if not matches:
        clean_text = text.strip()
        if clean_text:
            sections.append({"title": "Full Story", "content": clean_text})
        return sections

    # A delivery instruction belongs to the heading's speaker, not to the
    # preceding section. Regex matches may start at [/direction] or [narrator],
    # so normalize boundaries before slicing either adjacent section.
    boundaries = []
    for match in matches:
        start = match.start()
        prefix = re.match(r'(?:\s*\[/[a-zA-Z0-9_\-]+\]\s*)+', text[start:])
        if prefix:
            start += prefix.end()
        opening = re.search(r'\[([a-zA-Z0-9_\-]+)\]\s*$', text[:start])
        if opening:
            start = opening.start()
        instruction = re.search(
            r'\[(direction|emotion)\](?:(?!\[/?(?:direction|emotion)\]).)*'
            r'\[/\1\]\s*$', text[:start], re.DOTALL | re.IGNORECASE,
        )
        if instruction:
            start = instruction.start()
        boundaries.append(start)

    first_start = boundaries[0]
    if first_start > 0:
        pre_content = text[:first_start].strip()
        if pre_content:
            # Create a "Title" section for content before the first heading.
            # Only do this if the first match is not at the very start (position 0),
            # to allow custom headings at the beginning to be detected.
            sections.append({"title": "Title", "content": pre_content})

    # Matches a closing speaker tag at the very start of a string (possibly after whitespace)
    _leading_close_tag_re = re.compile(r'^(\s*\[/([a-zA-Z0-9_\-]+)\])', re.DOTALL)
    _leading_close_tags_re = re.compile(r'^(?:\s*\[/[a-zA-Z0-9_\-]+\]\s*)+', re.DOTALL)
    # Matches a lone opening speaker tag on its own line immediately before a heading
    _lone_open_tag_re = re.compile(r'\[([a-zA-Z0-9_\-]+)\]\s*$')

    for idx, match in enumerate(matches):
        start = boundaries[idx]
        raw_end = boundaries[idx + 1] if idx + 1 < len(matches) else len(text)

        # The chapter-heading regex allows optional tag prefixes like [/narrator]\n\n[narrator]
        # before the heading keyword. When the next match begins with a closing speaker tag
        # (e.g. "[/narrator]\n\n[narrator]\nCHAPTER IX"), that closing tag actually belongs
        # to the CURRENT chapter's content — extend end to include it.
        next_chunk = text[raw_end:]
        close_prefix = _leading_close_tag_re.match(next_chunk)
        if close_prefix:
            end = raw_end + len(close_prefix.group(1))
        else:
            end = raw_end

        # If there is a lone speaker-tag opening on the line(s) immediately before
        # the heading, include it so the content slice has a balanced open+close pair.
        # This handles patterns like:
        #   [narrator]
        #   CHAPTER VIII          <- match.start() is here
        #   ...prose...
        #   [/narrator]
        preceding = text[:start]
        preceding_stripped = preceding.rstrip('\r\n ')
        last_newline = preceding_stripped.rfind('\n')
        preceding_line = preceding_stripped[last_newline + 1:] if last_newline >= 0 else preceding_stripped
        if _lone_open_tag_re.match(preceding_line.strip()):
            # Rewind start to the beginning of that opening-tag line
            start = len(preceding_stripped) - len(preceding_line.lstrip())

        leading_close_tags = _leading_close_tags_re.match(text[start:end])
        if leading_close_tags:
            start += leading_close_tags.end()

        content = text[start:end].strip()
        if not content:
            continue
        heading_raw = (match.group(0) or "").strip()
        title = _clean_heading_text(match.group(1) or '')
        sections.append({
            "title": title or f"{default_label} {idx + 1}",
            "content": content,
            "heading": heading_raw,
            "heading_start": match.start() + base_offset,
            "heading_end": match.end() + base_offset,
        })

    return sections


def split_text_into_sections(text: str, section_headings: Optional[Any] = None) -> List[Dict[str, str]]:
    """
    Split text into logical sections (book/chapter/section/letter/part).

    ``Book`` is a section-heading label, not a separate hierarchy.  Treating
    headings such as "Book 1" as top-level collections caused ordinary works
    divided into books (for example, The Odyssey) to be exported as many
    unrelated books containing generic "Full Book" chapters.
    """
    section_pattern = _build_section_heading_pattern(section_headings)
    section_matches = list(section_pattern.finditer(text))
    if section_matches:
        return _build_sections_from_matches(text, section_matches, "Section")

    clean_text = text.strip()
    return [{"title": "Full Story", "content": clean_text}] if clean_text else []


def split_text_into_book_sections(text: str, section_headings: Optional[Any] = None) -> Dict[str, Any]:
    """Return a flat section structure with legacy-compatible result keys."""
    section_pattern = _build_section_heading_pattern(section_headings)
    section_matches = list(section_pattern.finditer(text))
    if section_matches:
        sections = _build_sections_from_matches(text, section_matches, "Section")
        return {"kind": "section", "books": [], "sections": sections}

    clean_text = text.strip()
    sections = [{"title": "Full Story", "content": clean_text}] if clean_text else []
    return {"kind": "none", "books": [], "sections": sections}


def _resolve_llm_chunk_size(config: Dict[str, Any]) -> int:
    provider = (config.get("llm_provider") or DEFAULT_LLM_PROVIDER).lower().strip()
    key = "llm_gemini_chunk_size" if provider == "gemini" else "llm_local_chunk_size"
    raw_value = config.get(key, 500)
    try:
        resolved = int(raw_value)
    except (TypeError, ValueError):
        resolved = 500
    return max(50, resolved)


def _resolve_llm_chunk_chapters(config: Dict[str, Any]) -> bool:
    provider = (config.get("llm_provider") or DEFAULT_LLM_PROVIDER).lower().strip()
    key = "llm_gemini_chunk_chapters" if provider == "gemini" else "llm_local_chunk_chapters"
    return bool(config.get(key, True))


def _chunk_text_by_paragraph_words(text: str, max_words: int) -> List[str]:
    content = (text or "").strip()
    if not content:
        return []
    try:
        max_words = int(max_words)
    except (TypeError, ValueError):
        max_words = 500
    max_words = max(50, max_words)
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n+", content) if part.strip()]
    if not paragraphs:
        return [content]

    chunks: List[str] = []
    current_parts: List[str] = []
    current_words = 0

    for paragraph in paragraphs:
        paragraph_words = len(paragraph.split())
        if not current_parts:
            current_parts = [paragraph]
            current_words = paragraph_words
            continue

        if current_words >= max_words:
            chunks.append("\n\n".join(current_parts).strip())
            current_parts = [paragraph]
            current_words = paragraph_words
            continue

        if current_words + paragraph_words > max_words:
            current_parts.append(paragraph)
            chunks.append("\n\n".join(current_parts).strip())
            current_parts = []
            current_words = 0
            continue

        current_parts.append(paragraph)
        current_words += paragraph_words

    if current_parts:
        chunks.append("\n\n".join(current_parts).strip())
    return chunks


def _append_llm_chunks(
    sections: List[Dict[str, Any]],
    content: str,
    title: Optional[str],
    source: str,
    max_words: int,
) -> None:
    clean_content = (content or "").strip()
    if not clean_content:
        return
    chunks = _chunk_text_by_paragraph_words(clean_content, max_words)
    if not chunks:
        chunks = [clean_content]
    if len(chunks) == 1:
        sections.append({
            "title": title,
            "content": chunks[0],
            "source": source,
        })
        return
    for idx, chunk in enumerate(chunks):
        sections.append({
            "title": title if idx == 0 else None,
            "content": chunk,
            "source": source,
        })


def build_gemini_sections(text: str, prefer_chapters: bool, config: dict, section_headings: Optional[Any] = None):
    """Create sections for configured LLM processing based on detected sections or chunks."""
    sections = []
    if not text:
        return sections

    llm_chunk_size = _resolve_llm_chunk_size(config)
    llm_chunk_chapters = _resolve_llm_chunk_chapters(config)

    hierarchy = split_text_into_book_sections(text, section_headings) if prefer_chapters else None
    book_matches = (hierarchy or {}).get("books") or []
    section_matches = (hierarchy or {}).get("sections") or []

    if prefer_chapters and book_matches:
        for book_idx, book in enumerate(hierarchy.get("books") or [], start=1):
            book_title = (book.get("title") or f"Book {book_idx}").strip()
            for chapter in book.get("chapters") or []:
                chapter_title = (chapter.get("title") or "").strip()
                title = f"{book_title} — {chapter_title}".strip(" —") if chapter_title else book_title
                if llm_chunk_chapters:
                    _append_llm_chunks(
                        sections,
                        chapter.get("content") or "",
                        title,
                        "section",
                        llm_chunk_size,
                    )
                else:
                    sections.append({
                        "title": title,
                        "content": (chapter.get("content") or "").strip(),
                        "source": "section",
                    })
    elif prefer_chapters and section_matches:
        for chapter in hierarchy.get("sections") or []:
            if llm_chunk_chapters:
                _append_llm_chunks(
                    sections,
                    chapter.get("content") or "",
                    chapter.get("title"),
                    "section",
                    llm_chunk_size,
                )
            else:
                sections.append({
                    "title": chapter.get("title"),
                    "content": (chapter.get("content") or "").strip(),
                    "source": "section",
                })
    elif prefer_chapters:
        clean_text = text.strip()
        if clean_text:
            if llm_chunk_chapters:
                chunks = _chunk_text_by_paragraph_words(clean_text, llm_chunk_size)
                if not chunks:
                    chunks = [clean_text]
                if len(chunks) == 1:
                    sections.append({
                        "title": "Full Story",
                        "content": chunks[0],
                        "source": "full"
                    })
                else:
                    for chunk in chunks:
                        sections.append({
                            "title": None,
                            "content": chunk,
                            "source": "chunk"
                        })
            else:
                sections.append({
                    "title": "Full Story",
                    "content": clean_text,
                    "source": "full"
                })
    else:
        chunks = _chunk_text_by_paragraph_words(text, llm_chunk_size)
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
    """Build a section prompt for the configured LLM, with optional speaker memory."""
    parts = []
    if prompt_prefix:
        parts.append(prompt_prefix.strip())

    speakers = [s for s in (known_speakers or []) if s]
    if speakers:
        speaker_line = (
            "Known speaker tags so far (use these exact tags when they apply; "
            "only introduce a new tag if the speaker is truly new): "
            + ", ".join(speakers)
        )
        parts.append(speaker_line)

    content = (section.get("content") or "").strip()
    if content:
        parts.append(content)
    return "\n\n".join(parts).strip()


class LLMProviderChainError(RuntimeError):
    """Raised when every eligible provider in the configured chain fails."""

    def __init__(self, message: str, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = bool(retryable)


class LLMProfileRetryError(LLMProviderChainError):
    """Ask the section client to retry one profile before advancing."""

    def __init__(
        self,
        message: str,
        *,
        current_profile: Dict[str, Any],
        next_profile: Optional[Dict[str, Any]] = None,
        failures: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        super().__init__(message, retryable=True)
        self.current_profile = _public_llm_profile(current_profile)
        self.next_profile = _public_llm_profile(next_profile) if next_profile else None
        self.failures = list(failures or [])


def _default_llm_model_for_provider(config: Dict[str, Any], provider: str) -> str:
    model_keys = {
        "gemini": "gemini_model",
        "atlas": "atlas_cloud_model",
        "openrouter": "openrouter_model",
        "local": "llm_local_model",
    }
    return str(config.get(model_keys.get(provider, "")) or "").strip()


def _default_llm_api_key_for_provider(config: Dict[str, Any], provider: str) -> str:
    key_names = {
        "gemini": "gemini_api_key",
        "atlas": "atlas_cloud_api_key",
        "openrouter": "openrouter_api_key",
        "local": "llm_local_api_key",
    }
    return str(config.get(key_names.get(provider, "")) or "").strip()


def _coerce_llm_daily_request_limit(value: Any, default: int = 18) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = int(default)
    return max(0, min(parsed, 1000000))


def _resolve_llm_profile_chain(config: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return the primary profile followed by any configured backup profiles."""
    primary_provider = str(
        config.get("llm_provider") or DEFAULT_LLM_PROVIDER
    ).lower().strip()
    if primary_provider not in SUPPORTED_LLM_PROVIDERS:
        raise LLMProviderChainError(f"Unsupported LLM provider: {primary_provider}")

    profiles: List[Dict[str, str]] = [{
        "id": "primary",
        "name": "Primary",
        "provider": primary_provider,
        "model": _default_llm_model_for_provider(config, primary_provider),
        "api_key": "",
        "daily_request_limit": 0,
    }]
    raw_backups = config.get("llm_backup_profiles") or []
    if not isinstance(raw_backups, list):
        raise LLMProviderChainError("LLM backup profiles must be a list")

    seen_ids = {"primary"}
    primary_key = _default_llm_api_key_for_provider(config, primary_provider)
    seen_targets = {(profiles[0]["provider"], profiles[0]["model"], primary_key)}
    for index, raw_profile in enumerate(raw_backups, start=1):
        if not isinstance(raw_profile, dict):
            continue
        provider = str(raw_profile.get("provider") or "").lower().strip()
        if not provider:
            continue
        if provider not in SUPPORTED_LLM_PROVIDERS:
            raise LLMProviderChainError(f"Unsupported LLM provider: {provider}")
        model = str(raw_profile.get("model") or "").strip()
        api_key = str(raw_profile.get("api_key") or "").strip()
        resolved_model = model or _default_llm_model_for_provider(config, provider)
        target = (
            provider,
            resolved_model,
            api_key or _default_llm_api_key_for_provider(config, provider),
        )
        if target in seen_targets:
            continue
        profile_id = re.sub(
            r"[^a-zA-Z0-9_-]",
            "-",
            str(raw_profile.get("id") or f"backup-{index}").strip(),
        ).strip("-") or f"backup-{index}"
        if profile_id in seen_ids:
            profile_id = f"{profile_id}-{index}"
        name = str(raw_profile.get("name") or f"Backup {index}").strip()
        profiles.append({
            "id": profile_id,
            "name": name or f"Backup {index}",
            "provider": provider,
            "model": resolved_model,
            "api_key": api_key,
            "daily_request_limit": _coerce_llm_daily_request_limit(
                raw_profile.get("daily_request_limit"),
                18,
            ),
        })
        seen_ids.add(profile_id)
        seen_targets.add(target)
    return profiles


def _public_llm_profile(profile: Dict[str, Any]) -> Dict[str, Any]:
    """Return profile status without ever exposing its API key."""
    return {
        "id": profile.get("id") or "",
        "name": profile.get("name") or "",
        "provider": profile.get("provider") or "",
        "model": profile.get("model") or "",
        "daily_request_limit": int(profile.get("daily_request_limit") or 0),
    }


def _llm_usage_day_key(now: Optional[datetime] = None) -> str:
    """Return the current usage day using Gemini's Pacific-time boundary."""
    pacific = ZoneInfo("America/Los_Angeles")
    current = now or datetime.now(tz=pacific)
    if current.tzinfo is None:
        current = current.replace(tzinfo=pacific)
    else:
        current = current.astimezone(pacific)
    return current.date().isoformat()


def _load_llm_profile_usage(day_key: str) -> Dict[str, Any]:
    try:
        payload = json.loads(LLM_PROFILE_USAGE_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        payload = {}
    if payload.get("pacific_date") != day_key or not isinstance(payload.get("profiles"), dict):
        return {"pacific_date": day_key, "profiles": {}}
    return payload


def _reserve_llm_profile_request(profile: Dict[str, Any]) -> tuple[bool, int, int]:
    """Atomically reserve one provider request under a profile's daily cap."""
    limit = _coerce_llm_daily_request_limit(profile.get("daily_request_limit"), 0)
    if limit == 0:
        return True, 0, 0
    profile_id = str(profile.get("id") or "").strip()
    if not profile_id:
        return True, 0, limit
    day_key = _llm_usage_day_key()
    with LLM_PROFILE_USAGE_LOCK:
        payload = _load_llm_profile_usage(day_key)
        profiles = payload["profiles"]
        used = max(0, int(profiles.get(profile_id) or 0))
        if used >= limit:
            return False, used, limit
        used += 1
        profiles[profile_id] = used
        write_json_atomic(LLM_PROFILE_USAGE_FILE, payload)
        return True, used, limit


def _is_retryable_llm_error(exc: Exception) -> bool:
    """Identify provider availability/rate errors that may use a backup."""
    message = str(exc or "").lower()
    status_match = re.search(r"(?:http|error)\s*\(?\s*(\d{3})", message)
    if status_match:
        status_code = int(status_match.group(1))
        if status_code in (408, 409, 425, 429) or status_code >= 500:
            return True
        if 400 <= status_code < 500:
            return False

    non_retryable_markers = (
        "api key is required",
        "api key not configured",
        "model is required",
        "model name is required",
        "base url is required",
        "prompt must not be empty",
        "unsupported llm provider",
        "unsupported local llm provider",
    )
    if any(marker in message for marker in non_retryable_markers):
        return False

    retryable_markers = (
        "429",
        "quota",
        "rate limit",
        "rate_limit",
        "resource_exhausted",
        "unavailable",
        "overloaded",
        "high demand",
        "timed out",
        "timeout",
        "connection",
        "network",
        "temporarily",
        "try again",
        "502",
        "503",
        "504",
    )
    return any(marker in message for marker in retryable_markers)


def _llm_error_action(exc: Exception) -> str:
    """Return stop, retry_profile, or advance_profile for a provider failure."""
    if getattr(exc, 'retries_exhausted', False):
        # OpenRouter already performed its bounded retries; do not multiply
        # them by the browser's per-section retry loop before failover.
        return "advance_profile"
    if not _is_retryable_llm_error(exc):
        return "stop"
    message = str(exc or "").lower()
    high_demand_markers = (
        "high demand",
        "overloaded",
    )
    if any(marker in message for marker in high_demand_markers):
        return "retry_profile"
    quota_markers = (
        "quota exceeded",
        "exceeded your current quota",
        "resource_exhausted",
        "resource exhausted",
        "insufficient quota",
        "requests per day",
        "daily request limit",
    )
    if any(marker in message for marker in quota_markers):
        return "advance_profile"
    transient_capacity_markers = (
        "temporarily unavailable",
        "service unavailable",
        "unavailable",
        "try again",
        "timed out",
        "timeout",
        "connection",
        "network",
        "502",
        "503",
        "504",
    )
    if any(marker in message for marker in transient_capacity_markers):
        return "retry_profile"
    if "429" in message or "rate limit" in message or "rate_limit" in message:
        return "retry_profile"
    return "retry_profile"


def _run_llm_prompt_for_provider(
    prompt: str,
    config: Dict[str, Any],
    provider: str,
    model_override: Optional[str] = None,
    api_key_override: Optional[str] = None,
    response_schema=None,
    response_schema_name=None,
    response_schema_strict=True,
    before_retry=None,
) -> str:
    """Run one prompt through one explicitly selected provider."""
    model_override = str(model_override or "").strip()
    api_key_override = str(api_key_override or "").strip()
    if response_schema is not None:
        from src.structured_output import validate_schema, StructuredOutputError
        validate_schema(response_schema, response_schema_name, response_schema_strict)
        if provider != "openrouter":
            raise StructuredOutputError(
                f"Provider '{provider}' does not support this structured-output path; "
                "choose an OpenRouter profile. The schema was not dropped.")
    if provider == "gemini":
        api_key = api_key_override or (config.get("gemini_api_key") or "").strip()
        if not api_key:
            raise GeminiProcessorError("Gemini API key not configured")
        model_name = model_override or config.get("gemini_model") or DEFAULT_GEMINI_MODEL
        processor = GeminiProcessor(api_key=api_key, model_name=model_name)
        return processor.generate_text(prompt)

    if provider == "atlas":
        api_key = api_key_override or (config.get("atlas_cloud_api_key") or "").strip()
        if not api_key:
            raise AtlasCloudProcessorError("Atlas Cloud API key not configured")
        processor = AtlasCloudProcessor(
            api_key=api_key,
            base_url=(config.get("atlas_cloud_base_url") or DEFAULT_ATLAS_CLOUD_BASE_URL),
            model_name=(model_override or config.get("atlas_cloud_model") or DEFAULT_ATLAS_CLOUD_MODEL),
            timeout=int(config.get("atlas_cloud_timeout") or 120),
            temperature=config.get("llm_local_temperature"),
            top_p=config.get("llm_local_top_p"),
            top_k=config.get("llm_local_top_k"),
            repetition_penalty=config.get("llm_local_repeat_penalty"),
            max_tokens=config.get("llm_local_max_tokens"),
            disable_reasoning=bool(config.get("llm_local_disable_reasoning", False)),
        )
        return processor.generate_text(prompt)

    if provider == "openrouter":
        api_key = api_key_override or (config.get("openrouter_api_key") or "").strip()
        if not api_key:
            raise OpenRouterProcessorError("OpenRouter API key not configured")
        processor = OpenRouterProcessor(
            api_key=api_key,
            base_url=(config.get("openrouter_base_url") or DEFAULT_OPENROUTER_BASE_URL),
            model_name=(model_override or config.get("openrouter_model") or DEFAULT_OPENROUTER_MODEL),
            timeout=int(config.get("openrouter_timeout") or 120),
            temperature=config.get("llm_local_temperature"),
            top_p=config.get("llm_local_top_p"),
            top_k=config.get("llm_local_top_k"),
            repetition_penalty=config.get("llm_local_repeat_penalty"),
            max_tokens=config.get("llm_local_max_tokens"),
            disable_reasoning=bool(config.get("llm_local_disable_reasoning", False)),
            before_retry=before_retry,
        )
        if response_schema is not None:
            return processor.generate_text(
                prompt, response_schema=response_schema,
                response_schema_name=response_schema_name,
                response_schema_strict=response_schema_strict)
        return processor.generate_text(prompt)

    if provider != "local":
        raise LocalLLMProcessorError(f"Unsupported LLM provider: {provider}")

    local_provider = (config.get("llm_local_provider") or "").lower().strip()
    base_url = (config.get("llm_local_base_url") or "").strip()
    model_name = model_override or (config.get("llm_local_model") or "").strip()
    api_key = api_key_override or (config.get("llm_local_api_key") or "").strip()
    timeout = int(config.get("llm_local_timeout") or 120)
    temperature = config.get("llm_local_temperature")
    top_p = config.get("llm_local_top_p")
    top_k = config.get("llm_local_top_k")
    repeat_penalty = config.get("llm_local_repeat_penalty")
    max_tokens = config.get("llm_local_max_tokens")
    disable_reasoning = bool(config.get("llm_local_disable_reasoning", False))

    processor = LocalLLMProcessor(
        provider=local_provider,
        base_url=base_url,
        model_name=model_name,
        api_key=api_key,
        timeout=timeout,
        temperature=temperature,
        top_p=top_p,
        top_k=top_k,
        repeat_penalty=repeat_penalty,
        max_tokens=max_tokens,
        disable_reasoning=disable_reasoning,
    )
    return processor.generate_text(prompt)


def _run_llm_prompt_with_failover(
    prompt: str,
    config: Dict[str, Any],
    preferred_profile: Optional[str] = None,
    defer_transient_failover: bool = False,
    response_schema=None,
    response_schema_name=None,
    response_schema_strict=True,
) -> tuple[str, Dict[str, Any], List[Dict[str, Any]]]:
    """Run a prompt through the configured profile chain.

    A preferred profile is used by multi-section prep after failover so every
    later section does not repeatedly consume time against a provider already
    known to be unavailable for that run.
    """
    structured_options = {}
    if response_schema is not None:
        from src.structured_output import validate_schema
        validate_schema(response_schema, response_schema_name, response_schema_strict)
        structured_options = dict(response_schema=response_schema,
                                  response_schema_name=response_schema_name,
                                  response_schema_strict=response_schema_strict)
    profiles = _resolve_llm_profile_chain(config)
    preferred = str(preferred_profile or "").strip()
    preferred_index = next(
        (index for index, profile in enumerate(profiles) if profile["id"] == preferred),
        None,
    )
    if preferred_index is not None:
        profiles = profiles[preferred_index:]

    failures: List[Dict[str, Any]] = []
    for index, profile in enumerate(profiles):
        provider = profile["provider"]
        if response_schema is not None and provider != "openrouter":
            failures.append({
                "profile_id": profile["id"], "profile_name": profile["name"],
                "provider": provider, "model": profile.get("model") or "",
                "error": "Profile cannot honor the requested JSON schema; skipped without an API request",
                "failure_kind": "unsupported_structured_output",
            })
            continue
        allowed, used, limit = _reserve_llm_profile_request(profile)
        if not allowed:
            failures.append({
                "profile_id": profile["id"],
                "profile_name": profile["name"],
                "provider": provider,
                "model": profile.get("model") or "",
                "error": (
                    f"Daily request limit reached ({used}/{limit}); "
                    "the counter resets at midnight Pacific Time"
                ),
                "failure_kind": "daily_limit",
            })
            if index + 1 < len(profiles):
                logger.info(
                    "LLM profile %s reached its daily request limit; trying backup %s",
                    profile["name"],
                    profiles[index + 1]["name"],
                )
                continue
            summary = "; ".join(
                f"{entry['profile_name']}: {entry['error']}" for entry in failures
            )
            raise LLMProviderChainError(
                f"LLM provider chain stopped ({summary})",
                retryable=False,
            )
        def reserve_retry():
            retry_allowed, retry_used, retry_limit = _reserve_llm_profile_request(profile)
            if not retry_allowed:
                limit_error = OpenRouterProcessorError(
                    f"Daily request limit reached ({retry_used}/{retry_limit}); retry was not submitted")
                limit_error.retries_exhausted = True
                raise limit_error

        retry_options = {'before_retry': reserve_retry} if provider == 'openrouter' else {}
        try:
            result = _run_llm_prompt_for_provider(
                prompt,
                config,
                provider,
                model_override=profile.get("model"),
                api_key_override=profile.get("api_key"),
                **structured_options,
                **retry_options,
            )
            return result, _public_llm_profile(profile), failures
        except (GeminiProcessorError, LocalLLMProcessorError, AtlasCloudProcessorError, OpenRouterProcessorError) as exc:
            action = _llm_error_action(exc)
            failures.append({
                "profile_id": profile["id"],
                "profile_name": profile["name"],
                "provider": provider,
                "model": profile.get("model") or "",
                "error": str(exc),
                "failure_kind": action,
            })
            has_backup = index + 1 < len(profiles)
            if action == "retry_profile" and defer_transient_failover:
                raise LLMProfileRetryError(
                    str(exc),
                    current_profile=profile,
                    next_profile=profiles[index + 1] if has_backup else None,
                    failures=failures,
                ) from exc
            if action == "stop" or not has_backup:
                if len(failures) == 1 and action != "advance_profile":
                    raise
                summary = "; ".join(
                    f"{entry['profile_name']}: {entry['error']}" for entry in failures
                )
                raise LLMProviderChainError(
                    f"LLM provider chain failed ({summary})",
                    retryable=action == "retry_profile",
                ) from exc
            logger.warning(
                "LLM profile %s failed (%s); trying backup %s: %s",
                profile["name"],
                action,
                profiles[index + 1]["name"],
                exc,
            )

    if response_schema is not None:
        from src.structured_output import StructuredOutputError
        raise StructuredOutputError("No compatible structured-output profile succeeded. " +
                                    "; ".join(f"{f['profile_name']}: {f['error']}" for f in failures))
    raise LLMProviderChainError("No LLM providers are configured")


def _run_llm_prompt(prompt: str, config: Dict[str, Any], **structured_options) -> str:
    """Run a prompt through the configured primary and backup providers."""
    result, _profile, _failures = _run_llm_prompt_with_failover(prompt, config, **structured_options)
    return result


def compose_gemini_speaker_profile_prompt(prompt_prefix: str, speakers: List[str], context: str = "", processed_text: str = "") -> str:
    """Build a bounded, schema-enforced speaker-profile request."""
    parts = []
    if prompt_prefix:
        parts.append(prompt_prefix.strip())
    if context:
        parts.append(context.strip())
    if processed_text:
        parts.append(
            "The following are bounded excerpts from the processed story. Use them "
            "to understand each speaker's personality, role, and speaking style:\n\n"
            + processed_text.strip()
        )
    speaker_line = ", ".join([s for s in speakers if s])
    if speaker_line:
        parts.append("Create one row for every exact speaker ID in this list:\n" + speaker_line)
    parts.append(
        "REQUIRED OUTPUT FORMAT: Return only a Markdown table with exactly these "
        "columns: Character Name | Full Description | Voice Type | Voice Design Prompt. "
        "Preserve each speaker ID exactly as supplied. Keep Full Description limited to "
        "the narrative character profile: role, personality, dramatic purpose, and "
        "emotional range. Voice Type must be a concise casting label describing the sound "
        "of the voice. Voice Design Prompt must be a synthesis-ready positive instruction "
        "in this order: [explicit gender], [age/range], [timbre], "
        "[pace using a rate term such as slow, measured, lively, or brisk], [accent], "
        "[emotional delivery]. Begin with an age-aware, all-capitals label: 'FEMALE CHILD "
        "VOICE' or 'MALE CHILD VOICE' for children; 'TEENAGE FEMALE/MALE VOICE', 'YOUNG "
        "ADULT FEMALE/MALE VOICE', 'ADULT FEMALE/MALE VOICE', 'MIDDLE-AGED FEMALE/MALE "
        "VOICE', or 'ELDERLY FEMALE/MALE VOICE' as appropriate. Use GENDER-NEUTRAL in "
        "place of FEMALE/MALE when needed. Never label a child or teenager as ADULT. Keep it concise at 75-150 "
        "characters. Do not mention audiobooks, narration, dialogue, or a use case, and never "
        "include negative wording such as 'not', 'never', or 'no'. Do not omit narrator "
        "and do not return blank cells."
    )
    return "\n\n".join(parts).strip()


def build_speaker_profile_excerpts(
    processed_text: str,
    speakers: List[str],
    *,
    max_chars_per_speaker: int = 1600,
    max_total_chars: int = 12000,
) -> str:
    """Collect representative tagged passages without resending an entire book."""
    if not processed_text or not speakers:
        return ""
    wanted = {str(speaker).strip().lower(): str(speaker).strip() for speaker in speakers if str(speaker).strip()}
    excerpts: Dict[str, List[str]] = {key: [] for key in wanted}
    lengths = {key: 0 for key in wanted}
    pattern = re.compile(r"\[([a-zA-Z0-9_-]+)\](.*?)\[/\1\]", re.DOTALL)
    for match in pattern.finditer(processed_text):
        key = match.group(1).strip().lower()
        if key not in wanted or lengths[key] >= max_chars_per_speaker:
            continue
        passage = re.sub(r"\s+", " ", match.group(2)).strip()
        if not passage:
            continue
        remaining = max_chars_per_speaker - lengths[key]
        passage = passage[:remaining].rstrip()
        if passage:
            excerpts[key].append(passage)
            lengths[key] += len(passage)

    blocks = []
    total = 0
    for key, display_name in wanted.items():
        sample = " … ".join(excerpts[key]).strip()
        if not sample:
            sample = "No tagged excerpt was available; infer cautiously from the speaker ID."
        block = f"Speaker: {display_name}\nExcerpts: {sample}"
        if blocks and total + len(block) > max_total_chars:
            block = f"Speaker: {display_name}\nExcerpts: Additional excerpt omitted for context size; infer cautiously from the speaker ID."
        blocks.append(block)
        total += len(block)
    return "\n\n".join(blocks)


def parse_gemini_speaker_table(text: str) -> Dict[str, Dict[str, str]]:
    """Parse JSON or speaker tables, including dedicated VoiceDesign prompts."""
    if not text:
        return {}
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json|markdown|md)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    def add_profile(profiles, name, description, voice, voice_design_prompt=""):
        name = str(name or "").strip()
        description = str(description or "").strip()
        voice = str(voice or "").strip()
        voice_design_prompt = str(voice_design_prompt or "").strip()
        if not name or not description or not voice:
            return
        profile = {
            "name": name,
            "description": description,
            "voice": voice,
        }
        if voice_design_prompt:
            profile["voice_design_prompt"] = voice_design_prompt
        profiles[name.lower()] = profile

    try:
        decoded = json.loads(cleaned)
    except (TypeError, ValueError, json.JSONDecodeError):
        decoded = None
    if decoded is not None:
        profiles = {}
        if isinstance(decoded, dict) and isinstance(decoded.get("profiles"), (list, dict)):
            decoded = decoded["profiles"]
        if isinstance(decoded, dict):
            for name, entry in decoded.items():
                if not isinstance(entry, dict):
                    continue
                add_profile(
                    profiles,
                    entry.get("name") or entry.get("character") or entry.get("speaker") or name,
                    entry.get("description") or entry.get("full_description") or entry.get("profile"),
                    entry.get("voice") or entry.get("voice_profile") or entry.get("voice_type"),
                    entry.get("voice_design_prompt") or entry.get("voice_prompt") or entry.get("tts_prompt"),
                )
        elif isinstance(decoded, list):
            for entry in decoded:
                if not isinstance(entry, dict):
                    continue
                add_profile(
                    profiles,
                    entry.get("name") or entry.get("character") or entry.get("speaker"),
                    entry.get("description") or entry.get("full_description") or entry.get("profile"),
                    entry.get("voice") or entry.get("voice_profile") or entry.get("voice_type"),
                    entry.get("voice_design_prompt") or entry.get("voice_prompt") or entry.get("tts_prompt"),
                )
        if profiles:
            return profiles

    lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
    if not lines:
        return {}
    rows = []
    for line in lines:
        if '|' in line:
            parts = [part.strip() for part in line.strip('|').split('|')]
            if len(parts) >= 3:
                rows.append(parts[:4])
    if not rows:
        return {}
    profiles = {}
    for row in rows:
        name, description, voice = row[:3]
        voice_design_prompt = row[3] if len(row) > 3 else ""
        normalized_columns = [column.strip().lower().replace(" ", "_") for column in (name, description, voice)]
        if all(re.fullmatch(r":?-{3,}:?", column.replace(" ", "")) for column in (name, description, voice)):
            continue
        if normalized_columns[0] in {"character", "character_name", "speaker", "speaker_name", "name"}:
            continue
        add_profile(profiles, name, description, voice, voice_design_prompt)
    return profiles


def _voice_age_category(source: str) -> str:
    """Infer a conservative casting age category from explicit wording or an age."""
    text = (source or "").lower()
    age_match = re.search(
        r"\b(\d{1,2})(?:\s*[-–]\s*(\d{1,2}))?\s*[- ]?\s*(?:years?|yrs?)(?:\s*[- ]\s*old)?\b",
        text,
    )
    if age_match:
        low = int(age_match.group(1))
        high = int(age_match.group(2) or low)
        age = max(low, high)
        if age <= 12:
            return "child"
        if age <= 17:
            return "teenage"
        if age <= 29:
            return "young_adult"
        if age >= 65:
            return "elderly"
        if age >= 45:
            return "middle_aged"
        return "adult"
    if re.search(r"\b(child|child-like|kid|pre-?teen|boy|girl)\b", text):
        return "child"
    if re.search(r"\b(teen|teenage|adolescent)\b", text):
        return "teenage"
    if re.search(r"\byoung adult\b", text):
        return "young_adult"
    if re.search(r"\b(middle-aged|middle aged)\b", text):
        return "middle_aged"
    if re.search(r"\b(elderly|senior|older adult)\b", text):
        return "elderly"
    return "adult"


def _voice_age_gender_prefix(gender: str, source: str) -> str:
    gender_label = {
        "female": "FEMALE",
        "male": "MALE",
        "neutral": "GENDER-NEUTRAL",
    }.get((gender or "").lower(), "GENDER-NEUTRAL")
    age_category = _voice_age_category(source)
    if age_category == "child":
        return f"{gender_label} CHILD VOICE"
    age_label = {
        "teenage": "TEENAGE",
        "young_adult": "YOUNG ADULT",
        "middle_aged": "MIDDLE-AGED",
        "elderly": "ELDERLY",
        "adult": "ADULT",
    }[age_category]
    return f"{age_label} {gender_label} VOICE"


VOICE_DESIGN_PREFIX_PATTERN = (
    r"\b(?:(?:female|male|gender[- ]neutral)\s+child|"
    r"(?:teenage|young adult|middle[- ]aged|elderly|adult)\s+"
    r"(?:female|male|gender[- ]neutral))\s+voice\b[.,;:]?"
)


def build_profile_voice_design_prompt(profile: Dict[str, Any]) -> str:
    """Guarantee a compact VoiceDesign prompt without using narrative biography text."""
    name = str(profile.get("name") or "").strip()
    voice_type = re.sub(r"\s+", " ", str(profile.get("voice") or "").strip())
    supplied = re.sub(r"\s+", " ", str(profile.get("voice_design_prompt") or "").strip())
    gender_source = f"{name} {voice_type} {supplied}".lower()

    if re.search(r"\bfemale\b|\bwoman\b|\bgirl\b|\bsoprano\b|\balto\b", gender_source):
        gender = "female"
    elif re.search(r"\bmale\b|\bman\b|\bboy\b|\bbaritone\b|\bbass\b|\btenor\b", gender_source):
        gender = "male"
    elif re.search(r"\bneutral\b|\bnonbinary\b|\bnon-binary\b", gender_source):
        gender = "neutral"
    else:
        gender = "neutral"

    gender_phrase = _voice_age_gender_prefix(gender, gender_source)

    prompt = supplied or voice_type
    prompt = re.sub(
        r"\b(?:suitable\s+)?for\s+(?:sustained\s+)?(?:an?\s+)?audiobook(?:\s+(?:dialogue|narration))?\b",
        " ",
        prompt,
        flags=re.IGNORECASE,
    )
    prompt = re.sub(r"\baudiobook(?:\s+(?:dialogue|narration))?\b", " ", prompt, flags=re.IGNORECASE)
    prompt = re.sub(
        VOICE_DESIGN_PREFIX_PATTERN,
        " ",
        prompt,
        flags=re.IGNORECASE,
    )
    prompt = re.sub(
        r"\bchild[- ]like\s*\((\d{1,2}(?:\s*[-–]\s*\d{1,2})?)\s*years?\)",
        r"age \1",
        prompt,
        flags=re.IGNORECASE,
    )
    prompt = re.sub(r"\bchild[- ]like\b", " ", prompt, flags=re.IGNORECASE)
    prompt = re.sub(r"\bemotional(?=\s*[.,;]|$)", "delivery", prompt, flags=re.IGNORECASE)
    prompt = re.sub(
        r"\b(?:but\s+)?(?:not|never|no)\b[^,.;]*[,.;]?",
        "",
        prompt,
        flags=re.IGNORECASE,
    )
    prompt = re.sub(r"\s+", " ", prompt).strip(" ,;")
    if not prompt:
        prompt = voice_type
    prompt = f"{gender_phrase}. {prompt}" if prompt else gender_phrase
    if not re.search(r"\bEnglish\b|\baccent\b", prompt, re.IGNORECASE):
        prompt = f"{prompt.rstrip('.')}. Neutral English accent."
    prompt = re.sub(r"\s+", " ", prompt).strip()
    if len(prompt) > 150:
        prompt = prompt[:150].rsplit(" ", 1)[0].rstrip(" ,;") + "."
    elif not prompt.endswith("."):
        prompt += "."
    return prompt


def _is_chatterbox_engine(engine_name: str) -> bool:
    normalized = _normalize_engine_name(engine_name)
    return normalized.startswith("chatterbox")


def _create_text_processor_for_engine(engine_name: str, chunk_size: int, config: Optional[Dict] = None) -> TextProcessor:
    if _normalize_engine_name(engine_name) == "breeze_api":
        limit = max(120, min(4000, int((config or {}).get("breeze_api_chunk_size", 1000))))
        return TextProcessor(chunk_strategy="characters", char_soft_limit=limit,
                             char_hard_limit=limit + 150, allow_sentence_overflow=True)
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
    # Kokoro works best with smaller character-based chunks for faster processing
    if _normalize_engine_name(engine_name) == "kokoro":
        kokoro_chunk_size = 500  # ~80-100 words, generates ~30-40s of audio
        if config:
            kokoro_chunk_size = config.get("kokoro_chunk_size", 500)
        return TextProcessor(
            chunk_strategy="characters",
            char_soft_limit=kokoro_chunk_size,
            char_hard_limit=kokoro_chunk_size + 50,
        )
    if _normalize_engine_name(engine_name) == "azure_speech":
        azure_chunk_size = 1000
        if config:
            azure_chunk_size = config.get("azure_speech_chunk_size", azure_chunk_size)
        return TextProcessor(
            chunk_strategy="characters",
            char_soft_limit=azure_chunk_size,
            char_hard_limit=azure_chunk_size + 100,
        )
    if _normalize_engine_name(engine_name) == "edge_tts":
        edge_chunk_size = 1000
        if config:
            edge_chunk_size = config.get("edge_tts_chunk_size", edge_chunk_size)
        return TextProcessor(
            chunk_strategy="characters",
            char_soft_limit=edge_chunk_size,
            char_hard_limit=edge_chunk_size + 100,
        )
    if _normalize_engine_name(engine_name) == "elevenlabs":
        elevenlabs_chunk_size = 4000
        if config:
            elevenlabs_chunk_size = config.get("elevenlabs_chunk_size", elevenlabs_chunk_size)
        return TextProcessor(
            chunk_strategy="characters",
            char_soft_limit=elevenlabs_chunk_size,
            char_hard_limit=elevenlabs_chunk_size + 100,
        )
    if _normalize_engine_name(engine_name) == "openai_tts":
        openai_chunk_size = 4000
        if config:
            openai_chunk_size = config.get("openai_tts_chunk_size", openai_chunk_size)
        return TextProcessor(
            chunk_strategy="characters",
            char_soft_limit=openai_chunk_size,
            char_hard_limit=min(openai_chunk_size + 96, 4096),
        )
    if _normalize_engine_name(engine_name) == "localai_tts":
        localai_chunk_size = 1000
        if config:
            localai_chunk_size = config.get("localai_tts_chunk_size", localai_chunk_size)
        return TextProcessor(
            chunk_strategy="characters",
            char_soft_limit=localai_chunk_size,
            char_hard_limit=localai_chunk_size + 100,
        )
    if _normalize_engine_name(engine_name) in {"pocket_tts", "pocket_tts_preset"}:
        pocket_chunk_size = 450
        if config:
            pocket_chunk_size = config.get("pocket_tts_chunk_size", pocket_chunk_size)
        return TextProcessor(
            chunk_strategy="characters",
            char_soft_limit=pocket_chunk_size,
            char_hard_limit=pocket_chunk_size + 50,
        )
    if _normalize_engine_name(engine_name) in {"qwen3_custom", "qwen3_clone"}:
        qwen_chunk_size = 500
        if config:
            qwen_chunk_size = config.get("qwen3_chunk_size", qwen_chunk_size)
        return TextProcessor(
            chunk_strategy="characters",
            char_soft_limit=qwen_chunk_size,
            char_hard_limit=qwen_chunk_size + 50,
        )
    if _normalize_engine_name(engine_name) in {"omnivoice_clone", "omnivoice_design"}:
        omnivoice_chunk_size = 500
        if config:
            omnivoice_chunk_size = config.get("omnivoice_chunk_size", omnivoice_chunk_size)
        return TextProcessor(
            chunk_strategy="characters",
            char_soft_limit=omnivoice_chunk_size,
            char_hard_limit=omnivoice_chunk_size + 50,
        )
    if _normalize_engine_name(engine_name) == "dots_tts":
        dots_chunk_size = 250
        if config:
            dots_chunk_size = config.get("dots_tts_chunk_size", dots_chunk_size)
        return TextProcessor(
            chunk_strategy="characters",
            char_soft_limit=dots_chunk_size,
            char_hard_limit=dots_chunk_size + 50,
            allow_sentence_overflow=True,
        )
    if _normalize_engine_name(engine_name) == "voxcpm_local":
        voxcpm_chunk_size = 550
        if config:
            voxcpm_chunk_size = config.get("voxcpm_chunk_size", voxcpm_chunk_size)
        return TextProcessor(
            chunk_strategy="characters",
            char_soft_limit=voxcpm_chunk_size,
            char_hard_limit=voxcpm_chunk_size + 50,
        )
    if _normalize_engine_name(engine_name) == "kitten_tts":
        kitten_chunk_size = 300
        if config:
            kitten_chunk_size = config.get("kitten_tts_chunk_size", kitten_chunk_size)
        return TextProcessor(
            chunk_strategy="characters",
            char_soft_limit=kitten_chunk_size,
            char_hard_limit=kitten_chunk_size + 50,
        )
    if _normalize_engine_name(engine_name) == "index_tts":
        index_chunk_size = 400
        if config:
            index_chunk_size = config.get("index_tts_chunk_size", index_chunk_size)
        return TextProcessor(
            chunk_strategy="characters",
            char_soft_limit=index_chunk_size,
            char_hard_limit=index_chunk_size + 100,
        )
    if engine_name == "audio8_tts":
        audio8_chunk_size = int((config or {}).get("audio8_tts_chunk_size", 140))
        audio8_chunk_size = max(40, min(150, audio8_chunk_size))
        audio8_hard_limit = int((config or {}).get("audio8_tts_hard_chunk_size", 400))
        audio8_hard_limit = max(audio8_chunk_size, min(1000, audio8_hard_limit))
        return TextProcessor(
            chunk_size=audio8_chunk_size,
            chunk_strategy="characters",
            char_soft_limit=audio8_chunk_size,
            char_hard_limit=audio8_hard_limit,
            allow_sentence_overflow=False,
        )
    if _normalize_engine_name(engine_name) == "breeze_tts_2":
        breeze_chunk_size = int((config or {}).get("breeze_tts_2_chunk_size", 500))
        breeze_chunk_size = max(120, min(900, breeze_chunk_size))
        return TextProcessor(
            chunk_strategy="characters",
            char_soft_limit=breeze_chunk_size,
            char_hard_limit=min(1000, breeze_chunk_size + 150),
            allow_sentence_overflow=True,
        )
    return TextProcessor(chunk_size=chunk_size)


def estimate_total_chunks(
    text: str,
    split_by_chapter: bool,
    chunk_size: int,
    include_full_story: bool = False,
    engine_name: Optional[str] = None,
    config: Optional[Dict] = None,
    section_headings: Optional[Any] = None,
) -> int:
    """Estimate total chunk count for a job to power progress indicators."""
    processor = _create_text_processor_for_engine(engine_name or DEFAULT_CONFIG["tts_engine"], chunk_size, config)
    sections = [{"content": text}]
    if split_by_chapter:
        detected = split_text_into_sections(text, section_headings)
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
        raise

def _is_concurrent_cloud_job(job_data: Dict[str, Any]) -> bool:
    if (job_data.get("job_type") or "audio") != "audio":
        return False
    engine_name = _normalize_engine_name((job_data.get("config") or {}).get("tts_engine"))
    return engine_name in CLOUD_TTS_ENGINES


def _cloud_job_limit(job_data: Dict[str, Any]) -> int:
    value = (job_data.get("config") or {}).get("cloud_tts_concurrent_jobs", 2)
    try:
        return max(1, min(4, int(value or 1)))
    except (TypeError, ValueError):
        return 2


def _run_queued_job(job_data: Dict[str, Any], *, cloud_slot: bool = False) -> None:
    """Process one queue entry and release any cloud-concurrency slot afterward."""
    global active_cloud_jobs, current_job_id
    job_id = job_data["job_id"]
    try:
        with queue_lock:
            job_entry = jobs.get(job_id)
            if not job_entry or job_entry.get("status") in {
                "paused", "archived", "deleted", "cancelled"
            }:
                return
            current_job_ids.add(job_id)
            current_job_id = job_id
            job_entry["status"] = "processing"
            if not job_entry.get("started_at"):
                job_entry["started_at"] = datetime.now().isoformat()
        _persist_job_state(job_id)
        logger.info("Processing job %s%s", job_id, " in a cloud slot" if cloud_slot else "")

        try:
            job_type = job_data.get("job_type") or "audio"
            if job_type == "audio":
                process_audio_job(job_data)
            elif job_type == "qwen3_voice_design_preview":
                process_qwen3_voice_design_preview_task(job_data)
            elif job_type == "qwen3_voice_design_save":
                process_qwen3_voice_design_save_task(job_data)
            elif job_type == "breeze_voice_design_preview":
                process_breeze_voice_design_preview_task(job_data)
            elif job_type == "breeze_voice_design_save":
                process_qwen3_voice_design_save_task(job_data)
            elif job_type == "omnivoice_design_preview":
                process_omnivoice_design_preview_task(job_data)
            elif job_type == "omnivoice_design_save":
                process_omnivoice_design_save_task(job_data)
            else:
                raise ValueError(f"Unsupported job type: {job_type}")
        except Exception as exc:
            logger.error("Error processing job %s: %s", job_id, exc, exc_info=True)
            with queue_lock:
                job_entry = jobs.get(job_id)
                if job_entry and job_entry.get("status") not in {
                    "paused", "interrupted", "cancelled"
                }:
                    job_entry["status"] = "failed"
                    job_entry["error"] = str(exc)
            _persist_job_state(job_id)
    finally:
        with queue_lock:
            current_job_ids.discard(job_id)
            current_job_id = next(iter(current_job_ids), None)
        if cloud_slot:
            with cloud_job_condition:
                active_cloud_jobs = max(0, active_cloud_jobs - 1)
                cloud_job_condition.notify_all()
        job_queue.task_done()


def process_job_worker():
    """Dispatch queued jobs, allowing a configurable number of cloud jobs concurrently."""
    global active_cloud_jobs
    logger.info("Job dispatcher thread started")

    while True:
        try:
            job_data = job_queue.get(timeout=1)
            if job_data is None:
                job_queue.task_done()
                logger.info("Job dispatcher thread stopping")
                break

            job_id = job_data["job_id"]
            if cancel_flags.get(job_id, False):
                logger.info("Job %s was cancelled before processing", job_id)
                with queue_lock:
                    if job_id in jobs:
                        jobs[job_id]["status"] = "cancelled"
                _persist_job_state(job_id)
                job_queue.task_done()
                continue

            with queue_lock:
                job_entry = jobs.get(job_id)
                inactive = not job_entry or job_entry.get("status") in {
                    "paused", "archived", "deleted", "cancelled"
                }
            if inactive:
                job_queue.task_done()
                continue

            if _is_concurrent_cloud_job(job_data):
                limit = _cloud_job_limit(job_data)
                with cloud_job_condition:
                    while active_cloud_jobs >= limit and not cancel_flags.get(job_id, False):
                        cloud_job_condition.wait(timeout=0.5)
                    if cancel_flags.get(job_id, False):
                        with queue_lock:
                            if job_id in jobs:
                                jobs[job_id]["status"] = "cancelled"
                        _persist_job_state(job_id)
                        job_queue.task_done()
                        continue
                    active_cloud_jobs += 1
                try:
                    cloud_job_executor.submit(_run_queued_job, job_data, cloud_slot=True)
                except Exception:
                    with cloud_job_condition:
                        active_cloud_jobs = max(0, active_cloud_jobs - 1)
                        cloud_job_condition.notify_all()
                    job_queue.task_done()
                    raise
                continue

            _run_queued_job(job_data)
        except queue.Empty:
            continue
        except Exception as exc:
            logger.error("Worker thread error: %s", exc, exc_info=True)
            time.sleep(1)


def _apply_word_replacements(text: str, replacements: list) -> str:
    """Apply a list of {original, replacement} substitutions to text (case-insensitive)."""
    if not replacements or not text:
        return text
    import re as _re
    for entry in replacements:
        original = entry.get('original', '')
        replacement = entry.get('replacement', '')
        if not original or not replacement:
            continue
        try:
            escaped = _re.escape(original)
            text = _re.sub(escaped, replacement, text, flags=_re.IGNORECASE)
        except Exception:
            pass
    return text



def _release_cached_narration_engines():
    """Free narration models before casting; caller owns the GPU lifecycle lock."""
    with tts_engine_lock:
        for name, engine in list(tts_engine_instances.items()):
            engine.cleanup()
            tts_engine_instances.pop(name, None)
            engine_config_signatures.pop(name, None)


def _release_voice_design_memory():
    """Wait for casting to finish, then stop its persistent model workers."""
    global qwen3_voice_design_process, breeze_voice_design_process
    global qwen3_voice_design_log_handle, breeze_voice_design_log_handle
    global qwen3_voice_design_model, qwen3_voice_design_signature
    from src.process_lifecycle import stop_owned_worker

    with gpu_generation_lifecycle_lock:
        with qwen3_voice_design_process_lock:
            stop_owned_worker(qwen3_voice_design_process)
            qwen3_voice_design_process = None
            if qwen3_voice_design_log_handle:
                qwen3_voice_design_log_handle.close()
                qwen3_voice_design_log_handle = None
        with breeze_voice_design_process_lock:
            stop_owned_worker(breeze_voice_design_process)
            breeze_voice_design_process = None
            if breeze_voice_design_log_handle:
                breeze_voice_design_log_handle.close()
                breeze_voice_design_log_handle = None
        with tts_engine_lock:
            qwen3_voice_design_model = None
            qwen3_voice_design_signature = None
        gc.collect()
        # Only clear a CUDA context that the main process already initialized.
        torch_module = sys.modules.get("torch")
        if torch_module is not None and torch_module.cuda.is_initialized():
            torch_module.cuda.empty_cache()
        logger.info("Voice-design workers released; GPU memory cleanup complete before narration")


def process_audio_job(job_data):
    engine_name = _normalize_engine_name((job_data.get("config") or {}).get("tts_engine"))
    if engine_name in CLOUD_TTS_ENGINES:
        return _process_audio_job(job_data)
    logger.info("Job %s: waiting for GPU access and preparing narration memory", job_data.get("job_id"))
    with gpu_generation_lifecycle_lock:
        _release_voice_design_memory()
        return _process_audio_job(job_data)


def _process_audio_job(job_data):
    """Process a single audio generation job"""
    job_id = job_data['job_id']
    text = job_data['text']
    voice_assignments = job_data['voice_assignments']
    config = job_data['config']
    split_by_chapter = job_data.get('split_by_chapter', False)
    generate_full_story = job_data.get('generate_full_story', False)
    section_headings = job_data.get('section_headings')
    word_replacements = job_data.get('word_replacements') or []
    job_log = None
    _job_log_handler = None

    try:
        # Check for cancellation
        if cancel_flags.get(job_id, False):
            raise JobCancelled()
        
        review_mode = bool(job_data.get('review_mode', False))
        merge_options_override = job_data.get('merge_options') or {}
        processor = _create_text_processor_for_engine(config.get("tts_engine"), config["chunk_size"], config)
        job_dir = OUTPUT_DIR / job_id
        job_dir.mkdir(parents=True, exist_ok=True)

        # Per-job file logger — writes job.log inside the job output directory.
        _job_log_path = job_dir / "job.log"
        _job_log_handler = logging.FileHandler(_job_log_path, encoding="utf-8")
        _job_log_handler.setLevel(logging.DEBUG)
        _job_log_handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        ))
        job_log = logging.getLogger(f"{__name__}.job.{job_id}")
        job_log.setLevel(logging.DEBUG)
        job_log.propagate = False  # write only to file; global logger still handles terminal
        job_log.addHandler(_job_log_handler)

        job_log.info("=" * 72)
        job_log.info("JOB STARTED  id=%s", job_id)
        job_log.info("engine=%s  review_mode=%s  split_by_chapter=%s  full_story=%s",
                     config.get("tts_engine"), review_mode, split_by_chapter, generate_full_story)
        job_log.info("total_chunks=%s  resume_from=%s  chunk_size=%s",
                     job_data.get('total_chunks'), job_data.get('resume_from_chunk_index', 0),
                     config.get('chunk_size'))
        job_log.info("output_format=%s  speed=%s  text_length=%d chars",
                     config.get('output_format'), config.get('speed'), len(text or ''))
        speakers = list(voice_assignments.keys()) if voice_assignments else []
        job_log.info("speakers=%s", speakers)

        with queue_lock:
            job_entry = jobs.get(job_id)
            if job_entry is not None:
                job_entry['job_dir'] = str(job_dir)
        total_chunks = max(1, job_data.get('total_chunks') or jobs.get(job_id, {}).get('total_chunks') or 1)
        resume_from_chunk_index = int(job_data.get("resume_from_chunk_index") or 0)
        processed_chunks = max(0, min(resume_from_chunk_index, total_chunks))
        job_start_time = datetime.now()
        cancel_event = cancel_events.setdefault(job_id, threading.Event())
        remaining_skip = processed_chunks
        from src.job_timing import JobTiming
        with queue_lock:
            _prior_tm = (jobs.get(job_id) or {}).get("timing_metrics") or {}
        timing = JobTiming(_prior_tm, processed_chunks)

        with queue_lock:
            job_entry = jobs.get(job_id)
            if job_entry is not None:
                if not job_entry.get("chunks"):
                    existing_chunks = _load_chunks_metadata(job_dir)
                    if existing_chunks:
                        job_entry["chunks"] = existing_chunks
                job_entry["resume_from_chunk_index"] = resume_from_chunk_index
                if resume_from_chunk_index > 0:
                    job_entry["last_completed_chunk_index"] = resume_from_chunk_index - 1
                job_entry["processed_chunks"] = processed_chunks
                job_entry["total_chunks"] = total_chunks
                job_entry["progress"] = int((processed_chunks / total_chunks) * 100) if total_chunks else 0
        _persist_job_state(job_id)

        def update_progress(increment: int = 1):
            if cancel_flags.get(job_id, False):
                raise JobCancelled()
            nonlocal processed_chunks
            processed_chunks += increment
            processed_chunks = min(processed_chunks, total_chunks)
            if increment > 0:
                timing.complete()
            remaining = max(total_chunks - processed_chunks, 0)
            eta_seconds = timing.eta(remaining) if remaining else 0
            percent = max(0, min(100, int(processed_chunks / total_chunks * 100)))
            live_tm = timing.snapshot()

            with queue_lock:
                job_entry = jobs.get(job_id)
                if job_entry:
                    job_entry['processed_chunks'] = processed_chunks
                    job_entry['total_chunks'] = total_chunks
                    job_entry['progress'] = percent if job_entry.get('status') != 'completed' else 100
                    job_entry['eta_seconds'] = eta_seconds
                    job_entry['last_update'] = datetime.now().isoformat()
                    if increment > 0:
                        job_entry['last_completed_chunk_index'] = max(0, processed_chunks - 1)
                        job_entry['resume_from_chunk_index'] = processed_chunks
                        if live_tm is not None:
                            job_entry['timing_metrics'] = live_tm

            _persist_job_state(job_id)

            # Engines report a completed chunk through progress_cb and then
            # chunk_cb. Pause only after chunk_cb has registered its file, so
            # the persisted resume index never advances beyond saved audio.
            if increment == 0 and pause_flags.get(job_id, False):
                raise JobPaused()

        def pause_cb() -> bool:
            return bool(pause_flags.get(job_id, False))

        def init_post_process(total_steps: int):
            with queue_lock:
                job_entry = jobs.get(job_id)
                if job_entry:
                    job_entry['post_process_total'] = max(int(total_steps or 0), 0)
                    job_entry['post_process_done'] = 0
                    job_entry['post_process_percent'] = 0
                    job_entry['post_process_active'] = True

        def update_post_process(increment: int = 1):
            with queue_lock:
                job_entry = jobs.get(job_id)
                if job_entry:
                    total_steps = int(job_entry.get('post_process_total') or 0)
                    done_steps = int(job_entry.get('post_process_done') or 0) + increment
                    job_entry['post_process_done'] = min(done_steps, total_steps) if total_steps else done_steps
                    if total_steps:
                        job_entry['post_process_percent'] = int(min((job_entry['post_process_done'] / total_steps) * 100, 100))
                    job_entry['post_process_active'] = True

        def update_post_process_progress(start_offset: int, chunk_count: int, ratio: float):
            with queue_lock:
                job_entry = jobs.get(job_id)
                if job_entry:
                    total_steps = int(job_entry.get('post_process_total') or 0)
                    if total_steps <= 0:
                        return
                    clamped = max(0.0, min(float(ratio or 0), 1.0))
                    current_done = int(min(start_offset + (clamped * max(chunk_count, 1)), total_steps))
                    overall = current_done / total_steps
                    job_entry['post_process_done'] = current_done
                    job_entry['post_process_percent'] = int(min(overall * 100, 100))
                    job_entry['post_process_active'] = True
        
        # Determine sections when requested
        chapter_sections = [{"title": "Full Story", "content": text}]
        book_sections = []
        book_mode = False
        if split_by_chapter:
            hierarchy = split_text_into_book_sections(text, section_headings)
            if hierarchy.get("kind") == "book" and hierarchy.get("books"):
                book_mode = True
                book_sections = hierarchy.get("books") or []
                job_log.info("Text split into book mode: %d books", len(book_sections))
            elif hierarchy.get("sections"):
                chapter_sections = hierarchy.get("sections")
                job_log.info("Text split into %d chapter(s)", len(chapter_sections))
            else:
                logger.info("Section splitting enabled but no headings detected; falling back to single output")
                job_log.info("Section splitting enabled but no headings detected — falling back to single output")
                split_by_chapter = False
        
        chapter_count = len(chapter_sections)
        book_count = len(book_sections) if book_mode else 0
        with queue_lock:
            job_entry = jobs.get(job_id)
            if job_entry:
                job_entry['chapter_count'] = chapter_count
                job_entry['chapter_mode'] = split_by_chapter
                job_entry['full_story_requested'] = generate_full_story
                job_entry['book_mode'] = book_mode
                job_entry['book_count'] = book_count
                job_entry['post_process_total'] = 0
                job_entry['post_process_done'] = 0
                job_entry['post_process_active'] = False
        
        output_format = config['output_format']
        crossfade_seconds = float(config.get('crossfade_duration', 0) or 0)
        merger = None if review_mode else AudioMerger(
            crossfade_ms=int(max(0.0, crossfade_seconds) * 1000),
            intro_silence_ms=int(max(0, config.get('intro_silence_ms', 0) or 0)),
            inter_chunk_silence_ms=int(max(0, config.get('inter_chunk_silence_ms', 0) or 0)),
            bitrate_kbps=int(config.get('output_bitrate_kbps') or 0),
            acx_compliance=bool(config.get('acx_compliance', False)),
        )
        chapter_outputs = []
        full_story_entry = None
        all_full_story_chunks = [] if (split_by_chapter and generate_full_story) else None
        chunk_dirs_to_cleanup = []
        review_manifest = {
            "chapter_mode": split_by_chapter,
            "book_mode": book_mode,
            "chapters": [],
            "books": [],
            "full_story_requested": generate_full_story,
            "output_format": output_format,
            "chunk_dirs_to_cleanup": [],
            "all_full_story_chunks": [],
        }

        # On resume: restore chapter/book entries that were recorded before the pause.
        # These were saved to review_manifest_partial.json when the job was paused.
        _restored_chapter_indices: set = set()
        if resume_from_chunk_index > 0 and review_mode:
            _partial_manifest_path = job_dir / "review_manifest_partial.json"
            if _partial_manifest_path.exists():
                try:
                    with _partial_manifest_path.open("r", encoding="utf-8") as _fh:
                        _partial = json.load(_fh)
                    review_manifest["chapters"] = list(_partial.get("chapters") or [])
                    review_manifest["books"] = list(_partial.get("books") or [])
                    review_manifest["chunk_dirs_to_cleanup"] = list(_partial.get("chunk_dirs_to_cleanup") or [])
                    review_manifest["all_full_story_chunks"] = list(_partial.get("all_full_story_chunks") or [])
                    # The chapter loop rebuilds the full-story list, including
                    # skipped chapters. Restoring it here would duplicate them.
                    # Track which chapter indices are already in the manifest so the
                    # chapter loop does not append them a second time (prevents duplication).
                    _restored_chapter_indices = {
                        ch["index"] for ch in review_manifest["chapters"] if "index" in ch
                    }
                    logger.info(
                        "Job %s: Restored partial review_manifest — %d chapters, %d books from before pause",
                        job_id, len(review_manifest["chapters"]), len(review_manifest["books"]),
                    )
                except Exception as _e:
                    logger.warning("Job %s: Could not load partial review_manifest: %s", job_id, _e)
        
        # Prepare TTS engine
        engine_name = _normalize_engine_name(config.get("tts_engine"))
        logger.info("Job %s: Creating TTS engine '%s'", job_id, engine_name)
        job_log.info("Initializing TTS engine: %s", engine_name)
        engine = get_tts_engine(engine_name, config=config)
        _dev = getattr(engine, 'device', 'unknown')
        logger.info("Job %s: Engine device = %s", job_id, _dev)
        job_log.info("Engine ready — device=%s", _dev)

        # For IndexTTS with split_by_chapter: pre-collect ALL chapters into one
        # subprocess call to avoid per-chapter model-reload overhead (~30-60s each).
        # Results are cached by output_path; generate_chunks returns from cache.
        _prebuilt_audio_cache: Dict[str, str] = {}  # output_path -> file_path (same value)

        job_chunks: List[Dict[str, Any]] = []
        with queue_lock:
            existing_job_chunks = list(jobs.get(job_id, {}).get("chunks") or [])
        if existing_job_chunks:
            job_chunks = existing_job_chunks
        if resume_from_chunk_index:
            claimed_paths = {}
            for record in job_chunks:
                path = str(Path(record.get("file_path") or "").resolve()).casefold()
                identity = (record.get("chapter_index"), record.get("text"))
                if path in claimed_paths and claimed_paths[path] != identity:
                    raise RuntimeError(
                        "This job has conflicting chunk files from an older resume. "
                        "Start a new generation from the saved project; resuming cannot restore overwritten audio."
                    )
                claimed_paths[path] = identity

        def register_chunk(chapter_idx: int, chunk_idx: int, segment: Dict[str, Any], file_path: str):
            chunk_id = f"{chapter_idx}-{segment.get('order_index', chunk_idx)}"
            speaker_name = segment.get("speaker")
            speaker_assignment = None
            if voice_assignments:
                candidate = voice_assignments.get(speaker_name) or voice_assignments.get("default")
                speaker_assignment = _clone_voice_assignment(candidate)
            voice_label = _voice_label_from_assignment(speaker_assignment)
            order_index = segment.get("order_index")
            record = {
                "id": chunk_id,
                "order_index": order_index if order_index is not None else len(job_chunks),
                "chapter_index": chapter_idx,
                "chunk_index": chunk_idx,
                "speaker": segment.get("speaker"),
                "engine": engine_name,
                "emotion": segment.get("emotion"),
                "delivery_instruction": segment.get("delivery_instruction") or segment.get("emotion"),
                "text": segment.get("text"),
                "file_path": file_path,
                "relative_file": os.path.relpath(file_path, job_dir),
                "duration_seconds": segment.get("duration_seconds"),
                "voice_assignment": speaker_assignment,
            }
            if voice_label:
                record["voice_label"] = voice_label
            job_chunks[:] = [old for old in job_chunks if not (
                old.get("chapter_index") == chapter_idx and old.get("order_index") == record["order_index"]
            )]
            job_chunks.append(record)
            with queue_lock:
                job_entry = jobs.get(job_id)
                if job_entry is not None:
                    job_entry["chunks"] = list(job_chunks)

        def make_chunk_callback(
            chapter_idx: int,
            output_files: Optional[List[str]] = None,
            chunk_offset: int = 0,
        ):
            def chunk_cb(chunk_idx: int, segment: Dict[str, Any], file_path: str):
                adjusted_segment = dict(segment)
                order_index = adjusted_segment.get("order_index")
                if order_index is not None:
                    adjusted_segment["order_index"] = int(order_index) + chunk_offset
                register_chunk(
                    chapter_idx,
                    int(chunk_idx) + chunk_offset,
                    adjusted_segment,
                    file_path,
                )
                if output_files is not None:
                    output_files.append(file_path)
                _persist_chunks_metadata(job_id, job_dir)
                update_progress(0)  # progress_cb already increments; just register chunk
            return chunk_cb

        def run_with_cancel(operation):
            if cancel_event.is_set() or cancel_flags.get(job_id, False):
                raise JobCancelled()
            result = operation()
            if cancel_event.is_set() or cancel_flags.get(job_id, False):
                raise JobCancelled()
            return result

        def _resolve_section_output_dir(
            base_dir: Path,
            section_title: Optional[str],
            chapter_folder_idx: int,
        ) -> tuple[Path, int, bool, str]:
            title = (section_title or "").strip()
            normalized = re.sub(r"\s+", " ", title).strip().lower()
            if normalized == "title":
                return base_dir / "title", chapter_folder_idx, True, "title"

            non_chapter_sections = {
                "introduction",
                "intro",
                "prologue",
                "preface",
                "foreword",
                "afterword",
                "epilogue",
                "acknowledgment",
                "acknowledgments",
                "acknowledgement",
                "acknowledgements",
                "appendix",
                "author note",
                "authors note",
                "author's note",
            }
            if normalized in non_chapter_sections:
                fallback = normalized.replace("'", "").replace(" ", "-") or "section"
                folder_name = slugify_filename(title, fallback).lower()
                return base_dir / folder_name, chapter_folder_idx, False, folder_name

            chapter_like = re.match(
                r"^(chapter|book|part|section|letter)\b",
                normalized,
                flags=re.IGNORECASE,
            )
            if title and not chapter_like:
                folder_name = slugify_filename(title, "section").lower()
                return base_dir / folder_name, chapter_folder_idx, False, folder_name

            folder_name = f"chapter_{chapter_folder_idx:02d}"
            slug_default = f"chapter-{chapter_folder_idx:02d}"
            return base_dir / folder_name, chapter_folder_idx + 1, False, slug_default

        def _apply_chunk_skip(segments: List[Dict[str, Any]], skip_count: int) -> tuple[List[Dict[str, Any]], int]:
            remaining = skip_count
            filtered: List[Dict[str, Any]] = []
            for segment in segments:
                chunks = segment.get("chunks") or []
                if remaining >= len(chunks):
                    remaining -= len(chunks)
                    continue
                if remaining > 0:
                    chunks = chunks[remaining:]
                    remaining = 0
                if chunks:
                    updated = dict(segment)
                    updated["chunks"] = chunks
                    filtered.append(updated)
            return filtered, skip_count - remaining

        def generate_chunks(chapter_idx: int, section_text: str, output_dir: Path):
            if cancel_flags.get(job_id, False):
                raise JobCancelled()

            # IndexTTS pre-build: all chunks were already generated in one subprocess.
            # Return the cached files for this chapter's output_dir directly.
            if _prebuilt_audio_cache:
                _out_dir_str = str(output_dir.resolve()).lower()
                cached = sorted(
                    [p for p in _prebuilt_audio_cache
                     if str(Path(p).parent.resolve()).lower() == _out_dir_str],
                    key=lambda p: p,
                )
                if cached:
                    return cached

            segments = processor.process_text(section_text)
            if not segments:
                return []
            original_section_items: List[Dict[str, Any]] = []
            for segment_index, original_segment in enumerate(segments):
                for chunk_index, chunk_text in enumerate(original_segment.get("chunks") or []):
                    original_section_items.append({
                        "speaker": original_segment.get("speaker"),
                        "emotion": original_segment.get("emotion"),
                        "delivery_instruction": original_segment.get("delivery_instruction") or original_segment.get("emotion"),
                        "text": chunk_text,
                        "segment_index": segment_index,
                        "chunk_index": chunk_index,
                        "order_index": len(original_section_items),
                    })
            section_skip = 0
            resume_prefix_files: List[str] = []
            nonlocal remaining_skip
            if remaining_skip > 0:
                segments, skipped = _apply_chunk_skip(segments, remaining_skip)
                remaining_skip = max(0, remaining_skip - skipped)
                if not segments:
                    # Entire chapter was skipped — return existing chunk files from disk
                    # so the caller can still build the review_manifest entry for this chapter.
                    if output_dir.exists():
                        def existing_chunk_order(path: Path) -> tuple[int, str]:
                            match = re.search(r"(\d+)$", path.stem)
                            return (
                                int(match.group(1)) if match else 10**12,
                                path.name.lower(),
                            )
                        existing = sorted(
                            (
                                p for p in output_dir.iterdir()
                                if p.is_file() and p.suffix.lower() in {".wav", ".mp3", ".ogg", ".flac"}
                            ),
                            key=existing_chunk_order,
                        )
                        if existing:
                            return [str(path) for path in existing]
                    return []
                section_skip = skipped
                prefix_by_index: Dict[int, str] = {}
                for record in job_chunks:
                    try:
                        record_chapter = int(record.get("chapter_index", -1))
                    except (TypeError, ValueError):
                        continue
                    if record_chapter != chapter_idx:
                        continue
                    try:
                        record_index = int(record.get("order_index", record.get("chunk_index")))
                    except (TypeError, ValueError):
                        continue
                    file_path = str(record.get("file_path") or "")
                    if 0 <= record_index < section_skip and file_path and Path(file_path).is_file():
                        prefix_by_index[record_index] = file_path
                for candidate in sorted(output_dir.glob("*")) if output_dir.exists() else []:
                    if not candidate.is_file() or candidate.suffix.lower() not in {
                        ".wav", ".mp3", ".ogg", ".flac"
                    }:
                        continue
                    match = re.search(r"(\d+)$", candidate.stem)
                    if not match:
                        continue
                    candidate_index = int(match.group(1))
                    if 0 <= candidate_index < section_skip:
                        prefix_by_index.setdefault(candidate_index, str(candidate))
                resume_prefix_files = [
                    prefix_by_index[index]
                    for index in range(section_skip)
                    if index in prefix_by_index
                ]
                if len(resume_prefix_files) != section_skip:
                    raise RuntimeError(
                        f"Resume expected {section_skip} saved chunks in chapter {chapter_idx}, "
                        f"but found {len(resume_prefix_files)}. Restore missing files or start a new generation."
                    )
                existing_record_indices = {
                    int(record.get("order_index", record.get("chunk_index")))
                    for record in job_chunks
                    if str(record.get("chapter_index")) == str(chapter_idx)
                    and str(record.get("chunk_index", "")).isdigit()
                }
                for prefix_index, prefix_file in sorted(prefix_by_index.items()):
                    if prefix_index in existing_record_indices or prefix_index >= len(original_section_items):
                        continue
                    register_chunk(
                        chapter_idx,
                        prefix_index,
                        original_section_items[prefix_index],
                        prefix_file,
                    )
                if prefix_by_index:
                    _persist_chunks_metadata(job_id, job_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            # Apply word replacements to each chunk before TTS submission
            if word_replacements:
                for segment in segments:
                    segment["chunks"] = [
                        _apply_word_replacements(chunk, word_replacements)
                        for chunk in (segment.get("chunks") or [])
                    ]
            generated_files: List[str] = []
            chunk_cb = make_chunk_callback(chapter_idx, generated_files, section_skip)
            supports_chunk_cb = False
            flat_segments: List[Dict[str, Any]] = []
            render_segments: List[Dict[str, Any]] = []
            normal_descriptors: List[Dict[str, Any]] = []
            pause_descriptors: List[Dict[str, Any]] = []
            render_descriptor_lookup: Dict[tuple[int, int], Dict[str, Any]] = {}
            order_index = 0
            for seg_idx, segment in enumerate(segments):
                speaker = segment.get("speaker")
                chunks = segment.get("chunks") or []
                render_chunks: List[str] = []
                for chunk_idx, chunk_text in enumerate(chunks):
                    descriptor = {
                        "segment_index": seg_idx,
                        "chunk_index": chunk_idx,
                        "order_index": order_index,
                        "speaker": speaker,
                        "text": chunk_text,
                        "emotion": segment.get("emotion"),
                        "delivery_instruction": segment.get("delivery_instruction") or segment.get("emotion"),
                    }
                    flat_segments.append(descriptor)
                    pause_seconds = pause_seconds_for_text(
                        chunk_text,
                        config.get("pause_marker_three_seconds", 0.25),
                        config.get("pause_marker_six_seconds", 0.5),
                    )
                    if pause_seconds is not None:
                        descriptor["pause_seconds"] = pause_seconds
                        pause_descriptors.append(descriptor)
                    else:
                        render_chunks.append(chunk_text)
                        normal_descriptors.append(descriptor)
                    order_index += 1
                if render_chunks:
                    render_segment = dict(segment)
                    render_segment["chunks"] = render_chunks
                    render_segment_index = len(render_segments)
                    segment_descriptors = [
                        descriptor
                        for descriptor in normal_descriptors
                        if descriptor["segment_index"] == seg_idx
                    ]
                    for render_chunk_index, descriptor in enumerate(segment_descriptors):
                        descriptor["render_segment_index"] = render_segment_index
                        descriptor["render_chunk_index"] = render_chunk_index
                        descriptor["render_order_index"] = sum(
                            len(item.get("chunks") or []) for item in render_segments
                        ) + render_chunk_index
                        render_descriptor_lookup[(render_segment_index, render_chunk_index)] = descriptor
                    render_segments.append(render_segment)

            # Engines may restart their own filenames at zero on every call.
            # Stage every batch, then commit with stable section-relative indices.
            render_dir = output_dir / f".tts-render-{uuid.uuid4().hex}"
            render_dir.mkdir(parents=True, exist_ok=True)

            final_files_by_order: Dict[int, str] = {}
            next_normal_callback = 0
            pending_rendered_chunks: Dict[int, tuple[Dict[str, Any], str]] = {}
            rendered_callback_lock = threading.Lock()

            def commit_rendered_chunk(descriptor: Dict[str, Any], source_path: str) -> str:
                source = Path(source_path)
                suffix = source.suffix.lower() or ".wav"
                final_path = output_dir / (
                    f"tts_chunk_{section_skip + int(descriptor['order_index']):06d}{suffix}"
                )
                final_path.parent.mkdir(parents=True, exist_ok=True)
                if source.resolve() != final_path.resolve():
                    os.replace(source, final_path)
                final_files_by_order[int(descriptor["order_index"])] = str(final_path)
                update_progress(1)
                chunk_cb(int(descriptor["order_index"]), descriptor, str(final_path))
                return str(final_path)

            def commit_pause_chunk(descriptor: Dict[str, Any]) -> str:
                final_path = output_dir / (
                    f"pause_chunk_{section_skip + int(descriptor['order_index']):06d}.wav"
                )
                try:
                    silence_rate = int(config.get("sample_rate") or engine.sample_rate or 24000)
                except (TypeError, ValueError, AttributeError):
                    silence_rate = 24000
                write_silence_wav(
                    final_path,
                    float(
                        0.5
                        if descriptor.get("pause_seconds") is None
                        else descriptor.get("pause_seconds")
                    ),
                    sample_rate=silence_rate,
                )
                final_files_by_order[int(descriptor["order_index"])] = str(final_path)
                update_progress(1)
                chunk_cb(int(descriptor["order_index"]), descriptor, str(final_path))
                return str(final_path)

            def commit_pauses_before(order_limit: int) -> None:
                for descriptor in pause_descriptors:
                    descriptor_order = int(descriptor["order_index"])
                    if descriptor_order >= order_limit:
                        break
                    if descriptor_order not in final_files_by_order:
                        commit_pause_chunk(descriptor)

            def pause_aware_chunk_cb(_chunk_idx: int, _segment: Dict[str, Any], file_path: str):
                nonlocal next_normal_callback
                descriptor = render_descriptor_lookup.get((
                    int(_segment.get("segment_index", -1)),
                    int(_segment.get("chunk_index", -1)),
                ))
                if descriptor is None and _segment.get("order_index") is not None:
                    try:
                        descriptor = normal_descriptors[int(_segment["order_index"])]
                    except (IndexError, TypeError, ValueError):
                        descriptor = None
                if descriptor is None:
                    match = re.search(r"(\d+)$", Path(file_path).stem)
                    if match:
                        try:
                            descriptor = normal_descriptors[int(match.group(1))]
                        except (IndexError, ValueError):
                            descriptor = None
                if descriptor is None:
                    raise RuntimeError("Could not map a rendered TTS chunk to its source text")

                render_order = int(descriptor["render_order_index"])
                with rendered_callback_lock:
                    pending_rendered_chunks[render_order] = (descriptor, file_path)
                    while next_normal_callback in pending_rendered_chunks:
                        next_descriptor, next_path = pending_rendered_chunks.pop(next_normal_callback)
                        commit_pauses_before(int(next_descriptor["order_index"]))
                        commit_rendered_chunk(next_descriptor, next_path)
                        next_normal_callback += 1

            def pause_aware_progress_cb(*_args, **_kwargs):
                # Progress is committed with each moved output so pause markers
                # and spoken chunks advance the same saved checkpoint in order.
                if cancel_flags.get(job_id, False):
                    raise JobCancelled()

            engine_kwargs = {
                "segments": render_segments,
                "voice_config": voice_assignments,
                "output_dir": str(render_dir),
                "speed": config['speed'],
                "progress_cb": pause_aware_progress_cb,
            }
            sig_params = inspect.signature(engine.generate_batch).parameters
            if "sample_rate" in sig_params:
                engine_kwargs["sample_rate"] = config.get("sample_rate")
            if "chunk_cb" in sig_params:
                engine_kwargs["chunk_cb"] = pause_aware_chunk_cb
                supports_chunk_cb = True
            if "parallel_workers" in sig_params:
                parallel_setting = {
                    "kokoro_replicate": "replicate_max_parallel",
                    "chatterbox_turbo_replicate": "replicate_max_parallel",
                    "azure_speech": "azure_speech_max_parallel",
                    "edge_tts": "edge_tts_max_parallel",
                    "elevenlabs": "elevenlabs_max_parallel",
                    "openai_tts": "openai_tts_max_parallel",
                    "localai_tts": "localai_tts_max_parallel",
                    "breeze_api": "breeze_api_max_parallel",
                }.get(engine_name, "parallel_chunks")
                engine_kwargs["parallel_workers"] = max(
                    1,
                    min(8, int(config.get(parallel_setting, 1) or 1)),
                )
            if "start_index" in sig_params:
                engine_kwargs["start_index"] = 0
            if "pause_cb" in sig_params:
                engine_kwargs["pause_cb"] = pause_cb
            if "cancel_cb" in sig_params:
                engine_kwargs["cancel_cb"] = lambda: bool(cancel_flags.get(job_id, False))
            if "group_by_speaker" in sig_params:
                engine_kwargs["group_by_speaker"] = (
                    bool(config.get("group_chunks_by_speaker", False))
                    and not pause_descriptors
                )
            _total_text_chunks = sum(len(seg.get("chunks") or []) for seg in segments)
            if job_log:
                job_log.info("  chapter_idx=%d  segments=%d  text_chunks=%d  output_dir=%s",
                             chapter_idx, len(segments), _total_text_chunks, output_dir)
            try:
                audio_files = (
                    run_with_cancel(lambda: engine.generate_batch(**engine_kwargs))
                    if normal_descriptors
                    else []
                )
                if not supports_chunk_cb:
                    for descriptor, file_path in zip(normal_descriptors, audio_files or []):
                        commit_pauses_before(int(descriptor["order_index"]))
                        commit_rendered_chunk(descriptor, file_path)
                commit_pauses_before(len(flat_segments) + 1)
                audio_files = [final_files_by_order[index] for index in range(len(flat_segments))
                               if index in final_files_by_order]
                if len(audio_files) != len(flat_segments):
                    raise RuntimeError("TTS engine did not return all requested chunks")
            finally:
                shutil.rmtree(render_dir, ignore_errors=True)
            if job_log:
                job_log.info("  engine returned %d audio file(s) for chapter_idx=%d",
                             len(audio_files) if audio_files else 0, chapter_idx)

            return resume_prefix_files + list(audio_files or [])

        def _prebuild_subprocess_engine_all_chapters():
            """Collect all chapter segments and run one worker subprocess.

            Eliminates per-chapter model-reload overhead (~30-60s each) by sending
            all chunks to one tts_worker.py process. Results cached in
            _prebuilt_audio_cache; generate_chunks returns from cache without
            re-launching the engine.
            """
            if not hasattr(engine, 'generate_batch_prebuilt'):
                return
            if not split_by_chapter:
                return
            from src.engines.index_tts_engine import IndexTTSEngine  # noqa: F401
            if not isinstance(engine, (IndexTTSEngine, DotsTTSEngine)):
                return
            if any(pause_seconds_for_text(line) is not None for line in (text or "").splitlines()):
                logger.info(
                    "Job %s: using per-section rendering so universal pause markers "
                    "can be inserted before audio merge",
                    job_id,
                )
                return

            engine_label = getattr(engine, "name", engine.__class__.__name__)
            logger.info("Job %s: %s batch mode — pre-collecting all chapters into one subprocess", job_id, engine_label)

            all_worker_chunks: List[Dict] = []
            all_chunk_meta: List[Dict] = []
            temp_prompt_files: List[Path] = []
            global_order = 0

            # Build parallel lists: section texts and their target chunk dirs
            sections_to_process: List[str] = []
            chapter_output_dirs: List[Path] = []

            if book_mode:
                for book_idx, book in enumerate(book_sections, start=1):
                    _ch_folder = 1
                    for chapter in (book.get("chapters") or []):
                        sections_to_process.append(chapter.get("content", ""))
                        _cdir, _ch_folder, _, _ = _resolve_section_output_dir(
                            job_dir / f"book_{book_idx:02d}",
                            chapter.get("title"),
                            _ch_folder,
                        )
                        if job_log:
                            job_log.info(
                                "  prebuild section map: book=%d title='%s' -> %s",
                                book_idx,
                                chapter.get("title"),
                                os.path.relpath(_cdir, job_dir),
                            )
                        chapter_output_dirs.append(_cdir / "chunks")
            else:
                _ch_folder = 1
                for chapter in chapter_sections:
                    sections_to_process.append(chapter.get("content", ""))
                    _cdir, _ch_folder, _, _ = _resolve_section_output_dir(
                        job_dir,
                        chapter.get("title"),
                        _ch_folder,
                    )
                    if job_log:
                        job_log.info(
                            "  prebuild section map: title='%s' -> %s",
                            chapter.get("title"),
                            os.path.relpath(_cdir, job_dir),
                        )
                    chapter_output_dirs.append(_cdir / "chunks")

            _skip_remaining = int(job_data.get("resume_from_chunk_index") or 0)
            for ch_idx, (section_text, chunk_dir) in enumerate(zip(sections_to_process, chapter_output_dirs)):
                segments = processor.process_text(section_text)
                if not segments:
                    continue
                if _skip_remaining > 0:
                    segments, skipped = _apply_chunk_skip(segments, _skip_remaining)
                    _skip_remaining = max(0, _skip_remaining - skipped)
                    if not segments:
                        continue
                if word_replacements:
                    for seg in segments:
                        seg["chunks"] = [
                            _apply_word_replacements(c, word_replacements)
                            for c in (seg.get("chunks") or [])
                        ]
                chunk_dir.mkdir(parents=True, exist_ok=True)
                local_idx = 0
                for seg_idx, segment in enumerate(segments):
                    speaker = segment.get("speaker")
                    assignment = engine._voice_assignment_for(voice_assignments, speaker)
                    for chunk_text in (segment.get("chunks") or []):
                        out_path = chunk_dir / f"chunk_{local_idx:04d}.wav"
                        if hasattr(engine, "_build_worker_chunk"):
                            worker_chunk, temp_prompt = engine._build_worker_chunk(
                                chunk_text,
                                str(out_path),
                                assignment,
                                global_order,
                            )
                            if temp_prompt:
                                temp_prompt_files.append(temp_prompt)
                            all_worker_chunks.append(worker_chunk)
                        else:
                            spk_prompt = engine._resolve_prompt(assignment)
                            all_worker_chunks.append({
                                "text": chunk_text,
                                "spk_audio_prompt": spk_prompt,
                                "output_path": str(out_path),
                                "_order_index": global_order,
                            })
                        all_chunk_meta.append({
                            "speaker": speaker,
                            "text": chunk_text,
                            "segment_index": seg_idx,
                            "chunk_index": local_idx,
                            "chapter_index": ch_idx,
                            "output_path": str(out_path),
                            "assignment": assignment,
                            "_order_index": global_order,
                        })
                        local_idx += 1
                        global_order += 1

            if not all_worker_chunks:
                return

            chunk_lengths = [len(item.get("text") or "") for item in all_worker_chunks]
            max_chunk_chars = max(chunk_lengths) if chunk_lengths else 0
            avg_chunk_chars = (sum(chunk_lengths) / len(chunk_lengths)) if chunk_lengths else 0.0
            logger.info(
                "Job %s: %s single-subprocess batch — %d total chunks across %d chapters; max_chars=%d avg_chars=%.1f",
                job_id, engine_label, len(all_worker_chunks), len(sections_to_process), max_chunk_chars, avg_chunk_chars,
            )
            if job_log:
                job_log.info(
                    "  %s prebuild chunks=%d max_chars=%d avg_chars=%.1f",
                    engine_label, len(all_worker_chunks), max_chunk_chars, avg_chunk_chars,
                )

            group_spk = bool(config.get("group_chunks_by_speaker", False))

            def _batch_chunk_cb(chunk_idx: int, segment: Dict[str, Any], file_path: str):
                chapter_idx = segment.get("chapter_index", 0)
                make_chunk_callback(chapter_idx)(chunk_idx, segment, file_path)

            try:
                engine.generate_batch_prebuilt(
                    worker_chunks=all_worker_chunks,
                    chunk_meta=all_chunk_meta,
                    progress_cb=update_progress,
                    chunk_cb=_batch_chunk_cb,
                    pause_cb=pause_cb,
                    cancel_cb=lambda: bool(cancel_flags.get(job_id, False)),
                    group_by_speaker=group_spk,
                )
            finally:
                for temp_prompt in temp_prompt_files:
                    temp_prompt.unlink(missing_ok=True)

            for item in all_worker_chunks:
                p = item["output_path"]
                if Path(p).exists():
                    _prebuilt_audio_cache[p] = p

            logger.info("Job %s: %s pre-build complete — %d files cached", job_id, engine_label, len(_prebuilt_audio_cache))

        _prebuild_subprocess_engine_all_chapters()

        if cancel_flags.get(job_id, False):
            raise JobCancelled()

        if pause_flags.get(job_id, False):
            raise JobPaused()

        try:
            if split_by_chapter:
                if book_mode:
                    if not review_mode:
                        post_total = total_chunks * (2 if generate_full_story else 1)
                        init_post_process(post_total)
                        merge_chunk_offset = 0
                    chapter_global_idx = 0
                    for book_idx, book in enumerate(book_sections, start=1):
                        if cancel_flags.get(job_id, False):
                            raise JobCancelled()

                        book_dir = job_dir / f"book_{book_idx:02d}"
                        book_chunk_files = []
                        rel_book_chunks = []
                        book_chapter_indices = []
                        chapter_folder_idx = 1
                        for chapter_idx, chapter in enumerate(book.get("chapters") or [], start=1):
                            chapter_dir, chapter_folder_idx, _, _ = _resolve_section_output_dir(
                                book_dir,
                                chapter.get("title"),
                                chapter_folder_idx,
                            )
                            chunk_dir = chapter_dir / "chunks"
                            audio_files = generate_chunks(chapter_global_idx, chapter["content"], chunk_dir)
                            if not audio_files:
                                logger.warning(f"Book {book_idx} chapter {chapter_idx} had no audio chunks; skipping")
                                job_log.warning("Book %d chapter %d produced no audio chunks — skipping", book_idx, chapter_idx)
                                chapter_global_idx += 1
                                continue

                            chapter_global_idx += 1
                            book_chapter_indices.append(chapter_global_idx - 1)
                            book_chunk_files.extend(audio_files)

                            if all_full_story_chunks is not None:
                                all_full_story_chunks.extend(audio_files)
                                chunk_dirs_to_cleanup.append(chunk_dir)

                            rel_chunk_dir = os.path.relpath(chunk_dir, job_dir)
                            rel_chapter_dir = os.path.relpath(chapter_dir, job_dir)
                            rel_chunk_files = [os.path.relpath(path, job_dir) for path in audio_files]
                            rel_book_chunks.extend(rel_chunk_files)
                            if review_mode:
                                review_manifest["chapters"].append({
                                    "index": chapter_global_idx - 1,  # 0-indexed to match chunk.chapter_index
                                    "title": chapter.get("title"),
                                    "chunk_dir": rel_chunk_dir,
                                    "chunk_files": rel_chunk_files,
                                    "chapter_dir": rel_chapter_dir,
                                    "book_index": book_idx - 1,
                                    "book_title": book.get("title"),
                                    "book_order": chapter_idx - 1,
                                })
                                review_manifest["chunk_dirs_to_cleanup"].append(rel_chunk_dir)

                        if not book_chunk_files:
                            continue

                        slug = slugify_filename(book.get('title'), f"book-{book_idx:02d}")
                        output_filename = f"{slug}.{output_format}"
                        output_path = book_dir / output_filename

                        if review_mode:
                            rel_book_dir = os.path.relpath(book_dir, job_dir)
                            review_manifest["books"].append({
                                "index": book_idx - 1,
                                "title": book.get("title"),
                                "chapter_indices": book_chapter_indices,
                                "chunk_files": rel_book_chunks,
                                "book_dir": rel_book_dir,
                                "output_filename": output_filename,
                            })
                        else:
                            if job_log:
                                job_log.info("Merging book %d: %d chunks -> %s", book_idx, len(book_chunk_files), output_path)
                            merger.merge_wav_files(
                                input_files=book_chunk_files,
                                output_path=str(output_path),
                                format=output_format,
                                cleanup_chunks=not generate_full_story,
                                progress_callback=lambda ratio, offset=merge_chunk_offset, count=len(book_chunk_files): (
                                    update_post_process_progress(offset, count, ratio)
                                ),
                            )
                            if job_log:
                                job_log.info("Merge complete: %s (exists=%s)", output_path.name, output_path.exists())
                            update_progress(0)
                            update_post_process(len(book_chunk_files))
                            merge_chunk_offset += len(book_chunk_files)

                            # Cleanup empty chunk directory
                            if book_dir.exists() and not generate_full_story:
                                for chapter_dir in book_dir.glob("chapter_*"):
                                    try:
                                        (chapter_dir / "chunks").rmdir()
                                    except OSError:
                                        pass

                            relative_path = Path(f"book_{book_idx:02d}") / output_filename
                            chapter_outputs.append({
                                "index": book_idx,
                                "title": book.get("title"),
                                "file_url": f"/static/audio/{job_id}/{relative_path.as_posix()}",
                                "relative_path": relative_path.as_posix()
                            })
                else:
                    if not review_mode:
                        post_total = total_chunks * (2 if generate_full_story else 1)
                        init_post_process(post_total)
                    
                    # Phase 1: Generate chunks for all chapters (sequential)
                    chapter_folder_idx = 1
                    merge_tasks = []  # Collect merge tasks for parallel processing
                    
                    for idx, chapter in enumerate(chapter_sections, start=1):
                        if cancel_flags.get(job_id, False):
                            raise JobCancelled()

                        section_title = (chapter.get("title") or "").strip()
                        chapter_dir, chapter_folder_idx, is_title_section, slug_default = _resolve_section_output_dir(
                            job_dir,
                            section_title,
                            chapter_folder_idx,
                        )
                        chunk_dir = chapter_dir / "chunks"
                        job_log.info(
                            "Section folder map: title='%s' -> %s",
                            section_title,
                            os.path.relpath(chapter_dir, job_dir),
                        )
                        job_log.info("Generating audio for chapter %d: '%s'", idx, chapter.get('title', ''))
                        audio_files = generate_chunks(idx - 1, chapter["content"], chunk_dir)
                        if not audio_files:
                            logger.warning(f"Chapter {idx} had no audio chunks; skipping")
                            job_log.warning("Chapter %d produced no audio chunks — skipping", idx)
                            continue
                        job_log.info("Chapter %d generated %d chunk file(s)", idx, len(audio_files))

                        if all_full_story_chunks is not None:
                            all_full_story_chunks.extend(audio_files)
                            chunk_dirs_to_cleanup.append(chunk_dir)

                        slug = slugify_filename(chapter.get('title'), slug_default)
                        output_filename = f"{slug}.{output_format}"
                        output_path = chapter_dir / output_filename

                        if review_mode:
                            chapter_index = idx - 1  # 0-indexed to match chunk.chapter_index
                            if chapter_index not in _restored_chapter_indices:
                                rel_chunk_dir = os.path.relpath(chunk_dir, job_dir)
                                rel_chapter_dir = os.path.relpath(chapter_dir, job_dir)
                                rel_chunk_files = [os.path.relpath(path, job_dir) for path in audio_files]
                                review_manifest["chapters"].append({
                                    "index": chapter_index,
                                    "title": chapter['title'],
                                    "chunk_dir": rel_chunk_dir,
                                    "chunk_files": rel_chunk_files,
                                    "chapter_dir": rel_chapter_dir,
                                    "output_filename": output_filename,
                                })
                                review_manifest["chunk_dirs_to_cleanup"].append(rel_chunk_dir)
                        else:
                            # Collect merge task for parallel processing
                            merge_tasks.append({
                                "idx": idx,
                                "title": chapter['title'],
                                "audio_files": audio_files,
                                "output_path": output_path,
                                "chapter_dir": chapter_dir,
                                "chunk_dir": chunk_dir,
                                "relative_path": Path(chapter_dir.name) / output_filename
                            })
                    
                    # Phase 2: Process merges in parallel
                    if merge_tasks and not review_mode:
                        merge_chunk_offset = 0
                        total_merge_tasks = len(merge_tasks)
                        completed_merges = [0]  # Use list for mutable shared state in threads
                        
                        def merge_task_wrapper(task):
                            """Wrapper function for parallel merge execution"""
                            if cancel_flags.get(job_id, False):
                                raise JobCancelled()
                            
                            idx = task["idx"]
                            title = task["title"]
                            audio_files = task["audio_files"]
                            output_path = task["output_path"]
                            chapter_dir = task["chapter_dir"]
                            chunk_dir = task["chunk_dir"]
                            
                            # Calculate offset for this task
                            task_offset = merge_chunk_offset + sum(len(t["audio_files"]) for t in merge_tasks if t["idx"] < idx)
                            
                            if job_log:
                                job_log.info("Merging chapter %d ('%s'): %d chunks -> %s",
                                             idx, title, len(audio_files), output_path)
                            
                            merger.merge_wav_files(
                                input_files=audio_files,
                                output_path=str(output_path),
                                format=output_format,
                                cleanup_chunks=not generate_full_story,
                                progress_callback=lambda ratio, offset=task_offset, count=len(audio_files): (
                                    update_post_process_progress(offset, count, ratio)
                                ),
                            )
                            
                            if job_log:
                                job_log.info("Merge complete: %s (exists=%s)", output_path.name, output_path.exists())
                            
                            # Update progress and cleanup
                            update_progress(0)
                            update_post_process(len(audio_files))
                            with queue_lock:
                                completed_merges[0] += 1
                            
                            # Cleanup empty chunk directory
                            if chunk_dir.exists() and not generate_full_story:
                                try:
                                    chunk_dir.rmdir()
                                except OSError:
                                    pass
                            
                            return task
                        
                        # Execute merges in parallel using ThreadPoolExecutor
                        # Use CPU count for dynamic worker allocation, capped at total tasks
                        max_workers = min(os.cpu_count() or 4, total_merge_tasks)
                        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                            # Submit all merge tasks
                            future_to_task = {executor.submit(merge_task_wrapper, task): task for task in merge_tasks}
                            
                            # Wait for all to complete
                            for future in concurrent.futures.as_completed(future_to_task):
                                try:
                                    task = future.result()
                                    # Append to chapter_outputs in original order
                                    chapter_outputs.append({
                                        "index": task["idx"],
                                        "title": task["title"],
                                        "file_url": f"/static/audio/{job_id}/{task['relative_path'].as_posix()}",
                                        "relative_path": task["relative_path"].as_posix()
                                    })
                                except Exception as e:
                                    logger.error(f"Merge task failed: {e}")
                                    raise
            else:
                if not review_mode:
                    init_post_process(total_chunks)
                    merge_chunk_offset = 0
                chunk_dir = job_dir / "chunks"
                job_log.info("Generating audio chunks (single section)")
                audio_files = generate_chunks(0, text, chunk_dir)
                if not audio_files:
                    job_log.error("generate_chunks returned no files — raising ValueError")
                    raise ValueError("Unable to generate audio chunks")
                job_log.info("Generated %d chunk file(s)", len(audio_files))
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
                    if job_log:
                        job_log.info("Merging full story: %d chunks -> %s", len(audio_files), output_file)
                    merger.merge_wav_files(
                        input_files=audio_files,
                        output_path=str(output_file),
                        format=output_format,
                        progress_callback=lambda ratio, offset=merge_chunk_offset, count=len(audio_files): (
                            update_post_process_progress(offset, count, ratio)
                        ),
                    )
                    if job_log:
                        job_log.info("Merge complete: %s (exists=%s)", output_file.name, output_file.exists())
                    update_progress(0)
                    update_post_process(len(audio_files))
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
                format=output_format,
                progress_callback=lambda ratio, offset=merge_chunk_offset, count=len(all_full_story_chunks): (
                    update_post_process_progress(offset, count, ratio)
                ),
            )
            update_progress(0)
            update_post_process(len(all_full_story_chunks))
            merge_chunk_offset += len(all_full_story_chunks)

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
            write_json_atomic(manifest_path, review_manifest)
            chunks_meta_path = job_dir / "chunks_metadata.json"
            _tm_for_meta = (jobs.get(job_id) or {}).get("timing_metrics")
            chunks_meta = {
                "engine": engine_name,
                "created_at": datetime.now().isoformat(),
                "chunks": job_chunks,
            }
            if _tm_for_meta:
                chunks_meta["timing_metrics"] = _tm_for_meta
            write_json_atomic(chunks_meta_path, chunks_meta)
            
            # Auto-finish: merge audio and complete the job (review happens in library)
            with queue_lock:
                job_entry = jobs.get(job_id)
                if job_entry:
                    job_entry['review_manifest'] = manifest_path.name
                    job_entry['chapter_mode'] = split_by_chapter
                    job_entry['full_story_requested'] = generate_full_story
            
            _merge_review_job(job_id, jobs.get(job_id), review_manifest)
            with queue_lock:
                jobs[job_id]['timing_metrics'] = timing.snapshot(finished=True)
            _persist_job_state(job_id, force=True)
            _persist_chunks_metadata(job_id, job_dir)
            logger.info(f"Job {job_id} auto-finished and moved to library for chunk review")
            job_log.info("Job auto-finished in review mode — %d total chunks written", len(job_chunks))
            job_log.info("review_manifest.json and chunks_metadata.json saved to: %s", job_dir)
            return

        if not chapter_outputs:
            raise ValueError("No audio outputs were generated")

        metadata = {
            "chapter_mode": split_by_chapter,
            "book_mode": book_mode,
            "output_format": output_format,
            "chapters": chapter_outputs,
            "chapter_count": chapter_count,
            "book_count": book_count,
            "books": chapter_outputs if book_mode else [],
            "full_story": full_story_entry,
            "crossfade_duration": float(config.get('crossfade_duration', 0) or 0),
            "intro_silence_ms": int(max(0, config.get('intro_silence_ms', 0) or 0)),
            "inter_chunk_silence_ms": int(max(0, config.get('inter_chunk_silence_ms', 0) or 0)),
            "output_bitrate_kbps": int(config.get('output_bitrate_kbps') or 0),
            "acx_compliance": bool(config.get('acx_compliance', False)),
            "word_replacements": word_replacements,
        }
        save_job_metadata(job_dir, metadata)
        
        job_end_time = datetime.now()
        timing_metrics = timing.snapshot(finished=True)

        # Update job as completed
        with queue_lock:
            jobs[job_id]['status'] = 'completed'
            jobs[job_id]['progress'] = 100
            jobs[job_id]['processed_chunks'] = total_chunks
            jobs[job_id]['total_chunks'] = total_chunks
            jobs[job_id]['eta_seconds'] = 0
            jobs[job_id]['post_process_percent'] = 100
            jobs[job_id]['post_process_active'] = False
            primary_output = full_story_entry or (chapter_outputs[0] if chapter_outputs else None)
            jobs[job_id]['output_file'] = primary_output['file_url'] if primary_output else ''
            jobs[job_id]['chapter_outputs'] = chapter_outputs
            jobs[job_id]['chapter_mode'] = split_by_chapter
            jobs[job_id]['full_story_requested'] = generate_full_story
            jobs[job_id]['resume_from_chunk_index'] = total_chunks
            if full_story_entry:
                jobs[job_id]['full_story'] = full_story_entry
            jobs[job_id]['completed_at'] = job_end_time.isoformat()
            jobs[job_id]['timing_metrics'] = timing_metrics
        _persist_job_state(job_id, force=True)

        # Also write timing_metrics into chunks_metadata.json so the library can read it from disk.
        try:
            _cmeta_path = job_dir / "chunks_metadata.json"
            if _cmeta_path.exists():
                with _cmeta_path.open("r", encoding="utf-8") as _fh:
                    _cmeta = json.load(_fh)
                _cmeta["timing_metrics"] = timing_metrics
                with _cmeta_path.open("w", encoding="utf-8") as _fh:
                    json.dump(_cmeta, _fh, indent=2)
        except Exception as _e:
            logger.warning("Could not write timing_metrics to chunks_metadata.json: %s", _e)

        logger.info(f"Job {job_id} completed successfully with {len(chapter_outputs)} output file(s)")
        job_log.info("JOB COMPLETED — %d output file(s)  total_time=%.1fs  chunks=%d",
                     len(chapter_outputs),
                     timing_metrics.get('total_seconds', 0),
                     timing_metrics.get('chunk_count', 0))
        for _out in chapter_outputs:
            job_log.info("  output: %s", _out.get('relative_path', ''))
        
        # Optional VRAM cleanup after job completion
        if config.get("cleanup_vram_after_job", False):
            _cleanup_engine_vram(engine_name)
        
    except JobPaused:
        logger.info(f"Job {job_id} paused – stopping after current chunk")
        if job_log:
            job_log.info("JOB PAUSED at chunk %d / %d", processed_chunks, total_chunks)
        # Save the partial review_manifest so chapter/book entries before the pause
        # are preserved and can be restored when the job is resumed.
        if review_mode:
            try:
                _partial_manifest_path = job_dir / "review_manifest_partial.json"
                # Snapshot all_full_story_chunks as relative paths
                _rel_full_story = [
                    os.path.relpath(p, job_dir) for p in (all_full_story_chunks or [])
                ]
                _partial_to_save = dict(review_manifest)
                _partial_to_save["all_full_story_chunks"] = _rel_full_story
                with _partial_manifest_path.open("w", encoding="utf-8") as _fh:
                    json.dump(_partial_to_save, _fh, indent=2)
                logger.info(
                    "Job %s: Saved partial review_manifest — %d chapters, %d books",
                    job_id, len(review_manifest.get("chapters") or []), len(review_manifest.get("books") or []),
                )
            except Exception as _e:
                logger.warning("Job %s: Could not save partial review_manifest: %s", job_id, _e)
        with queue_lock:
            job_entry = jobs.get(job_id)
            if job_entry:
                job_entry['status'] = 'paused'
                job_entry['paused_at'] = datetime.now().isoformat()
                job_entry['timing_metrics'] = timing.snapshot()
                job_entry['eta_seconds'] = None
                job_entry['last_update'] = datetime.now().isoformat()
        _persist_job_state(job_id, force=True)
        _persist_chunks_metadata(job_id, job_dir)
        return
    except JobCancelled:
        logger.info(f"Job {job_id} cancelled – halting synthesis")
        if job_log:
            job_log.info("JOB CANCELLED at chunk %d / %d", processed_chunks, total_chunks)
        with queue_lock:
            job_entry = jobs.get(job_id)
            if job_entry:
                job_entry['status'] = 'cancelled'
                if 'timing' in locals():
                    job_entry['timing_metrics'] = timing.snapshot()
                job_entry['eta_seconds'] = None
                job_entry['last_update'] = datetime.now().isoformat()
        _persist_job_state(job_id, force=True)
        _persist_chunks_metadata(job_id, job_dir)
        return
    except Exception as e:
        logger.error(f"Error in job {job_id}: {e}", exc_info=True)
        if job_log:
            job_log.error("JOB FAILED: %s", e, exc_info=True)
        with queue_lock:
            job_entry = jobs[job_id]
            job_entry['status'] = 'interrupted' if processed_chunks > 0 else 'failed'
            job_entry['error'] = str(e)
            job_entry['interrupted_at'] = datetime.now().isoformat()
            if 'timing' in locals():
                job_entry['timing_metrics'] = timing.snapshot()
            if processed_chunks > 0:
                job_entry['last_completed_chunk_index'] = processed_chunks - 1
                job_entry['resume_from_chunk_index'] = processed_chunks
        _persist_job_state(job_id, force=True)
        _persist_chunks_metadata(job_id, job_dir)
        raise
    finally:
        cancel_flags.pop(job_id, None)
        cancel_events.pop(job_id, None)
        pause_flags.pop(job_id, None)
        if job_log is not None and _job_log_handler is not None:
            try:
                job_log.removeHandler(_job_log_handler)
                _job_log_handler.close()
            except Exception:
                pass


def _prune_qwen3_voice_design_tasks(max_age_seconds: int = 3600) -> None:
    """Bound abandoned preview results without touching active generations."""
    cutoff = datetime.now() - timedelta(seconds=max_age_seconds)
    removed = []
    with queue_lock:
        for task_id, entry in list(jobs.items()):
            if entry.get("job_type") not in {
                "qwen3_voice_design_preview", "qwen3_voice_design_save",
                "breeze_voice_design_preview", "breeze_voice_design_save",
            }:
                continue
            if entry.get("status") not in {"completed", "failed", "cancelled", "interrupted"}:
                continue
            timestamp = entry.get("completed_at") or entry.get("created_at") or ""
            try:
                expired = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00")).replace(tzinfo=None) < cutoff
            except (TypeError, ValueError):
                expired = False
            if expired:
                jobs.pop(task_id, None)
                removed.append(task_id)
    if removed:
        try:
            with _get_jobs_db_connection() as conn:
                conn.executemany("DELETE FROM jobs WHERE job_id=?", [(task_id,) for task_id in removed])
                conn.commit()
        except Exception as exc:
            logger.warning("Unable to prune acknowledged voice-design task rows: %s", exc)


def _enqueue_qwen3_voice_design_task(task_type: str, payload: Dict[str, Any]) -> str:
    _prune_qwen3_voice_design_tasks()
    start_worker_thread()
    job_id = str(uuid.uuid4())
    job_entry = {
        "status": "queued",
        "progress": 0,
        "created_at": datetime.now().isoformat(),
        "job_type": task_type,
        "title": "Qwen3 VoiceDesign",
    }
    with queue_lock:
        jobs[job_id] = job_entry
    job_payload = {
        "job_id": job_id,
        "job_type": task_type,
        "payload": payload,
    }
    if task_type == "qwen3_voice_design_preview":
        job_payload["config"] = load_config()
    job_queue.put(job_payload)
    return job_id


def _enqueue_breeze_voice_design_task(task_type: str, payload: Dict[str, Any]) -> str:
    _prune_qwen3_voice_design_tasks()
    start_worker_thread()
    job_id = str(uuid.uuid4())
    job_entry = {
        "status": "queued",
        "progress": 0,
        "created_at": datetime.now().isoformat(),
        "job_type": task_type,
        "title": "Breeze TTS 2 Voice Design",
    }
    with queue_lock:
        jobs[job_id] = job_entry
    job_queue.put({
        "job_id": job_id,
        "job_type": task_type,
        "payload": payload,
        **({"config": load_config()} if task_type == "breeze_voice_design_preview" else {}),
    })
    return job_id


def process_qwen3_voice_design_preview_task(job_data: Dict[str, Any]) -> None:
    """Process a queued Qwen3 VoiceDesign preview request."""
    job_id = job_data["job_id"]
    payload = job_data.get("payload") or {}
    config = job_data.get("config") or load_config()
    try:
        result = None
        last_error = None
        original_seed = payload.get("seed")
        for attempt in range(VOICE_DESIGN_MAX_ATTEMPTS):
            attempt_payload = dict(payload)
            if attempt:
                try:
                    retry_seed = (int(original_seed) + attempt) & 0x7fffffff
                except (TypeError, ValueError):
                    retry_seed = uuid.uuid4().int & 0x7fffffff
                attempt_payload["seed"] = retry_seed
                logger.warning(
                    "Retrying Qwen3 VoiceDesign task %s with seed %s after: %s",
                    job_id,
                    retry_seed,
                    last_error,
                )
            try:
                result = _generate_voice_design_preview(attempt_payload, config)
                result["attempts"] = attempt + 1
                break
            except Exception as exc:
                last_error = exc
                _cleanup_qwen_voice_design_generation(force_cuda=True)
        if result is None:
            raise last_error or RuntimeError("Qwen3 VoiceDesign generation failed.")
        result["task_id"] = job_id
        with queue_lock:
            job_entry = jobs.get(job_id)
            if job_entry:
                job_entry["status"] = "completed"
                job_entry["progress"] = 100
                job_entry["completed_at"] = datetime.now().isoformat()
                job_entry["result"] = result
        _persist_job_state(job_id, force=True)
    except Exception as exc:
        with queue_lock:
            job_entry = jobs.get(job_id)
            if job_entry:
                job_entry["status"] = "failed"
                job_entry["error"] = str(exc)
        _persist_job_state(job_id, force=True)
        raise
    finally:
        _cleanup_qwen_voice_design_generation()


def process_breeze_voice_design_preview_task(job_data: Dict[str, Any]) -> None:
    """Process a queued Breeze TTS 2 reference-free voice-design preview."""
    job_id = job_data["job_id"]
    payload = job_data.get("payload") or {}
    config = job_data.get("config") or load_config()
    try:
        result = _generate_breeze_voice_design_preview(payload, config)
        result["task_id"] = job_id
        with queue_lock:
            job_entry = jobs.get(job_id)
            if job_entry:
                job_entry["status"] = "completed"
                job_entry["progress"] = 100
                job_entry["completed_at"] = datetime.now().isoformat()
                job_entry["result"] = result
        _persist_job_state(job_id, force=True)
    except Exception as exc:
        with queue_lock:
            job_entry = jobs.get(job_id)
            if job_entry:
                job_entry["status"] = "failed"
                job_entry["error"] = str(exc)
        _persist_job_state(job_id, force=True)
        raise


def process_qwen3_voice_design_save_task(job_data: Dict[str, Any]) -> None:
    """Process a queued Qwen3 VoiceDesign save request."""
    job_id = job_data["job_id"]
    payload = job_data.get("payload") or {}
    try:
        result = _save_voice_design_payload(payload)
        with queue_lock:
            job_entry = jobs.get(job_id)
            if job_entry:
                job_entry["status"] = "completed"
                job_entry["progress"] = 100
                job_entry["completed_at"] = datetime.now().isoformat()
                job_entry["result"] = result
        _persist_job_state(job_id, force=True)
    except Exception as exc:
        with queue_lock:
            job_entry = jobs.get(job_id)
            if job_entry:
                job_entry["status"] = "failed"
                job_entry["error"] = str(exc)
        _persist_job_state(job_id, force=True)
        raise


def _serialize_gpu_generation(function):
    @wraps(function)
    def guarded(*args, **kwargs):
        with gpu_generation_lifecycle_lock:
            return function(*args, **kwargs)
    return guarded


@_serialize_gpu_generation
def _generate_omnivoice_design_preview(payload: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    """Generate an OmniVoice voice-design preview clip and return base64 audio."""
    if not omnivoice_available():
        raise ImportError(f"OmniVoice design engine not available. {omnivoice_unavailable_reason()} Install OmniVoice from Settings.")
    instruct = (payload.get("instruct") or "").strip()
    text = (payload.get("text") or "").strip()
    if not instruct:
        raise ValueError("Voice instruction string is required.")
    if not text:
        raise ValueError("Sample text is required.")
    engine = get_tts_engine("omnivoice_design", config)
    audio = engine.generate_audio(text, voice=instruct)
    if audio is None or len(audio) == 0:
        raise RuntimeError("OmniVoice design generated no audio.")
    import numpy as np, io, wave
    sample_rate = getattr(engine, "sample_rate", 24000)
    if audio.dtype != np.int16:
        audio = (np.clip(audio, -1.0, 1.0) * 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(audio.tobytes())
    audio_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    return {"audio_base64": audio_b64}


def process_omnivoice_design_preview_task(job_data: Dict[str, Any]) -> None:
    job_id = job_data["job_id"]
    payload = job_data.get("payload") or {}
    config = job_data.get("config") or load_config()
    try:
        result = _generate_omnivoice_design_preview(payload, config)
        with queue_lock:
            job_entry = jobs.get(job_id)
            if job_entry:
                job_entry["status"] = "completed"
                job_entry["progress"] = 100
                job_entry["completed_at"] = datetime.now().isoformat()
                job_entry["result"] = result
    except Exception as exc:
        with queue_lock:
            job_entry = jobs.get(job_id)
            if job_entry:
                job_entry["status"] = "failed"
                job_entry["error"] = str(exc)
        raise


def process_omnivoice_design_save_task(job_data: Dict[str, Any]) -> None:
    job_id = job_data["job_id"]
    payload = job_data.get("payload") or {}
    try:
        result = _save_voice_design_payload(payload)
        with queue_lock:
            job_entry = jobs.get(job_id)
            if job_entry:
                job_entry["status"] = "completed"
                job_entry["progress"] = 100
                job_entry["completed_at"] = datetime.now().isoformat()
                job_entry["result"] = result
    except Exception as exc:
        with queue_lock:
            job_entry = jobs.get(job_id)
            if job_entry:
                job_entry["status"] = "failed"
                job_entry["error"] = str(exc)
        raise


def _enqueue_omnivoice_design_task(task_type: str, payload: Dict[str, Any]) -> str:
    start_worker_thread()
    job_id = str(uuid.uuid4())
    job_entry = {
        "job_id": job_id,
        "status": "queued",
        "progress": 0,
        "created_at": datetime.now().isoformat(),
        "completed_at": None,
        "error": None,
        "result": None,
        "job_type": task_type,
        "payload": payload,
    }
    if task_type == "omnivoice_design_preview":
        job_entry["config"] = load_config()
    with queue_lock:
        jobs[job_id] = job_entry
    job_queue.put(job_entry)
    return job_id


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


def _redact_config_secrets(config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Return a job-safe config snapshot without persisted API credentials."""
    snapshot = copy.deepcopy(config or {})
    for key in SECRET_CONFIG_KEYS:
        if key in snapshot:
            snapshot[key] = ""
    for profile in snapshot.get("llm_backup_profiles") or []:
        if isinstance(profile, dict) and "api_key" in profile:
            profile["api_key"] = ""
    return snapshot


def _hydrate_config_secrets(config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Merge current local credentials into a redacted runtime snapshot."""
    hydrated = copy.deepcopy(config or {})
    current = load_config()
    for key in SECRET_CONFIG_KEYS:
        if not hydrated.get(key) and current.get(key):
            hydrated[key] = current[key]
    current_profiles = {
        str(profile.get("id") or ""): profile
        for profile in (current.get("llm_backup_profiles") or [])
        if isinstance(profile, dict) and profile.get("id")
    }
    for profile in hydrated.get("llm_backup_profiles") or []:
        if not isinstance(profile, dict) or profile.get("api_key"):
            continue
        current_profile = current_profiles.get(str(profile.get("id") or ""))
        if current_profile and current_profile.get("api_key"):
            profile["api_key"] = current_profile["api_key"]
    return hydrated


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


def _load_external_voice_archives() -> set:
    if not EXTERNAL_VOICES_ARCHIVE_FILE.exists():
        return set()
    try:
        with EXTERNAL_VOICES_ARCHIVE_FILE.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
            if isinstance(data, list):
                return {item for item in data if isinstance(item, str)}
    except (json.JSONDecodeError, OSError) as exc:
        logger.error("Unable to read external voice archive list: %s", exc)
    return set()


def _save_external_voice_archives(archives: set) -> None:
    EXTERNAL_VOICES_ARCHIVE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with EXTERNAL_VOICES_ARCHIVE_FILE.open("w", encoding="utf-8") as handle:
        json.dump(sorted(archives), handle, indent=2)


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


def _auto_register_voice_prompt_files() -> int:
    """Scan data/voice_prompts/ and add registry entries for any audio files
    not already tracked in chatterbox_voices.json.

    Returns the number of newly registered entries.
    """
    existing_entries = _load_chatterbox_voice_entries()
    registered_files = {e.get("file_name") for e in existing_entries if e.get("file_name")}

    new_entries = []
    for path in sorted(VOICE_PROMPT_DIR.glob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in VOICE_PROMPT_EXTENSIONS:
            continue
        if path.name in registered_files:
            continue
        # Build a friendly display name from the filename stem
        display_name = path.stem.replace("_", " ").replace("-", " ").title()
        entry = {
            "id": str(uuid.uuid4()),
            "name": display_name,
            "file_name": path.name,
            "created_at": datetime.now().isoformat(),
            "gender": None,
            "language": None,
            "description": None,
            "archived": False,
            "size_bytes": None,
            "duration_seconds": None,
        }
        new_entries.append(entry)
        logger.info("Auto-registered voice prompt: %s -> %s", path.name, display_name)

    if new_entries:
        _save_chatterbox_voice_entries(existing_entries + new_entries)
        logger.info("Auto-registered %d voice prompt file(s) from disk", len(new_entries))

    return len(new_entries)


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
    transcript = _get_voice_prompt_transcript(file_path) if exists and file_path else ""
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
        "description": entry.get("description"),
        "voice_design": entry.get("voice_design"),
        "transcript": transcript,
        "transcript_available": bool(transcript),
        "archived": bool(entry.get("archived", False)),
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


@app.route('/api/pocket-tts/voices', methods=['GET'])
def get_pocket_tts_voices():
    """Return built-in Pocket TTS preset voices."""
    return jsonify({
        "success": True,
        "voices": POCKET_TTS_PRESET_VOICES,
    })


@app.route('/api/pocket-tts/huggingface-access', methods=['POST'])
def verify_pocket_tts_huggingface_access():
    """Verify that a Hugging Face token can read Pocket TTS gated weights."""
    payload = request.get_json(silent=True) or {}
    token = str(payload.get("token") or load_config().get("huggingface_token") or "").strip()
    if not token:
        return jsonify({
            "success": False,
            "error": "Enter a Hugging Face access token first.",
        }), 400
    try:
        from huggingface_hub import get_hf_file_metadata, hf_hub_url
        from huggingface_hub.errors import HfHubHTTPError

        model_url = hf_hub_url("kyutai/pocket-tts", "tts_b6369a24.safetensors")
        get_hf_file_metadata(model_url, token=token, timeout=15)
        return jsonify({
            "success": True,
            "message": "Access confirmed. Pocket TTS voice-cloning weights are available to this token.",
        })
    except HfHubHTTPError as exc:
        status_code = getattr(getattr(exc, "response", None), "status_code", None)
        if status_code in {401, 403}:
            message = (
                "Access was denied. Sign in to Hugging Face, accept the Pocket TTS model conditions, "
                "then create a read or fine-grained token for kyutai/pocket-tts."
            )
            return jsonify({"success": False, "error": message}), 403
        return jsonify({"success": False, "error": f"Hugging Face access check failed: {exc}"}), 502
    except Exception as exc:
        logger.warning("Pocket TTS Hugging Face access check failed: %s", exc)
        return jsonify({"success": False, "error": f"Hugging Face access check failed: {exc}"}), 502


@app.route('/api/azure-speech/voices', methods=['GET', 'POST'])
def get_azure_speech_voices():
    """Validate Azure credentials and return the region-specific voice catalog."""
    data = (request.get_json(silent=True) or {}) if request.method == 'POST' else {}
    config = load_config()
    api_key = (
        data.get('key')
        or data.get('subscription_key')
        or config.get('azure_speech_key')
        or ''
    ).strip()
    region = (data.get('region') or config.get('azure_speech_region') or '').strip().lower()
    force = bool(data.get('force')) or request.args.get('force', '').lower() in {'1', 'true', 'yes'}

    if not api_key:
        return jsonify({"success": False, "error": "Azure Speech resource key is required."}), 400
    if not region:
        return jsonify({"success": False, "error": "Azure Speech region is required."}), 400

    now = time.time()
    credential_fingerprint = hashlib.sha256(api_key.encode('utf-8')).hexdigest()[:16]
    cache_key = f"{region}:{credential_fingerprint}"
    if not force:
        with azure_voice_cache_lock:
            cached = azure_voice_cache.get(cache_key)
            if cached and now - cached.get("timestamp", 0) < 6 * 60 * 60:
                return jsonify({
                    "success": True,
                    "region": region,
                    "voices": cached.get("voices", []),
                    "cached": True,
                })

    try:
        engine = AzureSpeechEngine(
            subscription_key=api_key,
            region=region,
            timeout=int(config.get('azure_speech_timeout') or 60),
            requests_per_minute=0,
        )
        voices = engine.list_voices()
    except AzureSpeechError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception as exc:  # pragma: no cover - defensive network failure path
        logger.error("Failed to load Azure Speech voices: %s", exc, exc_info=True)
        return jsonify({"success": False, "error": "Unable to load Azure Speech voices."}), 502

    with azure_voice_cache_lock:
        azure_voice_cache[cache_key] = {"timestamp": now, "voices": voices}
    return jsonify({
        "success": True,
        "region": region,
        "voices": voices,
        "cached": False,
    })


@app.route('/api/edge-tts/voices', methods=['GET', 'POST'])
def get_edge_tts_voices():
    """Return the current Edge voice catalog without using a static voice list."""
    data = (request.get_json(silent=True) or {}) if request.method == 'POST' else {}
    force = bool(data.get('force')) or request.args.get('force', '').lower() in {'1', 'true', 'yes'}
    if not isolated_engine_available("edge_tts"):
        return jsonify({
            "success": False,
            "error": (
                "Edge TTS is not installed. Run install-update.bat, then restart TTS-Story."
            ),
        }), 503

    now = time.time()
    if not force:
        with edge_voice_cache_lock:
            if now - float(edge_voice_cache.get("timestamp") or 0) < 6 * 60 * 60:
                return jsonify({
                    "success": True,
                    "voices": edge_voice_cache.get("voices") or [],
                    "cached": True,
                    "experimental": True,
                })
    try:
        engine = get_engine("edge_tts", default_voice=load_config().get('edge_tts_default_voice'))
        voices = engine.list_voices()
    except EdgeTTSError as exc:
        return jsonify({"success": False, "error": str(exc)}), 502
    except Exception as exc:  # pragma: no cover - defensive network failure path
        logger.error("Failed to load Edge TTS voices: %s", exc, exc_info=True)
        return jsonify({"success": False, "error": "Unable to load Edge TTS voices."}), 502

    with edge_voice_cache_lock:
        edge_voice_cache.update({"timestamp": now, "voices": voices})
    return jsonify({
        "success": True,
        "voices": voices,
        "cached": False,
        "experimental": True,
    })


@app.route('/api/breeze-api/catalog', methods=['GET', 'POST'])
def breeze_api_catalog():
    config = load_config()
    data = request.get_json(silent=True) or {}
    if "api_key" in data:
        config["breeze_api_key"] = data["api_key"]
    try:
        return jsonify(success=True, **_create_engine("breeze_api", config).catalog())
    except BreezeAPIError as exc:
        return jsonify(success=False, error=str(exc)), 400
    except (ValueError, KeyError):
        return jsonify(success=False, error="Unable to load Breeze catalog. Check the API key, network and account access."), 400


def _breeze_production_progress(job_id, message):
    if cancel_flags.get(job_id):
        raise JobCancelled()
    if pause_flags.get(job_id):
        raise JobPaused()
    with queue_lock:
        entry = jobs.get(job_id)
        if entry is not None:
            entry['breeze_voice_status'] = message
    logger.info('Job %s: %s', job_id, message)


@app.route('/api/breeze-api/productions', methods=['GET'])
def breeze_api_productions():
    return jsonify(success=True, productions=BREEZE_PRODUCTIONS.list())


@app.route('/api/breeze-api/productions/<job_id>/release', methods=['POST'])
def breeze_api_release_production(job_id):
    if not _engine_management_request_allowed():
        return _engine_management_denied('Production voice removal')
    data = request.get_json(silent=True) or {}
    if data.get('confirm_release') is not True:
        return jsonify(success=False, error='Confirm that the production is delivered/approved and paid, or deliberately abandoned, before releasing its voices.'), 400
    with queue_lock:
        entry = jobs.get(job_id) or {}
        if entry.get('status') in {'queued', 'processing', 'pausing', 'paused', 'interrupted'} or _has_active_regen_tasks(entry):
            return jsonify(success=False, error='Finish or cancel this job and its regeneration tasks before releasing voices.'), 409
    try:
        result = BREEZE_PRODUCTIONS.release(job_id, _create_engine('breeze_api', load_config()))
        return jsonify(success=True, production=result)
    except (ProductionError, BreezeAPIError, OSError) as exc:
        return jsonify(success=False, error=str(exc)), 400


@app.route('/api/breeze-api/productions/<job_id>/recover', methods=['POST'])
def breeze_api_recover_production(job_id):
    if not _engine_management_request_allowed():
        return _engine_management_denied('Production voice recovery')
    data = request.get_json(silent=True) or {}
    with queue_lock:
        entry = jobs.get(job_id) or {}
        if entry.get('status') in {'queued', 'processing', 'pausing'} or _has_active_regen_tasks(entry):
            return jsonify(success=False, error='Pause or stop the job and its regeneration tasks before recovery.'), 409
    try:
        result = BREEZE_PRODUCTIONS.recover(job_id, str(data.get('sample_key') or ''),
            _create_engine('breeze_api', load_config()), confirm_absent=data.get('confirm_absent') is True)
        return jsonify(success=True, **result)
    except (ProductionError, BreezeAPIError, OSError, ValueError) as exc:
        return jsonify(success=False, error=str(exc)), 400


@app.route('/api/breeze-api/clone', methods=['POST'])
def breeze_api_clone():
    data = request.get_json(silent=True) or {}
    if data.get("consent") is not True:
        return jsonify(success=False, error="Confirm rights and consent before uploading a voice sample."), 400
    root = VOICE_PROMPT_DIR.resolve()
    path = (root / str(data.get("file_name") or "")).resolve()
    if path.parent != root or not path.is_file():
        return jsonify(success=False, error="Select an existing voice-library sample."), 400
    language = str(data.get("language") or "en")
    if not re.fullmatch(r"[a-z]{2}", language):
        return jsonify(success=False, error="Use a two-letter language code, such as en."), 400
    try:
        result = _create_engine("breeze_api", load_config()).clone_preview(path, str(data.get("name") or path.stem), language)
        return jsonify(success=True, **result)
    except (BreezeAPIError, ValueError):
        return jsonify(success=False, error="Breeze could not create the clone. Check sample format (WAV/MP3, 3+ seconds, ≤5 MB), credits and account permissions."), 400


@app.route('/api/breeze-api/preview/<preview_id>')
def breeze_api_preview(preview_id):
    if not re.fullmatch(r"[A-Za-z0-9_-]+", preview_id):
        abort(400)
    try:
        response = _create_engine("breeze_api", load_config()).request("GET", f"/voice-previews/{preview_id}/stream")
        return Response(response.content, mimetype=response.headers.get("Content-Type", "audio/mpeg"))
    except BreezeAPIError:
        return jsonify(success=False, error="Unable to download Breeze preview."), 400


@app.route('/api/breeze-api/save-voice', methods=['POST'])
def breeze_api_save_voice():
    data = request.get_json(silent=True) or {}
    preview_id = str(data.get("preview_id") or "")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", preview_id):
        return jsonify(success=False, error="Invalid preview ID."), 400
    try:
        result = _create_engine("breeze_api", load_config()).save_preview(preview_id, str(data.get("name") or "TTS-Story voice"), str(data.get("language") or "en"))
        return jsonify(success=True, **result)
    except (BreezeAPIError, ValueError):
        return jsonify(success=False, error="Unable to save Breeze voice. Check verification requirements and available voice slots."), 400


@app.route('/api/elevenlabs/catalog', methods=['GET', 'POST'])
def get_elevenlabs_catalog():
    """Validate ElevenLabs credentials and return models, voices, and quota usage."""
    data = (request.get_json(silent=True) or {}) if request.method == 'POST' else {}
    config = load_config()
    api_key = (data.get('api_key') or config.get('elevenlabs_api_key') or '').strip()
    base_url = (
        data.get('base_url')
        or config.get('elevenlabs_base_url')
        or DEFAULT_ELEVENLABS_BASE_URL
    ).strip()
    force = bool(data.get('force')) or request.args.get('force', '').lower() in {'1', 'true', 'yes'}
    if not api_key:
        return jsonify({"success": False, "error": "An ElevenLabs API key is required."}), 400

    fingerprint = hashlib.sha256(api_key.encode('utf-8')).hexdigest()[:16]
    cache_key = f"{base_url.rstrip('/')}:{fingerprint}"
    now = time.time()
    cached_catalog = None
    if not force:
        with elevenlabs_catalog_cache_lock:
            cached = elevenlabs_catalog_cache.get(cache_key)
            if cached and now - float(cached.get("timestamp") or 0) < 30 * 60:
                cached_catalog = cached

    try:
        engine = ElevenLabsEngine(
            api_key=api_key,
            base_url=base_url,
            timeout=int(config.get('elevenlabs_timeout') or 120),
            max_parallel=int(config.get('elevenlabs_max_parallel') or 2),
        )
        if cached_catalog:
            models = cached_catalog.get("models") or []
            voices = cached_catalog.get("voices") or []
        else:
            models = engine.list_models()
            voices = engine.list_voices()
            with elevenlabs_catalog_cache_lock:
                elevenlabs_catalog_cache[cache_key] = {
                    "timestamp": now,
                    "models": models,
                    "voices": voices,
                }
        warnings = []
        try:
            subscription = engine.get_subscription()
        except ElevenLabsError as exc:
            # Restricted API keys may permit voice/model/TTS access without
            # granting the user-subscription permission. Catalog use should
            # remain available in that case.
            logger.info("ElevenLabs usage information is unavailable: %s", exc)
            subscription = {}
            warnings.append(
                "Voices and models loaded, but this API key cannot read subscription usage."
            )
    except ElevenLabsError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception as exc:  # pragma: no cover - defensive network failure path
        logger.error("Failed to load ElevenLabs catalog: %s", exc, exc_info=True)
        return jsonify({"success": False, "error": "Unable to load the ElevenLabs catalog."}), 502

    return jsonify({
        "success": True,
        "models": models,
        "voices": voices,
        "subscription": subscription,
        "warnings": warnings,
        "cached": bool(cached_catalog),
    })


@app.route('/api/openai-tts/catalog', methods=['GET'])
def get_openai_tts_catalog():
    """Return official voices plus locally configured compatible voice IDs."""
    config = load_config()
    custom = [
        value.strip() for value in str(config.get("openai_tts_custom_voices") or "").split(",")
        if value.strip()
    ]
    voice_ids = list(dict.fromkeys([*OPENAI_TTS_VOICES, *custom]))
    voices = [{
        "short_name": voice_id,
        "voice_id": voice_id,
        "display_name": voice_id.replace("_", " ").title(),
        "locale": "",
        "gender": "",
    } for voice_id in voice_ids]
    return jsonify({
        "success": True,
        "voices": voices,
        "models": [
            {"model_id": "gpt-4o-mini-tts", "name": "GPT-4o mini TTS"},
            {"model_id": "gpt-4o-mini-tts-2025-12-15", "name": "GPT-4o mini TTS (2025-12-15 snapshot)"},
            {"model_id": "tts-1", "name": "TTS-1"},
            {"model_id": "tts-1-hd", "name": "TTS-1 HD"},
        ],
        "configured_model": config.get("openai_tts_model") or DEFAULT_OPENAI_TTS_MODEL,
    })


@app.route('/api/localai-tts/catalog', methods=['GET', 'POST'])
def get_localai_tts_catalog():
    """Discover TTS-capable models and saved voice profiles from LocalAI."""
    config = load_config()
    payload = request.get_json(silent=True) or {}
    base_url = str(
        payload.get("base_url")
        or config.get("localai_tts_base_url")
        or DEFAULT_LOCALAI_TTS_BASE_URL
    ).strip()
    api_key = str(
        payload.get("api_key")
        if "api_key" in payload else config.get("localai_tts_api_key") or ""
    ).strip()
    timeout = payload.get("timeout") or config.get("localai_tts_timeout") or 180
    configured_model = str(
        payload.get("model") or config.get("localai_tts_model") or ""
    ).strip()
    consent_confirmed = bool(
        payload.get("consent_confirmed")
        if "consent_confirmed" in payload
        else config.get("localai_tts_voice_profile_consent_confirmed", False)
    )
    try:
        catalog = discover_localai_tts_catalog(
            base_url,
            api_key,
            timeout=min(int(timeout), 120),
        )
    except (LocalAITTSDiscoveryError, TypeError, ValueError) as exc:
        return jsonify({"success": False, "error": str(exc)}), 502
    selected_model = next(
        (model for model in catalog.get("models", []) if model.get("model_id") == configured_model),
        None,
    )
    model_supports_cloning = (
        selected_model.get("voice_cloning") if selected_model else None
    )
    tts_story_voices: List[Dict[str, Any]] = []
    if catalog.get("voice_profiles_supported") and model_supports_cloning is True:
        _auto_register_voice_prompt_files()
        entries = _load_chatterbox_voice_entries()
        _backfill_generated_voice_transcripts(entries)
        for entry in entries:
            if entry.get("archived"):
                continue
            serialized = _serialize_chatterbox_voice(entry)
            file_name = serialized.get("file_name")
            if not file_name or serialized.get("missing_file"):
                continue
            has_transcript = bool(serialized.get("transcript"))
            if not has_transcript:
                continue
            enabled = has_transcript and consent_confirmed
            suffix = ""
            if not consent_confirmed:
                suffix = " (rights/consent confirmation required)"
            tts_story_voices.append({
                "short_name": build_tts_story_voice_reference(file_name),
                "voice_id": build_tts_story_voice_reference(file_name),
                "display_name": f"{serialized.get('name') or Path(file_name).stem}{suffix}",
                "locale": serialized.get("language") or "",
                "gender": serialized.get("gender") or "",
                "category": "TTS-Story sample",
                "source": "tts_story",
                "transcript_available": has_transcript,
                "disabled": not enabled,
                "disabled_reason": (
                    "Confirm voice-cloning rights/consent in LocalAI TTS Settings."
                    if not consent_confirmed else ""
                ),
            })
    catalog["voices"] = [*(catalog.get("voices") or []), *tts_story_voices]
    return jsonify({
        "success": True,
        **catalog,
        "configured_model": configured_model,
        "configured_voice": config.get("localai_tts_default_voice") or "",
        "configured_language": config.get("localai_tts_default_language") or "",
        "selected_model_voice_cloning": model_supports_cloning,
        "tts_story_voice_count": len(tts_story_voices),
        "tts_story_voice_ready_count": sum(not voice["disabled"] for voice in tts_story_voices),
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
_voice_prompt_transcript_cache: Optional[Dict[str, str]] = None


def _load_voice_prompt_transcripts() -> Dict[str, str]:
    """Load cached prompt transcripts from data/voice_prompts/transcripts.json."""
    global _voice_prompt_transcript_cache
    if _voice_prompt_transcript_cache is not None:
        return _voice_prompt_transcript_cache
    transcripts_path = VOICE_PROMPT_DIR / "transcripts.json"
    if not transcripts_path.exists():
        _voice_prompt_transcript_cache = {}
        return _voice_prompt_transcript_cache
    try:
        with transcripts_path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
            _voice_prompt_transcript_cache = data.get("transcripts", {})
            return _voice_prompt_transcript_cache
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Failed to load voice prompt transcripts: %s", exc)
        _voice_prompt_transcript_cache = {}
        return _voice_prompt_transcript_cache


def _save_voice_prompt_transcripts(transcripts: Dict[str, str]) -> None:
    transcripts_path = VOICE_PROMPT_DIR / "transcripts.json"
    transcripts_path.parent.mkdir(parents=True, exist_ok=True)
    with transcripts_path.open("w", encoding="utf-8") as handle:
        json.dump({"transcripts": transcripts}, handle, indent=2, ensure_ascii=False)


def _set_voice_prompt_transcript(file_path: Path, transcript: str) -> None:
    key = _voice_prompt_transcript_key(file_path)
    if not key:
        return
    transcripts = _load_voice_prompt_transcripts()
    transcripts[key] = transcript
    _save_voice_prompt_transcripts(transcripts)


def _get_voice_prompt_transcript(file_path: Path) -> str:
    key = _voice_prompt_transcript_key(file_path)
    if not key:
        return ""
    return str(_load_voice_prompt_transcripts().get(key) or "").strip()


def _update_voice_prompt_transcript(file_path: Path, transcript: str) -> None:
    key = _voice_prompt_transcript_key(file_path)
    if not key:
        return
    transcripts = _load_voice_prompt_transcripts()
    cleaned = str(transcript or "").strip()
    if cleaned:
        transcripts[key] = cleaned
    else:
        transcripts.pop(key, None)
    _save_voice_prompt_transcripts(transcripts)


def _backfill_generated_voice_transcripts(entries: List[Dict[str, Any]]) -> int:
    """Recover exact preview text already stored with generated voice samples."""
    transcripts = _load_voice_prompt_transcripts()
    updated = 0
    for entry in entries:
        file_name = entry.get("file_name")
        preview_text = str((entry.get("voice_design") or {}).get("preview_text") or "").strip()
        if not file_name or not preview_text:
            continue
        file_path = VOICE_PROMPT_DIR / Path(file_name).name
        key = _voice_prompt_transcript_key(file_path)
        if key and not str(transcripts.get(key) or "").strip():
            transcripts[key] = preview_text
            updated += 1
    if updated:
        _save_voice_prompt_transcripts(transcripts)
    return updated


def _apply_voice_design_cleanup(audio_data, sample_rate: int):
    try:
        from src.audio_effects import AudioPostProcessor
    except Exception:  # pragma: no cover - optional dependency
        return audio_data
    try:
        sox_path = AudioPostProcessor.SOX_PATH
    except Exception:  # pragma: no cover
        return audio_data
    if not sox_path or not sox_path.exists():
        return audio_data

    input_path = None
    output_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_in:
            input_path = Path(temp_in.name)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_out:
            output_path = Path(temp_out.name)
        sf.write(str(input_path), audio_data, int(sample_rate))
        command = [
            str(sox_path),
            str(input_path),
            str(output_path),
            "fade",
            "0.01",
        ]
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "SoX cleanup failed")
        cleaned, _ = sf.read(str(output_path), dtype='float32')
        return cleaned
    except Exception as exc:
        logger.warning("SoX cleanup failed for voice design audio: %s", exc)
        return audio_data
    finally:
        if input_path:
            input_path.unlink(missing_ok=True)
        if output_path:
            output_path.unlink(missing_ok=True)


def _clean_voice_design_instruction(value: str) -> str:
    """Keep VoiceDesign instructions compact, positive, and synthesis-focused."""
    text = re.sub(r"\s+", " ", (value or "").strip())
    negative_patterns = (
        r"\bnever\s+childlike\b",
        r"\bno\s+feminine\s+resonance\b",
        r"\bnot\s+theatrical\b",
        r"\bnot\s+girlish\b",
    )
    for pattern in negative_patterns:
        text = re.sub(pattern, "", text, flags=re.IGNORECASE)
    text = re.sub(
        r"\b(?:suitable\s+)?for\s+(?:sustained\s+)?(?:an?\s+)?audiobook(?:\s+(?:dialogue|narration))?\b",
        " ",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"\baudiobook(?:\s+(?:dialogue|narration))?\b", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\bemotional(?=\s*[.,;]|$)", "delivery", text, flags=re.IGNORECASE)
    text = re.sub(
        r"\b(?:but\s+)?(?:not|never|no)\b[^,.;]*[,.;]?",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"\s*[,;]\s*[,;]+", ", ", text)
    text = re.sub(r"\s+([,.;])", r"\1", text).strip(" ,;")
    if len(text) > 150:
        text = text[:150].rsplit(" ", 1)[0].rstrip(" ,;")
    return text


def _build_qwen_voice_design_instruction(payload: Dict[str, Any]) -> tuple[str, str]:
    """Build an instruction from voice traits, never from the narrative profile."""
    structured = any(
        key in payload for key in ("voice_type", "voice_design_prompt", "required_gender")
    )
    if not structured:
        # Voice Manager supplies a complete manual instruction and remains supported.
        instruct = _clean_voice_design_instruction(payload.get("instruct") or "")
        language = (payload.get("language") or "English").strip() or "English"
        return instruct, language

    gender = (payload.get("gender") or "").strip().lower()
    if gender in {"nonbinary", "non-binary", "gender-neutral"}:
        gender = "neutral"
    if gender not in {"female", "male", "neutral"}:
        raise ValueError(
            "VoiceDesign requires an explicit Male, Female, or Neutral speaker gender. "
            "Add the gender to the speaker name or Voice Design Prompt."
        )

    source = payload.get("voice_design_prompt") or payload.get("voice_type") or ""
    gender_phrase = _voice_age_gender_prefix(gender, str(source))
    traits = _clean_voice_design_instruction(source)
    traits = re.sub(
        VOICE_DESIGN_PREFIX_PATTERN,
        " ",
        traits,
        flags=re.IGNORECASE,
    )
    traits = re.sub(
        r"\bchild[- ]like\s*\((\d{1,2}(?:\s*[-–]\s*\d{1,2})?)\s*years?\)",
        r"age \1",
        traits,
        flags=re.IGNORECASE,
    )
    traits = re.sub(r"\bchild[- ]like\b", " ", traits, flags=re.IGNORECASE)
    traits = re.sub(r"\s+", " ", traits).strip(" ,;.")
    if not traits and payload.get("voice_type"):
        traits = _clean_voice_design_instruction(str(payload.get("voice_type"))).strip(" ,;.")
    if not traits:
        raise ValueError("Voice Type or Voice Design Prompt is required.")
    expected = re.compile(rf"\b{re.escape(gender_phrase)}\b", re.IGNORECASE)
    instruct = f"{gender_phrase}. {traits}"
    instruct = _clean_voice_design_instruction(instruct)
    if not expected.search(instruct):
        raise ValueError(f'Final VoiceDesign instruction must contain "{gender_phrase}".')
    return instruct, "English"


def _ensure_voice_design_preview_length(text: str) -> str:
    """Pad unusually short custom previews so casting samples demonstrate the voice."""
    cleaned = re.sub(r"\s+", " ", (text or "").strip())
    if not cleaned:
        return cleaned
    padding = (
        "The speaker continues with clear articulation and natural pacing, moving from calm reflection "
        "through firm conviction and rising urgency to demonstrate a believable emotional range for audiobook dialogue."
    )
    while len(cleaned.split()) < MIN_VOICE_DESIGN_PREVIEW_WORDS:
        cleaned = f"{cleaned.rstrip()} {padding}"
    return cleaned


def _cleanup_qwen_voice_design_generation(*, force_cuda: bool = False) -> None:
    """Release per-preview objects while retaining the loaded Qwen model."""
    global qwen3_voice_design_generation_count
    qwen3_voice_design_generation_count += 1
    gc.collect()
    try:
        import torch
        if torch.cuda.is_available() and (
            force_cuda
            or qwen3_voice_design_generation_count % VOICE_DESIGN_CUDA_CLEANUP_INTERVAL == 0
        ):
            torch.cuda.empty_cache()
    except Exception as exc:  # pragma: no cover - defensive cleanup
        logger.debug("Qwen3 VoiceDesign cleanup skipped: %s", exc)


def _generate_voice_design_preview(payload: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    text = _ensure_voice_design_preview_length(payload.get("text") or "")
    instruct, language = _build_qwen_voice_design_instruction(payload)
    if not text:
        raise ValueError("Text is required to generate a preview.")

    generation_kwargs: Dict[str, Any] = dict(VOICE_DESIGN_CASTING_GENERATION)
    for key in (
        "temperature",
        "top_p",
        "top_k",
        "subtalker_temperature",
        "subtalker_top_p",
        "subtalker_top_k",
    ):
        value = payload.get(key)
        if value not in (None, ""):
            generation_kwargs[key] = int(value) if key.endswith("top_k") else float(value)

    try:
        seed = int(payload.get("seed"))
    except (TypeError, ValueError):
        seed = uuid.uuid4().int & 0x7fffffff
    seed = max(0, min(seed, 0x7fffffff))

    started_at = time.perf_counter()
    temporary_output = Path(tempfile.gettempdir()) / f"tts-story-qwen-{uuid.uuid4().hex}.wav"
    try:
        with gpu_inference_lock:
            worker_result = _run_isolated_qwen_voice_design({
                "id": uuid.uuid4().hex,
                "text": text,
                "instruct": instruct or "",
                "language": language,
                "seed": seed,
                "generation_kwargs": generation_kwargs,
                "output_path": str(temporary_output),
                "model_id": (config.get("qwen3_voice_design_model_id") or "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign").strip(),
                "device": (config.get("qwen3_custom_device") or "auto").strip(),
                "dtype": (config.get("qwen3_custom_dtype") or "bfloat16").strip(),
                "attention": (config.get("qwen3_custom_attn_implementation") or "flash_attention_2").strip(),
            })
        raw_audio, sr = sf.read(temporary_output, dtype="float32")
    finally:
        temporary_output.unlink(missing_ok=True)
    audio_data = _apply_voice_design_cleanup(raw_audio, int(sr))
    duration_seconds = float(len(audio_data)) / float(sr)
    if duration_seconds < MIN_VOICE_DESIGN_PREVIEW_SECONDS:
        raise RuntimeError(
            f"VoiceDesign produced a {duration_seconds:.1f}-second preview. "
            f"Casting samples must be at least {MIN_VOICE_DESIGN_PREVIEW_SECONDS:.0f} seconds; "
            "try generating the candidate again."
        )
    if duration_seconds > MAX_VOICE_DESIGN_PREVIEW_SECONDS:
        raise RuntimeError(
            f"VoiceDesign produced an abnormal {duration_seconds:.1f}-second preview. "
            "The generation likely missed its ending token and will be retried with a new seed."
        )
    buffer = io.BytesIO()
    sf.write(buffer, audio_data, int(sr), format="wav")
    wav_bytes = buffer.getvalue()
    encoded = base64.b64encode(wav_bytes).decode("ascii")
    elapsed_seconds = time.perf_counter() - started_at
    cuda_metrics = {
        key: worker_result[key]
        for key in ("cuda_allocated_mb", "cuda_reserved_mb", "cuda_peak_allocated_mb")
        if key in worker_result
    }
    logger.info(
        "Qwen3 VoiceDesign completed seed=%s duration=%.1fs elapsed=%.1fs allocated=%sMB reserved=%sMB peak=%sMB",
        seed,
        duration_seconds,
        elapsed_seconds,
        cuda_metrics.get("cuda_allocated_mb", "n/a"),
        cuda_metrics.get("cuda_reserved_mb", "n/a"),
        cuda_metrics.get("cuda_peak_allocated_mb", "n/a"),
    )
    return {
        "audio_base64": encoded,
        "mime_type": "audio/wav",
        "engine": "qwen3_voice_design",
        "cleanup_applied": True,
        "instruction": instruct,
        "preview_text": text,
        "duration_seconds": duration_seconds,
        "elapsed_seconds": elapsed_seconds,
        "language": language,
        "model": (config.get("qwen3_voice_design_model_id") or "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign").strip(),
        "sampling_parameters": generation_kwargs,
        "seed": seed,
        "wav_sha256": hashlib.sha256(wav_bytes).hexdigest(),
        **cuda_metrics,
    }


def _generate_breeze_voice_design_preview(payload: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    """Generate a reference-free Breeze casting sample in the persistent Breeze worker."""
    text = _ensure_voice_design_preview_length(payload.get("text") or "")
    instruct, language = _build_qwen_voice_design_instruction(payload)
    if not text:
        raise ValueError("Text is required to generate a preview.")
    if str(language or "English").lower() not in {"english", "chinese", "auto"}:
        raise ValueError("Breeze TTS 2 voice design currently supports English and Chinese.")
    try:
        seed = int(payload.get("seed"))
    except (TypeError, ValueError):
        seed = uuid.uuid4().int & 0x7fffffff
    seed = max(0, min(seed, 0x7fffffff))

    model_id = (config.get("breeze_tts_2_model_id") or "BreezeBlue/Breeze-TTS-2").strip()
    if config.get("breeze_tts_2_runtime") == "q8":
        model_id = "HoppouAI/Breeze-TTS-2.cpp/breeze-tts-2-q8_0.gguf"
    constructor = {
        "runtime": config.get("breeze_tts_2_runtime") or "pytorch",
        "device": (config.get("breeze_tts_2_device") or "auto").strip(),
        "model_id": model_id,
        # Keep the constructor stable so changing the candidate seed does not
        # force the persistent worker to discard and reload the model.
        "seed": int(config.get("breeze_tts_2_seed") or 42),
        "clone_cfg_scale": float(config.get("breeze_tts_2_clone_cfg_scale") or 1.0),
        "design_cfg_scale": float(config.get("breeze_tts_2_design_cfg_scale") or 4.0),
        "direction_cfg_scale": float(config.get("breeze_tts_2_direction_cfg_scale") or 4.0),
        "max_new_tokens": int(config.get("breeze_tts_2_max_new_tokens") or 1500),
        "max_seq_len": int(config.get("breeze_tts_2_max_seq_len") or 2048),
        "fast_mode": bool(config.get("breeze_tts_2_fast_mode", False)),
        "default_instruction": (config.get("breeze_tts_2_default_instruction") or "Speak clearly and naturally.").strip(),
    }
    started_at = time.perf_counter()
    temporary_output = Path(tempfile.gettempdir()) / f"tts-story-breeze-{uuid.uuid4().hex}.wav"
    try:
        with gpu_inference_lock:
            worker_result = _run_isolated_breeze_voice_design({
                "id": uuid.uuid4().hex,
                "text": text,
                "instruct": instruct,
                "seed": seed,
                "output_path": str(temporary_output),
                "constructor": constructor,
            })
        raw_audio, sr = sf.read(temporary_output, dtype="float32")
    finally:
        temporary_output.unlink(missing_ok=True)
    audio_data = _apply_voice_design_cleanup(raw_audio, int(sr))
    duration_seconds = float(len(audio_data)) / float(sr)
    if duration_seconds < MIN_VOICE_DESIGN_PREVIEW_SECONDS:
        raise RuntimeError(
            f"Breeze voice design produced a {duration_seconds:.1f}-second preview. "
            f"Casting samples must be at least {MIN_VOICE_DESIGN_PREVIEW_SECONDS:.0f} seconds; "
            "try generating the candidate again."
        )
    if duration_seconds > MAX_VOICE_DESIGN_PREVIEW_SECONDS:
        raise RuntimeError(
            f"Breeze voice design produced an abnormal {duration_seconds:.1f}-second preview."
        )
    buffer = io.BytesIO()
    sf.write(buffer, audio_data, int(sr), format="wav")
    wav_bytes = buffer.getvalue()
    elapsed_seconds = time.perf_counter() - started_at
    cuda_metrics = {
        key: worker_result[key]
        for key in ("cuda_allocated_mb", "cuda_reserved_mb", "cuda_peak_allocated_mb")
        if key in worker_result
    }
    logger.info(
        "Breeze voice design completed seed=%s duration=%.1fs elapsed=%.1fs allocated=%sMB reserved=%sMB peak=%sMB",
        seed, duration_seconds, elapsed_seconds,
        cuda_metrics.get("cuda_allocated_mb", "n/a"),
        cuda_metrics.get("cuda_reserved_mb", "n/a"),
        cuda_metrics.get("cuda_peak_allocated_mb", "n/a"),
    )
    return {
        "audio_base64": base64.b64encode(wav_bytes).decode("ascii"),
        "mime_type": "audio/wav",
        "engine": "breeze_tts_2_voice_design",
        "cleanup_applied": True,
        "instruction": instruct,
        "preview_text": text,
        "duration_seconds": duration_seconds,
        "elapsed_seconds": elapsed_seconds,
        "language": "English" if str(language).lower() == "auto" else language,
        "model": model_id,
        "sampling_parameters": {
            "cfg_scale": constructor["design_cfg_scale"],
            "max_new_tokens": constructor["max_new_tokens"],
            "fast_mode": constructor["fast_mode"],
        },
        "seed": seed,
        "wav_sha256": hashlib.sha256(wav_bytes).hexdigest(),
        **cuda_metrics,
    }


def _save_voice_design_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    name = (payload.get("name") or "").strip()
    text = (payload.get("text") or "").strip()
    gender = (payload.get("gender") or "").strip() or None
    language = (payload.get("language") or "English").strip() or "English"
    description = (payload.get("description") or "").strip() or None
    audio_base64 = payload.get("audio_base64")

    if not name:
        raise ValueError("Voice name is required.")
    if not text:
        raise ValueError("Sample text is required.")
    if not audio_base64:
        raise ValueError("Preview audio is required.")

    try:
        audio_bytes = base64.b64decode(audio_base64)
    except Exception as exc:
        raise ValueError("Invalid audio payload.") from exc

    slug = _slugify_filename(name)
    target_path = VOICE_PROMPT_DIR / f"{slug}.wav"
    counter = 1
    while target_path.exists():
        target_path = VOICE_PROMPT_DIR / f"{slug}_{counter}.wav"
        counter += 1

    audio_stream = io.BytesIO(audio_bytes)
    audio_data, sample_rate = sf.read(audio_stream, dtype='float32')
    if not payload.get("cleanup_applied"):
        audio_data = _apply_voice_design_cleanup(audio_data, int(sample_rate))
    sf.write(str(target_path), audio_data, int(sample_rate))

    duration_seconds = _measure_audio_duration(target_path)
    if not duration_seconds:
        target_path.unlink(missing_ok=True)
        raise ValueError("Unable to determine audio duration.")
    if duration_seconds < MIN_CHATTERBOX_PROMPT_SECONDS:
        target_path.unlink(missing_ok=True)
        raise ValueError(
            f"Clip is only {duration_seconds:.2f}s. Voice prompts require at least {MIN_CHATTERBOX_PROMPT_SECONDS:.0f} seconds."
        )

    entries = _load_chatterbox_voice_entries()
    entry = {
        "id": str(uuid.uuid4()),
        "name": name,
        "file_name": target_path.name,
        "created_at": datetime.utcnow().isoformat(),
        "size_bytes": target_path.stat().st_size,
        "duration_seconds": duration_seconds,
        "gender": gender,
        "language": language if language and language != "Auto" else None,
        "description": description,
        "voice_design": {
            "engine": (payload.get("engine") or "qwen3_voice_design").strip(),
            "instruction": (payload.get("instruction") or payload.get("instruct") or "").strip(),
            "preview_text": text,
            "language": language,
            "model": payload.get("model"),
            "sampling_parameters": payload.get("sampling_parameters") or {"mode": "Qwen defaults"},
            "seed": payload.get("seed"),
            "task_id": payload.get("source_task_id"),
            "candidate_group_id": payload.get("candidate_group_id"),
            "candidate_label": payload.get("candidate_label"),
            "preview_wav_sha256": payload.get("wav_sha256"),
            "wav_sha256": hashlib.sha256(target_path.read_bytes()).hexdigest(),
            "approval_status": payload.get("approval_status") or "pending",
        },
    }
    entries.append(entry)
    _save_chatterbox_voice_entries(entries)
    _set_voice_prompt_transcript(target_path, text)
    return _serialize_chatterbox_voice(entry)


def _voice_prompt_transcript_key(file_path: Path) -> Optional[str]:
    try:
        stat = file_path.stat()
    except OSError:
        return None
    key_data = f"{file_path.name}:{stat.st_size}:{stat.st_mtime}"
    return hashlib.md5(key_data.encode()).hexdigest()[:16]


@app.route('/api/voice-prompts', methods=['GET'])
def list_voice_prompts():
    """List available reference audio prompts."""
    try:
        # Load chatterbox voice registry for metadata lookup
        chatterbox_entries = _load_chatterbox_voice_entries()
        chatterbox_by_file = {e.get("file_name"): e for e in chatterbox_entries if e.get("file_name")}
        
        transcripts = _load_voice_prompt_transcripts()
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
            
            transcript_key = _voice_prompt_transcript_key(path)
            prompt_transcript = transcripts.get(transcript_key) if transcript_key else None
            prompts.append(
                {
                    "name": path.name,
                    "display": display_name,
                    "size_bytes": size_bytes,
                    "duration_seconds": duration_seconds,
                    "gender": gender,
                    "language": language,
                    "transcript": prompt_transcript,
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


@app.route('/api/voice-prompts/preview-fx', methods=['POST'])
def preview_voice_prompt_fx():
    """Preview FX on an existing voice prompt sample without regenerating audio."""
    from src.audio_effects import AudioPostProcessor, VoiceFXSettings
    data = request.json or {}
    prompt_path = (data.get("prompt_path") or "").strip()
    if not prompt_path:
        return jsonify({"success": False, "error": "prompt_path is required"}), 400

    file_name = Path(prompt_path).name
    if not file_name:
        return jsonify({"success": False, "error": "Invalid prompt_path"}), 400

    file_path = VOICE_PROMPT_DIR / file_name
    if not file_path.exists():
        return jsonify({"success": False, "error": "Audio file missing on disk."}), 404

    try:
        speed = float(data.get("speed", 1.0) or 1.0)
        pitch = float(data.get("pitch", 0.0) or 0.0)
    except (TypeError, ValueError):
        return jsonify({"success": False, "error": "Invalid pitch or speed value."}), 400

    speed = max(0.5, min(2.0, speed))
    pitch = max(-12.0, min(12.0, pitch))

    try:
        use_sox = abs(speed - 1.0) > 1e-3 or abs(pitch) > 1e-3
        sox_path = find_system_tool("sox")
        ffmpeg_path = find_system_tool("ffmpeg")
        
        # Convert MP3 to WAV if needed before SoX processing
        input_for_sox = file_path
        temp_mp3_conv = None
        if file_path.suffix.lower() == ".mp3" and ffmpeg_path:
            try:
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_out:
                    temp_mp3_conv = Path(temp_out.name)
                # Use FFmpeg to convert MP3 to WAV
                result = subprocess.run(
                    [str(ffmpeg_path), "-y", "-i", str(file_path), str(temp_mp3_conv)],
                    capture_output=True,
                    text=True
                )
                if result.returncode == 0:
                    input_for_sox = temp_mp3_conv
            except Exception:
                # If FFmpeg conversion fails, use original file
                if temp_mp3_conv:
                    temp_mp3_conv.unlink(missing_ok=True)
                temp_mp3_conv = None
        
        if use_sox and sox_path:
            output_path = None
            try:
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_out:
                    output_path = Path(temp_out.name)
                command = [str(sox_path), str(input_for_sox), str(output_path)]
                if abs(pitch) > 1e-3:
                    command += ["pitch", f"{pitch * 100:.2f}"]
                if abs(speed - 1.0) > 1e-3:
                    command += ["tempo", "-s", f"{speed:.3f}"]
                result = subprocess.run(command, capture_output=True, text=True)
                if result.returncode != 0:
                    raise RuntimeError(result.stderr.strip() or "SoX failed")
                audio_bytes = output_path.read_bytes()
            finally:
                if output_path:
                    output_path.unlink(missing_ok=True)
                if temp_mp3_conv:
                    temp_mp3_conv.unlink(missing_ok=True)
        else:
            audio_data, sample_rate = sf.read(str(file_path), dtype='float32')
            if abs(speed - 1.0) < 1e-3 and abs(pitch) < 1e-3:
                buffer = io.BytesIO()
                sf.write(buffer, audio_data, sample_rate, format='WAV')
                audio_bytes = buffer.getvalue()
            else:
                fx = VoiceFXSettings(
                    pitch_semitones=pitch,
                    speed=speed,
                    tone="neutral",
                )
                processor = AudioPostProcessor()
                processed = processor.apply(audio_data, sample_rate, fx, blend_override=0.0)
                buffer = io.BytesIO()
                sf.write(buffer, processed, sample_rate, format='WAV')
                audio_bytes = buffer.getvalue()
    except ImportError as exc:
        logger.error("Preview FX requires librosa: %s", exc)
        return jsonify({"success": False, "error": "Audio FX preview requires librosa."}), 400
    except Exception as exc:
        logger.error("Failed to preview voice prompt FX: %s", exc, exc_info=True)
        return jsonify({"success": False, "error": "Failed to process audio."}), 500

    encoded = base64.b64encode(audio_bytes).decode('ascii')
    return jsonify({
        "success": True,
        "audio_base64": encoded,
        "mime_type": "audio/wav",
    })


@app.route('/api/chatterbox-voices', methods=['GET'])
def list_chatterbox_voices():
    _auto_register_voice_prompt_files()
    entries = _load_chatterbox_voice_entries()
    _backfill_generated_voice_transcripts(entries)
    serialized = [_serialize_chatterbox_voice(entry) for entry in entries]
    return jsonify({"success": True, "voices": serialized})


@app.route('/api/chatterbox-voices', methods=['POST'])
def create_chatterbox_voice():
    name = (request.form.get("name") or "").strip()
    transcript = (request.form.get("transcript") or "").strip()
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
    if transcript:
        _set_voice_prompt_transcript(target_path, transcript)

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


def _collect_voice_files(voice_ids: List[str]) -> Tuple[List[Tuple[Path, str]], List[str]]:
    files: List[Tuple[Path, str]] = []
    missing: List[str] = []
    entries = _load_chatterbox_voice_entries()
    entries_by_id = {entry.get("id"): entry for entry in entries if entry.get("id")}

    for voice_id in voice_ids:
        if _is_external_voice_id(voice_id):
            short_name = _strip_external_voice_id(voice_id)
            file_path = EXTERNAL_VOICES_DIR / f"{short_name}.mp3"
            if file_path.exists():
                files.append((file_path, file_path.name))
            else:
                missing.append(voice_id)
            continue

        entry = entries_by_id.get(voice_id)
        if not entry:
            missing.append(voice_id)
            continue
        file_name = entry.get("file_name")
        if not file_name:
            missing.append(voice_id)
            continue
        file_path = VOICE_PROMPT_DIR / file_name
        if file_path.exists():
            files.append((file_path, file_name))
        else:
            missing.append(voice_id)

    return files, missing


@app.route('/api/chatterbox-voices/export', methods=['POST'])
def export_chatterbox_voices():
    data = request.get_json(silent=True) or {}
    voice_ids = data.get("voice_ids") or []
    if not isinstance(voice_ids, list) or not voice_ids:
        return jsonify({"success": False, "error": "No voice ids provided."}), 400

    files, missing = _collect_voice_files([str(v) for v in voice_ids])
    if not files:
        return jsonify({"success": False, "error": "No audio files found for export."}), 404

    if len(files) == 1:
        file_path, filename = files[0]
        mime_type, _ = mimetypes.guess_type(filename)
        return send_file(
            file_path,
            mimetype=mime_type or 'audio/mpeg',
            as_attachment=True,
            download_name=filename,
        )

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zipf:
        for file_path, filename in files:
            zipf.write(file_path, arcname=filename)
    buffer.seek(0)
    response = send_file(
        buffer,
        mimetype="application/zip",
        as_attachment=True,
        download_name="voice_samples.zip",
    )
    response.headers["X-Voice-Missing"] = json.dumps(missing)
    return response


@app.route('/api/chatterbox-voices/archive', methods=['POST'])
def archive_chatterbox_voices():
    data = request.get_json(silent=True) or {}
    voice_ids = data.get("voice_ids") or []
    archived = _coerce_bool(data.get("archived", True))
    if not isinstance(voice_ids, list) or not voice_ids:
        return jsonify({"success": False, "error": "No voice ids provided."}), 400

    entries = _load_chatterbox_voice_entries()
    entry_map = {entry.get("id"): entry for entry in entries if entry.get("id")}
    updated = 0
    external_ids = _load_external_voice_archives()

    for voice_id in [str(v) for v in voice_ids]:
        if _is_external_voice_id(voice_id):
            short_name = _strip_external_voice_id(voice_id)
            if archived:
                external_ids.add(short_name)
            else:
                external_ids.discard(short_name)
            updated += 1
            continue

        entry = entry_map.get(voice_id)
        if not entry:
            continue
        entry["archived"] = archived
        updated += 1

    _save_chatterbox_voice_entries(entries)
    _save_external_voice_archives(external_ids)
    return jsonify({"success": True, "updated": updated})


@app.route('/api/chatterbox-voices/batch-delete', methods=['POST'])
def batch_delete_chatterbox_voices():
    data = request.get_json(silent=True) or {}
    voice_ids = data.get("voice_ids") or []
    if not isinstance(voice_ids, list) or not voice_ids:
        return jsonify({"success": False, "error": "No voice ids provided."}), 400

    entries = _load_chatterbox_voice_entries()
    remaining_entries = []
    deleted = 0
    target_ids = {str(v) for v in voice_ids}
    external_ids = _load_external_voice_archives()

    for entry in entries:
        entry_id = entry.get("id")
        if entry_id and entry_id in target_ids:
            file_name = entry.get("file_name")
            file_path = VOICE_PROMPT_DIR / file_name if file_name else None
            if file_path and file_path.exists():
                try:
                    file_path.unlink()
                except OSError as exc:
                    logger.warning("Unable to delete voice prompt file %s: %s", file_path, exc)
            deleted += 1
            continue
        remaining_entries.append(entry)

    for voice_id in target_ids:
        if _is_external_voice_id(voice_id):
            short_name = _strip_external_voice_id(voice_id)
            local_file = EXTERNAL_VOICES_DIR / f"{short_name}.mp3"
            if local_file.exists():
                try:
                    local_file.unlink()
                except OSError as exc:
                    logger.warning("Unable to delete external voice file %s: %s", local_file, exc)
            prompt_file = VOICE_PROMPT_DIR / f"{short_name}.mp3"
            if prompt_file.exists():
                try:
                    prompt_file.unlink()
                except OSError as exc:
                    logger.warning("Unable to delete voice prompt file %s: %s", prompt_file, exc)
            external_ids.discard(short_name)
            deleted += 1

    _save_chatterbox_voice_entries(remaining_entries)
    _save_external_voice_archives(external_ids)
    return jsonify({"success": True, "deleted": deleted})


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


def _serialize_external_voice(voice: Dict[str, Any], archived_ids: Optional[set] = None) -> Dict[str, Any]:
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
    archived_ids = archived_ids or set()
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
        "archived": short_name in archived_ids,
        "download_url": f"{EXTERNAL_SAMPLES_BASE_URL}/{folder_name}/{short_name}.mp3",
        "voice_personalities": voice.get("VoiceTag", {}).get("VoicePersonalities", []),
    }


@app.route('/api/external-voices', methods=['GET'])
def list_external_voices():
    """List available external TTS voice samples from GitHub."""
    try:
        force_refresh = request.args.get('refresh', '').lower() == 'true'
        voices = _fetch_external_voices(force_refresh=force_refresh)
        archived_ids = _load_external_voice_archives()
        serialized = [_serialize_external_voice(v, archived_ids) for v in voices]
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
            "voice": _serialize_external_voice(voice, _load_external_voice_archives()),
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
    if "transcript" in data:
        file_name = entry.get("file_name")
        if file_name:
            _update_voice_prompt_transcript(
                VOICE_PROMPT_DIR / Path(file_name).name,
                str(data.get("transcript") or ""),
            )
    
    _save_chatterbox_voice_entries(entries)
    return jsonify({"success": True, "voice": _serialize_chatterbox_voice(entry)})


@app.route('/api/chatterbox-voices/<voice_id>/transcribe', methods=['POST'])
def transcribe_chatterbox_voice(voice_id: str):
    """Generate and persist an exact-reference transcript with local SenseVoice ASR."""
    entries = _load_chatterbox_voice_entries()
    entry = _resolve_chatterbox_voice(voice_id, entries)
    if not entry:
        return jsonify({"success": False, "error": "Voice not found."}), 404
    file_name = Path(str(entry.get("file_name") or "")).name
    if not file_name:
        return jsonify({"success": False, "error": "Voice sample file is missing."}), 404
    audio_path = VOICE_PROMPT_DIR / file_name
    if not audio_path.is_file():
        return jsonify({"success": False, "error": "Voice sample file is missing."}), 404
    try:
        transcript = voice_transcript_generator.transcribe(audio_path)
        _update_voice_prompt_transcript(audio_path, transcript)
    except VoiceTranscriptionError as exc:
        return jsonify({"success": False, "error": str(exc)}), 422
    except Exception as exc:  # pragma: no cover - defensive model/runtime failure
        logger.error("Voice sample transcription failed: %s", exc, exc_info=True)
        return jsonify({"success": False, "error": "Voice sample transcription failed."}), 500
    return jsonify({
        "success": True,
        "transcript": transcript,
        "voice": _serialize_chatterbox_voice(entry),
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
                "post_process_active": bool(job_entry.get("post_process_active")),
                "post_process_percent": int(job_entry.get("post_process_percent") or 0),
                "post_process_done": int(job_entry.get("post_process_done") or 0),
                "post_process_total": int(job_entry.get("post_process_total") or 0),
                "post_process_label": job_entry.get("post_process_label"),
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
        acx_compliance=bool(merge_options.get("acx_compliance", False)),
    )
    job_dir = _job_dir_from_entry(job_id, job_entry)

    chapters = manifest.get("chapters", []) or []
    all_full_story_chunks = manifest.get("all_full_story_chunks") or []
    books = manifest.get("books", []) or []
    total_steps = len(chapters) + len(books) + (1 if all_full_story_chunks else 0)
    with queue_lock:
        entry = jobs.get(job_id)
        if entry:
            entry["post_process_total"] = max(int(total_steps), 0)
            entry["post_process_done"] = 0
            entry["post_process_percent"] = 0
            entry["post_process_active"] = True

    chapter_outputs = []
    for chapter_step, chapter in enumerate(chapters, start=1):
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
        chapter_label = chapter.get("title") or f"chapter {chapter_step}"
        with queue_lock:
            entry = jobs.get(job_id)
            if entry:
                entry["post_process_label"] = f"Merging {chapter_label}"
        merger.merge_wav_files(
            input_files=chunk_paths,
            output_path=str(output_path),
            format=output_format,
            cleanup_chunks=False,
            progress_callback=lambda ratio, step=chapter_step: _update_review_post_progress(
                job_id,
                step,
                ratio,
            ),
        )
        with queue_lock:
            entry = jobs.get(job_id)
            if entry:
                entry["post_process_done"] = min(
                    chapter_step,
                    int(entry.get("post_process_total") or 0) or 0,
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
    if all_full_story_chunks:
        chunk_paths = [str(job_dir / rel_path) for rel_path in all_full_story_chunks]
        full_story_name = f"full_story.{output_format}"
        full_story_path = job_dir / full_story_name
        full_story_step = len(chapters) + 1
        with queue_lock:
            entry = jobs.get(job_id)
            if entry:
                entry["post_process_label"] = "Merging full story"
        merger.merge_wav_files(
            input_files=chunk_paths,
            output_path=str(full_story_path),
            format=output_format,
            cleanup_chunks=False,
            progress_callback=lambda ratio: _update_review_post_progress(
                job_id,
                full_story_step,
                ratio,
            ),
        )
        with queue_lock:
            entry = jobs.get(job_id)
            if entry:
                entry["post_process_done"] = min(
                    full_story_step,
                    int(entry.get("post_process_total") or 0) or 0,
                )
        full_story_entry = {
            "title": "Full Story",
            "file_url": f"/static/audio/{job_id}/{full_story_name}",
            "relative_path": full_story_name,
        }

    book_mode = bool(manifest.get("book_mode"))
    book_outputs = []
    if book_mode:
        # Merge book-level audio files
        for book_index, book in enumerate(manifest.get("books", []), start=1):
            book_chunk_files = book.get("chunk_files") or []
            if not book_chunk_files:
                continue
            
            chunk_paths = [str(job_dir / rel_path) for rel_path in book_chunk_files]
            missing_chunks = [p for p in chunk_paths if not Path(p).exists()]
            if missing_chunks:
                logger.error(f"Missing chunk files for book merge: {missing_chunks}")
                continue
            
            output_filename = book.get("output_filename")
            rel_book_dir = book.get("book_dir") or "."
            if not output_filename:
                continue
            
            book_dir_path = job_dir / rel_book_dir
            book_dir_path.mkdir(parents=True, exist_ok=True)
            output_path = book_dir_path / output_filename
            
            logger.info(f"Merging book-level audio: {len(chunk_paths)} chunks into {output_path}")
            book_step = len(chapters) + (1 if all_full_story_chunks else 0) + book_index
            book_label = book.get("title") or f"book {book_index}"
            with queue_lock:
                entry = jobs.get(job_id)
                if entry:
                    entry["post_process_label"] = f"Merging {book_label}"
            merger.merge_wav_files(
                input_files=chunk_paths,
                output_path=str(output_path),
                format=output_format,
                cleanup_chunks=False,
                progress_callback=lambda ratio, step=book_step: _update_review_post_progress(
                    job_id,
                    step,
                    ratio,
                ),
            )
            with queue_lock:
                entry = jobs.get(job_id)
                if entry:
                    entry["post_process_done"] = min(
                        book_step,
                        int(entry.get("post_process_total") or 0) or 0,
                    )
            
            rel_path = Path(rel_book_dir) / output_filename
            book_outputs.append({
                "index": book.get("index", 0),
                "title": book.get("title"),
                "file_url": f"/static/audio/{job_id}/{rel_path.as_posix()}",
                "relative_path": rel_path.as_posix(),
            })

    # Recompilation updates generated output records, but must never discard
    # user-authored Library metadata such as collection/audiobook titles,
    # chapter renames, author, cover details, or word replacements.
    metadata = load_job_metadata(job_dir) or {}
    generated_metadata = {
        "chapter_mode": job_entry.get("chapter_mode"),
        "book_mode": book_mode,
        "output_format": output_format,
        "chapters": chapter_outputs,
        "chapter_count": len(chapter_outputs),
        "books": book_outputs,
        "book_count": len(book_outputs),
        "full_story": full_story_entry,
        "crossfade_duration": float(merge_options.get("crossfade_duration") or 0),
        "intro_silence_ms": int(max(0, merge_options.get("intro_silence_ms") or 0)),
        "inter_chunk_silence_ms": int(max(0, merge_options.get("inter_chunk_silence_ms") or 0)),
        "output_bitrate_kbps": int(merge_options.get("output_bitrate_kbps") or 0),
        "acx_compliance": bool(merge_options.get("acx_compliance", False)),
        "word_replacements": (
            job_entry.get("word_replacements")
            or metadata.get("word_replacements")
            or []
        ),
    }
    metadata = merge_generated_library_metadata(
        metadata,
        generated_metadata,
        job_entry.get("chunks") or [],
    )
    save_job_metadata(job_dir, metadata)

    invalidate_library_cache()

    job_end_time = datetime.now()
    with queue_lock:
        entry = jobs.get(job_id)
        if entry:
            entry["status"] = "completed"
            entry["progress"] = 100
            entry["eta_seconds"] = 0
            entry["post_process_percent"] = 100
            entry["post_process_active"] = False
            entry["post_process_done"] = int(entry.get("post_process_total") or entry.get("post_process_done") or 0)
            entry["post_process_label"] = "Recompile complete"
            entry["chapter_outputs"] = chapter_outputs
            entry["completed_at"] = job_end_time.isoformat()
            if full_story_entry:
                entry["full_story"] = full_story_entry
            entry["output_file"] = (full_story_entry or (chapter_outputs[0] if chapter_outputs else {})).get("file_url")
            # Keep measured active time; paused wall time and WAV duration are
            # not synthesis timings and must never be used as substitutes.
            prior_timing = entry.get("timing_metrics") or {}
            started_at_str = prior_timing.get("started_at") or entry.get("started_at")
            total_chunks = entry.get("total_chunks") or 0
            total_seconds = prior_timing.get("total_seconds")
            chunk_times = list(prior_timing.get("chunk_times") or [])
            avg_chunk = round(sum(chunk_times) / len(chunk_times), 1) if chunk_times else None
            final_timing_metrics = {
                "started_at": started_at_str,
                "completed_at": job_end_time.isoformat(),
                "total_seconds": round(total_seconds, 1) if total_seconds is not None else None,
                "chunk_count": total_chunks,
                "avg_chunk_seconds": avg_chunk,
                "min_chunk_seconds": round(min(chunk_times), 1) if chunk_times else None,
                "max_chunk_seconds": round(max(chunk_times), 1) if chunk_times else None,
                "chunk_times": chunk_times,
            }
            entry["timing_metrics"] = final_timing_metrics
    _persist_job_state(job_id, force=True)

    # Write final timing_metrics to chunks_metadata.json so the library can read it from disk.
    try:
        _cmeta_path = job_dir / "chunks_metadata.json"
        if _cmeta_path.exists():
            with _cmeta_path.open("r", encoding="utf-8") as _fh:
                _cmeta_data = json.load(_fh)
            with queue_lock:
                _final_tm = (jobs.get(job_id) or {}).get("timing_metrics")
            if _final_tm:
                _cmeta_data["timing_metrics"] = _final_tm
                with _cmeta_path.open("w", encoding="utf-8") as _fh:
                    json.dump(_cmeta_data, _fh, indent=2)
    except Exception as _e:
        logger.warning("Could not write timing_metrics to chunks_metadata.json (review path): %s", _e)


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

    if not text:
        text = "This is a quick preview."

    config = load_config()
    # Use requested engine if provided, otherwise fall back to config
    if requested_engine:
        engine_name = _normalize_engine_name(requested_engine)
    else:
        engine_name = _normalize_engine_name(config.get("tts_engine"))
    sample_rate = int(config.get('sample_rate', DEFAULT_SAMPLE_RATE))
    audio_bytes = None

    # For prompt-based engines the 'voice' field carries a file path that must
    # be forwarded as audio_prompt_path, not as the voice name parameter.
    _PROMPT_ENGINES = {
        "chatterbox_turbo_local", "chatterbox_turbo_replicate",
        "voxcpm_local", "pocket_tts", "qwen3_clone", "omnivoice_clone",
        "dots_tts",
        "audio8_tts",
        "breeze_tts_2",
    }
    audio_prompt_path = data.get('audio_prompt_path') or None
    if engine_name in _PROMPT_ENGINES and voice and not audio_prompt_path:
        audio_prompt_path = voice
        voice = ''

    # Qwen3 engines don't use Kokoro-style lang codes — map 'a'/'b'/etc. to 'auto'
    _QWEN3_ENGINES = {"qwen3_custom", "qwen3_clone"}
    _KOKORO_LANG_CODES = {'a', 'b', 'e', 'f', 'h', 'i', 'j', 'p', 'z'}
    if engine_name in _QWEN3_ENGINES and lang_code in _KOKORO_LANG_CODES:
        lang_code = 'auto'

    if not voice and not audio_prompt_path and engine_name not in {"audio8_tts", "breeze_tts_2"}:
        return jsonify({"success": False, "error": "Voice is required for preview."}), 400

    try:
        logger.info("Preview request: engine=%s, voice=%s, lang_code=%s, prompt=%s",
                    engine_name, voice, lang_code, audio_prompt_path)
        engine = get_tts_engine(engine_name, config=config)
        # Check if engine has generate_audio method that returns numpy array
        if hasattr(engine, 'generate_audio'):
            import inspect as _inspect
            _sig = _inspect.signature(engine.generate_audio)
            # Qwen3 custom expects lowercase speaker names
            _voice = voice.lower() if engine_name == 'qwen3_custom' and voice else voice
            # For engines that accept audio_prompt_path natively, pass it directly.
            # For engines that use voice= as the prompt path (e.g. pocket_tts), put it back there.
            _has_prompt_param = 'audio_prompt_path' in _sig.parameters
            _effective_voice = audio_prompt_path if (audio_prompt_path and not _has_prompt_param) else _voice
            _kwargs = dict(
                text=text,
                voice=_effective_voice,
                lang_code=lang_code,
                speed=speed,
                sample_rate=sample_rate,
                fx_settings=fx_settings,
            )
            if audio_prompt_path and _has_prompt_param:
                _kwargs['audio_prompt_path'] = audio_prompt_path
            if 'voice_options' in _sig.parameters:
                _kwargs['voice_options'] = data.get('extra') or {}
            audio = engine.generate_audio(**_kwargs)
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
        config["remote_engine_management_token"] = ""
        return jsonify({
            "success": True,
            "settings": config
        })
    else:
        try:
            new_settings = request.json or {}
            current_config = load_config()
            protected_keys = {
                "remote_engine_management_enabled",
                "remote_engine_management_token",
            }
            protected_change = any(
                key in new_settings
                and (
                    key == "remote_engine_management_token"
                    and bool(str(new_settings.get(key) or "").strip())
                    or key == "remote_engine_management_enabled"
                    and bool(new_settings.get(key)) != bool(current_config.get(key))
                )
                for key in protected_keys
            )
            if (
                not _is_local_management_request()
                and protected_change
                and not _engine_management_request_allowed(current_config)
            ):
                return jsonify({
                    "success": False,
                    "error": "Remote administration security settings can be changed only locally or by an authenticated remote administrator.",
                }), 403
            config = load_config()
            if not str(new_settings.get("remote_engine_management_token") or "").strip():
                new_settings.pop("remote_engine_management_token", None)
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

    except (GeminiProcessorError, LocalLLMProcessorError, AtlasCloudProcessorError, OpenRouterProcessorError) as exc:
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


@app.route('/api/local-llm/models', methods=['POST'])
def list_local_llm_models():
    """List available local LLM models for LM Studio/Ollama."""
    try:
        data = request.json or {}
        config = load_config()

        provider = (data.get("provider") or config.get("llm_local_provider") or "").strip()
        base_url = (data.get("base_url") or config.get("llm_local_base_url") or "").strip()
        api_key = (data.get("api_key") or config.get("llm_local_api_key") or "").strip()
        timeout = int(data.get("timeout") or config.get("llm_local_timeout") or 30)

        models = LocalLLMProcessor.list_available_models(
            provider=provider,
            base_url=base_url,
            api_key=api_key,
            timeout=timeout,
        )
        return jsonify({
            "success": True,
            "models": models,
        })
    except (ValueError, TypeError):
        return jsonify({
            "success": False,
            "error": "Invalid timeout value"
        }), 400
    except (GeminiProcessorError, LocalLLMProcessorError, AtlasCloudProcessorError, OpenRouterProcessorError) as exc:
        return jsonify({
            "success": False,
            "error": str(exc)
        }), 400
    except Exception as exc:  # pragma: no cover - general failure
        logger.error("Error listing local LLM models: %s", exc, exc_info=True)
        return jsonify({
            "success": False,
            "error": "Failed to list local LLM models"
        }), 500


@app.route('/api/atlas-cloud/models', methods=['POST'])
def list_atlas_cloud_models():
    """List Atlas Cloud LLM models using an entered or saved API key."""
    try:
        data = request.json or {}
        config = load_config()
        api_key = (data.get("api_key") or config.get("atlas_cloud_api_key") or "").strip()
        base_url = (
            data.get("base_url")
            or config.get("atlas_cloud_base_url")
            or DEFAULT_ATLAS_CLOUD_BASE_URL
        ).strip()
        current_model = (
            data.get("model")
            or config.get("atlas_cloud_model")
            or DEFAULT_ATLAS_CLOUD_MODEL
        ).strip()
        timeout = int(data.get("timeout") or config.get("atlas_cloud_timeout") or 30)

        catalog = AtlasCloudProcessor.list_available_models(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
            current_model=current_model,
        )
        return jsonify({
            "success": True,
            "models": catalog.models,
            "warnings": catalog.warnings,
        })
    except (ValueError, TypeError):
        return jsonify({
            "success": False,
            "error": "Invalid Atlas Cloud timeout value"
        }), 400
    except AtlasCloudProcessorError as exc:
        return jsonify({
            "success": False,
            "error": str(exc)
        }), 400
    except Exception as exc:  # pragma: no cover - general failure
        logger.error("Error listing Atlas Cloud models: %s", exc, exc_info=True)
        return jsonify({
            "success": False,
            "error": "Failed to list Atlas Cloud models"
        }), 500


@app.route('/api/openrouter/models', methods=['POST'])
def list_openrouter_models():
    """List text-output models available under an OpenRouter API key."""
    try:
        data = request.json or {}
        config = load_config()
        api_key = (data.get("api_key") or config.get("openrouter_api_key") or "").strip()
        base_url = (
            data.get("base_url")
            or config.get("openrouter_base_url")
            or DEFAULT_OPENROUTER_BASE_URL
        ).strip()
        current_model = (
            data.get("model")
            or config.get("openrouter_model")
            or DEFAULT_OPENROUTER_MODEL
        ).strip()
        timeout = int(data.get("timeout") or config.get("openrouter_timeout") or 30)

        models = OpenRouterProcessor.list_available_models(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
            current_model=current_model,
        )
        return jsonify({
            "success": True,
            "models": models,
        })
    except (ValueError, TypeError):
        return jsonify({
            "success": False,
            "error": "Invalid OpenRouter timeout value"
        }), 400
    except OpenRouterProcessorError as exc:
        return jsonify({
            "success": False,
            "error": str(exc)
        }), 400
    except Exception as exc:  # pragma: no cover - general failure
        logger.error("Error listing OpenRouter models: %s", exc, exc_info=True)
        return jsonify({
            "success": False,
            "error": "Failed to list OpenRouter models"
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
            section_headings = data.get("section_headings")
            hierarchy = split_text_into_book_sections(text, section_headings)
            book_matches = hierarchy.get("books") or []
            section_matches = hierarchy.get("sections") or []

            if book_matches:
                books = hierarchy.get("books") or []
                chapters: List[Dict[str, Any]] = []
                for book in books:
                    chapters.extend(book.get("chapters") or [])
                stats['section_detection'] = {
                    "detected": True,
                    "count": len(chapters),
                    "titles": [c.get('title') for c in chapters if c.get('title')],
                    "kind": "book",
                    "book_count": len(books),
                    "section_count": len(chapters),
                }
            elif section_matches:
                sections = hierarchy.get("sections") or []
                stats['section_detection'] = {
                    "detected": True,
                    "count": len(sections),
                    "titles": [s.get('title') for s in sections if s.get('title')],
                    "kind": "section",
                    "book_count": 0,
                    "section_count": len(sections),
                }
            else:
                stats['section_detection'] = {
                    "detected": False,
                    "count": 0,
                    "titles": [],
                    "kind": None,
                    "book_count": 0,
                    "section_count": 0,
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


@app.route('/api/jobs/clear-all', methods=['DELETE'])
def clear_all_jobs():
    """Remove all jobs that are not actively processing from the queue, DB, and disk."""
    import shutil
    skipped = []
    removed = []
    errors = []

    try:
        with queue_lock:
            all_job_ids = list(jobs.keys())

        for job_id in all_job_ids:
            with queue_lock:
                job_entry = jobs.get(job_id)
                status = job_entry.get("status") if job_entry else None
            if status in {"processing", "pausing"}:
                skipped.append(job_id)
                continue
            try:
                with queue_lock:
                    if job_id in jobs:
                        jobs[job_id]["status"] = "deleted"
                        cancel_flags[job_id] = True
                        pause_flags.pop(job_id, None)
                        cancel_events.pop(job_id, None)
                    job_entry = jobs.get(job_id) or {}
                    job_dir = _job_dir_from_entry(job_id, job_entry)

                with _get_jobs_db_connection() as conn:
                    row = conn.execute("SELECT status, job_dir FROM jobs WHERE job_id=?", (job_id,)).fetchone()
                    if row and not job_dir or str(job_dir) == ".":
                        job_dir = _job_dir_from_entry(job_id, {"job_dir": row["job_dir"]})
                    db_status = (row["status"] if row else None) or status
                    conn.execute("DELETE FROM jobs WHERE job_id=?", (job_id,))
                    conn.commit()

                with queue_lock:
                    jobs.pop(job_id, None)

                job_data_dir = JOBS_DATA_DIR / job_id
                if job_data_dir.exists():
                    try:
                        shutil.rmtree(job_data_dir, onerror=handle_remove_readonly)
                    except Exception as rm_err:
                        logger.warning("Could not delete job data dir %s: %s", job_data_dir, rm_err)

                if db_status not in {"completed", "done", "review"} and job_dir and job_dir.exists():
                    try:
                        shutil.rmtree(job_dir, onerror=handle_remove_readonly)
                    except Exception as rm_err:
                        logger.warning("Could not delete job audio dir %s: %s", job_dir, rm_err)

                removed.append(job_id)
            except Exception as e:
                logger.error("Error clearing job %s: %s", job_id, e, exc_info=True)
                errors.append(job_id)

        # Also sweep DB for any persisted jobs not in memory
        try:
            with _get_jobs_db_connection() as conn:
                rows = conn.execute("SELECT job_id, status, job_dir FROM jobs").fetchall()
            for row in rows:
                job_id = row["job_id"]
                if job_id in removed or job_id in skipped or job_id in errors:
                    continue
                db_status = row["status"] or ""
                if db_status in {"processing", "pausing"}:
                    skipped.append(job_id)
                    continue
                try:
                    job_dir = _job_dir_from_entry(job_id, {"job_dir": row["job_dir"]})
                    with _get_jobs_db_connection() as conn:
                        conn.execute("DELETE FROM jobs WHERE job_id=?", (job_id,))
                        conn.commit()
                    job_data_dir = JOBS_DATA_DIR / job_id
                    if job_data_dir.exists():
                        shutil.rmtree(job_data_dir, onerror=handle_remove_readonly)
                    if db_status not in {"completed", "done", "review"} and job_dir and job_dir.exists():
                        shutil.rmtree(job_dir, onerror=handle_remove_readonly)
                    removed.append(job_id)
                except Exception as e:
                    logger.error("Error clearing DB job %s: %s", job_id, e, exc_info=True)
                    errors.append(job_id)
        except Exception as e:
            logger.error("Error sweeping jobs DB during clear-all: %s", e, exc_info=True)

        invalidate_library_cache()
        return jsonify({
            "success": True,
            "removed": len(removed),
            "skipped": len(skipped),
            "errors": len(errors),
        })
    except Exception as e:
        logger.error("clear_all_jobs failed: %s", e, exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/jobs/<job_id>/delete', methods=['DELETE'])
def delete_job(job_id: str):
    """Remove a job from the queue and delete its output files from disk."""
    import shutil
    try:
        with queue_lock:
            job_entry = jobs.get(job_id)
            if job_entry:
                status = job_entry.get("status")
                if status in {"processing", "pausing"}:
                    return jsonify({
                        "success": False,
                        "error": "Job is currently processing. Pause or cancel it before deleting.",
                    }), 409
                job_entry["status"] = "deleted"
                cancel_flags[job_id] = True
                pause_flags.pop(job_id, None)
                cancel_events.pop(job_id, None)
            else:
                status = None
            job_dir = _job_dir_from_entry(job_id, job_entry or {})

        with _get_jobs_db_connection() as conn:
            row = conn.execute("SELECT status, job_dir FROM jobs WHERE job_id=?", (job_id,)).fetchone()
            if not job_entry and not row:
                return jsonify({"success": False, "error": "Job not found"}), 404
            if row and not status:
                status = row["status"]
                if not job_dir or str(job_dir) == ".":
                    job_dir = _job_dir_from_entry(job_id, {"job_dir": row["job_dir"]})
            conn.execute("DELETE FROM jobs WHERE job_id=?", (job_id,))
            conn.commit()

        with queue_lock:
            jobs.pop(job_id, None)

        # Always delete the job metadata folder (data/jobs/<job_id>/).
        job_data_dir = JOBS_DATA_DIR / job_id
        if job_data_dir.exists():
            try:
                shutil.rmtree(job_data_dir, onerror=handle_remove_readonly)
                logger.info("Deleted job data directory: %s", job_data_dir)
            except Exception as rm_err:
                logger.warning("Could not delete job data directory %s: %s", job_data_dir, rm_err)

        # Only delete the audio output folder (static/audio/<job_id>/) for jobs
        # that never completed. Completed/done/review jobs are library items —
        # their audio must be preserved so the library entry survives.
        if status not in {"completed", "done", "review"} and job_dir.exists():
            try:
                shutil.rmtree(job_dir, onerror=handle_remove_readonly)
                logger.info("Deleted job audio directory: %s", job_dir)
            except Exception as rm_err:
                logger.warning("Could not delete job audio directory %s: %s", job_dir, rm_err)

        invalidate_library_cache()
        return jsonify({"success": True})
    except Exception as e:
        logger.error("Error deleting job %s: %s", job_id, e, exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/jobs/<job_id>/pause', methods=['POST'])
def pause_job(job_id: str):
    try:
        with queue_lock:
            job_entry = jobs.get(job_id)
            if not job_entry:
                return jsonify({"success": False, "error": "Job not found"}), 404
            if job_entry.get("status") not in {"queued", "processing"}:
                return jsonify({"success": False, "error": "Job is not running"}), 409
            pause_flags[job_id] = True
            job_entry["status"] = "pausing" if job_entry.get("status") == "processing" else "paused"
            if job_entry["status"] == "paused":
                job_entry["paused_at"] = datetime.now().isoformat()
        _persist_job_state(job_id, force=True)
        return jsonify({"success": True})
    except Exception as exc:
        logger.error("Failed to pause job %s: %s", job_id, exc, exc_info=True)
        return jsonify({"success": False, "error": "Failed to pause job"}), 500


@app.route('/api/jobs/<job_id>/resume', methods=['POST'])
def resume_job(job_id: str):
    try:
        start_worker_thread()
        with queue_lock:
            job_entry = jobs.get(job_id)
            if not job_entry:
                return jsonify({"success": False, "error": "Job not found"}), 404
            total_chunks = int(job_entry.get("total_chunks") or 0)
            processed_chunks = int(job_entry.get("processed_chunks") or 0)
            post_total = int(job_entry.get("post_process_total") or 0)
            post_done = int(job_entry.get("post_process_done") or 0)
            if total_chunks and processed_chunks >= total_chunks and (post_total == 0 or post_done >= post_total):
                job_entry["status"] = "completed"
                job_entry["progress"] = 100
                job_entry["eta_seconds"] = 0
                job_entry["interrupted_at"] = None
                _persist_job_state(job_id, force=True)
                return jsonify({"success": True, "message": "Job already completed"})
            resumable_statuses = {"paused", "interrupted"}
            if processed_chunks > 0 or job_entry.get('engine') == 'breeze_api':
                resumable_statuses.add("failed")
            if job_entry.get("status") not in resumable_statuses:
                return jsonify({"success": False, "error": "Job is not paused"}), 409
            pause_flags.pop(job_id, None)
            resume_from = job_entry.get("resume_from_chunk_index")
            if resume_from is None:
                resume_from = job_entry.get("processed_chunks") or 0
            job_entry["resume_from_chunk_index"] = int(resume_from or 0)
            job_entry["status"] = "queued"
            job_entry["paused_at"] = None
            job_entry["interrupted_at"] = None
            job_entry["error"] = None
        job_data = _build_job_data_from_entry(job_id, job_entry)
        job_queue.put(job_data)
        _persist_job_state(job_id, force=True)
        return jsonify({"success": True})
    except Exception as exc:
        logger.error("Failed to resume job %s: %s", job_id, exc, exc_info=True)
        return jsonify({"success": False, "error": "Failed to resume job"}), 500


@app.route('/api/jobs/<job_id>/details', methods=['GET'])
def get_job_details(job_id: str):
    try:
        with queue_lock:
            job_entry = jobs.get(job_id)
            if not job_entry:
                return jsonify({"success": False, "error": "Job not found"}), 404
            text = _load_job_text(job_entry.get("text_path"))
            payload = {
                "job_id": job_id,
                "status": job_entry.get("status"),
                "created_at": job_entry.get("created_at"),
                "started_at": job_entry.get("started_at"),
                "completed_at": job_entry.get("completed_at"),
                "engine": job_entry.get("engine"),
                "speakers": job_entry.get("speakers") or _extract_speakers_for_text(text),
                "text": text,
                "voice_assignments": job_entry.get("voice_assignments") or {},
                "chapter_mode": bool(job_entry.get("chapter_mode")),
                "full_story_requested": bool(job_entry.get("full_story_requested")),
                "resume_from_chunk_index": job_entry.get("resume_from_chunk_index"),
                "last_completed_chunk_index": job_entry.get("last_completed_chunk_index"),
                "timing_metrics": job_entry.get("timing_metrics"),
                "total_chunks": job_entry.get("total_chunks"),
                "processed_chunks": job_entry.get("processed_chunks"),
            }
        return jsonify({"success": True, "job": payload})
    except Exception as exc:
        logger.error("Failed to load job details %s: %s", job_id, exc, exc_info=True)
        return jsonify({"success": False, "error": "Failed to load job details"}), 500


@app.route('/api/sections/preview', methods=['POST'])
def preview_section_detection():
    """Preview detected book/section structure for UI review."""
    try:
        data = request.json or {}
        text = (data.get('text') or '').strip()
        section_headings = data.get('section_headings')
        voice_assignments = data.get('voice_assignments', {})

        if not text:
            return jsonify({
                "success": False,
                "error": "No text provided"
            }), 400

        voice_assignments = _prepare_voice_assignments(text, voice_assignments)

        hierarchy = split_text_into_book_sections(text, section_headings)

        def preview_content(content: str, limit: int = 220, heading: Optional[str] = None) -> str:
            snippet = (content or "").strip()
            if heading:
                snippet = re.sub(rf"^\s*{re.escape(heading)}\s*", "", snippet, flags=re.IGNORECASE)
            snippet = re.sub(r"\[/?[^\]]+\]", "", snippet)
            snippet = re.sub(r"\s+", " ", snippet).strip()
            if len(snippet) <= limit:
                return snippet
            return snippet[: limit - 1].rstrip() + "…"

        if hierarchy.get("kind") == "book":
            books = []
            for book in hierarchy.get("books") or []:
                chapters = []
                for chapter in book.get("chapters") or []:
                    chapters.append({
                        "title": chapter.get("title") or "",
                        "preview": preview_content(chapter.get("content") or "", heading=chapter.get("heading")),
                        "heading": chapter.get("heading"),
                        "heading_start": chapter.get("heading_start"),
                        "heading_end": chapter.get("heading_end"),
                    })
                books.append({
                    "title": book.get("title") or "",
                    "chapters": chapters,
                })

            return jsonify({
                "success": True,
                "kind": "book",
                "books": books,
                "sections": [],
                "book_count": len(books),
                "section_count": sum(len(b.get("chapters") or []) for b in books)
            })

        if hierarchy.get("kind") == "section":
            sections = [
                {
                    "title": section.get("title") or "",
                    "preview": preview_content(section.get("content") or "", heading=section.get("heading")),
                    "heading": section.get("heading"),
                    "heading_start": section.get("heading_start"),
                    "heading_end": section.get("heading_end"),
                }
                for section in hierarchy.get("sections") or []
            ]
            return jsonify({
                "success": True,
                "kind": "section",
                "books": [],
                "sections": sections,
                "book_count": 0,
                "section_count": len(sections)
            })

        return jsonify({
            "success": True,
            "kind": "none",
            "books": [],
            "sections": [],
            "book_count": 0,
            "section_count": 0
        })

    except Exception as e:
        logger.error(f"Error previewing section detection: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/api/library/<job_id>/title', methods=['PUT'])
def update_library_title(job_id: str):
    """Update the display title for a library collection."""
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    if not title:
        return jsonify({"success": False, "error": "Title is required"}), 400

    job_dir = OUTPUT_DIR / job_id
    if not job_dir.exists():
        return jsonify({"success": False, "error": "Item not found"}), 404

    metadata = load_job_metadata(job_dir) or {}
    metadata["collection_title"] = title
    save_job_metadata(job_dir, metadata)

    return jsonify({"success": True, "title": title})


@app.route('/api/gemini/process', methods=['POST'])
def process_text_with_gemini():
    """Process text with the configured LLM using section-based chunking."""
    try:
        data = request.json or {}
        text = (data.get('text') or '').strip()
        prefer_chapters = bool(data.get('prefer_chapters', True))
        section_headings = data.get('section_headings')
        prompt_override = (data.get('prompt_override') or '').strip()

        if not text:
            return jsonify({
                "success": False,
                "error": "No text provided"
            }), 400

        config = load_config()
        provider = (config.get("llm_provider") or DEFAULT_LLM_PROVIDER).lower().strip()
        if provider == "gemini":
            api_key = (config.get('gemini_api_key') or '').strip()
            if not api_key:
                return jsonify({
                    "success": False,
                    "error": "Gemini API key not configured"
                }), 400

        prompt_prefix = prompt_override or (config.get('gemini_prompt') or '').strip()

        sections = build_gemini_sections(text, prefer_chapters, config, section_headings)
        if not sections:
            return jsonify({
                "success": False,
                "error": "Unable to create sections for LLM processing"
            }), 400

        text_processor = TextProcessor(chunk_size=config.get('chunk_size', 500))
        known_speakers = set(text_processor.extract_speakers(text))
        active_profile = None

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
            response_text, profile_used, provider_failures = _run_llm_prompt_with_failover(
                combined_prompt,
                config,
                preferred_profile=active_profile,
            )
            active_profile = profile_used["id"]
            detected_speakers = text_processor.extract_speakers(response_text)
            for speaker_name in detected_speakers:
                known_speakers.add(speaker_name)
            processed_sections.append({
                "index": idx,
                "title": section.get('title'),
                "source": section.get('source'),
                "output": response_text.strip(),
                "speakers": detected_speakers,
                "llm_profile_used": profile_used,
                "llm_provider_used": profile_used["provider"],
                "provider_failures": provider_failures,
            })

        if not processed_sections:
            return jsonify({
                "success": False,
                "error": "LLM processing produced no output"
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
            "llm_profile_used": profile_used,
            "llm_provider_used": profile_used["provider"],
            "chapter_mode": any(section.get('source') == 'chapter' for section in sections),
            "section_count": len(processed_sections)
        })

    except (GeminiProcessorError, LocalLLMProcessorError, AtlasCloudProcessorError, OpenRouterProcessorError, LLMProviderChainError) as exc:
        return jsonify({
            "success": False,
            "error": str(exc)
        }), 400
    except Exception as e:  # pragma: no cover - general failure
        logger.error(f"Error during LLM processing: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": "Failed to process text with the configured LLM"
        }), 500


@app.route('/api/gemini/process-full', methods=['POST'])
def process_full_text_with_gemini():
    """Send the entire text to the configured LLM without chunking."""
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
        provider = (config.get("llm_provider") or DEFAULT_LLM_PROVIDER).lower().strip()
        if provider == "gemini":
            api_key = (config.get('gemini_api_key') or '').strip()
            if not api_key:
                return jsonify({
                    "success": False,
                    "error": "Gemini API key not configured"
                }), 400

        prompt_prefix = prompt_override or (config.get('gemini_prompt') or '').strip()

        prompt_parts = []
        if prompt_prefix:
            prompt_parts.append(prompt_prefix)
        prompt_parts.append(text)
        combined_prompt = "\n\n".join(part.strip() for part in prompt_parts if part).strip()

        response_text, profile_used, provider_failures = _run_llm_prompt_with_failover(
            combined_prompt,
            config,
        )

        return jsonify({
            "success": True,
            "result_text": response_text.strip(),
            "llm_profile_used": profile_used,
            "llm_provider_used": profile_used["provider"],
            "provider_failures": provider_failures,
        })

    except (GeminiProcessorError, LocalLLMProcessorError, AtlasCloudProcessorError, OpenRouterProcessorError, LLMProviderChainError) as exc:
        return jsonify({
            "success": False,
            "error": str(exc)
        }), 400
    except Exception as e:  # pragma: no cover - general failure
        logger.error(f"Error during full-text LLM processing: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": "Failed to process text with the configured LLM"
        }), 500


@app.route('/api/gemini/speaker-profiles', methods=['POST'])
def process_gemini_speaker_profiles():
    """Generate speaker profile table and parse structured attributes."""
    try:
        data = request.json or {}
        speakers = data.get('speakers') or []
        context = (data.get('context') or '').strip()
        prompt_override = (data.get('prompt_override') or '').strip()

        speakers = [str(s).strip() for s in speakers if str(s).strip()]
        if not speakers:
            return jsonify({
                "success": False,
                "error": "No speakers provided"
            }), 400

        config = load_config()
        provider = (config.get("llm_provider") or DEFAULT_LLM_PROVIDER).lower().strip()
        if provider == "gemini":
            api_key = (config.get('gemini_api_key') or '').strip()
            if not api_key:
                return jsonify({
                    "success": False,
                    "error": "Gemini API key not configured"
                }), 400
        prompt_prefix = prompt_override or (config.get('gemini_speaker_profile_prompt') or '').strip()
        if not prompt_prefix:
            return jsonify({
                "success": False,
                "error": "Speaker profile prompt not configured"
            }), 400

        processed_text = (data.get('processed_text') or '').strip()
        profile_excerpts = build_speaker_profile_excerpts(processed_text, speakers)
        prompt = compose_gemini_speaker_profile_prompt(prompt_prefix, speakers, context, profile_excerpts)
        response_text, profile_used, provider_failures = _run_llm_prompt_with_failover(
            prompt,
            config,
        )
        profiles = parse_gemini_speaker_table(response_text)

        if not profiles:
            return jsonify({
                "success": False,
                "error": "The LLM returned no usable speaker profiles. Try the request again or review the Speaker Profile Prompt."
            }), 422

        # Models and older custom prompts may still return the legacy three-column
        # table. Never report success with an empty Voice Design Prompt: preserve a
        # valid fourth column or build one from speaker gender + Voice Type only.
        for profile in profiles.values():
            profile["voice_design_prompt"] = build_profile_voice_design_prompt(profile)

        normalized_profile_names = {
            re.sub(r'[^a-z0-9]', '', str(profile.get("name") or key).lower())
            for key, profile in profiles.items()
        }
        missing_speakers = []
        for speaker in speakers:
            normalized = re.sub(r'[^a-z0-9]', '', speaker.lower())
            without_gender = re.sub(r'(male|female|neutral)$', '', normalized)
            if not any(
                candidate == normalized
                or (without_gender and re.sub(r'(male|female|neutral)$', '', candidate) == without_gender)
                for candidate in normalized_profile_names
            ):
                missing_speakers.append(speaker)

        return jsonify({
            "success": True,
            "profiles": profiles,
            "missing_speakers": missing_speakers,
            "raw": response_text.strip(),
            "llm_profile_used": profile_used,
            "llm_provider_used": profile_used["provider"],
            "provider_failures": provider_failures,
        })
    except (GeminiProcessorError, LocalLLMProcessorError, AtlasCloudProcessorError, OpenRouterProcessorError, LLMProviderChainError) as exc:
        return jsonify({
            "success": False,
            "error": str(exc)
        }), 400
    except Exception as e:  # pragma: no cover - general failure
        logger.error(f"Error during LLM speaker profile processing: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": "Failed to process speaker profiles with the configured LLM"
        }), 500


@app.route('/api/gemini/sections', methods=['POST'])
def get_gemini_sections():
    """Return the list of LLM processing sections for the provided text."""
    try:
        data = request.json or {}
        text = (data.get('text') or '').strip()
        prefer_chapters = bool(data.get('prefer_chapters', True))
        section_headings = data.get('section_headings')

        if not text:
            return jsonify({
                "success": False,
                "error": "No text provided"
            }), 400

        config = load_config()
        sections = build_gemini_sections(text, prefer_chapters, config, section_headings)

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
        logger.error(f"Error building LLM sections: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": "Failed to build LLM sections"
        }), 500


@app.route('/api/gemini/process-section', methods=['POST'])
def process_gemini_section():
    """Process a single text section through the configured LLM."""
    try:
        from src.structured_output import validate_schema, StructuredOutputError
        from src.directed_output import prepare_direction_request, assemble_directed
        data = request.json or {}
        structured_options = {}
        if 'response_schema' in data:
            validate_schema(data['response_schema'], data.get('response_schema_name'),
                            data.get('response_schema_strict', True))
            structured_options = {key: data[key] for key in (
                'response_schema', 'response_schema_name', 'response_schema_strict') if key in data}
        content = (data.get('content') or '').strip()
        prompt_override = (data.get('prompt_override') or '').strip()
        preferred_profile = (data.get('preferred_profile') or '').strip()

        if not content:
            return jsonify({
                "success": False,
                "error": "No section content provided"
            }), 400

        config = load_config()
        provider = (config.get("llm_provider") or DEFAULT_LLM_PROVIDER).lower().strip()
        if provider == "gemini":
            api_key = (config.get('gemini_api_key') or '').strip()
            if not api_key:
                return jsonify({
                    "success": False,
                    "error": "Gemini API key not configured"
                }), 400

        prompt_prefix = prompt_override or (config.get('gemini_prompt') or '').strip()

        raw_known = data.get('known_speakers') or []
        known_speakers = []
        if isinstance(raw_known, list):
            for entry in raw_known:
                if isinstance(entry, str):
                    normalized = entry.strip().lower()
                    if normalized:
                        known_speakers.append(normalized)

        text_processor = TextProcessor()
        prompt = compose_gemini_prompt(
            {"content": content},
            prompt_prefix,
            known_speakers
        )
        locked = None
        if data.get('directed_mode'):
            # This opt-in operates only on already locked speaker blocks, never
            # on raw prose that still requires speaker attribution.
            locked, prompt, schema = prepare_direction_request(data.get('content') or '')
            structured_options = dict(response_schema=schema,
                                      response_schema_name='tts_story_directions',
                                      response_schema_strict=True)
        response_text, profile_used, provider_failures = _run_llm_prompt_with_failover(
            prompt,
            config,
            preferred_profile=preferred_profile,
            defer_transient_failover=True,
            **structured_options,
        )
        audit = None
        if locked is not None:
            response_text, audit = assemble_directed(locked, response_text)
        detected_speakers = text_processor.extract_speakers(response_text)

        return jsonify({
            "success": True,
            "result_text": response_text if locked is not None else response_text.strip(),
            "speakers": detected_speakers,
            "llm_profile_used": profile_used,
            "llm_provider_used": profile_used["provider"],
            "provider_failures": provider_failures,
            **({"direction_audit": audit} if audit is not None else {}),
        })

    except StructuredOutputError as exc:
        return jsonify({"success": False, "error": str(exc), "retryable": False}), 400
    except (GeminiProcessorError, LocalLLMProcessorError, AtlasCloudProcessorError, OpenRouterProcessorError, LLMProviderChainError) as exc:
        err_str = str(exc)
        transient_markers = ("503", "UNAVAILABLE", "429", "quota", "rate limit", "rate_limit", "high demand", "try again")
        explicit_retryable = getattr(exc, "retryable", None)
        is_transient = (
            bool(explicit_retryable)
            if explicit_retryable is not None
            else any(m.lower() in err_str.lower() for m in transient_markers)
        )
        if is_transient:
            response_payload = {
                "success": False,
                "error": err_str,
                "retryable": True
            }
            current_profile = getattr(exc, "current_profile", None)
            next_profile = getattr(exc, "next_profile", None)
            failures = getattr(exc, "failures", None)
            if current_profile:
                response_payload["retry_profile"] = current_profile
            if next_profile:
                response_payload["next_profile"] = next_profile
            if failures:
                response_payload["provider_failures"] = failures
            return jsonify(response_payload), 503
        return jsonify({
            "success": False,
            "error": err_str
        }), 400
    except Exception as e:  # pragma: no cover - general failure
        logger.error(f"Error processing LLM section: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": "Failed to process section with the configured LLM"
        }), 500


@app.route('/api/prep-progress/save', methods=['POST'])
def save_prep_progress():
    """Persist LLM prep progress to disk so it survives backend restarts."""
    try:
        data = request.json or {}
        text_hash = (data.get('text_hash') or '').strip()
        if not text_hash or not re.match(r'^[a-z0-9_]+$', text_hash):
            return jsonify({"success": False, "error": "Invalid text_hash"}), 400
        payload = {
            "text_hash": text_hash,
            "sections": data.get('sections') or [],
            "outputs": data.get('outputs') or [],
            "known_speakers": data.get('known_speakers') or [],
            "timestamp": data.get('timestamp') or int(time.time() * 1000),
        }
        progress_file = PREP_PROGRESS_DIR / f"{text_hash}.json"
        with progress_file.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
        return jsonify({"success": True})
    except Exception as e:
        logger.error("Error saving prep progress: %s", e, exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/prep-progress/load', methods=['GET'])
def load_prep_progress():
    """Load saved Gemini prep progress for a given text hash."""
    try:
        text_hash = (request.args.get('text_hash') or '').strip()
        if not text_hash or not re.match(r'^[a-z0-9_]+$', text_hash):
            return jsonify({"success": False, "error": "Invalid text_hash"}), 400
        progress_file = PREP_PROGRESS_DIR / f"{text_hash}.json"
        if not progress_file.exists():
            return jsonify({"success": True, "found": False})
        with progress_file.open("r", encoding="utf-8") as f:
            payload = json.load(f)
        return jsonify({"success": True, "found": True, "progress": payload})
    except Exception as e:
        logger.error("Error loading prep progress: %s", e, exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/prep-progress/clear', methods=['DELETE'])
def clear_prep_progress():
    """Delete saved Gemini prep progress for a given text hash."""
    try:
        text_hash = (request.args.get('text_hash') or '').strip()
        if not text_hash or not re.match(r'^[a-z0-9_]+$', text_hash):
            return jsonify({"success": False, "error": "Invalid text_hash"}), 400
        progress_file = PREP_PROGRESS_DIR / f"{text_hash}.json"
        if progress_file.exists():
            progress_file.unlink()
        return jsonify({"success": True})
    except Exception as e:
        logger.error("Error clearing prep progress: %s", e, exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/generate', methods=['POST'])
def generate_audio():
    """Add audio generation job to queue"""
    try:
        # Ensure worker thread is running
        start_worker_thread()
        data = request.json or {}
        text = (data.get('text') or '').strip()
        voice_assignments = data.get('voice_assignments', {})
        logger.info("Received voice_assignments: %s", voice_assignments)
        split_by_chapter = bool(data.get('split_by_chapter', False))
        generate_full_story = bool(data.get('generate_full_story', False)) and split_by_chapter
        section_headings = data.get('section_headings')
        requested_format = (data.get('output_format') or '').strip().lower()
        requested_bitrate = data.get('output_bitrate_kbps')
        requested_engine = (data.get('tts_engine') or '').strip().lower()
        engine_options = data.get('engine_options') if isinstance(data.get('engine_options'), dict) else None
        review_mode = bool(data.get('review_mode', False))
        raw_replacements = data.get('word_replacements')
        word_replacements = [
            r for r in (raw_replacements or [])
            if isinstance(r, dict) and r.get('original') and r.get('replacement')
        ] if isinstance(raw_replacements, list) else []

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
        logger.info("Generation request using engine='%s' (requested='%s')", active_engine, requested_engine or "(config)")
        logger.warning("TTS generation engine selected: %s", active_engine)
        _apply_engine_option_overrides(config, active_engine, engine_options)
        if requested_format:
            config['output_format'] = requested_format
        if requested_bitrate:
            config['output_bitrate_kbps'] = requested_bitrate
        requested_acx = data.get('acx_compliance')
        if requested_acx is not None:
            config['acx_compliance'] = bool(requested_acx)

        voice_assignments = _prepare_voice_assignments(text, voice_assignments)

        _validate_voice_assignments_for_engine(
            active_engine,
            text,
            voice_assignments,
            config,
        )
        
        # Create job
        job_id = str(uuid.uuid4())
        if active_engine == 'breeze_api':
            voice_assignments = BREEZE_PRODUCTIONS.bind(
                job_id, voice_assignments, consent=data.get('breeze_upload_consent') is True,
                title=data.get('production_title') or text[:100])
        text_path = _write_job_text(job_id, text)
        text_length = len(text)
        speakers = _extract_speakers_for_text(text)
        estimated_chunks = estimate_total_chunks(
            text,
            split_by_chapter,
            int(config.get('chunk_size', 500)),
            include_full_story=generate_full_story,
            engine_name=active_engine,
            config=config,
            section_headings=section_headings,
        )
        
        merge_options = {
            "output_format": config.get('output_format'),
            "crossfade_duration": float(config.get('crossfade_duration') or 0),
            "intro_silence_ms": int(config.get('intro_silence_ms', 0) or 0),
            "inter_chunk_silence_ms": int(config.get('inter_chunk_silence_ms', 0) or 0),
            "output_bitrate_kbps": int(config.get('output_bitrate_kbps') or 0),
            "acx_compliance": bool(config.get('acx_compliance', False)),
        }

        job_dir_path = OUTPUT_DIR / job_id
        job_dir_path.mkdir(parents=True, exist_ok=True)
        job_dir = job_dir_path.as_posix()

        with queue_lock:
            jobs[job_id] = {
                "status": "queued",
                "text_preview": text[:200],
                "text_path": text_path,
                "text_length": text_length,
                "created_at": datetime.now().isoformat(),
                "review_mode": review_mode,
                "chapter_mode": split_by_chapter,
                "full_story_requested": generate_full_story,
                "job_dir": job_dir,
                "merge_options": merge_options,
                "chunks": [],
                "voice_assignments": voice_assignments,
                "config_snapshot": _redact_config_secrets(config),
                "custom_heading": json.dumps({"enabled_headings": section_headings}) if section_headings is not None else None,
                "section_headings": section_headings,
                "speakers": speakers,
                "regen_tasks": {},
                "engine": config.get("tts_engine"),
                "resume_from_chunk_index": 0,
                "word_replacements": word_replacements,
            }
            jobs[job_id]["job_payload"] = _build_job_payload(job_id, text, jobs[job_id])
        
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
            "job_dir": job_dir,
            "section_headings": section_headings,
            "resume_from_chunk_index": 0,
            "word_replacements": word_replacements,
        }

        _persist_job_state(job_id, force=True)

        # Write metadata.json so word_replacements (and other fields) survive server restarts
        _meta_path = job_dir_path / JOB_METADATA_FILENAME
        try:
            _meta_path.parent.mkdir(parents=True, exist_ok=True)
            _existing_meta = {}
            if _meta_path.exists():
                try:
                    with _meta_path.open("r", encoding="utf-8") as _f:
                        _existing_meta = json.load(_f)
                except Exception:
                    pass
            _existing_meta["word_replacements"] = word_replacements
            _existing_meta.setdefault("job_id", job_id)
            _existing_meta.setdefault("created_at", jobs[job_id]["created_at"])
            with _meta_path.open("w", encoding="utf-8") as _f:
                json.dump(_existing_meta, _f, indent=2, ensure_ascii=False)
        except Exception as _exc:
            logger.warning("Failed to write metadata.json at job creation for %s: %s", job_id, _exc)

        _archive_old_jobs()

        # Add to queue
        job_queue.put(job_data)
        logger.info(f"Job {job_id} added to queue. Queue size: {job_queue.qsize()}")

        try:
            show_first_run_notice = _consume_engine_first_run_notice(active_engine)
        except Exception as notice_error:
            logger.warning(
                "Unable to persist first-run notice state for %s: %s",
                active_engine,
                notice_error,
            )
            show_first_run_notice = True
        
        return jsonify({
            "success": True,
            "job_id": job_id,
            "status": "queued",
            "queue_position": job_queue.qsize(),
            "first_run_notice": show_first_run_notice,
            "engine": active_engine,
        })
        
    except ValueError as e:
        logger.error(f"Error queueing job: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": str(e)
        }), 400
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
        requested_name = request.args.get('download_name') if request else None

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
            metadata = load_job_metadata(job_dir)
            full_story = (metadata or {}).get("full_story") if metadata else None
            if full_story:
                rel_path = full_story.get("relative_path") or full_story.get("output_file")
                if rel_path:
                    candidate = job_dir / Path(rel_path)
                    if candidate.exists():
                        file_path = candidate
                        output_format = candidate.suffix.lstrip('.')

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

        # Use audiobook_title from metadata if available
        metadata = load_job_metadata(job_dir) or {}
        audiobook_title = metadata.get("audiobook_title")
        if audiobook_title:
            download_name = f"{audiobook_title}_{job_id}.{output_format}"
        else:
            download_name = f"audiobook_{job_id}.{output_format}"
        if requested_name:
            safe_name = Path(requested_name).name
            if safe_name:
                download_name = safe_name

        logger.info(f"Sending file: {file_path}")
        return send_file(
            file_path,
            as_attachment=True,
            download_name=download_name
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


# Global progress tracking for M4B exports
m4b_progress = {}


@app.route('/api/download/<job_id>/m4b', methods=['POST'])
def download_m4b(job_id):
    """Download audiobook as M4B format with chapter markers."""
    try:
        payload = request.get_json(silent=True) or {}
        bitrate_kbps = int(payload.get("bitrate", 128))
        requested_acx_compliance = bool(payload.get("acx_compliance", False))
        cover_art_data = payload.get("cover_art")
        allow_non_square_cover = bool(payload.get("allow_non_square_cover", False))

        job_dir = OUTPUT_DIR / job_id
        if not job_dir.exists():
            return jsonify({
                "success": False,
                "error": "Job directory not found"
            }), 404

        metadata = load_job_metadata(job_dir)
        if not metadata:
            return jsonify({
                "success": False,
                "error": "Metadata not found"
            }), 404

        # Check if original files are already ACX compliant
        original_acx_compliant = metadata.get("acx_compliance", False)
        # Skip ACX processing if original files are already compliant
        acx_compliance = requested_acx_compliance and not original_acx_compliant

        # Only allow M4B for chapter-mode jobs
        if not metadata.get("chapter_mode", False):
            return jsonify({
                "success": False,
                "error": "M4B export is only available for jobs with chapter mode enabled"
            }), 400

        chapters = metadata.get("chapters", [])
        if not chapters:
            return jsonify({
                "success": False,
                "error": "No chapters found"
            }), 400

        # Collect chapter audio files
        chapter_files = []
        chapter_metadata = []
        for chapter in chapters:
            relative_path = chapter.get("relative_path")
            if not relative_path:
                continue
            chapter_path = job_dir / relative_path
            if chapter_path.exists():
                chapter_files.append(str(chapter_path))
                chapter_metadata.append({
                    "title": sanitize_display_title(
                        chapter.get("title", f"Chapter {chapter.get('index', 0)}")
                    ),
                    "start_time": chapter.get("start_time", 0),
                })

        if not chapter_files:
            return jsonify({
                "success": False,
                "error": "No chapter audio files found"
            }), 400

        # Handle cover art
        cover_art_path = None
        if cover_art_data:
            try:
                import base64
                from PIL import Image, ImageOps
                import io

                header, encoded = cover_art_data.split(",", 1)
                img_data = base64.b64decode(encoded)
                img = Image.open(io.BytesIO(img_data))
                img.load()
                img = ImageOps.exif_transpose(img)
                width, height = img.size
                if width != height and not allow_non_square_cover:
                    return jsonify({
                        "success": False,
                        "error": (
                            f"Cover art is {width}x{height}, not square. "
                            "Confirm non-square cover embedding in the M4B dialog or select square artwork."
                        ),
                        "cover_width": width,
                        "cover_height": height,
                        "requires_non_square_confirmation": True,
                    }), 400

                # Convert without cropping; preserve the user's approved aspect ratio.
                if img.mode != "RGB":
                    img = img.convert("RGB")

                cover_art_path = job_dir / "cover_art.jpg"
                img.save(cover_art_path, "JPEG", quality=95)
            except Exception as e:
                logger.warning(f"Failed to process cover art: {e}")
                return jsonify({
                    "success": False,
                    "error": "Cover art could not be decoded. Select a valid PNG or JPEG image."
                }), 400

        output_filename = f"{job_id}.m4b"
        output_path = job_dir / output_filename

        # Initialize progress tracking
        m4b_progress[job_id] = {"progress": 0, "status": "encoding", "error": None}

        from src.audio_merger import AudioMerger
        merger = AudioMerger()
        
        def update_progress(progress):
            m4b_progress[job_id] = {
                "progress": progress,
                "status": "encoding" if progress < 1.0 else "complete",
                "error": None
            }
        
        try:
            merger.merge_to_m4b(
                input_files=chapter_files,
                output_path=str(output_path),
                chapter_metadata=chapter_metadata,
                bitrate_kbps=bitrate_kbps,
                acx_compliance=acx_compliance,
                cover_art_path=cover_art_path,
                progress_callback=update_progress,
            )
        except Exception as e:
            m4b_progress[job_id] = {
                "progress": m4b_progress.get(job_id, {}).get("progress", 0),
                "status": "error",
                "error": str(e)
            }
            raise

        # Get audiobook metadata for filename
        audiobook_title = metadata.get("audiobook_title") or f"audiobook_{job_id}"
        download_name = f"{audiobook_title}.m4b"

        return send_file(
            output_path,
            mimetype='audio/mp4',
            as_attachment=True,
            download_name=download_name
        )

    except Exception as e:
        logger.error(f"Error generating M4B for {job_id}: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/api/download/<job_id>/m4b/progress', methods=['GET'])
def m4b_progress_endpoint(job_id):
    """Get progress of M4B generation."""
    progress_info = m4b_progress.get(job_id, {"progress": 0, "status": "not_started", "error": None})
    return jsonify(progress_info)


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

        if metadata and (metadata.get("chapters") or metadata.get("books") or metadata.get("full_story")):
            chapters_data = []
            total_size = 0
            created_ts = None
            full_story_entry = None
            outputs = metadata.get("books") if metadata.get("book_mode") else metadata.get("chapters")
            for chapter in outputs or []:
                rel_path = chapter.get("relative_path")
                if not rel_path:
                    continue
                file_path = job_dir / Path(rel_path)
                file_exists = file_path.exists()

                if file_exists:
                    stat = file_path.stat()
                    created_time = datetime.fromtimestamp(stat.st_ctime)
                    created_ts = created_ts or created_time
                    total_size += stat.st_size
                    file_size = stat.st_size
                    file_format = file_path.suffix.lstrip('.')
                else:
                    file_size = None
                    file_format = metadata.get("output_format")

                chapters_data.append({
                    "index": chapter.get("index"),
                    "title": sanitize_display_title(chapter.get("title")),
                    "output_file": f"/static/audio/{job_id}/{Path(rel_path).as_posix()}",
                    "relative_path": Path(rel_path).as_posix(),
                    "file_size": file_size,
                    "format": file_format,
                    "missing_file": not file_exists,
                })

            manifest_path = job_dir / "review_manifest.json"
            if manifest_path.exists():
                try:
                    with manifest_path.open("r", encoding="utf-8") as handle:
                        manifest = json.load(handle)
                    manifest_chapters = manifest.get("chapters") or []
                except Exception:
                    manifest_chapters = []

                if manifest_chapters:
                    existing_paths = {chapter.get("relative_path") for chapter in chapters_data if chapter.get("relative_path")}
                    for chapter in manifest_chapters:
                        output_filename = chapter.get("output_filename")
                        if not output_filename:
                            continue
                        chapter_dir = chapter.get("chapter_dir") or "."
                        rel_path = (Path(chapter_dir) / output_filename).as_posix()
                        if rel_path.startswith("./"):
                            rel_path = rel_path[2:]
                        if rel_path in existing_paths:
                            continue
                        file_path = job_dir / Path(rel_path)
                        file_exists = file_path.exists()

                        if file_exists:
                            stat = file_path.stat()
                            created_time = datetime.fromtimestamp(stat.st_ctime)
                            created_ts = created_ts or created_time
                            total_size += stat.st_size
                            file_size = stat.st_size
                            file_format = file_path.suffix.lstrip(".")
                        else:
                            file_size = None
                            file_format = metadata.get("output_format")

                        chapters_data.append({
                            "index": chapter.get("index"),
                            "title": sanitize_display_title(chapter.get("title")),
                            "output_file": f"/static/audio/{job_id}/{rel_path}",
                            "relative_path": rel_path,
                            "file_size": file_size,
                            "format": file_format,
                            "missing_file": not file_exists,
                        })
                        existing_paths.add(rel_path)

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

            # Read engine and timing_metrics from chunks_metadata.json once for both branches
            _lib_chunks_meta_path = job_dir / "chunks_metadata.json"
            _lib_manifest_path = job_dir / "review_manifest.json"
            _lib_has_chunks = _lib_chunks_meta_path.exists() or _lib_manifest_path.exists()
            _lib_engine = None
            _lib_timing_metrics = None
            _lib_inferred_title = None
            if _lib_chunks_meta_path.exists():
                try:
                    with _lib_chunks_meta_path.open("r", encoding="utf-8") as f:
                        _lib_cmeta = json.load(f)
                        _lib_engine = _lib_cmeta.get("engine")
                        _lib_timing_metrics = _lib_cmeta.get("timing_metrics")
                        _lib_inferred_title = infer_collection_title_from_chunks(
                            _lib_cmeta.get("chunks") or []
                        )
                except Exception:
                    pass
            # Also check live job entry for timing_metrics (may be more up-to-date)
            _live_tm = (jobs.get(job_id) or {}).get("timing_metrics")
            if _live_tm:
                _lib_timing_metrics = _live_tm

            if chapters_data:
                chapters_data.sort(key=lambda c: c.get("index") or 0)
                _word_replacements = (jobs.get(job_id) or {}).get("word_replacements") or metadata.get("word_replacements") or []
                library_items.append({
                    "job_id": job_id,
                    "output_file": chapters_data[0]["output_file"],
                    "relative_path": chapters_data[0]["relative_path"],
                    "created_at": (created_ts or datetime.now()).isoformat(),
                    "file_size": total_size,
                    "format": metadata.get("output_format", chapters_data[0]["format"]),
                    "chapter_mode": metadata.get("chapter_mode", False),
                    "book_mode": metadata.get("book_mode", False),
                    "collection_title": metadata.get("collection_title") or _lib_inferred_title,
                    "books": chapters_data if metadata.get("book_mode") else [],
                    "chapters": chapters_data,
                    "full_story": full_story_entry,
                    "has_chunks": _lib_has_chunks,
                    "engine": _lib_engine,
                    "timing_metrics": _lib_timing_metrics,
                    "word_replacements": _word_replacements,
                    "audiobook_title": metadata.get("audiobook_title"),
                    "audiobook_author": metadata.get("audiobook_author"),
                    "audiobook_genre": metadata.get("audiobook_genre"),
                    "audiobook_year": metadata.get("audiobook_year"),
                    "audiobook_description": metadata.get("audiobook_description"),
                    "acx_compliance": metadata.get("acx_compliance", False),
                })
            elif full_story_entry:
                _word_replacements2 = (jobs.get(job_id) or {}).get("word_replacements") or metadata.get("word_replacements") or []
                library_items.append({
                    "job_id": job_id,
                    "output_file": full_story_entry["output_file"],
                    "relative_path": full_story_entry["relative_path"],
                    "created_at": (created_ts or datetime.now()).isoformat(),
                    "file_size": total_size or full_story_entry.get("file_size"),
                    "format": metadata.get("output_format", full_story_entry.get("format")),
                    "chapter_mode": metadata.get("chapter_mode", False),
                    "book_mode": metadata.get("book_mode", False),
                    "collection_title": metadata.get("collection_title") or _lib_inferred_title,
                    "books": [],
                    "chapters": [],
                    "full_story": full_story_entry,
                    "has_chunks": _lib_has_chunks,
                    "engine": _lib_engine,
                    "timing_metrics": _lib_timing_metrics,
                    "word_replacements": _word_replacements2,
                    "audiobook_title": metadata.get("audiobook_title"),
                    "audiobook_author": metadata.get("audiobook_author"),
                    "audiobook_genre": metadata.get("audiobook_genre"),
                    "audiobook_year": metadata.get("audiobook_year"),
                    "audiobook_description": metadata.get("audiobook_description"),
                    "acx_compliance": metadata.get("acx_compliance", False),
                })
            continue

        # Fallback: include chapter/book outputs even if metadata.json is missing.
        # This makes the library resilient if metadata writing failed but audio files exist.
        chapter_output_files = sorted(job_dir.glob("chapter_*/*"))
        if not chapter_output_files:
            chapter_output_files = sorted(job_dir.glob("book_*/*/*"))

        if chapter_output_files:
            chapters_data = []
            total_size = 0
            created_ts = None

            for idx, file_path in enumerate(chapter_output_files, start=1):
                if not file_path.is_file():
                    continue
                if file_path.name.lower().startswith("_silence_"):
                    continue
                if file_path.suffix.lower() not in {".mp3", ".wav", ".m4a", ".ogg", ".aac"}:
                    continue

                stat = file_path.stat()
                created_time = datetime.fromtimestamp(stat.st_ctime)
                created_ts = created_ts or created_time
                total_size += stat.st_size
                rel_path = file_path.relative_to(job_dir).as_posix()
                chapters_data.append({
                    "index": idx,
                    "title": f"Chapter {idx}",
                    "output_file": f"/static/audio/{job_id}/{rel_path}",
                    "relative_path": rel_path,
                    "file_size": stat.st_size,
                    "format": file_path.suffix.lstrip('.'),
                })

            if chapters_data:
                chunks_meta_path = job_dir / "chunks_metadata.json"
                manifest_path = job_dir / "review_manifest.json"
                has_chunks = chunks_meta_path.exists() or manifest_path.exists()
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
                    "format": chapters_data[0]["format"],
                    "chapter_mode": True,
                    "book_mode": False,
                    "books": [],
                    "chapters": chapters_data,
                    "full_story": None,
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


@app.route('/api/library/<job_id>/chapter-durations', methods=['GET'])
def get_library_chapter_durations(job_id):
    """Return title + exact start_time (seconds) for each chapter in the full-story audio.

    Calculates start times by walking the raw chunk files in the same order that
    AudioMerger uses when building full_story.mp3 — intro_silence prepended once,
    then inter_chunk_silence between every chunk.  This is the only approach that
    gives accurate timestamps regardless of how many chunks are in each chapter.
    """
    job_dir = OUTPUT_DIR / job_id
    if not job_dir.exists():
        return jsonify({"success": False, "error": "Item not found"}), 404

    # Load merge silence settings (new jobs have them in metadata.json; old jobs fall back to config)
    metadata_path = job_dir / "metadata.json"
    metadata = {}
    if metadata_path.exists():
        try:
            with metadata_path.open("r", encoding="utf-8") as f:
                metadata = json.load(f)
        except Exception:
            pass

    def _silence_val(key):
        if key in metadata:
            return int(max(0, metadata[key] or 0))
        try:
            return int(max(0, load_config().get(key) or 0))
        except Exception:
            return 0

    intro_silence_s = _silence_val("intro_silence_ms") / 1000.0
    inter_silence_s = _silence_val("inter_chunk_silence_ms") / 1000.0

    # Try to load review_manifest.json which has chunk-level detail
    manifest_path = job_dir / "review_manifest.json"
    manifest = {}
    if manifest_path.exists():
        try:
            with manifest_path.open("r", encoding="utf-8") as f:
                manifest = json.load(f)
        except Exception:
            pass

    manifest_chapters = manifest.get("chapters") or []
    all_full_story_chunks = manifest.get("all_full_story_chunks") or []

    def _chunk_duration(rel_path: str) -> float:
        p = job_dir / rel_path
        if not p.exists():
            return 0.0
        try:
            info = sf.info(str(p))
            return info.frames / info.samplerate
        except Exception:
            try:
                import wave
                if p.suffix.lower() == ".wav":
                    with wave.open(str(p), "rb") as wf:
                        return wf.getnframes() / wf.getframerate()
            except Exception:
                pass
            return 0.0

    chapters = []

    if manifest_chapters and all_full_story_chunks:
        # Build a map from chunk rel-path to chapter index
        chunk_to_chapter: Dict[str, int] = {}
        for c_idx, ch in enumerate(manifest_chapters):
            for rf in (ch.get("chunk_files") or []):
                chunk_to_chapter[rf] = c_idx

        # Walk chunks in full-story order, exactly as AudioMerger does.
        # The first chapter always starts at 0:00 (the intro_silence before it
        # is the very start of the file, so the timestamp for chapter 1 is 0).
        cursor = intro_silence_s
        current_chapter_idx = -1
        for i, rel_chunk in enumerate(all_full_story_chunks):
            c_idx = chunk_to_chapter.get(rel_chunk, -1)
            if c_idx != current_chapter_idx:
                current_chapter_idx = c_idx
                ch_meta = manifest_chapters[c_idx] if c_idx >= 0 else {}
                title = ch_meta.get("title") or f"Chapter {c_idx + 1}"
                start = 0.0 if not chapters else round(cursor, 3)
                chapters.append({"title": title, "start_time": start})
            dur = _chunk_duration(rel_chunk)
            cursor += dur
            if i < len(all_full_story_chunks) - 1:
                cursor += inter_silence_s

    else:
        # Fallback: use chapter audio file durations with silence correction.
        # Less accurate but works when chunk files have been cleaned up.
        raw_chapters = metadata.get("chapters") or []

        def _file_duration(rel: str) -> float:
            p = job_dir / rel
            if not p.exists():
                p = job_dir / Path(rel).name
            if not p.exists():
                return 0.0
            return _chunk_duration(str(p.relative_to(job_dir)))

        cursor = 0.0
        for idx, ch in enumerate(raw_chapters):
            rel = ch.get("relative_path") or ch.get("output_filename") or ""
            title = ch.get("title") or f"Chapter {ch.get('index', '?')}"
            if not rel:
                continue
            chapters.append({"title": title, "start_time": round(cursor, 3)})
            dur = _file_duration(rel)
            # Each chapter file has intro_silence baked in; only the first one's
            # intro_silence is present in the full story.
            effective = dur - (intro_silence_s if idx > 0 else 0)
            cursor += effective + (inter_silence_s if idx < len(raw_chapters) - 1 else 0)

    if not chapters:
        return jsonify({"success": False, "error": "No chapter data found for this item"}), 404

    return jsonify({
        "success": True,
        "chapters": chapters,
    })


@app.route('/api/library/<job_id>/restore-review', methods=['POST'])
def restore_library_item_to_review(job_id):
    """Restore a completed library item back to review mode for chunk editing."""
    try:
        job_dir = OUTPUT_DIR / job_id
        if not job_dir.exists():
            return jsonify({"success": False, "error": "Item not found"}), 404

        reused_payload = None
        with queue_lock:
            existing_job = jobs.get(job_id)
            if can_reuse_active_review_job(existing_job, job_dir):
                reused_payload = {
                    "success": True,
                    "job_id": job_id,
                    "chunk_count": len(existing_job.get("chunks") or []),
                    "already_restored": True,
                    "has_active_regen": _has_active_regen_tasks(existing_job),
                }
        if reused_payload is not None:
            return jsonify(reused_payload)

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
        metadata = load_job_metadata(job_dir) or {}

        config_snapshot = load_config()
        engine_name = chunks_meta.get("engine") or config_snapshot.get("tts_engine", "kokoro")
        # Ensure config_snapshot uses the original job's engine, not the current config
        config_snapshot["tts_engine"] = engine_name
        logger.info(f"Restoring job {job_id} with engine: {engine_name}")

        # Prefer chunks from chunks_metadata.json if available (has text/voice data)
        chunks = chunks_meta.get("chunks") or []
        chunks.sort(key=lambda c: c.get("order_index") if c.get("order_index") is not None else float('inf'))

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
                "config_snapshot": _redact_config_secrets(config_snapshot),
                "merge_options": {
                    "output_format": metadata.get("output_format") or config_snapshot.get("output_format"),
                    "crossfade_duration": float(metadata.get("crossfade_duration") or 0),
                    "intro_silence_ms": int(metadata.get("intro_silence_ms") or 0),
                    "inter_chunk_silence_ms": int(metadata.get("inter_chunk_silence_ms") or 0),
                    "output_bitrate_kbps": int(metadata.get("output_bitrate_kbps") or 0),
                    "acx_compliance": bool(metadata.get("acx_compliance", False)),
                },
                "word_replacements": metadata.get("word_replacements") or [],
                "chunks": valid_chunks,
                "regen_tasks": {},
                "engine": engine_name,
                "restored_at": datetime.now().isoformat(),
                "created_at": (
                    metadata.get("created_at")
                    or chunks_meta.get("created_at")
                    or datetime.fromtimestamp(job_dir.stat().st_ctime).isoformat()
                ),
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
        chunks.sort(key=lambda c: c.get("order_index") if c.get("order_index") is not None else float('inf'))
        for chunk in chunks:
            rel_file = chunk.get("relative_file")
            if rel_file:
                chunk["file_url"] = f"/static/audio/{job_id}/{rel_file}"

        # Load chapter information from review_manifest if available
        chapters = []
        books = []
        manifest_path = job_dir / "review_manifest.json"
        full_story_available = False
        if manifest_path.exists():
            with manifest_path.open("r", encoding="utf-8") as handle:
                manifest = json.load(handle)
                chapter_mode = manifest.get("chapter_mode", False)
                full_story_available = bool(manifest.get("all_full_story_chunks"))
                if chapter_mode:
                    for ch in manifest.get("chapters", []):
                        output_filename = ch.get("output_filename")
                        chapter_dir = ch.get("chapter_dir") or "."
                        rel_path = None
                        if output_filename:
                            rel_path = (Path(chapter_dir) / output_filename).as_posix()
                            if rel_path.startswith("./"):
                                rel_path = rel_path[2:]
                        chapters.append({
                            "index": ch.get("index"),
                            "title": ch.get("title"),
                            "output_filename": ch.get("output_filename"),
                            "relative_path": rel_path,
                            "book_index": ch.get("book_index"),
                            "book_title": ch.get("book_title"),
                            "book_order": ch.get("book_order"),
                        })
                if manifest.get("book_mode"):
                    for book in manifest.get("books", []):
                        output_filename = book.get("output_filename")
                        rel_path = None
                        if output_filename:
                            rel_path = (Path(book.get("book_dir") or ".") / output_filename).as_posix()
                            if rel_path.startswith("./"):
                                rel_path = rel_path[2:]
                        books.append({
                            "index": book.get("index"),
                            "title": book.get("title"),
                            "output_filename": book.get("output_filename"),
                            "relative_path": rel_path,
                            "chapter_indices": book.get("chapter_indices") or [],
                        })

        return jsonify({
            "success": True,
            "job_id": job_id,
            "engine": chunks_meta.get("engine", "kokoro"),
            "created_at": chunks_meta.get("created_at"),
            "updated_at": chunks_meta.get("updated_at"),
            "chunks": chunks,
            "chapters": chapters,
            "books": books,
            "has_chapters": len(chapters) > 1,
            "has_books": len(books) > 0,
            "full_story_available": full_story_available,
        })

    except Exception as exc:
        logger.error("Failed to get chunks for library item %s: %s", job_id, exc, exc_info=True)
        return jsonify({"success": False, "error": "Failed to load chunk data"}), 500


def _build_review_merger(config_snapshot: Optional[Dict[str, Any]] = None) -> AudioMerger:
    config_snapshot = config_snapshot or load_config()
    crossfade_seconds = float(config_snapshot.get("crossfade_duration") or 0)
    return AudioMerger(
        crossfade_ms=int(max(0.0, crossfade_seconds) * 1000),
        intro_silence_ms=int(max(0, config_snapshot.get("intro_silence_ms") or 0)),
        inter_chunk_silence_ms=int(max(0, config_snapshot.get("inter_chunk_silence_ms") or 0)),
        bitrate_kbps=int(config_snapshot.get("output_bitrate_kbps") or 0),
        acx_compliance=bool(config_snapshot.get("acx_compliance", False)),
    )


def _load_library_merge_options(
    job_dir: Path,
    manifest: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Load rebuild settings without replacing a job's saved export choices."""
    current = dict(load_config())
    metadata = load_job_metadata(job_dir) or {}
    manifest = manifest or {}
    option_names = (
        "output_format",
        "crossfade_duration",
        "intro_silence_ms",
        "inter_chunk_silence_ms",
        "output_bitrate_kbps",
        "acx_compliance",
    )
    resolved = dict(current)
    for option_name in option_names:
        if option_name in metadata and metadata[option_name] is not None:
            resolved[option_name] = metadata[option_name]
        elif option_name in manifest and manifest[option_name] is not None:
            resolved[option_name] = manifest[option_name]
    return resolved


def _update_metadata_chapter(job_id: str, job_dir: Path, chapter_entry: Dict[str, Any]) -> None:
    metadata = load_job_metadata(job_dir) or {}
    chapters = metadata.get("chapters") or []
    rel_path = chapter_entry.get("relative_path")
    chapter_index = chapter_entry.get("index")
    updated = False
    for position, entry in enumerate(chapters):
        if rel_path and entry.get("relative_path") == rel_path:
            custom_title = get_custom_chapter_title(metadata, chapter_index, position)
            if custom_title:
                chapter_entry["title"] = custom_title
            entry.update(chapter_entry)
            updated = True
            break
        if chapter_index is not None and entry.get("index") == chapter_index:
            custom_title = get_custom_chapter_title(metadata, chapter_index, position)
            if custom_title:
                chapter_entry["title"] = custom_title
            entry.update(chapter_entry)
            updated = True
            break
    if not updated:
        custom_title = get_custom_chapter_title(metadata, chapter_index)
        if custom_title:
            chapter_entry["title"] = custom_title
        chapters.append(chapter_entry)
    metadata["chapters"] = chapters
    metadata["chapter_count"] = len(chapters)
    if chapter_entry.get("format") and not metadata.get("output_format"):
        metadata["output_format"] = chapter_entry.get("format")
    save_job_metadata(job_dir, metadata)


def _update_metadata_full_story(job_id: str, job_dir: Path, full_story_entry: Dict[str, Any]) -> None:
    metadata = load_job_metadata(job_dir) or {}
    metadata["full_story"] = full_story_entry
    if full_story_entry.get("format") and not metadata.get("output_format"):
        metadata["output_format"] = full_story_entry.get("format")
    save_job_metadata(job_dir, metadata)


def _remove_existing_output(file_path: Path) -> None:
    try:
        if file_path.exists():
            file_path.unlink()
    except Exception as exc:
        logger.warning("Unable to remove existing output %s: %s", file_path, exc)


def _resolve_chapter_output_path(job_dir: Path, target: Dict[str, Any], output_format: str, chapter_index: int) -> Path:
    output_filename = target.get("output_filename") or f"chapter_{chapter_index + 1:02d}.{output_format}"
    chapter_dir = job_dir / (target.get("chapter_dir") or ".")
    chapter_dir.mkdir(parents=True, exist_ok=True)
    return chapter_dir / output_filename


def _sorted_chunk_files(chunk_dir: Path) -> List[Path]:
    def chunk_sort_key(path: Path) -> Tuple[int, str]:
        match = re.search(r"(\d+)", path.stem)
        return (int(match.group(1)) if match else 0, path.name)

    return sorted(chunk_dir.glob("chunk_*.wav"), key=chunk_sort_key)


def _scan_chunk_folders(job_dir: Path) -> List[Dict[str, Any]]:
    sources: List[Dict[str, Any]] = []
    title_chunk_dir = job_dir / "title" / "chunks"
    if title_chunk_dir.exists():
        title_chunks = _sorted_chunk_files(title_chunk_dir)
        if title_chunks:
            sources.append({
                "chapter_number": 0,
                "chapter_dir": "title",
                "chunk_dir": "title/chunks",
                "chunk_files": [path for path in title_chunks],
                "is_title": True,
            })

    chapter_dirs = []
    for chapter_dir in job_dir.glob("chapter_*"):
        match = re.match(r"chapter_(\d+)", chapter_dir.name)
        if not match:
            continue
        chapter_dirs.append((int(match.group(1)), chapter_dir))

    for chapter_number, chapter_dir in sorted(chapter_dirs, key=lambda item: item[0]):
        chunk_dir = chapter_dir / "chunks"
        if not chunk_dir.exists():
            continue
        chunks = _sorted_chunk_files(chunk_dir)
        if not chunks:
            continue
        sources.append({
            "chapter_number": chapter_number,
            "chapter_dir": chapter_dir.name,
            "chunk_dir": f"{chapter_dir.name}/chunks",
            "chunk_files": [path for path in chunks],
            "is_title": False,
        })

    return sources


def _rebuild_review_manifest_from_chunks(job_id: str, job_dir: Path, force_rebuild: bool = False) -> Dict[str, Any]:
    chunks_meta_path = job_dir / "chunks_metadata.json"
    if not chunks_meta_path.exists():
        raise FileNotFoundError("chunks_metadata.json not found")

    with chunks_meta_path.open("r", encoding="utf-8") as handle:
        chunks_meta = json.load(handle)

    chunks = [dict(item) for item in (chunks_meta.get("chunks") or []) if isinstance(item, dict)]
    chunk_sources = _scan_chunk_folders(job_dir)
    has_title_section = any(source.get("is_title") for source in chunk_sources)
    if not chunks and not chunk_sources:
        raise ValueError("No chunks found for this job")

    existing_manifest = None
    manifest_path = job_dir / "review_manifest.json"
    if manifest_path.exists():
        try:
            with manifest_path.open("r", encoding="utf-8") as handle:
                existing_manifest = json.load(handle)
        except Exception:
            existing_manifest = None

    title_by_index = {}
    if existing_manifest:
        for entry in existing_manifest.get("chapters") or []:
            if entry.get("index") is not None and entry.get("title"):
                title_by_index[int(entry["index"])] = entry["title"]

    output_format = None
    metadata = load_job_metadata(job_dir) or {}
    if metadata.get("output_format"):
        output_format = metadata.get("output_format")
    if not output_format:
        config = load_config()
        output_format = config.get("output_format") or "mp3"

    chapter_map: Dict[int, Dict[str, Any]] = {}
    all_full_story_chunks: List[str] = []

    if chunk_sources:
        # Build lookup from original chunks_metadata keyed by normalised relative_file
        # so speaker/text/voice data is preserved during force_rebuild.
        original_by_rel: Dict[str, Dict[str, Any]] = {}
        for orig in chunks:
            rel = (orig.get("relative_file") or "").replace("\\", "/")
            if rel:
                original_by_rel[rel] = orig

        rebuilt_chunks = []
        order_index = 0
        for source in chunk_sources:
            chapter_number = int(source["chapter_number"])
            chapter_index = 0 if source.get("is_title") else (chapter_number if has_title_section else chapter_number - 1)
            chunk_files = []
            for chunk_path in source["chunk_files"]:
                rel_file = chunk_path.relative_to(job_dir).as_posix()
                chunk_files.append(rel_file)
                chunk_match = re.search(r"(\d+)", chunk_path.stem)
                chunk_index = int(chunk_match.group(1)) if chunk_match else 0
                orig = original_by_rel.get(rel_file) or {}
                record = {
                    "id": f"{chapter_index}-{chunk_index}-{order_index}",
                    "order_index": order_index,
                    "chapter_index": chapter_index,
                    "chunk_index": chunk_index,
                    "relative_file": rel_file,
                }
                # Carry over text/speaker/voice data from original if present
                for field in ("speaker", "text", "engine", "emotion", "delivery_instruction", "voice_assignment", "voice_label",
                              "duration_seconds", "regenerated_at", "regen_status", "file_path"):
                    if field in orig:
                        record[field] = orig[field]
                rebuilt_chunks.append(record)
                order_index += 1

            all_full_story_chunks.extend(chunk_files)
            chapter_map[chapter_index] = {
                "chunk_files": chunk_files,
                "chunk_dir": source["chunk_dir"],
                "chapter_dir": source["chapter_dir"],
                "chapter_number": chapter_number,
                "is_title": source.get("is_title", False),
            }

        if force_rebuild:
            chunks_meta_path = job_dir / "chunks_metadata.json"
            chunks_meta = {
                "engine": chunks_meta.get("engine"),
                "created_at": chunks_meta.get("created_at", datetime.now().isoformat()),
                "updated_at": datetime.now().isoformat(),
                "chunks": rebuilt_chunks,
            }
            with chunks_meta_path.open("w", encoding="utf-8") as handle:
                json.dump(chunks_meta, handle, indent=2)
            chunks = rebuilt_chunks
    else:
        sorted_chunks = sorted(chunks, key=lambda c: (c.get("chapter_index") or 0, c.get("order_index") or 0))

        for chunk in sorted_chunks:
            chapter_index = chunk.get("chapter_index")
            if chapter_index is None:
                continue
            rel_file = chunk.get("relative_file")
            if not rel_file:
                file_path = chunk.get("file_path")
                if file_path:
                    rel_file = os.path.relpath(file_path, job_dir)
            if not rel_file:
                continue
            rel_file = rel_file.replace("\\", "/")

            all_full_story_chunks.append(rel_file)

            entry = chapter_map.setdefault(int(chapter_index), {
                "chunk_files": [],
                "chunk_dir": None,
                "chapter_dir": None,
            })
            entry["chunk_files"].append(rel_file)

            rel_path = Path(rel_file)
            parts = list(rel_path.parts)
            if "chunks" in parts:
                chunk_idx = parts.index("chunks")
                entry["chunk_dir"] = Path(*parts[:chunk_idx + 1]).as_posix()
                entry["chapter_dir"] = Path(*parts[:chunk_idx]).as_posix() or "."
            else:
                entry["chunk_dir"] = rel_path.parent.as_posix()
                entry["chapter_dir"] = rel_path.parent.parent.as_posix() if rel_path.parent.parent else "."

    if not chapter_map:
        raise ValueError("No chapter data could be derived from chunks")

    merge_options = _load_library_merge_options(job_dir, existing_manifest)
    merger = _build_review_merger(merge_options)
    chapter_entries = []
    chapter_outputs = []

    # Collect merge tasks for parallel processing
    merge_tasks = []
    for chapter_index in sorted(chapter_map.keys()):
        data = chapter_map[chapter_index]
        chunk_files = data.get("chunk_files") or []
        if not chunk_files:
            continue

        chapter_number = data.get("chapter_number")
        is_title_section = bool(data.get("is_title"))
        chapter_dir = data.get("chapter_dir") or "."
        if is_title_section:
            title = title_by_index.get(chapter_index) or "Title"
            output_filename = f"title.{output_format}"
        else:
            display_number = chapter_number if isinstance(chapter_number, int) else (chapter_index + 1)
            title = title_by_index.get(chapter_index) or f"Chapter {display_number}"
            output_filename = f"chapter_{display_number:02d}.{output_format}"

        target = {
            "chapter_dir": chapter_dir,
            "output_filename": output_filename,
        }
        output_path = _resolve_chapter_output_path(job_dir, target, output_format, chapter_index)
        
        if force_rebuild:
            output_dir = output_path.parent
            if output_dir.exists():
                for item in output_dir.iterdir():
                    if item.is_file():
                        _remove_existing_output(item)
        
        if force_rebuild or not output_path.exists():
            chunk_paths = [str(job_dir / Path(rel_path)) for rel_path in chunk_files]
            missing = [p for p in chunk_paths if not Path(p).exists()]
            if not missing:
                merge_tasks.append({
                    "chapter_index": chapter_index,
                    "title": title,
                    "chunk_files": chunk_files,
                    "chunk_paths": chunk_paths,
                    "output_path": output_path,
                    "chapter_dir": chapter_dir,
                    "output_filename": output_filename,
                })
            else:
                logger.warning("Missing chunk files for chapter %s: %s", chapter_index, missing)
                # Still add entry even if missing chunks
                rel_output = (Path(chapter_dir) / output_path.name).as_posix()
                if rel_output.startswith("./"):
                    rel_output = rel_output[2:]
                chapter_entries.append({
                    "index": chapter_index,
                    "title": title,
                    "chunk_dir": data.get("chunk_dir"),
                    "chunk_files": chunk_files,
                    "chapter_dir": chapter_dir,
                    "output_filename": output_path.name,
                })
                if output_path.exists():
                    chapter_outputs.append({
                        "index": chapter_index,
                        "title": title,
                        "file_url": f"/static/audio/{job_id}/{rel_output}",
                        "relative_path": rel_output,
                        "format": output_format,
                    })
        else:
            # File exists, just add entries without merging
            rel_output = (Path(chapter_dir) / output_path.name).as_posix()
            if rel_output.startswith("./"):
                rel_output = rel_output[2:]
            chapter_entries.append({
                "index": chapter_index,
                "title": title,
                "chunk_dir": data.get("chunk_dir"),
                "chunk_files": chunk_files,
                "chapter_dir": chapter_dir,
                "output_filename": output_path.name,
            })
            chapter_outputs.append({
                "index": chapter_index,
                "title": title,
                "file_url": f"/static/audio/{job_id}/{rel_output}",
                "relative_path": rel_output,
                "format": output_format,
            })
    
    # Execute merges in parallel with dynamic worker allocation
    if merge_tasks:
        def repair_merge_wrapper(task):
            """Wrapper function for parallel merge in repair operation"""
            chapter_index = task["chapter_index"]
            chunk_paths = task["chunk_paths"]
            output_path = task["output_path"]
            
            merger.merge_wav_files(
                input_files=chunk_paths,
                output_path=str(output_path),
                format=output_format,
                cleanup_chunks=False,
            )
            return task
        
        # Use CPU count for dynamic worker allocation, capped at total tasks
        max_workers = min(os.cpu_count() or 4, len(merge_tasks))
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_task = {executor.submit(repair_merge_wrapper, task): task for task in merge_tasks}
            
            for future in concurrent.futures.as_completed(future_to_task):
                try:
                    task = future.result()
                    rel_output = (Path(task["chapter_dir"]) / task["output_path"].name).as_posix()
                    if rel_output.startswith("./"):
                        rel_output = rel_output[2:]
                    
                    chapter_entries.append({
                        "index": task["chapter_index"],
                        "title": task["title"],
                        "chunk_dir": task["chapter_dir"],
                        "chunk_files": task["chunk_files"],
                        "chapter_dir": task["chapter_dir"],
                        "output_filename": task["output_path"].name,
                    })
                    chapter_outputs.append({
                        "index": task["chapter_index"],
                        "title": task["title"],
                        "file_url": f"/static/audio/{job_id}/{rel_output}",
                        "relative_path": rel_output,
                        "format": output_format,
                    })
                except Exception as e:
                    logger.error(f"Merge task failed for chapter {task['chapter_index']}: {e}")
                    raise

    full_story_entry = None
    full_story_path = job_dir / f"full_story.{output_format}"
    if all_full_story_chunks:
        if force_rebuild:
            _remove_existing_output(full_story_path)
        if force_rebuild or not full_story_path.exists():
            chunk_paths = [str(job_dir / Path(rel_path)) for rel_path in all_full_story_chunks]
            missing = [p for p in chunk_paths if not Path(p).exists()]
            if not missing:
                merger.merge_wav_files(
                    input_files=chunk_paths,
                    output_path=str(full_story_path),
                    format=output_format,
                    cleanup_chunks=False,
                )
        if full_story_path.exists():
            full_story_entry = {
                "title": "Full Story",
                "file_url": f"/static/audio/{job_id}/{full_story_path.name}",
                "relative_path": full_story_path.name,
                "format": output_format,
            }

    review_manifest = {
        "chapter_mode": True,
        "book_mode": False,
        "chapters": chapter_entries,
        "books": [],
        "full_story_requested": bool(all_full_story_chunks),
        "output_format": output_format,
        "chunk_dirs_to_cleanup": [c.get("chunk_dir") for c in chapter_entries if c.get("chunk_dir")],
        "all_full_story_chunks": all_full_story_chunks,
    }
    with manifest_path.open("w", encoding="utf-8") as handle:
        json.dump(review_manifest, handle, indent=2)

    metadata.update({
        "chapter_mode": True,
        "book_mode": False,
        "output_format": output_format,
        "chapters": chapter_outputs,
        "chapter_count": len(chapter_outputs),
        "books": [],
        "book_count": 0,
        "full_story": full_story_entry,
    })
    save_job_metadata(job_dir, metadata)

    return {
        "chapters": chapter_outputs,
        "full_story": full_story_entry,
        "manifest": review_manifest,
    }


@app.route('/api/library/<job_id>/rebuild/chapter', methods=['POST'])
def rebuild_library_chapter(job_id):
    """Rebuild a single chapter output from review chunks."""
    try:
        payload = request.get_json(silent=True) or {}
        if "chapter_index" not in payload:
            return jsonify({"success": False, "error": "chapter_index is required"}), 400
        chapter_index = int(payload.get("chapter_index"))

        job_dir = OUTPUT_DIR / job_id
        if not job_dir.exists():
            return jsonify({"success": False, "error": "Item not found"}), 404

        manifest_path = job_dir / "review_manifest.json"
        if not manifest_path.exists():
            return jsonify({"success": False, "error": "Review manifest not found"}), 404

        with manifest_path.open("r", encoding="utf-8") as handle:
            manifest = json.load(handle)

        chapters = manifest.get("chapters") or []
        target = next((ch for ch in chapters if ch.get("index") == chapter_index), None)
        if not target and chapters:
            target = chapters[min(max(chapter_index, 0), len(chapters) - 1)]
        if not target:
            return jsonify({"success": False, "error": "Chapter not found"}), 404

        chunk_files = target.get("chunk_files") or []
        if not chunk_files:
            return jsonify({"success": False, "error": "No chunk files available for this chapter"}), 400

        chunk_paths = [str(job_dir / rel_path) for rel_path in chunk_files]
        missing = [p for p in chunk_paths if not Path(p).exists()]
        if missing:
            return jsonify({"success": False, "error": "Missing chunk files for this chapter"}), 409

        config_snapshot = _load_library_merge_options(job_dir, manifest)
        output_format = config_snapshot.get("output_format") or "mp3"
        output_path = _resolve_chapter_output_path(job_dir, target, output_format, chapter_index)
        _remove_existing_output(output_path)

        merger = _build_review_merger(config_snapshot)
        merger.merge_wav_files(
            input_files=chunk_paths,
            output_path=str(output_path),
            format=output_format,
            cleanup_chunks=False,
        )

        rel_path = (Path(target.get("chapter_dir") or ".") / output_path.name).as_posix()
        if rel_path.startswith("./"):
            rel_path = rel_path[2:]
        chapter_entry = {
            "index": target.get("index"),
            "title": target.get("title"),
            "file_url": f"/static/audio/{job_id}/{rel_path}",
            "relative_path": rel_path,
            "format": output_format,
        }
        _update_metadata_chapter(job_id, job_dir, chapter_entry)
        invalidate_library_cache()

        return jsonify({"success": True, "chapter": chapter_entry})
    except Exception as exc:
        logger.error("Failed to rebuild chapter for %s: %s", job_id, exc, exc_info=True)
        return jsonify({"success": False, "error": "Failed to rebuild chapter"}), 500


@app.route('/api/library/<job_id>/rebuild/full-story', methods=['POST'])
def rebuild_library_full_story(job_id):
    """Rebuild full story output from review chunks."""
    try:
        job_dir = OUTPUT_DIR / job_id
        if not job_dir.exists():
            return jsonify({"success": False, "error": "Item not found"}), 404

        manifest_path = job_dir / "review_manifest.json"
        if not manifest_path.exists():
            return jsonify({"success": False, "error": "Review manifest not found"}), 404

        with manifest_path.open("r", encoding="utf-8") as handle:
            manifest = json.load(handle)

        chunk_files = manifest.get("all_full_story_chunks") or []
        if not chunk_files:
            return jsonify({"success": False, "error": "No full story chunks available"}), 400

        chunk_paths = [str(job_dir / rel_path) for rel_path in chunk_files]
        missing = [p for p in chunk_paths if not Path(p).exists()]
        if missing:
            return jsonify({"success": False, "error": "Missing chunk files for full story"}), 409

        config_snapshot = _load_library_merge_options(job_dir, manifest)
        output_format = config_snapshot.get("output_format") or "mp3"
        full_story_name = f"full_story.{output_format}"
        full_story_path = job_dir / full_story_name
        _remove_existing_output(full_story_path)

        merger = _build_review_merger(config_snapshot)
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
            "format": output_format,
        }
        _update_metadata_full_story(job_id, job_dir, full_story_entry)
        invalidate_library_cache()

        return jsonify({"success": True, "full_story": full_story_entry})
    except Exception as exc:
        logger.error("Failed to rebuild full story for %s: %s", job_id, exc, exc_info=True)
        return jsonify({"success": False, "error": "Failed to rebuild full story"}), 500


@app.route('/api/library/<job_id>/rebuild/selected', methods=['POST'])
def rebuild_library_selected_chapters(job_id):
    """Rebuild selected chapter outputs from review chunks."""
    try:
        payload = request.get_json(silent=True) or {}
        indices = payload.get("chapter_indices") or []
        if not isinstance(indices, list) or not indices:
            return jsonify({"success": False, "error": "chapter_indices is required"}), 400

        job_dir = OUTPUT_DIR / job_id
        if not job_dir.exists():
            return jsonify({"success": False, "error": "Item not found"}), 404

        manifest_path = job_dir / "review_manifest.json"
        if not manifest_path.exists():
            return jsonify({"success": False, "error": "Review manifest not found"}), 404

        with manifest_path.open("r", encoding="utf-8") as handle:
            manifest = json.load(handle)

        chapters = manifest.get("chapters") or []
        index_set = {int(idx) for idx in indices}
        targets = [ch for ch in chapters if ch.get("index") in index_set]
        if not targets:
            return jsonify({"success": False, "error": "No matching chapters found"}), 404

        config_snapshot = _load_library_merge_options(job_dir, manifest)
        output_format = config_snapshot.get("output_format") or "mp3"
        merger = _build_review_merger(config_snapshot)
        rebuilt = []

        # Collect merge tasks for parallel processing
        merge_tasks = []
        for target in targets:
            chunk_files = target.get("chunk_files") or []
            if not chunk_files:
                continue
            chunk_paths = [str(job_dir / rel_path) for rel_path in chunk_files]
            missing = [p for p in chunk_paths if not Path(p).exists()]
            if missing:
                continue

            chapter_index = int(target.get("index") or 0)
            output_path = _resolve_chapter_output_path(job_dir, target, output_format, chapter_index)
            merge_tasks.append({
                "target": target,
                "chapter_index": chapter_index,
                "chunk_paths": chunk_paths,
                "output_path": output_path,
            })
        
        # Execute merges in parallel with dynamic worker allocation
        if merge_tasks:
            def selected_merge_wrapper(task):
                """Wrapper function for parallel merge in selected chapters rebuild"""
                target = task["target"]
                chunk_paths = task["chunk_paths"]
                output_path = task["output_path"]
                
                _remove_existing_output(output_path)
                merger.merge_wav_files(
                    input_files=chunk_paths,
                    output_path=str(output_path),
                    format=output_format,
                    cleanup_chunks=False,
                )
                return task
            
            # Use CPU count for dynamic worker allocation, capped at total tasks
            max_workers = min(os.cpu_count() or 4, len(merge_tasks))
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_task = {executor.submit(selected_merge_wrapper, task): task for task in merge_tasks}
                
                for future in concurrent.futures.as_completed(future_to_task):
                    try:
                        task = future.result()
                        target = task["target"]
                        output_path = task["output_path"]
                        
                        rel_path = (Path(target.get("chapter_dir") or ".") / output_path.name).as_posix()
                        if rel_path.startswith("./"):
                            rel_path = rel_path[2:]
                        chapter_entry = {
                            "index": target.get("index"),
                            "title": target.get("title"),
                            "file_url": f"/static/audio/{job_id}/{rel_path}",
                            "relative_path": rel_path,
                            "format": output_format,
                        }
                        _update_metadata_chapter(job_id, job_dir, chapter_entry)
                        rebuilt.append(chapter_entry)
                    except Exception as e:
                        logger.error(f"Merge task failed for chapter {task['target'].get('index')}: {e}")
                        raise

        invalidate_library_cache()
        return jsonify({"success": True, "chapters": rebuilt})
    except Exception as exc:
        logger.error("Failed to rebuild selected chapters for %s: %s", job_id, exc, exc_info=True)
        return jsonify({"success": False, "error": "Failed to rebuild selected chapters"}), 500


@app.route('/api/library/<job_id>/rebuild/all', methods=['POST'])
def rebuild_library_all(job_id):
    """Rebuild all chapter outputs and full story from review chunks."""
    try:
        job_dir = OUTPUT_DIR / job_id
        if not job_dir.exists():
            return jsonify({"success": False, "error": "Item not found"}), 404

        manifest_path = job_dir / "review_manifest.json"
        if not manifest_path.exists():
            return jsonify({"success": False, "error": "Review manifest not found"}), 404

        with manifest_path.open("r", encoding="utf-8") as handle:
            manifest = json.load(handle)

        chapters = manifest.get("chapters") or []
        all_full_story_chunks = manifest.get("all_full_story_chunks") or []

        config_snapshot = _load_library_merge_options(job_dir, manifest)
        output_format = config_snapshot.get("output_format") or "mp3"
        merger = _build_review_merger(config_snapshot)
        rebuilt_chapters = []

        # Collect chapter merge tasks for parallel processing
        merge_tasks = []
        for target in chapters:
            chunk_files = target.get("chunk_files") or []
            if not chunk_files:
                continue
            chunk_paths = [str(job_dir / rel_path) for rel_path in chunk_files]
            missing = [p for p in chunk_paths if not Path(p).exists()]
            if missing:
                continue

            chapter_index = int(target.get("index") or 0)
            output_path = _resolve_chapter_output_path(job_dir, target, output_format, chapter_index)
            merge_tasks.append({
                "target": target,
                "chapter_index": chapter_index,
                "chunk_paths": chunk_paths,
                "output_path": output_path,
            })
        
        # Execute chapter merges in parallel with dynamic worker allocation
        if merge_tasks:
            def all_merge_wrapper(task):
                """Wrapper function for parallel merge in rebuild all operation"""
                target = task["target"]
                chunk_paths = task["chunk_paths"]
                output_path = task["output_path"]
                
                _remove_existing_output(output_path)
                merger.merge_wav_files(
                    input_files=chunk_paths,
                    output_path=str(output_path),
                    format=output_format,
                    cleanup_chunks=False,
                )
                return task
            
            # Use CPU count for dynamic worker allocation, capped at total tasks
            max_workers = min(os.cpu_count() or 4, len(merge_tasks))
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_task = {executor.submit(all_merge_wrapper, task): task for task in merge_tasks}
                
                for future in concurrent.futures.as_completed(future_to_task):
                    try:
                        task = future.result()
                        target = task["target"]
                        output_path = task["output_path"]
                        
                        rel_path = (Path(target.get("chapter_dir") or ".") / output_path.name).as_posix()
                        if rel_path.startswith("./"):
                            rel_path = rel_path[2:]
                        chapter_entry = {
                            "index": target.get("index"),
                            "title": target.get("title"),
                            "file_url": f"/static/audio/{job_id}/{rel_path}",
                            "relative_path": rel_path,
                            "format": output_format,
                        }
                        _update_metadata_chapter(job_id, job_dir, chapter_entry)
                        rebuilt_chapters.append(chapter_entry)
                    except Exception as e:
                        logger.error(f"Merge task failed for chapter {task['target'].get('index')}: {e}")
                        raise

        full_story_entry = None
        if all_full_story_chunks:
            chunk_paths = [str(job_dir / rel_path) for rel_path in all_full_story_chunks]
            missing = [p for p in chunk_paths if not Path(p).exists()]
            if not missing:
                full_story_name = f"full_story.{output_format}"
                full_story_path = job_dir / full_story_name
                _remove_existing_output(full_story_path)
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
                    "format": output_format,
                }
                _update_metadata_full_story(job_id, job_dir, full_story_entry)

        invalidate_library_cache()
        return jsonify({
            "success": True,
            "chapters": rebuilt_chapters,
            "full_story": full_story_entry,
        })
    except Exception as exc:
        logger.error("Failed to rebuild all outputs for %s: %s", job_id, exc, exc_info=True)
        return jsonify({"success": False, "error": "Failed to rebuild outputs"}), 500


@app.route('/api/library/<job_id>/word-replacements', methods=['GET', 'PUT'])
def library_job_word_replacements(job_id):
    """Get or update the word replacement registry for a library job."""
    job_dir = OUTPUT_DIR / job_id
    if not job_dir.is_dir():
        return jsonify({"success": False, "error": "Job not found"}), 404
    metadata_path = job_dir / "metadata.json"

    if request.method == 'GET':
        replacements = (jobs.get(job_id) or {}).get("word_replacements") or []
        if not replacements and metadata_path.exists():
            try:
                with metadata_path.open("r", encoding="utf-8") as f:
                    replacements = json.load(f).get("word_replacements") or []
            except Exception:
                pass
        return jsonify({"success": True, "word_replacements": replacements})

    # PUT — update
    data = request.get_json(silent=True) or {}
    raw = data.get("word_replacements")
    if not isinstance(raw, list):
        return jsonify({"success": False, "error": "word_replacements must be a list"}), 400
    replacements = [
        r for r in raw
        if isinstance(r, dict) and r.get("original") and r.get("replacement")
    ]
    # Update in-memory job entry (outside queue_lock to avoid SQLite deadlock)
    job_in_memory = False
    with queue_lock:
        if job_id in jobs:
            jobs[job_id]["word_replacements"] = replacements
            job_in_memory = True
    if job_in_memory:
        _persist_job_state(job_id, force=True)
    # Persist to metadata.json so it survives server restarts, even for older
    # library items that were created before metadata.json was always written.
    try:
        meta = {}
        if metadata_path.exists():
            with metadata_path.open("r", encoding="utf-8") as f:
                meta = json.load(f)
        meta["job_id"] = meta.get("job_id") or job_id
        meta["word_replacements"] = replacements
        with metadata_path.open("w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)
    except Exception as exc:
        logger.warning("Failed to persist word_replacements to metadata for %s: %s", job_id, exc)
    invalidate_library_cache()
    return jsonify({"success": True, "word_replacements": replacements})


@app.route('/api/library/<job_id>/chapter/<int:chapter_index>/rename', methods=['POST'])
def rename_library_chapter(job_id: str, chapter_index: int):
    """Rename a chapter title in the library metadata."""
    try:
        payload = request.get_json(silent=True) or {}
        new_title = (payload.get("title") or "").strip()
        if not new_title:
            return jsonify({"success": False, "error": "Title cannot be empty"}), 400

        job_dir = OUTPUT_DIR / job_id
        if not job_dir.exists():
            return jsonify({"success": False, "error": "Item not found"}), 404

        metadata = load_job_metadata(job_dir) or {}
        chapters = metadata.get("chapters", [])

        if chapter_index < 0 or chapter_index >= len(chapters):
            return jsonify({"success": False, "error": f"Chapter index {chapter_index} out of range"}), 404

        # Store custom title in metadata (preserves original title if needed)
        if "custom_chapter_titles" not in metadata:
            metadata["custom_chapter_titles"] = {}
        metadata["custom_chapter_titles"][str(chapter_index)] = new_title

        # Also update the chapter title in the chapters array for display
        chapters[chapter_index]["title"] = new_title
        metadata["chapters"] = chapters

        save_job_metadata(job_dir, metadata)
        invalidate_library_cache()

        return jsonify({"success": True, "title": new_title})
    except Exception as exc:
        logger.error("Failed to rename chapter %s for %s: %s", chapter_index, job_id, exc, exc_info=True)
        return jsonify({"success": False, "error": "Failed to rename chapter"}), 500


@app.route('/api/library/<job_id>/metadata', methods=['POST'])
def update_library_metadata(job_id: str):
    """Update audiobook metadata for a library item."""
    try:
        payload = request.get_json(silent=True) or {}
        job_dir = OUTPUT_DIR / job_id
        if not job_dir.exists():
            return jsonify({"success": False, "error": "Item not found"}), 404

        metadata = load_job_metadata(job_dir) or {}

        # Update audiobook metadata fields
        if "title" in payload:
            metadata["audiobook_title"] = payload["title"].strip()
        if "author" in payload:
            metadata["audiobook_author"] = payload["author"].strip()
        if "genre" in payload:
            metadata["audiobook_genre"] = payload["genre"].strip()
        if "year" in payload:
            metadata["audiobook_year"] = payload["year"].strip()
        if "description" in payload:
            metadata["audiobook_description"] = payload["description"].strip()

        # Handle cover art upload
        if "cover_art" in payload and payload["cover_art"]:
            # In a real implementation, this would handle file upload
            # For now, store the base64 or path
            metadata["audiobook_cover_art"] = payload["cover_art"]

        save_job_metadata(job_dir, metadata)
        invalidate_library_cache()

        return jsonify({"success": True})
    except Exception as exc:
        logger.error("Failed to update metadata for %s: %s", job_id, exc, exc_info=True)
        return jsonify({"success": False, "error": "Failed to update metadata"}), 500


@app.route('/api/library/<job_id>/repair', methods=['POST'])
def repair_library_job(job_id):
    """Rebuild missing review manifest/metadata from existing chunk files."""
    try:
        payload = request.get_json(silent=True) or {}
        force_rebuild = bool(payload.get("force_rebuild"))
        job_dir = OUTPUT_DIR / job_id
        if not job_dir.exists():
            return jsonify({"success": False, "error": "Item not found"}), 404

        result = _rebuild_review_manifest_from_chunks(job_id, job_dir, force_rebuild=force_rebuild)
        invalidate_library_cache()
        return jsonify({
            "success": True,
            "chapters": result.get("chapters"),
            "full_story": result.get("full_story"),
        })
    except FileNotFoundError as exc:
        return jsonify({"success": False, "error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception as exc:
        logger.error("Failed to repair library job %s: %s", job_id, exc, exc_info=True)
        return jsonify({"success": False, "error": "Failed to repair library item"}), 500


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
        
        # Delete both persisted job-side data and Library audio. The helper
        # retries transient Windows locks and verifies each path is truly gone.
        remove_directory_with_retries(JOBS_DATA_DIR / job_id)
        remove_directory_with_retries(job_dir)

        with queue_lock:
            jobs.pop(job_id, None)
            cancel_flags.pop(job_id, None)
            pause_flags.pop(job_id, None)
            cancel_events.pop(job_id, None)
        with _get_jobs_db_connection() as conn:
            conn.execute("DELETE FROM jobs WHERE job_id=?", (job_id,))
            conn.commit()
        invalidate_library_cache()
        
        return jsonify({
            "success": True
        })
        
    except PermissionError as e:
        logger.warning("Library item %s could not be completely deleted: %s", job_id, e)
        invalidate_library_cache()
        return jsonify({
            "success": False,
            "error": str(e),
            "retryable": True,
        }), 409
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
            cancel_events.setdefault(job_id, threading.Event()).set()
            
            # Update job status
            jobs[job_id]["status"] = "cancelled"
            jobs[job_id]["progress"] = 0
            jobs[job_id]["cancelled_at"] = datetime.now().isoformat()
        _persist_job_state(job_id, force=True)
        
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
                    if job_info.get("job_type") in {
                        "qwen3_voice_design_preview",
                        "qwen3_voice_design_save",
                        "breeze_voice_design_preview",
                        "breeze_voice_design_save",
                        "omnivoice_design_preview",
                        "omnivoice_design_save",
                    }:
                        continue
                    all_jobs.append({
                        "job_id": job_id,
                        "status": job_info.get("status", "unknown"),
                        "progress": job_info.get("progress", 0),
                        "created_at": (
                            job_info.get("created_at")
                            or job_info.get("updated_at")
                            or ""
                        ),
                        "text_preview": job_info.get("text_preview", ""),
                        "output_file": job_info.get("output_file", ""),
                        "error": job_info.get("error", ""),
                        "total_chunks": job_info.get("total_chunks"),
                        "processed_chunks": job_info.get("processed_chunks", 0),
                        "eta_seconds": job_info.get("eta_seconds"),
                        "breeze_voice_status": job_info.get("breeze_voice_status", ""),
                        "engine": job_info.get("engine"),
                        "chapter_mode": job_info.get("chapter_mode", False),
                        "chapter_count": job_info.get("chapter_count"),
                        "book_mode": job_info.get("book_mode", False),
                        "book_count": job_info.get("book_count"),
                        "resume_from_chunk_index": job_info.get("resume_from_chunk_index"),
                        "last_completed_chunk_index": job_info.get("last_completed_chunk_index"),
                        "interrupted_at": job_info.get("interrupted_at"),
                        "full_story_requested": job_info.get("full_story_requested", False),
                        "review_mode": job_info.get("review_mode", False),
                        "review_has_active_regen": job_info.get("review_mode", False) and _has_active_regen_tasks(job_info),
                        "post_process_total": job_info.get("post_process_total", 0),
                        "post_process_done": job_info.get("post_process_done", 0),
                        "post_process_active": job_info.get("post_process_active", False),
                        "post_process_percent": job_info.get("post_process_percent", 0),
                    })
                
                all_jobs.sort(key=lambda x: x.get("created_at") or "", reverse=True)
            
            return jsonify({
                "success": True,
                "jobs": all_jobs,
                "current_job": current_job_id,
                "current_jobs": sorted(current_job_ids),
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


def _load_saved_projects() -> List[Dict[str, Any]]:
    if not PROJECTS_FILE.exists():
        return []
    try:
        payload = json.loads(PROJECTS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.error("Unable to read saved projects from %s: %s", PROJECTS_FILE, exc)
        return []
    if not isinstance(payload, list):
        logger.error("Saved project file is not a JSON list: %s", PROJECTS_FILE)
        return []
    return [project for project in payload if isinstance(project, dict)]


def _project_timestamp(project: Dict[str, Any]) -> float:
    value = str(project.get("saved_at") or "").strip()
    if not value:
        return 0.0
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return 0.0


def _normalize_saved_project(project: Dict[str, Any]) -> Dict[str, Any]:
    normalized = copy.deepcopy(project)
    project_id = str(normalized.get("id") or uuid.uuid4()).strip()
    normalized["id"] = project_id or str(uuid.uuid4())
    normalized["name"] = str(normalized.get("name") or "Untitled Project").strip() or "Untitled Project"
    normalized["saved_at"] = str(normalized.get("saved_at") or datetime.utcnow().isoformat())
    return normalized


def _merge_imported_projects(
    existing: List[Dict[str, Any]], incoming: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    merged = [_normalize_saved_project(project) for project in existing]
    for raw_project in incoming:
        if not isinstance(raw_project, dict):
            continue
        project = _normalize_saved_project(raw_project)
        project_id = project["id"]
        project_name = project["name"].casefold()
        match_index = next(
            (
                index
                for index, saved in enumerate(merged)
                if str(saved.get("id")) == project_id
                or str(saved.get("name") or "").strip().casefold() == project_name
            ),
            None,
        )
        if match_index is None:
            merged.append(project)
        elif _project_timestamp(project) >= _project_timestamp(merged[match_index]):
            # Keep the established ID when matching a legacy copy by name.
            project["id"] = str(merged[match_index].get("id") or project_id)
            merged[match_index] = project
    return merged


@app.route('/api/projects', methods=['GET'])
def list_saved_projects():
    """Return the shared, backend-managed project library."""
    with PROJECTS_LOCK:
        projects = _load_saved_projects()
    projects.sort(key=_project_timestamp, reverse=True)
    return jsonify({"success": True, "projects": projects})


@app.route('/api/projects', methods=['POST'])
def save_saved_project():
    payload = request.get_json(silent=True) or {}
    raw_project = payload.get("project") if isinstance(payload, dict) else None
    if not isinstance(raw_project, dict):
        return jsonify({"success": False, "error": "A project object is required."}), 400
    project = _normalize_saved_project(raw_project)
    with PROJECTS_LOCK:
        projects = _load_saved_projects()
        match_index = next(
            (index for index, saved in enumerate(projects) if str(saved.get("id")) == project["id"]),
            None,
        )
        if match_index is None:
            projects.append(project)
        else:
            projects[match_index] = project
        write_json_atomic(PROJECTS_FILE, projects, ensure_ascii=False)
    return jsonify({"success": True, "project": project})


@app.route('/api/projects/import', methods=['POST'])
def import_saved_projects():
    """Merge projects formerly isolated in an individual browser origin."""
    payload = request.get_json(silent=True) or {}
    incoming = payload.get("projects") if isinstance(payload, dict) else None
    if not isinstance(incoming, list):
        return jsonify({"success": False, "error": "A project list is required."}), 400
    with PROJECTS_LOCK:
        projects = _merge_imported_projects(_load_saved_projects(), incoming)
        write_json_atomic(PROJECTS_FILE, projects, ensure_ascii=False)
    projects.sort(key=_project_timestamp, reverse=True)
    return jsonify({"success": True, "projects": projects, "imported": len(incoming)})


@app.route('/api/projects/<project_id>', methods=['DELETE'])
def delete_saved_project(project_id: str):
    with PROJECTS_LOCK:
        projects = _load_saved_projects()
        remaining = [project for project in projects if str(project.get("id")) != str(project_id)]
        if len(remaining) == len(projects):
            return jsonify({"success": False, "error": "Project not found."}), 404
        write_json_atomic(PROJECTS_FILE, remaining, ensure_ascii=False)
    return jsonify({"success": True})


def _load_engine_first_run_notice_state() -> set[str]:
    try:
        with ENGINE_FIRST_RUN_NOTICE_FILE.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        seen = payload.get("seen") if isinstance(payload, dict) else []
        return {str(engine).strip().lower() for engine in (seen or []) if str(engine).strip()}
    except (OSError, ValueError, TypeError):
        return set()


def _consume_engine_first_run_notice(engine_name: str) -> bool:
    """Return True once per engine installation/first use, then persist it."""
    normalized = _normalize_engine_name(engine_name)
    if not normalized:
        return False
    with ENGINE_FIRST_RUN_NOTICE_LOCK:
        seen = _load_engine_first_run_notice_state()
        if normalized in seen:
            return False
        seen.add(normalized)
        ENGINE_FIRST_RUN_NOTICE_FILE.parent.mkdir(parents=True, exist_ok=True)
        write_json_atomic(
            ENGINE_FIRST_RUN_NOTICE_FILE,
            {"seen": sorted(seen)},
            ensure_ascii=False,
        )
    return True


def _reset_engine_first_run_notice(install_target: str) -> None:
    """Make the notice eligible again after a local engine is reinstalled."""
    generation_ids = ENGINE_INSTALL_GENERATION_IDS.get(install_target, {install_target})
    with ENGINE_FIRST_RUN_NOTICE_LOCK:
        seen = _load_engine_first_run_notice_state()
        updated = seen.difference(generation_ids)
        if updated == seen:
            return
        ENGINE_FIRST_RUN_NOTICE_FILE.parent.mkdir(parents=True, exist_ok=True)
        write_json_atomic(
            ENGINE_FIRST_RUN_NOTICE_FILE,
            {"seen": sorted(updated)},
            ensure_ascii=False,
        )


def _engine_setup_catalog(config: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Describe install/configuration state without loading model weights."""
    config = config or load_config()
    replicate_ready = bool((config.get("replicate_api_key") or "").strip())
    chatterbox_cloud_ready = bool(
        (config.get("chatterbox_turbo_replicate_api_token") or "").strip()
        or replicate_ready
    )
    openai_ready = bool(
        (config.get("openai_tts_api_key") or "").strip()
        or "api.openai.com" not in (
            config.get("openai_tts_base_url") or DEFAULT_OPENAI_TTS_BASE_URL
        ).lower()
    )
    definitions = [
        ("kokoro", "Kokoro", "local", isolated_engine_available("kokoro"), "kokoro"),
        ("kokoro_replicate", "Kokoro · Replicate", "cloud", replicate_ready, "kokoro-replicate"),
        ("chatterbox_turbo_local", "Chatterbox Local", "local", CHATTERBOX_TURBO_AVAILABLE, "chatterbox-local"),
        ("chatterbox_turbo_replicate", "Chatterbox Cloud", "cloud", chatterbox_cloud_ready, "chatterbox-replicate"),
        ("voxcpm_local", "VoxCPM 1.5", "local", isolated_engine_available("voxcpm_local"), "voxcpm"),
        ("pocket_tts", "Pocket TTS · Clone", "local", isolated_engine_available("pocket_tts"), "pocket-tts"),
        ("pocket_tts_preset", "Pocket TTS · Presets", "local", isolated_engine_available("pocket_tts_preset"), "pocket-tts"),
        ("qwen3_custom", "Qwen3-TTS · Custom Voice", "local", isolated_engine_available("qwen3_custom"), "qwen3"),
        ("qwen3_clone", "Qwen3-TTS · Voice Clone", "local", isolated_engine_available("qwen3_clone"), "qwen3"),
        ("omnivoice_clone", "OmniVoice · Voice Clone", "local", omnivoice_available(), "omnivoice"),
        ("kitten_tts", "KittenTTS", "local", isolated_engine_available("kitten_tts"), "kitten-tts"),
        ("index_tts", "IndexTTS", "local", INDEX_TTS_AVAILABLE, "index-tts"),
        ("dots_tts", "Dot.TTS", "local", DOTS_TTS_AVAILABLE, "dots-tts"),
        ("audio8_tts", "Audio8 TTS · Voice Clone", "local", isolated_engine_available("audio8_tts"), "audio8-tts"),
        ("breeze_tts_2", "Breeze TTS 2 · Design / Clone / Direction", "local", (
            _breeze_runtime_ready(config)
            and (Path(__file__).resolve().parent / "engines" / "breeze_tts_2" / ".license_accepted").is_file()
        ), "breeze-tts-2"),
        ("azure_speech", "Microsoft Azure Speech", "cloud", bool(
            (config.get("azure_speech_key") or "").strip()
            and (config.get("azure_speech_region") or "").strip()
        ), "azure-speech"),
        ("edge_tts", "Microsoft Edge TTS", "local_client", isolated_engine_available("edge_tts"), "edge-tts"),
        ("elevenlabs", "ElevenLabs", "cloud", bool(
            (config.get("elevenlabs_api_key") or "").strip()
        ), "elevenlabs"),
        ("openai_tts", "OpenAI-compatible TTS", "cloud", openai_ready, "openai-tts"),
        ("breeze_api", "Breeze API · Hosted", "cloud", bool(
            (config.get("breeze_api_key") or "").strip() and (config.get("breeze_api_model") or "").strip()
        ), "breeze-api"),
        ("localai_tts", "LocalAI TTS", "service", bool(
            (config.get("localai_tts_model") or "").strip()
        ), "localai-tts"),
    ]
    install_targets = {
        "kokoro": "kokoro",
        "chatterbox_turbo_local": "chatterbox_turbo_local",
        "voxcpm_local": "voxcpm_local",
        "pocket_tts": "pocket_tts",
        "pocket_tts_preset": "pocket_tts",
        "qwen3_custom": "qwen3",
        "qwen3_clone": "qwen3",
        "omnivoice_clone": "omnivoice",
        "kitten_tts": "kitten_tts",
        "index_tts": "index_tts",
        "dots_tts": "dots_tts",
        "audio8_tts": "audio8_tts",
        "breeze_tts_2": "breeze_tts_2",
        "edge_tts": "edge_tts",
    }
    return [{
        "id": engine_id,
        "name": name,
        "kind": kind,
        "ready": bool(ready),
        "settings_tab": settings_tab,
        "install_target": install_targets.get(engine_id),
        "uninstall_target": install_targets.get(engine_id) if ready else None,
        "license_accepted": (
            (Path(__file__).resolve().parent / "engines" / "breeze_tts_2" / ".license_accepted").is_file()
            if engine_id == "breeze_tts_2" else None
        ),
        "q8_ready": (Path(__file__).resolve().parent / "engines/breeze_tts_2/.q8_ready").is_file() if engine_id == "breeze_tts_2" else None,
        "uninstall_warning": (
            f"This will remove {name}'s runtime package and downloaded model files. "
            "Shared TTS dependencies, projects, generated audio, and saved voice samples will be kept. "
            "Reinstalling this engine later will require downloading its runtime and models again."
        ) if engine_id in install_targets else None,
        "action": (
            "ready" if ready else ("install" if engine_id in install_targets else "configure")
        ),
    } for engine_id, name, kind, ready, settings_tab in definitions]


def _run_engine_install_job(job_id: str, engine: str) -> None:
    job = ENGINE_INSTALL_JOBS[job_id]
    log_path = Path(job["log_path"])
    command = [sys.executable, str(Path(__file__).resolve().parent / "scripts" / "install_engine.py"), engine]
    if engine == "breeze_tts_2":
        command.extend(["--breeze-runtime", job.get("runtime", "pytorch")])
    try:
        with log_path.open("w", encoding="utf-8", errors="replace") as log_handle:
            process = subprocess.Popen(
                command,
                cwd=str(Path(__file__).resolve().parent),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
            job["pid"] = process.pid
            for line in process.stdout or []:
                log_handle.write(line)
                log_handle.flush()
                job["output"] = (job.get("output", "") + line)[-20000:]
            return_code = process.wait()
        job["status"] = "complete" if return_code == 0 else "failed"
        job["return_code"] = return_code
        job["restart_required"] = return_code == 0
        job["finished_at"] = datetime.now().isoformat()
        if return_code == 0:
            _reset_engine_first_run_notice(engine)
    except Exception as exc:
        logger.exception("Optional engine installation failed: %s", engine)
        job["status"] = "failed"
        job["error"] = str(exc)
        job["finished_at"] = datetime.now().isoformat()


def _run_engine_uninstall_job(job_id: str, engine: str) -> None:
    job = ENGINE_INSTALL_JOBS[job_id]
    log_path = Path(job["log_path"])
    command = [
        sys.executable,
        str(Path(__file__).resolve().parent / "scripts" / "install_engine.py"),
        "--uninstall",
        engine,
    ]
    try:
        with log_path.open("w", encoding="utf-8", errors="replace") as log_handle:
            process = subprocess.Popen(
                command,
                cwd=str(Path(__file__).resolve().parent),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
            job["pid"] = process.pid
            for line in process.stdout or []:
                log_handle.write(line)
                log_handle.flush()
                job["output"] = (job.get("output", "") + line)[-20000:]
            return_code = process.wait()
        job["status"] = "complete" if return_code == 0 else "failed"
        job["return_code"] = return_code
        job["restart_required"] = return_code == 0
        job["finished_at"] = datetime.now().isoformat()
    except Exception as exc:
        logger.exception("Optional engine removal failed: %s", engine)
        job["status"] = "failed"
        job["error"] = str(exc)
        job["finished_at"] = datetime.now().isoformat()


@app.route('/api/onboarding', methods=['GET', 'POST'])
def onboarding_state():
    if request.method == 'POST':
        try:
            FIRST_RUN_MARKER.unlink(missing_ok=True)
        except OSError as exc:
            return jsonify({"success": False, "error": str(exc)}), 500
    return jsonify({"success": True, "show_welcome": FIRST_RUN_MARKER.is_file()})


@app.route('/api/engines/status', methods=['GET'])
def engine_setup_status():
    return jsonify({"success": True, "engines": _engine_setup_catalog()})


@app.route('/api/system/status', methods=['GET'])
def system_status():
    return jsonify({"success": True, "instance_id": SERVER_INSTANCE_ID})


def _exit_for_supervised_restart() -> None:
    """Exit with the code understood by run.bat/run.sh after responding."""
    try:
        global qwen3_voice_design_process
        if qwen3_voice_design_process and qwen3_voice_design_process.poll() is None:
            qwen3_voice_design_process.terminate()
    except Exception:
        logger.warning("Unable to stop the Qwen voice-design worker before restart", exc_info=True)
    try:
        global breeze_voice_design_process
        if breeze_voice_design_process and breeze_voice_design_process.poll() is None:
            breeze_voice_design_process.terminate()
    except Exception:
        logger.warning("Unable to stop the Breeze voice-design worker before restart", exc_info=True)
    try:
        sys.stdout.flush()
        sys.stderr.flush()
    finally:
        os._exit(SERVER_RESTART_EXIT_CODE)


def _is_local_management_request() -> bool:
    """Return true only for a direct loopback request."""
    return request.remote_addr in {"127.0.0.1", "::1", None}


def _engine_management_request_allowed(config: Optional[Dict[str, Any]] = None) -> bool:
    """Authorize destructive engine management locally or with the saved remote token."""
    if _is_local_management_request():
        return True
    config = config or load_config()
    if not bool(config.get("remote_engine_management_enabled", False)):
        return False
    expected = str(config.get("remote_engine_management_token") or "").strip()
    supplied = str(request.headers.get("X-TTS-Story-Admin-Token") or "").strip()
    return bool(expected and supplied and hmac.compare_digest(expected, supplied))


def _engine_management_denied(action: str):
    return jsonify({
        "success": False,
        "error": (
            f"{action} is allowed locally, or remotely after Remote Engine Management "
            "is enabled and its administrator token is supplied."
        ),
    }), 403


@app.route('/api/system/restart', methods=['POST'])
def restart_system():
    if not _engine_management_request_allowed():
        return _engine_management_denied("Backend restart")
    if os.environ.get("TTS_STORY_RESTARTABLE") != "1":
        return jsonify({
            "success": False,
            "error": "Automatic restart is available when TTS-Story is launched with run.bat or run.sh.",
        }), 409
    active_engine_job = next((
        job for job in ENGINE_INSTALL_JOBS.values() if job.get("status") == "running"
    ), None)
    if active_engine_job or current_job_ids or current_job_id:
        return jsonify({
            "success": False,
            "error": "Wait for active audio and engine-management jobs to finish before restarting.",
        }), 409
    logger.info("Backend restart requested from Settings")
    threading.Timer(0.5, _exit_for_supervised_restart).start()
    return jsonify({
        "success": True,
        "message": "TTS-Story is restarting.",
        "instance_id": SERVER_INSTANCE_ID,
    }), 202


@app.route('/api/engines/install', methods=['POST'])
def install_optional_engine():
    if not _engine_management_request_allowed():
        return _engine_management_denied("Engine installation")
    payload = request.get_json(silent=True) or {}
    engine = str(payload.get("engine") or "").strip().lower()
    breeze_runtime = payload.get("runtime", "pytorch")
    if engine == "breeze_tts_2" and breeze_runtime not in ("pytorch", "q8"):
        return jsonify({"success": False, "error": "Unknown Breeze runtime."}), 400
    allowed = {
        entry["install_target"] for entry in _engine_setup_catalog() if entry.get("install_target")
    }
    if engine not in allowed:
        return jsonify({"success": False, "error": "Unknown optional engine installer."}), 400
    if engine == "breeze_tts_2":
        if payload.get("license_accepted") is not True:
            return jsonify({
                "success": False,
                "error": "Accept the BreezeBlue Research and Non-Commercial License before installing."
            }), 400
        marker = Path(__file__).resolve().parent / "engines" / "breeze_tts_2" / ".license_accepted"
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(
            f"Accepted through TTS-Story Settings at {datetime.now().isoformat()}.\n",
            encoding="utf-8",
        )
    with ENGINE_INSTALL_LOCK:
        active = next((
            existing for existing in ENGINE_INSTALL_JOBS.values()
            if existing.get("status") == "running"
        ), None)
        if active:
            return jsonify({
                "success": False,
                "error": f"{active.get('engine')} is already being installed.",
                "job_id": active.get("id"),
            }), 409
        job_id = str(uuid.uuid4())
        job = {
            "id": job_id,
            "engine": engine,
            "action": "install",
            "runtime": breeze_runtime if engine == "breeze_tts_2" else None,
            "status": "running",
            "output": "",
            "started_at": datetime.now().isoformat(),
            "log_path": str(ENGINE_INSTALL_LOG_DIR / f"{job_id}.log"),
        }
        ENGINE_INSTALL_JOBS[job_id] = job
        threading.Thread(
            target=_run_engine_install_job,
            args=(job_id, engine),
            name=f"engine-install-{engine}",
            daemon=True,
        ).start()
    return jsonify({"success": True, "job_id": job_id, "engine": engine}), 202


@app.route('/api/engines/uninstall', methods=['POST'])
def uninstall_optional_engine():
    if not _engine_management_request_allowed():
        return _engine_management_denied("Engine removal")
    if current_job_ids or current_job_id:
        return jsonify({
            "success": False,
            "error": "Wait for current TTS jobs to finish or cancel them before removing an engine.",
        }), 409
    payload = request.get_json(silent=True) or {}
    engine = str(payload.get("engine") or "").strip().lower()
    allowed = {
        entry["uninstall_target"]
        for entry in _engine_setup_catalog()
        if entry.get("uninstall_target")
    }
    if engine not in allowed:
        return jsonify({"success": False, "error": "Unknown or unavailable local engine."}), 400
    with ENGINE_INSTALL_LOCK:
        active = next((
            existing for existing in ENGINE_INSTALL_JOBS.values()
            if existing.get("status") == "running"
        ), None)
        if active:
            return jsonify({
                "success": False,
                "error": f"{active.get('engine')} is already being managed.",
                "job_id": active.get("id"),
            }), 409
        job_id = str(uuid.uuid4())
        job = {
            "id": job_id,
            "engine": engine,
            "action": "uninstall",
            "status": "running",
            "output": "",
            "started_at": datetime.now().isoformat(),
            "log_path": str(ENGINE_INSTALL_LOG_DIR / f"{job_id}.log"),
        }
        ENGINE_INSTALL_JOBS[job_id] = job
        threading.Thread(
            target=_run_engine_uninstall_job,
            args=(job_id, engine),
            name=f"engine-uninstall-{engine}",
            daemon=True,
        ).start()
    return jsonify({"success": True, "job_id": job_id, "engine": engine}), 202


@app.route('/api/engines/install/<job_id>', methods=['GET'])
@app.route('/api/engines/jobs/<job_id>', methods=['GET'])
def optional_engine_install_status(job_id: str):
    job = ENGINE_INSTALL_JOBS.get(job_id)
    if not job:
        return jsonify({"success": False, "error": "Engine management job not found."}), 404
    return jsonify({"success": True, "job": {
        key: value for key, value in job.items() if key != "log_path"
    }})


@app.route('/api/engines/jobs', methods=['GET'])
def optional_engine_install_jobs():
    """Return discoverable engine-management jobs for page refresh recovery."""
    with ENGINE_INSTALL_LOCK:
        jobs = [
            {key: value for key, value in job.items() if key != "log_path"}
            for job in ENGINE_INSTALL_JOBS.values()
        ]
    jobs.sort(key=lambda job: str(job.get("started_at") or ""), reverse=True)
    return jsonify({"success": True, "jobs": jobs[:20]})


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
        "kokoro_available": isolated_engine_available("kokoro"),
        "chatterbox_turbo_available": CHATTERBOX_TURBO_AVAILABLE,
        "chatterbox_turbo_unavailable_reason": (
            CHATTERBOX_TURBO_UNAVAILABLE_REASON if not CHATTERBOX_TURBO_AVAILABLE else ""
        ),
        "qwen3_available": isolated_engine_available("qwen3_custom"),
        "qwen3_voice_design_available": isolated_engine_available("qwen3_custom"),
        "qwen3_voice_design_api_version": 2,
        "breeze_voice_design_available": (
            _breeze_runtime_ready(config)
            and (Path(__file__).resolve().parent / "engines" / "breeze_tts_2" / ".license_accepted").is_file()
        ),
        "breeze_voice_design_api_version": 1,
        "omnivoice_available": omnivoice_available(),
        "pocket_tts_available": isolated_engine_available("pocket_tts"),
        "kitten_tts_available": isolated_engine_available("kitten_tts"),
        "index_tts_available": INDEX_TTS_AVAILABLE,
        "index_tts_unavailable_reason": INDEX_TTS_UNAVAILABLE_REASON if not INDEX_TTS_AVAILABLE else "",
        "dots_tts_available": DOTS_TTS_AVAILABLE,
        "dots_tts_unavailable_reason": DOTS_TTS_UNAVAILABLE_REASON if not DOTS_TTS_AVAILABLE else "",
        "audio8_tts_available": isolated_engine_available("audio8_tts"),
        "breeze_tts_2_available": _breeze_runtime_ready(config),
        "breeze_tts_2_license_accepted": (
            Path(__file__).resolve().parent / "engines" / "breeze_tts_2" / ".license_accepted"
        ).is_file(),
        "azure_speech_available": True,
        "azure_speech_configured": bool(
            (config.get("azure_speech_key") or "").strip()
            and (config.get("azure_speech_region") or "").strip()
        ),
        "edge_tts_available": isolated_engine_available("edge_tts"),
        "edge_tts_unavailable_reason": (
            EDGE_TTS_UNAVAILABLE_REASON if not isolated_engine_available("edge_tts") else ""
        ),
        "elevenlabs_available": True,
        "elevenlabs_configured": bool((config.get("elevenlabs_api_key") or "").strip()),
        "openai_tts_available": True,
        "openai_tts_configured": bool(
            (config.get("openai_tts_api_key") or "").strip()
            or "api.openai.com" not in (config.get("openai_tts_base_url") or DEFAULT_OPENAI_TTS_BASE_URL).lower()
        ),
        "localai_tts_available": True,
        "localai_tts_configured": bool((config.get("localai_tts_model") or "").strip()),
        "cuda_available": bool(shutil.which("nvidia-smi")),
        "vram": vram_info,
        "loaded_engines": list(tts_engine_instances.keys()),
    })


@app.route('/api/qwen3/metadata', methods=['GET'])
def qwen3_metadata():
    """Return supported speakers and languages for Qwen3 CustomVoice.
    
    Returns static metadata without loading the model to avoid consuming GPU memory at startup.
    """
    if not isolated_engine_available("qwen3_custom"):
        return jsonify({
            "success": False,
            "error": "Qwen3-TTS VoiceDesign is not installed. Install Qwen3-TTS from Settings → Engine Settings."
        }), 400
    # Return static metadata - these are the actual Qwen3-TTS-CustomVoice supported speakers/languages
    # Avoids loading the full model (~3-4GB GPU) just to get this list
    return jsonify({
        "success": True,
        "speakers": [
            "aiden", "dylan", "eric", "ono_anna", "ryan", "serena", "sohee", "uncle_fu", "vivian"
        ],
        "languages": [
            "auto", "english", "chinese", "japanese", "korean", "french", "german",
            "spanish", "italian", "portuguese", "russian"
        ],
    })


@app.route('/api/qwen3/voice-design/preview', methods=['POST'])
def qwen3_voice_design_preview():
    if not isolated_engine_available("qwen3_custom"):
        return jsonify({
            "success": False,
            "error": "Qwen3-TTS VoiceDesign is not installed. Install Qwen3-TTS from Settings → Engine Settings."
        }), 400
    payload = request.get_json(silent=True) or {}
    text = (payload.get("text") or "").strip()

    if not text:
        return jsonify({"success": False, "error": "Text is required to generate a preview."}), 400
    job_id = _enqueue_qwen3_voice_design_task("qwen3_voice_design_preview", payload)
    return jsonify({"success": True, "job_id": job_id}), 202


@app.route('/api/qwen3/voice-design/save', methods=['POST'])
def qwen3_voice_design_save():
    if not isolated_engine_available("qwen3_custom"):
        return jsonify({
            "success": False,
            "error": "Qwen3-TTS VoiceDesign is not installed. Install Qwen3-TTS from Settings → Engine Settings."
        }), 400
    payload = request.get_json(silent=True) or {}
    name = (payload.get("name") or "").strip()
    text = (payload.get("text") or "").strip()
    audio_base64 = payload.get("audio_base64")

    if not name:
        return jsonify({"success": False, "error": "Voice name is required."}), 400
    if not text:
        return jsonify({"success": False, "error": "Sample text is required."}), 400
    if not audio_base64:
        return jsonify({"success": False, "error": "Preview audio is required."}), 400

    try:
        base64.b64decode(audio_base64)
    except Exception:
        return jsonify({"success": False, "error": "Invalid audio payload."}), 400

    job_id = _enqueue_qwen3_voice_design_task("qwen3_voice_design_save", payload)
    return jsonify({"success": True, "job_id": job_id}), 202


@app.route('/api/breeze/voice-design/preview', methods=['POST'])
def breeze_voice_design_preview():
    marker = Path(__file__).resolve().parent / "engines" / "breeze_tts_2" / ".license_accepted"
    if not _breeze_runtime_ready() or not marker.is_file():
        return jsonify({
            "success": False,
            "error": (
                "Breeze TTS 2 Voice Design is not ready. Install Breeze TTS 2 and accept its "
                "Research and Non-Commercial License under Settings → Engine Settings."
            ),
        }), 400
    payload = request.get_json(silent=True) or {}
    if not (payload.get("text") or "").strip():
        return jsonify({"success": False, "error": "Text is required to generate a preview."}), 400
    job_id = _enqueue_breeze_voice_design_task("breeze_voice_design_preview", payload)
    return jsonify({"success": True, "job_id": job_id}), 202


@app.route('/api/breeze/voice-design/save', methods=['POST'])
def breeze_voice_design_save():
    marker = Path(__file__).resolve().parent / "engines" / "breeze_tts_2" / ".license_accepted"
    if not isolated_engine_available("breeze_tts_2") or not marker.is_file():
        return jsonify({
            "success": False,
            "error": "Breeze TTS 2 Voice Design is not installed or its license has not been accepted.",
        }), 400
    payload = request.get_json(silent=True) or {}
    if not (payload.get("name") or "").strip():
        return jsonify({"success": False, "error": "Voice name is required."}), 400
    if not (payload.get("text") or "").strip():
        return jsonify({"success": False, "error": "Sample text is required."}), 400
    audio_base64 = payload.get("audio_base64")
    if not audio_base64:
        return jsonify({"success": False, "error": "Preview audio is required."}), 400
    try:
        base64.b64decode(audio_base64)
    except Exception:
        return jsonify({"success": False, "error": "Invalid audio payload."}), 400
    job_id = _enqueue_breeze_voice_design_task("breeze_voice_design_save", payload)
    return jsonify({"success": True, "job_id": job_id}), 202


@app.route('/api/qwen3/voice-design/tasks/<task_id>', methods=['GET'])
def qwen3_voice_design_task_status(task_id: str):
    with queue_lock:
        job_entry = jobs.get(task_id)
        if not job_entry:
            return jsonify({"success": False, "error": "Task not found."}), 404
        if job_entry.get("job_type") not in {"qwen3_voice_design_preview", "qwen3_voice_design_save"}:
            return jsonify({"success": False, "error": "Task type mismatch."}), 400
        payload = {
            "success": True,
            "status": job_entry.get("status"),
            "progress": job_entry.get("progress"),
        }
        if job_entry.get("status") == "completed":
            payload["result"] = job_entry.get("result")
        if job_entry.get("status") == "failed":
            payload["error"] = job_entry.get("error")
        return jsonify(payload)


@app.route('/api/qwen3/voice-design/tasks/<task_id>', methods=['DELETE'])
def qwen3_voice_design_task_delete(task_id: str):
    """Acknowledge a terminal casting task and release its in-memory audio."""
    with queue_lock:
        job_entry = jobs.get(task_id)
        if not job_entry:
            return jsonify({"success": True, "removed": False})
        if job_entry.get("job_type") not in {"qwen3_voice_design_preview", "qwen3_voice_design_save"}:
            return jsonify({"success": False, "error": "Task type mismatch."}), 400
        if job_entry.get("status") not in {"completed", "failed", "cancelled", "interrupted"}:
            return jsonify({"success": False, "error": "Task is still active."}), 409
        jobs.pop(task_id, None)
    try:
        with _get_jobs_db_connection() as conn:
            conn.execute("DELETE FROM jobs WHERE job_id=?", (task_id,))
            conn.commit()
    except Exception as exc:
        logger.warning("Unable to remove acknowledged voice-design task %s: %s", task_id, exc)
    return jsonify({"success": True, "removed": True})


@app.route('/api/breeze/voice-design/tasks/<task_id>', methods=['GET'])
def breeze_voice_design_task_status(task_id: str):
    with queue_lock:
        job_entry = jobs.get(task_id)
        if not job_entry:
            return jsonify({"success": False, "error": "Task not found."}), 404
        if job_entry.get("job_type") not in {"breeze_voice_design_preview", "breeze_voice_design_save"}:
            return jsonify({"success": False, "error": "Task type mismatch."}), 400
        payload = {
            "success": True,
            "status": job_entry.get("status"),
            "progress": job_entry.get("progress", 0),
        }
        if job_entry.get("status") == "completed":
            payload["result"] = job_entry.get("result")
        if job_entry.get("status") == "failed":
            payload["error"] = job_entry.get("error")
        return jsonify(payload)


@app.route('/api/breeze/voice-design/tasks/<task_id>', methods=['DELETE'])
def breeze_voice_design_task_delete(task_id: str):
    with queue_lock:
        job_entry = jobs.get(task_id)
        if not job_entry:
            return jsonify({"success": True, "removed": False})
        if job_entry.get("job_type") not in {"breeze_voice_design_preview", "breeze_voice_design_save"}:
            return jsonify({"success": False, "error": "Task type mismatch."}), 400
        if job_entry.get("status") not in {"completed", "failed", "cancelled", "interrupted"}:
            return jsonify({"success": False, "error": "Task is still active."}), 409
        jobs.pop(task_id, None)
    try:
        with _get_jobs_db_connection() as conn:
            conn.execute("DELETE FROM jobs WHERE job_id=?", (task_id,))
            conn.commit()
    except Exception as exc:
        logger.warning("Unable to remove acknowledged Breeze voice-design task %s: %s", task_id, exc)
    return jsonify({"success": True, "removed": True})


@app.route('/api/voice-design/candidates/approve', methods=['POST'])
@app.route('/api/qwen3/voice-design/candidates/approve', methods=['POST'])
def qwen3_voice_design_approve_candidate():
    payload = request.get_json(silent=True) or {}
    selected_id = (payload.get("selected_id") or "").strip()
    group_id = (payload.get("candidate_group_id") or "").strip()
    candidate_ids = {
        str(candidate_id).strip()
        for candidate_id in (payload.get("candidate_ids") or [])
        if str(candidate_id).strip()
    }
    candidate_ids.add(selected_id)
    if not selected_id or not group_id:
        return jsonify({"success": False, "error": "Candidate and group IDs are required."}), 400
    entries = _load_chatterbox_voice_entries()
    selected = None
    for entry in entries:
        metadata = entry.get("voice_design") or {}
        belongs_to_group = metadata.get("candidate_group_id") == group_id
        belongs_to_legacy_group = entry.get("id") in candidate_ids
        if not belongs_to_group and not belongs_to_legacy_group:
            continue
        approved = entry.get("id") == selected_id
        metadata["candidate_group_id"] = group_id
        metadata["approval_status"] = "approved" if approved else "rejected"
        entry["voice_design"] = metadata
        entry["archived"] = not approved
        if approved:
            selected = entry
    if not selected:
        return jsonify({"success": False, "error": "Selected candidate was not found."}), 404
    _save_chatterbox_voice_entries(entries)
    return jsonify({"success": True, "voice": _serialize_chatterbox_voice(selected)})


@app.route('/api/omnivoice/voice-design/preview', methods=['POST'])
def omnivoice_voice_design_preview():
    if not omnivoice_available():
        return jsonify({
            "success": False,
            "error": f"OmniVoice design engine not available. {omnivoice_unavailable_reason()} Install OmniVoice from Settings."
        }), 400
    payload = request.get_json(silent=True) or {}
    text = (payload.get("text") or "").strip()
    instruct = (payload.get("instruct") or "").strip()
    if not text:
        return jsonify({"success": False, "error": "Text is required to generate a preview."}), 400
    if not instruct:
        return jsonify({"success": False, "error": "Voice instruction string is required."}), 400
    job_id = _enqueue_omnivoice_design_task("omnivoice_design_preview", payload)
    return jsonify({"success": True, "job_id": job_id}), 202


@app.route('/api/omnivoice/voice-design/save', methods=['POST'])
def omnivoice_voice_design_save():
    if not omnivoice_available():
        return jsonify({
            "success": False,
            "error": f"OmniVoice design engine not available. {omnivoice_unavailable_reason()} Install OmniVoice from Settings."
        }), 400
    payload = request.get_json(silent=True) or {}
    name = (payload.get("name") or "").strip()
    text = (payload.get("text") or "").strip()
    audio_base64 = payload.get("audio_base64")
    if not name:
        return jsonify({"success": False, "error": "Voice name is required."}), 400
    if not text:
        return jsonify({"success": False, "error": "Sample text is required."}), 400
    if not audio_base64:
        return jsonify({"success": False, "error": "Preview audio is required."}), 400
    try:
        base64.b64decode(audio_base64)
    except Exception:
        return jsonify({"success": False, "error": "Invalid audio payload."}), 400
    job_id = _enqueue_omnivoice_design_task("omnivoice_design_save", payload)
    return jsonify({"success": True, "job_id": job_id}), 202


@app.route('/api/omnivoice/voice-design/tasks/<task_id>', methods=['GET'])
def omnivoice_voice_design_task_status(task_id: str):
    with queue_lock:
        job_entry = jobs.get(task_id)
        if not job_entry:
            return jsonify({"success": False, "error": "Task not found."}), 404
        if job_entry.get("job_type") not in {"omnivoice_design_preview", "omnivoice_design_save"}:
            return jsonify({"success": False, "error": "Task type mismatch."}), 400
        payload = {
            "success": True,
            "status": job_entry.get("status"),
            "progress": job_entry.get("progress"),
        }
        if job_entry.get("status") == "completed":
            payload["result"] = job_entry.get("result")
        if job_entry.get("status") == "failed":
            payload["error"] = job_entry.get("error")
        return jsonify(payload)


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
    _init_jobs_db()
    _purge_stale_jobs()
    _restore_jobs_from_db()
    _archive_old_jobs()
    _cleanup_orphaned_chatterbox_voices()
    _auto_register_voice_prompt_files()
    _cleanup_orphaned_regen_folders()
    if os.environ.get("WERKZEUG_RUN_MAIN") != "true" and os.environ.get("TTS_STORY_SKIP_BROWSER") != "1":
        threading.Timer(1.5, lambda: webbrowser.open("http://localhost:5000")).start()
    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)
