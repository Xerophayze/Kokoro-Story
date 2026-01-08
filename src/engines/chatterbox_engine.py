"""Chatterbox API-backed TTS engine implementation."""
from __future__ import annotations

import base64
import io
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import librosa
import numpy as np
import requests
import soundfile as sf

from .base import EngineCapabilities, TtsEngineBase, VoiceAssignment

logger = logging.getLogger(__name__)

DEFAULT_CHATTERBOX_BASE_URL = "https://api.chatterbox.ai"
DEFAULT_CHATTERBOX_MODEL = "turbo"
CHATTERBOX_NATIVE_SAMPLE_RATE = 44100


class ChatterboxEngine(TtsEngineBase):
    """Adapter that communicates with the Chatterbox HTTP API."""

    name = "chatterbox"
    capabilities = EngineCapabilities(
        supports_voice_cloning=True,
        supports_emotion_tags=True,
        supported_languages=["en", "es", "fr", "de", "pt", "ja", "ko", "zh", "hi"],
    )

    def __init__(
        self,
        api_key: str,
        base_url: str = DEFAULT_CHATTERBOX_BASE_URL,
        model: str = DEFAULT_CHATTERBOX_MODEL,
        default_voice: Optional[str] = None,
        default_language: str = "en",
        request_timeout: int = 60,
        watermark_audio: bool = True,
    ):
        super().__init__(device="cpu")
        if not api_key:
            raise ValueError("Chatterbox API key is required to initialize the engine.")

        self.base_url = base_url.rstrip("/")
        self.model = model
        self.default_voice = default_voice
        self.default_language = default_language
        self.timeout = request_timeout
        self.watermark_audio = watermark_audio

        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
        )

    # ------------------------------------------------------------------
    @property
    def sample_rate(self) -> int:
        return CHATTERBOX_NATIVE_SAMPLE_RATE

    # ------------------------------------------------------------------
    def cleanup(self) -> None:  # pragma: no cover - trivial
        try:
            self.session.close()
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------------
    def generate_audio(
        self,
        text: str,
        voice: Optional[str],
        lang_code: Optional[str] = None,
        speed: float = 1.0,
        sample_rate: Optional[int] = None,
        audio_prompt_path: Optional[str] = None,
        fx_settings=None,  # Future-use placeholder to keep signature aligned
        extra: Optional[Dict] = None,
    ) -> np.ndarray:
        assignment = VoiceAssignment(
            voice=voice or self.default_voice,
            lang_code=lang_code or self.default_language,
            audio_prompt_path=audio_prompt_path,
            speed_override=speed,
            extra=extra or {},
        )
        target_sr = sample_rate or self.sample_rate
        audio_array, _ = self._synthesize(
            text=text,
            assignment=assignment,
            speed=speed,
            sample_rate=target_sr,
        )
        return audio_array

    # ------------------------------------------------------------------
    def generate_batch(
        self,
        segments: List[Dict],
        voice_config: Dict[str, Dict],
        output_dir: Path,
        speed: float = 1.0,
        sample_rate: Optional[int] = None,
        progress_cb=None,
        chunk_cb=None,
    ) -> List[str]:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        target_sample_rate = sample_rate or self.sample_rate
        output_files: List[str] = []
        chunk_index = 0

        for seg_idx, segment in enumerate(segments):
            speaker = segment["speaker"]
            chunks = segment["chunks"]

            assignment = self._voice_assignment_for(voice_config, speaker)
            logger.info(
                "Chatterbox segment %s/%s speaker=%s voice=%s",
                seg_idx + 1,
                len(segments),
                speaker,
                assignment.voice or self.default_voice,
            )

            for chunk_idx, chunk_text in enumerate(chunks):
                output_path = output_dir / f"chunk_{chunk_index:04d}.wav"

                audio_array, sr = self._synthesize(
                    text=chunk_text,
                    assignment=assignment,
                    speed=speed,
                    sample_rate=target_sample_rate,
                )
                sf.write(str(output_path), audio_array, sr)
                output_files.append(str(output_path))
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
                    chunk_cb(chunk_index - 1, chunk_meta, str(output_path))

        return output_files

    # ------------------------------------------------------------------
    def _voice_assignment_for(self, voice_config: Dict[str, Dict], speaker: str) -> VoiceAssignment:
        payload = voice_config.get(speaker) or voice_config.get("default") or {}
        return VoiceAssignment(
            voice=payload.get("voice") or self.default_voice,
            lang_code=payload.get("lang_code") or self.default_language,
            audio_prompt_path=payload.get("audio_prompt_path"),
            fx_payload=payload.get("fx"),
            speed_override=payload.get("speed"),
            extra=payload.get("extra") or {},
        )

    # ------------------------------------------------------------------
    def _synthesize(
        self,
        text: str,
        assignment: VoiceAssignment,
        speed: float,
        sample_rate: int,
    ) -> Tuple[np.ndarray, int]:
        payload = {
            "text": text,
            "model": self.model,
            "language": assignment.lang_code or self.default_language,
            "voice": assignment.voice or self.default_voice,
            "speed": assignment.speed_override or speed,
            "sample_rate": sample_rate,
            "watermark": self.watermark_audio,
        }

        extra = assignment.extra or {}
        tags = extra.get("paralinguistic_tags") or extra.get("tags")
        if tags:
            payload["tags"] = tags
        emotion = extra.get("emotion")
        if emotion:
            payload["emotion"] = emotion

        if assignment.audio_prompt_path:
            prompt_b64 = self._load_audio_prompt(assignment.audio_prompt_path)
            if prompt_b64:
                payload["voice_prompt"] = prompt_b64

        endpoint = f"{self.base_url}/v1/tts"
        response = self.session.post(endpoint, json=payload, timeout=self.timeout)
        if response.status_code >= 400:
            try:
                detail = response.json().get("error")
            except Exception:  # noqa: BLE001
                detail = response.text
            raise RuntimeError(f"Chatterbox synthesis failed ({response.status_code}): {detail}")

        data = response.json()
        audio_b64 = data.get("audio_base64") or data.get("audio")
        if not audio_b64:
            raise RuntimeError("Chatterbox response did not include audio data.")

        audio_array, response_sr = self._decode_audio(audio_b64)
        if response_sr != sample_rate:
            audio_array = librosa.resample(audio_array, orig_sr=response_sr, target_sr=sample_rate)
            response_sr = sample_rate

        return audio_array, response_sr

    # ------------------------------------------------------------------
    def _decode_audio(self, audio_b64: str) -> Tuple[np.ndarray, int]:
        audio_bytes = base64.b64decode(audio_b64)
        buffer = io.BytesIO(audio_bytes)
        audio_array, sr = sf.read(buffer, dtype="float32")
        if audio_array.ndim > 1:
            audio_array = np.mean(audio_array, axis=1)
        return audio_array, sr

    # ------------------------------------------------------------------
    def _load_audio_prompt(self, path_str: str) -> Optional[str]:
        candidate = Path(path_str)
        if not candidate.is_file():
            alt = Path("data/voice_prompts") / path_str
            if alt.is_file():
                candidate = alt
        if not candidate.is_file():
            logger.warning("Audio prompt file missing: %s", path_str)
            return None
        try:
            data = candidate.read_bytes()
        except OSError as exc:
            logger.error("Failed to read audio prompt %s: %s", path_str, exc)
            return None
        return base64.b64encode(data).decode("ascii")


__all__ = [
    "ChatterboxEngine",
    "DEFAULT_CHATTERBOX_BASE_URL",
    "DEFAULT_CHATTERBOX_MODEL",
    "CHATTERBOX_NATIVE_SAMPLE_RATE",
]
