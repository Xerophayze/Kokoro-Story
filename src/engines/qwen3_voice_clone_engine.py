"""Local Qwen3-TTS Voice Clone engine adapter."""
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
    from qwen_tts import Qwen3TTSModel  # type: ignore

    QWEN3_AVAILABLE = True
except ImportError:  # pragma: no cover - optional dependency
    Qwen3TTSModel = None  # type: ignore[assignment]
    snapshot_download = None  # type: ignore[assignment]
    QWEN3_AVAILABLE = False

# Try to import SenseVoice for automatic transcription
try:
    from funasr import AutoModel as FunASRAutoModel

    SENSEVOICE_AVAILABLE = True
except ImportError:
    FunASRAutoModel = None  # type: ignore[assignment]
    SENSEVOICE_AVAILABLE = False


class Qwen3VoiceCloneEngine(TtsEngineBase):
    """Offline Qwen3-TTS Voice Clone engine (Base model)."""

    name = "qwen3_clone"
    capabilities = EngineCapabilities(
        supports_voice_cloning=True,
        supports_emotion_tags=False,
    )

    def __init__(
        self,
        *,
        device: str = "auto",
        model_id: str = "Qwen/Qwen3-TTS-12Hz-1.7B-Base",
        dtype: str = "bfloat16",
        attn_implementation: str = "flash_attention_2",
        default_language: str = "Auto",
        default_prompt: Optional[str] = None,
        default_prompt_text: Optional[str] = None,
    ):
        if not QWEN3_AVAILABLE:
            raise ImportError("qwen-tts is not installed. Run setup to enable Qwen3-TTS local mode.")

        resolved_device = self._resolve_device(device)
        resolved_dtype = self._resolve_dtype(dtype)
        resolved_attn = self._resolve_attn_implementation(attn_implementation)
        logger.info(
            "Loading Qwen3 Voice Clone model=%s device=%s dtype=%s attn=%s",
            model_id,
            resolved_device,
            resolved_dtype,
            resolved_attn or "auto",
        )

        model_path = self._ensure_model(model_id)
        self.model = Qwen3TTSModel.from_pretrained(
            str(model_path),
            device_map=resolved_device,
            dtype=resolved_dtype,
            attn_implementation=resolved_attn or None,
        )

        self.device = resolved_device
        self.model_id = model_id
        self.default_language = default_language or "Auto"
        self.default_prompt = default_prompt
        self.default_prompt_text = default_prompt_text
        self.post_processor = AudioPostProcessor()

        self._sample_rate = None
        self._supported_languages = self._safe_supported_list("languages")

        self._asr_model = None
        self._transcript_cache: Dict[str, str] = {}
        self._transcripts_file = Path(__file__).parent.parent.parent / "data" / "voice_prompts" / "transcripts.json"
        self._load_persistent_transcripts()

    @property
    def sample_rate(self) -> int:
        return self._sample_rate or 24000

    @property
    def supported_languages(self) -> List[str]:
        return list(self._supported_languages or [])

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
                "Qwen3 outputs at %s Hz. Requested sample rate %s will be resampled during merge.",
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
            language = (assignment.extra.get("language") if assignment.extra else None) or self.default_language
            prompt_path = assignment.audio_prompt_path or self.default_prompt
            prompt_text = assignment.extra.get("prompt_text") or self.default_prompt_text

            if prompt_path:
                prompt_path = self._resolve_prompt_path(prompt_path)

            if prompt_path and not prompt_text:
                prompt_text = self._transcribe_audio(prompt_path)

            if not prompt_path:
                raise ValueError("Qwen3 Voice Clone requires a reference audio prompt.")

            x_vector_only_mode = False
            if not prompt_text:
                logger.warning(
                    "No transcript available for %s. Using x_vector_only_mode=True (quality may be reduced).",
                    Path(prompt_path).name if prompt_path else "unknown",
                )
                x_vector_only_mode = True

            logger.info(
                "Qwen3 Voice Clone segment %s/%s speaker=%s language=%s prompt=%s",
                seg_idx + 1,
                len(segments),
                speaker,
                language,
                Path(prompt_path).name if prompt_path else None,
            )

            for chunk_idx, chunk_text in enumerate(chunks):
                output_path = output_dir / f"chunk_{chunk_index:04d}.wav"
                wavs, sr = self.model.generate_voice_clone(
                    text=chunk_text,
                    language=language or "Auto",
                    ref_audio=prompt_path,
                    ref_text=prompt_text or "",
                    x_vector_only_mode=x_vector_only_mode,
                )
                audio = np.asarray(wavs[0], dtype=np.float32)
                self._sample_rate = int(sr)
                fx_settings = VoiceFXSettings.from_payload(assignment.fx_payload)
                if fx_settings:
                    audio = self.post_processor.apply(audio, int(sr), fx_settings)
                sf.write(str(output_path), audio, int(sr))
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
        logger.info("Cleaning up Qwen3 Voice Clone engine resources")
        try:
            if hasattr(self, "_asr_model") and self._asr_model is not None:
                del self._asr_model
                self._asr_model = None
        except Exception:
            pass
        try:
            if hasattr(self, "model") and self.model is not None:
                del self.model
                self.model = None
        except Exception:
            pass
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

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
        if resolved.is_file():
            return str(resolved)
        fallback = Path(__file__).parent.parent.parent / "data" / "voice_prompts" / prompt_path
        if fallback.is_file():
            return str(fallback)
        return str(resolved)

    def _get_audio_hash(self, audio_path: str) -> str:
        path = Path(audio_path)
        stat = path.stat()
        key_data = f"{path.name}:{stat.st_size}:{stat.st_mtime}"
        return hashlib.md5(key_data.encode()).hexdigest()[:16]

    def _load_persistent_transcripts(self) -> None:
        if self._transcripts_file.exists():
            try:
                with open(self._transcripts_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._transcript_cache = data.get("transcripts", {})
                    logger.info(
                        "Loaded %d cached transcripts from %s",
                        len(self._transcript_cache),
                        self._transcripts_file.name,
                    )
            except Exception as exc:
                logger.warning("Failed to load transcripts file: %s", exc)
                self._transcript_cache = {}

    def _save_persistent_transcripts(self) -> None:
        try:
            self._transcripts_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self._transcripts_file, "w", encoding="utf-8") as f:
                json.dump({"transcripts": self._transcript_cache}, f, indent=2, ensure_ascii=False)
        except Exception as exc:
            logger.warning("Failed to save transcripts file: %s", exc)

    def _transcribe_audio(self, audio_path: Optional[str]) -> Optional[str]:
        if not audio_path:
            return None
        cache_key = self._get_audio_hash(audio_path)
        if cache_key in self._transcript_cache:
            return self._transcript_cache[cache_key]
        if not SENSEVOICE_AVAILABLE:
            logger.warning("SenseVoice (funasr) not available for automatic transcription.")
            return None
        try:
            if self._asr_model is None:
                logger.info("Loading SenseVoice ASR model for Qwen3 voice clone transcription...")
                self._asr_model = FunASRAutoModel(
                    model="iic/SenseVoiceSmall",
                    trust_remote_code=True,
                    device=self.device,
                    disable_update=True,
                )
            result = self._asr_model.generate(input=audio_path, batch_size_s=0)
            if result and len(result) > 0:
                transcript = result[0].get("text", "").strip()
                if transcript:
                    transcript = re.sub(r"<\|[^|]+\|>", "", transcript).strip()
                if transcript:
                    self._transcript_cache[cache_key] = transcript
                    self._save_persistent_transcripts()
                    logger.info("Auto-transcribed and cached: %s -> %r", Path(audio_path).name, transcript[:80])
                    return transcript
        except Exception as exc:
            logger.warning("Failed to auto-transcribe reference audio: %s", exc)
        return None

    def _ensure_model(self, model_id: str) -> Path:
        local_model_dir = Path(__file__).parent.parent.parent / "models" / "qwen3"
        local_model_dir.mkdir(parents=True, exist_ok=True)
        model_path = local_model_dir / model_id.replace("/", "_")

        if not model_path.exists() or not any(model_path.iterdir()):
            logger.info("Downloading Qwen3 model to %s (this may take a few minutes)...", model_path)
            snapshot_download(
                repo_id=model_id,
                local_dir=str(model_path),
                local_dir_use_symlinks=False,
            )
        return model_path

    def _safe_supported_list(self, list_type: str) -> List[str]:
        getter = None
        if list_type == "languages":
            getter = getattr(self.model, "get_supported_languages", None)
        if callable(getter):
            try:
                return list(getter())
            except Exception:
                logger.warning("Failed to load Qwen3 supported %s", list_type, exc_info=True)
        return []

    @staticmethod
    def _resolve_device(device: str) -> str:
        candidate = (device or "auto").strip().lower()
        if candidate == "auto":
            return "cuda" if torch.cuda.is_available() else "cpu"
        if candidate.startswith("cuda") and not torch.cuda.is_available():
            raise RuntimeError("CUDA device requested but no GPU is available.")
        return candidate

    @staticmethod
    def _resolve_dtype(dtype_value: str) -> torch.dtype:
        normalized = (dtype_value or "").strip().lower()
        if normalized in {"bf16", "bfloat16"}:
            return torch.bfloat16
        if normalized in {"fp16", "float16"}:
            return torch.float16
        return torch.float32

    @staticmethod
    def _resolve_attn_implementation(attn_value: Optional[str]) -> Optional[str]:
        normalized = (attn_value or "").strip().lower().replace("-", "_")
        if normalized in {"", "auto"}:
            return None
        if normalized in {"flash_attention_2", "flash_attention2", "flash"}:
            try:
                import flash_attn  # type: ignore  # noqa: F401
            except Exception:
                logger.warning("flash-attn not installed; falling back to eager attention for Qwen3")
                return "eager"
            return "flash_attention_2"
        return normalized


__all__ = [
    "Qwen3VoiceCloneEngine",
    "QWEN3_AVAILABLE",
]
