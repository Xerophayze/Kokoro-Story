"""Local Qwen3-TTS CustomVoice engine adapter."""
from __future__ import annotations

import gc
import logging
import os
from collections import Counter
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


class Qwen3CustomVoiceEngine(TtsEngineBase):
    """Offline Qwen3-TTS CustomVoice engine."""

    name = "qwen3_custom"
    capabilities = EngineCapabilities(
        supports_voice_cloning=False,
        supports_emotion_tags=True,
    )

    def __init__(
        self,
        *,
        device: str = "auto",
        model_id: str = "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice",
        dtype: str = "bfloat16",
        attn_implementation: str = "flash_attention_2",
        default_language: str = "Auto",
        default_instruct: Optional[str] = None,
    ):
        if not QWEN3_AVAILABLE:
            raise ImportError("qwen-tts is not installed. Run setup to enable Qwen3-TTS local mode.")

        resolved_device = self._resolve_device(device)
        resolved_dtype = self._resolve_dtype(dtype)
        resolved_attn = self._resolve_attn_implementation(attn_implementation)
        logger.info(
            "Loading Qwen3 CustomVoice model=%s device=%s dtype=%s attn=%s",
            model_id,
            resolved_device,
            resolved_dtype,
            resolved_attn or "auto",
        )
        logger.warning(
            "Qwen3 attention debug: device=%s dtype=%s attn=%s",
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
        self._log_attention_backend(resolved_attn)

        self.device = resolved_device
        self.model_id = model_id
        self.default_language = default_language or "Auto"
        self.default_instruct = default_instruct
        self.post_processor = AudioPostProcessor()

        self._sample_rate = None
        self._supported_speakers = self._safe_supported_list("speakers")
        self._supported_languages = self._safe_supported_list("languages")

    @property
    def sample_rate(self) -> int:
        return self._sample_rate or 24000

    @property
    def supported_speakers(self) -> List[str]:
        return list(self._supported_speakers or [])

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
            voice_name = assignment.voice or self._fallback_speaker()
            language = (assignment.extra.get("language") if assignment.extra else None) or self.default_language
            # Emotion from segment takes priority, then user-provided instruct, then default
            segment_emotion = segment.get("emotion")
            user_instruct = (assignment.extra.get("instruct") if assignment.extra else None)
            if segment_emotion:
                # If both emotion and user instruct exist, combine them
                instruct = f"{segment_emotion}; {user_instruct}" if user_instruct else segment_emotion
            else:
                instruct = user_instruct or self.default_instruct

            if not voice_name:
                raise ValueError("Qwen3 CustomVoice requires a speaker selection.")

            logger.info(
                "Qwen3 CustomVoice segment %s/%s speaker=%s language=%s instruct=%s",
                seg_idx + 1,
                len(segments),
                voice_name,
                language,
                instruct[:50] + "..." if instruct and len(instruct) > 50 else instruct,
            )

            for chunk_idx, chunk_text in enumerate(chunks):
                output_path = output_dir / f"chunk_{chunk_index:04d}.wav"
                audio, sr = self._synthesize(chunk_text, voice_name, language, instruct)
                self._sample_rate = sr
                fx_settings = VoiceFXSettings.from_payload(assignment.fx_payload)
                if fx_settings:
                    audio = self.post_processor.apply(audio, sr, fx_settings)
                sf.write(str(output_path), audio, sr)
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
        logger.info("Cleaning up Qwen3 CustomVoice engine resources")
        try:
            if hasattr(self, "model") and self.model is not None:
                del self.model
                self.model = None
        except Exception:
            pass
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    def generate_audio(
        self,
        *,
        text: str,
        voice: str,
        lang_code: Optional[str] = None,
        speed: float = 1.0,
        sample_rate: Optional[int] = None,
        fx_settings: Optional[VoiceFXSettings] = None,
    ) -> np.ndarray:
        """Generate a single preview clip for the /api/preview endpoint."""
        language = lang_code or self.default_language
        wav, sr = self._synthesize(text, voice, language, self.default_instruct)
        self._sample_rate = sr
        audio = wav
        if fx_settings:
            audio = self.post_processor.apply(audio, sr, fx_settings)
        return audio

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

    def _synthesize(
        self,
        text: str,
        speaker: str,
        language: str,
        instruct: Optional[str],
    ) -> tuple[np.ndarray, int]:
        wavs, sr = self.model.generate_custom_voice(
            text=text,
            language=language or "Auto",
            speaker=speaker,
            instruct=instruct or "",
        )
        audio = np.asarray(wavs[0], dtype=np.float32)
        return audio, int(sr)

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

    def _fallback_speaker(self) -> Optional[str]:
        if self._supported_speakers:
            return self._supported_speakers[0]
        return None

    def _safe_supported_list(self, list_type: str) -> List[str]:
        getter = None
        if list_type == "speakers":
            getter = getattr(self.model, "get_supported_speakers", None)
        if list_type == "languages":
            getter = getattr(self.model, "get_supported_languages", None)
        if callable(getter):
            try:
                return list(getter())
            except Exception:
                logger.warning("Failed to load Qwen3 supported %s", list_type, exc_info=True)
        return []

    def _log_attention_backend(self, requested_attn: Optional[str]) -> None:
        try:
            candidates = [
                self.model,
                getattr(self.model, "model", None),
                getattr(self.model, "tts_model", None),
                getattr(self.model, "tts", None),
                getattr(self.model, "inner_model", None),
            ]
            target_model = next(
                (candidate for candidate in candidates if hasattr(candidate, "modules")), None
            )
            config = getattr(target_model or self.model, "config", None)
            config_attn = None
            if config is not None:
                config_attn = getattr(config, "attn_implementation", None) or getattr(
                    config, "_attn_implementation", None
                )
            # Check if flash_attention_2 is registered in transformers dispatch
            dispatch_available = "unknown"
            try:
                from transformers.modeling_utils import ALL_ATTENTION_FUNCTIONS
                dispatch_available = "flash_attention_2" in ALL_ATTENTION_FUNCTIONS
            except Exception:
                pass
            logger.warning(
                "Qwen3 attention audit: requested=%s config=%s dispatch_available=%s model=%s",
                requested_attn or "auto",
                config_attn or "unknown",
                dispatch_available,
                type(target_model or self.model).__name__,
            )
        except Exception:
            logger.warning("Qwen3 attention audit failed", exc_info=True)

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
                import flash_attn  # type: ignore
                logger.warning(
                    "flash-attn available (version=%s)",
                    getattr(flash_attn, "__version__", "unknown"),
                )
            except Exception:
                logger.warning(
                    "flash-attn not installed; falling back to eager attention for Qwen3"
                )
                return "eager"
            return "flash_attention_2"
        return normalized


__all__ = [
    "Qwen3CustomVoiceEngine",
    "QWEN3_AVAILABLE",
]
