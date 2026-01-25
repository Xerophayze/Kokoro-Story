"""Local  VoxCPM 1.5 engine adapter."""
from __future__ import annotations

import gc
import hashlib
import json
import logging
import os
import re
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import soundfile as sf
import torch

from .base import EngineCapabilities, TtsEngineBase, VoiceAssignment
from ..audio_effects import AudioPostProcessor, VoiceFXSettings

logger = logging.getLogger(__name__)

# Disable HuggingFace Hub symlinks warning on Windows
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

try:
    from huggingface_hub import snapshot_download
    from voxcpm import VoxCPM  # type: ignore

    VOXCPM_AVAILABLE = True
except ImportError:  # pragma: no cover - optional dependency
    VoxCPM = None  # type: ignore[assignment]
    snapshot_download = None  # type: ignore[assignment]
    VOXCPM_AVAILABLE = False

# Try to import SenseVoice for automatic transcription
try:
    from funasr import AutoModel as FunASRAutoModel
    SENSEVOICE_AVAILABLE = True
except ImportError:
    FunASRAutoModel = None  # type: ignore[assignment]
    SENSEVOICE_AVAILABLE = False


class VoxCPMLocalEngine(TtsEngineBase):
    """Offline VoxCPM engine with voice cloning support."""

    name = "voxcpm_local"
    capabilities = EngineCapabilities(
        supports_voice_cloning=True,
        supports_emotion_tags=True,
        supported_languages=["en", "zh"],
    )

    def __init__(
        self,
        *,
        device: str = "auto",
        model_id: str = "openbmb/VoxCPM1.5",
        default_prompt: Optional[str] = None,
        default_prompt_text: Optional[str] = None,
        cfg_value: float = 2.0,  # Lower CFG for stability - high values cause artifacts/skips
        inference_timesteps: int = 32,  # More steps = smoother audio, fewer artifacts
        normalize: bool = True,  # Enable text normalization for numbers/abbreviations
        denoise: bool = False,
    ):
        if not VOXCPM_AVAILABLE:
            raise ImportError("voxcpm is not installed. Run setup to enable VoxCPM local mode.")

        resolved_device = self._resolve_device(device)
        logger.info("Loading VoxCPM model=%s device=%s", model_id, resolved_device)

        # Download model to local directory to avoid Windows symlink issues
        # Use a local cache directory within the project to bypass HF Hub symlink requirements
        local_model_dir = Path(__file__).parent.parent.parent / "models" / "voxcpm"
        local_model_dir.mkdir(parents=True, exist_ok=True)
        model_path = local_model_dir / model_id.replace("/", "_")

        if not model_path.exists() or not any(model_path.iterdir()):
            logger.info("Downloading VoxCPM model to %s (this may take a few minutes)...", model_path)
            snapshot_download(
                repo_id=model_id,
                local_dir=str(model_path),
                local_dir_use_symlinks=False,
            )

        # VoxCPM handles device placement internally during from_pretrained
        self.model = VoxCPM.from_pretrained(str(model_path))

        self.device = resolved_device
        self.model_id = model_id
        self.default_prompt = default_prompt
        self.default_prompt_text = default_prompt_text
        self.cfg_value = float(cfg_value)
        self.inference_timesteps = int(inference_timesteps)
        self.normalize = bool(normalize)
        self.denoise = bool(denoise)
        self.post_processor = AudioPostProcessor()

        # Initialize ASR model for automatic transcription (lazy loaded)
        self._asr_model = None
        self._transcript_cache: Dict[str, str] = {}  # In-memory cache
        
        # Persistent transcript storage in data/voice_prompts/transcripts.json
        self._transcripts_file = Path(__file__).parent.parent.parent / "data" / "voice_prompts" / "transcripts.json"
        self._load_persistent_transcripts()

    @property
    def sample_rate(self) -> int:
        try:
            return int(self.model.tts_model.sample_rate)
        except Exception:
            return 44100

    def generate_batch(
        self,
        segments: List[Dict],
        voice_config: Dict[str, Dict],
        output_dir: Path,
        speed: float = 1.0,
        sample_rate: Optional[int] = None,
        progress_cb=None,
        chunk_cb=None,
        parallel_workers: int = 1,
    ) -> List[str]:
        if sample_rate and sample_rate != self.sample_rate:
            logger.warning(
                "VoxCPM outputs at %s Hz. Requested sample rate %s will be resampled during merge.",
                self.sample_rate,
                sample_rate,
            )
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        files: List[str] = []
        chunk_index = 0
        for seg_idx, segment in enumerate(segments):
            speaker = segment["speaker"]
            chunks = segment["chunks"]
            assignment = self._voice_assignment_for(voice_config, speaker)
            logger.info(
                "VoxCPM segment %s/%s speaker=%s voice_prompt=%s",
                seg_idx + 1,
                len(segments),
                speaker,
                assignment.audio_prompt_path,
            )

            for chunk_idx, chunk_text in enumerate(chunks):
                output_path = output_dir / f"chunk_{chunk_index:04d}.wav"
                audio = self._synthesize(chunk_text, assignment)
                fx_settings = VoiceFXSettings.from_payload(assignment.fx_payload)
                if fx_settings:
                    audio = self.post_processor.apply(audio, self.sample_rate, fx_settings)
                sf.write(str(output_path), audio, self.sample_rate)
                files.append(str(output_path))
                chunk_index += 1
                if callable(progress_cb):
                    progress_cb()
                if callable(chunk_cb):
                    chunk_meta = {
                        "speaker": speaker,
                        "text": chunk_text,
                        "segment_index": seg_idx,
                        "chunk_index": chunk_idx,
                    }
                    chunk_cb(chunk_idx, chunk_meta, str(output_path))

        return files

    def cleanup(self) -> None:  # pragma: no cover
        logger.info("Cleaning up VoxCPM Local engine resources")
        try:
            # Unload ASR model first (SenseVoice)
            if hasattr(self, "_asr_model") and self._asr_model is not None:
                logger.info("Unloading SenseVoice ASR model")
                del self._asr_model
                self._asr_model = None
        except Exception:
            pass
        try:
            # Unload main VoxCPM model
            if hasattr(self, "model") and self.model is not None:
                logger.info("Unloading VoxCPM TTS model")
                del self.model
                self.model = None
        except Exception:
            pass
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            allocated = torch.cuda.memory_allocated(0) / 1024**3
            logger.info("GPU memory after VoxCPM cleanup: %.2f GB", allocated)

    def _voice_assignment_for(self, voice_config: Dict[str, Dict], speaker: str) -> VoiceAssignment:
        payload = voice_config.get(speaker) or voice_config.get("default") or {}
        return VoiceAssignment(
            voice=payload.get("voice"),
            lang_code=payload.get("lang_code"),
            audio_prompt_path=payload.get("audio_prompt_path"),
            fx_payload=payload.get("fx"),
            speed_override=payload.get("speed"),
            extra=payload.get("extra") or {},
        )

    def _resolve_prompt_path(self, prompt_path: Optional[str]) -> Optional[str]:
        if not prompt_path:
            return None
        resolved = Path(prompt_path)
        if resolved.exists():
            final_path = str(resolved)
        else:
            # Check in data/voice_prompts directory (shared with Chatterbox)
            voice_prompts_dir = Path(__file__).parent.parent.parent / "data" / "voice_prompts"
            in_prompts_dir = voice_prompts_dir / prompt_path
            if in_prompts_dir.exists():
                final_path = str(in_prompts_dir)
            # Also check if it's just a filename without the directory prefix
            elif not resolved.is_absolute():
                in_prompts_dir_name = voice_prompts_dir / Path(prompt_path).name
                if in_prompts_dir_name.exists():
                    final_path = str(in_prompts_dir_name)
                else:
                    raise FileNotFoundError(f"Prompt file not found: {prompt_path}")
            else:
                raise FileNotFoundError(f"Prompt file not found: {prompt_path}")
        
        # Warn about lossy formats that can cause audio artifacts
        ext = Path(final_path).suffix.lower()
        if ext in (".mp3", ".aac", ".ogg", ".m4a", ".wma"):
            logger.warning(
                "Voice prompt '%s' uses lossy compression (%s). "
                "This can cause audio artifacts and skips in generated speech. "
                "For best quality, use WAV or FLAC files.",
                Path(final_path).name, ext
            )
        
        return final_path

    def _get_audio_hash(self, audio_path: str) -> str:
        """Get a hash key for an audio file based on filename and modification time."""
        path = Path(audio_path)
        # Use filename + file size + mtime for a quick unique key
        stat = path.stat()
        key_data = f"{path.name}:{stat.st_size}:{stat.st_mtime}"
        return hashlib.md5(key_data.encode()).hexdigest()[:16]

    def _load_persistent_transcripts(self) -> None:
        """Load transcripts from JSON file."""
        if self._transcripts_file.exists():
            try:
                with open(self._transcripts_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._transcript_cache = data.get("transcripts", {})
                    logger.info("Loaded %d cached transcripts from %s", 
                               len(self._transcript_cache), self._transcripts_file.name)
            except Exception as e:
                logger.warning("Failed to load transcripts file: %s", e)
                self._transcript_cache = {}

    def _save_persistent_transcripts(self) -> None:
        """Save transcripts to JSON file."""
        try:
            self._transcripts_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self._transcripts_file, "w", encoding="utf-8") as f:
                json.dump({"transcripts": self._transcript_cache}, f, indent=2, ensure_ascii=False)
            logger.debug("Saved %d transcripts to %s", len(self._transcript_cache), self._transcripts_file.name)
        except Exception as e:
            logger.warning("Failed to save transcripts file: %s", e)

    def _transcribe_audio(self, audio_path: str) -> Optional[str]:
        """Automatically transcribe reference audio using SenseVoice ASR."""
        # Use a hash key that includes file metadata for cache lookup
        cache_key = self._get_audio_hash(audio_path)
        
        # Check persistent cache first
        if cache_key in self._transcript_cache:
            logger.info("Using cached transcript for %s", Path(audio_path).name)
            return self._transcript_cache[cache_key]

        if not SENSEVOICE_AVAILABLE:
            logger.warning("SenseVoice (funasr) not available for automatic transcription. "
                          "Install with: pip install funasr")
            return None

        try:
            # Lazy load ASR model
            if self._asr_model is None:
                logger.info("Loading SenseVoice ASR model for automatic transcription...")
                self._asr_model = FunASRAutoModel(
                    model="iic/SenseVoiceSmall",
                    trust_remote_code=True,
                    device=self.device,
                    disable_update=True,  # Prevent network check on every load
                )

            # Transcribe the audio
            result = self._asr_model.generate(input=audio_path, batch_size_s=0)
            if result and len(result) > 0:
                # SenseVoice returns list of dicts with 'text' key
                transcript = result[0].get("text", "").strip()
                if transcript:
                    # Clean SenseVoice special tags like <|en|><|NEUTRAL|><|Speech|><|woitn|>
                    transcript = re.sub(r'<\|[^|]+\|>', '', transcript).strip()
                    if transcript:
                        # Cache the result persistently
                        self._transcript_cache[cache_key] = transcript
                        self._save_persistent_transcripts()
                        logger.info("Auto-transcribed and cached: %s -> %r", Path(audio_path).name, transcript[:80])
                        return transcript
        except Exception as e:
            logger.warning("Failed to auto-transcribe reference audio: %s", e)

        return None

    def _synthesize(self, text: str, assignment: VoiceAssignment) -> np.ndarray:
        prompt_path = assignment.audio_prompt_path or self.default_prompt
        prompt_text = assignment.extra.get("prompt_text") or self.default_prompt_text

        if prompt_path:
            prompt_path = self._resolve_prompt_path(prompt_path)

        # VoxCPM requires BOTH prompt_wav_path and prompt_text, or NEITHER
        # If we have a prompt audio but no transcript, try automatic transcription
        if prompt_path and not prompt_text:
            logger.info("No transcript provided for reference audio, attempting automatic transcription...")
            prompt_text = self._transcribe_audio(prompt_path)
            if not prompt_text:
                logger.warning(
                    "VoxCPM voice cloning requires a transcript (prompt_text) for the reference audio. "
                    "Auto-transcription failed. Falling back to no voice cloning."
                )
                prompt_path = None

        logger.info("VoxCPM generating: text=%r prompt_path=%s prompt_text=%s",
                    text[:50], prompt_path, prompt_text[:30] if prompt_text else None)
        wav = self.model.generate(
            text=text,
            prompt_wav_path=prompt_path,
            prompt_text=prompt_text,
            cfg_value=self.cfg_value,
            inference_timesteps=self.inference_timesteps,
            normalize=self.normalize,
            denoise=self.denoise,
            retry_badcase=True,
            retry_badcase_max_times=3,
            retry_badcase_ratio_threshold=6.0,
        )
        audio = np.asarray(wav, dtype=np.float32)
        
        # Normalize audio to prevent clipping and reduce artifacts
        max_val = np.abs(audio).max()
        if max_val > 0:
            # Normalize to 0.95 to leave headroom and prevent clipping
            audio = audio / max_val * 0.95
        
        return audio

    def _resolve_device(self, device: str) -> str:
        device = (device or "auto").strip().lower()
        if device == "auto":
            return "cuda" if torch.cuda.is_available() else "cpu"
        return device
